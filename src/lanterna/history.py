"""“What Lanterna did”: every confirmed change on this computer, newest first, with Undo where it can be undone.

Kept in Lanterna's own folder on this device (history.json, the last 300 changes). It is not synced: the changes
were made on this computer. An entry stores what the card showed plus what Undo needs (where files went, the
previous setting); nothing is sent anywhere.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import data_dir

LIMIT = 300
# kinds whose entries can be undone, and how (filled in by the code that made the change)
UNDO_TYPES = ("moves", "trash", "rmdir", "restore_backup", "theme", "power", "startup", "app")


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "history.json"
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [x for x in data if isinstance(x, dict) and x.get("id")] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-LIMIT:], ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, kind: str, details: dict, result: str = "", undo: dict | None = None, tid: int = 0) -> str:
        d = {k: v for k, v in (details or {}).items() if k not in ("preview",)}
        if isinstance(d.get("files"), list):
            d["files"] = d["files"][:60]
        if isinstance(d.get("groups"), list):
            d["groups"] = [{**g, "files": list(g.get("files", []))[:20]} for g in d["groups"][:30]]
        entry = {"id": uuid.uuid4().hex[:12], "kind": kind, "details": d, "result": str(result or "")[:500],
                 "at": time.time(), "tid": tid, "undo": undo if undo and undo.get("type") in UNDO_TYPES else None,
                 "undone": False, "note": ""}
        with self._lock:
            items = self._load()
            items.append(entry)
            self._save(items)
        return entry["id"]

    def items(self) -> list[dict]:
        """Newest first."""
        return list(reversed(self._load()))

    def get(self, hid: str) -> dict | None:
        return next((x for x in self._load() if x["id"] == str(hid)), None)

    def find_undo(self, key: str, value: str) -> dict | None:
        """The newest entry whose details[key] == value (the sort card's own Undo, after a restart)."""
        return next((x for x in self.items() if x.get("details", {}).get(key) == value), None)

    def mark(self, hid: str, note: str) -> None:
        with self._lock:
            items = self._load()
            for x in items:
                if x["id"] == str(hid):
                    x["undone"], x["note"] = True, str(note)[:300]
            self._save(items)

    def clear(self) -> None:
        with self._lock:
            self._save([])


# ---------------------------------------------------------------- undo for files
def undo_moves(moves: list, roots: set[str] = frozenset()) -> tuple[int, int]:
    """Puts moved files back. Returns (back, left): left = moved again or replaced since. Folders the move
    created are removed when they end up empty (never a root folder like Downloads)."""
    back = left = 0
    for src, dst in reversed(moves):
        s, d = Path(src), Path(dst)
        if d.exists() and not s.exists():
            s.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d), str(s))
            back += 1
            parent = d.parent
            while str(parent) not in roots and parent != s.parent and parent != parent.parent:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        else:
            left += 1
    return back, left


def undo_rmdir(path: str) -> bool:
    """Removes a folder Lanterna created, only if it is still empty."""
    try:
        Path(path).rmdir()
        return True
    except OSError:
        return False


def undo_restore_backup(path: str, backup: str) -> bool:
    """Puts the saved old version back; the current text is saved first, so this can be undone by hand too."""
    p, b = Path(path), Path(backup)
    if not b.is_file():
        return False
    if p.exists():
        from .workspace import _backup
        _backup(p)
    shutil.copy2(b, p)
    return True
