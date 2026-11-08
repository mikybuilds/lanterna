"""Encrypted backups: once a week all chats, memory, reminders and regular tasks go to one file in a folder
(Documents\\Lanterna backups by default); the last 4 are kept. A backup opens on any computer with its password.

The password itself is never stored: only a key made from it (scrypt) sits in the system's secure store, like the
API keys. No API keys or sign-in tokens are put in a backup. Restoring never removes or changes anything here: it
brings back what is missing (a deleted chat comes back as a chat again).
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

from . import __version__, keys

MAGIC = b"LNB1"
VAULT = "backup-key"                       # salt + key, base64, in the secure store (never the password)
EXT = ".lanterna-backup"
KEEP = 4
EVERY = 7 * 24 * 3600
MIN_PASSWORD = 8
_OURS = re.compile(r"^Lanterna backup \d{4}-\d{2}-\d{2}(?: \(\d+\))?" + re.escape(EXT) + "$")


class BackupError(Exception):
    """kind: password | format | folder | no_key"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


def derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


# ---------------------------------------------------------------- the key in the secure store
def stored() -> tuple[bytes, bytes] | None:
    raw = keys.stored_key(VAULT)
    try:
        blob = base64.b64decode(raw) if raw else b""
    except ValueError:
        return None
    return (blob[:16], blob[16:]) if len(blob) == 48 else None


def set_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise BackupError("password", "too short")
    salt = os.urandom(16)
    keys.set_key(VAULT, base64.b64encode(salt + derive(password, salt)).decode())


def forget() -> None:
    keys.delete_key(VAULT)


# ---------------------------------------------------------------- the file
def snapshot(store) -> dict:
    data = store.export_sync()
    data.pop("deleted", None)
    data["tasks"] = [{k: t[k] for k in ("text", "every", "at", "day", "only_if", "paused")} for t in store.tasks()]
    return {"app": "Lanterna", "version": __version__, "saved": dt.datetime.now().isoformat(timespec="seconds"),
            "data": data}


def seal(snap: dict, salt: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    raw = gzip.compress(json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC + salt)


def is_sealed(blob: bytes) -> bool:
    return blob[:4] == MAGIC


def open_sealed(blob: bytes, password: str = "") -> dict:
    """The backup's contents. The password may be left out on the computer that made it."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not is_sealed(blob) or len(blob) < 4 + 16 + 12 + 16:
        raise BackupError("format", "not a Lanterna backup")
    salt = blob[4:20]
    mine = stored()
    if password:
        key = derive(password, salt)
    elif mine and mine[0] == salt:
        key = mine[1]
    else:
        raise BackupError("password", "password needed")
    try:
        raw = AESGCM(key).decrypt(blob[20:32], blob[32:], MAGIC + salt)
    except InvalidTag:
        raise BackupError("password", "wrong password") from None
    try:
        snap = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, ValueError):
        raise BackupError("format", "broken backup") from None
    return snap


def from_plain(doc: dict) -> dict:
    """An older plain backup ("Save a backup of all chats", JSON) in the same shape. Ids come from the content,
    so restoring the same file twice adds nothing the second time."""
    def uid(*parts) -> str:
        return "json-" + hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]
    if not isinstance(doc, dict) or doc.get("app") != "Lanterna" or not isinstance(doc.get("threads"), list):
        raise BackupError("format", "not a Lanterna backup")
    data = {"threads": {}, "messages": {}, "facts": {}, "reminders": {}, "tasks": []}
    for th in doc["threads"]:
        msgs = [m for m in th.get("messages") or [] if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        tu = uid("t", th.get("title"), msgs[0].get("content") if msgs else "", msgs[0].get("at") if msgs else th.get("updated"))
        data["threads"][tu] = {"title": str(th.get("title") or ""), "title_at": 0, "created": (msgs[0].get("at") if msgs else None) or th.get("updated")}
        for i, m in enumerate(msgs):
            data["messages"][uid("m", tu, i, m.get("content"))] = {"thread": tu, "role": m["role"], "content": str(m.get("content") or ""),
                                                                   "model": str(m.get("model") or ""), "at": m.get("at")}
    for text in doc.get("memory") or []:
        data["facts"][uid("f", text)] = {"text": str(text), "at": None}
    for r in doc.get("reminders") or []:
        if isinstance(r, dict) and r.get("text") and r.get("due"):
            data["reminders"][uid("r", r["text"], r["due"])] = {"text": str(r["text"]), "due": float(r["due"]), "done": 0,
                                                               "created": None, "changed": 0, "repeat": ""}
    return {"app": "Lanterna", "version": doc.get("version", ""), "saved": doc.get("saved", ""), "data": data}


def read(blob: bytes, password: str = "") -> dict:
    """An encrypted backup or an older plain JSON one."""
    if is_sealed(blob):
        return open_sealed(blob, password)
    try:
        doc = json.loads(blob.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise BackupError("format", "not a Lanterna backup") from None
    return from_plain(doc)


# ---------------------------------------------------------------- the folder
def default_folder(documents: Path | None = None) -> Path:
    return (documents or Path.home() / "Documents") / "Lanterna backups"


def ours(folder: Path) -> list[Path]:
    """Lanterna's own backups in this folder, newest first (nothing else in the folder is ever touched)."""
    try:
        files = [p for p in folder.iterdir() if p.is_file() and _OURS.match(p.name)]
    except OSError:
        return []
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def write(store, folder: Path, now: dt.datetime | None = None) -> Path:
    key = stored()
    if not key:
        raise BackupError("no_key", "no backup password")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupError("folder", str(e)) from None
    from .export import free_path
    p = free_path(folder, f"Lanterna backup {(now or dt.datetime.now()):%Y-%m-%d}", EXT)
    tmp = p.with_name(p.name + ".part")
    tmp.write_bytes(seal(snapshot(store), *key))
    tmp.replace(p)
    for old in ours(folder)[KEEP:]:                      # keep the last 4
        try:
            old.unlink()
        except OSError:
            pass
    return p


def due(last: float, now: float) -> bool:
    return now - (last or 0) >= EVERY
