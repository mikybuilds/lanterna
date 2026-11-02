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
CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL, at REAL);
CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, text TEXT NOT NULL, due REAL NOT NULL,
    done INTEGER NOT NULL DEFAULT 0, created REAL);
"""
MAX_FACTS = 60


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

    # memory: short facts about the user, shown to the model in the system prompt
    def add_fact(self, text: str) -> int:
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM facts WHERE lower(text)=lower(?)", (text,)).fetchone():
                return 0
            rid = self._db.execute("INSERT INTO facts(text, at) VALUES (?,?)", (text, time.time())).lastrowid
            self._db.execute("DELETE FROM facts WHERE id NOT IN (SELECT id FROM facts ORDER BY id DESC LIMIT ?)", (MAX_FACTS,))
            return rid

    def facts(self) -> list[dict]:
        return self._q("SELECT id, text, at FROM facts ORDER BY id")

    def delete_fact(self, fid: int) -> None:
        self._q("DELETE FROM facts WHERE id=?", (fid,))

    def forget_facts(self, text: str) -> int:
        text = text.strip()
        if not text:
            return 0
        with self._lock, self._db:
            return self._db.execute("DELETE FROM facts WHERE instr(lower(text), lower(?)) > 0", (text,)).rowcount

    # reminders
    def add_reminder(self, text: str, due: float) -> int:
        with self._lock, self._db:
            return self._db.execute("INSERT INTO reminders(text, due, created) VALUES (?,?,?)", (text, due, time.time())).lastrowid

    def reminders(self) -> list[dict]:
        return self._q("SELECT id, text, due FROM reminders WHERE done=0 ORDER BY due")

    def cancel_reminder(self, rid: int) -> bool:
        with self._lock, self._db:
            return self._db.execute("UPDATE reminders SET done=2 WHERE id=? AND done=0", (rid,)).rowcount > 0

    def take_due(self, now: float | None = None) -> list[dict]:
        """Reminders whose time has come; each is returned once (marked done)."""
        now = time.time() if now is None else now
        with self._lock, self._db:
            rows = [dict(r) for r in self._db.execute("SELECT id, text, due FROM reminders WHERE done=0 AND due<=? ORDER BY due", (now,))]
            self._db.executemany("UPDATE reminders SET done=1 WHERE id=?", [(r["id"],) for r in rows])
            return rows

    def close(self) -> None:
        self._db.close()
