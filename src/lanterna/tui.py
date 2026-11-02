"""Full-screen terminal app (Textual): first-run setup, chats, settings. Works with mouse and keyboard.

Uses the same backend as the window app (app.Api), so chats are shared between both.
"""
from __future__ import annotations

import asyncio

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (Button, Checkbox, DataTable, Footer, Input, Label, ListItem, ListView, LoadingIndicator,
                             Markdown, ProgressBar, Select, Static)

from pathlib import Path

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
#model { color: $text-muted; width: auto; padding-left: 2; }
#log { padding: 1 2; height: 1fr; }
.msg-user { background: $panel; border-left: thick $primary; padding: 0 1; margin: 1 0 0 0; width: 1fr; }
.msg-bot { margin: 1 8 0 0; padding: 0; }
.msg-note { color: $text-muted; text-style: italic; margin: 1 0 0 0; }
.msg-err { color: $error; margin: 1 0 0 0; }
.welcome { color: $text-muted; margin: 2 0; content-align: center middle; width: 100%; }
#composer { margin: 0 2 1 2; border: round $panel-lighten-2; }
#attached { margin: 0 3; color: $primary; height: auto; }
.msg-tool { color: $text-muted; margin: 1 0 0 0; }
.listrow { height: auto; width: 100%; }
.listrow Label { width: 1fr; padding: 1 0 0 0; }
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
.lrow { height: auto; width: 100%; margin: 1 0 0 0; }
.lrow .lname { width: 1fr; }
.lrow ProgressBar { width: 30; padding: 1 1 0 0; }
.lrow Button { min-width: 22; }
#ollama-btns { height: auto; }
#picks { height: auto; }
#lmodels { height: auto; }
.modes { height: auto; width: 100%; }
.modes Button { margin: 0 1 0 0; }
"""


TOOL_TEXT = {"weather": "Checking the weather", "web_search": "Searching the web", "read_page": "Reading a page",
             "calculate": "Calculating", "date_calc": "Counting dates", "remember": "Saving to memory",
             "forget": "Updating memory", "set_reminder": "Setting a reminder", "list_reminders": "Checking reminders",
             "cancel_reminder": "Cancelling a reminder"}


def tool_text(chip: str, lang: str) -> str:
    emo, _, name = chip.partition(" ")
    return f"{emo} {t(TOOL_TEXT.get(name, name), lang)}"


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


class FileScreen(ModalScreen[str]):
    """Asks for the path of a file or photo to attach."""

    BINDINGS = [Binding("escape", "cancel", show=False)]

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog"):
            yield Label(t("Attach a file or photo", lang), classes="h")
            yield Static(t("Type or paste the path. Photos, PDF, Word, text and code files work.", lang), classes="muted")
            yield Input(placeholder="~/Pictures/photo.jpg", id="path")
            yield Label("", id="pathmsg", classes="bad")
            with Horizontal(classes="row"):
                yield Button(t("Attach", lang), id="ok", variant="primary")
                yield Button(t("Cancel", lang), id="cancel")

    def on_mount(self) -> None:
        self.query_one("#path", Input).focus()

    @on(Button.Pressed, "#ok")
    @on(Input.Submitted, "#path")
    def _ok(self) -> None:
        from pathlib import Path
        raw = self.query_one("#path", Input).value.strip().strip('"').strip("'")
        if raw and Path(raw).expanduser().is_file():
            self.dismiss(str(Path(raw).expanduser()))
        else:
            self.query_one("#pathmsg", Label).update(t("File not found.", L(self.app)))

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss("")


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


ROLE_TEXT = {"chat": "For chatting", "think": "For harder questions", "vision": "For photos"}
TIER_TEXT = {
    "none": "This computer is better with cloud models. Small local models will be slow.",
    "small": "Small local models will work. Hard questions are better in the cloud.",
    "medium": "Good for local models of about 8B. Auto mode fits best.",
    "large": "Strong card: bigger local models fit.",
    "huge": "Very strong card: the biggest open models fit.",
}
_ACTIVE = ("starting", "downloading", "verifying")


def _gb(x: float, lang: str) -> str:
    return f"{x:.1f} {t('GB', lang)}"


class LocalScreen(ModalScreen[str]):
    """Hardware, Ollama status, recommended models with Download buttons and progress, model picks.

    Returns "cloud" when the user picks the cloud instead (onboarding), otherwise "".
    Downloads start only when the user presses a Download button.
    """

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, onboarding: bool = False):
        super().__init__()
        self._onboarding = onboarding
        self._names: list[str] = []
        self._installed: set[str] = set()
        self._disk = 0.0
        self._running = False
        self._ticker = None

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with VerticalScroll(classes="dialog", id="localdlg"):
            yield Label(t("Local models", lang), classes="h")
            yield LoadingIndicator(id="loading")
            yield Static("", id="hwinfo", markup=False)
            yield Static("", id="ollama")
            with Horizontal(classes="row", id="ollama-btns"):
                yield Button(t("Download Ollama", lang), id="get-ollama", variant="primary")
                yield Button(t("Check again", lang), id="recheck")
            yield Label(t("Recommended for this computer", lang), classes="h")
            yield Vertical(id="lmodels")
            yield Static(t("Downloads start only when you press the button. Models are stored by Ollama on this computer.", lang),
                         classes="muted")
            yield Vertical(id="picks")
            with Horizontal(classes="row"):
                if self._onboarding:
                    yield Button(t("Use the cloud instead", lang), id="to-cloud")
                yield Button(t("Continue", lang) if self._onboarding else t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#ollama-btns").display = False
        self._load()

    @work(thread=True, exclusive=True, group="local")
    def _load(self) -> None:
        hw, st = self.app.api.hardware(), self.app.api.local_status()
        self.app.call_from_thread(self._show, hw, st)

    async def _show(self, hw: dict, st: dict) -> None:
        lang = L(self.app)
        H, A = hw["hw"], hw["advice"]
        self.query_one("#loading").display = False
        gpu = H["gpu"] or t("No graphics card found", lang)
        if H["vram_gb"]:
            gpu += f" · {_gb(H['vram_gb'], lang)}" + ("" if H["vram_exact"] else "?")
        self.query_one("#hwinfo", Static).update(
            f"{t('Graphics card', lang)}: {gpu}\n{t('RAM', lang)}: {_gb(H['ram_gb'], lang)}   "
            f"{t('Free disk', lang)}: {_gb(H['disk_free_gb'], lang)}\n\n{t(TIER_TEXT[A['tier']], lang)}")
        self._running, self._disk = st["running"], H["disk_free_gb"]
        self._download_page = st["download_page"]
        self.query_one("#ollama", Static).update(
            f"[green]✓ {t('Ollama {v} is running', lang, v=st['version'])}[/]" if st["running"]
            else t("Local models need Ollama, a free app. Install it, start it, then press Check again.", lang))
        self.query_one("#ollama-btns").display = not st["running"]
        self._installed = {m["name"] for m in st["models"]}
        box = self.query_one("#lmodels", Vertical)
        await box.remove_children()
        self._names = [m["name"] for m in A["models"]]
        for i, m in enumerate(A["models"]):
            row = Horizontal(classes="lrow", id=f"lrow-{i}")
            await box.mount(row)
            await row.mount(Label(f"{m['name']}\n[dim]{t(ROLE_TEXT[m['role']], lang)} · {_gb(m['size_gb'], lang)}[/]",
                                  classes="lname"))
            await row.mount(ProgressBar(total=100, show_eta=False, id=f"bar-{i}"))
            await row.mount(Button("", id=f"pull-{i}"))
            row.query_one(ProgressBar).display = False
            row.styles.height = "auto"
            setattr(row, "size_gb", m["size_gb"])
        await self._paint_picks(st)
        self._paint(st["pulls"])

    async def _paint_picks(self, st: dict) -> None:
        lang = L(self.app)
        box = self.query_one("#picks", Vertical)
        await box.remove_children()
        if self._onboarding or not st["running"] or not st["models"]:
            return
        picks, widgets = st["picks"], []
        for role, title, models in (("chat", "Chat model", st["models"]),
                                    ("vision", "Photo model", [m for m in st["models"] if m["vision"]])):
            names = [m["name"] for m in models]
            widgets += [Label(t(title, lang), classes="h"),
                        Select([(n, n) for n in names], prompt=t("Automatic", lang), id=f"pick-{role}",
                               value=picks.get(role) if picks.get(role) in names else Select.NULL)]
        await box.mount_all(widgets)                       # one step: no half-built screen if it closes early

    @on(Select.Changed)
    def _picked(self, ev: Select.Changed) -> None:
        role = (ev.select.id or "").removeprefix("pick-")
        value = "" if ev.value in (Select.NULL, Select.BLANK) else str(ev.value)
        if role in ("chat", "vision") and value != self.app.api.settings.local_models.get(role, ""):
            self.app.api.set_local_model(role, value)

    def _paint(self, pulls: list[dict]) -> None:
        lang = L(self.app)
        by = {p["name"]: p for p in pulls}
        active = False
        for i, name in enumerate(self._names):
            p = by.get(name)
            bar, btn = self.query_one(f"#bar-{i}", ProgressBar), self.query_one(f"#pull-{i}", Button)
            row = self.query_one(f"#lrow-{i}")
            if p and p["status"] == "done":
                self._installed.add(name)
            if name in self._installed:
                bar.display = False
                btn.label, btn.disabled, btn.variant = "✓ " + t("Installed", lang), True, "success"
            elif p and p["status"] in _ACTIVE:
                active = True
                bar.display = True
                bar.update(progress=p["percent"])
                btn.label, btn.disabled, btn.variant = t("Cancel", lang), False, "default"
            else:
                bar.display = False
                size = getattr(row, "size_gb", 0)
                no_disk = bool(self._disk) and self._disk < size + 1
                btn.label = t("Not enough disk space", lang) if no_disk else t("Download ({s})", lang, s=_gb(size, lang))
                btn.disabled, btn.variant = (not self._running or no_disk), "primary"
                if p and p["status"] == "error":
                    self.app.notify(t("Download failed: {e}", lang, e=p["error"]), severity="error")
        if active and self._ticker is None:
            self._ticker = self.set_interval(0.7, self._tick)
        elif not active and self._ticker is not None:
            self._ticker.stop()
            self._ticker = None

    def _tick(self) -> None:
        self._paint(self.app.api.pulls())

    @on(Button.Pressed)
    def _pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid.startswith("pull-"):
            name = self._names[int(bid[5:])]
            active = any(p["name"] == name and p["status"] in _ACTIVE for p in self.app.api.pulls())
            if active:
                self._paint(self.app.api.cancel_pull(name))
            else:
                res = self.app.api.pull_model(name)
                if not res.get("ok"):
                    self.app.notify(t("Ollama isn't running. Start it, or switch to Cloud in Settings.", L(self.app)),
                                    severity="error")
                self._paint(self.app.api.pulls())
        elif bid == "get-ollama":
            self.app.api.open_url(self._download_page)
        elif bid == "recheck":
            self.query_one("#loading").display = True
            self._load()
        elif bid == "to-cloud":
            self.dismiss("cloud")
        elif bid == "close":
            self.action_close()

    def action_close(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
        self.dismiss("")


class AboutScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang, api = L(self.app), self.app.api
        home = api.state()["homepage"]
        with Vertical(classes="dialog"):
            yield Label(f"{LOGO} Lanterna  v{__version__}", classes="title")
            yield Label(t("Made by {author}", lang, author=AUTHOR), classes="sub")
            yield Static(t("Lanterna is free and open source.", lang) + f"\n[link='{home}']{home}[/link]", classes="muted")
            yield Static(t("Checking for updates…", lang), id="update", classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Star on GitHub", lang), id="star", variant="primary")
                yield Button(t("Close", lang), id="close")

    def on_mount(self) -> None:
        self._check_update()

    @work(thread=True, exclusive=True, group="update")
    def _check_update(self) -> None:
        res = self.app.api.check_update()
        self.app.call_from_thread(self._show_update, res)

    def _show_update(self, res: dict) -> None:
        lang = L(self.app)
        box = self.query_one("#update", Static)
        if not res.get("latest"):                          # offline or no release yet: stay quiet
            box.update("")
        elif res.get("newer"):
            box.update(f"[b]{t('Version {v} is available', lang, v=res['latest'])}[/b]  "
                       f"[link='{res['url']}']{res['url']}[/link]")
        else:
            box.update("✓ " + t("You have the latest version", lang))

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
            mode = self.app.api.settings.mode
            yield Label(t("Mode", lang), classes="h")
            with Horizontal(classes="modes"):
                for m, name in (("cloud", "Cloud"), ("local", "Local"), ("auto", "Auto")):
                    yield Button(t(name, lang), id=f"mode-{m}", variant="primary" if m == mode else "default")
            if mode == "auto":
                yield Checkbox(t("Send hard questions to the cloud", lang), self.app.api.settings.auto_cloud, id="autocloud")
                yield Static(t("Long questions, proofs, code and analysis go to a bigger online model. Private chats: turn it off.", lang),
                             classes="muted")
            if mode != "cloud":
                yield Button(t("Local models", lang), id="localmodels")
            yield Label(t("Keys", lang), classes="h")
            yield Vertical(id="keys")
            yield Label(t("Memory", lang), classes="h")
            yield Vertical(id="facts")
            with Horizontal(classes="keyrow"):
                yield Input(placeholder=t("Add a fact", lang), id="newfact")
                yield Button(t("Add", lang), id="addfact")
            yield Label(t("Reminders", lang), classes="h")
            yield Vertical(id="rems")
            yield Label(t("Models", lang), classes="h")
            yield Button(t("Show models", lang), id="models")
            with Horizontal(classes="row"):
                yield Button(t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self._fill_keys()
        self._fill_memory()

    def _fill_memory(self) -> None:
        lang, api = L(self.app), self.app.api
        facts, rems = self.query_one("#facts", Vertical), self.query_one("#rems", Vertical)
        facts.remove_children()
        rems.remove_children()
        for f in api.facts():
            row = Horizontal(classes="listrow")
            facts.mount(row)
            row.mount(Label(f["text"], markup=False))
            row.mount(Button(t("Remove", lang), id=f"fact-{f['id']}"))
        if not api.facts():
            facts.mount(Static(t("Nothing yet. Say “remember that…” in a chat.", lang), classes="muted"))
        for r in api.reminders():
            row = Horizontal(classes="listrow")
            rems.mount(row)
            row.mount(Label(f"{r['when']}  {r['text']}", markup=False))
            row.mount(Button(t("Cancel", lang), id=f"rem-{r['id']}"))
        if not api.reminders():
            rems.mount(Static(t("No reminders. Say “remind me in 20 minutes…” in a chat.", lang), classes="muted"))

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
        elif bid.startswith("fact-"):
            self.app.api.delete_fact(int(bid[5:]))
            self._fill_memory()
        elif bid == "addfact":
            box = self.query_one("#newfact", Input)
            if box.value.strip():
                self.app.api.add_fact(box.value)
                box.value = ""
                self._fill_memory()
        elif bid.startswith("rem-"):
            self.app.api.cancel_reminder(int(bid[4:]))
            self._fill_memory()
        elif bid == "models":
            self.app.push_screen(ModelsScreen())
        elif bid.startswith("mode-"):
            self.app.api.save_settings({"mode": bid[5:]})
            self.dismiss("reopen")
        elif bid == "localmodels":
            self.app.push_screen(LocalScreen())
        elif bid == "close":
            self.action_close()

    @on(Checkbox.Changed, "#autocloud")
    def _auto_cloud(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"auto_cloud": ev.value})

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
                elif self.step == 2:
                    yield Label(t("How should Lanterna think?", lang), classes="sub")
                    with Horizontal(classes="row"):
                        for i, (m, name, desc) in enumerate((
                                ("cloud", "Cloud", "Free models online. Works on any laptop."),
                                ("local", "Local", "Models run on your graphics card. Fully private."),
                                ("auto", "Auto", "Local first, cloud when needed."))):
                            with Vertical(classes="card first" if i == 0 else "card"):
                                yield Static(t(name, lang), classes="cardname", markup=False)
                                yield Static(t(desc, lang), classes="muted")
                                yield Button(t("Choose", lang), id=f"mode-{m}", variant="primary" if i == 0 else "default")
                    with Horizontal(classes="row"):
                        yield Button(t("Back", lang), id="back")
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
        elif bid.startswith("mode-"):
            mode = bid[5:]
            self.app.api.save_settings({"mode": mode})
            if mode == "cloud":
                self.step = 3
            else:
                self.app.push_screen(LocalScreen(onboarding=True), self._local_done)
        elif bid.startswith("pick-"):
            pid = bid[5:]
            self.app.api.save_settings({"provider": pid})
            if self.app.api.state()["providers"] and any(p["id"] == pid and p["has_key"] for p in self.app.api.state()["providers"]):
                self._finish(True)
            else:
                self.app.push_screen(KeyScreen(pid), self._finish)

    def _local_done(self, res: str) -> None:
        api = self.app.api
        if res == "cloud":
            api.save_settings({"mode": "cloud"})
            self.step = 3
        elif api.settings.mode == "auto":
            self.step = 3                                   # auto also needs a cloud key
        elif api.local_status()["models"]:
            self._finish(True)
        else:
            self.app.notify(t("Download at least one model to continue.", L(self.app)), severity="warning")

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
        self._tools_seen = 0
        self._files: list[str] = []          # paths waiting to be sent

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
                yield Label("", id="attached")
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
        threads = self.app.api.threads() if threads is None else threads
        self.run_worker(self._refill_threads(threads), group="threads")

    async def _refill_threads(self, threads: list[dict]) -> None:
        # One refill at a time: overlapping refills used to show a chat twice in the list.
        if getattr(self, "_threads_lock", None) is None:
            self._threads_lock = asyncio.Lock()
        async with self._threads_lock:
            lv = self.query_one("#threads", ListView)
            await lv.clear()
            await lv.extend([ListItem(Label(th["title"] or t("New chat", L(self.app)), markup=False), name=str(th["id"]))
                             for th in threads])
            for i, th in enumerate(threads):
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
        if text.startswith("/file "):                     # "/file ~/photo.jpg" attaches without the dialog
            self._attach_file(text[6:].strip().strip('"'))
            ev.input.value = ""
            return
        if not text and not self._files:
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
        files, self._files = self._files, []
        self._paint_files()
        shown = "\n".join([text] * bool(text) + [f"📎 {Path(f).name}" for f in files])
        log.mount(Static(shown, classes="msg-user", markup=False))
        res = self.app.api.send(self.tid, text, [{"path": f} for f in files])
        if not res.get("ok"):
            err = res.get("message") or res.get("error")
            log.mount(Static(t("Error: {err}", L(self.app), err=err), classes="msg-err", markup=False))
            return
        self._stream, self._offset, self._text, self._notes_seen, self._tools_seen = res["stream"], 0, "", 0, 0
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
        for chip in r.get("tools", [])[self._tools_seen:]:
            await log.mount(Static(tool_text(chip, lang), classes="msg-tool", markup=False), before=self._bot)
        self._tools_seen = len(r.get("tools", []))
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
        local_mode = self.app.api.settings.mode == "local"
        if kind == "local" and err.get("message") == "no local models":
            return t("No local model yet. Download one in Settings → Local models.", lang)
        if kind == "local" or (kind == "network" and local_mode):
            return t("Ollama isn't running. Start it, or switch to Cloud in Settings.", lang)
        if kind == "network":
            return t("Network problem: {err}", lang, err=err.get("message", ""))
        if kind == "vision" and local_mode:
            return t("To understand photos, download a photo model in Settings → Local models.", lang)
        if kind == "vision":
            return t("To understand photos, add a free Gemini key in Settings.", lang)
        return t("Error: {err}", lang, err=err.get("message", ""))

    # attachments ---------------------------------------------------------------
    def action_attach(self) -> None:
        self.app.push_screen(FileScreen(), lambda p: p and self._attach_file(p))

    def _attach_file(self, path: str) -> None:
        p = Path(path).expanduser()
        if not p.is_file():
            self.app.notify(t("File not found.", L(self.app)), severity="error")
            return
        self._files.append(str(p))
        self._paint_files()
        self.query_one("#composer", Input).focus()

    def _paint_files(self) -> None:
        self.query_one("#attached", Label).update("  ".join(f"📎 {Path(f).name}" for f in self._files))

    # dialogs -----------------------------------------------------------------
    def action_settings(self) -> None:
        def done(res: str) -> None:
            if res == "lang":
                self.app.switch_screen(make_chat_screen(L(self.app)))
            elif res == "reopen":                         # mode changed: show the matching options
                self._load_model_label()
                self.app.push_screen(SettingsScreen(), done)
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
        Binding("ctrl+f", "attach", t("Attach", lang), priority=True),
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
        self.set_interval(10, self._alerts)

    def _alerts(self) -> None:
        for a in self.api.alerts():
            self.bell()
            self.notify(a["text"], title="⏰ " + t("Reminder", L(self)), timeout=30)


def run(force_setup: bool = False) -> int:
    LanternaApp(force_setup=force_setup).run()
    return 0
