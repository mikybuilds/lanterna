"""Round 114: a picture copied a moment ago (a snip from Win+Shift+S) is offered in the quick window."""
import base64
import json
import sys
import time
from pathlib import Path

import pytest

from lanterna import gui, keys, shell
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


class FakeWin:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, code):
        self.calls.append(("evaluate_js", code))

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))

    def restore(self):
        self.calls.append(("restore",))


class Shell:
    hwnd = 1
    hotkey, hotkey_ok = "ctrl+shift+space", True

    def __init__(self):
        self.copied_at = 0.0


@pytest.fixture
def desk(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    d = gui.Desk(api, FakeWin(), FakeWin())
    d.shell = Shell()
    return d


def _opened(desk):
    return [c[1] for c in desk.quick.calls if c[0] == "evaluate_js"][-1]


def test_a_fresh_picture_is_offered_once(desk, monkeypatch):
    seen = []
    monkeypatch.setattr(shell, "clipboard_text", lambda: "")
    monkeypatch.setattr(shell, "clipboard_image", lambda: seen.append(1) or b"\x89PNG fake")
    desk.toggle_quick()                                    # nothing copied lately: the clipboard isn't read
    assert seen == [] and _opened(desk).endswith('quickOpen(null, "")')
    desk.hide_quick()
    desk.shell.copied_at = time.time() - 3
    desk.toggle_quick()
    call = _opened(desk)
    pic = json.loads(call[call.index('quickOpen(null, "", ') + len('quickOpen(null, "", '):-1])
    assert pic["name"].startswith("snip-") and base64.b64decode(pic["data"]) == b"\x89PNG fake" and seen == [1]
    desk.hide_quick()
    desk.toggle_quick()                                    # the same copy isn't offered twice
    assert _opened(desk).endswith('quickOpen(null, "")') and seen == [1]
    desk.hide_quick()
    desk.api.save_settings({"copied_text": False})         # the same switch as for copied text
    desk.shell.copied_at = time.time()
    desk.toggle_quick()
    assert _opened(desk).endswith('quickOpen(null, "")') and seen == [1]


def test_copied_text_wins_over_a_picture(desk, monkeypatch):
    monkeypatch.setattr(shell, "clipboard_text", lambda: "Hello there")
    monkeypatch.setattr(shell, "clipboard_image", lambda: pytest.fail("not read when there is text"))
    desk.shell.copied_at = time.time()
    desk.toggle_quick()
    assert _opened(desk).endswith('quickOpen(null, "Hello there")')


def test_private_copies_and_other_systems_give_nothing(monkeypatch):
    monkeypatch.setattr(shell, "clipboard_private", lambda: True)
    assert shell.clipboard_image() == b""
    monkeypatch.setattr(sys, "platform", "linux")
    assert shell.clipboard_image() == b"" and shell.clipboard_private() is True


def test_the_quick_window_has_the_card():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "function showCopiedPic(pic)" in js and "showCopiedPic(pic);" in js and "window.quickOpen = (file, copied, pic)" in js
