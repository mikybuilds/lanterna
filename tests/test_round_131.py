"""Round 131 (1.1.8b1): ideas from the idea scout, the quickest first.

- Chats can be renamed and pinned: in the window with the "⋯" button next to a chat (or a right-click on it), in the
  terminal from the menu (Ctrl+P). Pinned chats are at the top of the list. A pin goes to the other devices with
  sync and has its own time, so pinning on one computer and renaming on another keeps both.
- Documents stay whole: Lanterna writes only plain text, so it no longer writes text into a Word, Excel or PDF file
  (a new one wouldn't open, an old one would break) and says what it can do instead. Adding to the end of a file
  keeps a copy of the old one, with Undo, like rewriting it.
- Screen readers and keys in the window: buttons with only a picture have a name, a screen reader says "Thinking…",
  the answer, a card waiting for Confirm and errors; who wrote each message is said too. Ctrl+N starts a new chat,
  Ctrl+K goes to the chat search (by the key's place, so a Ukrainian layout works too), Esc closes the chat list.
- Stop: while Lanterna answers, the send button is Stop (and Esc stops it, in the terminal too). The words written
  so far stay in the chat; stopped before a word, no empty answer is kept.
"""
import asyncio
import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from lanterna import gui, sync
from lanterna import store as store_mod
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


# ---------------------------------------------------------------- pinned chats: the store and sync
def _when(st: Store, tid: int, updated: float) -> None:
    st._q("UPDATE threads SET updated=? WHERE id=?", (updated, tid))


def test_pinned_chats_come_first_also_in_an_old_database(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)                                    # a database from before pins
    con.execute("CREATE TABLE threads (id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created REAL, updated REAL)")
    con.execute("INSERT INTO threads(title, created, updated) VALUES ('Old', 1, 1)")
    con.commit()
    con.close()
    st = Store(db)
    old = st.threads()[0]
    assert old["title"] == "Old" and old["pinned"] == 0
    a, b = st.new_thread("A"), st.new_thread("B")
    _when(st, a, 10)
    _when(st, b, 20)
    assert [x["title"] for x in st.threads()] == ["B", "A", "Old"]
    st.pin(old["id"])
    assert [x["title"] for x in st.threads()] == ["Old", "B", "A"]
    assert st.thread(old["id"])["pinned"] == 1
    st.pin(a)
    assert [x["title"] for x in st.threads()] == ["A", "Old", "B"]      # pinned ones: the newest first too
    st.pin(old["id"], False)
    st.pin(a, False)
    assert [x["title"] for x in st.threads()] == ["B", "A", "Old"]
    p = st.new_private()
    st.pin(p)                                                    # a private chat is never kept anywhere
    assert [x["id"] for x in st.threads()] == [b, a, old["id"]]
    st.close()


def test_a_pin_has_its_own_time_in_sync():
    a = {**sync.empty(), "threads": {"t1": {"title": "Renamed here", "title_at": 9, "created": 1}}}
    b = {**sync.empty(), "threads": {"t1": {"title": "Old", "title_at": 1, "created": 1, "pinned": 1, "pinned_at": 5}}}
    m = sync.merge(a, b)
    assert m["threads"]["t1"] == {"title": "Renamed here", "title_at": 9, "created": 1, "pinned": 1, "pinned_at": 5}
    assert sync.merge(b, a)["threads"]["t1"] == m["threads"]["t1"]
    assert "pinned" not in a["threads"]["t1"]                    # what came in isn't changed
    later = {**sync.empty(), "threads": {"t1": {"title": "Old", "title_at": 1, "created": 1, "pinned": 0, "pinned_at": 7}}}
    assert sync.merge(m, later)["threads"]["t1"]["pinned"] == 0  # unpinned later elsewhere: unpinned
    assert sync.merge(later, m)["threads"]["t1"]["pinned"] == 0
    assert sync.merge(m, later)["threads"]["t1"]["title"] == "Renamed here"
    assert sync.merge(a, a)["threads"] == a["threads"]          # no pins (an older Lanterna): rows as they were


def test_pins_travel_between_computers_and_come_back_from_a_backup(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(store_mod.time, "time", lambda: clock[0])
    one, two = Store(tmp_path / "1.db"), Store(tmp_path / "2.db")
    tid = one.new_thread("Plans")
    assert "pinned" not in next(iter(one.export_sync()["threads"].values()))   # nothing new for an unpinned chat

    def meet(x: Store, y: Store) -> None:
        merged = sync.merge(x.export_sync(), y.export_sync())
        x.import_sync(merged)
        y.import_sync(merged)
    meet(one, two)
    assert [(c["title"], c["pinned"]) for c in two.threads()] == [("Plans", 0)]
    clock[0] = 1010
    one.pin(tid)
    meet(two, one)
    there = two.threads()[0]
    assert there["pinned"] == 1
    clock[0] = 1020
    two.pin(there["id"], False)                                  # unpinned on the laptop later
    clock[0] = 1030
    one.rename(tid, "Holiday plans")                             # renamed on the PC meanwhile
    meet(one, two)
    assert [(c["title"], c["pinned"]) for c in one.threads()] == [("Holiday plans", 0)]
    assert [(c["title"], c["pinned"]) for c in two.threads()] == [("Holiday plans", 0)]
    clock[0] = 1040
    one.pin(tid)
    snap = one.export_sync()
    fresh = Store(tmp_path / "3.db")
    assert fresh.restore(snap)["chats"] == 1
    assert [(c["title"], c["pinned"]) for c in fresh.threads()] == [("Holiday plans", 1)]
    for st in (one, two, fresh):
        st.close()


# ---------------------------------------------------------------- the window
def test_the_window_can_pin_and_rename_a_chat(api):  # noqa: F811  (the fake vault and model from test_tui)
    assert {"pin_thread", "rename_thread"} <= gui.METHODS
    tid = api.store.new_thread("Old name")
    assert api.pin_thread(tid) is True and api.threads()[0]["pinned"] == 1
    assert api.rename_thread(tid, "  New name  ") is True and api.threads()[0]["title"] == "New name"
    assert api.pin_thread(tid, False) is True and api.threads()[0]["pinned"] == 0


def test_the_chat_list_has_a_menu_that_the_keyboard_reaches():
    js = (UI / "app.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    body = js[js.index("async function refreshThreads"):js.index("function renameChat")]
    assert 'class="del"' not in body and "<i class" not in body  # no button hidden inside a button any more
    assert 'class="th-more"' in body and "aria-haspopup" in body and "aria-label" in body
    assert "oncontextmenu" in body and 'role="menu"' in body and 'role="menuitem"' in body
    assert "api.pin_thread(x.id, !x.pinned)" in body and 'group(t("Pinned"), pinned)' in body
    assert "ArrowDown" in body and "Escape" in body
    rename = js[js.index("function renameChat"):]
    assert "api.rename_thread(x.id, name)" in rename and 'maxlength="80"' in rename
    assert 'id="i-pin"' in html and 'id="i-dots"' in html
    assert ".th-row:focus-within .th-more" in css and ".th-menu" in css


# ---------------------------------------------------------------- documents stay whole
from lanterna import history, pcfiles  # noqa: E402
from lanterna.app import action_title  # noqa: E402
from lanterna.workspace import Actions, Workspace, WorkError  # noqa: E402


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "diary (2).txt").write_text("Monday: rain", encoding="utf-8")
    (root / "report.docx").write_bytes(b"PK\x03\x04 a real Word file")
    acts = Actions()
    cards: list = []
    acts.bind(cards, 7)
    w = Workspace(lambda: str(root), acts)
    w.cards = cards
    return w


def test_adding_to_a_file_keeps_a_copy_and_can_be_undone(ws):
    f = ws.root() / "diary (2).txt"
    ws.propose_write("diary (2).txt", "Tuesday: sun", "append")
    a = ws.actions.confirm(ws.cards[-1]["id"])
    assert a.state == "done" and f.read_text(encoding="utf-8") == "Monday: rain\nTuesday: sun"
    assert a.undo and a.undo["type"] == "restore_backup" and a.undo["path"] == str(f)
    assert Path(a.undo["backup"]).read_text(encoding="utf-8") == "Monday: rain"
    assert history.undo_restore_backup(a.undo["path"], a.undo["backup"])
    assert f.read_text(encoding="utf-8") == "Monday: rain"
    # the card's line names the copy once, also when the file's own name has brackets
    line = action_title("write_append", {"path": "diary (2).txt"}, a.result, "uk", done=True)
    assert line.startswith("Дописано в diary (2).txt (стару версію збережено в ") and line.count("diary (2).txt") == 2
    assert line.endswith(".txt)") and "(2).txt (2)" not in line


def test_no_text_goes_into_word_excel_or_pdf_files(ws, tmp_path):
    before = (ws.root() / "report.docx").read_bytes()
    for name, mode in (("report.docx", "append"), ("report.docx", "replace"), ("new.xlsx", "create"),
                       ("scan.PDF", "create"), ("photo.jpg", "create"), ("notes.odt", "create")):
        with pytest.raises(WorkError) as e:
            ws.propose_write(name, "Some text", mode)
        assert "Nothing was changed" in str(e.value) and ".md" in str(e.value)
    assert not ws.cards and (ws.root() / "report.docx").read_bytes() == before
    ws.propose_write("report.md", "# Report", "create")       # what it offers instead works
    assert ws.actions.confirm(ws.cards[-1]["id"]).state == "done"
    # the file appeared as a .docx between the card and Confirm: still nothing written into it
    ws.propose_write("later.txt", "text", "create")
    card = ws.cards[-1]
    (ws.root() / "later.txt").write_text("someone else", encoding="utf-8")
    assert ws.actions.confirm(card["id"]).state == "failed"
    assert (ws.root() / "later.txt").read_text(encoding="utf-8") == "someone else"


def test_the_desktop_writer_refuses_documents_too(tmp_path):
    home = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in home.values():
        f.mkdir()
    acts, cards = Actions(), []
    acts.bind(cards, 3)
    pl = pcfiles.Places(acts, folders=lambda: home, opener=lambda p: None)
    with pytest.raises(WorkError) as e:
        pl.propose_write("desktop", "Letter.docx", "Dear Anna")
    assert "Letter.md" in str(e.value) and not cards and not list(home["desktop"].iterdir())
    assert "Nothing has been changed" in pl.propose_write("desktop", "Letter.txt", "Dear Anna") and len(cards) == 1


# ---------------------------------------------------------------- screen readers and keys (the window)
def _fn(js: str, start: str) -> str:
    """One top-level function of app.js: from its first line to the "}" that closes it at the line start."""
    i = js.index(start)
    return js[i:js.index("\n}\n", i) + 2]


def _main_layout(js: str) -> str:
    return js[js.index("function renderMain()"):js.index("$(\"#new\").onclick")]


def test_every_button_of_the_window_has_a_name():
    js = (UI / "app.js").read_text(encoding="utf-8")
    page = _main_layout(js)
    buttons = re.findall(r"<button([^>]*)>(.*?)</button>", page, re.S)
    assert len(buttons) >= 12
    for attrs, inner in buttons:
        words = re.sub(r"<[^>]+>", "", re.sub(r"\$\{icon\([^)]*\)\}", "", inner)).strip()
        named = "aria-label=" in attrs or "title=" in attrs or words
        runtime = 'id="lim"' in attrs or 'id="fold"' in attrs       # their words are put in right away
        assert named or runtime, attrs
    assert 'title="Send"' not in page and 'aria-label="${esc(t("Send"))}"' in page
    assert 'id="sr-say" aria-live="polite"' in page and 'role="heading"' in page
    assert 'id="threads" aria-label=' in page and 'id="input" rows="1"' in page
    assert re.search(r'<textarea id="input"[^>]*aria-label=', page)
    assert 'id="toasts" role="status" aria-live="polite"' in js


def test_a_screen_reader_hears_what_happens():
    js = (UI / "app.js").read_text(encoding="utf-8")
    send = _fn(js, "async function send(")
    assert 'announce(t("Thinking…"))' in send
    assert 't("Lanterna answered:") + " " + box.innerText)' in send   # innerText: list lines don't run together
    assert 'announce(t("A change is waiting for your Confirm."))' in send and "announce(msg)" in send
    helper = _fn(js, "function announce(")
    assert 'el.textContent = ""' in helper and ".slice(0, 3000)" in helper
    assert 'sr-only">${esc(t("You"))}: </span>' in js and '<span class="sr-only">Lanterna: </span>' in js
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".sr-only {" in css and ".th-menu button:focus-visible { background: var(--surface-2); outline: 2px" in css


def test_window_keys_work_with_any_keyboard_layout():
    js = (UI / "app.js").read_text(encoding="utf-8")
    keys = _fn(js, "function windowKeys(")
    assert 'e.code === "KeyN"' in keys and 'e.code === "KeyK"' in keys and "e.key === \"n\"" not in keys
    assert ".veil:not(.closing)" in keys and "QUICK" in keys
    assert 'aria-keyshortcuts="Control+N"' in js and 'aria-keyshortcuts="Control+K"' in js
    assert "windowKeys();" in _fn(js, "function renderMain()")


# ---------------------------------------------------------------- Stop
def _slow_model(monkeypatch, first_words: bool):
    """A pretend model: (maybe) a few words, then it waits until the test lets it go on."""
    from lanterna import app as app_mod
    started, go_on = threading.Event(), threading.Event()

    class Slow:
        def __init__(self, *a, **kw):
            self.last_reply = ""

        def ask(self, text, images=None):
            if first_words:
                yield "Перша частина. "
            started.set()
            go_on.wait(5)
            yield "Друга частина."
            self.last_reply = "Перша частина. Друга частина."
    monkeypatch.setattr(app_mod, "Conversation", Slow)
    return started, go_on


def _until_done(api, sid):  # noqa: F811
    for _ in range(200):
        p = api.poll(sid)
        if p.get("done"):
            return p
        time.sleep(0.02)
    raise AssertionError("the answer never ended")


@pytest.mark.parametrize("first_words", [True, False])
def test_stop_keeps_what_was_written(api, monkeypatch, first_words):  # noqa: F811
    assert "stop_answer" in gui.METHODS
    started, go_on = _slow_model(monkeypatch, first_words)
    tid = api.new_thread()["id"]
    r = api.send(tid, "Розкажи довгу історію")
    assert started.wait(5)
    assert api.stop_answer(r["stream"]) is True
    go_on.set()
    p = _until_done(api, r["stream"])
    assert p["stopped"] is True and p["error"] is None
    msgs = api.store.messages(tid)
    if first_words:
        assert p["final"] == "Перша частина." and "Друга" not in p["final"]
        assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[-1]["content"] == "Перша частина."
    else:
        assert p["final"] == "" and [m["role"] for m in msgs] == ["user"]      # no empty answer is kept
    assert api.stop_answer(r["stream"]) is False                                 # it is over


def test_an_answer_that_is_not_stopped_is_whole(api, monkeypatch):  # noqa: F811
    started, go_on = _slow_model(monkeypatch, True)
    tid = api.new_thread()["id"]
    r = api.send(tid, "Розкажи")
    assert started.wait(5)
    go_on.set()
    p = _until_done(api, r["stream"])
    assert p["stopped"] is False and p["final"] == "Перша частина. Друга частина."


@pytest.mark.parametrize("raw, kept", [
    ("вітер\n*", "вітер"), ("вітер\n- **", "вітер"), ("Гарно **", "Гарно"), ("План:\n\n1.", "План:"),
    ("Код:\n```", "Код:"), ("Текст.\n#", "Текст."),
    ("use `ls`", "use `ls`"), ("C#", "C#"), ("C++", "C++"), ("a_b", "a_b"), ("**Так**", "**Так**"), ("Готово!", "Готово!"),
])
def test_a_stopped_answer_loses_only_its_half_written_mark(raw, kept):
    from lanterna.app import cut_reply
    assert cut_reply(raw) == kept


def test_the_window_turns_send_into_stop():
    js = (UI / "app.js").read_text(encoding="utf-8")
    busy = _fn(js, "function setBusy(")
    assert 'b.classList.toggle("stop", on)' in busy and 'icon(on ? "stop" : "send")' in busy and "aria-label" in busy
    stop = _fn(js, "function stopAnswer(")
    assert "live.stopping = true" in stop and "api.stop_answer(live.sid)" in stop
    send = _fn(js, "async function send(")
    assert "if (live.stopping) api.stop_answer(r.stream)" in send          # pressed before the answer had started
    assert "p.stopped && !p.final.trim()" in send and "bot.remove()" in send
    assert '$("#send").onclick = () => (busy ? stopAnswer() : send());' in js
    keys = _fn(js, "function windowKeys(")
    assert 'e.key === "Escape" && !e.defaultPrevented && busy' in keys and "stopAnswer()" in keys
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".send.stop {" in css


# ---------------------------------------------------------------- the terminal
pytest.importorskip("textual")
from textual.widgets import Input, Label, ListView  # noqa: E402

from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)


def _row_text(lv: ListView, i: int) -> str:
    return str(lv.children[i].query_one(Label).content)


def test_the_terminal_renames_and_pins_the_open_chat(api):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "en", "provider": "groq"})
    a, b = api.store.new_thread("First"), api.store.new_thread("Second")
    _when(api.store, a, 10)
    _when(api.store, b, 20)

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            lv = scr.query_one("#threads", ListView)
            assert await wait_for(pilot, lambda: len(lv.children) == 2 and _row_text(lv, 0) == "Second")
            scr.open_thread(a)
            names = [c.title for c in app.get_system_commands(scr)]
            assert "Rename chat" in names and "Pin chat" in names and "Unpin chat" not in names
            assert names.index("Rename chat") < names.index("Delete chat")
            scr.action_pin_chat()
            assert api.store.thread(a)["pinned"] == 1
            assert await wait_for(pilot, lambda: _row_text(lv, 0) == "📌 First")
            assert "Unpin chat" in [c.title for c in app.get_system_commands(scr)]
            scr.action_rename_chat()
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "NameScreen")
            box = app.screen.query_one("#name", Input)
            assert box.value == "First"
            box.value = "Trip to Lviv"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: api.store.thread(a)["title"] == "Trip to Lviv")
            assert await wait_for(pilot, lambda: _row_text(lv, 0) == "📌 Trip to Lviv")
            assert str(scr.query_one("#chattitle", Label).content) == "Trip to Lviv"
            scr.action_rename_chat()                             # Esc leaves the name as it was
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "NameScreen")
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: chat_ready(app))
            assert api.store.thread(a)["title"] == "Trip to Lviv"
            scr.action_pin_chat()
            assert api.store.thread(a)["pinned"] == 0
            assert await wait_for(pilot, lambda: _row_text(lv, 0) == "Second")
    asyncio.run(go())


def test_the_terminal_stops_with_esc(api, monkeypatch):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "en", "provider": "groq"})
    started, go_on = _slow_model(monkeypatch, True)

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            assert "Stop the answer" not in [c.title for c in app.get_system_commands(scr)]
            box = scr.query_one("#composer", Input)
            box.value = "Розкажи довгу історію"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: started.is_set() and scr._stream)
            assert "Stop the answer" in [c.title for c in app.get_system_commands(scr)]
            await pilot.press("escape")
            go_on.set()
            assert await wait_for(pilot, lambda: scr._stream is None)
            tid = scr.tid
            assert [m["content"] for m in api.store.messages(tid)] == ["Розкажи довгу історію", "Перша частина."]
            notes = [str(w.content) for w in scr.query(".msg-note")]
            assert any("Stopped." in n for n in notes)
    asyncio.run(go())


def test_new_strings_are_translated_everywhere():
    from lanterna import i18n
    for s in ("Rename chat", "Pin chat", "Unpin chat", "Chat name", "Unpinned.", "Pinned to the top of the list.",
              "the old version is saved in {path}", "Stop the answer", "Stopped."):
        assert set(i18n._T[s]) == {"uk", "it"}
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
    js = (UI / "app.js").read_text(encoding="utf-8")
    for s in ("Pinned", "Chat options", "Pin to top", "Unpin", "Rename", "Send", "Lanterna answered:",
              "A change is waiting for your Confirm.", "Stop (Esc)", "Stopped."):
        assert re.search(r'^\s*"' + re.escape(s) + r'": \{ uk: "', js, re.M), s
