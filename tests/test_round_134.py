"""Round 134 (1.1.8b4): «Sources» under a reply, only the pages its tools really opened.

- The links come from what read_page and web_search brought back, never from the model's words: a link the model
  wrote itself (maybe made up) is not a source. A page that was found and then opened is under «Sources» with its
  title from the search; the other search results it saw are folded under «Search results: N».
- A link that looks like a scam is never shown, not even from a search; the check runs again when a chat is opened.
- They are kept with the reply on this computer (also in a private chat, in memory), shown in the window, the
  terminal and the Markdown export of a chat. The label is short; the whole address shows before a click, and the
  window opens https links only.
"""
import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

from lanterna import export, gui, i18n, sources, tools
from lanterna.discovery import Candidate
from lanterna.providers import ToolCall, ToolCalls
from lanterna.router import Router
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"
LVIV = "https://uk.wikipedia.org/wiki/%D0%9B%D1%8C%D0%B2%D1%96%D0%B2"
RESULTS = ("Web results (DuckDuckGo):\n"
           f"1. Львів — Вікіпедія\n   {LVIV}\n   Місто на заході України\n"
           "2. Погода у Львові\n   https://meteo.example.org/lviv\n   Прогноз на тиждень\n"
           "3. Бонус від банку\n   https://privat-bonus.top/x\n   Отримайте виплату")


class Box:
    """A toolbox that answers like the real tools."""

    def __init__(self, answers):
        self.answers, self.focus, self.page_limit, self.store = answers, "", 0, "the store"
        self.tools = {"web_search": "🔎"}

    def schemas(self, context=None):
        return ["web_search"]

    def run(self, name, arguments):
        return self.answers[name]


# ---------------------------------------------------------------- what counts as a source
def test_only_what_the_tools_brought_back_counts():
    box = Box({"web_search": RESULTS, "read_page": "Page https://www.example.org/after-redirect:\nthe text",
               "pc_info": "Page https://not-a-page.example.org/:\nWindows 11"})
    noted = sources.Noted(box)
    for name in ("web_search", "read_page", "read_page", "pc_info"):
        assert noted.run(name, "{}") == box.answers[name]           # the model gets the same answer
    assert noted.data() == {
        "read": [{"title": "", "url": "https://www.example.org/after-redirect"}],      # where it really ended up
        "found": [{"title": "Львів — Вікіпедія", "url": LVIV},
                  {"title": "Погода у Львові", "url": "https://meteo.example.org/lviv"}]}  # no fake bank, no PC info


@pytest.mark.parametrize("out", ["Error: the page answered HTTP 404.", "Error: could not open the page (ConnectTimeout).",
                                 "Not opened: this link looks like a scam (…).", "No results found.",
                                 "Error: web search isn't working right now (…)."])
def test_a_page_that_did_not_open_is_not_a_source(out):
    noted = sources.Noted(Box({"read_page": out, "web_search": out}))
    noted.run("read_page", "{}")
    noted.run("web_search", "{}")
    assert noted.data() == {}


def test_a_found_page_that_was_opened_is_under_sources_with_its_title():
    noted = sources.Noted(Box({"web_search": RESULTS, "read_page": f"Page {LVIV}/:\nМісто…"}))
    noted.run("web_search", "{}")
    noted.run("read_page", "{}")
    noted.run("read_page", "{}")                                     # read twice: one source
    assert noted.data() == {"read": [{"title": "Львів — Вікіпедія", "url": LVIV + "/"}],
                            "found": [{"title": "Погода у Львові", "url": "https://meteo.example.org/lviv"}]}


def test_there_are_at_most_a_few():
    many = "Web results (DuckDuckGo):\n" + "\n".join(f"{i}. T{i}\n   https://s{i}.example.org/\n   x" for i in range(1, 30))
    noted = sources.Noted(Box({"web_search": many}))
    noted.run("web_search", "{}")
    assert len(noted.data()["found"]) == sources.MAX_FOUND


def test_the_wrapper_is_the_same_toolbox_for_the_chat():
    tb = tools.Toolbox(None)
    noted = sources.Noted(tb)
    noted.focus, noted.page_limit = "Львів", 1234                   # the chat sets them for read_page
    assert (tb.focus, tb.page_limit) == ("Львів", 1234) and noted.focus == "Львів"
    assert noted.tools.keys() == tb.tools.keys() and noted.schemas(None) == tb.schemas(None) and noted.store is None
    assert noted.run("calculate", json.dumps({"expression": "2+2"})) == tb.run("calculate", json.dumps({"expression": "2+2"}))
    assert noted.data() == {}


# ---------------------------------------------------------------- how they are shown
def test_the_view_is_readable_and_safe():
    raw = sources.dumps({"read": [{"title": "", "url": LVIV}, {"title": "", "url": "javascript:alert(1)"},
                                  {"title": "", "url": "https://privat-bonus.top/x"}],   # stored before it was known
                         "found": [{"title": "A " * 80, "url": "http://old.example.org/a"},
                                   {"title": "Сайт", "url": "https://xn--80aswg.xn--j1amh/"}]})
    v = sources.view(raw)
    assert v["read"] == [{"url": LVIV, "site": "uk.wikipedia.org", "label": "uk.wikipedia.org/wiki/Львів"}]
    assert v["found"][0]["label"].endswith("…") and len(v["found"][0]["label"]) <= sources.LABEL
    assert v["found"][1]["site"] == "сайт.укр"
    assert v["found"][0]["url"].startswith("http://")                # shown, but the window doesn't make it a link
    for bad in ("", "not json", "[1, 2]", '{"read": "x"}', '{"read": [{"url": 5}]}', '{"found": [null]}'):
        assert sources.view(bad) == {}, bad
    assert sources.dumps({}) == ""


def test_the_export_of_a_chat_has_them():
    raw = sources.dumps({"read": [{"title": "Львів [вікі]", "url": LVIV}],
                         "found": [{"title": "Погода", "url": "https://meteo.example.org/lviv"}]})
    md = export.chat_markdown("Львів", [{"role": "user", "content": "Що там?", "at": 0, "sources": ""},
                                        {"role": "assistant", "content": "Місто.", "at": 0, "model": "M", "sources": raw}], "uk")
    assert f"**Джерела:**\n\n- [Львів (вікі)](<{LVIV}>)\n" in md
    assert "**Результати пошуку: 1**\n\n- [Погода](<https://meteo.example.org/lviv>)" in md
    assert export.chat_markdown("x", [{"role": "assistant", "content": "y", "at": 0}]).count("**") == 0


def test_the_window_shows_them_under_the_words():
    js = (UI / "app.js").read_text(encoding="utf-8")
    i = js.index("function sourcesBox(src)")
    box = js[i:js.index("\n}\n", i)]
    assert 's.url.startsWith("https://")' in box and 'data-href="${esc(s.url)}" title="${esc(s.url)}"' in box
    assert 't("Sources:")' in box and 't("Search results: {n}", { n: found.length })' in box and "<details" in box
    assert "addBot(m.content, m.model, m.sent, m.second, m.sources)" in js           # an opened chat
    i = js.index("function addBot(")
    bot = js[i:js.index("\n}\n", i)]
    assert bot.index("${sourcesBox(sources)}") < bot.index('<div class="meta">')
    i = js.index("else if (p.final !== undefined) {")
    final = js[i:js.index("else if (p.text)", i)]
    assert final.index("sourcesBox(p.sources)") < final.index('<div class="meta">') < final.index("sentBox(p.sent)")
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".srcs {" in css and "details.srcs-s" in css and "text-overflow: ellipsis" in css[css.index(".srcs {"):]


def test_new_strings_are_translated_everywhere():
    for s in ("Sources:", "Search results: {n}",
              "Only pages Lanterna really opened for this answer, not links the model wrote itself"):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)


# ---------------------------------------------------------------- a whole answer
class Fake:
    """A model that searches, opens a page and then answers with a link of its own."""

    def __init__(self, replies):
        self.replies = replies

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        yield from (self.replies.pop(0) if self.replies else ["Гаразд."])     # side jobs: a title and so on

    def close(self):
        pass


def _model(api, monkeypatch, *replies):
    fake = Fake([list(r) for r in replies])
    router = Router([Candidate("groq", "fake-model", 50)], client_for=lambda pid: fake)
    router.current = router.candidates[0]
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    monkeypatch.setattr(tools, "web_search", lambda query, **kw: RESULTS)
    monkeypatch.setattr(tools, "read_page", lambda url, **kw: f"Page {url}:\nЛьвів — місто на заході України.")


SEARCH = ToolCalls([ToolCall("c1", "web_search", json.dumps({"query": "Львів"}))])
READ = ToolCalls([ToolCall("c2", "read_page", json.dumps({"url": LVIV}))])
ANSWER = "Львів — місто на заході України ([джерело](https://made-up.example.com/lviv))."
SHOWN = {"read": [{"url": LVIV, "site": "uk.wikipedia.org", "label": "Львів — Вікіпедія"}],
         "found": [{"url": "https://meteo.example.org/lviv", "site": "meteo.example.org", "label": "Погода у Львові"}]}


def _until_done(api, sid):
    for _ in range(300):
        p = api.poll(sid)
        if p.get("done"):
            return p
        time.sleep(0.02)
    raise AssertionError("the answer never ended")


pytest.importorskip("textual")
from textual.widgets import Collapsible, Input, Markdown, Static  # noqa: E402

from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)


@pytest.mark.parametrize("private", [False, True])
def test_an_answer_keeps_the_pages_it_opened(api, monkeypatch, private):  # noqa: F811
    _model(api, monkeypatch, [SEARCH], [READ], [ANSWER], ["Будь ласка!"])
    tid = api.new_thread(private=private)["id"]
    p = _until_done(api, api.send(tid, "Що таке Львів?")["stream"])
    assert p["error"] is None and "made-up.example.com" in p["final"]
    assert p["sources"] == SHOWN                                     # the model's own link is not a source
    assert "made-up" not in json.dumps(p["sources"])
    msgs = api.messages(tid)
    assert msgs[-1]["sources"] == SHOWN and msgs[0]["sources"] == {}
    p = _until_done(api, api.send(tid, "Дякую")["stream"])            # no tools: no sources
    assert p["sources"] == {}
    assert [m["sources"] for m in api.messages(tid)] == [{}, SHOWN, {}, {}]
    if not private:                                                  # kept with the reply in the database
        row = sqlite3.connect(api.store.path).execute("SELECT sources FROM messages WHERE role='assistant' ORDER BY id").fetchall()
        assert json.loads(row[0][0])["read"][0]["url"] == LVIV and row[1][0] == ""


def test_an_older_database_gets_the_column(tmp_path):
    path = tmp_path / "old.db"
    Store(path).add(Store(path).new_thread("x"), "user", "hi")
    db = sqlite3.connect(path)
    try:
        db.execute("ALTER TABLE messages DROP COLUMN sources")
        db.commit()
    except sqlite3.OperationalError:
        pytest.skip("this SQLite can't drop a column")
    finally:
        db.close()
    st = Store(path)
    assert [m["sources"] for m in st.messages(1)] == [""]
    st.add(1, "assistant", "ok", sources='{"read": []}')
    assert st.messages(1)[-1]["sources"] == '{"read": []}'


def test_the_terminal_shows_them_under_the_answer(api, monkeypatch):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "uk", "provider": "groq"})
    _model(api, monkeypatch, [SEARCH], [READ], [ANSWER])

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            scr.query_one("#composer", Input).value = "Що таке Львів?"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: bool(scr.query(".srcs")) and scr._stream is None)
            text = str(scr.query_one(".srcs", Static).render())
            assert text.startswith("Джерела:") and f"• Львів — Вікіпедія\n  {LVIV}" in text and "made-up" not in text
            log = list(scr.query_one("#log").children)
            at = log.index(scr.query_one(".srcs", Static))
            assert isinstance(log[at - 1], Markdown)                 # right under the words
            found, sent = log[at + 1], log[at + 2]
            assert isinstance(found, Collapsible) and found.title == "🔎 Результати пошуку: 1"
            assert isinstance(sent, Collapsible) and "Що пішло в модель" in sent.title
            tid = scr.tid
            scr.open_thread(tid)                                     # opened again: the same lines
            assert await wait_for(pilot, lambda: len(scr.query(".srcs")) == 1)
            assert f"\n  {LVIV}" in str(scr.query_one(".srcs", Static).render())
    asyncio.run(go())
