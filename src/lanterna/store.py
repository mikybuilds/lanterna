"""Chats and messages in a local SQLite file (per-user data folder).

Every row also has a random `uid`, so the same chat can be recognised on another device when the user turns on
sync (sync.py). Deleted things leave a small note in `deleted` so they don't come back from another device.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
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
CREATE TABLE IF NOT EXISTS deleted (uid TEXT PRIMARY KEY, at REAL NOT NULL);
"""
# columns added for sync (older databases get them on open)
_ADDED = {"threads": ["uid TEXT", "title_at REAL NOT NULL DEFAULT 0"], "messages": ["uid TEXT", "sent TEXT NOT NULL DEFAULT ''"],
          "facts": ["uid TEXT"], "reminders": ["uid TEXT", "changed REAL NOT NULL DEFAULT 0"]}
MAX_FACTS = 60


def new_uid() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "lanterna.db"
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(_SCHEMA)
            with self._db:
                for table, cols in _ADDED.items():
                    have = {r[1] for r in self._db.execute(f"PRAGMA table_info({table})")}
                    for col in cols:
                        if col.split()[0] not in have:
                            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
                    self._db.execute(f"UPDATE {table} SET uid=lower(hex(randomblob(16))) WHERE uid IS NULL")
                    self._db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_uid ON {table}(uid)")
        self.changes = 0                     # bumped on every write; sync uses it to know when to upload

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock, self._db:
            if not sql.lstrip().upper().startswith("SELECT"):
                self.changes += 1
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _tomb(self, table: str, where: str, args: tuple) -> None:
        """Notes the uids of rows about to be deleted (call inside the lock)."""
        now = time.time()
        self._db.executemany("INSERT OR REPLACE INTO deleted(uid, at) VALUES (?,?)",
                             [(r[0], now) for r in self._db.execute(f"SELECT uid FROM {table} WHERE {where}", args)])
        self.changes += 1

    def new_thread(self, title: str = "") -> int:
        now = time.time()
        with self._lock, self._db:
            self.changes += 1
            return self._db.execute("INSERT INTO threads(uid, title, title_at, created, updated) VALUES (?,?,?,?,?)",
                                    (new_uid(), title, now if title else 0, now, now)).lastrowid

    def threads(self) -> list[dict]:
        return self._q("SELECT id, title, updated FROM threads ORDER BY updated DESC")

    def thread(self, tid: int) -> dict | None:
        r = self._q("SELECT id, title, updated FROM threads WHERE id=?", (tid,))
        return r[0] if r else None

    def rename(self, tid: int, title: str) -> None:
        self._q("UPDATE threads SET title=?, title_at=? WHERE id=?", (title.strip()[:80], time.time(), tid))

    def delete_thread(self, tid: int) -> None:
        with self._lock, self._db:
            self._tomb("threads", "id=?", (tid,))
            self._db.execute("DELETE FROM threads WHERE id=?", (tid,))

    def add(self, tid: int, role: str, content: str, model: str = "", sent: str = "") -> None:
        now = time.time()
        with self._lock, self._db:
            self.changes += 1
            self._db.execute("INSERT INTO messages(uid, thread, role, content, model, at, sent) VALUES (?,?,?,?,?,?,?)",
                             (new_uid(), tid, role, content, model, now, sent))
            self._db.execute("UPDATE threads SET updated=? WHERE id=?", (now, tid))

    def messages(self, tid: int) -> list[dict]:
        return self._q("SELECT role, content, model, at, sent FROM messages WHERE thread=? ORDER BY id", (tid,))

    # memory: short facts about the user, shown to the model in the system prompt
    def add_fact(self, text: str) -> int:
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM facts WHERE lower(text)=lower(?)", (text,)).fetchone():
                return 0
            self.changes += 1
            rid = self._db.execute("INSERT INTO facts(uid, text, at) VALUES (?,?,?)", (new_uid(), text, time.time())).lastrowid
            old = "id NOT IN (SELECT id FROM facts ORDER BY id DESC LIMIT ?)"
            self._tomb("facts", old, (MAX_FACTS,))
            self._db.execute(f"DELETE FROM facts WHERE {old}", (MAX_FACTS,))
            return rid

    def facts(self) -> list[dict]:
        return self._q("SELECT id, text, at FROM facts ORDER BY id")

    def delete_fact(self, fid: int) -> None:
        with self._lock, self._db:
            self._tomb("facts", "id=?", (fid,))
            self._db.execute("DELETE FROM facts WHERE id=?", (fid,))

    def forget_facts(self, text: str) -> int:
        text = text.strip()
        if not text:
            return 0
        with self._lock, self._db:
            self._tomb("facts", "instr(lower(text), lower(?)) > 0", (text,))
            return self._db.execute("DELETE FROM facts WHERE instr(lower(text), lower(?)) > 0", (text,)).rowcount

    # reminders
    def add_reminder(self, text: str, due: float) -> int:
        with self._lock, self._db:
            self.changes += 1
            now = time.time()
            return self._db.execute("INSERT INTO reminders(uid, text, due, created, changed) VALUES (?,?,?,?,?)",
                                    (new_uid(), text, due, now, now)).lastrowid

    def reminders(self) -> list[dict]:
        return self._q("SELECT id, text, due FROM reminders WHERE done=0 ORDER BY due")

    def cancel_reminder(self, rid: int) -> bool:
        with self._lock, self._db:
            self.changes += 1
            return self._db.execute("UPDATE reminders SET done=2, changed=? WHERE id=? AND done=0", (time.time(), rid)).rowcount > 0

    def take_due(self, now: float | None = None) -> list[dict]:
        """Reminders whose time has come; each is returned once (marked done)."""
        now = time.time() if now is None else now
        with self._lock, self._db:
            rows = [dict(r) for r in self._db.execute("SELECT id, text, due FROM reminders WHERE done=0 AND due<=? ORDER BY due", (now,))]
            self._db.executemany("UPDATE reminders SET done=1, changed=? WHERE id=?", [(now, r["id"]) for r in rows])
            if rows:
                self.changes += 1
            return rows

    # ---------------------------------------------------------------- sync
    def export_sync(self) -> dict:
        """Everything that is synced, keyed by uid (see sync.merge)."""
        with self._lock:
            q = lambda sql: [dict(r) for r in self._db.execute(sql)]   # noqa: E731
            tuid = {r["id"]: r["uid"] for r in q("SELECT id, uid FROM threads")}
            return {
                "threads": {r["uid"]: {"title": r["title"], "title_at": r["title_at"], "created": r["created"]}
                            for r in q("SELECT uid, title, title_at, created FROM threads")},
                "messages": {r["uid"]: {"thread": tuid[r["thread"]], "role": r["role"], "content": r["content"],
                                        "model": r["model"], "at": r["at"]}
                             for r in q("SELECT uid, thread, role, content, model, at FROM messages") if r["thread"] in tuid},
                "facts": {r["uid"]: {"text": r["text"], "at": r["at"]} for r in q("SELECT uid, text, at FROM facts")},
                "reminders": {r["uid"]: {"text": r["text"], "due": r["due"], "done": r["done"], "created": r["created"],
                                         "changed": r["changed"]}
                              for r in q("SELECT uid, text, due, done, created, changed FROM reminders")},
                "deleted": {r["uid"]: r["at"] for r in q("SELECT uid, at FROM deleted")},
            }

    def import_sync(self, snap: dict) -> int:
        """Brings this database in line with a merged snapshot. Local ids of existing rows stay the same
        (so an open chat stays open). Returns how many rows were added, changed or removed."""
        n = 0
        with self._lock, self._db:
            db = self._db
            gone = snap.get("deleted", {})
            db.executemany("INSERT OR REPLACE INTO deleted(uid, at) VALUES (?,?)", list(gone.items()))
            for table in ("threads", "facts", "reminders"):
                for (uid,) in db.execute(f"SELECT uid FROM {table}").fetchall():
                    if uid in gone:
                        db.execute(f"DELETE FROM {table} WHERE uid=?", (uid,))
                        n += 1
            ids = {r[0]: r[1] for r in db.execute("SELECT uid, id FROM threads")}
            for uid, t in snap.get("threads", {}).items():
                if uid in ids:
                    n += db.execute("UPDATE threads SET title=?, title_at=? WHERE uid=? AND title_at<?",
                                    (t["title"], t["title_at"], uid, t["title_at"])).rowcount
                else:
                    ids[uid] = db.execute("INSERT INTO threads(uid, title, title_at, created, updated) VALUES (?,?,?,?,?)",
                                          (uid, t["title"], t["title_at"], t["created"], t["created"])).lastrowid
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM messages")}
            for uid, m in sorted(snap.get("messages", {}).items(), key=lambda kv: kv[1]["at"] or 0):
                if uid not in have and m["thread"] in ids:
                    db.execute("INSERT INTO messages(uid, thread, role, content, model, at) VALUES (?,?,?,?,?,?)",
                               (uid, ids[m["thread"]], m["role"], m["content"], m["model"], m["at"]))
                    db.execute("UPDATE threads SET updated=max(coalesce(updated,0), ?) WHERE id=?", (m["at"] or 0, ids[m["thread"]]))
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM facts")}
            for uid, f in snap.get("facts", {}).items():
                if uid not in have:
                    db.execute("INSERT INTO facts(uid, text, at) VALUES (?,?,?)", (uid, f["text"], f["at"]))
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM reminders")}
            for uid, r in snap.get("reminders", {}).items():
                if uid in have:
                    n += db.execute("UPDATE reminders SET text=?, due=?, done=?, changed=? WHERE uid=? AND changed<?",
                                    (r["text"], r["due"], r["done"], r["changed"], uid, r["changed"])).rowcount
                else:
                    db.execute("INSERT INTO reminders(uid, text, due, done, created, changed) VALUES (?,?,?,?,?,?)",
                               (uid, r["text"], r["due"], r["done"], r["created"], r["changed"]))
                    n += 1
        return n

    def close(self) -> None:
        self._db.close()
