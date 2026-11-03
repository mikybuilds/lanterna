"""The working folder: one folder the user picked, where the assistant can look around and (with a confirmation
for every change) create and edit files.

Rules
- Nothing outside the chosen folder: every path is resolved and must stay inside it (no "..", no links out).
- Reading is immediate (the text goes to the model in use). Every change is only *proposed*: the user sees a card
  with what will happen and presses Confirm. Nothing is ever deleted; a replaced file is backed up first.
- Files that Windows would run on a double click (.exe, .bat, .ps1, …) are never written.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import data_dir
from .files import IMAGE_EXT, FileError, prepare_one

READ_LIMIT = 12000                 # characters of a file given to the model at once
WRITE_LIMIT = 200_000              # characters the assistant may write in one file
LIST_LIMIT = 200
SEARCH_FILES = 3000                # files looked at by one search
SEARCH_BYTES = 2 * 1024 * 1024     # bigger files: only their names are searched
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vs"}
NEVER_WRITE = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
               ".wsh", ".hta", ".lnk", ".scr", ".msi", ".msp", ".pif", ".reg", ".cpl", ".jar", ".url", ".sys"}
EXPIRE = 30 * 60                   # an unanswered card stops working after this many seconds


class WorkError(Exception):
    pass


def too_broad(p: Path) -> str:
    """Why this folder can't be the working folder ("" = fine): a whole disk, the home folder or system folders."""
    p = p.resolve()
    if p.parent == p:
        return "a whole disk"
    home = Path.home().resolve()
    if p == home:
        return "the whole home folder"
    blocked = [Path(os.environ[v]).resolve() for v in ("WINDIR", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
                                                       "APPDATA", "LOCALAPPDATA") if os.environ.get(v)]
    blocked += [Path(x) for x in ("/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/var", "/lib")]
    blocked += [home / ".ssh", home / ".config", home / ".local", home / ".gnupg"]
    for b in blocked:
        try:
            if p == b or p.is_relative_to(b):
                return "a system folder"
        except (OSError, ValueError):
            continue
    try:
        if p == data_dir().resolve() or p.is_relative_to(data_dir().resolve()):
            return "Lanterna's own data folder"
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------- confirmations
@dataclass
class Action:
    id: str
    kind: str                                  # write_new | write_replace | write_append | mkdir | move | drive_folder | drive_upload
    details: dict
    run: Callable[[], str]
    tid: int = 0
    created: float = field(default_factory=time.time)
    state: str = "pending"                     # pending | done | cancelled | failed | expired
    result: str = ""

    def card(self) -> dict:
        return {"id": self.id, "kind": self.kind, "details": self.details, "state": self.state, "result": self.result}


class Actions:
    """Changes waiting for the user's OK. The chat that proposed them gets a card (see bind)."""

    def __init__(self):
        self.items: dict[str, Action] = {}
        self._local = threading.local()
        self._lock = threading.Lock()

    def bind(self, sink: list | None, tid: int = 0) -> None:
        """Cards proposed in this thread go to `sink` (the reply being streamed)."""
        self._local.sink, self._local.tid = sink, tid

    def propose(self, kind: str, details: dict, run: Callable[[], str]) -> Action:
        a = Action(uuid.uuid4().hex[:12], kind, details, run, getattr(self._local, "tid", 0))
        with self._lock:
            self.items[a.id] = a
        sink = getattr(self._local, "sink", None)
        if sink is not None:
            sink.append(a.card())
        return a

    def get(self, aid: str) -> Action | None:
        a = self.items.get(str(aid))
        if a and a.state == "pending" and time.time() - a.created > EXPIRE:
            a.state = "expired"
        return a

    def confirm(self, aid: str) -> Action | None:
        with self._lock:
            a = self.get(aid)
            if not a or a.state != "pending":
                return a
            a.state = "running"
        try:
            a.result, a.state = a.run(), "done"
        except (WorkError, FileError, OSError) as e:
            a.result, a.state = str(e), "failed"
        except Exception as e:                       # noqa: BLE001  (Drive errors etc.)
            a.result, a.state = f"{e.__class__.__name__}: {e}", "failed"
        return a

    def cancel(self, aid: str) -> Action | None:
        a = self.get(aid)
        if a and a.state == "pending":
            a.state = "cancelled"
        return a


WAITING = ("Prepared. Nothing has been changed yet: the user now sees a card with this change and a Confirm button. "
           "Tell them in one short sentence what will happen when they confirm (future tense: 'it will be created', "
           "never 'I created' or 'done').")


# ---------------------------------------------------------------- the folder
class Workspace:
    def __init__(self, folder: Callable[[], str], actions: Actions):
        self._folder, self.actions = folder, actions

    def root(self) -> Path | None:
        f = (self._folder() or "").strip()
        if not f:
            return None
        p = Path(f).expanduser()
        return p.resolve() if p.is_dir() else None

    def _root(self) -> Path:
        r = self.root()
        if r is None:
            raise WorkError("No working folder is chosen (Settings → Working folder), or it no longer exists.")
        return r

    def path(self, rel: str) -> Path:
        """A path inside the folder, or WorkError."""
        root = self._root()
        rel = str(rel or "").strip().replace("\\", "/")
        if rel in ("", ".", "/"):
            return root
        p = (root / rel.lstrip("/")).resolve()
        if p != root and not p.is_relative_to(root):
            raise WorkError(f"'{rel}' is outside the working folder; only files inside it can be used.")
        return p

    def rel(self, p: Path) -> str:
        r = p.relative_to(self._root()).as_posix()
        return r or "."

    # -- reading (immediate)
    def list(self, path: str = "") -> str:
        d = self.path(path)
        if not d.is_dir():
            raise WorkError(f"'{path}' is not a folder.")
        items = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for x in items[:LIST_LIMIT]:
            try:
                st = x.stat()
            except OSError:
                continue
            when = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"📁 {x.name}/" if x.is_dir() else f"📄 {x.name}  ({_size(st.st_size)}, {when})")
        more = f"\n… and {len(items) - LIST_LIMIT} more" if len(items) > LIST_LIMIT else ""
        return f"Folder '{self.rel(d)}' ({len(items)} items):\n" + ("\n".join(lines) or "(empty)") + more

    def search(self, text: str) -> str:
        q = str(text or "").strip().lower()
        if not q:
            raise WorkError("Say what to look for.")
        root, hits, seen = self._root(), [], 0
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            for name in files:
                seen += 1
                if seen > SEARCH_FILES or len(hits) >= 30:
                    break
                p = Path(dirpath) / name
                if q in name.lower():
                    hits.append(f"📄 {self.rel(p)} (name)")
                    continue
                try:
                    if p.suffix.lower() in IMAGE_EXT or p.stat().st_size > SEARCH_BYTES:
                        continue
                    if p.suffix.lower() in (".pdf", ".docx"):
                        body = prepare_one(name, p.read_bytes())[0]
                    else:
                        body = p.read_text(encoding="utf-8", errors="ignore")
                except (OSError, FileError):
                    continue
                i = body.lower().find(q)
                if i >= 0:
                    line = " ".join(body[max(0, i - 60): i + 80].split())
                    hits.append(f"📄 {self.rel(p)}: …{line}…")
        return (f"Found {len(hits)}:\n" + "\n".join(hits)) if hits else f"Nothing with '{text}' in the working folder."

    def read(self, path: str, start: int = 0) -> str:
        p = self.path(path)
        if not p.is_file():
            raise WorkError(f"There is no file '{path}' in the working folder.")
        if p.suffix.lower() in IMAGE_EXT:
            return f"'{self.rel(p)}' is a picture. Ask the user to attach it to the chat to look at it."
        if p.suffix.lower() in (".pdf", ".docx"):
            body = prepare_one(p.name, p.read_bytes())[0]
        else:
            body = p.read_bytes()[:WRITE_LIMIT * 4].decode("utf-8", "replace")
        start = max(0, int(start or 0))
        part = body[start:start + READ_LIMIT]
        more = (f"\n[… {len(body) - start - READ_LIMIT} more characters: call folder_read again with start="
                f"{start + READ_LIMIT}]") if len(body) > start + READ_LIMIT else ""
        return f"File '{self.rel(p)}':\n{part}{more}"

    # -- changes (proposed, then confirmed by the user)
    def _check_target(self, p: Path) -> None:
        if p.suffix.lower() in NEVER_WRITE:
            raise WorkError(f"Lanterna doesn't create {p.suffix} files: Windows could run them.")
        if p == self._root():
            raise WorkError("Give a file name inside the working folder.")

    def propose_write(self, path: str, text: str, mode: str = "create") -> str:
        p = self.path(path)
        self._check_target(p)
        text = str(text or "")
        if len(text) > WRITE_LIMIT:
            raise WorkError("That is too long for one file.")
        mode = mode if mode in ("create", "replace", "append") else "create"
        if p.is_dir():
            raise WorkError(f"'{path}' is a folder.")
        if mode == "create" and p.exists():
            raise WorkError(f"'{self.rel(p)}' already exists. Use mode 'replace' to rewrite it or 'append' to add to it.")
        if mode != "create" and not p.exists():
            mode = "create"
        kind = {"create": "write_new", "replace": "write_replace", "append": "write_append"}[mode]
        rel = self.rel(p)

        def run() -> str:
            q = self.path(rel)                       # the folder may have changed since
            self._check_target(q)
            backup = ""
            if mode == "create" and q.exists():
                raise WorkError(f"'{rel}' appeared in the meantime; nothing was changed.")
            if mode == "replace" and q.exists():
                backup = _backup(q)
            q.parent.mkdir(parents=True, exist_ok=True)
            with open(q, "a" if mode == "append" else "w", encoding="utf-8", newline="") as f:
                f.write(("\n" if mode == "append" and q.exists() and q.stat().st_size else "") + text)
            return rel + (f" (the old version is saved in {backup})" if backup else "")

        self.actions.propose(kind, {"path": rel, "preview": text[:1500], "chars": len(text),
                                    "lines": text.count("\n") + 1 if text else 0}, run)
        return WAITING

    def propose_mkdir(self, path: str) -> str:
        p = self.path(path)
        if p.exists():
            return f"'{self.rel(p)}' already exists."
        rel = self.rel(p)

        def run() -> str:
            self.path(rel).mkdir(parents=True, exist_ok=True)
            return rel
        self.actions.propose("mkdir", {"path": rel}, run)
        return WAITING

    def propose_move(self, path: str, new_path: str) -> str:
        src, dst = self.path(path), self.path(new_path)
        if not src.exists():
            raise WorkError(f"There is no '{path}' in the working folder.")
        if src == self._root():
            raise WorkError("The working folder itself can't be moved.")
        if dst.exists():
            raise WorkError(f"'{self.rel(dst)}' already exists; choose another name.")
        if src.is_file():
            self._check_target(dst)
        a, b = self.rel(src), self.rel(dst)

        def run() -> str:
            s, d = self.path(a), self.path(b)
            if d.exists():
                raise WorkError(f"'{b}' appeared in the meantime; nothing was moved.")
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            return f"{a} → {b}"
        self.actions.propose("move", {"path": a, "to": b}, run)
        return WAITING


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _backup(p: Path) -> str:
    """Copies a file about to be replaced into Lanterna's own folder; returns where."""
    d = data_dir() / "file-backups" / time.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{time.strftime('%H%M%S')}-{p.name}"
    shutil.copy2(p, dest)
    return str(dest)


def folder_tools(ws: Workspace) -> list:
    """The tools the model sees while a working folder is chosen."""
    from .tools import Tool, _obj
    if ws.root() is None:
        return []
    s = {"type": "string"}
    where = f"the user's working folder ({ws.root().name})"
    return [
        Tool("folder_list", f"List files and subfolders in {where}. Paths are relative to it; '' is the folder itself.",
             _obj({"path": s}), lambda path="": ws.list(path), "📁"),
        Tool("folder_search", f"Find files in {where} by name or by text inside them.",
             _obj({"text": s}, ["text"]), lambda text: ws.search(text), "🔍"),
        Tool("folder_read", f"Read a file from {where} (text, code, Markdown, CSV, PDF, Word). Long files come in parts: "
             "pass `start` to continue.",
             _obj({"path": s, "start": {"type": "integer"}}, ["path"]), lambda path, start=0: ws.read(path, start), "📖"),
        Tool("folder_write", f"Create or change a text file in {where}. mode: create (new file), replace (rewrite), "
             "append (add to the end). Call it directly when the user asks for a file: they get a card with a Confirm "
             "button, so don't ask for permission in text first.",
             _obj({"path": s, "text": s, "mode": {"type": "string", "enum": ["create", "replace", "append"]}},
                  ["path", "text"]),
             lambda path, text, mode="create": ws.propose_write(path, text, mode), "📝"),
        Tool("folder_make", f"Create a subfolder in {where}. The user confirms it on a card (no need to ask first).",
             _obj({"path": s}, ["path"]), lambda path: ws.propose_mkdir(path), "📁"),
        Tool("folder_move", f"Move or rename a file or folder inside {where}. The user confirms it on a card (no need "
             "to ask first).",
             _obj({"path": s, "new_path": s}, ["path", "new_path"]),
             lambda path, new_path: ws.propose_move(path, new_path), "📦"),
    ]
