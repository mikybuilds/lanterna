"""The "what I'm doing" line under a reply that is being written, instead of three jumping dots.

Two sources:
- tool calls ("Searching the web: …", "Preparing the file hello.txt") — always in the app's language;
- the model's own reasoning: Gemini sends short thought summaries with a **Heading** per step; other models
  (<think> blocks, a `reasoning` field) send raw text, and the last line of it is shown while it lasts.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .i18n import t

HEAD = re.compile(r"^\s*\*\*(.{3,120}?)\*\*\s*$", re.M)
MAX_STEPS = 40
MAX_BUF = 20000

TOOL_TEXT = {
    "calculate": ("Calculating: {x}", "expression"),
    "date_calc": ("Counting dates", ""),
    "weather": ("Checking the weather: {x}", "place"),
    "web_search": ("Searching the web: {x}", "query"),
    "read_page": ("Reading {x}", "url"),
    "scam_check": ("Checking for signs of a scam", ""),
    "remember": ("Remembering: {x}", "fact"),
    "forget": ("Forgetting: {x}", "fact"),
    "set_reminder": ("Setting a reminder: {x}", "text"),
    "list_reminders": ("Looking at the reminders", ""),
    "cancel_reminder": ("Cancelling a reminder", ""),
    "add_task": ("Adding a regular task: {x}", "what"),
    "list_tasks": ("Looking at the regular tasks", ""),
    "delete_task": ("Deleting a regular task", ""),
    "currency": ("Converting currency", ""),
    "search_chats": ("Looking through earlier chats: {x}", "words"),
    "read_chat": ("Reading an earlier chat", ""),
    "convert_units": ("Converting units", ""),
    "transcribe_audio": ("Turning audio into text", ""),
    "folder_list": ("Looking at the files in the folder", ""),
    "folder_search": ("Searching the folder: {x}", "text"),
    "folder_read": ("Reading {x}", "path"),
    "folder_write": ("Preparing the file {x}", "path"),
    "pc_write": ("Preparing the file {x}", "path"),
    "folder_make": ("Preparing the folder {x}", "path"),
    "folder_move": ("Preparing to move {x}", "path"),
    "drive_list": ("Looking in Google Drive", ""),
    "drive_make_folder": ("Preparing the folder {x} in Google Drive", "name"),
    "drive_save_text": ("Preparing {x} for Google Drive", "name"),
    "drive_upload": ("Preparing {x} for Google Drive", "path"),
    "github_repos": ("Looking at your GitHub repositories", ""),
    "github_list": ("Looking in {x} on GitHub", "repo"),
    "github_read": ("Reading {x} on GitHub", "path"),
    "github_push": ("Preparing a push to {x}", "repo"),
    "github_new_repo": ("Preparing a new repository {x}", "name"),
    "app_search": ("Looking for the program: {x}", "query"),
    "app_info": ("Reading about the program {x}", "id"),
    "app_installed": ("Looking at the installed programs", ""),
    "app_updates": ("Checking for program updates", ""),
    "app_install": ("Preparing to install {x}", "id"),
    "app_update": ("Preparing to update {x}", "id"),
    "app_uninstall": ("Preparing to remove {x}", "id"),
    "pc_info": ("Looking at the computer", ""),
    "pc_look": ("Looking at the look settings", ""),
    "pc_look_set": ("Preparing changes to the look", ""),
    "pc_theme": ("Preparing the theme", ""),
}
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
CYRILLIC_LANGS = ("uk", "ru", "be", "bg", "sr", "mk")


def _short(text: str, n: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def fits_lang(text: str, lang: str) -> bool:
    """Whether a model's short note can be the user's language: models often write the "why" in English even in
    a Ukrainian chat (and an English line in Cyrillic is just as wrong)."""
    return bool(CYRILLIC.search(text)) == (lang in CYRILLIC_LANGS)


def tool_step(name: str, arguments: str, lang: str = "en", why: bool = True) -> str:
    """'web_search', '{"query": "Ferrara news"}' → 'Шукаю в інтернеті: Ferrara news'. why=False leaves out the
    model's own reason (the tool lines under a reply)."""
    try:
        args = json.loads(arguments or "{}")
    except ValueError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    text, key = TOOL_TEXT.get(name, ("Using {x}", ""))
    x = args.get(key, "") if key else name
    if key == "url":
        x = urlparse(str(x)).netloc or x
    x = _short(x or "")
    if "{x}" in text and not x:                   # no argument: say it without the colon / name
        text = text.replace(": {x}", "").replace(" {x}", "")
    line = t(text, lang, x=x) if "{x}" in text else t(text, lang)
    note = _short(args.get("intent") or "", 70) if why and isinstance(args.get("intent"), str) else ""
    if note and not fits_lang(note, lang):
        note = ""                                         # not in the user's language: the line alone says enough
    return f"{line} — {note}" if note else line           # the model's own "why", in the user's language


def _last_line(text: str) -> str:
    """The latest readable line of raw reasoning, without bullets and markdown."""
    for line in reversed(text.strip().splitlines()):
        line = re.sub(r"^[\s*\-•#>\d.)]+", "", line).replace("**", "").replace("$", "").strip()
        if len(line) >= 3:
            return _short(line, 90)
    return ""


class Steps:
    """Collects the steps of one reply. view() → {"steps": [{"kind", "text"}], "live": "the current line"}."""

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self.items: list[dict] = []
        self.buf = ""                  # reasoning since the last tool call
        self.heads = 0                 # how many **Headings** of buf are already steps
        self.live = ""

    def thought(self, text: str) -> None:
        if len(self.buf) < MAX_BUF:
            self.buf += text
        heads = HEAD.findall(self.buf)
        for h in heads[self.heads:]:
            self._add("think", _short(h, 90))
        self.heads = len(heads)
        if heads:
            self.live = _short(heads[-1], 90)
        else:
            self.live = _last_line(self.buf) or self.live

    def tool(self, name: str, arguments: str) -> None:
        self.buf, self.heads = "", 0
        self._add("tool", tool_step(name, arguments, self.lang))
        self.live = self.items[-1]["text"] if self.items else self.live

    def _add(self, kind: str, text: str) -> None:
        if text and len(self.items) < MAX_STEPS and (not self.items or self.items[-1]["text"] != text):
            self.items.append({"kind": kind, "text": text})

    def view(self) -> dict:
        return {"steps": list(self.items), "live": self.live}
