"""Round 104: a free hotkey by itself, search across chats, remembering silent models, help with copied text."""
import time

import pytest

from lanterna import health, keys, providers, router, shell
from lanterna.discovery import Candidate
from lanterna.providers import Provider, ProviderError


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


# ---------------------------------------------------------------- search across chats
def test_search_finds_words_in_any_case_and_language(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    s = api.store
    a = s.new_thread("Погода")
    s.add(a, "user", "Яка погода завтра у Феррарі?")
    s.add(a, "assistant", "Завтра у Феррарі +12°C і туман. " + "Довгий текст. " * 30)
    b = s.new_thread("Ferrari trip")
    s.add(b, "user", "plan a trip")
    c = s.new_thread("Інше")
    s.add(c, "user", "100% готово так")

    found = api.search_chats("ФЕРРАРІ")
    assert [x["id"] for x in found] == [a] and found[0]["hits"] == 2
    assert found[0]["snippet"] == "Яка погода завтра у Феррарі?"           # the first message with the words
    s.add(b, "assistant", "Слово " * 40 + "туман" + " і ще" * 40)
    snip = next(x for x in api.search_chats("туман") if x["id"] == b)["snippet"]
    assert snip.startswith("…") and snip.endswith("…") and "туман" in snip and len(snip) < 150
    assert [x["id"] for x in api.search_chats("ferrari")] == [b]          # the name counts too
    assert [x["id"] for x in api.search_chats("  туман   ")] == [b, a]           # newest first
    assert api.search_chats("%") == [] and api.search_chats("а") == []    # 2+ letters
    assert [x["id"] for x in api.search_chats("0% г")] == [c]               # % and _ are plain letters
    assert api.search_chats("о_т") == [] and api.search_chats("нема такого") == []


def test_search_is_offered_to_the_window():
    from lanterna import gui
    from lanterna.app import Api
    assert "search_chats" in gui.METHODS and callable(Api.search_chats)


def test_terminal_search_box(tmp_path, monkeypatch):
    import asyncio

    from textual.widgets import Input, ListView

    from lanterna.tui import LanternaApp
    api = _api(tmp_path, monkeypatch)
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True
    a = api.store.new_thread("Погода")
    api.store.add(a, "user", "туман у Феррарі")
    api.store.new_thread("Інше")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause(0.3)
            lv = app.screen.query_one("#threads", ListView)
            assert len(lv.children) == 2
            box = app.screen.query_one("#findchats", Input)
            box.value = "феррарі"
            await pilot.pause(0.4)
            assert [i.name for i in lv.children] == [str(a)]
            box.value = "нема такого"
            await pilot.pause(0.4)
            assert [i.name for i in lv.children] == [""]                   # "Nothing found." can't be opened
            box.value = ""
            await pilot.pause(0.4)
            assert len(lv.children) == 2
    asyncio.run(go())


# ---------------------------------------------------------------- remembering silent models
def test_health_rests_grow_and_an_answer_clears_them(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    now = [1000.0]
    h = health.Health(clock=lambda: now[0])
    assert h.bad("gemini", "x", "timeout") == 3600
    assert h.bad("gemini", "x", "timeout") == 3600                 # still resting: not a new strike
    now[0] += 3601
    assert h.bad("gemini", "x", "timeout") == 6 * 3600
    now[0] += 7 * 3600
    assert h.bad("gemini", "x", "gone") == 24 * 3600
    assert 0 < h.resting()["gemini/x"] <= 24 * 3600
    assert health.Health(clock=lambda: now[0]).rest_until("gemini", "x") == now[0] + 24 * 3600   # kept on disk
    h.good("gemini", "x")
    assert h.rest_until("gemini", "x") == 0 and h.resting() == {}


def test_health_picks_what_to_check(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    now = [1_000_000.0]
    h = health.Health(clock=lambda: now[0])
    cands = [Candidate("gemini", "ok1", 90, status="ok"), Candidate("gemini", "new1", 90),
             Candidate("gemini", "sick", 88, status="ok"), Candidate("ollama", "local", 80),
             *[Candidate("groq", f"n{i}", 70) for i in range(9)]]
    h.bad("gemini", "sick", "timeout")
    assert [c.model for c in h.to_check(cands)] == ["new1", "n0", "n1", "n2", "n3", "n4"]     # 6 at most, no local
    now[0] += 3601                                                   # the rest is over: worth a new try
    assert [c.model for c in h.to_check(cands)][:2] == ["new1", "sick"]
    assert h.due()
    h._checked()
    assert not h.due()
    now[0] += health.CHECK_EVERY
    assert h.due()


class _PingRouter:
    def __init__(self, cands, answers):
        self.candidates, self.answers, self.asked = cands, answers, []

    def client(self, pid):
        return self

    def ping(self, model):
        self.asked.append(model)
        a = self.answers[model]
        if isinstance(a, Exception):
            raise a
        return a


def test_the_daily_check(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    h = health.Health()
    cands = [Candidate("gemini", m, 90) for m in ("good", "stuck", "gone", "busy")]
    r = _PingRouter(cands, {"good": 0.5, "stuck": ProviderError("timeout", "slow"),
                            "gone": ProviderError("bad_request", "no", 404), "busy": ProviderError("rate", "429", 429)})
    waits = []
    out = h.check(r, sleep=waits.append)
    assert out == {"gemini/good": "ok", "gemini/stuck": "bad", "gemini/gone": "bad", "gemini/busy": "busy"}
    assert cands[0].status == "ok" and cands[0].latency == 0.5
    assert set(h.resting()) == {"gemini/stuck", "gemini/gone"}
    assert waits == [health.GAP["gemini"]] * 3                       # Gemini allows 5 a minute
    assert not h.due()
    # no internet: stop at once, and try again next time
    h2_home = tmp_path / "other"
    monkeypatch.setenv("LANTERNA_HOME", str(h2_home))
    h2 = health.Health()
    r2 = _PingRouter([Candidate("groq", "a", 90), Candidate("groq", "b", 90)],
                     {"a": ProviderError("network", "offline"), "b": 0.1})
    assert h2.check(r2, sleep=lambda s: None) == {} and r2.asked == ["a"] and h2.due()


def test_router_remembers_a_silent_model_across_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    p = Provider("t", "Test", "http://127.0.0.1:9/v1", needs_key=False)
    monkeypatch.setitem(providers.PROVIDERS, "t", p)

    class Fake:
        def __init__(self, bad):
            self.bad = bad

        def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
            if model in self.bad:
                raise ProviderError("timeout", "silent")
            yield "hi"

        def close(self):
            pass

    cands = lambda: [Candidate("t", "stuck", 90), Candidate("t", "fine", 80)]
    r1 = router.Router(cands(), client_for=lambda pid: Fake({"stuck"}))
    assert "".join(x for x in r1.stream([{"role": "user", "content": "q"}]) if isinstance(x, str)) == "hi"
    r2 = router.Router(cands(), client_for=lambda pid: Fake(set()))          # "after a restart"
    assert [c.model for c in r2.available()] == ["fine"] and "t/stuck" in r2.resting()
    health.HEALTH.bad("t", "fine", "timeout")                                  # an answer clears the mark
    monkeypatch.setattr(health.HEALTH, "rest_until", lambda p_, m: 0.0)
    r3 = router.Router([Candidate("t", "fine", 80)], client_for=lambda pid: Fake(set()))
    list(r3.stream([{"role": "user", "content": "q"}]))
    assert "t/fine" not in health.Health().resting() and "t/stuck" in health.Health().resting()


def test_ping_tells_a_silent_model_from_no_internet(monkeypatch):
    import httpx

    def silent(request):
        raise httpx.ReadTimeout("no answer", request=request)

    def offline(request):
        raise httpx.ConnectError("no route", request=request)
    for handler, kind in ((silent, "timeout"), (offline, "network")):
        c = providers.Client(Provider("t", "T", "http://x.invalid/v1", needs_key=False), transport=httpx.MockTransport(handler))
        with pytest.raises(ProviderError) as e:
            c.ping("m")
        assert e.value.kind == kind


# ---------------------------------------------------------------- the desk: free hotkey, copied text
class FakeWin:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name, *a))


class BusyShell:
    """Windows gives only the hotkeys in `free`."""
    hwnd = 1

    def __init__(self, free, current="ctrl+shift+space"):
        self.free, self.hotkey = set(free), current
        self.hotkey_ok = current in self.free
        self.copied_at = 0.0

    def set_hotkey(self, h):
        self.hotkey, self.hotkey_ok = h, h in self.free

    def stop(self):
        pass


@pytest.fixture
def desk(tmp_path, monkeypatch):
    from lanterna import gui, notify
    a = _api(tmp_path, monkeypatch)
    told = []
    monkeypatch.setattr(notify, "notify", lambda *x: told.append(x))
    d = gui.Desk(a, FakeWin(), FakeWin())
    a._desk = d
    d.told = told
    return d


def test_a_taken_default_hotkey_moves_to_a_free_one_once(desk):
    desk.shell = BusyShell(free={"alt+shift+l", "ctrl+shift+l"})
    assert desk.free_hotkey() == "alt+shift+l"
    s = desk.api.settings
    assert s.hotkey == "alt+shift+l" and s.hotkey_moved and desk.shell.hotkey_ok
    time.sleep(0.2)
    assert desk.told and "Ctrl+Shift+Space" in desk.told[0][1] and "Alt+Shift+L" in desk.told[0][1]
    desk.shell = BusyShell(free=set(), current="alt+shift+l")
    assert desk.free_hotkey() == "" and s.hotkey == "alt+shift+l"           # once only, never again


def test_a_hotkey_the_user_picked_is_not_changed(desk):
    desk.api.settings.hotkey = "ctrl+alt+space"
    desk.shell = BusyShell(free={"alt+shift+l"}, current="ctrl+alt+space")
    assert desk.free_hotkey() == "" and desk.api.settings.hotkey == "ctrl+alt+space" and not desk.told


def test_nothing_free_keeps_the_default(desk):
    desk.shell = BusyShell(free=set())
    assert desk.free_hotkey() == "" and desk.shell.hotkey == "ctrl+shift+space"
    assert desk.api.settings.hotkey == "ctrl+shift+space" and not desk.api.settings.hotkey_moved


def test_text_copied_a_moment_ago_is_offered_once(desk, monkeypatch):
    import json
    reads = []
    monkeypatch.setattr(shell, "clipboard_text", lambda: reads.append(1) or "  Buongiorno a tutti  ")
    desk.shell = BusyShell(free={"ctrl+shift+space"})
    desk.toggle_quick()                                     # nothing copied: the clipboard isn't even read
    assert reads == [] and desk.quick.calls[0][1].endswith('quickOpen(null, "")')
    desk.hide_quick()
    desk.shell.copied_at = time.time() - 5
    desk.toggle_quick()
    assert desk.quick.calls[-3][1].endswith(f'quickOpen(null, {json.dumps("Buongiorno a tutti")})') and reads == [1]
    desk.hide_quick()
    desk.toggle_quick()                                     # the same copy isn't offered twice
    assert desk.quick.calls[-3][1].endswith('quickOpen(null, "")') and reads == [1]
    desk.hide_quick()
    desk.shell.copied_at = time.time() - 600                # copied long ago
    desk.toggle_quick()
    assert desk.quick.calls[-3][1].endswith('quickOpen(null, "")')
    desk.hide_quick()
    desk.api.save_settings({"copied_text": False})          # turned off in Settings
    desk.shell.copied_at = time.time()
    desk.toggle_quick()
    assert desk.quick.calls[-3][1].endswith('quickOpen(null, "")') and reads == [1]


def test_clipboard_reading_is_windows_only(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    assert shell.clipboard_text() == ""


def test_new_settings_save(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api.save_settings({"copied_text": False, "hotkey_moved": True})
    assert api.settings.copied_text is False and api.settings.hotkey_moved is True


def test_window_script_parses():
    """A broken app.js shows an empty window: check its syntax whenever Node is around (it is on CI)."""
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node here")
    ui = Path(__file__).resolve().parents[1] / "src" / "lanterna" / "ui" / "app.js"
    r = subprocess.run([node, "--check", str(ui)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
