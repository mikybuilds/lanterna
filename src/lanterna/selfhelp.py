"""Lanterna's own help for the model (the lanterna_help tool): what Lanterna is and has, where it runs, installing and
updating it, its Settings, and its Chrome extension with the state on this computer now.

The web knows only older versions (a beta's new parts aren't on the project page yet), so a question about Lanterna
itself is answered from here. Buttons and settings are named as the window shows them, in the app's language.
"""
from __future__ import annotations

import re
import sys

from . import AUTHOR, HOMEPAGE, __version__
from .i18n import t

TOPICS = ("lanterna", "chrome")

TOOL = ("Lanterna's own help, up to date for this version and this computer: what Lanterna is and can do, where it "
        "runs, installing and updating it, where its settings are, and its Chrome extension (the steps to add it and "
        "whether it is connected now). Call it before answering any question about Lanterna itself (its features, "
        "settings, versions, how to install, update or set up it or its extension), and never web_search for these: "
        "the web knows only older versions.")
TOPIC = "lanterna: what it is, where it runs, installing, updating, Settings; chrome: its Chrome extension"

# Settings, tab by tab, as the window shows them (ui/app.js SET_TABS; a test keeps the two the same)
SETTINGS = (("General", ("Language", "Text size", "Theme", "Name", "Mode", "Local models", "Updates")),
            ("Models", ("Services", "Limits", "Free models right now")),
            ("Memory", ("Memory", "Reminders", "Regular tasks")),
            ("Chats", ("Working folder", "Chats", "Instructions and roles", "Backups")),
            ("Voice", ("Voice input", "Reading aloud")),
            ("Computer", ("Always at hand", "Computer", "MCP servers", "Connectors")),
            ("Chrome", ("Chrome", "Shortcuts")),
            ("Account", ("Account and sync", "Found a bug?")))

# Settings → Chrome: the steps to add the extension, word for word (ui/app.js chromeSettings)
STEPS = ("Open chrome://extensions in Chrome and turn on Developer mode (top right).",
         "Press «Load unpacked» and choose the folder the button below opens.",
         "Pin Lanterna on Chrome's toolbar: its button (or Alt+L) opens Lanterna next to the page.",
         "Leave Developer mode on: without it Chrome turns off extensions loaded from a folder, Lanterna's too.")
MODES = {"ask": "Ask first", "semi": "Semi-automatic", "full": "Automatic"}


def is_beta(version: str = __version__) -> bool:
    """A test version ("1.1.11b8"): a pre-release, never offered as an update."""
    return bool(re.search(r"\d(a|b|rc)\d+$", version or ""))


def _q(text: str, lang: str) -> str:
    return f"«{t(text, lang)}»"


def settings_map(lang: str = "en") -> str:
    return " · ".join(f"{_q(tab, lang)} ({', '.join(t(x, lang) for x in parts)})" for tab, parts in SETTINGS)


def about(lang: str = "en", window: bool = True, platform: str = sys.platform, version: str = __version__) -> str:
    """Topic "lanterna": what it is, where it runs, installing and updating, the Settings tabs."""
    q = lambda s: _q(s, lang)                                                    # noqa: E731
    test = ", a test version (beta): a pre-release on the Releases page, never offered as an update" \
        if is_beta(version) else ""
    here = ("Windows" if platform == "win32" else "Linux" if platform.startswith("linux") else platform) + \
        (", Lanterna's window app" if window else ", Lanterna's terminal app")
    return "\n".join([
        f"LANTERNA'S OWN HELP (version {version}{test}). Answer questions about Lanterna from this: the web knows "
        "only older versions.",
        f"- What it is: a free, open-source AI assistant made by {AUTHOR} ({HOMEPAGE}). It answers with free online "
        "models (Groq, Google Gemini and other services, with the user's own free keys) and, if the user wants, with "
        "local models through Ollama. It remembers facts and chats, sets reminders, searches the web, works with "
        "files and photos, helps with this computer (folders, programs, safe settings), and works in Chrome with "
        "an extension of its own (lanterna_help, topic chrome).",
        "- Where it runs: Windows 10 and 11 (a window, with the tray and a quick window) and Linux (a full-screen "
        "app in the terminal; its own window is optional). macOS isn't tested yet, and there is no app for phones. "
        "Chats, settings and keys can go to the user's other computers through their Google Drive "
        f"({q('Settings')} → {q('Account and sync')}).",
        f"- Install on Windows: Lanterna-Setup-x.y.z.exe from the latest release ({HOMEPAGE}/releases/latest), no "
        "admin rights needed. Windows may say «Windows protected your PC» because the installer isn't code-signed: "
        "More info → Run anyway. A portable zip is in the same release.",
        f"- Install on Linux: Python 3.10 or newer, pipx and git, then `pipx install git+{HOMEPAGE}`. `lanterna` "
        "starts it in a terminal; `lanterna desktop` adds it to the app menu and says what its own window still "
        "needs.",
        f"- Updates: Lanterna says when a new version is out ({q('Settings')} → {q('General')} → {q('Updates')}: "
        f"{q('Check for a new version when Lanterna starts')}); "
        f"{q('Update now')} in that notice installs it, and the chats, settings and keys stay. On Linux it runs "
        "`pipx upgrade lanterna`.",
        f"- This computer: {here}.",
        f"- {q('Settings')}, tab by tab: {settings_map(lang)}.",
    ])


def chrome(lang: str = "en", window: bool = True, on: bool = True, listening: bool = True, connected: bool = False,
           browser: str = "", mode: str = "semi", platform: str = sys.platform) -> str:
    """Topic "chrome": the extension, the steps to add it and its state on this computer now."""
    q = lambda s: _q(s, lang)                                                    # noqa: E731
    here = f"{q('Settings')} → Chrome"
    if not window:
        now = ("this is Lanterna's terminal app, and Chrome connects only to Lanterna's window app (on Linux its own "
               "window: lanterna_help, topic lanterna).")
    elif not on:
        now = f"{q('Let Lanterna work in Chrome')} is off ({here}): the user turns it on first, then the steps below."
    elif connected:
        now = (f"the extension is connected ({browser or 'Chrome'}): it is added and works. Its button on Chrome's "
               "toolbar (or Alt+L) opens Lanterna's side panel next to the page.")
    elif not listening:
        now = ("Lanterna couldn't open its connection for Chrome on this computer: starting Lanterna again usually "
               "helps.")
    else:
        now = ("the extension isn't connected: it isn't added yet, Chrome is closed, or Chrome turned it off "
               "(it does that when Developer mode is off, in chrome://extensions).")
    steps = [f"  {i}. {t(s, lang)}" for i, s in enumerate(STEPS, 1)]
    folder = q("Open the extension's folder")
    steps[1] += f" (the button: {folder} in {here})"
    running = ("Lanterna must be running for it (in the tray is enough)." if platform == "win32" else
               "Lanterna's window must be open for it.")
    return "\n".join([
        "LANTERNA IN CHROME (Lanterna's own extension; the web doesn't know it yet). Answer from this.",
        "- What it is: an extension for Google Chrome 116 or newer that comes with Lanterna, free. It isn't in the "
        "Chrome Web Store: Chrome loads it from a folder of Lanterna's. With it Lanterna works in the user's Chrome, "
        "in the tabs they see: it opens pages (new addresses in tabs of its own, in an orange «Lanterna» tab group), "
        "reads them, clicks, types, fills in forms, scrolls, gives a site a file and downloads. Its side panel next "
        "to the page is a Lanterna chat.",
        f"- Now on this computer: {now}",
        f"- To add it ({here} shows the same steps):",
        *steps,
        f"  {running}",
        f"- Chrome had Lanterna's extension before, or it's another Chrome: {q('Connect Chrome')} in {here}, then "
        "open Lanterna's side panel in Chrome within 2 minutes.",
        f"- How much it asks first in Chrome: {q(MODES.get(mode, MODES['semi']))} now "
        f"({q('How much Lanterna asks first in Chrome')} in {here}, or the switch in the side panel). Never, in any "
        "mode: passwords, card details, buying or paying, new accounts, CAPTCHAs.",
    ])


def help_text(topic: str, lang: str = "en", **state) -> str:
    """The lanterna_help tool's answer."""
    topic = str(topic or "").strip().lower()
    if topic == "chrome":
        return chrome(lang, **state)
    return about(lang, window=state.get("window", True))
