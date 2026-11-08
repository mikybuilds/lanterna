"""Round 115: encrypted weekly backups (the last 4 kept) and restoring from a backup."""
import base64
import json
import os
import time
from pathlib import Path

import pytest

from lanterna import backup, export, gui, keys
from lanterna.store import Store

VAULT: dict = {}


@pytest.fixture(autouse=True)
def vault(monkeypatch):
    VAULT.clear()
    monkeypatch.setattr(keys, "stored_key", lambda n: VAULT.get(n, ""))
    monkeypatch.setattr(keys, "set_key", lambda n, v: VAULT.__setitem__(n, v))
    monkeypatch.setattr(keys, "delete_key", lambda n: VAULT.pop(n, None))
    monkeypatch.setattr(keys, "get_key", lambda n: None)


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.backup_dir = str(tmp_path / "backups")
    return api


def _fill(store):
    a = store.new_thread("Секретний план")
    store.add(a, "user", "Мій пароль від Wi-Fi — котик123")
    store.add(a, "assistant", "Записав.")
    store.add_fact("Любить чай")
    store.add_reminder("Подзвонити мамі", time.time() + 3600, "day")
    store.add_task("Погода в Києві", "day", "08:00", 0, "", time.time() + 3600)
    return a


def test_the_file_is_encrypted_and_only_a_key_is_stored(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    _fill(api.store)
    assert api.backup_set_password("short") == {"ok": False, "error": "password"}
    r = api.backup_set_password("довгий пароль 42")
    assert r["ok"] and r["status"]["on"] and r["name"].endswith(".lanterna-backup")
    blob = Path(r["path"]).read_bytes()
    assert blob[:4] == b"LNB1" and "котик".encode() not in blob and "Секрет".encode() not in blob
    assert "довгий" not in VAULT["backup-key"] and len(base64.b64decode(VAULT["backup-key"])) == 48
    snap = backup.read(blob)                                       # this computer: no password needed
    assert any(m["content"].startswith("Мій пароль") for m in snap["data"]["messages"].values())
    assert snap["data"]["tasks"][0]["text"] == "Погода в Києві" and "deleted" not in snap["data"]


def test_another_computer_needs_the_password(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    _fill(api.store)
    blob = Path(api.backup_set_password("довгий пароль 42")["path"]).read_bytes()
    api.backup_off()                                               # like a new computer: no key here
    assert not api.backup_status()["on"]
    with pytest.raises(backup.BackupError) as e:
        backup.read(blob)
    assert e.value.kind == "password"
    with pytest.raises(backup.BackupError):
        backup.read(blob, "не той пароль")
    assert backup.read(blob, "довгий пароль 42")["app"] == "Lanterna"
    other = _api(tmp_path / "pc2", monkeypatch)
    data = base64.b64encode(blob).decode()
    assert other.backup_restore("a.lanterna-backup", data) == {"ok": False, "error": "password", "sealed": True}
    r = other.backup_restore("a.lanterna-backup", data, "довгий пароль 42")
    assert r["ok"] and (r["chats"], r["messages"], r["facts"], r["reminders"], r["tasks"]) == (1, 2, 1, 1, 1)
    assert other.store.threads()[0]["title"] == "Секретний план"


def test_restore_brings_back_only_what_is_missing(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    a = _fill(api.store)
    b = api.store.new_thread("Друга")
    api.store.add(b, "user", "питання")
    api.store.add(b, "assistant", "стара відповідь")
    api.backup_set_password("довгий пароль 42")
    blob = backup.ours(Path(api.settings.backup_dir))[0].read_bytes()
    api.store.trim_tail(b, 1)                                       # Retry took the old answer back on purpose
    api.store.add(b, "assistant", "нова відповідь")
    api.delete_thread(a)                                            # deleted by mistake
    r = api.backup_restore("x.lanterna-backup", base64.b64encode(blob).decode())
    assert r["ok"] and r["chats"] == 1 and r["messages"] == 2 and r["facts"] == 0 and r["tasks"] == 0
    titles = sorted(t["title"] for t in api.store.threads())
    assert titles == ["Друга", "Секретний план"]
    assert [m["content"] for m in api.store.messages(b)] == ["питання", "нова відповідь"]
    again = api.backup_restore("x.lanterna-backup", base64.b64encode(blob).decode())
    assert again["chats"] == again["messages"] == 0
    # the chat that came back has new ids: sync won't delete it again
    snap = api.store.export_sync()
    assert not set(snap["threads"]) & set(snap["deleted"])


def test_an_older_plain_backup_restores_once(tmp_path, monkeypatch):
    src = Store(tmp_path / "old.db")
    _fill(src)
    doc = json.dumps(export.backup(src), ensure_ascii=False).encode()
    api = _api(tmp_path / "new", monkeypatch)
    r = api.backup_restore("Lanterna backup.json", base64.b64encode(doc).decode())
    assert r["ok"] and r["chats"] == 1 and r["messages"] == 2 and r["facts"] == 1 and r["reminders"] == 1
    assert api.backup_restore("Lanterna backup.json", base64.b64encode(doc).decode())["chats"] == 0
    assert api.backup_restore("x.json", base64.b64encode(b'{"hello": 1}').decode())["error"] == "format"
    assert api.backup_restore("x.bin", base64.b64encode(b"\x00\x01garbage").decode())["error"] == "format"


def test_the_last_four_are_kept_and_nothing_else_is_touched(tmp_path, monkeypatch):
    import datetime as dt
    api = _api(tmp_path, monkeypatch)
    _fill(api.store)
    folder = Path(api.settings.backup_dir)
    folder.mkdir(parents=True)
    (folder / "my notes.txt").write_text("mine")
    (folder / "Lanterna backup 2020-01-01.json").write_text("{}")   # not a weekly backup: never removed
    backup.set_password("довгий пароль 42")
    made = []
    for i in range(6):
        p = backup.write(api.store, folder, now=dt.datetime(2026, 1, 1) + dt.timedelta(days=7 * i))
        os.utime(p, (1_700_000_000 + i * 1000, 1_700_000_000 + i * 1000))
        made.append(p.name)
    left = sorted(p.name for p in folder.iterdir())
    assert left == sorted(made[2:] + ["my notes.txt", "Lanterna backup 2020-01-01.json"])


def test_weekly_by_itself(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    _fill(api.store)
    assert api.check_backup() == ""                                 # no password: nothing
    backup.set_password("довгий пароль 42")
    first = api.check_backup()
    assert first and Path(first).exists()
    assert api.check_backup() == ""                                 # not due again
    assert api.check_backup(now=time.time() + 8 * 24 * 3600)        # a week later
    api.settings.backup_dir = str(tmp_path / "file.txt")
    Path(api.settings.backup_dir).write_text("x")                   # a folder that can't be used
    later = time.time() + 30 * 24 * 3600
    assert api.check_backup(now=later) == ""
    assert api.settings.backup_last > later - backup.EVERY          # tries again in a day, not every minute


def test_folder_setting(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    assert api.backup_set_folder("relative/path")["ok"] is False
    assert api.backup_set_folder(str(tmp_path / "new folder"))["ok"]
    assert api.backup_status()["folder"] == str(tmp_path / "new folder") and api.backup_status()["custom"]
    assert api.backup_set_folder("")["status"]["folder"].endswith("Lanterna backups")


def test_the_window_can_use_it():
    assert {"backup_status", "backup_set_password", "backup_off", "backup_now", "backup_set_folder",
            "backup_open_folder", "backup_restore"} <= gui.METHODS
    js = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert "async function paintBackup(box)" in js and 'type="password" id="bk-pw"' in js
