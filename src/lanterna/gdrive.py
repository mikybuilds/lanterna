"""Google Drive connector: the assistant can create folders and put files in the user's own Google Drive.

Permission: only `drive.file` — Lanterna sees and changes ONLY the files and folders it created itself (or that
the user opened with it). It can't read or list the rest of the Drive. This is separate from chat sync
(hidden app folder) and has its own sign-in, so it can be connected and disconnected on its own.

Every upload and every new folder is a proposed change: the user confirms it on a card first.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path

import httpx

from . import sync
from .sync import DRIVE, UPLOAD, SyncError

SCOPE_FILE = "https://www.googleapis.com/auth/drive.file"
VAULT_TOKEN, VAULT_ACCOUNT = "google-drive-token", "google-drive-account"
FOLDER = "application/vnd.google-apps.folder"
GDOC = "application/vnd.google-apps.document"
MAX_UPLOAD = 100 * 1024 * 1024


def _q(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("'", "\\'")


class Files(sync.Drive):
    """Drive calls for the files Lanterna created (drive.file)."""

    def folder_id(self, name: str) -> str:
        """A folder by name or path ("School/Math"), among the ones Lanterna can see. "" = My Drive."""
        parent = "root"
        for part in [x for x in str(name or "").replace("\\", "/").split("/") if x.strip()]:
            r = self._call("GET", f"{DRIVE}/files", params={
                "q": f"name='{_q(part.strip())}' and mimeType='{FOLDER}' and '{parent}' in parents and trashed=false",
                "fields": "files(id)", "pageSize": 1})
            found = r.json().get("files", [])
            if not found:
                raise SyncError("missing", part.strip())
            parent = found[0]["id"]
        return parent

    def list(self, folder: str = "") -> list[dict]:
        parent = self.folder_id(folder)
        r = self._call("GET", f"{DRIVE}/files", params={
            "q": f"'{parent}' in parents and trashed=false", "pageSize": 100, "orderBy": "folder,name",
            "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)"})
        return r.json().get("files", [])

    def make_folder(self, name: str, parent: str = "") -> dict:
        pid = self.folder_id(parent)
        r = self._call("POST", f"{DRIVE}/files", params={"fields": "id,name,webViewLink"},
                       json={"name": name, "mimeType": FOLDER, "parents": [pid]})
        return r.json()

    def upload(self, name: str, data: bytes, mime: str = "application/octet-stream", parent: str = "",  # noqa: D102
               convert_to: str = "") -> dict:
        pid = self.folder_id(parent)
        meta = {"name": name, "parents": [pid]}
        if convert_to:
            meta["mimeType"] = convert_to
        start = self._call("POST", f"{UPLOAD}/files", params={"uploadType": "resumable", "fields": "id,name,webViewLink"},
                           content=json.dumps(meta).encode(),
                           headers={"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime})
        loc = start.headers.get("location", "")
        if not loc.startswith(UPLOAD + "/files"):
            raise SyncError("other", "Google Drive did not accept the upload")
        r = self._call("PUT", loc, content=data, headers={"Content-Type": mime})
        return r.json()


class Connector:
    """phase: off · waiting (browser sign-in open) · ready."""

    def __init__(self, http: httpx.Client | None = None, browser=webbrowser.open):
        self.http, self.browser = http, browser
        self.phase = "ready" if sync._vault_get(VAULT_TOKEN) else "off"
        self.account, self.error, self.url = sync._vault_get(VAULT_ACCOUNT), "", ""
        self._cancel = threading.Event()

    def status(self) -> dict:
        return {"phase": self.phase, "account": self.account, "error": self.error,
                "url": self.url if self.phase == "waiting" else ""}

    def files(self) -> Files:
        tok = sync._vault_get(VAULT_TOKEN)
        if not tok:
            raise SyncError("auth", "Google Drive is not connected")
        return Files(tok, self.http)

    def start(self) -> dict:
        if self.phase != "waiting":
            self.phase, self.error = "waiting", ""
            self._cancel.clear()
            threading.Thread(target=self._sign_in, daemon=True).start()
        return self.status()

    def cancel(self) -> dict:
        self._cancel.set()
        return self.status()

    def _sign_in(self) -> None:
        try:
            def open_page(url: str) -> None:
                self.url = url
                self.browser(url)
            tok = sync.sign_in(open_page, cancel=self._cancel, client=self.http, scope=SCOPE_FILE)
            if not tok.get("refresh_token"):
                raise SyncError("auth", "Google gave no refresh token")
            sync._vault_set(VAULT_TOKEN, tok["refresh_token"])
            self.account = self.files().account()
            if self.account:
                sync._vault_set(VAULT_ACCOUNT, self.account)
            self.phase = "ready"
        except SyncError as e:
            self.phase, self.error = "off", "" if e.kind == "cancelled" else str(e)
        except Exception as e:                       # noqa: BLE001  never leave the UI waiting
            self.phase, self.error = "off", str(e)[:200]

    def disconnect(self) -> dict:
        tok = sync._vault_get(VAULT_TOKEN)
        if tok:
            sync.revoke(tok, self.http)
        for k in (VAULT_TOKEN, VAULT_ACCOUNT):
            sync._vault_del(k)
        self.phase, self.account, self.error = "off", "", ""
        return self.status()

    def _auth_lost(self, e: SyncError) -> None:
        if e.kind == "auth":
            self.disconnect()
            self.error = "signed_out"


WAITING = ("Prepared. Nothing has been sent to Google Drive yet: the user now sees a card with this action and a "
           "Confirm button. Tell them in one short sentence what will happen when they confirm.")
MISSING = ("There is no folder '{name}' that Lanterna can see. Lanterna sees only the folders it created itself; "
           "offer to create it with drive_make_folder.")


def drive_tools(conn: Connector, ws, actions) -> list:
    """The tools the model sees while Google Drive is connected."""
    from .tools import Tool, _obj
    if conn.phase != "ready":
        return []
    s = {"type": "string"}

    def guard(fn):
        def run(*a, **kw):
            try:
                return fn(*a, **kw)
            except SyncError as e:
                if e.kind == "missing":
                    return MISSING.format(name=e)
                conn._auth_lost(e)
                return f"Error: Google Drive: {e}"
        return run

    def _link(info: dict) -> str:
        return f"{info.get('name', '')}|{info.get('webViewLink', '')}"

    @guard
    def drive_list(folder: str = "") -> str:
        items = conn.files().list(folder)
        if not items:
            return "Nothing here that Lanterna created. (Lanterna sees only its own files and folders in Google Drive.)"
        return "\n".join(("📁 " if f["mimeType"] == FOLDER else "📄 ") + f["name"] for f in items)

    @guard
    def drive_make_folder(name: str, parent: str = "") -> str:
        name = str(name).strip().strip("/")[:200]
        if not name:
            return "Error: give the folder a name."
        if parent:
            conn.files().folder_id(parent)            # fail now if the parent is missing, not after the click
        try:                                          # don't make a second folder with the same name
            conn.files().folder_id(f"{parent}/{name}" if parent else name)
            return f"The folder '{name}' already exists in Google Drive (Lanterna created it earlier). Nothing to do."
        except SyncError as e:
            if e.kind != "missing":
                raise
        actions.propose("drive_folder", {"name": name, "parent": parent},
                        lambda: _link(conn.files().make_folder(name, parent)))
        return WAITING

    @guard
    def drive_upload(path: str, folder: str = "") -> str:
        p: Path = ws.path(path)
        if not p.is_file():
            return f"Error: there is no file '{path}' in the working folder."
        size = p.stat().st_size
        if size > MAX_UPLOAD:
            return "Error: the file is bigger than 100 MB."
        if folder:
            conn.files().folder_id(folder)
        rel = ws.rel(p)
        actions.propose("drive_upload", {"path": rel, "folder": folder, "size": size},
                        lambda: _link(conn.files().upload(Path(rel).name, ws.path(rel).read_bytes(), parent=folder)))
        return WAITING

    @guard
    def drive_save_text(name: str, text: str, folder: str = "", google_doc: bool = True) -> str:
        name, text = str(name).strip()[:200] or "Lanterna", str(text or "")
        if folder:
            conn.files().folder_id(folder)
        actions.propose("drive_text", {"name": name, "folder": folder, "preview": text[:1500], "doc": bool(google_doc)},
                        lambda: _link(conn.files().upload(name, text.encode("utf-8"), "text/plain", folder,
                                                          GDOC if google_doc else "")))
        return WAITING

    tools = [
        Tool("drive_list", "List what is in the user's Google Drive among the files and folders Lanterna created "
             "(it can't see the others). folder: name or path like 'School/Math', '' = My Drive.",
             _obj({"folder": s}), drive_list, "☁️"),
        Tool("drive_make_folder", "Create a folder in the user's Google Drive (parent: a folder Lanterna created, "
             "'' = My Drive). The user confirms it on a card (no need to ask first).",
             _obj({"name": s, "parent": s}, ["name"]), drive_make_folder, "☁️"),
        Tool("drive_save_text", "Save text to the user's Google Drive as a new Google Doc (or a .txt file with "
             "google_doc=false). The user confirms it on a card (no need to ask first).",
             _obj({"name": s, "text": s, "folder": s, "google_doc": {"type": "boolean"}}, ["name", "text"]),
             drive_save_text, "☁️"),
    ]
    if ws.root() is not None:
        tools.append(Tool("drive_upload", "Upload a file from the working folder to the user's Google Drive "
                          "(folder: one Lanterna created, '' = My Drive). The user confirms it on a card (no need to ask first).",
                          _obj({"path": s, "folder": s}, ["path"]), drive_upload, "☁️"))
    return tools
