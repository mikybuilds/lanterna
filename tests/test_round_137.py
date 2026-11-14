"""Round 137 (1.1.8b7): reminders also when Lanterna is closed.

- At the next reminder's time the system starts Lanterna for a moment: on Windows a task of the user's own in Task
  Scheduler (no administrator rights; missed while the computer was off, it comes right after signing in), on Linux
  a systemd user timer (Persistent). That run shows what is due as a notification, sets the alarm for the next one
  and quits; with no reminders left the task or timer goes away. Nothing runs in between.
- A reminder never comes twice: the open Lanterna and that run (or the window and the terminal) share the database,
  and the first one to look takes it. While Lanterna is open the run leaves the reminders to it; quitting hands them
  over, also one due in a moment.
- The alarm never rings before the reminder's time, and one that rings a moment early still finds it.
- Settings → Memory and reminders: "Remind me when Lanterna is closed too" (on by default, this computer only, not
  synced) turns all of it off. The uninstaller and `lanterna desktop --remove` take the alarm away.
- Tests, a second profile and previews (LANTERNA_HOME) never touch the system's scheduler.
"""
import asyncio
import json
import math
import re
import sys
import threading
import time
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from lanterna import cli, gui, i18n, keys, wake
from lanterna import notify as notify_mod
from lanterna.app import SYNC_PREFS, Api
from lanterna.config import Settings, data_dir
from lanterna.store import Store

ROOT = Path(__file__).resolve().parents[1]
UI = Path(gui.__file__).parent / "ui"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
CLOCK = "⏰"


@pytest.fixture
def alarm(monkeypatch):
    """wake.sync as on a normal computer (no LANTERNA_HOME), with a fake system alarm."""
    calls, result = [], {"ok": True}

    def fake_arm(when):
        calls.append(when)
        return result["ok"]
    fake_arm.calls, fake_arm.result = calls, result
    monkeypatch.setattr(wake, "allowed", lambda: True)
    monkeypatch.setattr(wake, "arm", fake_arm)
    monkeypatch.setattr(wake, "_state", None)
    return fake_arm


@pytest.fixture
def no_keys(monkeypatch):
    """Never the real key vault."""
    monkeypatch.setattr(keys, "get_key", lambda p: None)
    monkeypatch.setattr(keys, "stored_key", lambda p: "")
    monkeypatch.setattr(keys, "set_key", lambda p, k: None)
    monkeypatch.setattr(keys, "delete_key", lambda p: None)


def system(monkeypatch, **kw):
    monkeypatch.setattr(wake, "sys", types.SimpleNamespace(**kw))


# ---------------------------------------------------------------- the Windows task
def test_the_windows_task_runs_once_at_the_time_or_as_soon_as_it_can_after_it():
    when = time.mktime((2026, 12, 24, 18, 30, 0, 0, 0, -1))
    exe = r"D:\Програми\Lanterna & Co\Lanterna.exe"                   # any letters, a space and "&"
    xml = wake.task_xml(when, [exe, "--remind"])
    assert xml.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    root = ET.fromstring(xml.encode("utf-16"))
    get = lambda path: root.findtext(path, namespaces=NS)               # noqa: E731
    assert get("t:Triggers/t:TimeTrigger/t:StartBoundary") == "2026-12-24T18:30:00"     # local time, once
    assert get("t:Settings/t:StartWhenAvailable") == "true"            # missed (computer off): right after sign-in
    assert get("t:Settings/t:DisallowStartIfOnBatteries") == "false"
    assert get("t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"
    assert get("t:Principals/t:Principal/t:LogonType") == "InteractiveToken"   # the user's own, while signed in
    assert get("t:Principals/t:Principal/t:RunLevel") == "LeastPrivilege"      # no administrator rights
    assert get("t:Actions/t:Exec/t:Command") == f'"{exe}"'             # spaces: quoted; "&" survives
    assert get("t:Actions/t:Exec/t:Arguments") == "--remind"
    plain = ET.fromstring(wake.task_xml(when, [r"C:\L\Lanterna.exe", "--remind"]).encode("utf-16"))
    assert plain.findtext("t:Actions/t:Exec/t:Command", namespaces=NS) == r"C:\L\Lanterna.exe"


def test_windows_alarm_is_set_with_schtasks_and_taken_away(monkeypatch):
    system(monkeypatch, platform="win32", executable=r"C:\L\Lanterna.exe", frozen=True)
    seen = []

    def fake_run(args, timeout=30):
        seen.append(list(args))
        if "/XML" in args:
            raw = Path(args[args.index("/XML") + 1]).read_bytes()
            assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")              # UTF-16 with its mark, as schtasks wants
            seen.append(raw.decode("utf-16"))
        return 0
    monkeypatch.setattr(wake, "_run", fake_run)
    when = time.time() + 3600
    assert wake.arm(when)
    assert seen[0][:5] == ["schtasks", "/Create", "/TN", r"Lanterna\Reminders", "/XML"] and seen[0][-1] == "/F"
    assert time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(when)) in seen[1]
    assert r"<Command>C:\L\Lanterna.exe</Command><Arguments>--remind</Arguments>" in seen[1]
    assert not Path(seen[0][5]).exists()                               # the file was only for schtasks
    seen.clear()
    assert wake.arm(None)
    assert seen == [["schtasks", "/Delete", "/TN", r"Lanterna\Reminders", "/F"]]
    monkeypatch.setattr(wake, "_run", lambda args, timeout=30: 1)
    assert not wake.arm(when)                                          # schtasks said no

    def missing(args, timeout=30):
        raise FileNotFoundError("schtasks")
    monkeypatch.setattr(wake, "_run", missing)
    assert not wake.arm(when)


# ---------------------------------------------------------------- the Linux timer
def test_linux_alarm_is_a_persistent_user_timer(monkeypatch, tmp_path):
    system(monkeypatch, platform="linux", executable="/usr/bin/python3")
    tools = {"systemctl": "/usr/bin/systemctl", "lanterna": "/usr/local/bin/lanterna"}
    monkeypatch.setattr(wake, "shutil", types.SimpleNamespace(which=tools.get))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    seen = []
    monkeypatch.setattr(wake, "_run", lambda args, timeout=30: seen.append(list(args)) or 0)
    when = time.mktime((2026, 12, 24, 18, 30, 0, 0, 0, -1))
    assert wake.arm(when)
    units = tmp_path / "cfg" / "systemd" / "user"
    timer = (units / "lanterna-reminders.timer").read_text(encoding="utf-8")
    service = (units / "lanterna-reminders.service").read_text(encoding="utf-8")
    assert "OnCalendar=2026-12-24 18:30:00\n" in timer and "Persistent=true\n" in timer   # missed: when it starts
    assert "WantedBy=timers.target" in timer
    assert 'ExecStart="/usr/local/bin/lanterna" "remind"\n' in service and "Type=oneshot" in service
    user = ["systemctl", "--user"]
    assert seen == [user + ["daemon-reload"], user + ["enable", "lanterna-reminders.timer"],
                    user + ["restart", "lanterna-reminders.timer"]]
    stamp = tmp_path / "data" / "systemd" / "timers" / "stamp-lanterna-reminders.timer"
    stamp.parent.mkdir(parents=True)
    stamp.write_text("", encoding="utf-8")
    seen.clear()
    assert wake.arm(None)
    assert seen == [user + ["disable", "--now", "lanterna-reminders.timer"], user + ["daemon-reload"]]
    assert not list(units.iterdir()) and not stamp.exists()            # nothing of it is left
    seen.clear()
    assert wake.arm(None) and seen == []                               # not there: nothing to do
    tools.pop("systemctl")
    assert not wake.arm(when)                                          # no systemd: the open Lanterna still reminds


def test_systemd_command_lines_are_quoted():
    assert wake._sd_quote('/opt/My "Apps"/50%/lanterna') == '"/opt/My \\"Apps\\"/50%%/lanterna"'
    assert wake.service_text(["/a b/lanterna", "remind"]).endswith('ExecStart="/a b/lanterna" "remind"\n')


def test_what_the_system_runs(monkeypatch, tmp_path):
    system(monkeypatch, platform="win32", executable=r"C:\Program Files\Lanterna\Lanterna.exe", frozen=True)
    assert wake.command() == [r"C:\Program Files\Lanterna\Lanterna.exe", "--remind"]
    py = tmp_path / "python.exe"
    py.write_bytes(b"")
    system(monkeypatch, platform="win32", executable=str(py))
    assert wake.command() == [str(py), "-m", "lanterna.gui", "--remind"]
    (tmp_path / "pythonw.exe").write_bytes(b"")
    assert wake.command() == [str(tmp_path / "pythonw.exe"), "-m", "lanterna.gui", "--remind"]   # no black window
    system(monkeypatch, platform="linux", executable="/usr/bin/python3")
    monkeypatch.setattr(wake, "shutil", types.SimpleNamespace(which={"lanterna": "/usr/local/bin/lanterna"}.get))
    assert wake.command() == ["/usr/local/bin/lanterna", "remind"]
    monkeypatch.setattr(wake, "shutil", types.SimpleNamespace(which=lambda name: None))
    assert wake.command() == [str(Path("/usr/bin/python3")), "-m", "lanterna.cli", "remind"]


# ---------------------------------------------------------------- moving the alarm
def test_the_alarm_follows_the_next_reminder(alarm, tmp_path):
    store = Store(tmp_path / "r.db")
    now = time.time()
    assert wake.sync(store, now=now) and alarm.calls == [None]          # no reminders: none (taken away for sure)
    assert wake.sync(store, now=now + 15) and alarm.calls == [None]     # nothing changed: the system isn't asked
    store.add_reminder("Подзвонити мамі", now + 600.4)
    wake.sync(store, now=now + 30)
    assert alarm.calls[-1] == math.ceil(now + 600.4)                    # never before its time
    n = len(alarm.calls)
    wake.sync(store, now=now + 45)
    assert len(alarm.calls) == n
    store.add_reminder("Ліки", now + 300)
    wake.sync(store, now=now + 60)
    assert alarm.calls[-1] == math.ceil(now + 300)
    saved = json.loads((data_dir() / "wake.json").read_text(encoding="utf-8"))
    assert saved["armed"] == math.ceil(now + 300) and saved["ok"] is True
    n = len(alarm.calls)
    wake.sync(store, now=now + 297)                                     # due in a moment: the open Lanterna shows it
    assert len(alarm.calls) == n
    wake.sync(store, now=now + 297, closing=True)                       # quitting: the system shows it in a moment
    assert alarm.calls[-1] == math.ceil(now + 297 + wake.SOON)
    wake.sync(store, on=False, now=now + 298)                           # turned off: taken away
    assert alarm.calls[-1] is None


def test_an_alarm_that_couldnt_be_set_is_tried_again_after_an_hour(alarm, tmp_path):
    store = Store(tmp_path / "r.db")
    now = time.time()
    store.add_reminder("Ліки", now + 7200)
    alarm.result["ok"] = False
    assert not wake.sync(store, now=now)
    assert not wake.sync(store, now=now + 15) and len(alarm.calls) == 1   # not every 15 seconds
    alarm.result["ok"] = True
    assert wake.sync(store, now=now + wake.RETRY + 1) and len(alarm.calls) == 2


def test_a_moved_lanterna_gets_the_alarm_again_and_a_new_start_remembers_it(alarm, tmp_path, monkeypatch):
    store = Store(tmp_path / "r.db")
    now = time.time()
    store.add_reminder("Ліки", now + 7200)
    monkeypatch.setattr(wake, "command", lambda: [r"D:\Old\Lanterna.exe", "--remind"])
    wake.sync(store, now=now)
    monkeypatch.setattr(wake, "command", lambda: [r"E:\New\Lanterna.exe", "--remind"])
    wake.sync(store, now=now + 15)
    assert len(alarm.calls) == 2
    monkeypatch.setattr(wake, "_state", None)                           # Lanterna starts again: reads what was set
    wake.sync(store, now=now + 30)
    assert len(alarm.calls) == 2


def test_tests_and_second_profiles_never_touch_the_system(monkeypatch, tmp_path, no_keys):
    assert not wake.allowed()                                           # LANTERNA_HOME is set for every test
    monkeypatch.setattr(wake, "arm", lambda when: pytest.fail("the system's scheduler was touched"))
    store = Store(tmp_path / "r.db")
    store.add_reminder("x", time.time() + 600)
    assert wake.sync(store) is False
    api = Api(store=Store(tmp_path / "a.db"), scheduler=False)
    api.closing()
    api._arm_for_closed()
    monkeypatch.delenv("LANTERNA_HOME")
    assert wake.allowed()


# ---------------------------------------------------------------- the run at a reminder's time
def test_the_run_shows_what_is_due_and_sets_the_next(alarm, monkeypatch):
    shown = []
    monkeypatch.setattr(notify_mod, "notify", lambda title, msg: shown.append((title, msg)) or True)
    now = time.time()
    st = Store()
    st.add_reminder("Полити квіти", now - 3600)                         # the computer was off then
    st.add_reminder("Ліки", now + 2)                                    # the alarm rang a moment early
    later = st.add_reminder("Зустріч", now + 7200)
    st.close()
    assert wake.remind_now() == 0
    late = time.strftime("%H:%M", time.localtime(now - 3600))
    assert shown == [(f"Lanterna {CLOCK}", f"Полити квіти ({late})"), (f"Lanterna {CLOCK}", "Ліки")]
    assert alarm.calls == [math.ceil(now + 7200)]
    st = Store()
    assert [r["id"] for r in st.reminders()] == [later]
    st.add_reminder("Ще одне", time.time() - 1)
    st.close()

    shown.clear()
    wake.still_here()                                                   # Lanterna is open: it shows them itself
    assert wake.running()
    assert wake.remind_now() == 0 and shown == []
    assert not wake.running(time.time() + wake.ALIVE + 1)               # crashed or killed: the system takes over
    wake.gone()                                                         # quit: the system takes over at once
    assert not wake.running()

    s = Settings.load()
    s.remind_closed = False
    s.save()
    assert wake.remind_now() == 0 and shown == []                       # turned off: nothing, and no alarm
    assert alarm.calls[-1] is None
    st = Store()
    assert len(st.reminders()) == 2                                     # still there for when Lanterna opens
    st.close()


def test_two_programs_never_show_one_reminder_twice(tmp_path):
    db = tmp_path / "two.db"
    a, b = Store(db), Store(db)
    for round_ in range(15):
        now = time.time()
        ids = {a.add_reminder(f"r{round_}-{i}", now - 1) for i in range(4)}
        got = [[], []]
        go = threading.Barrier(2)

        def take(i, st):
            go.wait()
            got[i] += [r["id"] for r in st.take_due()]
        threads = [threading.Thread(target=take, args=(i, st)) for i, st in enumerate((a, b))]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)
        assert not set(got[0]) & set(got[1]), round_
        assert set(got[0]) | set(got[1]) == ids, round_
    a.close()
    b.close()


def test_the_app_hears_about_every_change_to_reminders(tmp_path):
    st = Store(tmp_path / "h.db")
    heard = []
    st.on_reminders = lambda: heard.append(1)
    assert st.next_reminder() is None
    now = time.time()
    rid = st.add_reminder("a", now + 600)
    st.add_reminder("b", now + 300)
    assert st.next_reminder() == pytest.approx(now + 300)
    st.snooze_reminder(rid, 30)
    st.cancel_reminder(rid)
    assert len(heard) == 4
    st.on_reminders = lambda: 1 / 0                                     # a broken listener never breaks saving
    assert st.add_reminder("c", now + 900)
    st.close()


def test_the_app_hands_the_reminders_over_when_it_quits(monkeypatch, tmp_path, no_keys):
    monkeypatch.setattr(wake, "allowed", lambda: True)
    calls = []
    monkeypatch.setattr(wake, "sync", lambda store, on=True, now=None, closing=False: calls.append((on, closing)) or True)
    api = Api(store=Store(tmp_path / "a.db"), scheduler=False)
    wake.still_here()
    api.closing()
    assert not wake.running() and calls == [(True, True)]
    assert api.state()["platform"] == sys.platform                      # the window shows the right note
    api.save_settings({"remind_closed": False})
    assert api.settings.remind_closed is False and api._wake.is_set()   # the loop moves the alarm at once
    assert Settings.load().remind_closed is False
    api._arm_for_closed()
    assert calls[-1] == (False, False)
    assert Settings().remind_closed is True and "remind_closed" not in SYNC_PREFS   # on; this computer only


def test_the_system_can_start_the_run(monkeypatch):
    monkeypatch.setattr(wake, "remind_now", lambda: 7)
    assert gui.main(["--remind"]) == 7
    assert cli.main(["remind"]) == 7


def test_removing_lanterna_takes_the_alarm_away(monkeypatch):
    from lanterna import desktop
    gone = []
    monkeypatch.setattr(desktop, "remove", lambda: gone.append("menu"))
    monkeypatch.setattr(wake, "forget", lambda: gone.append("alarm"))
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli.main(["desktop", "--remove"]) == 0
    assert gone == ["menu", "alarm"]
    iss = (ROOT / "packaging" / "lanterna.iss").read_text(encoding="utf-8")
    assert "[UninstallRun]" in iss and '/Delete /TN ""Lanterna\\Reminders"" /F' in iss
    assert wake.TASK == "Lanterna\\Reminders"


def test_forget_takes_it_away_and_forgets_what_was_set(alarm):
    (data_dir() / "wake.json").write_text('{"armed": 1, "ok": true}', encoding="utf-8")
    wake.forget()
    assert alarm.calls == [None] and not (data_dir() / "wake.json").exists()


# ---------------------------------------------------------------- what Settings say
def test_settings_say_what_happens_in_every_language():
    js = (UI / "app.js").read_text(encoding="utf-8")
    block = js[js.index("const WAKES = {"):]
    block = block[:block.index("};")]
    assert dict(re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', block)) == wake.NOTES     # the window says the same
    assert 'id="remind-closed"' in js and "save_settings({ remind_closed: rc.checked })" in js
    for s in [*wake.NOTES.values(), "Remind me when Lanterna is closed too"]:          # the window and the terminal
        for lang in set(i18n.LANGS) - {"en"}:
            assert i18n.t(s, lang) != s, (lang, s)
    old = "Reminders pop up while Lanterna is open."                    # (the window's own, from before)
    assert re.search(re.escape(f'"{old}": {{ uk: "') + '.+, it: "', js)
    assert all(i18n.catalog(lang).get(old) for lang in i18n.FILE_LANGS)


@pytest.mark.skipif(sys.platform not in wake.NOTES, reason="no system alarm on this system")
def test_terminal_settings_turn_it_off(tmp_path, no_keys):
    pytest.importorskip("textual")
    from textual.widgets import Checkbox

    from lanterna.tui import LanternaApp, SettingsScreen
    api = Api(store=Store(tmp_path / "t.db"))
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True

    async def wait(pilot, cond):
        for _ in range(150):
            await pilot.pause(0.05)
            if cond():
                return
        raise AssertionError("timeout")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(110, 60)) as pilot:
            await pilot.pause(0.3)
            app.screen.action_settings()
            await wait(pilot, lambda: isinstance(app.screen, SettingsScreen) and app.screen.query("#remindclosed"))
            box = app.screen.query_one("#remindclosed", Checkbox)
            assert box.value is True
            box.value = False
            await wait(pilot, lambda: api.settings.remind_closed is False)
    asyncio.run(go())
