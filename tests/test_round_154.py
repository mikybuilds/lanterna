"""Round 154 (1.1.11b8): Lanterna's own help.

Asked "how do I install your extension?", Lanterna said it was no browser extension, only a program for Windows
and Ubuntu: the message has "встановити" in it, so the model had to call a tool, it had none about Lanterna and
searched the web, and the web knows only the older versions. Now the model gets lanterna_help whenever the talk is
about Lanterna itself: what it is, where it runs, installing and updating it, the Settings tab by tab, and the
Chrome extension with the steps to add it and its state on this computer. Buttons and settings are named as the
window shows them, in the app's language. Nothing here starts Chrome or calls a model.
"""
import json
import re
from pathlib import Path

from lanterna import chat, i18n, selfhelp, thinking
from lanterna.discovery import Candidate
from lanterna.providers import ToolCall, ToolCalls
from lanterna.router import Router
from lanterna.tools import GROUPS, LOOKUP_TOOLS, READ_ONLY_TOOLS, LookupOnly
from test_tui import api  # noqa: F401  (the fake vault and model)

JS = (Path(selfhelp.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
STR = r'"((?:[^"\\]|\\.)*)"'
QUESTION = "як мені встановити твоє розширення?"          # the user's question, word for word


def _window_word(text: str, lang: str) -> str:
    """The word the window shows: its own table (app.js), or Lanterna's (i18n) when that has none."""
    m = re.search(r"^\s*" + re.escape(json.dumps(text, ensure_ascii=False)) + r"\s*:\s*\{\s*uk:\s*" + STR +
                  r",\s*it:\s*" + STR, JS, re.M)
    if not m:
        return i18n.t(text, lang)
    return json.loads(f'"{m.group(1 if lang == "uk" else 2)}"')


def _quoted() -> set[str]:
    """Every name the help puts in «»."""
    names = {tab for tab, _ in selfhelp.SETTINGS} | {x for _, parts in selfhelp.SETTINGS for x in parts}
    return names | set(selfhelp.STEPS) | set(selfhelp.MODES.values()) | {
        "Settings", "General", "Updates", "Account and sync", "Check for a new version when Lanterna starts",
        "Update now", "Let Lanterna work in Chrome", "Open the extension's folder", "Connect Chrome",
        "How much Lanterna asks first in Chrome"}


# ---------------------------------------------------------------- what the help says
def test_the_help_knows_the_chrome_extension_and_the_steps_to_add_it():
    out = selfhelp.chrome("uk", platform="win32")
    assert "LANTERNA IN CHROME" in out and "Chrome 116 or newer" in out and "isn't in the Chrome Web Store" in out
    for step in selfhelp.STEPS:                                                  # the window's steps, word for word
        assert _window_word(step, "uk") in out
    assert "«Відкрити папку розширення» in «Налаштування» → Chrome" in out
    assert "in the tray is enough" in out and "«Підключити Chrome»" in out
    assert "Never, in any mode: passwords, card details, buying or paying" in out
    assert "\\" not in out and "/home/" not in out                              # no folder of the user's in it


def test_the_help_says_how_it_is_on_this_computer_now():
    assert "isn't connected: it isn't added yet" in selfhelp.chrome("en")
    assert "is connected (Chrome 157): it is added and works" in selfhelp.chrome("en", connected=True,
                                                                                browser="Chrome 157")
    assert "«Let Lanterna work in Chrome» is off" in selfhelp.chrome("en", on=False)
    assert "couldn't open its connection" in selfhelp.chrome("en", listening=False)
    assert "this is Lanterna's terminal app" in selfhelp.chrome("en", window=False)
    assert "«Автоматично» now" in selfhelp.chrome("uk", mode="full")
    assert "«Semi-automatic» now" in selfhelp.chrome("en", mode="odd")          # an unknown mode: the default
    assert "Lanterna's window must be open" in selfhelp.chrome("en", platform="linux")


def test_about_says_where_lanterna_runs_how_to_install_and_update_it():
    out = selfhelp.about("en", window=False, platform="linux", version="1.1.11b8")
    assert "version 1.1.11b8, a test version (beta)" in out and "never offered as an update" in out
    assert "Windows 10 and 11" in out and "macOS isn't tested yet" in out and "no app for phones" in out
    assert "Lanterna-Setup-x.y.z.exe" in out and "https://github.com/mikybuilds/lanterna/releases/latest" in out
    assert "`pipx install git+https://github.com/mikybuilds/lanterna`" in out and "`lanterna desktop`" in out
    assert "«Settings» → «General» → «Updates»" in out and "«Update now»" in out
    assert "This computer: Linux, Lanterna's terminal app." in out
    assert "beta" not in selfhelp.about("en", version="1.1.11")
    assert "«Налаштування», tab by tab: «Загальне» (Мова, Розмір тексту" in selfhelp.about("uk")
    assert selfhelp.is_beta("1.2.0rc1") and not selfhelp.is_beta("1.1.11")
    assert selfhelp.help_text("chrome", "en").startswith("LANTERNA IN CHROME")
    assert selfhelp.help_text("something else", "en").startswith("LANTERNA'S OWN HELP")
    assert len(selfhelp.about("uk")) < 4000 and len(selfhelp.chrome("uk")) < 4000   # Groq's free plan: one result


def test_the_settings_tabs_steps_and_modes_are_the_windows_own():
    block = JS[JS.index("const SET_TABS = ["):JS.index("];", JS.index("const SET_TABS = ["))]
    tabs = tuple((label, tuple(json.loads(f"[{parts}]"))) for _, label, parts in
                 re.findall(r'\["(\w+)", "([^"]+)", \[([^\]]*)\]\]', block))
    assert tabs == selfhelp.SETTINGS
    steps = re.search(r"const steps = \[(.*?)\];", JS, re.S).group(1)
    assert tuple(json.loads(f"[{steps}]")) == selfhelp.STEPS
    modes = re.search(r"const MODES = (\[.*?\]);", JS).group(1)
    assert dict(json.loads(modes)) == selfhelp.MODES


def test_every_name_the_help_quotes_is_the_windows_own_word():
    for text in _quoted():
        for lang in ("uk", "it"):
            assert i18n.t(text, lang) == _window_word(text, lang), (lang, text)
        assert text == "Chrome" or i18n.t(text, "uk") != text, text              # translated
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(text), (lang, text)


# ---------------------------------------------------------------- when the model gets it
def test_words_about_lanterna_itself_bring_the_help():
    about_itself = [QUESTION, "Чи є версія для Mac?", "Як тебе встановити на Ubuntu?", "що ти вмієш?",
                    "how do I install your extension?", "What can you do?", "Come si installa l'estensione?",
                    "Что ты умеешь?", "Wo finde ich die Einstellungen?", "є нова версія?", "Лантерна, привіт",
                    "де в налаштуваннях вимкнути нагадування?", "update you to the beta"]
    other = ["яка погода в Києві?", "розв'яжи рівняння 2x+3=7", "напиши твір про осінь", "скільки буде 15% від 200?",
             "remind me in 20 minutes to stretch", "переклади це на англійську"]
    assert [s for s in about_itself if not GROUPS["self"].search(s)] == []
    assert [s for s in other if GROUPS["self"].search(s)] == []


def test_the_question_gets_the_help_tool_and_it_only_looks(api):  # noqa: F811
    names = lambda text: [s["function"]["name"] for s in api.toolbox.schemas(text)]   # noqa: E731
    assert "lanterna_help" in names(QUESTION) and "lanterna_help" not in names("яка погода в Києві?")
    assert chat.must_use_tool(QUESTION)                         # "встановити": this round must call a tool
    assert "lanterna_help" in LOOKUP_TOOLS and "lanterna_help" in READ_ONLY_TOOLS
    assert "lanterna_help" in [s["function"]["name"] for s in LookupOnly(api.toolbox).schemas()]   # a second opinion
    assert not chat.acting_pc("lanterna_help")
    tool = api.toolbox.tools["lanterna_help"]
    assert tool.label == "❓" and '"❓": "info"' in JS                              # the window's info icon
    assert tool.parameters["properties"]["topic"]["enum"] == ["lanterna", "chrome"]
    assert "never web_search for these" in tool.description
    assert thinking.tool_step("lanterna_help", '{"topic": "chrome"}', "uk") == "Дивлюся довідку Lanterna"


def test_the_help_tells_the_state_of_this_lanterna(api, monkeypatch):  # noqa: F811
    api.settings.lang = "uk"
    assert "terminal app" in api.lanterna_help("chrome")       # the tests (and the terminal app) don't listen
    api._browser_wanted = True                                 # the window app
    assert "couldn't open its connection" in api.lanterna_help("chrome")
    monkeypatch.setattr(api.browser, "server", object())
    assert "isn't connected: it isn't added yet" in api.lanterna_help("chrome")
    monkeypatch.setattr(api.browser, "status", lambda: {"connected": True, "browser": "Chrome 157"})
    assert "is connected (Chrome 157)" in api.lanterna_help("chrome")
    api.settings.browser_on = False
    assert "«Дозволити Lanterna працювати в Chrome» is off" in api.lanterna_help("chrome")
    assert api.lanterna_help("lanterna").startswith("LANTERNA'S OWN HELP")


def test_the_model_is_told_to_ask_the_help_not_the_web():
    plain = chat.system_prompt("Anna")
    assert "with its own extension for Chrome (Settings → Chrome shows how to add it)" in plain
    assert "lanterna_help" not in plain                         # not offered: not named
    assert chat.SELF_NOTE in chat.system_prompt("Anna", helps=True)
    assert "never web_search" in chat.SELF_NOTE


class _Fake:
    """A model from a script; keeps what each request offered."""

    def __init__(self, replies):
        self.replies, self.seen = replies, []

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        self.seen.append({"tools": [t["function"]["name"] for t in tools or []], "choice": tool_choice,
                          "messages": [dict(m) for m in messages]})
        yield from self.replies.pop(0)

    def close(self):
        pass


def test_the_question_from_the_screenshot_is_answered_from_lanternas_own_help(api):  # noqa: F811
    api.settings.lang = "uk"
    fake = _Fake([[ToolCalls([ToolCall("c1", "lanterna_help", '{"topic": "chrome"}')])],
                  ["Відкрий «Налаштування» → Chrome: там 4 кроки і кнопка «Відкрити папку розширення»."]])
    s = chat.Conversation(router=Router([Candidate("gemini", "able", 90)], client_for=lambda pid: fake),
                          lang="uk", toolbox=api.toolbox)
    out = "".join(p for p in s.ask(QUESTION) if isinstance(p, str))
    first, second = fake.seen
    assert first["choice"] == "required" and "lanterna_help" in first["tools"]
    assert chat.SELF_NOTE in first["messages"][0]["content"]
    told = second["messages"][-1]
    assert told["role"] == "tool" and "LANTERNA IN CHROME" in told["content"]
    assert "Натисни «Завантажити розпаковане розширення»" in told["content"]
    assert out.startswith("Відкрий «Налаштування» → Chrome") and "⚠️" not in out
