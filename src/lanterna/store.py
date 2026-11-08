"""Chats and messages in a local SQLite file (per-user data folder).

Every row also has a random `uid`, so the same chat can be recognised on another device when the user turns on
sync (sync.py). Deleted things leave a small note in `deleted` so they don't come back from another device.
"""
from __future__ import annotations

import re
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
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, text TEXT NOT NULL, every TEXT NOT NULL DEFAULT 'day',
    at TEXT NOT NULL DEFAULT '08:00', day INTEGER NOT NULL DEFAULT 0, only_if TEXT NOT NULL DEFAULT '',
    next REAL NOT NULL, last REAL NOT NULL DEFAULT 0, last_result TEXT NOT NULL DEFAULT '',
    paused INTEGER NOT NULL DEFAULT 0, thread INTEGER, created REAL);
"""
# columns added for sync (older databases get them on open)
_ADDED = {"threads": ["uid TEXT", "title_at REAL NOT NULL DEFAULT 0", "summary TEXT NOT NULL DEFAULT ''",
                      "summary_upto INTEGER NOT NULL DEFAULT 0"], "messages": ["uid TEXT", "sent TEXT NOT NULL DEFAULT ''"],
          "facts": ["uid TEXT"], "reminders": ["uid TEXT", "changed REAL NOT NULL DEFAULT 0",
                                                   "repeat TEXT NOT NULL DEFAULT ''"]}
MAX_FACTS = 60
_MARKS = re.compile(r"(\*\*|__|`)(?=\S)(.+?)(?<=\S)\1|(?<![\w*])([*_])(?=\S)([^*_\n]+?)(?<=\S)\3(?![\w*])")


def plain_fact(text: str) -> str:
    """A memory fact as plain text: models sometimes write *Title* or **word**, and the marks showed as they are."""
    return " ".join(_MARKS.sub(lambda m: m.group(2) or m.group(4), str(text or "")).split())
REPEATS = ("day", "weekday", "week", "month")      # a reminder that comes back; "" = once


def next_due(due: float, repeat: str, now: float) -> float:
    """The next time a repeating reminder comes back after `now`, at the same wall-clock time (local time, so a
    clock change doesn't shift it). Missed times (the PC was off) are skipped, not shown one by one.
    month: the same day of the month (the 31st becomes the last day in shorter months)."""
    import calendar
    import datetime as dt
    first = dt.datetime.fromtimestamp(due)
    t = first
    for n in range(1, 5000):
        if repeat == "month":
            y, m = divmod(first.month - 1 + n, 12)
            y, m = first.year + y, m + 1
            t = first.replace(year=y, month=m, day=min(first.day, calendar.monthrange(y, m)[1]))
        elif repeat == "week":
            t += dt.timedelta(days=7)
        else:
            t += dt.timedelta(days=1)
            while repeat == "weekday" and t.weekday() >= 5:
                t += dt.timedelta(days=1)
        if t.timestamp() > now:
            return t.timestamp()
    return now + 86400


def new_uid() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "lanterna.db"
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # SQLite's own lower() changes only Latin letters: lc() lowers any language ("Алергія" = "алергія")
        self._db.create_function("lc", 1, lambda s: (s or "").lower(), deterministic=True)
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
        # private chats: only in memory (negative ids), never in the database, the sync or a backup
        self._private: dict[int, dict] = {}
        self._next_private = -1

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

    # ---------------------------------------------------------------- private chats (memory only)
    def new_private(self) -> int:
        with self._lock:
            tid, self._next_private = self._next_private, self._next_private - 1
            now = time.time()
            self._private[tid] = {"title": "", "created": now, "updated": now, "msgs": []}
            return tid

    def forget_private(self, keep: int = 0) -> list[int]:
        """Drops the private chats (all but `keep`); returns their ids."""
        with self._lock:
            gone = [tid for tid in self._private if tid != keep]
            for tid in gone:
                del self._private[tid]
            return gone

    def new_thread(self, title: str = "") -> int:
        now = time.time()
        with self._lock, self._db:
            self.changes += 1
            return self._db.execute("INSERT INTO threads(uid, title, title_at, created, updated) VALUES (?,?,?,?,?)",
                                    (new_uid(), title, now if title else 0, now, now)).lastrowid

    def threads(self) -> list[dict]:
        return self._q("SELECT id, title, updated FROM threads ORDER BY updated DESC")

    def thread(self, tid: int) -> dict | None:
        if tid < 0:
            p = self._private.get(tid)
            return {"id": tid, "title": p["title"], "updated": p["updated"], "private": True} if p else None
        r = self._q("SELECT id, title, updated FROM threads WHERE id=?", (tid,))
        return r[0] if r else None

    def rename(self, tid: int, title: str) -> None:
        if tid < 0:
            if tid in self._private:
                self._private[tid]["title"] = title.strip()[:80]
            return
        self._q("UPDATE threads SET title=?, title_at=? WHERE id=?", (title.strip()[:80], time.time(), tid))

    def summary(self, tid: int) -> tuple[str, int]:
        """A long chat's summary of its older part and how many of its first messages it covers."""
        if tid < 0:
            return "", 0
        r = self._q("SELECT summary, summary_upto FROM threads WHERE id=?", (tid,))
        return (r[0]["summary"], r[0]["summary_upto"]) if r else ("", 0)

    def set_summary(self, tid: int, text: str, upto: int) -> None:
        # not counted as a change: the summary stays on this device (each device makes its own), no sync upload
        if tid < 0:
            return
        with self._lock, self._db:
            self._db.execute("UPDATE threads SET summary=?, summary_upto=? WHERE id=?", (text, int(upto), tid))

    def delete_thread(self, tid: int) -> None:
        if tid < 0:
            with self._lock:
                self._private.pop(tid, None)
            return
        with self._lock, self._db:
            self._tomb("threads", "id=?", (tid,))
            self._db.execute("DELETE FROM threads WHERE id=?", (tid,))

    def add(self, tid: int, role: str, content: str, model: str = "", sent: str = "") -> None:
        now = time.time()
        if tid < 0:
            with self._lock:
                p = self._private.get(tid)
                if p is not None:
                    p["msgs"].append({"role": role, "content": content, "model": model, "at": now, "sent": sent})
                    p["updated"] = now
            return
        with self._lock, self._db:
            self.changes += 1
            self._db.execute("INSERT INTO messages(uid, thread, role, content, model, at, sent) VALUES (?,?,?,?,?,?,?)",
                             (new_uid(), tid, role, content, model, now, sent))
            self._db.execute("UPDATE threads SET updated=? WHERE id=?", (now, tid))

    def trim_tail(self, tid: int, n: int) -> None:
        """Removes the last n messages of a chat (answer again / edit the last message); other devices drop them too."""
        if n <= 0:
            return
        if tid < 0:
            with self._lock:
                p = self._private.get(tid)
                if p is not None:
                    del p["msgs"][-n:]
            return
        where = "id IN (SELECT id FROM messages WHERE thread=? ORDER BY id DESC LIMIT ?)"
        with self._lock, self._db:
            self._tomb("messages", where, (tid, n))
            self._db.execute(f"DELETE FROM messages WHERE {where}", (tid, n))

    def messages(self, tid: int) -> list[dict]:
        if tid < 0:
            with self._lock:
                return [dict(m) for m in (self._private.get(tid) or {}).get("msgs", [])]
        return self._q("SELECT role, content, model, at, sent FROM messages WHERE thread=? ORDER BY id", (tid,))

    def search(self, query: str, limit: int = 40) -> list[dict]:
        """Chats whose name or messages contain the words (any case, any language), newest first, with a snippet
        around the first match: [{id, title, updated, hits, snippet}]."""
        q = " ".join((query or "").split()).lower()
        if len(q) < 2:
            return []
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._lock:
            rows = self._db.execute(
                "SELECT t.id, t.title, t.updated, (SELECT COUNT(*) FROM messages m WHERE m.thread=t.id AND lc(m.content) LIKE ? ESCAPE '\\') AS hits,"
                " (SELECT m.content FROM messages m WHERE m.thread=t.id AND lc(m.content) LIKE ? ESCAPE '\\' ORDER BY m.id LIMIT 1) AS first"
                " FROM threads t WHERE lc(t.title) LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM messages m WHERE m.thread=t.id AND lc(m.content) LIKE ? ESCAPE '\\')"
                " ORDER BY t.updated DESC LIMIT ?", (like, like, like, like, int(limit))).fetchall()
        out = []
        for r in rows:
            text = " ".join((r["first"] or "").split())
            i = text.lower().find(q)
            snippet = ""
            if i >= 0:
                a, b = max(0, i - 40), min(len(text), i + len(q) + 80)
                snippet = ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")
            out.append({"id": r["id"], "title": r["title"], "updated": r["updated"], "hits": r["hits"], "snippet": snippet})
        return out

    # memory: short facts about the user, shown to the model in the system prompt
    def add_fact(self, text: str, force: bool = False) -> int:
        """The new fact's id; 0 if it is already there; -1 if memory is full (nothing old is dropped behind the
        user's back: they choose what to forget). force: the user added it by hand, so it goes in anyway."""
        text = plain_fact(text)
        if not text:
            return 0
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM facts WHERE lc(text)=lc(?)", (text,)).fetchone():
                return 0
            if not force and self._db.execute("SELECT COUNT(*) FROM facts").fetchone()[0] >= MAX_FACTS:
                return -1
            self.changes += 1
            return self._db.execute("INSERT INTO facts(uid, text, at) VALUES (?,?,?)", (new_uid(), text, time.time())).lastrowid

    def facts(self) -> list[dict]:
        """Shown and sent without Markdown marks (facts saved before 1.1.4 may have them; the saved text stays)."""
        return [{**f, "text": plain_fact(f["text"]) or f["text"]} for f in self._q("SELECT id, text, at FROM facts ORDER BY id")]

    def delete_fact(self, fid: int) -> None:
        with self._lock, self._db:
            self._tomb("facts", "id=?", (fid,))
            self._db.execute("DELETE FROM facts WHERE id=?", (fid,))

    def forget_facts(self, text: str) -> int:
        text = text.strip()
        if not text:
            return 0
        with self._lock, self._db:
            self._tomb("facts", "instr(lc(text), lc(?)) > 0", (text,))
            return self._db.execute("DELETE FROM facts WHERE instr(lc(text), lc(?)) > 0", (text,)).rowcount

    # reminders
    def add_reminder(self, text: str, due: float, repeat: str = "") -> int:
        repeat = repeat if repeat in REPEATS else ""
        with self._lock, self._db:
            self.changes += 1
            now = time.time()
            return self._db.execute("INSERT INTO reminders(uid, text, due, created, changed, repeat) VALUES (?,?,?,?,?,?)",
                                    (new_uid(), text, due, now, now, repeat)).lastrowid

    def reminders(self) -> list[dict]:
        return self._q("SELECT id, text, due, repeat FROM reminders WHERE done=0 ORDER BY due")

    def cancel_reminder(self, rid: int) -> bool:
        with self._lock, self._db:
            self.changes += 1
            return self._db.execute("UPDATE reminders SET done=2, changed=? WHERE id=? AND done=0", (time.time(), rid)).rowcount > 0

    def take_due(self, now: float | None = None) -> list[dict]:
        """Reminders whose time has come; each is returned once. A one-time one is marked done; a repeating one
        moves on to its next time."""
        now = time.time() if now is None else now
        with self._lock, self._db:
            rows = [dict(r) for r in self._db.execute(
                "SELECT id, text, due, repeat FROM reminders WHERE done=0 AND due<=? ORDER BY due", (now,))]
            for r in rows:
                if r["repeat"] in REPEATS:
                    self._db.execute("UPDATE reminders SET due=?, changed=? WHERE id=?",
                                     (next_due(r["due"], r["repeat"], now), now, r["id"]))
                else:
                    self._db.execute("UPDATE reminders SET done=1, changed=? WHERE id=?", (now, r["id"]))
            if rows:
                self.changes += 1
            return rows

    def snooze_reminder(self, rid: int, minutes: float = 10, now: float | None = None) -> int:
        """Shows the reminder again in `minutes`. A one-time one comes back itself; for a repeating one a one-time
        copy is made (its regular time stays). The id of the reminder that will come back, 0 if there is none
        (unknown, or cancelled in the meantime)."""
        now = time.time() if now is None else now
        minutes = max(1.0, min(float(minutes), 24 * 60))
        with self._lock, self._db:
            r = self._db.execute("SELECT id, text, repeat, done FROM reminders WHERE id=?", (int(rid),)).fetchone()
            if not r or r["done"] == 2:
                return 0
            self.changes += 1
            if r["repeat"] in REPEATS:
                return self._db.execute("INSERT INTO reminders(uid, text, due, created, changed) VALUES (?,?,?,?,?)",
                                        (new_uid(), r["text"], now + minutes * 60, now, now)).lastrowid
            self._db.execute("UPDATE reminders SET due=?, done=0, changed=? WHERE id=?", (now + minutes * 60, now, r["id"]))
            return r["id"]

    # regular tasks (this device only: not synced, so two computers never run the same task)
    _TASK_FIELDS = {"text", "every", "at", "day", "only_if", "next", "last", "last_result", "paused", "thread"}

    def add_task(self, text: str, every: str, at: str, day: int, only_if: str, next_at: float) -> int:
        with self._lock, self._db:
            return self._db.execute("INSERT INTO tasks(text, every, at, day, only_if, next, created) VALUES (?,?,?,?,?,?,?)",
                                    (text, every, at, int(day), only_if, next_at, time.time())).lastrowid

    def tasks(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT * FROM tasks ORDER BY id")]

    def task(self, task_id: int) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
            return dict(r) if r else None

    def update_task(self, task_id: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in self._TASK_FIELDS}
        if fields:
            with self._lock, self._db:
                self._db.execute(f"UPDATE tasks SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                                 (*fields.values(), int(task_id)))

    def delete_task(self, task_id: int) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM tasks WHERE id=?", (int(task_id),)).rowcount > 0

    def due_tasks(self, now: float) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT * FROM tasks WHERE paused=0 AND next<=? ORDER BY next", (now,))]

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
                                         "changed": r["changed"], "repeat": r["repeat"]}
                              for r in q("SELECT uid, text, due, done, created, changed, repeat FROM reminders")},
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
            gone = {r[0] for r in db.execute("SELECT uid FROM deleted")}     # deleted here or there: never brought back
            for table in ("threads", "messages", "facts", "reminders"):
                for (uid,) in db.execute(f"SELECT uid FROM {table}").fetchall():
                    if uid in gone:
                        db.execute(f"DELETE FROM {table} WHERE uid=?", (uid,))
                        n += 1
            ids = {r[0]: r[1] for r in db.execute("SELECT uid, id FROM threads")}
            for uid, t in snap.get("threads", {}).items():
                if uid in ids:
                    n += db.execute("UPDATE threads SET title=?, title_at=? WHERE uid=? AND title_at<?",
                                    (t["title"], t["title_at"], uid, t["title_at"])).rowcount
                elif uid not in gone:
                    ids[uid] = db.execute("INSERT INTO threads(uid, title, title_at, created, updated) VALUES (?,?,?,?,?)",
                                          (uid, t["title"], t["title_at"], t["created"], t["created"])).lastrowid
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM messages")}
            for uid, m in sorted(snap.get("messages", {}).items(), key=lambda kv: kv[1]["at"] or 0):
                if uid not in have and uid not in gone and m["thread"] in ids:
                    db.execute("INSERT INTO messages(uid, thread, role, content, model, at) VALUES (?,?,?,?,?,?)",
                               (uid, ids[m["thread"]], m["role"], m["content"], m["model"], m["at"]))
                    db.execute("UPDATE threads SET updated=max(coalesce(updated,0), ?) WHERE id=?", (m["at"] or 0, ids[m["thread"]]))
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM facts")}
            for uid, f in snap.get("facts", {}).items():
                if uid not in have and uid not in gone:
                    db.execute("INSERT INTO facts(uid, text, at) VALUES (?,?,?)", (uid, f["text"], f["at"]))
                    n += 1
            have = {r[0] for r in db.execute("SELECT uid FROM reminders")}
            for uid, r in snap.get("reminders", {}).items():
                if uid in have:
                    # an older Lanterna sends no "repeat": the reminder keeps the one it has here
                    n += db.execute("UPDATE reminders SET text=?, due=?, done=?, changed=?, repeat=COALESCE(?, repeat)"
                                    " WHERE uid=? AND changed<?", (r["text"], r["due"], r["done"], r["changed"],
                                                                    r.get("repeat"), uid, r["changed"])).rowcount
                elif uid not in gone:
                    db.execute("INSERT INTO reminders(uid, text, due, done, created, changed, repeat) VALUES (?,?,?,?,?,?,?)",
                               (uid, r["text"], r["due"], r["done"], r["created"], r["changed"], r.get("repeat") or ""))
                    n += 1
            # a repeating reminder that an older Lanterna marked "shown" keeps coming back
            for row in db.execute("SELECT id, due, repeat FROM reminders WHERE done=1 AND repeat!=''").fetchall():
                db.execute("UPDATE reminders SET done=0, due=? WHERE id=?", (next_due(row[1], row[2], time.time()), row[0]))
        return n

    def restore(self, data: dict) -> dict:
        """Brings back from a backup what this database doesn't have: chats (a deleted one comes back as a chat
        again), their messages, memory, reminders and regular tasks. Nothing here is removed or changed; messages
        taken back on purpose (Retry, Edit) in a chat that is still here stay away. Returns counts."""
        out = {"chats": 0, "messages": 0, "facts": 0, "reminders": 0, "tasks": 0}
        now = time.time()
        with self._lock, self._db:
            db = self._db
            gone = {r[0] for r in db.execute("SELECT uid FROM deleted")}

            def alias(uid: str) -> str:
                # a deleted thing comes back under a new id that sync doesn't delete again; the same one each time,
                # so restoring the same backup twice adds nothing
                while uid in gone:
                    uid = "re-" + uid
                return uid
            ids = {r[0]: r[1] for r in db.execute("SELECT uid, id FROM threads")}
            back: dict[str, int] = {}                        # chats made again from the backup
            for uid, t in (data.get("threads") or {}).items():
                if alias(uid) in ids:
                    ids[uid] = ids[alias(uid)]
                    continue
                created = t.get("created") or now
                back[uid] = db.execute("INSERT INTO threads(uid, title, title_at, created, updated) VALUES (?,?,?,?,?)",
                                       (alias(uid), str(t.get("title") or ""), t.get("title_at") or 0, created,
                                        created)).lastrowid
                out["chats"] += 1
            have = {r[0] for r in db.execute("SELECT uid FROM messages")}
            for uid, m in sorted((data.get("messages") or {}).items(), key=lambda kv: kv[1].get("at") or 0):
                tid = back.get(m.get("thread")) or ids.get(m.get("thread"))
                if not tid or alias(uid) in have or (uid in gone and m.get("thread") not in back):
                    continue
                if m.get("role") not in ("user", "assistant"):
                    continue
                db.execute("INSERT INTO messages(uid, thread, role, content, model, at) VALUES (?,?,?,?,?,?)",
                           (alias(uid), tid, m["role"], str(m.get("content") or ""),
                            str(m.get("model") or ""), m.get("at") or now))
                db.execute("UPDATE threads SET updated=max(coalesce(updated,0), ?) WHERE id=?", (m.get("at") or now, tid))
                out["messages"] += 1
            have = {r[0] for r in db.execute("SELECT uid FROM facts")}
            texts = {str(r[0]).casefold() for r in db.execute("SELECT text FROM facts")}
            for uid, f in (data.get("facts") or {}).items():
                text = str(f.get("text") or "").strip()
                if not text or alias(uid) in have or text.casefold() in texts:
                    continue
                db.execute("INSERT INTO facts(uid, text, at) VALUES (?,?,?)", (alias(uid), text, f.get("at") or now))
                texts.add(text.casefold())
                out["facts"] += 1
            have = {r[0] for r in db.execute("SELECT uid FROM reminders")}
            for uid, r in (data.get("reminders") or {}).items():
                if alias(uid) in have or not r.get("text") or not r.get("due"):
                    continue
                db.execute("INSERT INTO reminders(uid, text, due, done, created, changed, repeat) VALUES (?,?,?,?,?,?,?)",
                           (alias(uid), str(r["text"]), float(r["due"]), int(bool(r.get("done"))),
                            r.get("created") or now, now, r.get("repeat") or ""))
                out["reminders"] += 1
            for row in db.execute("SELECT id, due, repeat FROM reminders WHERE done=1 AND repeat!=''").fetchall():
                db.execute("UPDATE reminders SET done=0, due=? WHERE id=?", (next_due(row[1], row[2], now), row[0]))
            mine = {(r[0], r[1], r[2]) for r in db.execute("SELECT text, every, at FROM tasks")}
            for tk in data.get("tasks") or []:
                k = (str(tk.get("text") or ""), str(tk.get("every") or "day"), str(tk.get("at") or "08:00"))
                if not k[0] or k in mine:
                    continue
                db.execute("INSERT INTO tasks(text, every, at, day, only_if, next, paused, created) VALUES (?,?,?,?,?,?,?,?)",
                           (*k, int(tk.get("day") or 0), str(tk.get("only_if") or ""), now + 60, int(bool(tk.get("paused"))), now))
                mine.add(k)
                out["tasks"] += 1
            if any(out.values()):
                self.changes += 1
        return out

    def close(self) -> None:
        self._db.close()
