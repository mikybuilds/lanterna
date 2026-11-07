"""Round 105: bug fixes — synced deletions, memory in any language, the window's own method list, honest notes,
notifications from Lanterna, the screen under the mouse, the right model per answer, search errors."""
import threading
import time

import httpx
import pytest

from lanterna import keys, notify, router, sent, tools
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Provider, ProviderError
from lanterna.store import MAX_FACTS, Store


def _api(tmp_path, monkeypatch, key=None):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: key if n == "groq" else None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


# ---------------------------------------------------------------- sync
def test_a_message_deleted_on_one_device_goes_on_the_other(tmp_path):
    a, b = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    tid = a.new_thread("Чат")
    a.add(tid, "user", "питання")
    a.add(tid, "assistant", "стара відповідь")
    b.import_sync(a.export_sync())
    a.trim_tail(tid, 1)                                   # "Retry": the old answer is removed on device A
    a.add(tid, "assistant", "нова відповідь")
    b.import_sync(a.export_sync())
    btid = b.threads()[0]["id"]
    assert [m["content"] for m in b.messages(btid)] == ["питання", "нова відповідь"]


def test_a_deleted_message_is_not_brought_back_by_an_older_copy(tmp_path):
    a, b = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    tid = a.new_thread("Чат")
    a.add(tid, "user", "питання")
    a.add(tid, "assistant", "стара відповідь")
    b.import_sync(a.export_sync())
    old_b = b.export_sync()                               # device B still has the old answer
    a.trim_tail(tid, 1)
    a.import_sync(old_b)                                  # ...and its copy arrives later
    assert [m["content"] for m in a.messages(tid)] == ["питання"]
    f = a.add_fact("Алергія на арахіс")
    copy = a.export_sync()
    a.delete_fact(f)
    a.import_sync(copy)
    assert a.facts() == []


# ---------------------------------------------------------------- memory
def test_memory_matches_any_language_and_never_drops_facts_silently(tmp_path):
    s = Store(tmp_path / "t.db")
    assert s.add_fact("Алергія на арахіс") > 0
    assert s.add_fact("алергія на АРАХІС") == 0           # the same fact in another case
    assert s.forget_facts("алергію") == 0 and s.forget_facts("АЛЕРГІЯ") == 1
    for i in range(MAX_FACTS):
        s.add_fact(f"факт {i}")
    assert s.add_fact("ще один") == -1 and len(s.facts()) == MAX_FACTS and s.facts()[0]["text"] == "факт 0"
    assert s.add_fact("додав сам", force=True) > 0


def test_the_memory_tool_says_when_memory_is_full(tmp_path):
    s = Store(tmp_path / "t.db")
    tb = tools.Toolbox(s)
    assert tb._remember("Живе в Києві").startswith("Saved")
    assert tb._remember("живе в києві").startswith("Already")
    for i in range(MAX_FACTS):
        s.add_fact(f"f{i}")
    assert "full" in tb._remember("Новий факт") and "Новий факт" not in [f["text"] for f in s.facts()]


def test_a_fact_added_by_hand_is_always_kept(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    for i in range(MAX_FACTS):
        api.store.add_fact(f"f{i}")
    assert "моє" in [f["text"] for f in api.add_fact("моє")]


# ---------------------------------------------------------------- the window gets only its own methods
def test_the_page_sees_only_the_allowed_methods(tmp_path, monkeypatch):
    from lanterna import gui
    api = _api(tmp_path, monkeypatch)
    page = gui.WindowApi(api)
    public = {n for n in vars(page) if not n.startswith("_")}
    assert public == gui.METHODS
    for name in ("store", "mcp", "actions", "toolbox", "settings", "action_confirm_any"):
        assert not hasattr(page, name)
    assert page.threads() == [] and page.state()["version"]


# ---------------------------------------------------------------- honest notes
def test_what_went_to_the_model_names_files_attached_earlier():
    from lanterna.app import _files_in
    msgs = [{"role": "user", "content": "дивись\n\n[File: звіт.pdf]\n```\nтекст\n```"},
            {"role": "assistant", "content": "ок"}, {"role": "user", "content": "[File: звіт.pdf]\n```\nще\n```\n[File: a.txt]\n```\n1\n```"}]
    assert _files_in(msgs) == ["звіт.pdf", "a.txt"]
    rows = sent.build("M", False, 3, False, 0, [], 0, [], old_files=["звіт.pdf"])
    assert {"t": "Files attached earlier in this chat (again): {names}", "v": {"names": "звіт.pdf"}} in rows


def test_a_failed_regular_task_tells_once(tmp_path, monkeypatch):
    from lanterna import app as appmod
    api = _api(tmp_path, monkeypatch)
    told = []
    monkeypatch.setattr(appmod, "notify", lambda *x: told.append(x))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: (_ for _ in ()).throw(ProviderError("network", "offline")))
    task = {"id": api.store.add_task("погода", "day", "08:00", 0, "", time.time()), "text": "погода", "last_result": ""}
    assert api._run_task(task) == ""
    assert len(told) == 1 and "погода" in told[0][1] and api._alerts
    task["last_result"] = api.store.task(task["id"])["last_result"]
    api._run_task(task)
    assert len(told) == 1                                  # not again on every failed run


def test_out_of_limits_says_when_a_model_is_back(tmp_path, monkeypatch):
    from lanterna.limits import TRACKER
    api = _api(tmp_path, monkeypatch, key="k")
    r = router.Router([Candidate("groq", "a", 90), Candidate("groq", "b", 80)])
    TRACKER.note("groq", "a", 429, {}, "", 3 * 3600)
    TRACKER.note("groq", "b", 429, {}, "", 5 * 3600)
    assert 3 * 3600 - 60 < api._back_in(r) <= 3 * 3600


# ---------------------------------------------------------------- notifications from the tray icon
def test_notifications_go_through_lanterna_s_icon(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "win32")
    got = []
    monkeypatch.setattr(notify, "TRAY", lambda title, msg: got.append((title, msg)) or True)
    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no PowerShell")))
    assert notify.notify("Lanterna", "Час на перерву") and got == [("Lanterna", "Час на перерву")]


def test_shell_balloon_needs_the_tray():
    from lanterna import shell
    s = shell.Shell("x", None, [], on_click=lambda: None, on_hotkey=lambda: None)
    assert s.balloon("t", "m") is False                    # no icon yet


# ---------------------------------------------------------------- the right model per answer
def test_each_answer_knows_its_own_model(monkeypatch):
    p = Provider("t", "T", "http://x.invalid/v1", needs_key=False)
    monkeypatch.setitem(PROVIDERS, "t", p)
    gate = threading.Event()

    class Fake:
        def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
            if model == "slow":
                gate.wait(5)
            yield model

        def close(self):
            pass
    r = router.Router([Candidate("t", "slow", 90), Candidate("t", "fast", 80)], client_for=lambda pid: Fake())
    seen = {}

    def ask(name, skip_first):
        if skip_first:
            r._until[("t", "slow")] = r._clock() + 60
        list(r.stream([{"role": "user", "content": name}]))
        seen[name] = r.used().model
    a = threading.Thread(target=ask, args=("A", False))
    a.start()
    time.sleep(0.2)
    ask("B", True)                                          # B answers with "fast" while A is still on "slow"
    gate.set()
    a.join(5)
    assert seen == {"A": "slow", "B": "fast"}


# ---------------------------------------------------------------- web search
def test_a_broken_search_page_is_not_nothing_found():
    def page(html):
        return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html)))
    assert tools.web_search("q", http=page('<div class="no-results">No results.</div>')) == "No results found."
    out = tools.web_search("q", http=page("<html>Please confirm you are a human</html>"))
    assert out.startswith("Error: web search isn't working")


def test_screen_under_the_mouse_is_windows_only(monkeypatch):
    import sys

    from lanterna import gui
    monkeypatch.setattr(sys, "platform", "linux")
    assert gui._cursor_monitor() is None
