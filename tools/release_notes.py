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
    sys.stdout.write(section(changelog.read_text(encoding="utf-8"), sys.argv[1]))
