"""Is there a newer Lanterna? Asks the project's public release list when the app starts (can be turned off) and in About.

Sends nothing about the user: a plain GET of the latest release, no IDs, no stats.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

from . import HOMEPAGE, __version__

# The project page is <host>/<owner>/<repo>; its release list lives on api.<host>.
_REPO = "/".join(HOMEPAGE.rstrip("/").split("/")[-2:])
_API = HOMEPAGE.rstrip("/").replace("//", "//api.", 1).rsplit("/", 2)[0]


def _parts(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def newer(latest: str, current: str = __version__) -> bool:
    return _parts(latest) > _parts(current)


def check(transport: httpx.BaseTransport | None = None) -> dict:
    """{"current", "latest", "newer", "url", "notes", "assets"}; latest is "" when the check failed (offline, not published yet)."""
    out = {"current": __version__, "latest": "", "newer": False, "url": HOMEPAGE + "/releases/latest", "notes": [], "assets": {}}
    try:
        with httpx.Client(base_url=_API, timeout=6, transport=transport,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "Lanterna"}) as c:
            r = c.get(f"repos/{_REPO}/releases/latest")
        if r.status_code == 200:
            data = r.json()
            out["latest"] = str(data.get("tag_name", "")).lstrip("v")
            out["newer"] = bool(out["latest"]) and newer(out["latest"])
            out["notes"] = release_notes(str(data.get("body") or ""), out["latest"])
            out["assets"] = {str(a["name"]): str(a["browser_download_url"]) for a in data.get("assets") or []
                             if isinstance(a, dict) and a.get("name") and a.get("browser_download_url")}
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return out


def release_notes(body: str, version: str, limit: int = 6) -> list[str]:
    """The first few "- " lines of this version's section in the release text (the changelog)."""
    out, inside = [], False
    for line in body.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(version) and line[3:].strip().split(" ")[0] == version
        elif inside and line.lstrip().startswith("- "):
            out.append(line.strip()[2:].strip())
    return out[:limit]


def install_kind() -> str:
    """How this copy was installed, so the update steps fit: installer | portable | pipx | source | pip."""
    if getattr(sys, "frozen", False):
        return "installer" if (Path(sys.executable).parent / "unins000.exe").exists() else "portable"
    if "pipx" in Path(sys.prefix).as_posix().lower():
        return "pipx"
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists() and (root / "pyproject.toml").exists():
        return "source"
    return "pip"


SAME_DATA = "Your chats, settings and keys stay as they are."


def how_to(kind: str, latest: str, assets: dict | None = None) -> dict:
    """What to do for this kind of install: steps (English; the caller translates), a command to copy, a download link."""
    assets = assets or {}
    page = HOMEPAGE + "/releases/latest"
    if kind == "installer":
        name = f"Lanterna-Setup-{latest}.exe"
        return {"steps": ["Press Download and save {file}.", "Close Lanterna, then run the file you downloaded.",
                          "If Windows says “Windows protected your PC”, choose More info → Run anyway.", SAME_DATA],
                "file": name, "command": "", "download": assets.get(name, page)}
    if kind == "portable":
        name = f"Lanterna-{latest}-portable-windows.zip"
        return {"steps": ["Press Download and save {file}.", "Close Lanterna, unzip the new folder and use it instead of the old one.",
                          SAME_DATA],
                "file": name, "command": "", "download": assets.get(name, page)}
    if kind == "source":
        return {"steps": ["Close Lanterna.", "In the project folder run:", "Start Lanterna again."],
                "file": "", "command": "git pull && pip install -e .", "download": ""}
    command = "pipx upgrade lanterna" if kind == "pipx" else "pip install --upgrade git+" + HOMEPAGE
    return {"steps": ["Close Lanterna.", "Open a terminal and run:", "Start Lanterna again. " + SAME_DATA],
            "file": "", "command": command, "download": ""}
