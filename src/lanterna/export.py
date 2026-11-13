"""Saving chats: one chat as Markdown, or a backup of all chats, memory and reminders as JSON.

Files go to the user's Downloads folder (or home), with a name that never overwrites an older file.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import __version__, sources
from .i18n import t


def safe_name(title: str, fallback: str = "chat") -> str:
    """A file name part from a chat title: letters, digits, spaces and dashes only, at most 60 characters."""
    name = re.sub(r"[^\w\- ]+", "", title or "", flags=re.U).strip()
    return re.sub(r"\s+", " ", name)[:60].strip() or fallback


def free_path(folder: Path, stem: str, ext: str) -> Path:
    """folder/stem.ext, or stem (2).ext, stem (3).ext… if that name is taken."""
    p, n = folder / f"{stem}{ext}", 2
    while p.exists():
        p, n = folder / f"{stem} ({n}){ext}", n + 1
    return p


def chat_markdown(title: str, messages: list[dict], lang: str = "en", user: str = "") -> str:
    """One chat as a readable Markdown file."""
    now = dt.datetime.now()
    out = [f"# {title or t('New chat', lang)}", "",
           f"_{t('Saved from Lanterna on {date}', lang, date=f'{now:%Y-%m-%d %H:%M}')}_", ""]
    for m in messages:
        when = dt.datetime.fromtimestamp(m["at"]).strftime("%Y-%m-%d %H:%M") if m.get("at") else ""
        if m["role"] == "user":
            who = user or t("You", lang)
        else:
            who = "Lanterna" + (f" ({m['model']})" if m.get("model") else "")
        out += [f"### {who}" + (f" · {when}" if when else ""), "", str(m["content"]).strip(), ""]
        src = sources.view(m.get("sources", "")) if m["role"] == "assistant" else {}
        for kind, head in (("read", t("Sources:", lang)), ("found", t("Search results: {n}", lang, n=len(src.get("found", []))))):
            if src.get(kind):                          # the links the tools really opened or found
                out += [f"**{head}**", "", *(f"- [{s['label'].replace('[', '(').replace(']', ')')}](<{s['url']}>)"
                                             for s in src[kind]), ""]
    return "\n".join(out).rstrip() + "\n"


def backup(store) -> dict:
    """Everything the user made in Lanterna, as plain data (no keys, no settings secrets)."""
    threads = []
    for th in store.threads():
        threads.append({"title": th["title"], "updated": th["updated"],
                        "messages": [{"role": m["role"], "content": m["content"], "model": m.get("model", ""),
                                      "at": m.get("at")} for m in store.messages(th["id"])]})
    return {"app": "Lanterna", "version": __version__, "saved": dt.datetime.now().isoformat(timespec="seconds"),
            "threads": threads,
            "memory": [f["text"] for f in store.facts()],
            "reminders": [{"text": r["text"], "due": r["due"]} for r in store.reminders()]}


def write_backup(store, folder: Path) -> Path:
    p = free_path(folder, f"Lanterna backup {dt.date.today():%Y-%m-%d}", ".json")
    p.write_text(json.dumps(backup(store), ensure_ascii=False, indent=1), encoding="utf-8")
    return p
