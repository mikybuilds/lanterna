"""1.0: always at hand (tray, hotkey, quick window, screenshot). No real windows, tray or registry here."""
import sys

import pytest

from lanterna import autostart, keys, shell


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


# ---------------------------------------------------------------- hotkeys
def test_every_offered_hotkey_parses():
    for h in shell.HOTKEYS:
        assert (shell.parse_hotkey(h) is None) == (h == "")
    mods, vk = shell.parse_hotkey("ctrl+shift+space")
    assert mods & shell.MOD_CONTROL and mods & shell.MOD_SHIFT and mods & shell.MOD_NOREPEAT and vk == 0x20
    assert shell.parse_hotkey("alt+shift+l")[1] == ord("L")
    assert shell.parse_hotkey("space") is None and shell.parse_hotkey("ctrl+f13") is None
    assert shell.pretty_hotkey("ctrl+shift+space") == "Ctrl+Shift+Space"


def test_shell_does_nothing_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    s = shell.Shell("x", None, [], on_click=lambda: None, on_hotkey=lambda: None)
    assert s.start() is False and shell.tell_running_copy() is False


# ---------------------------------------------------------------- Start with Windows
class FakeReg:
    HKEY_CURRENT_USER, REG_SZ = 1, 1

    def __init__(self):
        self.values = {}

    class _K:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path):
        return self._K()

    CreateKey = OpenKey

    def QueryValueEx(self, k, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], 1

    def SetValueEx(self, k, name, _, kind, value):
        self.values[name] = value

    def DeleteValue(self, k, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_autostart_writes_and_removes_one_value(monkeypatch):
    reg = FakeReg()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(autostart, "_reg", lambda: reg)
    assert autostart.enabled() is False
    assert autostart.set_enabled(True) is True
    assert reg.values["Lanterna"].endswith("--tray")
    assert autostart.set_enabled(False) is False and reg.values == {}
    assert autostart.set_enabled(False) is False                      # off twice is fine


def test_autostart_is_off_on_other_systems(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert autostart.enabled() is False and autostart.set_enabled(True) is False


# ---------------------------------------------------------------- settings
def test_desktop_settings(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setattr(autostart, "set_enabled", lambda on: asked.append(on) or on)
    assert a.settings.tray is True and a.settings.hotkey == "ctrl+shift+space"
    a.save_settings({"hotkey": "rm -rf", "tray": 0})                  # unknown hotkeys are ignored
    assert a.settings.hotkey == "ctrl+shift+space" and a.settings.tray is False
    a.save_settings({"hotkey": "", "autostart": True})
    assert a.settings.hotkey == "" and asked == [True] and not hasattr(a.settings, "autostart")
    st = a.desktop_status()
    assert st["available"] is False and {h["id"] for h in st["hotkeys"]} == set(shell.HOTKEYS)
    assert a.screenshot() == {} and a.quick_hide() is None             # no window app: nothing happens


def test_window_methods_are_exposed():
    from lanterna import gui
    from lanterna.app import Api
    for m in ("desktop_status", "quick_hide", "open_in_main", "screenshot"):
        assert m in gui.METHODS and callable(getattr(Api, m))


# ---------------------------------------------------------------- the desk (fake windows)
class FakeWin:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name, *a))


class FakeShell:
    hwnd, hotkey_ok = 1, True

    def __init__(self):
        self.stopped = False
        self.hotkeys = []

    def stop(self):
        self.stopped = True

    def set_hotkey(self, h):
        self.hotkeys.append(h)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    from lanterna import gui, notify
    a = _api(tmp_path, monkeypatch)
    told = []
    monkeypatch.setattr(notify, "notify", lambda *x: told.append(x))
    d = gui.Desk(a, FakeWin(), FakeWin())
    d.shell = FakeShell()
    a._desk = d
    d.told = told
    return d


def test_closing_the_window_hides_it_in_the_tray(desk):
    import time
    assert desk.main_closing() is False
    assert ("hide",) in desk.main.calls and desk.main_shown is False
    assert desk.main_closing() is False
    time.sleep(0.2)
    assert len(desk.told) == 1 and desk.api.settings.tray_told           # the notice comes once


def test_closing_with_tray_off_ends_the_app(desk):
    import time
    desk.api.settings.tray = False
    assert desk.main_closing() is True and desk.quitting
    time.sleep(0.2)
    assert desk.shell.stopped and ("destroy",) in desk.quick.calls
    assert desk.quick_closing() is True


def test_quick_window_toggles_and_opens_in_main(desk):
    desk.toggle_quick()
    assert desk.quick_shown and ("show",) in desk.quick.calls
    assert any(c[0] == "evaluate_js" and "quickOpen(null)" in c[1] for c in desk.quick.calls)
    assert desk.quick_closing() is False and not desk.quick_shown          # its X only hides it
    desk.toggle_quick()
    desk.toggle_quick()
    assert not desk.quick_shown
    desk.open_in_main(7)
    assert any(c[0] == "evaluate_js" and "onShown(7)" in c[1] for c in desk.main.calls)


def test_screenshot_hides_the_quick_window_for_a_moment(desk, monkeypatch):
    from lanterna import gui
    monkeypatch.setattr(gui.Desk, "grab", staticmethod(lambda: {"name": "s.png", "size": 3, "data": "YWJj"}))
    desk.toggle_quick()
    desk.quick.calls.clear()
    assert desk.screenshot()["name"] == "s.png"
    assert [c[0] for c in desk.quick.calls] == ["hide", "show"]
    desk.hide_quick()
    desk.ask_screen()                                                       # tray: screen first, then the window
    assert desk.quick_shown and any("s.png" in c[1] for c in desk.quick.calls if c[0] == "evaluate_js")


def test_hotkey_change_reaches_the_tray(desk):
    desk.api.save_settings({"hotkey": "alt+shift+l"})
    assert desk.shell.hotkeys == ["alt+shift+l"]
    labels = [x[0] for x in desk._menu() if x]
    assert any("Alt+Shift+L" in s for s in labels) and len(labels) == 4


def test_grab_returns_a_png_attachment(monkeypatch):
    from PIL import Image, ImageGrab

    from lanterna import gui
    monkeypatch.setattr(ImageGrab, "grab", lambda *a, **k: Image.new("RGB", (40, 30), "white"))
    f = gui.Desk.grab()
    import base64
    assert f["name"].endswith(".png") and base64.b64decode(f["data"])[:4] == b"\x89PNG"


# ---------------------------------------------------------------- regular tasks
def test_next_run_for_every_kind():
    import datetime as dt

    from lanterna.tasks import next_run
    fri = dt.datetime(2026, 11, 6, 9, 30)                                   # a Friday
    assert next_run("day", "08:00", 0, fri) == dt.datetime(2026, 11, 7, 8, 0)
    assert next_run("day", "10:15", 0, fri) == dt.datetime(2026, 11, 6, 10, 15)
    assert next_run("weekday", "08:00", 0, fri) == dt.datetime(2026, 11, 9, 8, 0)      # skips the weekend
    assert next_run("week", "09:00", 2, fri) == dt.datetime(2026, 11, 11, 9, 0)         # next Wednesday
    assert next_run("hour", "00:05", 0, fri) == dt.datetime(2026, 11, 6, 10, 5)
    assert next_run("day", "nonsense", 0, fri) == dt.datetime(2026, 11, 7, 8, 0)        # bad time → 08:00


def test_describe_and_skip():
    from lanterna.i18n import t
    from lanterna.tasks import describe, is_skip
    uk = lambda s, **kw: t(s, "uk", **kw)                                    # noqa: E731
    assert describe({"every": "day", "at": "8:00"}, uk) == "Щодня о 08:00"
    assert describe({"every": "week", "at": "09:00", "day": 0}, uk) == "понеділок о 09:00"
    assert is_skip("SKIP") and is_skip(" skip. ") and not is_skip("Завтра дощ, візьми парасольку")


def test_model_tool_adds_lists_and_deletes_tasks(tmp_path, monkeypatch):
    import datetime as dt
    a = _api(tmp_path, monkeypatch)
    tb = a.toolbox
    tb._now = lambda: dt.datetime(2026, 11, 6, 9, 30)
    out = tb.run("add_task", '{"what": "Погода в Києві на сьогодні", "every": "day", "at": "08:00"}')
    assert out.startswith("Regular task #1 added") and "2026-11-07 08:00" in out
    assert "#1 Погода в Києві" in tb.run("list_tasks", "{}")
    for i in range(9):
        tb.run("add_task", f'{{"what": "задача {i}", "every": "hour"}}')
    assert tb.run("add_task", '{"what": "ще одна", "every": "day"}').startswith("Error: there are already 10")
    assert tb.run("delete_task", '{"id": 1}') == "Regular task #1 deleted."
    names = {s["function"]["name"] for s in tb.schemas("яка погода завтра?")}
    assert "add_task" not in names and "add_task" in {s["function"]["name"] for s in tb.schemas("щоранку кажи погоду")}


class _FakeConv:
    replies = []

    def __init__(self, router, name, lang="en", toolbox=None, **kw):
        self.router, self.toolbox, self.last_reply = router, toolbox, ""
        _FakeConv.tools = sorted(toolbox.tools) if toolbox else []

    def ask(self, text, images=None):
        _FakeConv.prompts.append(text)
        self.last_reply = _FakeConv.replies.pop(0)
        yield from ()


def _task_api(tmp_path, monkeypatch, replies):
    from lanterna import app as appmod
    a = _api(tmp_path, monkeypatch)
    _FakeConv.replies, _FakeConv.prompts = list(replies), []
    monkeypatch.setattr(appmod, "Conversation", _FakeConv)
    monkeypatch.setattr(appmod, "notify", lambda *x: _FakeConv.prompts.append(("notify", x)))

    class R:
        current = None
    monkeypatch.setattr(a, "_get_router", lambda refresh=False: R())
    return a


def test_running_a_task_saves_and_notifies(tmp_path, monkeypatch):
    a = _task_api(tmp_path, monkeypatch, ["Сьогодні +5, хмарно.", "SKIP"])
    a.task_add({"text": "Погода в Києві", "every": "day", "at": "08:00", "only_if": ""})
    r = a.task_run(1)
    assert r["ok"] and r["text"] == "Сьогодні +5, хмарно." and r["tid"]
    assert [m["content"] for m in a.store.messages(r["tid"])] == ["Сьогодні +5, хмарно."]
    assert a.store.thread(r["tid"])["title"].startswith("🔁 Погода")
    assert _FakeConv.tools == ["calculate", "date_calc", "read_page", "weather", "web_search"]     # safe tools only
    assert any(isinstance(p, tuple) and p[0] == "notify" for p in _FakeConv.prompts)
    assert a.alerts()[0]["kind"] == "task"
    a.store.update_task(1, only_if="буде дощ")
    r = a.task_run(1)                                                      # nothing to tell: no message, no alert
    assert r["ok"] and r["text"] == "" and "exactly SKIP" in _FakeConv.prompts[-1]
    assert len(a.store.messages(r["tid"])) == 1 and a.alerts() == []


def test_due_tasks_run_once_and_late_ones_are_skipped(tmp_path, monkeypatch):
    import time
    a = _task_api(tmp_path, monkeypatch, ["готово"] * 3)
    started = []
    monkeypatch.setattr(a, "_run_task", lambda task: started.append(task["id"]))
    a.task_add({"text": "a", "every": "day"})
    a.task_add({"text": "b", "every": "day"})
    now = time.time()
    a.store.update_task(1, next=now - 60)                                  # due a minute ago
    a.store.update_task(2, next=now - 7 * 3600)                            # missed while the PC was off
    assert a.check_tasks(now) == 1
    time.sleep(0.1)
    assert started == [1]
    assert all(x["next"] > now for x in a.store.tasks())                   # both moved to their next time
    assert a.check_tasks(now) == 0


def test_task_settings_api(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    assert a.task_add({"text": "  "})["ok"] is False
    lst = a.task_add({"text": "Новини", "every": "week", "day": 0, "at": "09:00"})["tasks"]
    assert lst[0]["when"] == "Every Monday at 09:00" and lst[0]["next_text"]
    lst = a.task_pause(1, True)
    assert lst[0]["paused"] == 1 and lst[0]["next_text"] == ""
    assert a.store.due_tasks(10 ** 12) == []                                # paused tasks never run
    assert a.task_pause(1, False)[0]["paused"] == 0
    assert a.task_delete(1) == [] and a.task_run(1)["ok"] is False
    from lanterna import gui
    for m in ("task_list", "task_add", "task_delete", "task_pause", "task_run"):
        assert m in gui.METHODS
