"""Is there a newer Lanterna? Asks the project's public release list, only when the About screen is opened.

Sends nothing about the user: a plain GET of the latest release, no IDs, no stats.
"""
from __future__ import annotations

import re

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
    """{"current", "latest", "newer", "url"}; latest is "" when the check failed (offline, not published yet)."""
    out = {"current": __version__, "latest": "", "newer": False, "url": HOMEPAGE + "/releases/latest"}
    try:
        with httpx.Client(base_url=_API, timeout=6, transport=transport,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "Lanterna"}) as c:
            r = c.get(f"repos/{_REPO}/releases/latest")
        if r.status_code == 200:
            tag = str(r.json().get("tag_name", ""))
            out["latest"] = tag.lstrip("v")
            out["newer"] = bool(out["latest"]) and newer(out["latest"])
    except (httpx.HTTPError, ValueError):
        pass
    return out
