"""Looks for things that must never be published: API keys, private keys, e-mail addresses, personal paths.

    python tools/scan_secrets.py            # files tracked by git (or all files when git is missing)
    python tools/scan_secrets.py --history  # also every version in the git history

Exits with 1 and prints file:line for each finding. Values are shown masked.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "Groq key": r"gsk_[A-Za-z0-9]{20,}",
    "Google API key": r"AIza[0-9A-Za-z_\-]{30,}",
    "OpenRouter key": r"sk-or-v1-[0-9a-f]{20,}",
    "OpenAI-style key": r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}",
    "GitHub token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}",
    "Cerebras key": r"\bcsk-[a-z0-9]{30,}",
    "Slack/Telegram token": r"\bxox[abpr]-[A-Za-z0-9-]{10,}|\b\d{8,10}:AA[A-Za-z0-9_-]{30,}",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "e-mail address": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "personal path": r"[A-Za-z]:\\Users\\[^\\\s\"']+|/home/[a-z][a-z0-9_-]+/|JarvisBot",
}
# Addresses that are fine to publish (git trailers, placeholders)
ALLOWED_EMAILS = re.compile(r"noreply@|@example\.(?:com|org)|@users\.noreply\.", re.I)
SKIP_DIRS = {".git", ".venv", "build", "dist", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_FILES = {"scan_secrets.py"}                 # this file describes the patterns
BINARY = {".png", ".jpg", ".jpeg", ".ico", ".gif", ".webp", ".pdf", ".exe", ".zip", ".db"}


def _rx():
    return {name: re.compile(p) for name, p in PATTERNS.items()}


def _mask(s: str) -> str:
    return s[:4] + "…" + s[-3:] if len(s) > 10 else "…"


def scan_text(text: str, where: str, rx=None) -> list[str]:
    rx = rx or _rx()
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, r in rx.items():
            for m in r.finditer(line):
                if name == "e-mail address" and ALLOWED_EMAILS.search(m.group(0)):
                    continue
                out.append(f"{where}:{n}: {name}: {_mask(m.group(0))}")
    return out


def tracked_files() -> list[Path]:
    try:
        names = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()
        return [ROOT / n for n in names]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts)]


def scan_files() -> list[str]:
    rx, found = _rx(), []
    for p in tracked_files():
        if p.name in SKIP_FILES or p.suffix.lower() in BINARY or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += scan_text(text, str(p.relative_to(ROOT)), rx)
    return found


def scan_history() -> list[str]:
    """Every added line in every commit (a key removed later is still public in the history)."""
    log = subprocess.run(["git", "log", "-p", "--all", "--no-color", "--format=commit %h"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    rx, found, commit, path = _rx(), [], "", ""
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++") and Path(path).name not in SKIP_FILES:
            found += scan_text(line[1:], f"{commit}:{path}", rx)
    # author e-mails of the commits themselves
    authors = subprocess.run(["git", "log", "--all", "--format=%h %ae %ce"], cwd=ROOT, capture_output=True,
                             text=True).stdout
    for line in authors.splitlines():
        h, *mails = line.split()
        for m in mails:
            if not ALLOWED_EMAILS.search(m):
                found.append(f"{h}: commit author e-mail: {_mask(m)}")
    return sorted(set(found))


def main(argv: list[str]) -> int:
    found = scan_files()
    if "--history" in argv:
        found += scan_history()
    for f in found:
        print(f)
    print(f"{len(found)} finding(s)" if found else "clean: no keys, e-mails or personal paths found")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
