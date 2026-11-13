"""“What went to the model” under each reply: which kinds of data this answer sent, and where.

Built from what the reply really used (the message, the chat so far, memory, attachments, the tools that ran and
their arguments). Stored with the reply on this device only (not synced), as English templates translated on
display. It names files and searches, never their contents.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from .scam import refuse

FILE_NAMES = {"pc_list", "pc_overview", "pc_find", "pc_duplicates", "pc_space", "pc_folders", "folder_list",
              "folder_search", "drive_list", "github_list", "github_repos"}
FILE_READ = {"pc_read", "folder_read", "github_read"}
PC_INFO = {"pc_info", "pc_load", "pc_startup", "pc_power"}
PROGRAMS = {"app_installed", "app_updates"}


def _arg(arguments: str, key: str) -> str:
    try:
        v = json.loads(arguments or "{}").get(key, "")
        return str(v)[:120]
    except (ValueError, AttributeError):
        return ""


SECOND = "A second opinion: the same question to another model, without the first answer"


def build(model: str, local: bool, history: int, name: bool, facts: int, files: list[str], photos: int,
          tools: list[tuple[str, str]], summary: bool = False, old_files: list[str] | None = None,
          parts: list[str] | None = None, second: bool = False, private: bool = False) -> list[dict]:
    """[{"t": template, "v": vars}] — the first line says where it went."""
    out = [{"t": "Stayed on this computer ({model})" if local else "Sent to {model}", "v": {"model": model or "?"}}]
    out.append({"t": "Your message and {n} earlier messages of this chat" if history else "Your message", "v": {"n": history}})
    if private:
        out.append({"t": "Private chat: it isn't saved, and memory and your other chats aren't used", "v": {}})
    if second:
        out.append({"t": SECOND, "v": {}})
    if summary:
        out.append({"t": "A short summary of the older part of this chat", "v": {}})
    if name:
        out.append({"t": "Your name", "v": {}})
    if facts:
        out.append({"t": "What Lanterna remembers about you ({n} facts)", "v": {"n": facts}})
    if files:
        out.append({"t": "Attached files: {names}", "v": {"names": ", ".join(files[:6])}})
    if parts:
        out.append({"t": "Only the parts of {names} that fit your question", "v": {"names": ", ".join(parts[:6])}})
    if photos:
        out.append({"t": "Photos: {n}", "v": {"n": photos}})
    if old_files:                                      # attached earlier: their text goes along with the chat again
        out.append({"t": "Files attached earlier in this chat (again): {names}", "v": {"names": ", ".join(old_files[:6])}})
    seen: set = set()

    def once(t: str, v: dict | None = None) -> None:
        key = (t, json.dumps(v or {}, sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append({"t": t, "v": v or {}})

    for tool, args in tools:
        if tool in FILE_NAMES:
            once("Names and sizes of files in your folders")
        elif tool in FILE_READ:
            once("The text of the file {path}", {"path": _arg(args, "path") or "?"})
        elif tool in PC_INFO:
            once("Information about this computer (system, memory, disks, running programs)")
        elif tool in PROGRAMS:
            once("The list of your installed programs")
        elif tool == "web_search":
            once("Search words to DuckDuckGo: {q}", {"q": _arg(args, "query") or _arg(args, "q")})
        elif tool == "read_page" and not refuse(_arg(args, "url")):     # a link that looks like a scam is not opened
            once("A web page was opened: {site}", {"site": urlparse(_arg(args, "url")).netloc or "?"})
        elif tool == "search_chats":
            once("Words looked up in your earlier chats on this computer: {q}", {"q": _arg(args, "words")})
        elif tool == "read_chat":
            once("The text of your earlier chat #{id}", {"id": _arg(args, "id") or "?"})
        elif tool == "currency":
            once("Exchange rates from the National Bank of Ukraine (nothing about you)")
        elif tool == "weather":
            once("A city name to Open-Meteo (weather): {city}", {"city": _arg(args, "city") or _arg(args, "place")})
    return out


def dumps(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False)


def is_second(raw: str) -> bool:
    """Whether a stored reply was a second opinion (its "what went to the model" says so)."""
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return False
    return isinstance(items, list) and any(isinstance(x, dict) and x.get("t") == SECOND for x in items)


def view(raw: str, lang: str) -> list[str]:
    """Translated lines for display; [] when nothing was recorded (older replies)."""
    from .i18n import t
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    return [t(x["t"], lang, **x.get("v", {})) for x in items if isinstance(x, dict) and x.get("t")]
