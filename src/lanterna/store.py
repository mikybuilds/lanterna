"""Chats and messages in a local SQLite file (per-user data folder). Nothing leaves the computer."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .config import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, thread INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL, content TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', at REAL);
CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread, id);
"""


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "lanterna.db"
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(_SCHEMA)

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock, self._db:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def new_thread(self, title: str = "") -> int:
        now = time.time()
        with self._lock, self._db:
            return self._db.execute("INSERT INTO threads(title, created, updated) VALUES (?,?,?)", (title, now, now)).lastrowid

    def threads(self) -> list[dict]:
        return self._q("SELECT id, title, updated FROM threads ORDER BY updated DESC")

    def thread(self, tid: int) -> dict | None:
        r = self._q("SELECT id, title, updated FROM threads WHERE id=?", (tid,))
        return r[0] if r else None

    def rename(self, tid: int, title: str) -> None:
        self._q("UPDATE threads SET title=? WHERE id=?", (title.strip()[:80], tid))

    def delete_thread(self, tid: int) -> None:
        self._q("DELETE FROM threads WHERE id=?", (tid,))

    def add(self, tid: int, role: str, content: str, model: str = "") -> None:
        now = time.time()
        with self._lock, self._db:
            self._db.execute("INSERT INTO messages(thread, role, content, model, at) VALUES (?,?,?,?,?)", (tid, role, content, model, now))
            self._db.execute("UPDATE threads SET updated=? WHERE id=?", (now, tid))

    def messages(self, tid: int) -> list[dict]:
        return self._q("SELECT role, content, model, at FROM messages WHERE thread=? ORDER BY id", (tid,))

    def close(self) -> None:
        self._db.close()
