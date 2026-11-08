"""Print one version's section of CHANGELOG.md (used as the release text; the app shows its "- " lines in the update card).

    python tools/release_notes.py 0.1.1
"""
from __future__ import annotations

import sys
from pathlib import Path


def section(text: str, version: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().split(" ")[0] == version
        if inside:
            out.append(line)
    return "\n".join(out).strip() + "\n" if out else ""


if __name__ == "__main__":
    changelog = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    sys.stdout.reconfigure(encoding="utf-8")
    text, version = changelog.read_text(encoding="utf-8"), sys.argv[1]
    notes = section(text, version)
    if not notes and any(c.isalpha() for c in version):          # a test version (1.1.6b1): what is not released yet
        body = section(text, "Unreleased")
        notes = (f"## {version} — test version\n\nFor testing before the release; the app doesn't offer it as an "
                 "update.\n" + body.split("\n", 1)[1]) if body else ""
    sys.stdout.write(notes)
