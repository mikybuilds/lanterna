"""Full-screen terminal app (Textual): first-run setup, chats, settings. Works with mouse and keyboard.

Uses the same backend as the window app (app.Api), so chats are shared between both.
"""
from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (Button, DataTable, Footer, Input, Label, ListItem, ListView, LoadingIndicator,
                             Markdown, Static)

from . import AUTHOR, __version__
from .app import Api
from .cli import FIRST_CHOICES
from .i18n import LANGS, t
from .providers import PROVIDERS

AMBER = "#F5B544"
THEME = Theme(name="lanterna", primary=AMBER, secondary="#7C8BB5", accent=AMBER, warning="#F0A030",
              error="#E5675C", success="#6CC28A", background="#0B0E17", surface="#121726", panel="#1A2034",
              foreground="#E6E8EF", dark=True)
LOGO = "🏮"

CSS = """
Screen { background: $background; }
.title { text-style: bold; color: $primary; content-align: center middle; width: 100%; margin: 1 0 0 0; }
.sub { color: $text-muted; content-align: center middle; width: 100%; margin: 0 0 1 0; }
.muted { color: $text-muted; }
.ok { color: $success; }
.bad { color: $error; }
.center-col { width: 76; max-width: 100%; height: auto; }
.row { height: auto; width: 100%; align-horizontal: center; }
.row Button { margin: 0 1; }
#onboard { align: center middle; }
.card { border: round $panel-lighten-2; padding: 0 2; margin: 0 1; width: 1fr; height: auto; }
.card.first { border: round $primary; }
.card .cardname { text-style: bold; width: 100%; }
.card Button { width: 100%; margin: 1 0 0 0; }
#sidebar { width: 30; background: $surface; border-right: solid $panel; padding: 0 1; }
#brand { text-style: bold; color: $primary; height: 1; margin: 1 0; }
#newchat { width: 100%; margin-bottom: 1; }
#threads { background: $surface; height: 1fr; }
#threads > ListItem { background: $surface; padding: 0 1; }
#threads > ListItem.-highlight { background: $panel; }
#main { width: 1fr; }
#topbar { height: 1; padding: 0 2; background: $surface; }
#chattitle { width: 1fr; text-style: bold; }
#model { color: $text-muted; width: auto; }
#log { padding: 1 2; height: 1fr; }
.msg-user { background: $panel; border-left: thick $primary; padding: 0 1; margin: 1 0 0 0; width: 1fr; }
.msg-bot { margin: 1 8 0 0; padding: 0; }
.msg-note { color: $text-muted; text-style: italic; margin: 1 0 0 0; }
.msg-err { color: $error; margin: 1 0 0 0; }
.welcome { color: $text-muted; margin: 2 0; content-align: center middle; width: 100%; }
#composer { margin: 0 2 1 2; border: round $panel-lighten-2; }
#composer:focus { border: round $primary; }
ModalScreen { align: center middle; background: $background 70%; }
.dialog { width: 80; max-width: 100%; height: auto; max-height: 90%; border: round $primary; background: $surface; padding: 1 2; }
.dialog .h { text-style: bold; color: $primary; margin: 1 0 0 0; }
.keyrow { height: auto; width: 100%; }
.keyrow Label { width: 1fr; padding: 1 0 0 0; }
.keyrow Input { width: 1fr; }
#keys { height: auto; }
Button:focus { text-style: bold; }
.dialog > .h:first-child { margin-top: 0; }
.keyrow Button { min-width: 10; margin-left: 1; }
#models-table { height: 18; }
"""


def L(app) -> str:
    return app.api.settings.lang


# ---------------------------------------------------------------------------------------------- dialogs
class KeyScreen(ModalScreen[bool]):
    """Asks for a provider key, checks it with the provider and stores it in the system vault."""

    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, provider: str):
        super().__init__()
        self.pid = provider

    def compose(self) -> ComposeResult:
        lang, p = L(self.app), PROVIDERS[self.pid]
        with Vertical(classes="dialog"):
            yield Label(t("Key for {p}", lang, p=p.name), classes="h")
            yield Static(f"[link='{p.key_url}']{p.key_url}[/link]")
            yield Static("\n".join([t("1. Sign in or create a free account.", lang),
                                    t("2. Create an API key and copy it.", lang),
                                    t("3. Paste it here.", lang)]), classes="muted")
            yield Input(placeholder=t("Paste the key here", lang), password=True, id="key")
            yield Label("", id="keystatus")
            yield Static(t("Your key stays on this computer, in the system's secure vault.", lang), classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Open the site", lang), id="open")
                yield Button(t("Check the key", lang), id="check", variant="primary")
                yield Button(t("Cancel", lang), id="cancel")

    def on_mount(self) -> None:
        self.query_one("#key", Input).focus()

    @on(Button.Pressed, "#open")
    def _open(self) -> None:
        self.app.api.open_url(PROVIDERS[self.pid].key_url)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#check")
    @on(Input.Submitted, "#key")
    def _check(self) -> None:
        key = self.query_one("#key", Input).value.strip()
        status = self.query_one("#keystatus", Label)
        if not key:
            status.update(t("Paste a key first.", L(self.app)))
            return
        status.set_classes("muted")
        status.update(t("Checking the key…", L(self.app)))
        self.query_one("#check", Button).disabled = True
        self._run_check(key)

    @work(thread=True, exclusive=True)
    def _run_check(self, key: str) -> None:
        res = self.app.api.check_key(self.pid, key)
        self.app.call_from_thread(self._checked, res)

    def _checked(self, res: dict) -> None:
        lang = L(self.app)
        status = self.query_one("#keystatus", Label)
        self.query_one("#check", Button).disabled = False
        if res.get("ok"):
            status.set_classes("ok")
            status.update(t("Key works ✓", lang))
            self.set_timer(0.6, self._close_ok)
        else:
            status.set_classes("bad")
            status.update(t("The key didn't work: {err}", lang, err=res.get("message") or res.get("error")))


    def _close_ok(self) -> None:
        self.dismiss(True)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "no", show=False)]

    def __init__(self, question: str, yes: str):
        super().__init__()
        self.question, self.yes = question, yes

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.question, classes="h")
            with Horizontal(classes="row"):
                yield Button(self.yes, id="yes", variant="error")
                yield Button(t("Cancel", L(self.app)), id="no")

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss(False)


class ModelsScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog"):
            yield Label(t("Free models right now", lang), classes="h")
            yield LoadingIndicator(id="loading")
            yield DataTable(id="models-table", cursor_type="row", zebra_stripes=True)
            yield Label("", id="modelsmsg", classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Search again", lang), id="refresh")
                yield Button(t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        lang = L(self.app)
        tb = self.query_one(DataTable)
        tb.add_columns(t("Service", lang), t("Model", lang), t("Score", lang), t("Status", lang))
        self._load(False)

    @on(Button.Pressed, "#refresh")
    def _refresh(self) -> None:
        self._load(True)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)

    def _load(self, refresh: bool) -> None:
        self.query_one("#loading").display = True
        self.query_one("#modelsmsg", Label).update(t("Looking for free models…", L(self.app)))
        self._fetch(refresh)

    @work(thread=True, exclusive=True)
    def _fetch(self, refresh: bool) -> None:
        res = self.app.api.models(refresh)
        self.app.call_from_thread(self._show, res)

    def _show(self, res: dict) -> None:
        lang = L(self.app)
        self.query_one("#loading").display = False
        tb = self.query_one(DataTable)
        tb.clear()
        msg = self.query_one("#modelsmsg", Label)
        if not res.get("ok"):
            msg.update(t("No working key. Add one in Settings (Ctrl+S).", lang))
            return
        for m in res["models"]:
            st = t(m["status"], lang) + (f" · {m['latency']:.1f}s" if m.get("latency") else "")
            tb.add_row(m["provider"], m["model"] + (" 👁" if m["vision"] else ""), str(m["score"]), st)
        msg.update(t("Now using: {m}", lang, m=res.get("current") or "—"))


class AboutScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang, api = L(self.app), self.app.api
        home = api.state()["homepage"]
        with Vertical(classes="dialog"):
            yield Label(f"{LOGO} Lanterna  v{__version__}", classes="title")
            yield Label(t("Made by {author}", lang, author=AUTHOR), classes="sub")
            yield Static(t("Lanterna is free and open source.", lang) + f"\n[link='{home}']{home}[/link]", classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Star on GitHub", lang), id="star", variant="primary")
                yield Button(t("Close", lang), id="close")

    @on(Button.Pressed, "#star")
    def _star(self) -> None:
        self.app.api.open_url(self.app.api.state()["homepage"])

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[str]):
    """Returns "lang" when the language changed (the app then rebuilds its screens)."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with VerticalScroll(classes="dialog"):
            yield Label(t("Language", lang), classes="h")
            with Horizontal(classes="row"):
                for code, name in LANGS.items():
                    yield Button(name, id=f"lang-{code}", variant="primary" if code == lang else "default")
            yield Label(t("Name", lang), classes="h")
            with Horizontal(classes="keyrow"):
                yield Input(self.app.api.settings.name, id="name")
                yield Button(t("Save", lang), id="savename")
            yield Label(t("Keys", lang), classes="h")
            yield Vertical(id="keys")
            yield Label(t("Models", lang), classes="h")
            yield Button(t("Show models", lang), id="models")
            with Horizontal(classes="row"):
                yield Button(t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self._fill_keys()

    def _fill_keys(self) -> None:
        lang = L(self.app)
        box = self.query_one("#keys", Vertical)
        box.remove_children()
        for p in self.app.api.state()["providers"]:
            if p["local"]:
                continue
            row = Horizontal(classes="keyrow")
            box.mount(row)
            row.mount(Label(f"{p['name']:16} {p['masked'] if p['has_key'] else t('not set', lang)}"))
            row.mount(Button(t("Change", lang) if p["has_key"] else t("Add", lang), id=f"set-{p['id']}"))
            if p["has_key"]:
                row.mount(Button(t("Remove", lang), id=f"del-{p['id']}", variant="error"))

    @on(Button.Pressed)
    def _pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid.startswith("lang-"):
            self.app.api.save_settings({"lang": bid[5:]})
            self.dismiss("lang")
        elif bid == "savename":
            self.app.api.save_settings({"name": self.query_one("#name", Input).value})
            self.app.notify(t("Saved.", L(self.app)))
        elif bid.startswith("set-"):
            self.app.push_screen(KeyScreen(bid[4:]), lambda _ok: self._fill_keys())
        elif bid.startswith("del-"):
            self.app.api.delete_key(bid[4:])
            self._fill_keys()
        elif bid == "models":
            self.app.push_screen(ModelsScreen())
        elif bid == "close":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss("")


# ---------------------------------------------------------------------------------------------- onboarding
class OnboardScreen(Screen):
    step = reactive(0, recompose=True)

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Center(id="onboard"):
            with Vertical(classes="center-col"):
                yield Label(f"{LOGO}  Lanterna", classes="title")
                if self.step == 0:
                    yield Label("Choose your language · Вибери мову · Scegli la lingua", classes="sub")
                    with Horizontal(classes="row"):
                        for code, name in LANGS.items():
                            yield Button(name, id=f"lang-{code}", variant="primary" if code == lang else "default")
                elif self.step == 1:
                    yield Label(t("Welcome to Lanterna", lang), classes="sub")
                    yield Static(t("A friendly assistant on free AI models.", lang) + "\n"
                                 + t("Lanterna is free and open source.", lang) + " "
                                 + t("Made by {author}", lang, author=AUTHOR), classes="muted")
                    yield Label(t("What should I call you?", lang), classes="h")
                    yield Input(self.app.api.settings.name, placeholder=t("Your name", lang), id="name")
                    with Horizontal(classes="row"):
                        yield Button(t("Back", lang), id="back")
                        yield Button(t("Next", lang), id="next", variant="primary")
                else:
                    yield Label(t("Pick your first free service:", lang), classes="sub")
                    with Horizontal(classes="row"):
                        for i, (pid, tag, det) in enumerate(FIRST_CHOICES):
                            with Vertical(classes="card first" if i == 0 else "card"):
                                yield Static(f"{PROVIDERS[pid].name} — {t(tag, lang)}", classes="cardname", markup=False)
                                yield Static("\n".join("• " + x for x in t(det, lang).split(" · ")), classes="muted")
                                yield Button(t("Choose", lang), id=f"pick-{pid}", variant="primary" if i == 0 else "default")
                    yield Static(t("You can add the other services later as backups.", lang), classes="sub")
                    with Horizontal(classes="row"):
                        yield Button(t("Back", lang), id="back")

    def on_mount(self) -> None:
        self._focus()

    def watch_step(self) -> None:
        self.call_after_refresh(self._focus)

    def _focus(self) -> None:
        for sel in ("#name", "Button.-primary", "Button"):
            found = self.query(sel)
            if found:
                found.first().focus()
                return

    @on(Input.Submitted, "#name")
    def _name_done(self) -> None:
        self._next()

    @on(Button.Pressed)
    def _pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid.startswith("lang-"):
            self.app.api.save_settings({"lang": bid[5:]})
            self.step = 1
        elif bid == "next":
            self._next()
        elif bid == "back":
            self.step = max(0, self.step - 1)
        elif bid.startswith("pick-"):
            pid = bid[5:]
            self.app.api.save_settings({"provider": pid, "mode": "cloud"})
            if self.app.api.state()["providers"] and any(p["id"] == pid and p["has_key"] for p in self.app.api.state()["providers"]):
                self._finish(True)
            else:
                self.app.push_screen(KeyScreen(pid), self._finish)

    def _next(self) -> None:
        self.app.api.save_settings({"name": self.query_one("#name", Input).value})
        self.step = 2

    def _finish(self, ok: bool) -> None:
        if ok:
            self.app.api.save_settings({"onboarded": True})
            self.app.switch_screen(make_chat_screen(L(self.app)))


# ---------------------------------------------------------------------------------------------- chat
class _ChatScreen(Screen):
    def __init__(self):
        super().__init__()
        self.tid: int | None = None
        self._stream: str | None = None
        self._offset = 0
        self._text = ""
        self._bot: Markdown | None = None
        self._timer = None
        self._notes_seen = 0

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(f"{LOGO} Lanterna", id="brand")
                yield Button("+ " + t("New chat", lang), id="newchat", variant="primary")
                yield ListView(id="threads")
            with Vertical(id="main"):
                with Horizontal(id="topbar"):
                    yield Label(t("New chat", lang), id="chattitle")
                    yield Label("", id="model")
                yield VerticalScroll(id="log")
                yield Input(placeholder=t("Message Lanterna…", lang), id="composer")
        yield Footer()

    def on_mount(self) -> None:
        threads = self.app.api.threads()
        self._fill_threads(threads)
        if threads:
            self.open_thread(threads[0]["id"])
        else:
            self._welcome()
        self.query_one("#composer", Input).focus()
        self._load_model_label()

    @work(thread=True, exclusive=True, group="model")
    def _load_model_label(self) -> None:
        res = self.app.api.models(False)
        self.app.call_from_thread(self._set_model, res.get("current") or "")

    def _set_model(self, label: str) -> None:
        self.query_one("#model", Label).update(label)

    # threads -----------------------------------------------------------------
    def _fill_threads(self, threads: list[dict] | None = None) -> None:
        lv = self.query_one("#threads", ListView)
        lv.clear()
        threads = self.app.api.threads() if threads is None else threads
        for i, th in enumerate(threads):
            lv.append(ListItem(Label(th["title"] or t("New chat", L(self.app)), markup=False), name=str(th["id"])))
            if th["id"] == self.tid:
                lv.index = i

    @on(ListView.Selected, "#threads")
    def _picked(self, ev: ListView.Selected) -> None:
        if ev.item.name and not self._stream:
            self.open_thread(int(ev.item.name))
            self.query_one("#composer", Input).focus()

    def open_thread(self, tid: int) -> None:
        self.tid = tid
        log = self.query_one("#log", VerticalScroll)
        log.remove_children()
        th = next((x for x in self.app.api.threads() if x["id"] == tid), None)
        self.query_one("#chattitle", Label).update((th or {}).get("title") or t("New chat", L(self.app)))
        msgs = self.app.api.messages(tid)
        if not msgs:
            self._welcome()
        for m in msgs:
            if m["role"] == "user":
                log.mount(Static(m["content"], classes="msg-user", markup=False))
            else:
                log.mount(Markdown(m["content"], classes="msg-bot"))
        log.scroll_end(animate=False)

    def _welcome(self) -> None:
        lang, name = L(self.app), self.app.api.settings.name
        text = t("Hi, {name}! Ask me anything.", lang, name=name) if name else t("Hi! Ask me anything.", lang)
        self.query_one("#log", VerticalScroll).mount(Static(text, classes="welcome", markup=False))

    def action_new_chat(self) -> None:
        if self._stream:
            return
        self.tid = None
        self.query_one("#log", VerticalScroll).remove_children()
        self.query_one("#chattitle", Label).update(t("New chat", L(self.app)))
        self.query_one("#threads", ListView).index = None
        self._welcome()
        self.query_one("#composer", Input).focus()

    @on(Button.Pressed, "#newchat")
    def _new_btn(self) -> None:
        self.action_new_chat()

    def action_delete_chat(self) -> None:
        if self.tid is None or self._stream:
            return
        lang = L(self.app)

        def done(yes: bool) -> None:
            if yes:
                self.app.api.delete_thread(self.tid)
                self.tid = None
                self._fill_threads()
                self.action_new_chat()

        self.app.push_screen(ConfirmScreen(t("Delete this chat?", lang), t("Delete", lang)), done)

    # sending -----------------------------------------------------------------
    @on(Input.Submitted, "#composer")
    def _submit(self, ev: Input.Submitted) -> None:
        text = ev.value.strip()
        if not text:
            return
        if self._stream:
            self.app.notify(t("Wait for the reply to finish.", L(self.app)))
            return
        ev.input.value = ""
        log = self.query_one("#log", VerticalScroll)
        if self.tid is None:
            self.tid = self.app.api.new_thread()["id"]
            log.remove_children()
        log.query(".welcome").remove()
        log.mount(Static(text, classes="msg-user", markup=False))
        res = self.app.api.send(self.tid, text)
        if not res.get("ok"):
            log.mount(Static(t("Error: {err}", L(self.app), err=res.get("error")), classes="msg-err", markup=False))
            return
        self._stream, self._offset, self._text, self._notes_seen = res["stream"], 0, "", 0
        self._bot = Markdown("_" + t("Thinking…", L(self.app)) + "_", classes="msg-bot")
        log.mount(self._bot)
        log.scroll_end(animate=False)
        self._fill_threads()
        self._timer = self.set_interval(0.12, self._poll)

    async def _poll(self) -> None:
        if not self._stream:
            return
        r = self.app.api.poll(self._stream, self._offset)
        log = self.query_one("#log", VerticalScroll)
        lang = L(self.app)
        for note in r.get("notes", [])[self._notes_seen:]:
            await log.mount(Static("↪ " + t("switched to {m}", lang, m=note), classes="msg-note", markup=False), before=self._bot)
        self._notes_seen = len(r.get("notes", []))
        changed = False
        if "final" in r:
            self._text, changed = r["final"], True
            if r.get("model"):
                self._set_model(r["model"])
        elif r.get("text"):
            self._text += r["text"]
            self._offset = r["offset"]
            changed = True
        if changed and self._bot is not None:
            await self._bot.update(self._text)
            log.scroll_end(animate=False)
        if r.get("done"):
            self._stream = None
            err = r.get("error")
            if err:
                await log.mount(Static(self._error_text(err), classes="msg-err", markup=False))
                if not self._text and self._bot is not None:
                    self._bot.remove()
                log.scroll_end(animate=False)
            self._fill_threads()
            th = next((x for x in self.app.api.threads() if x["id"] == self.tid), None)
            if th:
                self.query_one("#chattitle", Label).update(th["title"])
            self._timer.stop()      # last: stopping cancels this very callback at its next await

    def _error_text(self, err: dict) -> str:
        lang, kind = L(self.app), err.get("kind")
        if kind == "rate":
            return t("All free models are busy or out of limits. Try again in a minute.", lang)
        if kind == "auth":
            return t("No working key. Add one in Settings (Ctrl+S).", lang)
        if kind == "network":
            return t("Network problem: {err}", lang, err=err.get("message", ""))
        return t("Error: {err}", lang, err=err.get("message", ""))

    # dialogs -----------------------------------------------------------------
    def action_settings(self) -> None:
        def done(res: str) -> None:
            if res == "lang":
                self.app.switch_screen(make_chat_screen(L(self.app)))
            else:
                self._load_model_label()

        self.app.push_screen(SettingsScreen(), done)

    def action_models(self) -> None:
        self.app.push_screen(ModelsScreen(), lambda _r: self._load_model_label())

    def action_about(self) -> None:
        self.app.push_screen(AboutScreen())


def make_chat_screen(lang: str) -> Screen:
    """Builds the chat screen with footer key hints in the chosen language."""
    bindings = [
        Binding("ctrl+n", "new_chat", t("New chat", lang), priority=True),
        Binding("ctrl+d", "delete_chat", t("Delete chat", lang), priority=True),
        Binding("ctrl+s", "settings", t("Settings", lang), priority=True),
        Binding("ctrl+o", "models", t("Models", lang), priority=True),
        Binding("f1", "about", t("About", lang), priority=True),
        Binding("ctrl+q", "app.quit", t("Quit", lang), priority=True),
    ]
    return type("ChatScreen", (_ChatScreen,), {"BINDINGS": bindings})()


# ---------------------------------------------------------------------------------------------- app
class LanternaApp(App):
    CSS = CSS
    TITLE = "Lanterna"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, api: Api | None = None, force_setup: bool = False):
        super().__init__()
        self.api = api or Api()
        self.force_setup = force_setup

    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = "lanterna"
        if self.force_setup or not self.api.settings.onboarded:
            self.push_screen(OnboardScreen())
        else:
            self.push_screen(make_chat_screen(L(self)))


def run(force_setup: bool = False) -> int:
    LanternaApp(force_setup=force_setup).run()
    return 0
