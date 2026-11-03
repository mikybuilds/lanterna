"""Working folder, confirmation cards, Google Drive connector, limits and the self-update."""
import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest

from lanterna import gdrive, keys, limits, sync, updates
from lanterna.workspace import Actions, Workspace, WorkError, folder_tools, too_broad


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "work"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "plan.md").write_text("# Plan\nBuy milk\nStudy history", encoding="utf-8")
    (root / "secret.txt").write_text("outside", encoding="utf-8") if False else None
    (tmp_path / "outside.txt").write_text("do not read", encoding="utf-8")
    acts = Actions()
    cards: list = []
    acts.bind(cards, 7)
    w = Workspace(lambda: str(root), acts)
    w.cards = cards
    return w


# ---------------------------------------------------------------- working folder
def test_reading_stays_inside_the_folder(ws):
    assert "plan.md" in ws.list("notes") and "📁 notes/" in ws.list("")
    assert "Buy milk" in ws.read("notes/plan.md")
    assert "notes/plan.md" in ws.search("history")
    for bad in ("../outside.txt", "notes/../../outside.txt", str(Path(ws.root()).parent / "outside.txt")):
        with pytest.raises(WorkError):
            ws.read(bad)


def test_changes_wait_for_confirmation_and_back_up(ws):
    out = ws.propose_write("notes/new.md", "hello")
    assert "Nothing has been changed" in out and not (ws.root() / "notes" / "new.md").exists()
    card = ws.cards[-1]
    assert card["kind"] == "write_new" and card["details"]["path"] == "notes/new.md"
    a = ws.actions.confirm(card["id"])
    assert a.state == "done" and (ws.root() / "notes" / "new.md").read_text(encoding="utf-8") == "hello"
    assert ws.actions.confirm(card["id"]).state == "done"          # a second click does nothing more

    ws.propose_write("notes/plan.md", "rewritten", "replace")
    a = ws.actions.confirm(ws.cards[-1]["id"])
    assert (ws.root() / "notes" / "plan.md").read_text(encoding="utf-8") == "rewritten"
    backup = Path(a.result.split("saved in ")[1].rstrip(")"))
    assert backup.read_text(encoding="utf-8").startswith("# Plan") and ws.root() not in backup.parents

    ws.propose_mkdir("school/math")
    ws.propose_move("notes/new.md", "school/new.md")
    mk, mv = ws.cards[-2:]
    assert ws.actions.cancel(mv["id"]).state == "cancelled" and ws.actions.confirm(mv["id"]).state == "cancelled"
    ws.actions.confirm(mk["id"])
    assert (ws.root() / "school" / "math").is_dir() and (ws.root() / "notes" / "new.md").exists()


def test_refuses_risky_writes(ws):
    for name in ("run.bat", "x.ps1", "a.exe", "notes/link.lnk"):
        with pytest.raises(WorkError):
            ws.propose_write(name, "echo hi")
    with pytest.raises(WorkError):
        ws.propose_write("notes/plan.md", "x")                       # exists: create would overwrite
    with pytest.raises(WorkError):
        ws.propose_move("notes/plan.md", "../plan.md")
    assert not ws.cards


def test_no_folder_no_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")   # tests run inside AppData\Local\Temp
    w = Workspace(lambda: "", Actions())
    assert folder_tools(w) == []
    w2 = Workspace(lambda: str(tmp_path), Actions())
    assert {t.name for t in folder_tools(w2)} == {"folder_list", "folder_search", "folder_read", "folder_write",
                                                   "folder_make", "folder_move"}
    assert too_broad(Path(tmp_path.anchor)) and too_broad(Path.home()) and not too_broad(tmp_path)


def test_expired_card(ws, monkeypatch):
    ws.propose_mkdir("later")
    a = ws.actions.items[ws.cards[-1]["id"]]
    a.created -= 3600
    assert ws.actions.confirm(a.id).state == "expired" and not (ws.root() / "later").exists()


# ---------------------------------------------------------------- the chat proposes, the user confirms
def _sse_tool(name, args):
    tc = {"index": 0, "id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [tc]}}]})}\n\ndata: [DONE]\n\n".encode()


def _sse(text):
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


def test_api_card_flow(tmp_path, monkeypatch):
    from lanterna.app import Api
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    work = tmp_path / "work"
    work.mkdir()
    calls = []

    def h(req):
        calls.append(json.loads(req.content))
        if len(calls) == 1:
            return httpx.Response(200, content=_sse_tool("folder_write", {"path": "todo.md", "text": "- milk"}))
        return httpx.Response(200, content=_sse("I prepared todo.md; press Confirm."))

    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    assert a.set_workdir(str(tmp_path.anchor))["error"] == "too_broad"
    assert a.set_workdir(str(work))["ok"]
    a._router = Router([Candidate("groq", "m", 50)], client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))
    tid = a.new_thread()["id"]
    sid = a.send(tid, "make a todo list file with milk")["stream"]
    for _ in range(200):
        p = a.poll(sid)
        if p["done"]:
            break
        time.sleep(0.02)
    assert any(t["function"]["name"] == "folder_write" for t in calls[0]["tools"])
    card = p["cards"][0]
    assert card["kind"] == "write_new" and not (work / "todo.md").exists()
    r = a.action_confirm(card["id"])
    assert r["state"] == "done" and (work / "todo.md").read_text(encoding="utf-8") == "- milk"
    assert a.store.messages(tid)[-1]["content"].startswith("✅ ")


# ---------------------------------------------------------------- Google Drive
class FakeDrive:
    def __init__(self):
        self.items = {}            # id -> {name, mimeType, parents}
        self.uploads = {}

    def __call__(self, req):
        url, m, path = str(req.url), req.method, req.url.path
        if url.startswith(sync.TOKEN_URL):
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        assert req.headers["Authorization"] == "Bearer at"
        if m == "GET" and path.endswith("/drive/v3/files"):
            q = req.url.params["q"]
            parent = q.split("' in parents")[0].rsplit("'", 1)[1]
            name = q.split("name='")[1].split("'")[0] if "name='" in q else None
            found = [{"id": i, **f} for i, f in self.items.items() if parent in f["parents"] and (name is None or f["name"] == name)]
            return httpx.Response(200, json={"files": found})
        if m == "POST" and path.endswith("/drive/v3/files") and "/upload/" not in path:
            meta = json.loads(req.content)
            fid = f"d{len(self.items) + 1}"
            self.items[fid] = {"name": meta["name"], "mimeType": meta["mimeType"], "parents": meta["parents"]}
            return httpx.Response(200, json={"id": fid, "name": meta["name"], "webViewLink": f"https://drive.google.com/{fid}"})
        if m == "POST" and req.url.params.get("uploadType") == "resumable":
            meta = json.loads(req.content)
            fid = f"u{len(self.uploads) + 1}"
            self.uploads[fid] = {"meta": meta}
            return httpx.Response(200, headers={"location": f"{sync.UPLOAD}/files?uploadType=resumable&upload_id={fid}"})
        if m == "PUT":
            fid = req.url.params["upload_id"]
            self.uploads[fid]["data"] = req.content
            meta = self.uploads[fid]["meta"]
            self.items[fid] = {"name": meta["name"], "mimeType": meta.get("mimeType", "file"), "parents": meta["parents"]}
            return httpx.Response(200, json={"id": fid, "name": meta["name"], "webViewLink": f"https://drive.google.com/{fid}"})
        raise AssertionError(f"{m} {url}")


def test_drive_tools(ws, monkeypatch):
    v = {gdrive.VAULT_TOKEN: "rt"}
    monkeypatch.setattr(keys, "get_key", lambda n: v.get(n))
    fake = FakeDrive()
    conn = gdrive.Connector(http=httpx.Client(transport=httpx.MockTransport(fake)))
    tools = {t.name: t for t in gdrive.drive_tools(conn, ws, ws.actions)}
    assert set(tools) == {"drive_list", "drive_make_folder", "drive_save_text", "drive_upload"}
    assert "Lanterna sees only the folders it created" in tools["drive_upload"].run(path="notes/plan.md", folder="School")

    tools["drive_make_folder"].run(name="School")
    assert not fake.items                                            # nothing before the click
    a = ws.actions.confirm(ws.cards[-1]["id"])
    assert a.state == "done" and a.result.endswith("|https://drive.google.com/d1")
    n = len(ws.cards)
    assert "already exists" in tools["drive_make_folder"].run(name="School") and len(ws.cards) == n

    tools["drive_upload"].run(path="notes/plan.md", folder="School")
    ws.actions.confirm(ws.cards[-1]["id"])
    up = fake.uploads["u1"]
    assert up["data"].startswith(b"# Plan") and up["meta"]["parents"] == ["d1"] and up["meta"]["name"] == "plan.md"

    tools["drive_save_text"].run(name="Notes", text="hello", folder="School")
    ws.actions.confirm(ws.cards[-1]["id"])
    assert fake.uploads["u2"]["meta"]["mimeType"] == gdrive.GDOC
    assert "📁 School" in tools["drive_list"].run() and "plan.md" in tools["drive_list"].run(folder="School")

    off = gdrive.Connector()
    off.phase = "off"
    assert gdrive.drive_tools(off, ws, ws.actions) == []


def test_drive_sign_in_asks_only_for_own_files(monkeypatch):
    seen = {}
    monkeypatch.setattr(sync, "sign_in", lambda *a, **kw: seen.update(kw) or {"refresh_token": "rt"})
    v = {}
    monkeypatch.setattr(keys, "get_key", lambda n: v.get(n))
    monkeypatch.setattr(keys, "set_key", lambda n, k: v.__setitem__(n, k))
    monkeypatch.setattr(gdrive.Files, "account", lambda self: "me@example.org")
    c = gdrive.Connector()
    c._sign_in()
    assert seen["scope"] == gdrive.SCOPE_FILE and c.phase == "ready" and v[gdrive.VAULT_TOKEN] == "rt"
    assert sync.VAULT_TOKEN not in v                                  # chat sync stays separate


# ---------------------------------------------------------------- limits
def test_limits_from_headers_and_messages(tmp_path):
    now = [1_800_000_000.0]
    L = limits.Limits(tmp_path / "l.json", clock=lambda: now[0])
    L.note("groq", "llama", 200, {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
                                  "x-ratelimit-reset-requests": "2m30s", "x-ratelimit-remaining-tokens": "5800",
                                  "x-ratelimit-limit-tokens": "6000", "x-ratelimit-reset-tokens": "7.5s"})
    L.note("gemini", "g3", 200, {})
    L.note("gemini", "g3", 429, {}, "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20, model: g3")
    rows = {r["model"]: r for r in L.view({"gemini/g3": 40})}
    req = next(x for x in rows["llama"]["left"] if x["kind"] == "requests")
    assert req == {"kind": "requests", "period": "day", "remaining": 990, "limit": 1000, "reset_in": 150}
    assert rows["g3"]["limit"] == 20 and rows["g3"]["used"] == 1 and rows["g3"]["refused"] == 1 and rows["g3"]["resting"] == 40
    now[0] += 10                                                      # the token window passed: not shown any more
    assert [x["kind"] for x in limits.Limits(tmp_path / "l.json", clock=lambda: now[0]).view()[1]["left"]] == ["requests"]
    now[0] += 86400 * 2                                               # another day: counts start again
    assert limits.Limits(tmp_path / "l.json", clock=lambda: now[0]).view() == []


def test_replies_are_counted(monkeypatch):
    from lanterna.providers import PROVIDERS, Client
    c = Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=_sse("hi"), headers={"x-ratelimit-remaining-requests": "5"})))
    assert c.chat("m", []) == "hi"
    row = limits.TRACKER.view()[0]
    assert row["used"] == 1 and row["left"][0]["remaining"] == 5


# ---------------------------------------------------------------- self-update
def test_update_downloads_checks_and_installs(tmp_path):
    from lanterna import HOMEPAGE
    blob = b"MZ fake installer" * 1000
    good = "sha256:" + hashlib.sha256(blob).hexdigest()
    info = {"latest": "9.9.9", "newer": True,
            "assets": {"Lanterna-Setup-9.9.9.exe": f"{HOMEPAGE}/releases/download/v9.9.9/Lanterna-Setup-9.9.9.exe"},
            "digests": {"Lanterna-Setup-9.9.9.exe": good}}
    asset = updates.setup_asset(info)
    assert asset["sha256"] == good[7:]
    assert updates.setup_asset({**info, "digests": {}}) is None                       # no checksum: by hand only
    assert updates.setup_asset({**info, "assets": {"Lanterna-Setup-9.9.9.exe": "https://example.org/x.exe"}}) is None

    ran, quit_ = [], []
    tr = httpx.MockTransport(lambda r: httpx.Response(200, content=blob, headers={"content-length": str(len(blob))}))
    u = updates.Updater(transport=tr, launch=lambda p, lang: ran.append((p.read_bytes() == blob, lang)),
                        quit_app=lambda: quit_.append(1), folder=tmp_path / "upd")
    u.start(asset, "uk", wait=True)
    assert ran == [(True, "uk")] and quit_ == [1] and u.status()["done"] == len(blob)

    bad = updates.Updater(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"evil")),
                          launch=lambda p, lang: ran.append("evil"), quit_app=lambda: None, folder=tmp_path / "upd2")
    st = bad.start(asset, wait=True) and bad.status()
    assert st["phase"] == "error" and "checksum" in st["error"] and "evil" not in ran
    assert not list((tmp_path / "upd2").glob("*.exe"))
    names = ["VERYSILENT", "SUPPRESSMSGBOXES", "NORESTART", "CLOSEAPPLICATIONS", "RELAUNCH=1", "LANG=uk"]
    assert updates.setup_args("uk") == [chr(47) + n for n in names]


def test_installer_reopens_after_silent_update():
    iss = (Path(__file__).parents[1] / "packaging" / "lanterna.iss").read_text(encoding="utf-8")
    assert "Check: ShouldRelaunch" in iss and "{param:RELAUNCH|0}" in iss and "CloseApplications=force" in iss


# ---------------------------------------------------------------- router: limits and broken answers
def test_daily_limit_is_remembered_and_skipped_quietly():
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router, Switched
    msg = ("You exceeded your current quota. Quota exceeded for metric: generate_content_free_tier_requests, limit: 20, "
           "model: big. Please retry in 1h31m43.18s.")

    def h(req):
        if json.loads(req.content)["model"] == "big":
            return httpx.Response(429, json=[{"error": {"code": 429, "message": msg}}])
        return httpx.Response(200, content=_sse("ok"))
    mk = lambda: Router([Candidate("gemini", "big", 90), Candidate("gemini", "small", 80)],
                        client_for=lambda pid: Client(PROVIDERS["gemini"], "k", transport=httpx.MockTransport(h)))
    r = mk()
    out = list(r.stream([{"role": "user", "content": "hi"}]))
    assert isinstance(out[0], Switched) and out[-1] == "ok"
    row = next(x for x in limits.TRACKER.view() if x["model"] == "big")
    assert row["limit"] == 20 and 5400 < row["resting"] <= 5504
    r2 = mk()                                                          # like after a restart: no new attempt, no note
    assert list(r2.stream([{"role": "user", "content": "hi"}])) == ["ok"]


def test_a_broken_answer_rests_only_that_model():
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router

    def h(req):
        if json.loads(req.content)["model"] == "flaky":
            raise httpx.RemoteProtocolError("peer closed connection")
        return httpx.Response(200, content=_sse("ok"))
    r = Router([Candidate("gemini", "flaky", 90), Candidate("gemini", "fine", 80)],
               client_for=lambda pid: Client(PROVIDERS["gemini"], "k", transport=httpx.MockTransport(h)))
    assert list(r.stream([{"role": "user", "content": "hi"}]))[-1] == "ok"
    assert [c.model for c in r.available()] == ["fine"]


def test_refusal_inside_a_tool_round_is_not_a_day_off():
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router
    seen = []

    def h(req):
        body = json.loads(req.content)
        seen.append(body["model"])
        if body["model"] == "picky":
            return httpx.Response(400, json={"error": {"message": "missing thought_signature"}})
        return httpx.Response(200, content=_sse("ok"))
    r = Router([Candidate("gemini", "picky", 90), Candidate("gemini", "other", 80)],
               client_for=lambda pid: Client(PROVIDERS["gemini"], "k", transport=httpx.MockTransport(h)))
    msgs = [{"role": "user", "content": "hi"}, {"role": "tool", "tool_call_id": "c1", "content": "x"}]
    list(r.stream(msgs))
    assert 0 < r.resting()["gemini/picky"] <= 60
