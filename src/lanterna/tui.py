"""Full-screen terminal app (Textual): first-run setup, chats, settings. Works with mouse and keyboard.

Uses the same backend as the window app (app.Api), so chats are shared between both.
"""
from __future__ import annotations

import asyncio
import re
import threading
import time

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.app import SystemCommand
from textual.command import CommandPalette, DiscoveryHit, Hit, Hits, Provider
from textual.widgets import (Button, Checkbox, Collapsible, DataTable, Footer, Input, Label, ListItem, ListView, LoadingIndicator,
                             Markdown, OptionList, ProgressBar, Select, Static, TabbedContent, TabPane, TextArea)
from textual.widgets.option_list import Option

from pathlib import Path

from . import AUTHOR, __version__
from .app import Api, action_title, card_text
from .cli import FIRST_CHOICES
from .i18n import LANGS, t
from .providers import PROVIDERS


def lang_rows(per: int = 4) -> list[list[tuple[str, str]]]:
    """Language buttons in rows, so seven of them fit an 80-column terminal."""
    items = list(LANGS.items())
    return [items[i:i + per] for i in range(0, len(items), per)]


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
#findchats { width: 100%; margin-bottom: 1; }
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
AskForm { height: auto; margin: 1 8 0 0; padding: 0 1; border: round $panel-lighten-2; }
AskForm .askq { margin-top: 1; }
AskForm Input { margin: 0; }
AskForm Horizontal { height: auto; margin-top: 1; }
.follow { height: auto; margin: 1 8 0 0; }
.learned { height: auto; margin: 1 8 0 0; }
.learnedtext { width: auto; color: $text-muted; padding: 0 1 0 0; }
.followbtn { width: auto; min-width: 4; height: 1; border: none; margin: 0 0 0 0; padding: 0 1; background: $panel; }
.welcome { color: $text-muted; margin: 2 0; content-align: center middle; width: 100%; }
#composer { margin: 0 2 1 2; border: round $panel-lighten-2; }
#attached { margin: 0 3; color: $primary; height: auto; }
.msg-tool { color: $text-muted; margin: 1 0 0 0; }
.listrow { height: auto; width: 100%; }
.listrow Label { width: 1fr; padding: 1 0 0 0; }
#composer:focus { border: round $primary; }
ModalScreen { align: center middle; background: $background 70%; }
#updcmd { width: 1fr; height: auto; padding: 1 1; background: $boost; color: $warning; }
#updrest { margin-top: 1; }
#updbox .row { margin-top: 1; }
#bugtext { height: 6; }
#bugpreview { height: auto; max-height: 10; padding: 0 1; background: $boost; color: $text-muted; }
#bugbox .row { margin-top: 1; }
.dialog { width: 80; max-width: 100%; height: auto; max-height: 90%; border: round $primary; background: $surface; padding: 1 2; }
.dialog .h { text-style: bold; color: $primary; margin: 1 0 0 0; }
.keyrow { height: auto; width: 100%; }
.histrow { height: auto; width: 100%; }
.sent { margin: 0 8 0 0; padding: 0; border: none; background: transparent; }
.sent CollapsibleTitle { color: $text-muted; padding: 0; }
.sugg { height: auto; }
.idea { margin: 0 0 0 0; min-width: 20; height: 3; }
.histtext { width: 1fr; padding: 1 0 0 0; }
#histrows { height: auto; }
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
#sidefoot { height: auto; border-top: solid $panel; padding-top: 1; }
.sidebtn { width: 100%; height: 1; min-width: 0; border: none; background: $surface; color: $text-muted;
           content-align: left middle; text-align: left; padding: 0 1; margin: 0; text-style: none; }
.sidebtn:hover, .sidebtn:focus { background: $panel; color: $text; }
.hint { color: $text-muted; margin: 1 0 0 0; width: 100%; content-align: center middle; }
.bigdialog { width: 110; max-width: 100%; height: 90%; max-height: 90%; }
.dlghead { height: 1; width: 100%; margin-bottom: 1; }
.dlgtitle { text-style: bold; color: $primary; width: auto; }
.dlgkeys { width: 1fr; content-align: right middle; text-align: right; }
.bigdialog TabbedContent { height: 1fr; }
.bigdialog TabPane { padding: 0; height: 1fr; }
.setpane { height: 1fr; padding: 0 1 0 0; }
.setpane > .h:first-child { margin-top: 0; }
#cn-list, #cn-mine { height: 1fr; border: none; background: $surface; }
#cn-about, #cn-mineinfo { height: auto; min-height: 2; margin-top: 1; }
#cn-q { width: 1fr; }
#autobar { height: 1; width: 100%; background: $boost; display: none; }
#autotext { width: 1fr; color: $warning; padding: 0 1; }
#autostop { width: auto; min-width: 10; }
#cn-cat { width: 34; }
#choices { height: auto; max-height: 16; margin-top: 1; }
"""


VOICE_ERR = {"off": "Turn on voice input in Settings first.", "no_engine": "Download the speech engine in Settings → Voice input first.", "no_key": "Online voice input needs the Groq key (Settings → Keys).",
             "no_mic": "No microphone found.", "network": "Couldn't reach the speech service. Check the internet.", "engine": "The speech engine didn't work this time.", "empty": "I didn't hear anything. Try again a bit closer to the microphone."}

TOOL_TEXT = {"weather": "Checking the weather", "web_search": "Searching the web", "read_page": "Reading a page",
             "calculate": "Calculating", "date_calc": "Counting dates", "remember": "Saving to memory",
             "forget": "Updating memory", "set_reminder": "Setting a reminder", "list_reminders": "Checking reminders",
             "cancel_reminder": "Cancelling a reminder", "add_task": "Adding a regular task",
             "list_tasks": "Checking regular tasks", "delete_task": "Deleting a regular task",
             "currency": "Converting currency", "convert_units": "Converting units",
             "transcribe_audio": "Turning audio into text", "search_chats": "Looking through earlier chats",
             "read_chat": "Reading an earlier chat"}


def tool_text(chip: str, lang: str) -> str:
    emo, _, name = chip.partition(" ")
    return f"{emo} {t(TOOL_TEXT.get(name, name), lang)}"


def L(app) -> str:
    return app.api.settings.lang


# ---------------------------------------------------------------------------------------------- dialogs


_OL_ITEM = re.compile(r"^(\s{0,3})(\d{1,4})([.)])(\s+)")


def count_on(text: str) -> str:
    """Some models write "1." before every item and put text between the items, so every item is its own list
    and shows 1, 1, 1. A "1." that starts a list right after a one-item list counts on instead (like the window)."""
    out, fence, last, items, inside, gap = [], False, 0, 0, False, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else _OL_ITEM.match(line)
        if m:
            n = int(m.group(2))
            if not inside:
                if n == 1 and items == 1 and last:
                    n = last + 1
                    line = f"{m.group(1)}{n}{m.group(3)}{m.group(4)}" + line[m.end():]
                items = 0
            inside, gap, last, items = True, False, n, items + 1
        elif not line.strip():
            gap = True
        elif inside and gap and not line.startswith(("  ", "\t")):
            inside = False                       # text after a blank line ends the list
        out.append(line)
    return "\n".join(out)


class AskForm(Vertical):
    """The mini-questionnaire before a big task: options to tick, "Other" to type; the answers go as a message."""

    def __init__(self, questions: list[dict]):
        super().__init__()
        self.questions = questions

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        yield Label(t("Questions for you:", lang), classes="h")
        for i, q in enumerate(self.questions):
            yield Label(f"{i + 1}. {q['question']}", classes="askq")
            for j, o in enumerate(q.get("options") or []):
                yield Checkbox(o, False, id=f"ask{i}_{j}")
            yield Input(placeholder=t("Other", lang) + "…", id=f"ask{i}_other")
        with Horizontal():
            yield Button(t("Send answers", lang), variant="primary", id="asksend")
            yield Button(t("Skip", lang), id="askskip")

    @on(Checkbox.Changed)
    def _one_choice(self, ev: Checkbox.Changed) -> None:
        i, j = ev.checkbox.id[3:].split("_")
        if ev.value and not self.questions[int(i)].get("multi"):     # one answer: the other options untick
            for k in range(len(self.questions[int(i)].get("options") or [])):
                if str(k) != j:
                    self.query_one(f"#ask{i}_{k}", Checkbox).value = False

    def _send(self, text: str) -> None:
        box = self.app.screen.query_one("#composer", Input)
        box.value = text
        box.post_message(Input.Submitted(box, text))

    @on(Button.Pressed, "#asksend")
    def _answers(self) -> None:
        lang = L(self.app)
        lines, skipped = [t("My answers to your questions:", lang)], t("(skipped)", lang)
        for i, q in enumerate(self.questions):
            picked = [o for j, o in enumerate(q.get("options") or []) if self.query_one(f"#ask{i}_{j}", Checkbox).value]
            own = self.query_one(f"#ask{i}_other", Input).value.strip()
            ans = ", ".join(picked + ([own] if own else []))
            lines.append(f"{i + 1}. {q['question']} — {ans or skipped}")
        self._send("\n".join(lines))

    @on(Button.Pressed, "#askskip")
    def _skip(self) -> None:
        self._send(t("Skip the questions: do it your way and tell me what you assumed.", L(self.app)))

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
            if p.note:
                yield Static(t(p.note, lang), classes="muted", markup=False)
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


class ActCard(Vertical):
    """A change the assistant proposed (working folder, Google Drive): it happens only after Confirm."""

    DEFAULT_CSS = """
    ActCard { border: round $warning; padding: 0 1; margin: 1 0 0 0; height: auto; }
    ActCard .row { height: auto; }
    """

    def __init__(self, card: dict):
        super().__init__()
        self.card = card

    def compose(self) -> ComposeResult:
        lang, c = L(self.app), self.card
        d = c.get("details", {})
        k = c["kind"]
        icon = ("🤖 " if k == "auto_on" else "🎨 " if k == "sys_look" else "☁️ " if k.startswith("drive_") else "🐙 " if k.startswith("github_") else "🗑 " if k == "pc_trash" else
                "🗂 " if k.startswith("pc_") else "📦 " if k.startswith("app_") else "⚙️ " if k.startswith("sys_") else "🧩 " if k == "mcp_call" else "📬 " if k.startswith("mail_") else "📁 ")
        yield Static(icon + action_title(k, d, "", lang), markup=False)
        body = card_text(k, d, lang)
        if body:
            yield Static(body, classes="muted", markup=False)
        if d.get("preview"):
            yield Static(d["preview"][:600] + ("…" if len(d["preview"]) > 600 else ""), classes="muted", markup=False)
        yield Static(t("Lanterna will do this only after you confirm.", lang), classes="muted", id="actq", markup=False)
        with Horizontal(classes="row", id="actbtns"):
            yield Button(t("Confirm", lang), id="actyes", variant="primary")
            yield Button(t("Cancel", lang), id="actno")
        yield Button(t("Undo", lang), id="actundo")

    def on_mount(self) -> None:
        self.query_one("#actundo").display = False
        if self.card.get("state", "pending") != "pending":       # done on its own (or answered before)
            self.query_one("#actbtns").display = False
            self._show({"state": self.card["state"], "text": self.card.get("text", ""), "result": self.card.get("result", "")})

    @on(Button.Pressed, "#actyes")
    @on(Button.Pressed, "#actno")
    def _answer(self, ev: Button.Pressed) -> None:
        api, lang, yes = self.app.api, L(self.app), ev.button.id == "actyes"
        self.query_one("#actbtns").display = False
        if yes:
            self.query_one("#actq", Static).update(t("Installing… this can take a few minutes." if self.card["kind"].startswith("app_")
                                                     else "Working…", lang))

        def work() -> None:                                   # installs take minutes: keep the app responsive
            r = api.action_confirm(self.card["id"]) if yes else api.action_cancel(self.card["id"])
            self.app.call_from_thread(self._show, r)
        threading.Thread(target=work, daemon=True).start()

    def _show(self, r: dict) -> None:
        lang = L(self.app)
        msg = ("✅ " + r.get("text", "") if r["state"] == "done" else t("Cancelled", lang) if r["state"] == "cancelled"
               else "⚠️ " + t("Couldn't do it: {error}", lang, error=r.get("result", "")) if r["state"] == "failed"
               else t("This card has expired. Ask again.", lang))
        if r["state"] == "done" and (self.card.get("auto") or self.card.get("details", {}).get("auto")):
            msg += "  · 🤖 " + t("on its own; Undo is in What Lanterna did", lang)
        self.query_one("#actq", Static).update(msg)
        self.query_one("#actundo").display = self.card["kind"] == "pc_sort" and r["state"] == "done"
        if self.card["kind"] == "auto_on" and r["state"] == "done" and hasattr(self.screen, "_paint_auto"):
            self.screen._paint_auto()

    @on(Button.Pressed, "#actundo")
    def _undo(self) -> None:
        r = self.app.api.pc_undo(self.card.get("details", {}).get("undo", ""))
        self.query_one("#actundo").display = False
        self.query_one("#actq", Static).update(("↩ " if r["ok"] else "⚠️ ") + r["text"])


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


class NameScreen(ModalScreen[str]):
    """A chat's new name: Enter or Save keeps it, Esc or Cancel leaves the old one."""
    BINDINGS = [Binding("escape", "no", show=False)]

    def __init__(self, heading: str, value: str):
        super().__init__()
        self.heading, self.value = heading, value

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog"):
            yield Label(self.heading, classes="h")
            yield Input(self.value, placeholder=t("Chat name", lang), max_length=80, id="name")
            with Horizontal(classes="row"):
                yield Button(t("Save", lang), id="yes", variant="primary")
                yield Button(t("Cancel", lang), id="no")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    @on(Input.Submitted, "#name")
    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if name:
            self.dismiss(name)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss("")


class UpdateScreen(ModalScreen[None]):
    """A new version is out: what's new and the steps for this kind of install."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, info: dict):
        super().__init__()
        self.info = info

    def compose(self) -> ComposeResult:
        lang, u = L(self.app), self.info
        with VerticalScroll(classes="dialog", id="updbox"):
            yield Label(f"{LOGO} " + t("Lanterna {v} is out", lang, v=u["latest"]), classes="title")
            yield Label(t("You have {v}.", lang, v=u["current"]), classes="sub")
            if u.get("notes"):
                yield Label(t("What's new", lang), classes="h")
                yield Static("\n".join("• " + n for n in u["notes"]), markup=False, classes="muted")
            yield Label(t("How to update", lang), classes="h")
            steps = [f"{i}. {s}" for i, s in enumerate(u.get("steps") or [], 1)]
            # the command goes right under the "run:" step
            cut = next((i + 1 for i, s in enumerate(steps) if s.endswith(":")), len(steps)) if u.get("command") else len(steps)
            yield Static("\n".join(steps[:cut]), markup=False, id="updsteps")
            if u.get("command"):
                with Horizontal(classes="keyrow"):
                    yield Static(u["command"], markup=False, id="updcmd")
                    yield Button(t("Copy", lang), id="updcopy")
            if steps[cut:]:
                yield Static("\n".join(steps[cut:]), markup=False, id="updrest")
            if u.get("auto"):
                yield Static(t("Or press Update now: Lanterna runs it for you and you only start it again.", lang),
                             id="updstate", classes="muted")
            with Horizontal(classes="row"):
                if u.get("auto"):
                    yield Button(t("Update now", lang), id="updnow", variant="primary")
                    yield Button(t("Restart now", lang), id="updrestart", variant="success")
                if u.get("download"):
                    yield Button(t("Download", lang), id="upddl", variant="primary")
                yield Button(t("Release page", lang), id="updpage")
                yield Button(t("Later", lang), id="updlater")

    def on_mount(self) -> None:
        if self.info.get("auto"):
            self.query_one("#updrestart", Button).display = False

    @on(Button.Pressed, "#updnow")
    def _now(self, ev: Button.Pressed) -> None:
        ev.button.disabled = True
        self._show(self.app.api.update_install())
        self._timer = self.set_interval(0.7, lambda: self._show(self.app.api.update_status()))

    def _show(self, st: dict) -> None:
        lang, box = L(self.app), self.query_one("#updstate", Static)
        if st["phase"] in ("installing", "downloading"):
            box.update(t("Updating with pipx… this can take a minute or two.", lang))
            return
        if hasattr(self, "_timer"):
            self._timer.stop()
        if st["phase"] == "restart":
            box.update("✓ " + t("Lanterna {v} is installed. Start it again to use it.", lang, v=self.info["latest"]))
            self.query_one("#updnow", Button).display = False
            self.query_one("#updrestart", Button).display = True
            self.query_one("#updrestart", Button).focus()
        else:
            box.update("⚠️ " + t("The update didn't work: {error}", lang, error=st.get("error", "")) + "\n"
                       + t("This version keeps working. You can update by hand.", lang))
            self.query_one("#updnow", Button).disabled = False

    @on(Button.Pressed, "#updrestart")
    def _restart(self) -> None:
        self.app.exit("restart")

    @on(Button.Pressed, "#updcopy")
    def _copy(self, ev: Button.Pressed) -> None:
        self.app.copy_to_clipboard(self.info["command"])
        ev.button.label = t("Copied", L(self.app))

    @on(Button.Pressed, "#upddl")
    def _download(self) -> None:
        self.app.api.open_url(self.info["download"])

    @on(Button.Pressed, "#updpage")
    def _page(self) -> None:
        self.app.api.open_url(self.info["url"])

    @on(Button.Pressed, "#updlater")
    def action_close(self) -> None:
        self.dismiss(None)


class HistoryScreen(ModalScreen[None]):
    """What Lanterna did: confirmed changes on this computer, newest first, with Undo."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with VerticalScroll(classes="dialog", id="histbox"):
            yield Label(f"{LOGO} " + t("What Lanterna did", lang), classes="title")
            yield Static(t("Changes you confirmed on this computer, newest first. Undo puts files back, takes them out of the Recycle Bin or switches a setting back.", lang), classes="muted")
            yield Vertical(id="histrows")
            yield Static("", id="histmsg", classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Clear the list", lang), id="histclear")
                yield Button(t("Close", lang), id="histclose", variant="primary")

    def on_mount(self) -> None:
        self._fill(self.app.api.history_list())

    def _fill(self, items: list[dict]) -> None:
        import datetime as _dt
        lang, box = L(self.app), self.query_one("#histrows", Vertical)
        box.remove_children()
        if not items:
            box.mount(Static(t("Nothing yet. When you confirm a change on a card, it shows up here.", lang), classes="muted"))
            return
        for x in items[:100]:
            when = _dt.datetime.fromtimestamp(x["at"]).strftime("%d.%m %H:%M")
            text = f"{when}  {x['title']}" + (f"\n   ↩ {x['note'] or t('Undone', lang)}" if x["undone"] else "")
            row = Horizontal(Static(text, markup=False, classes="histtext"), classes="histrow")
            box.mount(row)
            if x["can_undo"]:
                row.mount(Button(t("Undo", lang), id=f"hu-{x['id']}"))

    @on(Button.Pressed)
    def _pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if bid.startswith("hu-"):
            ev.button.disabled = True
            self._undo(bid[3:])
        elif bid == "histclear":
            self._fill(self.app.api.history_clear())
        elif bid == "histclose":
            self.dismiss(None)

    @work(thread=True, exclusive=True, group="undo")
    def _undo(self, hid: str) -> None:
        r = self.app.api.history_undo(hid)
        self.app.call_from_thread(self._after, r)

    def _after(self, r: dict) -> None:
        self.query_one("#histmsg", Static).update(("↩ " if r["ok"] else "⚠️ ") + r["text"])
        self._fill(self.app.api.history_list())

    def action_close(self) -> None:
        self.dismiss(None)


class DoctorScreen(ModalScreen[None]):
    """Check Lanterna: keys, internet, sync, folders, programs, local models — each with a plain sentence."""

    BINDINGS = [Binding("escape", "close", show=False)]
    COLORS = {"ok": "green", "warn": "yellow", "fail": "red", "info": "grey62"}

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with VerticalScroll(classes="dialog", id="docbox"):
            yield Label(f"{LOGO} " + t("Check Lanterna", lang), classes="title")
            yield Static(t("Checking Lanterna…", lang), id="docres")
            with Horizontal(classes="row"):
                yield Button(t("Copy", lang), id="doccopy")
                yield Button(t("Report a bug", lang), id="docbug")
                yield Button(t("Close", lang), id="docclose", variant="primary")

    def on_mount(self) -> None:
        self._text = ""
        self._run()

    @work(thread=True, exclusive=True, group="doctor")
    def _run(self) -> None:
        res = self.app.api.doctor()
        self.app.call_from_thread(self._fill, res)

    def _fill(self, res: dict) -> None:
        from rich.markup import escape
        from .doctor import MARK
        lang = L(self.app)
        lines = [f"[{self.COLORS[c['status']]}]{MARK[c['status']]}[/] [b]{escape(c['title'])}[/]  {escape(c['detail'])}"
                 for c in res["checks"]]
        lines += ["", t("Everything works." if res["worst"] == "ok" else "Something needs attention (see the lines above).", lang)]
        self.query_one("#docres", Static).update("\n".join(lines))
        self._text = res["text"]

    @on(Button.Pressed, "#doccopy")
    def _copy(self, ev: Button.Pressed) -> None:
        if self._text:
            self.app.copy_to_clipboard(self._text)
            ev.button.label = t("Copied", L(self.app))

    @on(Button.Pressed, "#docbug")
    def _bug(self) -> None:
        self.dismiss(None)
        self.app.push_screen(BugScreen())

    @on(Button.Pressed, "#docclose")
    def action_close(self) -> None:
        self.dismiss(None)


class BugScreen(ModalScreen[None]):
    """Report a bug: the user writes, sees the exact text, and sends it from their mail app or GitHub."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with VerticalScroll(classes="dialog", id="bugbox"):
            yield Label(f"{LOGO} " + t("Report a bug", lang), classes="title")
            yield Static(t("Tell what went wrong. You see the whole text first, and you send it yourself.", lang), classes="muted")
            yield TextArea(id="bugtext")
            yield Checkbox(t("Add app and system info", lang), value=True, id="buginfo")
            yield Static(t("Version, system, mode and the last errors. Never chats, keys or your name.", lang), classes="muted")
            yield Label(t("This is exactly what will be sent:", lang), classes="h")
            yield Static("", markup=False, id="bugpreview")
            yield Static("", id="bugnote", classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Write e-mail", lang), id="bugmail", variant="primary")
                yield Button(t("Open on GitHub", lang), id="buggh")
                yield Button(t("Copy text", lang), id="bugcopy")
                yield Button(t("Close", lang), id="bugclose")

    def on_mount(self) -> None:
        self.query_one("#bugtext", TextArea).focus()
        self._refresh()

    def _refresh(self) -> dict:
        lang = L(self.app)
        r = self.app.api.bug_report(self.query_one("#bugtext", TextArea).text, self.query_one("#buginfo", Checkbox).value)
        self.report = r
        self.query_one("#bugpreview", Static).update(r["body"] or "…")
        self.query_one("#bugmail", Button).display = bool(r["email"])
        self._say(t("No mail app? Copy the text and send it to {email} from any mail.", lang, email=r["email"]) if r["email"]
                  else t("Reports by e-mail are coming soon. For now open it on GitHub (free account) or copy the text.", lang))
        return r

    def _say(self, msg: str) -> None:
        self.query_one("#bugnote", Static).update(msg)

    def _ready(self) -> bool:
        if self._refresh()["ok"]:
            return True
        self._say("[b]" + t("Write a few words first.", L(self.app)) + "[/b]")
        self.query_one("#bugtext", TextArea).focus()
        return False

    @on(TextArea.Changed, "#bugtext")
    @on(Checkbox.Changed, "#buginfo")
    def _changed(self) -> None:
        self._refresh()

    @on(Button.Pressed, "#bugcopy")
    def _copy(self, ev: Button.Pressed) -> None:
        if self._ready():
            self.app.copy_to_clipboard(self.report["body"])
            ev.button.label = t("Copied", L(self.app))

    @on(Button.Pressed, "#buggh")
    def _github(self) -> None:
        if self._ready():
            self.app.api.open_url(self.report["issue"])

    @on(Button.Pressed, "#bugmail")
    def _mail(self) -> None:
        if not self._ready():
            return
        lang, r = L(self.app), self.report
        if r["cut"]:
            self.app.copy_to_clipboard(r["body"])
            self._say(t("The text is long, so the letter is shortened. The full text is copied: paste it into the letter.", lang))
        else:
            self._say(t("Your mail app opens with the letter ready. Check it and press Send.", lang))
        self.app.api.open_mail(r["mailto"])

    @on(Button.Pressed, "#bugclose")
    def action_close(self) -> None:
        self.dismiss(None)


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
                yield Button(t("Install Ollama", lang), id="install-ollama", variant="primary")
                yield Button(t("Download Ollama", lang), id="get-ollama", variant="primary")
                yield Button(t("Check again", lang), id="recheck")
            yield Label(t("Recommended for this computer", lang), classes="h")
            yield Vertical(id="lmodels")
            yield Static(t("Downloads start only when you press the button. Models are stored by Ollama on this computer.", lang),
                         classes="muted")
            yield Vertical(id="picks")
            yield Checkbox(t("Use a local model when the online limits run out", lang), self.app.api.settings.local_fallback,
                           id="localfallback")
            yield Static(t("In Cloud mode, when every free online model is out of its limit or there is no internet, a model downloaded here answers instead. It stays on this computer.", lang), classes="muted")
            with Horizontal(classes="row"):
                if self._onboarding:
                    yield Button(t("Use the cloud instead", lang), id="to-cloud")
                yield Button(t("Continue", lang) if self._onboarding else t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#ollama-btns").display = False
        self._load()

    @on(Checkbox.Changed, "#localfallback")
    def _fallback(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"local_fallback": ev.value})

    @on(Button.Pressed, "#install-ollama")
    def _install_ollama(self, ev: Button.Pressed) -> None:
        lang = L(self.app)

        def go(yes: bool) -> None:
            if yes:
                ev.button.disabled = True
                ev.button.label = t("Installing… this can take a few minutes.", lang)
                self._run_install()
        self.app.push_screen(ConfirmScreen(t("Install Ollama with winget? Windows may ask for administrator rights.", lang)
                                           + "\n\nwinget install --id Ollama.Ollama --exact", t("Install", lang)), go)

    @work(thread=True, exclusive=True, group="install")
    def _run_install(self) -> None:
        r = self.app.api.install_ollama()
        self.app.call_from_thread(self.app.notify, r["text"])
        self.app.call_from_thread(self._load)

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
        self.query_one("#install-ollama", Button).display = bool(st.get("can_install"))
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
                yield Button(t("How to update", lang), id="howupdate", variant="warning")
                yield Button(t("Star on GitHub", lang), id="star", variant="primary")
                yield Button(t("Check Lanterna", lang), id="doctor")
                yield Button(t("Report a bug", lang), id="aboutbug")
                yield Button(t("Close", lang), id="close")

    @on(Button.Pressed, "#doctor")
    def _doctor(self) -> None:
        self.dismiss(None)
        self.app.push_screen(DoctorScreen())

    def on_mount(self) -> None:
        self.query_one("#howupdate", Button).display = False
        self._check_update()

    @on(Button.Pressed, "#howupdate")
    def _how(self) -> None:
        info = self._update
        self.dismiss(None)
        self.app.push_screen(UpdateScreen(info))

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
            box.update(f"[b]{t('Version {v} is available', lang, v=res['latest'])}[/b]")
            self._update = res
            self.query_one("#howupdate", Button).display = True
        else:
            box.update("✓ " + t("You have the latest version", lang))

    @on(Button.Pressed, "#aboutbug")
    def _bug(self) -> None:
        self.dismiss(None)
        self.app.push_screen(BugScreen())

    @on(Button.Pressed, "#star")
    def _star(self) -> None:
        self.app.api.open_url(self.app.api.state()["homepage"])

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)


SET_TABS = [("general", "General"), ("models", "Models"), ("memory", "Memory and reminders"), ("chats", "Chats"),
            ("voice", "Voice"), ("pc", "Computer and tools"), ("account", "Account")]


class SettingsScreen(ModalScreen[str]):
    """Returns "lang" when the language changed (the app then rebuilds its screens). In tabs, like the window."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, tab: str = ""):
        super().__init__()
        self.tab = tab if tab in dict(SET_TABS) else ""

    @on(TabbedContent.TabActivated, "#settabs")
    def _tab_seen(self, ev: TabbedContent.TabActivated) -> None:
        self.app._set_tab = (ev.pane.id or "st-general")[3:]           # opens on the same tab next time

    @on(Button.Pressed, "#openconn")
    def _open_connectors(self) -> None:
        self.dismiss("")
        if hasattr(self.app.screen, "action_connectors"):
            self.app.screen.action_connectors()

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog bigdialog"):
            with Horizontal(classes="dlghead"):
                yield Label("⚙ " + t("Settings", lang), classes="dlgtitle")
                yield Label(t("Tab: next · ←/→: tabs · Esc: close", lang), classes="muted dlgkeys")
            with TabbedContent(initial=f"st-{self.tab or getattr(self.app, '_set_tab', '') or 'general'}", id="settabs"):
                with TabPane(t("General", lang), id="st-general"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Language", lang), classes="h")
                        for row in lang_rows():
                            with Horizontal(classes="row"):
                                for code, name in row:
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
                        yield Label(t("Updates", lang), classes="h")
                        yield Checkbox(t("Check for a new version when Lanterna starts", lang), self.app.api.settings.update_check, id="updcheck")
                        yield Static(t("A plain request to the project's release page, nothing about you.", lang), classes="muted")
                with TabPane(t("Models", lang), id="st-models"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Keys", lang), classes="h")
                        yield Vertical(id="keys")
                        yield Label(t("Models", lang), classes="h")
                        yield Button(t("Show models", lang), id="models")
                        yield Label(t("Limits", lang), classes="h")
                        yield Static("", id="limits", classes="muted")
                with TabPane(t("Memory and reminders", lang), id="st-memory"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Memory", lang), classes="h")
                        yield Vertical(id="facts")
                        with Horizontal(classes="keyrow"):
                            yield Input(placeholder=t("Add a fact", lang), id="newfact")
                            yield Button(t("Add", lang), id="addfact")
                        yield Label(t("Reminders", lang), classes="h")
                        yield Vertical(id="rems")
                        st = self.app.api.settings
                        yield Checkbox(t("Morning summary", lang), st.morning, id="morning")
                        yield Static(t("Once a day at this time: the weather in your city, today's reminders and regular tasks. Made on this computer without a model; only the weather is asked from Open-Meteo.", lang), classes="muted")
                        with Horizontal(classes="keyrow"):
                            yield Input(st.morning_at, placeholder="08:00", id="morningat")
                            yield Input(st.morning_city, placeholder=t("City for the weather (optional)", lang), id="morningcity")
                            yield Button(t("Save", lang), id="morningsave")
                            yield Button(t("Show it now", lang), id="morningshow")
                        yield Label(t("Regular tasks", lang), classes="h")
                        yield Static(t("Lanterna does these on its own and sends you the result. They run while Lanterna is open or in the tray and stay on this computer.", lang), classes="muted")
                        yield Vertical(id="tasks")
                with TabPane(t("Chats", lang), id="st-chats"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Chats", lang), classes="h")
                        yield Checkbox(t("Name new chats automatically", lang), self.app.api.settings.ai_titles, id="aititles")
                        yield Static(t("After the first answer, a fast online model (or the local one in Local mode) gives the chat a short name. One small extra request.", lang), classes="muted")
                        yield Checkbox(t("Suggest what to ask next", lang), self.app.api.settings.follow_ups, id="followups")
                        yield Static(t("Up to 3 buttons under an answer with follow-up questions, written by a fast online model (not Gemini, and not in Local mode). One small extra request per answer.", lang), classes="muted")
                        yield Checkbox(t("Remember long chats", lang), self.app.api.settings.compact_chats, id="compactchats")
                        yield Static(t("When a chat gets long, a fast model writes a short summary of its older part, so Lanterna still remembers it. The summary stays on this device. One small extra request every 10 messages.", lang), classes="muted")
                        yield Checkbox(t("Ask before big tasks", lang), self.app.api.settings.ask_first, id="askfirst")
                        yield Static(t("Before a big task (a program, a plan, a project) the model may first ask you 1-4 short questions with options. Your answers become its instructions.", lang), classes="muted")
                        yield Checkbox(t("Learn about me from chats", lang), self.app.api.settings.auto_memory, id="automemory")
                        yield Static(t("When you tell something about yourself (job, city, what you like), a fast model adds it to Memory. You see each new fact and can undo it. Never passwords or numbers. Off by default.", lang), classes="muted")
                        yield Label(t("Instructions and roles", lang), classes="h")
                        yield Static(t("Tell Lanterna how to answer in every chat: about you, the tone, the length. For example: “Answer briefly. I study at a technical school, explain in simple words.”", lang), classes="muted")
                        yield TextArea(self.app.api.settings.instructions, id="instructions")
                        yield Button(t("Save", lang), id="instrsave")
                        yield Static(t("F6 changes the role of the open chat: Tutor, Translator, Proofreader or none.", lang), classes="muted")
                        yield Label(t("Working folder", lang), classes="h")
                        yield Static(t("Lanterna can look at the files in one folder you choose, and create or change files there after you confirm each change. It never deletes anything and sees nothing outside this folder.", lang)
                                     + " " + t("The files it opens are sent to the model in use (to the online service in Cloud mode).", lang), classes="muted")
                        yield Static("", id="wdinfo")
                        with Horizontal(classes="keyrow"):
                            yield Input(self.app.api.settings.work_dir, placeholder=t("Folder path", lang), id="wdpath")
                            yield Button(t("Save", lang), id="wdsave")
                            yield Button(t("Stop using it", lang), id="wdoff")
                        yield Label(t("Backups", lang), classes="h")
                        yield Static("", id="bkinfo", classes="muted")
                        with Horizontal(classes="keyrow"):
                            yield Input(placeholder=t("Password (at least {n} characters)", lang, n=8), password=True, id="bkpw")
                            yield Input(placeholder=t("The same password again", lang), password=True, id="bkpw2")
                            yield Button(t("Turn on", lang), id="bkset")
                        with Horizontal(classes="keyrow"):
                            yield Button(t("Back up now", lang), id="bknow")
                            yield Button(t("Turn off backups", lang), id="bkoff")
                        with Horizontal(classes="keyrow"):
                            yield Input(placeholder=t("Backup file path (.lanterna-backup or .json)", lang), id="bkfile")
                            yield Input(placeholder=t("Its password (if it was made elsewhere)", lang), password=True, id="bkfilepw")
                            yield Button(t("Restore", lang), id="bkrestore")
                        yield Button(t("Save a backup of all chats", lang), id="backupall")
                        yield Static(t("All chats, memory and reminders in one JSON file in Downloads. It is plain text: keep it somewhere safe.", lang), classes="muted")
                with TabPane(t("Voice", lang), id="st-voice"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Voice input", lang), classes="h")
                        yield Static(t("Press the microphone next to the message box (or F2), speak, and press it again: your words appear in the box.", lang), classes="muted")
                        with Horizontal(classes="modes"):
                            for eng, label in (("off", "Off"), ("groq", "Online (Groq Whisper)"), ("local", "On this computer (whisper.cpp)")):
                                yield Button(("● " if self.app.api.settings.voice == eng else "") + t(label, lang), id=f"voice-{eng}")
                        yield Static("", id="voiceinfo", classes="muted")
                        yield Button(t("Download ({mb} MB)", lang, mb="…"), id="voiceget")
                        yield Label(t("Reading aloud", lang), classes="h")
                        yield Static(t("F3 reads the last answer aloud; F3 again stops. Code and links are skipped.", lang), classes="muted")
                        with Horizontal(classes="modes"):
                            for eng, label in (("off", "Off"), ("system", "System voice (spd-say)"), ("piper", "Piper (natural voices)")):
                                yield Button(("● " if self.app.api.settings.tts == eng else "") + t(label, lang), id=f"tts-{eng}")
                        yield Static("", id="ttsinfo", classes="muted")
                        yield Button(t("Download ({mb} MB)", lang, mb="…"), id="ttsget")
                        yield Checkbox(t("Read each new answer aloud", lang), self.app.api.settings.tts_auto, id="ttsauto")
                with TabPane(t("Computer and tools", lang), id="st-pc"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Computer", lang), classes="h")
                        yield Checkbox(t("Let Lanterna help with this computer", lang), self.app.api.settings.pc_access, id="pcaccess")
                        yield Static(t("Your folders (Downloads, Desktop, Documents, Pictures, Videos, Music), programs and a few safe settings. Lanterna looks on its own; every change — moving, the Recycle Bin, installing, a setting — waits for your Confirm. File names and the files it opens go to the model in use.", lang), classes="muted")
                        yield Checkbox(t("Weekly tidy-up of Downloads", lang), self.app.api.settings.tidy_weekly, id="tidyweekly")
                        yield Static(t("Once a week, if new files are lying loose in Downloads, Lanterna makes a chat with a card to sort them into folders. Nothing moves until you confirm.", lang), classes="muted")
                        yield Checkbox(t("Help free up disk space", lang), self.app.api.settings.space_help, id="spacehelp")
                        yield Static(t("Lanterna can show what takes up space (big and old files, old installers, the Recycle Bin) and warns you when the disk is almost full. Removing goes only to the Recycle Bin, after you confirm.", lang), classes="muted")
                        yield Label(t("Connectors", lang), classes="h")
                        yield Button("🔌 " + t("Open Connectors", lang), id="openconn", variant="primary")
                        yield Static("", id="gdinfo", classes="muted")
                        with Horizontal(classes="row"):
                            yield Button(t("Connect", lang) + " Google Drive", id="gdon", variant="primary")
                            yield Button(t("Cancel", lang), id="gdcancel")
                            yield Button(t("Disconnect", lang), id="gdoff")
                        yield Static("", id="ghinfo", classes="muted")
                        with Horizontal(classes="row"):
                            yield Button(t("Connect", lang) + " GitHub", id="ghon", variant="primary")
                            yield Button(t("Cancel", lang), id="ghcancel")
                            yield Button(t("Disconnect", lang), id="ghoff")
                        yield Label(t("MCP servers", lang), classes="h")
                        yield Static(t("Add outside tools made by other people: a program on this computer or a web address. Lanterna asks before each use of a tool.", lang), classes="muted")
                        yield Button("", id="mcptoggle")
                        yield Vertical(id="mcplist")
                        yield Vertical(id="mcppresets")
                        with Horizontal(classes="keyrow", id="mcpaddrow"):
                            yield Input(placeholder=t("Command or https:// address", lang), id="mcpwhere")
                            yield Input(placeholder=t("Name (optional)", lang), id="mcpname")
                            yield Button(t("Add", lang), id="mcpadd")
                with TabPane(t("Account", lang), id="st-account"):
                    with VerticalScroll(classes="setpane"):
                        yield Label(t("Account and sync", lang), classes="h")
                        yield SyncBox()
            with Horizontal(classes="row"):
                yield Button(t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self.tab = self.tab or getattr(self.app, "_set_tab", "") or "general"
        self.query_one("#settabs", TabbedContent).active = f"st-{self.tab}"
        self._fill_keys()
        self._fill_memory()
        self._paint_wd()
        self._paint_voice()
        self._paint_tts()
        self._paint_backup()
        self._paint_mcp()
        self._paint_limits()
        self._paint_drive()
        self.set_interval(1.0, self._paint_drive)
        self._paint_github()
        self.set_interval(1.0, self._paint_github)

    # -- working folder, limits, Google Drive
    def _paint_wd(self, err: str = "") -> None:
        lang, w = L(self.app), self.app.api.workdir()
        info = ("📁 " + w["path"] + (" · " + t("not found", lang) if w["missing"] else "")) if w["path"] else t("No folder chosen.", lang)
        self.query_one("#wdinfo", Static).update(info + ("\n" + err if err else ""))

    @on(Button.Pressed, "#wdsave")
    @on(Input.Submitted, "#wdpath")
    def _wd_save(self) -> None:
        self._wd_set(self.query_one("#wdpath", Input).value)

    @on(Button.Pressed, "#wdoff")
    def _wd_off(self) -> None:
        self.query_one("#wdpath", Input).value = ""
        self._wd_set("")

    def _wd_set(self, path: str) -> None:
        lang, r = L(self.app), self.app.api.set_workdir(path)
        errs = {"not_found": "There is no such folder.",
                "too_broad": "Choose a smaller folder: not a whole disk, your whole home folder or a system folder."}
        self._paint_wd("" if r["ok"] else t(errs.get(r["error"], r["error"]), lang))

    def _paint_limits(self) -> None:
        lang, rows = L(self.app), self.app.api.limits()
        lines = []
        for r in rows:
            parts = [t("Requests today: {n}", lang, n=r["used"])]
            if r["limit"]:
                left = 0 if r["resting"] else max(0, r["limit"] - r["used"])
                parts.append(t("{left} of {limit} left today", lang, left=left, limit=r["limit"]))
            for x in r["left"]:
                parts.append(f"{x['kind']} ({x['period'] or '—'}): {x['remaining']}" + (f"/{x['limit']}" if x["limit"] else ""))
            if r["resting"]:
                parts.append(t("resting, back in {t}", lang, t=f"{max(1, round(r['resting'] / 60))} min"))
            lines.append(f"{r['service']} · {r['model']}: " + " · ".join(parts))
        self.query_one("#limits", Static).update("\n".join(lines) or t("No requests to online models yet today.", lang))

    def _paint_drive(self) -> None:
        lang, st = L(self.app), self.app.api.drive_status()
        ph = st["phase"]
        info = (t("Connected as {account}", lang, account=st["account"]) if st["account"] else t("Connected", lang)) if ph == "ready" \
            else t("Finish signing in in your browser…", lang) + ("\n" + st["url"] if st["url"] else "") if ph == "waiting" \
            else t("Lets the assistant create folders and save files in your Google Drive, after you confirm each one. It sees only what it created itself.", lang)
        if st["error"]:
            info += "\n" + (t("Google Drive was disconnected. Connect it again.", lang) if st["error"] == "signed_out" else st["error"])
        self.query_one("#gdinfo", Static).update("☁️ Google Drive — " + info)
        for bid, on_ in (("gdon", ph == "off"), ("gdcancel", ph == "waiting"), ("gdoff", ph == "ready")):
            self.query_one(f"#{bid}", Button).display = on_

    @on(Button.Pressed, "#gdon")
    def _gd_on(self) -> None:
        self.app.api.drive_connect()
        self._paint_drive()

    @on(Button.Pressed, "#gdcancel")
    def _gd_cancel(self) -> None:
        self.app.api.drive_cancel()

    @on(Button.Pressed, "#gdoff")
    def _gd_off(self) -> None:
        self.app.api.drive_disconnect()
        self._paint_drive()

    def _paint_github(self) -> None:
        lang, st = L(self.app), self.app.api.github_status()
        ph = st["phase"]
        if ph == "ready":
            info = t("Connected as @{account}", lang, account=st["account"] or "?") + "\n" + t("Choose repositories", lang) + ": " + st["install_url"]
        elif ph == "waiting":
            info = t("Type this code on GitHub:", lang) + f" {st['code']}  →  {st['url']}"
        elif not st["configured"]:
            info = t("The GitHub connector isn't set up in this version yet.", lang)
        else:
            info = t("Lets the assistant push files from the chat's folder to the repositories you choose, after you confirm each push. It can't delete repositories or change their settings.", lang)
        errs = {"signed_out": "GitHub was disconnected. Connect it again.", "expired": "The code expired. Press Connect again."}
        if st["error"] and st["error"] != "not_configured":
            info += "\n" + t(errs.get(st["error"], st["error"]), lang)
        self.query_one("#ghinfo", Static).update("🐙 GitHub — " + info)
        for bid, on_ in (("ghon", ph == "off" and st["configured"]), ("ghcancel", ph == "waiting"), ("ghoff", ph == "ready")):
            self.query_one(f"#{bid}", Button).display = on_

    @on(Button.Pressed, "#ghon")
    def _gh_on(self) -> None:
        self.app.api.github_connect()
        self._paint_github()

    @on(Button.Pressed, "#ghcancel")
    def _gh_cancel(self) -> None:
        self.app.api.github_cancel()
        self._paint_github()

    @on(Button.Pressed, "#ghoff")
    def _gh_off(self) -> None:
        self.app.api.github_disconnect()
        self._paint_github()

    def _paint_mcp(self) -> None:
        """Settings → MCP servers: on/off (after the risk question), the servers, add one by command or address."""
        lang, st = L(self.app), self.app.api.mcp_status()
        self.query_one("#mcptoggle", Button).label = t("Turn off" if st["enabled"] else "Use MCP servers", lang)
        self.query_one("#mcpaddrow").display = st["enabled"]
        box = self.query_one("#mcplist", Vertical)
        box.remove_children()
        box.display = st["enabled"]
        for s in st["servers"]:
            state = (t("Off", lang) if not s["on"] else t("{n} tools", lang, n=len(s["tools"])) if s["state"] == "ready"
                     else t("Didn't start: {error}", lang, error=s["error"]) if s["state"] == "error" else t("Starting…", lang))
            pin = ("  ⚠ " + t("No version fixed: each start may run newer code that nobody checked. Add @version to the package to fix it.", lang)
                   if s.get("unpinned") else "")
            row = [Label(f"🧩 {t(s['name'], lang) if s.get('preset') else s['name']}  ({state})  {s['where'][:60]}{pin}", markup=False)]
            if s.get("newer"):
                row.append(Button(t("Update to {v}", lang, v=s["newer"]), id=f"mcpnew-{s['id']}"))
            box.mount(Horizontal(*row, Button(t("Pause" if s["on"] else "Resume", lang), id=f"mcpon-{s['id']}-{0 if s['on'] else 1}"),
                                 Button(t("Remove", lang), id=f"mcpdel-{s['id']}"), classes="listrow"))
        if st["enabled"] and not st["servers"]:
            box.mount(Static(t("No servers yet.", lang), classes="muted"))
        pre = self.query_one("#mcppresets", Vertical)
        pre.remove_children()
        pre.display = st["enabled"]
        if st["enabled"]:
            pre.mount(Static(t("Ready-made servers", lang) + " — " + t("checked, with the version fixed: their code doesn't change until a Lanterna update", lang)
                             + (" " + t("For a folder one, type the folder in the box below first.", lang)), classes="muted"))
            for p in self.app.api.mcp_presets()["presets"]:
                need = (t("Needs {name} {v} or newer", lang, name=p["needs"], v=p["node"]) if p["missing"] == "node-old"
                        else t("Needs {name}", lang, name=p["needs"]) + f" ({p['link']})")
                text = f"{p['icon']} {t(p['name'], lang)} · {t('Version {v}', lang, v=p['version'])} — {t(p['about'], lang)}"
                tail = ([Label("✓ " + t("Added", lang))] if p["added"] else [Label(need, classes="muted")] if p["missing"]
                        else [Button(t("Add", lang), id=f"mcppre-{p['id']}")])
                pre.mount(Horizontal(Label(text, markup=False), *tail, classes="listrow"))
        if any(s["on"] and s["state"] == "starting" for s in st["servers"]):
            self.set_timer(1.0, self._paint_mcp)

    def _mcp_preset(self, pid: str) -> None:
        lang = L(self.app)
        p = next((x for x in self.app.api.mcp_presets()["presets"] if x["id"] == pid), None)
        if p is None:
            return
        folder = ""
        if p["folder"]:
            folder = self.query_one("#mcpwhere", Input).value.strip().strip('"')
            chk = self.app.api.check_folder(folder) if folder else {"ok": False, "error": ""}
            if not chk.get("ok") or not chk.get("path"):
                self.app.notify(t({"not_found": "There is no such folder.", "too_broad": "Choose a smaller folder: not a whole disk, your whole home folder or a system folder."}
                                  .get(chk.get("error"), "For a folder one, type the folder in the box below first."), lang), severity="warning")
                return
            folder = chk["path"]
        ask = (t("Lanterna will start this program with your rights each time it opens:", lang) + "\n" + p["command"].replace("<folder>", folder)
               + "\n" + t("Add it only if you trust where it comes from.", lang))

        def done(yes: bool) -> None:
            if not yes:
                return
            r = self.app.api.mcp_add_preset(pid, folder)
            if not r.get("ok"):
                self.app.notify(t(r.get("error", ""), lang), severity="warning")
                return
            self.query_one("#mcpwhere", Input).value = ""
            self.app.notify(t("Added. The first start can take a minute: it downloads the server.", lang))
            self._paint_mcp()
        self.app.push_screen(ConfirmScreen(ask, t("Add", lang)), done)

    def _mcp_toggle(self) -> None:
        lang = L(self.app)
        if self.app.api.mcp_status()["enabled"]:
            self.app.api.mcp_enable(False)
            self._paint_mcp()
            return

        def done(yes: bool) -> None:
            if yes:
                self.app.api.mcp_enable(True)
                self._paint_mcp()
        self.app.push_screen(ConfirmScreen(t("MCP servers are made by other people. A program server runs with your rights (files, internet); what a tool is asked goes to that server; a server can send text that tries to trick the assistant. Lanterna asks before every call. Turn on?", lang), t("Turn on", lang)), done)

    def _mcp_add(self) -> None:
        lang = L(self.app)
        where = self.query_one("#mcpwhere", Input).value.strip()
        if not where:
            return
        kind = "http" if where.lower().startswith(("http://", "https://")) else "stdio"
        ask = t("Lanterna will send tool requests to this address:" if kind == "http" else "Lanterna will start this program with your rights each time it opens:", lang) + f"\n{where}\n" + t("Add it only if you trust where it comes from.", lang)

        def done(yes: bool) -> None:
            if not yes:
                return
            r = self.app.api.mcp_add({"name": self.query_one("#mcpname", Input).value.strip(), "kind": kind, "where": where})
            if not r.get("ok"):
                self.app.notify(t(r.get("error", ""), lang), severity="warning")
                return
            self.query_one("#mcpwhere", Input).value = ""
            self.query_one("#mcpname", Input).value = ""
            self._paint_mcp()
        self.app.push_screen(ConfirmScreen(ask, t("Add", lang)), done)

    def _paint_backup(self) -> None:
        """Settings → Backups: on or off, the folder, the last one."""
        import datetime as dt
        lang, s = L(self.app), self.app.api.backup_status()
        text = (t("Weekly backups are on.", lang) + (" " + t("Last one: {when}", lang, when=dt.datetime.fromtimestamp(s["last"]).strftime("%Y-%m-%d %H:%M")) if s["last"] else "")
                if s["on"] else t("Set a password to turn on weekly backups. Lanterna keeps only a key made from it, in the Windows secure store, like your API keys. If you forget the password, the backups can't be opened.", lang))
        self.query_one("#bkinfo", Static).update(text + "\n" + t("Folder", lang) + ": " + s["folder"])
        self.query_one("#bkset", Button).label = t("Change password", lang) if s["on"] else t("Turn on", lang)
        self.query_one("#bknow", Button).display = s["on"]
        self.query_one("#bkoff", Button).display = s["on"]

    def _backup_button(self, bid: str) -> None:
        import base64
        lang = L(self.app)
        errs = {"password": "The password is wrong.", "format": "This file isn't a Lanterna backup, or it is damaged.",
                "folder": "Lanterna can't write to this folder. Choose another one.", "no_key": "Set a backup password first."}
        if bid == "bkset":
            a, b = self.query_one("#bkpw", Input), self.query_one("#bkpw2", Input)
            if len(a.value) < 8:
                self.app.notify(t("The password needs at least {n} characters.", lang, n=8), severity="warning")
                return
            if a.value != b.value:
                self.app.notify(t("The two passwords are different.", lang), severity="warning")
                return
            r = self.app.api.backup_set_password(a.value)
            a.value = b.value = ""
        elif bid == "bknow":
            r = self.app.api.backup_now()
        elif bid == "bkoff":
            r = self.app.api.backup_off()
        else:                                                  # bkrestore
            box, pw = self.query_one("#bkfile", Input), self.query_one("#bkfilepw", Input)
            p = Path(box.value.strip().strip('"')).expanduser()
            if not p.is_file():
                self.app.notify(t("There is no such file.", lang), severity="warning")
                return
            r = self.app.api.backup_restore(p.name, base64.b64encode(p.read_bytes()).decode(), pw.value)
            pw.value = ""
            if r.get("ok"):
                n = sum(r[k] for k in ("chats", "messages", "facts", "reminders", "tasks"))
                self.app.notify(t("Restored: {c} chats, {m} messages, {f} memory facts, {r} reminders, {k} regular tasks.", lang,
                                  c=r["chats"], m=r["messages"], f=r["facts"], r=r["reminders"], k=r["tasks"]) if n
                                else t("Nothing to restore: everything in this backup is already here.", lang), timeout=10)
        if not r.get("ok"):
            self.app.notify(t(errs.get(r.get("error"), "Something went wrong: {e}"), lang, e=r.get("error", "")), severity="error")
        elif r.get("name"):
            self.app.notify(t("Backup saved: {name}", lang, name=r["name"]), timeout=6)
        self._paint_backup()

    def _paint_tts(self) -> None:
        """Settings → Reading aloud: Piper's download, or that it is ready."""
        lang, v = L(self.app), self.app.api.tts_status()
        info, get = self.query_one("#ttsinfo", Static), self.query_one("#ttsget", Button)
        P = v["piper"]
        get.display = False
        if v["engine"] == "system":
            info.update(t("The voices already on your computer. Nothing to download, works offline.", lang))
        elif v["engine"] != "piper":
            info.update("")
        elif P["engine"] and P["voice"]:
            info.update(t("Ready. Everything is on this computer.", lang))
        elif P["phase"] == "downloading":
            info.update(t("Downloading… {done} of {total} MB", lang, done=round(P["done"] / 1e6), total=round(P["total"] / 1e6)))
            self.set_timer(1.0, self._paint_tts)
        elif not P["platform_ok"]:
            info.update(t("Piper has no ready download for this system.", lang))
        else:
            mb = (0 if P["engine"] else P["engine_mb"]) + (0 if P["voice"] else P["voice_mb"])
            info.update(t("A separate free program with more natural voices, offline after a one-time download from its own page. It has its own license (GPL), so it is not part of Lanterna.", lang)
                        + ("\n" + t("The download didn't work. Check the internet and try again.", lang) if P["phase"] == "error" else ""))
            get.label = t("Download ({mb} MB)", lang, mb=mb)
            get.display = True

    def _paint_voice(self) -> None:
        """Settings → Voice input: what the local engine needs, or that it is ready / downloading."""
        lang, v = L(self.app), self.app.api.voice_status()
        info, get = self.query_one("#voiceinfo", Static), self.query_one("#voiceget", Button)
        loc = v["local"]
        get.display = False
        if v["engine"] == "groq":
            info.update(t("Fast and accurate. Your recording goes to Groq to be turned into text. Needs the Groq key.", lang))
        elif v["engine"] != "local":
            info.update("")
        elif loc["engine"] and loc["model"]:
            info.update(t("Ready. Everything is on this computer.", lang))
        elif loc.get("phase") == "downloading":
            info.update(t("Downloading… {done} of {total} MB", lang, done=round(loc["done"] / 1e6), total=round(loc["total"] / 1e6)))
            self.set_timer(1.0, self._paint_voice)
        elif not loc["platform_ok"] and not loc["engine"]:
            info.update(t("There is no ready speech engine for this system. Install whisper.cpp (the whisper-cli command) and Lanterna will use it.", lang))
        else:
            mb = (0 if loc["engine"] else v["engine_mb"]) + (0 if loc["model"] else next(m["mb"] for m in v["models"] if m["id"] == v["model"]))
            info.update(t("Nothing leaves your PC. A one-time download: the speech engine and a model. Slower on older computers.", lang) + ("\n" + t("The download didn't work. Check the internet and try again.", lang) if loc.get("phase") == "error" else ""))
            get.label = t("Download ({mb} MB)", lang, mb=mb)
            get.display = True

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
            again = {"day": "Every day", "weekday": "On weekdays", "week": "Every week", "month": "Every month"}
            rep = f"  🔁 {t(again[r['repeat']], lang)}" if r.get("repeat") in again else ""
            row.mount(Label(f"{r['when']}  {r['text']}{rep}", markup=False))
            row.mount(Button(t("Cancel", lang), id=f"rem-{r['id']}"))
        if not api.reminders():
            rems.mount(Static(t("No reminders. Say “remind me in 20 minutes…” in a chat.", lang), classes="muted"))
        tasks = self.query_one("#tasks", Vertical)
        tasks.remove_children()
        paused = t("paused", lang)
        for x in api.task_list():
            row = Horizontal(classes="listrow")
            tasks.mount(row)
            row.mount(Label(f"{x['when']}  {x['text']}" + (f"  ({paused})" if x["paused"] else ""), markup=False))
            row.mount(Button(t("Resume" if x["paused"] else "Pause", lang), id=f"taskpause-{x['id']}-{0 if x['paused'] else 1}"))
            row.mount(Button(t("Remove", lang), id=f"taskdel-{x['id']}"))
        if not api.task_list():
            tasks.mount(Static(t("No regular tasks. Say “every morning at 8 tell me the weather” in a chat, or add one here.", lang), classes="muted"))

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
            if p.get("note"):                                # what to know before signing up, under the row
                box.mount(Static(t(p["note"], lang), classes="muted", markup=False))

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
        elif bid == "morningsave":
            self.app.api.save_settings({"morning_at": self.query_one("#morningat", Input).value,
                                        "morning_city": self.query_one("#morningcity", Input).value})
            self.query_one("#morningat", Input).value = self.app.api.settings.morning_at
            self.app.notify(t("Saved", L(self.app)), timeout=3)
        elif bid in ("bkset", "bknow", "bkoff", "bkrestore"):
            self._backup_button(bid)
        elif bid == "instrsave":
            self.app.api.save_settings({"instructions": self.query_one("#instructions", TextArea).text})
            self.app.notify(t("Saved", L(self.app)), timeout=3)
        elif bid == "morningshow":
            self.app.notify(self.app.api.morning_preview(), title="☀️ " + t("Morning summary", L(self.app)),
                            timeout=20, markup=False)
        elif bid.startswith("rem-"):
            self.app.api.cancel_reminder(int(bid[4:]))
            self._fill_memory()
        elif bid.startswith("voice-"):
            self.app.api.save_settings({"voice": bid[6:]})
            self.dismiss("reopen")
        elif bid == "voiceget":
            self.app.api.voice_setup()
            self._paint_voice()
        elif bid.startswith("tts-"):
            self.app.api.save_settings({"tts": bid[4:]})
            self.dismiss("reopen")
        elif bid == "ttsget":
            self.app.api.tts_setup()
            self._paint_tts()
        elif bid == "mcptoggle":
            self._mcp_toggle()
        elif bid == "mcpadd":
            self._mcp_add()
        elif bid.startswith("mcpdel-"):
            self.app.api.mcp_remove(bid[7:])
            self._paint_mcp()
        elif bid.startswith("mcppre-"):
            self._mcp_preset(bid[7:])
        elif bid.startswith("mcpnew-"):
            self.app.api.mcp_update_preset(bid[7:])
            self._paint_mcp()
        elif bid.startswith("mcpon-"):
            sid, on = bid[6:].rsplit("-", 1)
            self.app.api.mcp_update(sid, {"on": on == "1"})
            self._paint_mcp()
        elif bid.startswith("taskdel-"):
            self.app.api.task_delete(int(bid[8:]))
            self._fill_memory()
        elif bid.startswith("taskpause-"):
            _, num, paused = bid.split("-")
            self.app.api.task_pause(int(num), paused == "1")
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

    @on(Checkbox.Changed, "#ttsauto")
    def _tts_auto(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"tts_auto": ev.value})

    @on(Checkbox.Changed, "#morning")
    def _morning(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"morning": ev.value})

    @on(Checkbox.Changed, "#tidyweekly")
    def _tidy(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"tidy_weekly": ev.value})

    @on(Checkbox.Changed, "#spacehelp")
    def _space(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"space_help": ev.value})

    @on(Checkbox.Changed, "#pcaccess")
    def _pc_access(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"pc_access": ev.value})

    @on(Button.Pressed, "#backupall")
    def _backup_all(self) -> None:
        r = self.app.api.export_all()
        self.app.notify(t("Saved to {name}", L(self.app), name=r["path"]))

    @on(Checkbox.Changed, "#automemory")
    def _auto_memory(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"auto_memory": ev.value})

    @on(Checkbox.Changed, "#askfirst")
    def _ask_first(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"ask_first": ev.value})

    @on(Checkbox.Changed, "#compactchats")
    def _compact_chats(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"compact_chats": ev.value})

    @on(Checkbox.Changed, "#followups")
    def _follow_ups(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"follow_ups": ev.value})

    @on(Checkbox.Changed, "#aititles")
    def _ai_titles(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"ai_titles": ev.value})

    @on(Checkbox.Changed, "#updcheck")
    def _update_check(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"update_check": ev.value})

    @on(Checkbox.Changed, "#autocloud")
    def _auto_cloud(self, ev: Checkbox.Changed) -> None:
        self.app.api.save_settings({"auto_cloud": ev.value})

    def action_close(self) -> None:
        self.dismiss("")


# ---------------------------------------------------------------------------------------------- onboarding
class SyncBox(Vertical):
    """Google sign-in and sync: used in Settings and as the first step of the setup."""

    DEFAULT_CSS = "SyncBox { height: auto; }"

    def __init__(self, first: bool = False):
        super().__init__()
        self.first = first

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        yield Static("", id="syncinfo", classes="muted")
        yield Static("", id="syncerr")
        with Horizontal(classes="keyrow", id="syncpwrow"):
            yield Input(placeholder=t("Sync password", lang), password=True, id="syncpw")
            yield Button(t("Continue", lang), id="syncok", variant="primary")
        with Horizontal(classes="row", id="syncbtns"):
            yield Button(t("Sign in with Google", lang), id="syncin", variant="primary")
            yield Button(t("Cancel", lang), id="synccancel")
            yield Button(t("Sync now", lang), id="syncnow")
            yield Button(t("Sync without a password", lang), id="syncopen")
            yield Button(t("Forgot your password? Start over", lang), id="syncreset")
            yield Button(t("Sign out", lang), id="syncout")
            yield Button(t("Sign out and delete the copy in Google Drive", lang), id="syncdel", variant="error")

    def on_mount(self) -> None:
        self._sync_working = False
        self._paint_sync()
        self.set_interval(1.0, self._paint_sync)

    def _paint_sync(self) -> None:
        lang, st = L(self.app), self.app.api.sync_status()
        ph = "syncing" if self._sync_working else st["phase"]
        errs = {"password": "Wrong password.", "short": "At least 8 characters.",
                "changed": "The sync password was changed on another device. Enter the new one.",
                "gone": "The copy in Google Drive was deleted on another device. Enter the new password from that device, or set sync up again here.",
                "has_password": "The copy in Google Drive has a password. Enter it, or start over if you forgot it.",
                "signed_out": "You were signed out. Sign in again to keep syncing.",
                "scope": "Google didn't give Lanterna the permission it needs. Sign in again and leave the box for Lanterna's own folder ticked."}
        who = t("Signed in as {account}", lang, account=st["account"]) if st["account"] else t("Signed in with Google", lang)
        if ph == "off":
            info = ("" if self.first else t("Sign in with Google to see your chats on all your devices.", lang) + " ") + t(
                "Lanterna uses only a hidden folder of its own in your Google Drive. You choose next: a sync password only you know, or just your Google account.", lang)
        elif ph == "waiting":
            info = t("Finish signing in in your browser…", lang)
        elif ph == "password":
            info = who + "\n" + (t("Enter the sync password you chose on your other device.", lang) if st["cloud"] else
                                  t("Choose a sync password (at least 8 characters). You will need it on your other devices.", lang)
                                  + " " + t("If you forget it, the chats on your devices stay, but the copy in Google Drive can't be opened.", lang)
                                  + "\n" + t("Just your Google account: other devices only need to sign in. Anyone who gets into that account could read the chats, so API keys aren't synced this way: you add them on each device.", lang))
        elif ph == "syncing":
            info = who + "\n" + t("Syncing…", lang)
        else:
            when = time.strftime("%H:%M", time.localtime(st["last"])) if st["last"] else ""
            info = who + ("\n" + t("Last synced at {time}", lang, time=when) if when else "") + (
                "\n" + t("Without a password: API keys stay on each device.", lang) if st.get("no_password") else "")
        self.query_one("#syncinfo", Static).update(info)
        e = st["error"]
        self.query_one("#syncerr", Static).update(
            "" if not e else t(errs[e], lang) if e in errs else t("Couldn't sync: {error}", lang, error=e))
        self.query_one("#syncpwrow").display = ph == "password"
        show = {"syncin": ph == "off", "synccancel": ph == "waiting", "syncnow": ph in ("ready", "error"),
                "syncopen": ph == "password" and not st["cloud"], "syncreset": ph == "password" and bool(st["cloud"]),
                "syncout": ph in ("password", "ready", "error"), "syncdel": ph in ("ready", "error")}
        for bid, on in show.items():
            self.query_one(f"#{bid}", Button).display = on

    @on(Button.Pressed, "#syncin")
    def _sync_in(self) -> None:
        self.app.api.sync_sign_in()
        self._paint_sync()

    @on(Button.Pressed, "#synccancel")
    def _sync_cancel(self) -> None:
        self.app.api.sync_cancel()

    @on(Button.Pressed, "#syncok")
    @on(Input.Submitted, "#syncpw")
    def _sync_pw(self) -> None:
        pw = self.query_one("#syncpw", Input).value
        self.query_one("#syncpw", Input).value = ""
        self._sync_job(lambda: self.app.api.sync_password(pw))

    @on(Button.Pressed, "#syncopen")
    def _sync_open(self) -> None:
        self._sync_job(self.app.api.sync_no_password)

    @on(Button.Pressed, "#syncreset")
    def _sync_reset(self, ev: Button.Pressed) -> None:
        if not getattr(self, "_reset_armed", False):        # second press confirms
            self._reset_armed = True
            ev.button.label = t("Delete the copy in Google Drive and set sync up again? The chats on your devices stay and go into the new copy. Other devices will then need the new password, or nothing if you sync without one.", L(self.app))
            return
        self._reset_armed = False
        ev.button.label = t("Forgot your password? Start over", L(self.app))
        self._sync_job(self.app.api.sync_start_over)

    @on(Button.Pressed, "#syncnow")
    def _sync_now(self) -> None:
        self._sync_job(self.app.api.sync_now)

    @on(Button.Pressed, "#syncout")
    def _sync_out(self) -> None:
        self.app.api.sync_sign_out(False)
        self._paint_sync()

    @on(Button.Pressed, "#syncdel")
    def _sync_del(self, ev: Button.Pressed) -> None:
        if not getattr(self, "_del_armed", False):          # second press confirms
            self._del_armed = True
            ev.button.label = t("Delete the encrypted copy of your chats from Google Drive? Chats on this device stay.", L(self.app))
            return
        self._del_armed = False
        self._sync_job(lambda: self.app.api.sync_sign_out(True))

    def _sync_job(self, fn) -> None:
        self._sync_working = True
        self._paint_sync()

        def run():
            try:
                fn()
            finally:
                self._sync_working = False
                self.app.call_from_thread(self._paint_sync)
        threading.Thread(target=run, daemon=True).start()



class GoogleScreen(Screen):
    """First start: sign in with Google so chats, settings and keys come from the other devices (can be skipped)."""

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Center(id="onboard"):
            with Vertical(classes="center-col"):
                yield Label(f"{LOGO}  Lanterna", classes="title")
                yield Label(t("Sign in with Google", lang), classes="sub")
                yield Static(t("Your chats, settings and API keys on all your devices. The same sign-in also connects Google Drive.", lang)
                             + "\n" + t("Already use Lanterna on another device? Sign in and everything comes over by itself.", lang),
                             classes="muted")
                yield SyncBox(first=True)
                with Horizontal(classes="row"):
                    yield Button(t("Continue without an account", lang), id="noacct")
                yield Static(t("You can sign in later in Settings → Account and sync.", lang), classes="muted")

    def on_mount(self) -> None:
        self._done = False
        self.set_interval(1.0, self._check)

    def _check(self) -> None:
        st = self.app.api.sync_status()
        if st["phase"] == "ready" and st["last"]:
            self._next()

    @on(Button.Pressed, "#noacct")
    def _skip(self) -> None:
        self._next()

    def _next(self) -> None:
        if self._done:
            return
        self._done = True
        api = self.app.api
        api.save_settings({"sync_asked": True})
        st = api.state()
        if any(p["has_key"] for p in st["providers"]) or api.settings.mode == "local":
            api.save_settings({"onboarded": True})
            self.app.switch_screen(make_chat_screen(L(self.app)))
        else:
            self.app.switch_screen(OnboardScreen(3 if api.settings.onboarded else 1))


class OnboardScreen(Screen):
    step = reactive(0, recompose=True)

    def __init__(self, step: int = 0):
        super().__init__()
        self.set_reactive(OnboardScreen.step, step)

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Center(id="onboard"):
            with Vertical(classes="center-col"):
                yield Label(f"{LOGO}  Lanterna", classes="title")
                if self.step == 0:
                    yield Label("Choose your language · Вибери мову · Scegli la lingua", classes="sub")
                    for row in lang_rows():
                        with Horizontal(classes="row"):
                            for code, name in row:
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
            if not self.app.api.settings.sync_asked and self.app.api.sync_status()["phase"] == "off":
                self.app.switch_screen(GoogleScreen())
            else:
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
class ChoiceScreen(ModalScreen[str]):
    """A short list of things to do; returns the chosen id ("" when closed)."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, title: str, choices: list[tuple[str, str]], text: str = ""):
        super().__init__()
        self.title_text, self.choices, self.text = title, choices, text

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="h", markup=False)
            if self.text:
                yield Static(self.text, classes="muted", markup=False)
            yield OptionList(*(Option(label, id=cid) for cid, label in self.choices), id="choices")
            with Horizontal(classes="row"):
                yield Button(t("Cancel", L(self.app)), id="no")

    def on_mount(self) -> None:
        self.query_one("#choices", OptionList).focus()

    @on(OptionList.OptionSelected, "#choices")
    def _picked(self, ev: OptionList.OptionSelected) -> None:
        self.dismiss(ev.option.id or "")

    @on(Button.Pressed, "#no")
    def action_close(self) -> None:
        self.dismiss("")


class ValuesScreen(ModalScreen[dict]):
    """Asks for the values a connector needs (a key, a token); they go only to the system's secure vault."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, title: str, fields: list[dict]):
        super().__init__()
        self.title_text, self.fields = title, fields

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="h", markup=False)
            for i, f in enumerate(self.fields):
                yield Label(t("Key or token", lang) if f["name"] == "token" else f["name"], markup=False)
                if f.get("about"):
                    yield Static(f["about"], classes="muted", markup=False)
                yield Input(password=bool(f.get("secret", True)), id=f"val{i}")
            yield Static(t("Kept in the system's secure store, not in files.", lang), classes="muted")
            with Horizontal(classes="row"):
                yield Button(t("Add", lang), id="ok", variant="primary")
                yield Button(t("Cancel", lang), id="no")

    @on(Button.Pressed, "#ok")
    @on(Input.Submitted)
    def _ok(self) -> None:
        vals = {f["name"]: self.query_one(f"#val{i}", Input).value.strip() for i, f in enumerate(self.fields)}
        if all(vals.values()):
            self.dismiss(vals)

    @on(Button.Pressed, "#no")
    def action_close(self) -> None:
        self.dismiss({})


MAIL_ERRS = {"auth": "The mail service didn't accept the address or the app password. Check that it is an app password, not your usual one.",
             "network": "Couldn't reach the mail server. Check the server name and your internet.",
             "address": "Check the email address.", "password": "Paste the app password.",
             "server": "Check the server names.", "vault": "The system's secure store isn't available."}


class MailScreen(ModalScreen[bool]):
    """Mail over IMAP with an app password (Gmail, ukr.net, iCloud, Yahoo, Zoho or any other)."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def compose(self) -> ComposeResult:
        lang, st = L(self.app), self.app.api.mail_status()
        self.presets = {p["id"]: p for p in st["presets"]}
        with VerticalScroll(classes="dialog"):
            yield Label(t("Connect mail", lang), classes="h")
            yield Static(t("Lanterna connects to your mailbox with an app password: a separate password your mail service makes just for Lanterna. You can revoke it there any time. It is kept only in the system's secure store.", lang), classes="muted")
            yield Label(t("Mail service", lang))
            yield Select([(t(p["name"], lang), pid) for pid, p in self.presets.items()], value=st.get("preset") or "gmail",
                         allow_blank=False, id="mlpreset")
            yield Label(t("Email address", lang))
            yield Input(st.get("address", ""), placeholder="you@example.com", id="mladdr")
            yield Label(t("App password", lang))
            yield Input(password=True, id="mlpw")
            yield Static("", id="mlhow", classes="muted", markup=False)
            with Vertical(id="mlservers"):
                yield Label(t("Servers", lang))
                with Horizontal(classes="keyrow"):
                    yield Input(placeholder="imap.example.com", id="mlimap")
                    yield Input("993", id="mlimapport")
                with Horizontal(classes="keyrow"):
                    yield Input(placeholder="smtp.example.com", id="mlsmtp")
                    yield Input("465", id="mlsmtpport")
            yield Static(t("Lanterna reads without marking letters as read. Sorting, drafts and sending happen only after you confirm a card.", lang), classes="muted")
            yield Static("", id="mlerr", classes="bad", markup=False)
            with Horizontal(classes="row"):
                yield Button(t("Connect", lang), id="mlok", variant="primary")
                yield Button(t("Cancel", lang), id="no")

    def on_mount(self) -> None:
        self._paint()
        self.query_one("#mladdr", Input).focus()

    @on(Select.Changed, "#mlpreset")
    def _paint(self) -> None:
        lang = L(self.app)
        p = self.presets.get(self.query_one("#mlpreset", Select).value) or {}
        self.query_one("#mlhow", Static).update(t(p.get("how", ""), lang) + (f"\n{p['help']}" if p.get("help") else ""))
        self.query_one("#mlservers").display = p.get("id") == "other"

    @on(Input.Submitted)
    def _enter(self, ev: Input.Submitted) -> None:
        if ev.input.id == "mladdr" or (ev.input.id == "mlpw" and self.query_one("#mlservers").display):
            self.focus_next()                                 # Enter goes on to the next field
        elif ev.input.id in ("mlpw", "mlsmtpport"):
            self._go()
        else:
            self.focus_next()

    @on(Button.Pressed, "#mlok")
    def _go(self) -> None:
        q = lambda i: self.query_one(i, Input).value.strip()            # noqa: E731
        form = {"preset": self.query_one("#mlpreset", Select).value, "address": q("#mladdr"),
                "password": self.query_one("#mlpw", Input).value, "imap": q("#mlimap"), "imap_port": q("#mlimapport"),
                "smtp": q("#mlsmtp"), "smtp_port": q("#mlsmtpport")}
        self.query_one("#mlok", Button).disabled = True
        self.query_one("#mlerr", Static).update(t("Connecting…", L(self.app)))
        self._connect(form)

    @work(thread=True, exclusive=True, group="mail")
    def _connect(self, form: dict) -> None:
        r = self.app.api.mail_connect(form)
        self.app.call_from_thread(self._done, r)

    def _done(self, r: dict) -> None:
        lang = L(self.app)
        self.query_one("#mlok", Button).disabled = False
        if r.get("ok"):
            self.app.notify(t("Mail connected: {a}", lang, a=r.get("address", "")), timeout=6)
            self.dismiss(True)
            return
        self.query_one("#mlerr", Static).update(
            t(MAIL_ERRS[r["error"]], lang) if r.get("error") in MAIL_ERRS else t("Couldn't do it: {error}", lang, error=r.get("message") or r.get("error")))

    @on(Button.Pressed, "#no")
    def action_close(self) -> None:
        self.dismiss(False)


class ConnectorsScreen(ModalScreen[None]):
    """Connectors, like the window: Yours (what is connected) and Browse (ready-made ones + the public catalog)."""

    BINDINGS = [Binding("escape", "close", show=False)]

    def __init__(self, tab: str = "browse"):
        super().__init__()
        self.tab = tab
        self.reg: list[dict] = []
        self.shown: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        lang = L(self.app)
        with Vertical(classes="dialog bigdialog"):
            with Horizontal(classes="dlghead"):
                yield Label("🔌 " + t("Connectors", lang), classes="dlgtitle")
                yield Label(t("Enter: choose · Tab: next · Esc: close", lang), classes="muted dlgkeys")
            with TabbedContent(initial=f"cn-{self.tab}", id="cntabs"):
                with TabPane(t("Yours", lang), id="cn-yours"):
                    yield OptionList(id="cn-mine")
                    yield Static("", id="cn-mineinfo", classes="muted", markup=False)
                with TabPane(t("Browse", lang), id="cn-browse"):
                    with Horizontal(classes="keyrow"):
                        yield Input(placeholder="🔎 " + t("Search", lang), id="cn-q")
                        yield Select([(t(v, lang), k) for k, v in self.app.api.connectors()["categories"].items()],
                                     prompt=t("All categories", lang), id="cn-cat")
                    yield OptionList(id="cn-list")
                    yield Static("", id="cn-about", classes="muted", markup=False)
            with Horizontal(classes="row"):
                yield Button(t("Close", lang), id="close", variant="primary")

    def on_mount(self) -> None:
        self._load()
        self.set_interval(2.0, self._tick)
        self.query_one("#cn-q" if self.tab == "browse" else "#cn-mine").focus()

    def _load(self) -> None:
        self.C = self.app.api.connectors()
        self._paint_browse()
        self._paint_mine()

    def _gone(self) -> bool:
        """The window is closing: a late answer (a search, a sign-in) has nothing to paint."""
        return not self.is_attached or not self.query("#cn-cat") or not self.query("#cn-q")

    def _tick(self) -> None:                                # a browser sign-in finishing, a server starting
        if self._gone():
            return
        st = self.app.api.mcp_status()
        sig = [(s["id"], s["state"], s["signing"], s["sign_error"], len(s["tools"])) for s in st["servers"]]
        if sig != getattr(self, "_sig", None):
            self._sig = sig
            self._load()

    # -- Browse
    def _paint_browse(self) -> None:
        if self._gone():
            return
        lang = L(self.app)
        q = self.query_one("#cn-q", Input).value.strip().lower()
        cat = self.query_one("#cn-cat", Select).value
        cat = cat if isinstance(cat, str) else ""             # nothing picked: Select.NULL
        words = q.split()
        items = [c for c in self.C["catalog"] if (not cat or c["cat"] == cat)
                 and all(w in " ".join([c["name"], c["by"], c["about"], t(c["about"], lang), c.get("why") or ""]).lower() for w in words)]
        items.sort(key=lambda c: c["auth"] == "closed")
        ol = self.query_one("#cn-list", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        self.shown = {}
        for c in items:
            mark = "✓" if c["added"] else "✕" if c["auth"] == "closed" else "+"
            name = t(c["name"], lang) if c["builtin"] else c["name"]
            self.shown[c["id"]] = c
            ol.add_option(Option(f"{mark} {name}  ·  {t(c['about'], lang) if c['about'] else t('Unavailable', lang)}", id=c["id"]))
        if self.reg:
            ol.add_option(None)
            for i, e in enumerate(self.reg):
                self.shown[f"reg{i}"] = e
                ol.add_option(Option(f"{'✓' if e.get('added') else '🌐'} {e['name']}  ·  {t('Made by {who}', lang, who=e['by'])}"
                                     + (f" · {t('through {host}', lang, host=e['through'])}" if e.get("through") else ""), id=f"reg{i}"))
        if not ol.option_count:
            ol.add_option(Option(t("No ready-made connector with these words.", lang), id="none", disabled=True))
        if keep is not None and keep < ol.option_count:
            ol.highlighted = keep
        elif items:                                           # the first one's description shows at once
            ol.highlighted = 0
        self._about()

    @on(Input.Changed, "#cn-q")
    def _typed(self) -> None:
        self.reg = []
        self._paint_browse()
        if getattr(self, "_q_timer", None):
            self._q_timer.stop()
        if len(self.query_one("#cn-q", Input).value.strip()) >= 2:
            self._q_timer = self.set_timer(0.6, self._search)

    @on(Select.Changed, "#cn-cat")
    def _cat(self) -> None:
        self._paint_browse()

    @on(Input.Submitted, "#cn-q")
    def _to_list(self) -> None:
        ol = self.query_one("#cn-list", OptionList)
        ol.focus()
        if ol.highlighted is None and ol.option_count:
            ol.highlighted = 0

    @work(thread=True, exclusive=True, group="registry")
    def _search(self) -> None:
        q = self.app.call_from_thread(lambda: "" if self._gone() else self.query_one("#cn-q", Input).value.strip())
        if not q:
            return
        r = self.app.api.connectors_search(q)
        self.app.call_from_thread(self._found, q, r)

    def _found(self, q: str, r: dict) -> None:
        if not self._gone() and q == self.query_one("#cn-q", Input).value.strip():
            self.reg = r.get("registry") or []
            self._paint_browse()

    @on(OptionList.OptionHighlighted, "#cn-list")
    def _about(self) -> None:
        lang, ol = L(self.app), self.query_one("#cn-list", OptionList)
        c = self.shown.get(ol.get_option_at_index(ol.highlighted).id) if ol.highlighted is not None else None
        if not c:
            self.query_one("#cn-about", Static).update("")
            return
        if c.get("registry"):
            text = (c.get("about") or "") + "\n" + t("Made by other people and not checked by Lanterna. Add only what you trust: what a tool is asked goes to its maker.", lang)
        elif c["auth"] == "closed":
            alt = next((x for x in self.C["catalog"] if x["id"] == c.get("instead")), None)
            text = t(c["why"], lang) + (f"\n{t('Use {name}', lang, name=t(alt['name'], lang) if alt['builtin'] else alt['name'])} → Enter" if alt else "")
        else:
            text = t(c["about"], lang) + "\n" + (t("Made by the service itself", lang) if c.get("official") else t("Made by {who}", lang, who=c["by"]))
        self.query_one("#cn-about", Static).update(text)

    @on(OptionList.OptionSelected, "#cn-list")
    def _picked(self, ev: OptionList.OptionSelected) -> None:
        c = self.shown.get(ev.option.id or "")
        if not c:
            return
        if c.get("registry"):
            return self._add_entry(c, {})
        if c["auth"] == "closed":
            alt = next((x for x in self.C["catalog"] if x["id"] == c.get("instead")), None)
            return self._open(alt) if alt else self.app.notify(t(c["why"], L(self.app)), timeout=8)
        self._open(c)

    def _open(self, c: dict) -> None:
        lang = L(self.app)
        if c["builtin"] == "mail":
            return self.app.push_screen(MailScreen(), lambda ok: self._load())
        if c["builtin"]:                                    # Google Drive, GitHub: in Settings
            self.dismiss()
            return self.app.screen.action_settings("pc") if hasattr(self.app.screen, "action_settings") else None
        if c["added"]:
            return self.app.notify(t("Added {name}.", lang, name=c["name"]), timeout=4)
        self._with_mcp(lambda: self._add(c))

    def _with_mcp(self, then) -> None:
        if self.app.api.mcp_status()["enabled"]:
            return then()

        def done(yes: bool) -> None:
            if yes:
                self.app.api.mcp_enable(True)
                then()
        lang = L(self.app)
        self.app.push_screen(ConfirmScreen(t("MCP servers are made by other people. A program server runs with your rights (files, internet); what a tool is asked goes to that server; a server can send text that tries to trick the assistant. Lanterna asks before every call. Turn on?", lang), t("Turn on", lang)), done)

    def _add(self, c: dict) -> None:
        lang, r = L(self.app), self.app.api.connector_add(c["id"])
        if not r.get("ok"):
            return self.app.notify(t("Couldn't do it: {error}", lang, error=r.get("error")), severity="error", timeout=8)
        self.app.notify(t("A sign-in page for {name} opened in your browser. Sign in there and come back.", lang, name=c["name"])
                        if c["auth"] == "oauth" else t("Added {name}.", lang, name=c["name"]), timeout=10)
        self._load()
        self.query_one("#cntabs", TabbedContent).active = "cn-yours"

    def _add_entry(self, e: dict, values: dict) -> None:
        if not values and not self.app.api.mcp_status()["enabled"]:
            return self._with_mcp(lambda: self._add_entry(e, values))
        self.app.notify(t("Connecting…", L(self.app)), timeout=3)
        self._entry_job(e, values)

    @work(thread=True, exclusive=True, group="entry")
    def _entry_job(self, e: dict, values: dict) -> None:
        r = self.app.api.connector_add_entry(e, values)
        self.app.call_from_thread(self._entry_done, e, values, r)

    def _entry_done(self, e: dict, values: dict, r: dict) -> None:
        lang = L(self.app)
        if r.get("ok"):
            self.app.notify(t("Added {name}.", lang, name=e["name"]), timeout=6)
            self.reg = [x for x in self.reg if x is not e]
            self._load()
            self.query_one("#cntabs", TabbedContent).active = "cn-yours"
            return
        need = ([{"name": "token", "secret": True, "about": t("This server wants a key or token. Make one on its website and paste it here.", lang)}]
                if r.get("error") == "token" else
                [x for x in e.get("env") or [] if x["name"] in (r.get("missing") or [])] if r.get("error") == "values" else [])
        if need:
            return self.app.push_screen(ValuesScreen(e["name"], need),
                                        lambda vals: self._add_entry(e, {**values, **vals}) if vals else None)
        self.app.notify(t("Couldn't do it: {error}", lang, error=r.get("error")), severity="error", timeout=8)

    # -- Yours
    def _paint_mine(self) -> None:
        lang, C = L(self.app), self.C
        ol = self.query_one("#cn-mine", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        self.mine: dict[str, dict] = {}
        mail = C["mail"]
        built = [("mail", "📬 " + t("Mail", lang), mail["address"] if mail["connected"] else t("Not connected", lang)),
                 ("gdrive", "📁 Google Drive", t("Connected", lang) if C["drive"].get("phase") == "ready" else t("Not connected", lang)),
                 ("github", "🐙 GitHub", t("Connected", lang) if C["github"].get("phase") == "ready" else t("Not connected", lang))]
        ol.add_option(Option(t("Built into Lanterna", lang), disabled=True))
        for bid, name, state in built:
            self.mine[bid] = {"builtin": bid}
            ol.add_option(Option(f"  {name}  ·  {state}", id=bid))
        servers = C["mcp"]["servers"]
        ol.add_option(None)
        ol.add_option(Option(t("Added by you", lang), disabled=True))
        for s in servers:
            self.mine[s["id"]] = s
            ol.add_option(Option(f"  🧩 {s['name']}  ·  {self._state(s)}", id=s["id"]))
        if not servers:
            ol.add_option(Option("  " + t("Nothing here yet. Find a connector in Browse and press +.", lang).replace("+", "Enter"), disabled=True))
        if keep is not None and keep < ol.option_count:
            ol.highlighted = keep
        self.query_one("#cn-mineinfo", Static).update(
            "" if C["mcp"]["enabled"] or not servers else t("MCP servers are turned off, so these connectors don't work now.", lang))

    def _state(self, s: dict) -> str:
        lang = L(self.app)
        if not s["on"]:
            return t("Off", lang)
        if s["sign_error"]:
            return t("Sign-in failed: {error}", lang, error=s["sign_error"])
        if s["signing"]:
            return t("Waiting for you to sign in in the browser…", lang)
        if s["state"] == "signin":
            return t("Sign in to use it", lang)
        if s["state"] == "ready":
            return t("Ready · {n} tools", lang, n=len(s["tools"]))
        if s["state"] == "error":
            return t("Didn't start: {error}", lang, error=s["error"])
        return t("Connecting…", lang)

    @on(OptionList.OptionSelected, "#cn-mine")
    def _mine_picked(self, ev: OptionList.OptionSelected) -> None:
        lang, x = L(self.app), self.mine.get(ev.option.id or "")
        if not x:
            return
        if x.get("builtin") == "mail":
            if not self.C["mail"]["connected"]:
                return self.app.push_screen(MailScreen(), lambda ok: self._load())

            def off(yes: bool) -> None:
                if yes:
                    self.app.api.mail_disconnect()
                    self._load()
            return self.app.push_screen(ConfirmScreen(t("Disconnect mail? The app password is removed from this computer.", lang), t("Disconnect", lang)), off)
        if x.get("builtin"):
            self.dismiss()
            return self.app.screen.action_settings("pc") if hasattr(self.app.screen, "action_settings") else None
        s = x
        acts = []
        if s["auth"] == "oauth":
            acts += [("cancel", t("Cancel", lang))] if s["signing"] else [("signin", t("Sign in", lang))]
            if s["state"] in ("ready", "error") and not s["signing"]:
                acts.append(("signout", t("Sign out", lang)))
        acts += [("toggle", t("Pause" if s["on"] else "Resume", lang)), ("tools", t("Tools", lang)), ("remove", t("Remove", lang))]
        self.app.push_screen(ChoiceScreen(s["name"], acts, self._state(s)), lambda a: self._mine_act(s, a))

    def _mine_act(self, s: dict, act: str) -> None:
        lang, api = L(self.app), self.app.api
        if act == "signin":
            r = api.mcp_sign_in(s["id"])
            self.app.notify(t("A sign-in page for {name} opened in your browser. Sign in there and come back.", lang, name=s["name"])
                            if r.get("ok") else t("Couldn't do it: {error}", lang, error=r.get("error")), timeout=10)
        elif act == "cancel":
            api.mcp_sign_cancel(s["id"])
        elif act == "signout":
            api.mcp_sign_out(s["id"])
        elif act == "toggle":
            api.mcp_update(s["id"], {"on": not s["on"]})
        elif act == "tools":
            names = "\n".join("• " + x["name"] for x in s["tools"]) or t("No tools yet.", lang)
            return self.app.push_screen(ChoiceScreen(s["name"] + " · " + t("Tools", lang), [], names))
        elif act == "remove":
            def rm(yes: bool) -> None:
                if yes:
                    api.mcp_remove(s["id"])
                    self._load()
            return self.app.push_screen(ConfirmScreen(t("Remove {name}? Its sign-in is removed from this computer too.", lang, name=s["name"]), t("Remove", lang)), rm)
        self._load()

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss()


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
                yield Input(placeholder="🔎 " + t("Search chats", lang), id="findchats")
                yield ListView(id="threads")
                with Vertical(id="sidefoot"):
                    yield Button("🔌 " + t("Connectors", lang), id="sb-conn", classes="sidebtn")
                    yield Button("⚙  " + t("Settings", lang), id="sb-set", classes="sidebtn")
                    yield Button("☰  " + t("All commands", lang), id="sb-menu", classes="sidebtn")
            with Vertical(id="main"):
                with Horizontal(id="topbar"):
                    yield Label(t("New chat", lang), id="chattitle")
                    yield Label("", id="model")
                yield VerticalScroll(id="log")
                yield Label("", id="attached")
                with Horizontal(id="autobar"):
                    yield Label("", id="autotext")
                    yield Button(t("Stop", lang), id="autostop", classes="sidebtn")
                yield Input(placeholder=t("Message Lanterna…", lang), id="composer")
        yield Footer(show_command_palette=False)

    @on(Button.Pressed, "#sb-conn")
    def _sb_conn(self) -> None:
        self.action_connectors()

    @on(Button.Pressed, "#sb-set")
    def _sb_set(self) -> None:
        self.action_settings()

    @on(Button.Pressed, "#sb-menu")
    def _sb_menu(self) -> None:
        self.app.action_command_palette()

    def on_mount(self) -> None:
        threads = self.app.api.threads()
        self._fill_threads(threads)
        if threads:
            self.open_thread(threads[0]["id"])
        else:
            self._welcome()
        self.query_one("#composer", Input).focus()
        self._load_model_label()
        if not getattr(self.app, "_update_asked", False):
            self.app._update_asked = True
            self._update_notice()
        self._sync_seen = self.app.api.sync_status()["last"]
        self.set_interval(10, self._watch_sync)
        self.set_interval(2, self._paint_auto)
        self._paint_auto()

    def _paint_auto(self) -> None:
        """"Lanterna acts on its own in this chat": a line over the message box with the time left and Stop."""
        tid = getattr(self, "tid", None)
        st = self.app.api.auto_status(tid) if tid and tid > 0 else {"on": False, "left": 0}
        bar = self.query_one("#autobar")
        bar.display = st["on"]
        if st["on"]:
            self.query_one("#autotext", Label).update("🤖 " + t("Lanterna acts on its own in this chat: {n} min left", L(self.app),
                                                               n=-(-st["left"] // 60)))

    @on(Button.Pressed, "#autostop")
    def _auto_stop(self) -> None:
        if getattr(self, "tid", None):
            self.app.api.auto_stop(self.tid)
        self._paint_auto()

    def _watch_sync(self) -> None:
        """A sync brought chats from another device: show them without a restart."""
        last = self.app.api.sync_status()["last"]
        if last == self._sync_seen or self._stream:
            return
        self._sync_seen = last
        self._fill_threads()
        if self.tid is not None and not self.query_one("#composer", Input).value:
            if len(self.app.api.messages(self.tid)) != len(self.query("#log .msg-user, #log .msg-bot")):
                self.open_thread(self.tid)

    @work(thread=True, exclusive=True, group="update")
    def _update_notice(self) -> None:
        res = self.app.api.update_notice()
        if res.get("newer"):
            self.app.call_from_thread(self._show_update_notice, res)

    def _show_update_notice(self, res: dict) -> None:
        if self.app.screen is self:                        # don't cover a dialog the user already opened
            self.app.push_screen(UpdateScreen(res))

    @work(thread=True, exclusive=True, group="model")
    def _load_model_label(self) -> None:
        res = self.app.api.models(False)
        self.app.call_from_thread(self._set_model, res.get("current") or "")

    def _set_model(self, label: str) -> None:
        self.query_one("#model", Label).update(label)

    # threads -----------------------------------------------------------------
    def _fill_threads(self, threads: list[dict] | None = None) -> None:
        q = self.query_one("#findchats", Input).value.strip()
        if len(q) >= 2:                                    # the search box: chats with these words
            threads = [{**x, "title": (x["title"] or t("New chat", L(self.app))) + ("\n  " + x["snippet"][:70] if x["snippet"] else "")}
                       for x in self.app.api.search_chats(q)] or [{"id": None, "title": t("Nothing found.", L(self.app))}]
        else:
            threads = self.app.api.threads() if threads is None else threads
        self.run_worker(self._refill_threads(threads), group="threads")

    @on(Input.Changed, "#findchats")
    def _find(self, ev: Input.Changed) -> None:
        self._fill_threads()

    async def _refill_threads(self, threads: list[dict]) -> None:
        # One refill at a time: overlapping refills used to show a chat twice in the list.
        if getattr(self, "_threads_lock", None) is None:
            self._threads_lock = asyncio.Lock()
        async with self._threads_lock:
            lv = self.query_one("#threads", ListView)
            await lv.clear()
            await lv.extend([ListItem(Label(("📌 " if th.get("pinned") else "") + (th["title"] or t("New chat", L(self.app))),
                                            markup=False), name=str(th["id"]) if th["id"] is not None else "")
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
        self._leave_private(tid)
        self.tid = tid
        log = self.query_one("#log", VerticalScroll)
        log.remove_children()
        th = next((x for x in self.app.api.threads() if x["id"] == tid), None)
        self.query_one("#chattitle", Label).update("🕶 " + t("Private chat", L(self.app)) if tid < 0
                                                   else (th or {}).get("title") or t("New chat", L(self.app)))
        msgs = self.app.api.messages(tid)
        if not msgs:
            self._welcome()
        for m in msgs:
            if m.get("after_summary"):
                log.mount(Static("↑ " + t("Older messages are summarized for the model", L(self.app)), classes="msg-note", markup=False))
            if m["role"] == "user":
                log.mount(Static(m["content"], classes="msg-user", markup=False))
            else:
                if m.get("second"):
                    log.mount(Static("👥 " + t("Second opinion", L(self.app)), classes="msg-note", markup=False))
                log.mount(Markdown(count_on(m["content"]), classes="msg-bot"))
                if m.get("sent"):
                    log.mount(sent_box(m["sent"], L(self.app)))
        for card in self.app.api.cards(tid):              # changes still waiting for Confirm
            log.mount(ActCard(card))
        log.scroll_end(animate=False)

    def _welcome(self) -> None:
        lang, name = L(self.app), self.app.api.settings.name
        text = t("Hi, {name}! Ask me anything.", lang, name=name) if name else t("Hi! Ask me anything.", lang)
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(text, classes="welcome", markup=False))
        ideas = (["Sort my Downloads", "Why is my computer slow?", "What's the weather tomorrow?",
                  "Remind me in 20 minutes to take a break", "Explain something simply", "Help me plan my week"]
                 if self.app.api.settings.pc_access else
                 ["What's the weather tomorrow?", "Remind me in 20 minutes to take a break", "Explain something simply",
                  "Help me plan my week", "Write a short message for me", "Give me an idea for today"])
        # built whole, then mounted: adding children to a box that isn't mounted yet fails on slow machines
        log.mount(Vertical(Label(t("Try one:", lang), classes="muted"),
                           *(Button(t(idea, lang), id=f"idea{i}", classes="idea") for i, idea in enumerate(ideas)),
                           classes="welcome sugg"))
        log.mount(Static(t("Enter sends · Ctrl+P: all commands · Ctrl+N: new chat · /file and a path: attach a file", lang),
                         classes="hint", markup=False))

    @on(Button.Pressed, ".idea")
    def _idea(self, ev: Button.Pressed) -> None:
        box = self.query_one("#composer", Input)          # one press sends it, like typing it and pressing Enter
        box.value = str(ev.button.label)
        box.post_message(Input.Submitted(box, box.value))

    def _leave_private(self, to: int | None) -> None:
        if self.tid is not None and self.tid < 0 and to != self.tid:
            self.app.api.forget_private(to if to is not None and to < 0 else 0)

    def action_private_chat(self) -> None:
        """F7: a private chat: only in memory, not saved or synced, memory and other chats not used."""
        if self._stream:
            return
        self.action_new_chat()
        self._private_next = True
        lang = L(self.app)
        self.query_one("#chattitle", Label).update("🕶 " + t("Private chat", lang))
        self.query_one("#log", VerticalScroll).mount(
            Static("🕶 " + t("It isn't saved, and memory and your other chats aren't used. It disappears when you leave it.", lang),
                   classes="msg-note", markup=False), before=0)

    def action_new_chat(self) -> None:
        if self._stream:
            return
        self._leave_private(None)
        self._private_next = False
        self.tid = None
        self.query_one("#log", VerticalScroll).remove_children()
        self.query_one("#chattitle", Label).update(t("New chat", L(self.app)))
        self.query_one("#threads", ListView).index = None
        self._welcome()
        self.query_one("#composer", Input).focus()

    @on(Button.Pressed, "#newchat")
    def _new_btn(self) -> None:
        self.action_new_chat()

    def action_retry(self) -> None:
        """Ctrl+R: answer the last question again (the old answer is replaced)."""
        if self.tid is None or self._stream:
            return
        res = self.app.api.send(self.tid, "", [], again=True)
        if not res.get("ok"):
            return
        self.open_thread(self.tid)
        self._watch(res["stream"])

    def action_next_role(self) -> None:
        """F6: the open chat's role goes round: none → Tutor → Translator → Proofreader → none."""
        from .roles import ROLES
        order = ["", *ROLES]
        lang = L(self.app)
        if self.tid is None:
            self._new_role = order[(order.index(getattr(self, "_new_role", "")) + 1) % len(order)]
            role = self._new_role
        else:
            role = order[(order.index(self.app.api.chat_role(self.tid)["role"]) + 1) % len(order)]
            self.app.api.set_chat_role(self.tid, role)
        self.app.notify(f"{ROLES[role][1]} {t(ROLES[role][0], lang)}" if role else t("No role", lang),
                        title=t("Role of this chat", lang), timeout=4)

    def action_second_opinion(self) -> None:
        """F4: the last question to another model; its answer comes under the first one."""
        if self.tid is None or self._stream:
            return
        res = self.app.api.second_opinion(self.tid)
        if not res.get("ok"):
            if res.get("error") in ("no_other", "enough"):
                self.app.notify(t("No other model is free right now. Add a key for one more free service in Settings → Keys, or try later.", L(self.app))
                                if res["error"] == "no_other" else t("Two second opinions are enough for one question.", L(self.app)), timeout=6)
            return
        self.open_thread(self.tid)
        self._watch(res["stream"])

    def action_voice(self) -> None:
        """F2: start recording; F2 again: stop, and the words go to the message box."""
        lang = L(self.app)
        if not getattr(self, "_recording", False):
            r = self.app.api.voice_start()
            if not r.get("ok"):
                self.app.notify(t(VOICE_ERR.get(r.get("error"), VOICE_ERR["engine"]), lang), severity="warning")
                return
            self._recording = True
            self.app.notify(t("Listening… Press F2 again to stop.", lang), timeout=4)
            return
        self._recording = False
        self.app.notify(t("Turning speech into text…", lang), timeout=3)
        self._voice_text()

    def action_read_aloud(self) -> None:
        """F3: reads the last answer aloud; F3 again while it reads: stop."""
        if getattr(self, "_reading", False):
            self._reading = False
            self.app.api.tts_stop()
            return
        last = next((m["content"] for m in reversed(self.app.api.store.messages(self.tid)) if m["role"] == "assistant"),
                    "") if self.tid else ""
        if last:
            self._read(last)

    @work(thread=True, group="speak", exclusive=True)
    def _read(self, text: str) -> None:
        self._reading = True
        r = self.app.api.tts_play(text)
        if not r.get("ok"):
            self._reading = False
            msg = {"off": "Reading aloud is off. Turn it on in Settings → Reading aloud.",
                   "not_ready": "Download Piper first: Settings → Reading aloud.",
                   "no_player": "No speech program found. Install speech-dispatcher (spd-say), or choose Piper in Settings → Reading aloud."
                   }.get(r.get("error"), "Couldn't read it aloud this time.")
            self.app.call_from_thread(self.app.notify, t(msg, L(self.app)), severity="warning")

    @work(thread=True, group="voice")
    def _voice_text(self) -> None:
        r = self.app.api.voice_stop()
        self.app.call_from_thread(self._voice_done, r)

    def _voice_done(self, r: dict) -> None:
        lang = L(self.app)
        if not r.get("ok"):
            self.app.notify(t(VOICE_ERR.get(r.get("error"), VOICE_ERR["engine"]), lang), severity="warning")
            return
        box = self.query_one("#composer", Input)
        box.value = (box.value.rstrip() + " " if box.value.strip() else "") + r["text"]
        box.focus()

    def action_save_chat(self) -> None:
        """Ctrl+X: the chat as a Markdown file in Downloads."""
        lang = L(self.app)
        r = self.app.api.export_chat(self.tid) if self.tid is not None else {"ok": False}
        self.app.notify(t("Saved to {name}", lang, name=r["path"]) if r.get("ok") else t("Nothing to save yet.", lang))

    def action_edit_last(self) -> None:
        """Ctrl+E: the last question and its answer go; the question comes back to the box to change it."""
        if self.tid is None or self._stream:
            return
        r = self.app.api.edit_last(self.tid)
        if not r.get("ok"):
            return
        self.open_thread(self.tid)
        box = self.query_one("#composer", Input)
        box.value = r["text"]
        box.focus()

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

    def action_stop_answer(self) -> None:
        """Esc while it answers: the answer ends where it is (what was written stays)."""
        if self._stream:
            self.app.api.stop_answer(self._stream)

    def _saved_chat(self) -> dict | None:
        """The open chat if it is a saved one (a private chat isn't in the list, so it has no name or pin)."""
        return self.app.api.store.thread(self.tid) if self.tid and self.tid > 0 else None

    def action_rename_chat(self) -> None:
        th = self._saved_chat()
        if not th:
            return
        tid = th["id"]

        def done(name: str | None) -> None:
            if name:
                self.app.api.rename_thread(tid, name)
                if self.tid == tid:
                    self.query_one("#chattitle", Label).update(name[:80])
                self._fill_threads()

        self.app.push_screen(NameScreen(t("Rename chat", L(self.app)), th["title"] or ""), done)

    def action_pin_chat(self) -> None:
        th = self._saved_chat()
        if not th:
            return
        self.app.api.pin_thread(th["id"], not th["pinned"])
        self._fill_threads()
        lang = L(self.app)
        self.notify(t("Unpinned.", lang) if th["pinned"] else t("Pinned to the top of the list.", lang), timeout=4)

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
        log.query(".follow").remove()                     # old follow-up ideas go when you write
        log.query(AskForm).remove()
        self._asked = None
        if self.tid is None:
            self.tid = self.app.api.new_thread(private=getattr(self, "_private_next", False))["id"]
            self._private_next = False
            if getattr(self, "_new_role", ""):
                self.app.api.set_chat_role(self.tid, self._new_role)
                self._new_role = ""
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
        self._watch(res["stream"])

    def _watch(self, sid: str) -> None:
        """Shows "Thinking…" and follows the answer's stream."""
        log = self.query_one("#log", VerticalScroll)
        self._stream, self._offset, self._text, self._notes_seen, self._tools_seen = sid, 0, "", 0, 0
        self._cards_seen, self._live, self._dirty, self._drawn_at = 0, "", False, 0.0
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
        notes = r.get("notes", [])
        if len(notes) > self._notes_seen:                  # one line, updated: not a ladder of "switched to" notes
            text = "↪ " + t("switched to {m}", lang, m=notes[-1]) + (
                " " + t("(tried {n} models)", lang, n=len(notes) + 1) if len(notes) > 1 else "")
            if getattr(self, "_switch_note", None) is not None and self._notes_seen:
                self._switch_note.update(text)
            else:
                self._switch_note = Static(text, classes="msg-note", markup=False)
                await log.mount(self._switch_note, before=self._bot)
        self._notes_seen = len(r.get("notes", []))
        for chip in r.get("tools", [])[self._tools_seen:]:
            await log.mount(Static(tool_text(chip, lang), classes="msg-tool", markup=False), before=self._bot)
        self._tools_seen = len(r.get("tools", []))
        for card in r.get("cards", [])[self._cards_seen:]:
            await log.mount(ActCard(card))
        self._cards_seen = len(r.get("cards", []))
        changed = False
        if "final" in r and r.get("stopped"):
            note = Static("⏹ " + t("Stopped.", lang), classes="msg-note", markup=False)
            if self._bot is None:
                await log.mount(note)
            elif r["final"].strip():
                await log.mount(note, after=self._bot)
            else:                                        # stopped before a word: no empty answer
                await log.mount(note, before=self._bot)
                self._bot.remove()
                self._bot = None
        if "final" in r:
            self._text, changed = r["final"], True
            self._naming = bool(r.get("titling"))       # a fast model is naming this new chat
            self._suggesting = bool(r.get("suggesting"))   # follow-up buttons are coming
            self._learning = bool(r.get("learning"))       # a side model looks for facts to remember
            if r.get("questions") and not getattr(self, "_asked", None):
                self._asked = r["questions"]
                await log.mount(AskForm(r["questions"]), after=self._bot)
            if r.get("model"):
                self._set_model(r["model"])
            if r.get("sent") and self._bot is not None:
                await log.mount(sent_box(r["sent"], lang), after=self._bot)
        elif r.get("text"):
            self._text += r["text"]
            self._offset = r["offset"]
            changed = True
        if not self._text and r.get("live") and self._bot is not None and r["live"] != getattr(self, "_live", ""):
            self._live = r["live"]                       # what it is doing now, instead of a bare "Thinking…"
            await self._bot.update("_" + re.sub(r"([_*`\[\]])", r"\\\1", r["live"]) + "_")
        # a long answer is parsed again on every redraw: draw it less often (up to once a second), never skip the end
        self._dirty = getattr(self, "_dirty", False) or changed
        gap = min(1.0, len(self._text) / 4000)
        if self._dirty and self._bot is not None and ("final" in r or r.get("done")
                                                      or time.monotonic() - getattr(self, "_drawn_at", 0.0) >= gap):
            await self._bot.update(count_on(self._text))
            log.scroll_end(animate=False)
            self._dirty, self._drawn_at = False, time.monotonic()
        if r.get("done"):
            self._stream = None
            err = r.get("error")
            if not err and self._text and self.app.api.settings.tts_auto and self.app.api.settings.tts != "off":
                self._read(self._text)
            if err:
                await log.mount(Static(self._error_text(err), classes="msg-err", markup=False))
                if not self._text and self._bot is not None:
                    self._bot.remove()
                log.scroll_end(animate=False)
            self._fill_threads()
            th = next((x for x in self.app.api.threads() if x["id"] == self.tid), None)
            if th:
                self.query_one("#chattitle", Label).update(th["title"])
            if getattr(self, "_naming", False):
                self._naming = False
                self._wait_name(self.tid)
            if getattr(self, "_suggesting", False):
                self._suggesting = False
                self._wait_follow(self.tid)
            if getattr(self, "_learning", False):
                self._learning = False
                self._wait_memory(self.tid)
            self._timer.stop()      # last: stopping cancels this very callback at its next await

    @work(thread=True, group="follow")
    def _wait_follow(self, tid: int) -> None:
        ideas = self.app.api.wait_follow_ups(tid)
        self.app.call_from_thread(self._show_follow, tid, ideas)

    def _show_follow(self, tid: int, ideas: list[str]) -> None:
        if not ideas or tid != self.tid or self._stream:
            return
        log = self.query_one("#log", VerticalScroll)
        log.mount(Vertical(*(Button("→ " + x, classes="followbtn", name=x) for x in ideas), classes="follow"))
        log.scroll_end(animate=False)

    @work(thread=True, group="memory")
    def _wait_memory(self, tid: int) -> None:
        facts = self.app.api.wait_memory(tid)
        self.app.call_from_thread(self._show_memory, tid, facts)

    def _show_memory(self, tid: int, facts: list[dict]) -> None:
        """ "Remembered: …" with an Undo button under the answer, for each new fact."""
        if not facts or tid != self.tid:
            return
        lang = L(self.app)
        log = self.query_one("#log", VerticalScroll)
        for f in facts:
            log.mount(Horizontal(Static(t("Remembered: {fact}", lang, fact=f["text"]), classes="learnedtext"),
                                 Button(t("Undo", lang), classes="followbtn forgetbtn", name=str(f["id"])), classes="learned"))
        log.scroll_end(animate=False)

    @on(Button.Pressed, ".forgetbtn")
    def _forget(self, ev: Button.Pressed) -> None:
        ev.stop()
        self.app.api.delete_fact(int(ev.button.name or 0))
        row = ev.button.parent
        if row is not None:
            row.query_one(".learnedtext", Static).update(t("Removed from memory.", L(self.app)))
            ev.button.remove()

    @on(Button.Pressed, ".followbtn")
    def _follow_pressed(self, ev: Button.Pressed) -> None:
        if self._stream:
            return
        box = self.query_one("#composer", Input)
        box.value = ev.button.name or ""
        box.post_message(Input.Submitted(box, box.value))

    @work(thread=True, group="title")
    def _wait_name(self, tid: int) -> None:
        title = self.app.api.wait_title(tid)
        self.app.call_from_thread(self._named, tid, title)

    def _named(self, tid: int, title: str) -> None:
        self._fill_threads()
        if title and tid == self.tid:
            self.query_one("#chattitle", Label).update(title)

    def _error_text(self, err: dict) -> str:
        lang, kind = L(self.app), err.get("kind")
        if kind == "rate":
            back = int(err.get("back_in") or 0)
            h, m = back // 3600, max(1, round(back % 3600 / 60))
            when = t("{h} h {m} min", lang, h=h, m=m) if h else t("{m} min", lang, m=m)
            first = (t("All free models are out of limits for now. The first one is back in about {time}.", lang, time=when)
                     if back > 120 else t("All free models are busy or out of limits. Try again in a minute.", lang))
            tip = ("Tip: add a key for one more free service (Settings → Keys) to get more answers a day."
                   if err.get("more_keys") else "Tip: a local model (Settings → Local models) answers when the limits run out.")
            return first + " " + t(tip, lang)
        if kind == "file":
            return err.get("message", "")
        if kind == "auth":
            return t("No working key. Add one in Settings (Ctrl+S).", lang)
        if kind == "empty":
            return t("The model sent no answer. Press Retry or ask in other words.", lang)
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
    def action_settings(self, tab: str = "") -> None:
        def done(res: str) -> None:
            if res == "lang":
                self.app.switch_screen(make_chat_screen(L(self.app)))
            elif res == "reopen":                         # mode changed: show the matching options
                self._load_model_label()
                self.app.push_screen(SettingsScreen(), done)
            else:
                self._load_model_label()

        self.app.push_screen(SettingsScreen(tab), done)

    def action_connectors(self, tab: str = "") -> None:
        tab = tab or ("browse" if not self.app.api.mcp_status()["servers"] and not self.app.api.mail_status()["connected"] else "yours")
        self.app.push_screen(ConnectorsScreen(tab))

    def action_doctor(self) -> None:
        self.app.push_screen(DoctorScreen())

    def action_bug(self) -> None:
        self.app.push_screen(BugScreen())

    def action_models(self) -> None:
        self.app.push_screen(ModelsScreen(), lambda _r: self._load_model_label())

    def action_about(self) -> None:
        self.app.push_screen(AboutScreen())

    def action_history(self) -> None:
        self.app.push_screen(HistoryScreen())


def sent_box(lines: list[str], lang: str) -> Collapsible:
    """Folded under a reply: which kinds of data went to the model, and where."""
    return Collapsible(Static("\n".join("• " + x for x in lines), markup=False, classes="muted"),
                       title="🔒 " + t("What went to the model", lang), collapsed=True, classes="sent")


# Everything the chat screen can do: (label, action, keys). All of it is in the menu (Ctrl+P), searchable;
# only the first few show at the bottom. Keys that terminals take for themselves have a second key
# (Ctrl+H is Backspace in many Linux terminals, F1 is the terminal's own help in some).
CHAT_COMMANDS = [
    ("New chat", "new_chat", "Ctrl+N"),
    ("All commands", "app.command_palette", "Ctrl+P"),
    ("Settings", "settings", "Ctrl+S"),
    ("Models", "models", "Ctrl+O"),
    ("Quit", "app.quit", "Ctrl+Q"),
    ("Private chat", "private_chat", "F7"),
    ("Attach a file or photo", "attach", "Ctrl+F"),
    ("Retry", "retry", "Ctrl+R"),
    ("Edit", "edit_last", "Ctrl+E"),
    ("Second opinion", "second_opinion", "F4"),
    ("Role of this chat", "next_role", "F6"),
    ("Save chat", "save_chat", "Ctrl+X"),
    ("Rename chat", "rename_chat", ""),
    ("Pin chat", "pin_chat", ""),
    ("Delete chat", "delete_chat", "Ctrl+D"),
    ("Stop the answer", "stop_answer", "Esc"),
    ("Voice input", "voice", "F2"),
    ("Read aloud", "read_aloud", "F3"),
    ("Connectors", "connectors", ""),
    ("What Lanterna did", "history", "F9"),
    ("Check Lanterna", "doctor", ""),
    ("Found a bug?", "bug", ""),
    ("About", "about", ""),
]
FOOTER_KEYS = {"new_chat", "app.command_palette", "settings", "models", "app.quit"}
_KEYS = {"Ctrl+N": "ctrl+n", "Ctrl+P": "ctrl+p", "Ctrl+S": "ctrl+s", "Ctrl+O": "ctrl+o", "Ctrl+Q": "ctrl+q", "F7": "f7",
         "Ctrl+F": "ctrl+f", "Ctrl+R": "ctrl+r", "Ctrl+E": "ctrl+e", "F4": "f4", "F6": "f6", "Ctrl+X": "ctrl+x",
         "Ctrl+D": "ctrl+d", "F2": "f2", "F3": "f3", "F9": "f9", "Esc": "escape"}


def make_chat_screen(lang: str) -> Screen:
    """Builds the chat screen with footer key hints in the chosen language."""
    bindings = [Binding(_KEYS[k], action, t("Menu" if action == "app.command_palette" else label, lang),
                        show=action in FOOTER_KEYS, key_display=k, priority=True)
                for label, action, k in CHAT_COMMANDS if k]
    bindings += [Binding("ctrl+h", "history", show=False, priority=True),          # where the terminal sends it
                 Binding("f1", "app.command_palette", show=False, priority=True)]
    return type("ChatScreen", (_ChatScreen,), {"BINDINGS": bindings})()


class _MenuCommands(Provider):
    """The menu's commands in our own order (the most used first, Quit last), not sorted by name."""

    async def discover(self) -> Hits:
        for name, help_text, callback, discover in self.app.get_system_commands(self.screen):
            if discover:
                yield DiscoveryHit(name, callback, help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, help_text, callback, *_ in self.app.get_system_commands(self.screen):
            if (score := matcher.match(name)) > 0:
                yield Hit(score, matcher.highlight(name), callback, help=help_text)


# ---------------------------------------------------------------------------------------------- app
class LanternaApp(App):
    CSS = CSS
    TITLE = "Lanterna"
    ENABLE_COMMAND_PALETTE = True
    COMMAND_PALETTE_BINDING = "ctrl+p"
    COMMANDS = {_MenuCommands}
    BINDINGS = [Binding("f8", "snooze", show=False, priority=True)]   # "snooze 10 min" on the last reminder

    def action_command_palette(self) -> None:
        """The menu with every command (Ctrl+P, F1, or ☰ in the sidebar); only over the chat, not over a dialog."""
        if isinstance(self.screen, _ChatScreen) and not CommandPalette.is_open(self):
            self.push_screen(CommandPalette(placeholder=t("Type to find a command…", L(self)), id="--command-palette"))

    def get_system_commands(self, screen: Screen):
        if not isinstance(screen, _ChatScreen):
            return
        lang = L(self)
        for label, action, key in CHAT_COMMANDS:
            if action in ("app.command_palette", "app.quit"):
                continue
            if action == "pin_chat" and (screen._saved_chat() or {}).get("pinned"):
                label = "Unpin chat"
            if action == "stop_answer" and not screen._stream:  # only while it answers
                continue
            yield SystemCommand(t(label, lang), key, getattr(screen, f"action_{action}"))
            if action == "connectors":
                yield SystemCommand(t("Connect mail", lang), "", lambda: self.push_screen(MailScreen()))
        for tab, label in SET_TABS:
            if tab != "general":
                yield SystemCommand(t("Settings", lang) + " → " + t(label, lang), "", lambda tab=tab: screen.action_settings(tab))
        yield SystemCommand(t("Quit", lang), "Ctrl+Q", self.action_quit)

    def __init__(self, api: Api | None = None, force_setup: bool = False):
        super().__init__()
        self.api = api or Api()
        self.force_setup = force_setup

    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = "lanterna"
        if self.force_setup or not self.api.settings.onboarded:
            self.push_screen(OnboardScreen())
        elif not self.api.settings.sync_asked and self.api.sync_status()["phase"] == "off":
            self.push_screen(GoogleScreen())
        else:
            self.push_screen(make_chat_screen(L(self)))
        self.set_interval(10, self._alerts)

    _snooze: tuple[int, float] = (0, 0.0)                   # the last reminder that came, for F8

    def action_snooze(self) -> None:
        rid, at = self._snooze
        if rid and time.time() - at < 30 * 60 and self.api.snooze_reminder(rid, 10):
            self._snooze = (0, 0.0)
            self.notify(t("I'll remind you again in 10 minutes.", L(self)), timeout=6)

    def _alerts(self) -> None:
        for a in self.api.alerts():
            self.bell()
            kind = a.get("kind")
            title = ("🧹 " + t("Weekly tidy-up", L(self)) if kind == "tidy" else "💾 " + t("Disk space", L(self)) if kind == "space"
                     else "☀️ " + t("Morning summary", L(self)) if kind == "morning"
                     else "🔁 " + t("Regular task", L(self)) if kind == "task" else "⏰ " + t("Reminder", L(self)))
            text = a["text"]
            if not kind and a.get("id"):
                self._snooze = (int(a["id"]), time.time())
                text += "\n" + t("F8: snooze 10 min", L(self))
            self.notify(text, title=title, timeout=30, markup=False)
            if a.get("tid") and hasattr(self.screen, "_fill_threads"):
                self.screen._fill_threads()


def run(force_setup: bool = False) -> int:
    result = LanternaApp(force_setup=force_setup).run()
    if result == "restart":                                  # after Update now (pipx): start the new version
        import os
        from .updates import restart_args
        args = restart_args()
        os.execv(args[0], args)
    return 0
