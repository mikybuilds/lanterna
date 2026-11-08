"""Sign in with Google and keep the same chats on every device.

How it works
- Sign-in opens the browser on Google's own page (OAuth for desktop apps: a one-time local address on 127.0.0.1
  and PKCE). Lanterna asks for one permission only, `drive.appdata`: a hidden folder that belongs to Lanterna
  in the user's own Google Drive. It cannot see any other file.
- Chats, memory, reminders, the name/language, the main settings and the API keys of the model services are
  kept there as ONE file, encrypted with AES-256-GCM. The key comes from a sync password the user chooses
  (scrypt), so Google cannot read any of it. Sign-in tokens (Google, GitHub) are never synced.
- Or, if the user chooses so, without a password: a random key is kept in a second file in the same hidden folder,
  so signing in with Google is enough on every device. Then the copy is only as safe as the Google account, so the
  API keys are NOT synced in this mode (each device keeps its own).
- Forgot the password? Start over: the copy in Drive is deleted (chats on the devices stay) and made again.
- The same sign-in can also give the Google Drive connector its permission (drive.file: only files Lanterna
  created), so a new device needs one sign-in for both.
- The sign-in token and the derived key stay in the system's secure vault on each device.
- Syncing = download the file, merge it with this device (nothing is lost; deletions are remembered),
  save the result here and upload it if it changed.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse

import httpx

from . import keys, quiet

# The OAuth client of the Lanterna desktop app. For installed apps Google does not treat the client secret as
# a secret (it cannot be hidden in an app people download); it only lets the app open Google's sign-in page as
# "Lanterna". Access to anyone's data still needs that person to sign in and agree.
CLIENT_ID = "293789654281-ga9imgva33udo3cpmslv0bvf1kn5n4dl.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPE = "https://www.googleapis.com/auth/drive.appdata"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FILE_NAME = "lanterna-sync.bin"
KEY_FILE = "lanterna-sync-key.json"              # only without a password: the copy's key, next to it
VAULT_TOKEN, VAULT_KEY, VAULT_ACCOUNT = "google-sync-token", "google-sync-key", "google-sync-account"
VAULT_MODE = "google-sync-mode"                  # "open" = synced without a password on this device
MAGIC = b"LNT1"
# Settings that follow the user to every device (folders and local models belong to one computer).
PREFS = ("mode", "provider", "models", "auto_cloud", "update_check", "pc_access", "ai_titles", "follow_ups", "compact_chats", "ask_first", "auto_memory")
SIGN_IN_TIMEOUT = 300


class SyncError(Exception):
    """kind: auth | password | network | cancelled | gone (the file was deleted) | other"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


# ---------------------------------------------------------------- encryption
def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def encrypt(data: dict, key: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    raw = gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC + salt)


def salt_of(blob: bytes) -> bytes:
    if blob[:4] != MAGIC or len(blob) < 4 + 16 + 12 + 16:
        raise SyncError("other", "not a Lanterna sync file")
    return blob[4:20]


def decrypt(blob: bytes, key: bytes) -> dict:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = salt_of(blob)
    try:
        raw = AESGCM(key).decrypt(blob[20:32], blob[32:], MAGIC + salt)
    except InvalidTag:
        raise SyncError("password", "wrong sync password") from None
    return json.loads(gzip.decompress(raw).decode("utf-8"))


# ---------------------------------------------------------------- merging
def empty() -> dict:
    return {"threads": {}, "messages": {}, "facts": {}, "reminders": {}, "deleted": {}, "profile": {}, "prefs": {},
            "keys": {}}


def merge(a: dict, b: dict) -> dict:
    """Union of two snapshots. Newer title / reminder state wins; deleted things stay deleted."""
    out = empty()
    gone = {**a.get("deleted", {})}
    for uid, at in b.get("deleted", {}).items():
        gone[uid] = max(at, gone.get(uid, 0))
    out["deleted"] = gone
    for table, stamp in (("threads", "title_at"), ("reminders", "changed"), ("facts", None), ("messages", None)):
        rows = dict(a.get(table, {}))
        for uid, row in b.get(table, {}).items():
            if uid not in rows or (stamp and (row.get(stamp) or 0) > (rows[uid].get(stamp) or 0)):
                rows[uid] = row
        out[table] = {u: r for u, r in rows.items() if u not in gone}
    out["messages"] = {u: m for u, m in out["messages"].items() if m.get("thread") in out["threads"]}
    for part in ("profile", "prefs"):
        pa, pb = a.get(part, {}), b.get(part, {})
        out[part] = pb if (pb.get("at") or 0) > (pa.get("at") or 0) else pa
    ka = dict(a.get("keys", {}))                     # per service: the newest key (or removal, key "") wins
    for pid, kb in b.get("keys", {}).items():
        if pid not in ka or (kb.get("at") or 0) > (ka[pid].get("at") or 0):
            ka[pid] = kb
    out["keys"] = ka
    return out


def fingerprint(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- Google sign-in
def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


_DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>Lanterna</title>
<body style="font:16px system-ui;background:#0b0d12;color:#ece8df;display:grid;place-items:center;height:90vh">
<div style="text-align:center"><div style="font-size:42px">🏮</div><h2>{title}</h2><p>{text}</p></div></body>"""


def sign_in(open_browser=quiet.open_url, timeout: float = SIGN_IN_TIMEOUT, cancel: threading.Event | None = None,
            client: httpx.Client | None = None, scope: str = SCOPE) -> dict:
    """Runs the browser sign-in and returns Google's tokens (with a refresh_token). Blocks until done."""
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                return
            got.update({k: v[0] for k, v in q.items()})
            ok = "code" in got
            page = _DONE_PAGE.format(title="Signed in" if ok else "Sign-in was cancelled",
                                     text="You can close this tab and go back to Lanterna." if ok else "You can close this tab.")
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):            # keep the console quiet (the URL holds the one-time code)
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    srv.timeout = 0.5
    redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": redirect, "response_type": "code", "scope": scope,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "access_type": "offline", "prompt": "consent"})
    try:
        open_browser(url)
        end = time.monotonic() + timeout
        while "code" not in got and "error" not in got:
            if time.monotonic() > end:
                raise SyncError("cancelled", "no answer from the browser")
            if cancel is not None and cancel.is_set():
                raise SyncError("cancelled", "cancelled")
            srv.handle_request()
    finally:
        srv.server_close()
    if "error" in got:
        raise SyncError("cancelled", got["error"])
    return _token({"code": got["code"], "code_verifier": verifier, "redirect_uri": redirect,
                   "grant_type": "authorization_code"}, client)


def _token(data: dict, client: httpx.Client | None = None) -> dict:
    data = {**data, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    try:
        r = (client or httpx).post(TOKEN_URL, data=data, timeout=30)
    except httpx.HTTPError as e:
        raise SyncError("network", str(e)) from e
    if r.status_code != 200:
        try:
            err = r.json().get("error", "")
        except ValueError:
            err = ""
        raise SyncError("auth" if err in ("invalid_grant", "unauthorized_client", "invalid_client") else "other",
                        f"Google: {err or r.status_code}")
    return r.json()


# ---------------------------------------------------------------- Drive (hidden app folder)
class Drive:
    def __init__(self, refresh_token: str, http: httpx.Client | None = None):
        self.refresh_token = refresh_token
        self.http = http or httpx.Client(timeout=60)
        self._access, self._until = "", 0.0

    def _auth(self) -> dict:
        if time.time() > self._until - 60:
            t = _token({"refresh_token": self.refresh_token, "grant_type": "refresh_token"}, self.http)
            self._access, self._until = t["access_token"], time.time() + float(t.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._access}"}

    def _call(self, method: str, url: str, **kw) -> httpx.Response:
        try:
            r = self.http.request(method, url, headers={**self._auth(), **kw.pop("headers", {})}, **kw)
        except httpx.HTTPError as e:
            raise SyncError("network", str(e)) from e
        if r.status_code in (401, 403):
            raise SyncError("auth", f"Google Drive: {r.status_code}")
        if r.status_code == 404 and method == "GET":
            raise SyncError("gone", "Google Drive: the file is gone")
        if r.status_code >= 400 and not (method == "DELETE" and r.status_code == 404):
            raise SyncError("other", f"Google Drive: {r.status_code} {r.text[:120]}")
        return r

    def find_all(self, name: str = FILE_NAME) -> list[str]:
        r = self._call("GET", f"{DRIVE}/files", params={"spaces": "appDataFolder", "q": f"name='{name}'",
                                                        "fields": "files(id,modifiedTime)", "orderBy": "modifiedTime desc"})
        return [f["id"] for f in r.json().get("files", [])]

    def find(self, name: str = FILE_NAME) -> str:
        files = self.find_all(name)
        return files[0] if files else ""

    def download(self, fid: str) -> bytes:
        return self._call("GET", f"{DRIVE}/files/{fid}", params={"alt": "media"}).content

    def upload(self, blob: bytes, fid: str = "", name: str = FILE_NAME) -> str:
        if fid:
            self._call("PATCH", f"{UPLOAD}/files/{fid}", params={"uploadType": "media"}, content=blob,
                       headers={"Content-Type": "application/octet-stream"})
            return fid
        boundary = "lanterna" + secrets.token_hex(8)
        meta = json.dumps({"name": name, "parents": ["appDataFolder"]}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
                f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode() + blob +
                f"\r\n--{boundary}--".encode())
        r = self._call("POST", f"{UPLOAD}/files", params={"uploadType": "multipart", "fields": "id"}, content=body,
                       headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        return r.json()["id"]

    def delete(self, fid: str) -> None:
        self._call("DELETE", f"{DRIVE}/files/{fid}")

    def account(self) -> str:
        """The Google account's e-mail, to show who is signed in (only on this device)."""
        try:
            r = self._call("GET", f"{DRIVE}/about", params={"fields": "user(emailAddress)"})
            return r.json().get("user", {}).get("emailAddress", "")
        except SyncError:
            return ""


def revoke(token: str, client: httpx.Client | None = None) -> None:
    try:
        (client or httpx).post(REVOKE_URL, data={"token": token}, timeout=15)
    except httpx.HTTPError:
        pass


# ---------------------------------------------------------------- vault
def _vault_get(name: str) -> str:
    return keys.get_key(name) or ""


def _vault_set(name: str, value: str) -> None:
    keys.set_key(name, value)


def _vault_del(name: str) -> None:
    keys.delete_key(name)


# ---------------------------------------------------------------- the sync itself
class Syncer:
    """State machine used by the window app, the terminal app and the CLI.

    phase: off (not signed in) · waiting (browser sign-in open) · password (needs the sync password) ·
           ready (signed in, synced or about to) · syncing · error
    """

    def __init__(self, store, settings, http: httpx.Client | None = None, browser=quiet.open_url):
        self.store, self.settings, self.http, self.browser = store, settings, http, browser
        self.lock = threading.Lock()
        self.phase = "ready" if self.signed_in() else "off"
        self.error, self.last, self.account = "", 0.0, _vault_get(VAULT_ACCOUNT)
        self.cloud_exists: bool | None = None
        self.url = ""                                  # the sign-in page, for "open in another browser"
        self._cancel = threading.Event()
        self._fid, self._synced_changes, self._remote_fp = "", -1, ""
        self._may_create = False                       # only a password (or none) just chosen here makes a new copy
        self.extra_scope = ""                          # e.g. the Drive connector's scope, asked in the same sign-in
        self.on_token = None                           # (refresh_token, account, granted scopes) after a sign-in
        self.on_sign_out = None                        # (refresh_token) after sign-out
        self.on_change = None                          # () after synced settings or keys changed here
        if self.phase == "ready" and not _vault_get(VAULT_KEY):
            self.phase = "password"

    # -- state
    @staticmethod
    def signed_in() -> bool:
        return bool(_vault_get(VAULT_TOKEN))

    @staticmethod
    def no_password() -> bool:
        return _vault_get(VAULT_MODE) == "open"

    def status(self) -> dict:
        return {"phase": self.phase, "account": self.account, "error": self.error, "last": self.last,
                "cloud": self.cloud_exists, "url": self.url if self.phase == "waiting" else "",
                "no_password": self.no_password() and self.phase not in ("off", "password")}

    def _drive(self) -> Drive:
        tok = _vault_get(VAULT_TOKEN)
        if not tok:
            raise SyncError("auth", "not signed in")
        return Drive(tok, self.http)

    # -- sign in / out
    def start_sign_in(self) -> dict:
        if self.phase == "waiting":
            return self.status()
        self.phase, self.error = "waiting", ""
        self._cancel.clear()
        threading.Thread(target=self._sign_in, daemon=True).start()
        return self.status()

    def cancel_sign_in(self) -> dict:
        self._cancel.set()
        return self.status()

    def _sign_in(self) -> None:
        try:
            def open_page(url: str) -> None:
                self.url = url
                self.browser(url)
            scope = " ".join(x for x in (SCOPE, self.extra_scope) if x)
            tok = sign_in(open_page, cancel=self._cancel, client=self.http, scope=scope)
            if not tok.get("refresh_token"):
                raise SyncError("auth", "Google gave no refresh token")
            granted = str(tok.get("scope") or scope)
            if SCOPE not in granted.split():
                revoke(tok["refresh_token"], self.http)
                raise SyncError("auth", "scope")
            _vault_set(VAULT_TOKEN, tok["refresh_token"])
            d = self._drive()
            self.account = d.account()
            if self.account:
                _vault_set(VAULT_ACCOUNT, self.account)
            self._fid = d.find()
            self.cloud_exists = bool(self._fid)
            self.phase = "ready" if self._fid and self._adopt_open(d) else "password"
            if self.on_token:
                try:
                    self.on_token(tok["refresh_token"], self.account, granted)
                except Exception:                        # noqa: BLE001  the Drive part is optional
                    pass
        except SyncError as e:
            self.phase, self.error = ("off", "" if e.kind == "cancelled" else str(e)) if not self.signed_in() else ("password", "")
        except Exception as e:                       # never leave the UI waiting
            self.phase, self.error = "off", str(e)[:200]
        if self.phase == "ready":                    # a copy without a password: the Google sign-in was enough
            self.sync()

    def _adopt_open(self, d: Drive) -> bool:
        """The copy was made without a password: take its key from the hidden folder (True), or False."""
        kid = d.find(KEY_FILE)
        if not kid:
            return False
        try:
            k = json.loads(d.download(kid))
            salt, key = base64.b64decode(k["salt"]), base64.b64decode(k["key"])
        except (ValueError, KeyError, TypeError):
            return False
        if len(salt) != 16 or len(key) != 32:
            return False
        fid = d.find()
        if fid:
            blob = d.download(fid)
            if salt_of(blob) != salt:
                return False
            decrypt(blob, key)                               # raises if it doesn't open
        _vault_set(VAULT_KEY, base64.b64encode(salt + key).decode())
        _vault_set(VAULT_MODE, "open")
        return True

    def use_no_password(self) -> dict:
        """Sync with the Google account alone. Joins a copy made that way, or makes a new one if there is none."""
        try:
            d = self._drive()
            self._fid = d.find()
            if self._fid:
                if not self._adopt_open(d):
                    self.cloud_exists, self.error = True, "has_password"
                    return self.status()
            else:
                salt, key = os.urandom(16), os.urandom(32)
                for kid in d.find_all(KEY_FILE):              # a left-over key of an earlier copy
                    d.delete(kid)
                d.upload(json.dumps({"v": 1, "salt": base64.b64encode(salt).decode(),
                                     "key": base64.b64encode(key).decode()}).encode(), name=KEY_FILE)
                _vault_set(VAULT_KEY, base64.b64encode(salt + key).decode())
                _vault_set(VAULT_MODE, "open")
                self._may_create = True
            self.phase, self.error = "ready", ""
        except SyncError as e:
            self.error = str(e)[:200]
            return self.status()
        return self.sync()

    def start_over(self) -> dict:
        """Forgot the password: deletes the copy in Google Drive (chats on the devices stay); then a new password,
        or none, makes it again from this device. Other devices are asked for the new one."""
        try:
            d = self._drive()
            for name in (FILE_NAME, KEY_FILE):
                for fid in d.find_all(name):
                    d.delete(fid)
        except SyncError as e:
            self.error = str(e)[:200]
            return self.status()
        _vault_del(VAULT_KEY)
        _vault_del(VAULT_MODE)
        self._fid, self.cloud_exists, self.phase, self.error, self.last = "", False, "password", "", 0.0
        return self.status()

    def set_password(self, password: str) -> dict:
        """First device: creates the cloud copy with this password. Other devices: checks it opens the copy."""
        password = str(password or "")
        if len(password) < 8:
            self.error = "short"
            return self.status()
        try:
            d = self._drive()
            self._fid = d.find()
            if self._fid and self._adopt_open(d):            # made without a password: nothing to check
                self.phase, self.error = "ready", ""
                return self.sync()
            if self._fid:
                blob = d.download(self._fid)
                key = derive_key(password, salt_of(blob))
                decrypt(blob, key)                           # raises on a wrong password
                salt = salt_of(blob)
            else:
                salt = os.urandom(16)
                key = derive_key(password, salt)
                self._may_create = True
            _vault_set(VAULT_KEY, base64.b64encode(salt + key).decode())
            _vault_del(VAULT_MODE)
            self.phase, self.error = "ready", ""
        except SyncError as e:
            self.error = e.kind if e.kind == "password" else str(e)
            return self.status()
        return self.sync()

    def sign_out(self, delete_cloud: bool = False) -> dict:
        tok = _vault_get(VAULT_TOKEN)
        if tok and delete_cloud:
            try:
                d = self._drive()
                for name in (FILE_NAME, KEY_FILE):
                    for fid in d.find_all(name):
                        d.delete(fid)
            except SyncError as e:
                self.error = str(e)
                return self.status()
        if tok:
            revoke(tok, self.http)
        for name in (VAULT_TOKEN, VAULT_KEY, VAULT_ACCOUNT, VAULT_MODE):
            _vault_del(name)
        if tok and self.on_sign_out:
            self.on_sign_out(tok)
        self.phase, self.error, self.account, self.last, self.cloud_exists, self._fid = "off", "", "", 0.0, None, ""
        return self.status()

    # -- sync
    def _profile(self) -> dict:
        return {"name": self.settings.name, "lang": self.settings.lang, "at": getattr(self.settings, "profile_at", 0) or 0}

    def _prefs(self) -> dict:
        s = self.settings
        # a device that was set up before settings were synced still beats a fresh install
        at = getattr(s, "prefs_at", 0) or (1 if getattr(s, "onboarded", False) else 0)
        return {**{k: getattr(s, k) for k in PREFS}, "at": at}

    def _keys(self) -> dict:
        """API keys of the model services stored on this device (not environment variables), with when they
        last changed; a removed key is kept as "" so the removal reaches the other devices too."""
        from .providers import PROVIDERS
        if self.no_password():                               # only as safe as the Google account: keys stay here
            return {}
        stamps = getattr(self.settings, "keys_at", {}) or {}
        out = {}
        for pid, p in PROVIDERS.items():
            if not p.needs_key:
                continue
            k, at = keys.stored_key(pid), stamps.get(pid, 0)
            if k:
                out[pid] = {"key": k, "at": at or 1}
            elif at:
                out[pid] = {"key": "", "at": at}
        return out

    def _apply_extras(self, merged: dict, local: dict) -> None:
        from .providers import PROVIDERS
        s, changed = self.settings, False
        p = merged.get("prefs", {})
        if (p.get("at") or 0) > (local["prefs"].get("at") or 0):
            for k in PREFS:
                if k in p:
                    setattr(s, k, p[k])
            s.prefs_at, changed = p["at"], True
        for pid, kv in ({} if self.no_password() else merged.get("keys", {})).items():
            if pid not in PROVIDERS:                         # a service that closed, or one this version doesn't know
                continue
            mine = local["keys"].get(pid, {})
            if kv.get("key", "") == mine.get("key", "") or (kv.get("at") or 0) <= (mine.get("at") or 0):
                continue
            if kv.get("key"):
                keys.set_key(pid, kv["key"])
            else:
                keys.delete_key(pid)
            s.keys_at = {**(s.keys_at or {}), pid: kv["at"]}
            changed = True
        if changed:
            s.save()
            if self.on_change:
                self.on_change()

    def sync(self, force: bool = True) -> dict:
        """Download, merge, save here, upload if changed. Quietly does nothing when not ready."""
        if self.phase not in ("ready", "error") or not self.lock.acquire(blocking=False):
            return self.status()
        try:
            raw = _vault_get(VAULT_KEY)
            if not raw:
                self.phase = "password"
                return self.status()
            sk = base64.b64decode(raw)
            salt, key = sk[:16], sk[16:]
            self.phase = "syncing"
            d = self._drive()
            self._fid = self._fid or d.find()
            blob = b""
            if self._fid:
                try:
                    blob = d.download(self._fid)
                except SyncError as e:
                    if e.kind != "gone":
                        raise
                    self._fid = d.find()
                    blob = d.download(self._fid) if self._fid else b""
            if not self._fid and not self._may_create:      # deleted on another device: don't bring it back
                _vault_del(VAULT_KEY)
                _vault_del(VAULT_MODE)
                self.phase, self.error, self.cloud_exists = "password", "gone", False
                return self.status()
            remote = empty()
            if blob:
                if salt_of(blob) != salt:                    # the copy was made again (another password, or none)
                    if self._adopt_open(d):
                        sk = base64.b64decode(_vault_get(VAULT_KEY))
                        salt, key = sk[:16], sk[16:]
                    else:
                        _vault_del(VAULT_KEY)
                        _vault_del(VAULT_MODE)
                        self.phase, self.error = "password", "changed"
                        return self.status()
                remote = decrypt(blob, key)
            local = {**self.store.export_sync(), "profile": self._profile(), "prefs": self._prefs(), "keys": self._keys()}
            merged = merge(local, remote)
            if fingerprint(merged) != fingerprint(local):
                self.store.import_sync(merged)
                self._apply_extras(merged, local)
                p = merged.get("profile", {})
                if (p.get("at") or 0) > (self._profile()["at"] or 0):
                    self.settings.name, self.settings.lang = p.get("name", self.settings.name), p.get("lang", self.settings.lang)
                    self.settings.profile_at = p["at"]
                    self.settings.save()
            if fingerprint(merged) != fingerprint(remote) or not self._fid:
                self._fid = d.upload(encrypt(merged, key, salt), self._fid)
            self._may_create = False
            self.cloud_exists = True
            self._synced_changes = self.store.changes
            self.last, self.phase, self.error = time.time(), "ready", ""
        except SyncError as e:
            if e.kind == "auth":
                for name in (VAULT_TOKEN, VAULT_KEY, VAULT_MODE):
                    _vault_del(name)
                self.phase, self.error = "off", "signed_out"
            elif e.kind == "password":
                _vault_del(VAULT_KEY)
                self.phase, self.error = "password", "password"
            else:
                self.phase, self.error = "error", str(e)[:200]
        except Exception as e:
            self.phase, self.error = "error", str(e)[:200]
        finally:
            self.lock.release()
        return self.status()

    def dirty(self) -> bool:
        return self.store.changes != self._synced_changes

    def loop(self, every: float = 120.0, stop: threading.Event | None = None) -> None:
        """Background: sync when something changed here (checked every 15 s) and at least every `every` seconds."""
        stop = stop or threading.Event()
        next_full = 0.0
        while not stop.wait(15):
            if self.phase in ("ready", "error") and (self.dirty() or time.monotonic() > next_full):
                self.sync()
                next_full = time.monotonic() + every
