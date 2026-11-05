"""Bug reports. The user writes what went wrong, sees the exact text, and sends it themselves:
from their own mail app (a ready letter) or as a GitHub issue. Lanterna never sends a report on its own.

What is added (only when "add app and system info" is on): Lanterna version and kind of install,
the system and Python versions, interface language, mode, service, model, and the last few errors.
Never: chats, memory, the user's name, keys, e-mail addresses or personal folders.
"""
from __future__ import annotations

import os
import platform
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import quote

from . import HOMEPAGE, __version__

# The address reports go to. Empty until the project has its own mailbox; then only GitHub is offered.
# LANTERNA_BUG_EMAIL overrides it (for testing).
BUG_EMAIL = ""

MAX_TEXT = 4000            # what the user can type
MAIL_LIMIT = 1900          # longer mailto: links fail in some mail apps (Windows passes ~2000 characters)
ISSUE_LIMIT = 7000         # GitHub accepts long links, browsers too

_errors: deque[tuple[str, str, str]] = deque(maxlen=3)
_KEYLIKE = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,}\b")
_MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def email() -> str:
    addr = os.environ.get("LANTERNA_BUG_EMAIL", BUG_EMAIL).strip()
    return addr if _MAIL.fullmatch(addr) else ""


def scrub(text: str) -> str:
    """Removes what must not leave the computer from text Lanterna adds itself (error messages)."""
    text = str(text or "")
    home = str(Path.home())
    for h in {home, home.replace("\\", "/")}:
        if len(h) > 3:
            text = text.replace(h, "~")
    text = _MAIL.sub("[e-mail]", text)
    return _KEYLIKE.sub("[hidden]", text)


def remember_error(kind: str, message: str) -> None:
    """Called when a reply fails, so a report can say what the last errors were."""
    _errors.append((time.strftime("%H:%M"), str(kind or "other")[:20], scrub(message)[:200]))


def recent_errors() -> list[str]:
    return [f"{at} {kind}: {msg}" for at, kind, msg in _errors]


def _system() -> str:
    if sys.platform == "win32":
        ver = platform.version()                       # 10.0.26200 — build 22000+ is Windows 11
        try:
            name = "Windows 11" if int(ver.split(".")[2]) >= 22000 else f"Windows {platform.release()}"
        except (IndexError, ValueError):
            name = f"Windows {platform.release()}"
        return f"{name} ({ver})"
    if sys.platform.startswith("linux"):
        try:
            info = platform.freedesktop_os_release()
            name = info.get("PRETTY_NAME") or info.get("NAME") or "Linux"
        except (OSError, AttributeError):
            name = "Linux"
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        return f"{name}{' · ' + desktop if desktop else ''} · kernel {platform.release()}"
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}"
    return platform.platform()


def system_info(settings=None, model: str = "") -> list[str]:
    from .updates import install_kind
    lines = [f"Lanterna {__version__} ({install_kind()})",
             f"System: {_system()} · {platform.machine()}",
             f"Python {platform.python_version()}"]
    if settings is not None:
        lines.append(f"Language: {settings.lang} · mode: {settings.mode} · service: {settings.provider or '-'}")
    if model:
        lines.append(f"Model: {scrub(model)}")
    errs = recent_errors()
    if errs:
        lines.append("Last errors:")
        lines += [f"  {e}" for e in errs]
    return lines


def _subject(text: str) -> str:
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    first = first[:70] + ("…" if len(first) > 70 else "")
    return f"Lanterna {__version__} bug: {first}" if first else f"Lanterna {__version__} bug report"


def _mailto(addr: str, subject: str, body: str) -> str:
    return f"mailto:{addr}?subject={quote(subject)}&body={quote(body)}"


def compose(text: str, include_info: bool = True, settings=None, model: str = "", extra: list[str] | None = None) -> dict:
    """The report as the user will see it, plus ready links. `cut` means the letter had to be shortened
    (the full text should then be copied and pasted into the mail)."""
    text = str(text or "").strip()[:MAX_TEXT]
    info = (system_info(settings, model) + [scrub(x) for x in (extra or [])]) if include_info else []
    body = text + ("\n\n---\n" + "\n".join(info) if info else "")
    subject = _subject(text)
    addr = email()
    out = {"ok": bool(text), "subject": subject, "body": body, "email": addr, "mailto": "", "cut": False,
           "issue": f"{HOMEPAGE}/issues/new?title={quote(subject)}&body={quote(body)}"[:ISSUE_LIMIT]}
    if addr:
        url = _mailto(addr, subject, body)
        if len(url) > MAIL_LIMIT:                       # keep the system info, shorten the description
            note = "\n[…shortened: the full text is in the clipboard]"
            keep = len(text)
            while keep > 0 and len(url) > MAIL_LIMIT:
                keep = int(keep * 0.85)
                short = text[:keep].rstrip() + note + ("\n\n---\n" + "\n".join(info) if info else "")
                url = _mailto(addr, subject, short)
            out["cut"] = True
        out["mailto"] = url
    if len(out["issue"]) >= ISSUE_LIMIT:                # never a broken %-escape at the end
        out["issue"] = re.sub(r"%[0-9A-F]?$", "", out["issue"])
    return out


def valid_mailto(url: str) -> bool:
    """Only a letter to the project's own address may be opened."""
    addr = email()
    return bool(addr) and isinstance(url, str) and url.startswith(f"mailto:{addr}?") and len(url) <= MAIL_LIMIT + 50 \
        and not any(c in url for c in "\n\r\"'<> ")
