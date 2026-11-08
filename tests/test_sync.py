"""Google sign-in and sync: encryption, merging two devices, and the Drive calls (Google is faked)."""
import json
import threading
import urllib.parse
import urllib.request

import httpx
import pytest

from lanterna import keys, sync
from lanterna.config import Settings
from lanterna.store import Store


@pytest.fixture
def vault(monkeypatch):
    v = {}
    monkeypatch.setattr(keys, "get_key", lambda n: v.get(n))
    monkeypatch.setattr(keys, "set_key", lambda n, k: v.__setitem__(n, k))
    monkeypatch.setattr(keys, "delete_key", lambda n: v.pop(n, None))
    monkeypatch.setattr(keys, "stored_key", lambda n: v.get(n) or "")
    monkeypatch.setattr(sync, "derive_key", lambda pw, salt: (pw.encode() * 32)[:32])   # scrypt is slow; tested once below
    return v


class FakeGoogle:
    """Token endpoint + Drive appDataFolder in memory."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.names: dict[str, str] = {}
        self.made = 0
        self.calls: list[str] = []
        self.revoked: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url, m = str(req.url), req.method
        self.calls.append(f"{m} {req.url.path}")
        if url.startswith(sync.TOKEN_URL):
            form = dict(urllib.parse.parse_qsl(req.content.decode()))
            assert form["client_id"] == sync.CLIENT_ID and form["client_secret"] == sync.CLIENT_SECRET
            if form["grant_type"] == "authorization_code":
                assert form["code"] == "the-code" and len(form["code_verifier"]) >= 43
                return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt-1", "expires_in": 3600})
            assert form["refresh_token"] == "rt-1"
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        if url.startswith(sync.REVOKE_URL):
            self.revoked.append(dict(urllib.parse.parse_qsl(req.content.decode()))["token"])
            return httpx.Response(200)
        assert req.headers["Authorization"] == "Bearer at"
        path = req.url.path
        if path.endswith("/about"):
            return httpx.Response(200, json={"user": {"emailAddress": "anna@example.com"}})
        if m == "GET" and path.endswith("/drive/v3/files"):
            assert req.url.params["spaces"] == "appDataFolder"
            want = req.url.params.get("q", "").split("'")[1] if "'" in req.url.params.get("q", "") else ""
            return httpx.Response(200, json={"files": [{"id": i} for i in self.files
                                                       if not want or self.names.get(i, sync.FILE_NAME) == want]})
        if m == "POST" and "/upload/" in path:
            assert b'"parents": ["appDataFolder"]' in req.content
            self.made += 1
            fid = f"f{self.made}"
            self.names[fid] = json.loads(req.content.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0])["name"]
            self.files[fid] = req.content.split(b"application/octet-stream\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            return httpx.Response(200, json={"id": fid})
        fid = path.rsplit("/", 1)[1]
        if m == "PATCH":
            self.files[fid] = req.content
            return httpx.Response(200, json={"id": fid})
        if m == "GET":
            return httpx.Response(200, content=self.files[fid]) if fid in self.files else httpx.Response(404)
        if m == "DELETE":
            self.files.pop(fid, None)
            return httpx.Response(204)
        return httpx.Response(404)


def device(tmp_path, name, google, vault_dict, monkeypatch):
    """One 'device': its own database and settings, but (in the test) the same fake vault and Google."""
    st = Store(tmp_path / f"{name}.db")
    se = Settings(name=name.title(), lang="en")
    s = sync.Syncer(st, se, http=httpx.Client(transport=httpx.MockTransport(google)))
    return st, se, s


# ---------------------------------------------------------------- pieces
def test_encryption_round_trip_and_wrong_password():
    salt = b"s" * 16
    key = sync.derive_key("correct horse", salt)
    blob = sync.encrypt({"hello": "світ"}, key, salt)
    assert blob[:4] == b"LNT1" and b"hello" not in blob and sync.salt_of(blob) == salt
    assert sync.decrypt(blob, key) == {"hello": "світ"}
    with pytest.raises(sync.SyncError) as e:
        sync.decrypt(blob, sync.derive_key("wrong horse", salt))
    assert e.value.kind == "password"


def test_merge_keeps_both_sides_and_remembers_deletions():
    a = {**sync.empty(), "threads": {"t1": {"title": "Old", "title_at": 1, "created": 1}, "t2": {"title": "Gone", "title_at": 1, "created": 1}},
         "messages": {"m1": {"thread": "t1", "role": "user", "content": "hi", "model": "", "at": 1},
                      "m2": {"thread": "t2", "role": "user", "content": "x", "model": "", "at": 1}},
         "facts": {"f1": {"text": "likes tea", "at": 1}}, "profile": {"name": "A", "lang": "en", "at": 5}}
    b = {**sync.empty(), "threads": {"t1": {"title": "New title", "title_at": 9, "created": 1}},
         "messages": {"m3": {"thread": "t1", "role": "assistant", "content": "hello", "model": "x", "at": 2}},
         "deleted": {"t2": 3, "f9": 3}, "profile": {"name": "B", "lang": "uk", "at": 2}}
    m = sync.merge(a, b)
    assert m["threads"] == {"t1": {"title": "New title", "title_at": 9, "created": 1}}
    assert set(m["messages"]) == {"m1", "m3"}                      # m2 belonged to the deleted chat
    assert set(m["facts"]) == {"f1"} and m["profile"]["name"] == "A"
    assert sync.merge(b, a)["threads"] == m["threads"]              # order doesn't matter


def test_store_export_import_keeps_local_ids(tmp_path):
    one, two = Store(tmp_path / "1.db"), Store(tmp_path / "2.db")
    t = one.new_thread()
    one.add(t, "user", "ciao")
    one.rename(t, "Italian")
    one.add_fact("lives in Ferrara")
    keep = two.new_thread("mine")
    two.add(keep, "user", "local message")
    two.import_sync(sync.merge(two.export_sync(), one.export_sync()))
    titles = {x["title"]: x["id"] for x in two.threads()}
    assert titles["mine"] == keep and "Italian" in titles
    assert [m["content"] for m in two.messages(titles["Italian"])] == ["ciao"]
    assert [f["text"] for f in two.facts()] == ["lives in Ferrara"]
    # deleting on one device removes it on the other, and it doesn't come back
    one.delete_thread(t)
    two.import_sync(sync.merge(two.export_sync(), one.export_sync()))
    assert [x["title"] for x in two.threads()] == ["mine"]
    one.import_sync(sync.merge(one.export_sync(), two.export_sync()))
    assert [x["title"] for x in one.threads()] == ["mine"]


def test_old_database_gets_sync_ids(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "old.db")
    db.executescript("""CREATE TABLE threads (id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created REAL, updated REAL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, thread INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '', at REAL);
        INSERT INTO threads VALUES (1, 'old chat', 1, 1); INSERT INTO messages VALUES (1, 1, 'user', 'hi', '', 1);""")
    db.commit()
    db.close()
    snap = Store(tmp_path / "old.db").export_sync()
    assert [t["title"] for t in snap["threads"].values()] == ["old chat"] and len(snap["messages"]) == 1


# ---------------------------------------------------------------- the whole flow
def test_sign_in_through_the_browser(vault, monkeypatch):
    google = FakeGoogle()

    def browser(url):                         # plays the user's browser: Google sends it back with a code
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        assert q["scope"] == sync.SCOPE and q["code_challenge_method"] == "S256" and q["redirect_uri"].startswith("http://127.0.0.1:")
        back = q["redirect_uri"] + "/?" + urllib.parse.urlencode({"code": "the-code", "state": q["state"]})
        threading.Thread(target=lambda: urllib.request.urlopen(back, timeout=5).read(), daemon=True).start()

    tok = sync.sign_in(browser, timeout=10, client=httpx.Client(transport=httpx.MockTransport(google)))
    assert tok["refresh_token"] == "rt-1"


def test_two_devices_share_chats(tmp_path, vault, monkeypatch):
    google = FakeGoogle()
    a_store, a_set, a = device(tmp_path, "pc", google, vault, monkeypatch)
    monkeypatch.setattr(sync, "sign_in", lambda *a_, **k: {"refresh_token": "rt-1"})
    a._sign_in()
    assert a.phase == "password" and a.cloud_exists is False and a.account == "anna@example.com"
    assert a.set_password("short")["error"] == "short"
    t = a_store.new_thread("From the PC")
    a_store.add(t, "user", "secret plans")
    st = a.set_password("pc-password-1")
    assert st["phase"] == "ready" and st["error"] == "" and len(google.files) == 1
    blob = next(iter(google.files.values()))
    assert b"secret plans" not in blob and b"From the PC" not in blob          # Google only sees ciphertext

    # the laptop: same Google account, has its own chat
    vault.pop(sync.VAULT_KEY)
    b_store, b_set, b = device(tmp_path, "laptop", google, vault, monkeypatch)
    b_store.add(b_store.new_thread("From the laptop"), "user", "hello")
    b._sign_in()
    assert b.cloud_exists is True
    assert b.set_password("wrong-password")["error"] == "password"
    assert b.set_password("pc-password-1")["phase"] == "ready"
    assert {x["title"] for x in b_store.threads()} == {"From the PC", "From the laptop"}

    # back on the PC (same key in this shared fake vault)
    assert a.sync()["phase"] == "ready"
    assert {x["title"] for x in a_store.threads()} == {"From the PC", "From the laptop"}
    pc_chat = next(x["id"] for x in a_store.threads() if x["title"] == "From the PC")
    assert [m["content"] for m in a_store.messages(pc_chat)] == ["secret plans"]

    # nothing changed: no upload
    google.calls.clear()
    a.sync()
    assert not any(c.startswith(("PATCH", "POST /upload")) for c in google.calls)

    # sign out and delete the copy
    a.sign_out(delete_cloud=True)
    assert google.files == {} and google.revoked == ["rt-1"] and a.phase == "off"
    assert sync.VAULT_TOKEN not in vault and sync.VAULT_KEY not in vault


def test_lost_access_signs_out_quietly(tmp_path, vault, monkeypatch):
    google = FakeGoogle()
    st, se, s = device(tmp_path, "pc", google, vault, monkeypatch)
    vault[sync.VAULT_TOKEN] = "rt-1"
    vault[sync.VAULT_KEY] = __import__("base64").b64encode(b"s" * 16 + b"k" * 32).decode()
    s.phase = "ready"
    google_revoked = lambda req: httpx.Response(400, json={"error": "invalid_grant"})   # noqa: E731
    s.http = httpx.Client(transport=httpx.MockTransport(google_revoked))
    out = s.sync()
    assert out["phase"] == "off" and out["error"] == "signed_out" and sync.VAULT_TOKEN not in vault


def test_api_methods(tmp_path, vault, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna.app import Api
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    assert a.sync_status()["phase"] == "off"
    before = a.settings.profile_at
    a.save_settings({"name": "Anna"})
    assert a.settings.profile_at > before


def test_settings_in_terminal_app_show_sign_in(tmp_path, vault, monkeypatch):
    pytest.importorskip("textual")
    import asyncio
    from textual.widgets import Button
    from lanterna.app import Api
    from lanterna.tui import LanternaApp, SettingsScreen
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.onboarded, a.settings.update_check, a.settings.mode = True, False, "local"
    a.settings.sync_asked = True
    started = []
    monkeypatch.setattr(a.syncer, "start_sign_in", lambda: started.append(1) or a.syncer.status())

    async def go():
        app = LanternaApp(api=a)
        async with app.run_test(size=(110, 60)) as pilot:
            app.push_screen(SettingsScreen())
            for _ in range(100):
                await pilot.pause(0.05)
                if isinstance(app.screen, SettingsScreen) and app.screen.query("#syncin"):
                    break
            scr = app.screen
            assert scr.query_one("#syncin", Button).display and not scr.query_one("#syncnow", Button).display
            assert not scr.query_one("#syncpwrow").display
            scr.query_one("#syncin", Button).press()
            await pilot.pause(0.2)
            assert started == [1]
            a.syncer.phase, a.syncer.cloud_exists = "password", False
            await pilot.pause(1.3)
            assert scr.query_one("#syncpwrow").display and scr.query_one("#syncout", Button).display
    asyncio.run(go())


def test_settings_and_keys_follow_to_a_new_device(tmp_path, vault, monkeypatch):
    """The laptop signs in and gets the PC's service, mode and API key; a key removed later goes back too."""
    from lanterna.providers import PROVIDERS
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    google = FakeGoogle()
    monkeypatch.setattr(sync, "sign_in", lambda *a_, **k: {"refresh_token": "rt-1", "scope": sync.SCOPE})
    pc_keys, lap_keys = {"gemini": "AIza-pc-key"}, {}
    cur = {"k": pc_keys}                                   # which device's vault the API keys are in
    box = lambda n: cur["k"] if n in PROVIDERS else vault   # noqa: E731
    monkeypatch.setattr(keys, "stored_key", lambda n: box(n).get(n) or "")
    monkeypatch.setattr(keys, "set_key", lambda n, k: box(n).__setitem__(n, k))
    monkeypatch.setattr(keys, "delete_key", lambda n: box(n).pop(n, None))

    a_store, a_set, a = device(tmp_path, "pc", google, vault, monkeypatch)
    a_set.mode, a_set.provider, a_set.onboarded = "auto", "gemini", True     # set up before 0.3.3: no prefs_at / keys_at
    a_set.work_dir = "C:/Users/anna/proj"
    a._sign_in()
    assert a.set_password("pc-password-1")["phase"] == "ready"
    assert b"AIza-pc-key" not in next(iter(google.files.values()))          # keys travel encrypted

    vault.pop(sync.VAULT_KEY)
    cur["k"] = lap_keys
    b_store, b_set, b = device(tmp_path, "laptop", google, vault, monkeypatch)
    changed = []
    b.on_change = lambda: changed.append(1)
    b._sign_in()
    assert b.set_password("pc-password-1")["phase"] == "ready"
    assert lap_keys == {"gemini": "AIza-pc-key"} and (b_set.mode, b_set.provider) == ("auto", "gemini") and changed
    assert b_set.work_dir == ""                                            # folders stay per computer

    lap_keys.pop("gemini")                                                  # removed on the laptop later
    b_set.keys_at = {"gemini": 20}
    b.sync()
    cur["k"] = pc_keys
    a.sync()
    assert "gemini" not in pc_keys and a_set.keys_at["gemini"] == 20


def test_one_google_sign_in_also_connects_drive(tmp_path, vault, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna import gdrive
    from lanterna.app import Api
    google = FakeGoogle()
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    http = httpx.Client(transport=httpx.MockTransport(google))
    a.syncer.http = a.drive.http = http
    asked = []
    monkeypatch.setattr(sync, "sign_in", lambda *a_, **k: asked.append(k["scope"]) or
                        {"refresh_token": "rt-1", "scope": f"{sync.SCOPE} {gdrive.SCOPE_FILE}"})
    a.syncer._sign_in()
    assert asked == [f"{sync.SCOPE} {gdrive.SCOPE_FILE}"]
    assert a.drive_status()["phase"] == "ready" and a.drive_status()["account"] == "anna@example.com"
    a.drive_disconnect()                                   # Drive off: the shared sign-in stays for sync
    assert google.revoked == [] and vault.get(sync.VAULT_TOKEN) == "rt-1" and a.drive_status()["phase"] == "off"
    a.drive.adopt("rt-1", "anna@example.com")
    a.sync_sign_out(False)                                 # sync off: Drive used the same sign-in, so it goes too
    assert google.revoked == ["rt-1"] and a.drive_status()["phase"] == "off" and gdrive.VAULT_TOKEN not in vault


def test_sign_in_without_the_sync_permission_is_refused(tmp_path, vault, monkeypatch):
    google = FakeGoogle()
    st, se, s = device(tmp_path, "pc", google, vault, monkeypatch)
    monkeypatch.setattr(sync, "sign_in", lambda *a_, **k: {"refresh_token": "rt-1", "scope": "https://www.googleapis.com/auth/drive.file"})
    s._sign_in()
    assert s.phase == "off" and s.error == "scope" and sync.VAULT_TOKEN not in vault and google.revoked == ["rt-1"]


def test_terminal_app_asks_for_google_first(tmp_path, vault, monkeypatch):
    """New install: language, then the Google step; skipping goes on with the setup. An existing install sees
    the Google step once and then the chat."""
    pytest.importorskip("textual")
    import asyncio
    from textual.widgets import Button
    from lanterna.app import Api
    from lanterna.tui import GoogleScreen, LanternaApp, OnboardScreen, _ChatScreen
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.update_check = False

    async def wait_for(app, pilot, kind):
        for _ in range(100):
            await pilot.pause(0.05)
            if isinstance(app.screen, kind):
                return app.screen
        raise AssertionError(f"no {kind.__name__}, got {type(app.screen).__name__}")

    async def new_install():
        app = LanternaApp(api=a)
        async with app.run_test(size=(110, 50)) as pilot:
            scr = await wait_for(app, pilot, OnboardScreen)
            scr.query_one("#lang-uk", Button).press()
            g = await wait_for(app, pilot, GoogleScreen)
            assert g.query_one("#syncin", Button).display
            g.query_one("#noacct", Button).press()
            scr = await wait_for(app, pilot, OnboardScreen)
            assert scr.step == 1 and a.settings.sync_asked

    async def existing_install():
        app = LanternaApp(api=a)
        async with app.run_test(size=(110, 50)) as pilot:
            g = await wait_for(app, pilot, GoogleScreen)
            g.query_one("#noacct", Button).press()
            await wait_for(app, pilot, _ChatScreen)

    asyncio.run(new_install())
    a.settings.onboarded, a.settings.mode, a.settings.sync_asked = True, "local", False
    asyncio.run(existing_install())
    assert a.settings.sync_asked


# ---------------------------------------------------------------- forgot the password · no password
@pytest.fixture
def vaults(monkeypatch):
    """A vault per device: `vaults.on("pc")` makes the next calls use that device's vault."""
    class V(dict):
        now = "pc"

        def on(self, name):
            self.now = name
            return self

        def box(self):
            return self.setdefault(self.now, {})
    v = V()
    monkeypatch.setattr(keys, "get_key", lambda n: v.box().get(n))
    monkeypatch.setattr(keys, "set_key", lambda n, k: v.box().__setitem__(n, k))
    monkeypatch.setattr(keys, "delete_key", lambda n: v.box().pop(n, None))
    monkeypatch.setattr(keys, "stored_key", lambda n: v.box().get(n) or "")
    monkeypatch.setattr(sync, "derive_key", lambda pw, salt: (pw.encode() * 32)[:32])
    monkeypatch.setattr(sync, "sign_in", lambda *a_, **k: {"refresh_token": "rt-1"})
    return v


def _titles(store):
    return {x["title"] for x in store.threads()}


def test_forgot_password_start_over_keeps_every_chat(tmp_path, vaults):
    google = FakeGoogle()
    a_store, _, a = device(tmp_path, "pc", google, None, None)
    b_store, _, b = device(tmp_path, "laptop", google, None, None)
    a_store.add(a_store.new_thread("From the PC"), "user", "hi")
    b_store.add(b_store.new_thread("From the laptop"), "user", "hi")
    vaults.on("pc")
    a._sign_in()
    a.set_password("old-password-1")
    vaults.on("laptop")
    b._sign_in()
    assert b.set_password("old-password-1")["phase"] == "ready"

    # nobody remembers it now: the PC starts over
    vaults.on("pc")
    st = a.start_over()
    assert st["phase"] == "password" and st["cloud"] is False and google.files == {}
    assert sync.VAULT_KEY not in vaults["pc"] and sync.VAULT_TOKEN in vaults["pc"]      # still signed in
    # the laptop syncs meanwhile: it must not bring the old copy back with the old password
    vaults.on("laptop")
    st = b.sync()
    assert st["phase"] == "password" and st["error"] == "gone" and google.files == {}
    # a new password on the PC; the laptop joins with it, and every chat is there
    vaults.on("pc")
    assert a.set_password("new-password-2")["phase"] == "ready" and len(google.files) == 1
    vaults.on("laptop")
    assert b.set_password("old-password-1")["error"] == "password"
    assert b.set_password("new-password-2")["phase"] == "ready"
    assert _titles(b_store) == {"From the PC", "From the laptop"}
    vaults.on("pc")
    a.sync()
    assert _titles(a_store) == {"From the PC", "From the laptop"}


def test_sync_without_a_password(tmp_path, vaults):
    google = FakeGoogle()
    a_store, _, a = device(tmp_path, "pc", google, None, None)
    b_store, _, b = device(tmp_path, "laptop", google, None, None)
    a_store.add(a_store.new_thread("From the PC"), "user", "hi")
    b_store.add(b_store.new_thread("From the laptop"), "user", "hi")
    vaults.on("pc")
    vaults.box()["groq"] = "gsk_pc_key"
    a._sign_in()
    assert a.status()["phase"] == "password" and not a.status()["no_password"]
    st = a.use_no_password()
    assert st["phase"] == "ready" and st["no_password"] and len(google.files) == 2
    copy = next(google.files[f] for f in google.files if google.names[f] == sync.FILE_NAME)
    key_file = json.loads(next(google.files[f] for f in google.files if google.names[f] == sync.KEY_FILE))
    sk = __import__("base64").b64decode(vaults["pc"][sync.VAULT_KEY])
    data = sync.decrypt(copy, sk[16:])
    assert data["keys"] == {} and b"gsk_pc_key" not in copy                  # API keys never go to the cloud this way
    assert __import__("base64").b64decode(key_file["key"]) == sk[16:]

    # the laptop: signing in with Google is enough
    vaults.on("laptop")
    vaults.box()["groq"] = "gsk_laptop_key"
    b._sign_in()
    assert b.status()["phase"] == "ready" and b.status()["no_password"]
    assert _titles(b_store) == {"From the PC", "From the laptop"}
    assert vaults["laptop"]["groq"] == "gsk_laptop_key"                     # its own key stays its own

    # a copy with a password can't be joined without it
    google2 = FakeGoogle()
    c_store, _, c = device(tmp_path, "third", google2, None, None)
    vaults.on("third")
    c._sign_in()
    c.set_password("secret-pass-1")
    vaults.on("fourth")
    d_store, _, d = device(tmp_path, "fourth", google2, None, None)
    d._sign_in()
    assert d.status()["phase"] == "password" and d.status()["cloud"]
    assert d.use_no_password()["error"] == "has_password"


def test_a_device_follows_when_the_copy_is_made_again_without_a_password(tmp_path, vaults):
    google = FakeGoogle()
    a_store, _, a = device(tmp_path, "pc", google, None, None)
    b_store, _, b = device(tmp_path, "laptop", google, None, None)
    vaults.on("pc")
    a._sign_in()
    a.set_password("old-password-1")
    vaults.on("laptop")
    b._sign_in()
    b.set_password("old-password-1")
    b_store.add(b_store.new_thread("Laptop only"), "user", "hi")
    vaults.on("pc")
    a.start_over()
    a.use_no_password()
    vaults.on("laptop")
    st = b.sync()                                    # its old copy is gone; the new one has no password
    assert st["phase"] == "ready" and st["no_password"] and "Laptop only" in _titles(b_store)
    vaults.on("pc")
    a.sync()
    assert "Laptop only" in _titles(a_store)
    a.sign_out(delete_cloud=True)
    assert google.files == {} and sync.VAULT_MODE not in vaults["pc"]


def test_window_and_terminal_offer_both_ways():
    from pathlib import Path

    from lanterna import gui, tui
    assert {"sync_no_password", "sync_start_over"} <= gui.METHODS
    js = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert "api.sync_no_password()" in js and "api.sync_start_over()" in js and 'id="sync-reset"' in js
    src = Path(tui.__file__).read_text(encoding="utf-8")
    assert "#syncopen" in src and "#syncreset" in src
