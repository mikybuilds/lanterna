"""«Sources» under a reply: the web pages its tools really opened, and the search results the model saw.

Taken only from what the tools brought back (read_page, web_search), never from links the model wrote, so a
made-up address can't pass for a source. Kept with the reply on this computer only (not synced). A link that
looks like a scam is never shown. pc_disk's figure of the disk (diskmap.figure, drawn above the reply) is kept
the same way, under "disk".
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urlsplit

from .scam import refuse

MAX_READ = 8                    # pages opened for one answer
MAX_FOUND = 10                  # search results it saw
LABEL = 80                      # characters of a title or an address shown
_HIT = re.compile(r"^\d+\. (.+)\n   (https?://\S+)", re.M)       # one result of tools.web_search


def _ok(url: str) -> bool:
    return (url.startswith(("https://", "http://")) and len(url) <= 2000 and bool(urlsplit(url).hostname)
            and not any(c in url for c in "\"'<> \n\r\t") and not refuse(url))


def _key(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


class Noted:
    """One answer's toolbox: the same tools, and it notes which web pages they really opened or found, and the
    figure of the disk the last pc_disk of the whole disk made."""

    def __init__(self, box):
        object.__setattr__(self, "_box", box)
        object.__setattr__(self, "read", [])        # [url] of pages read_page opened (after redirects)
        object.__setattr__(self, "found", [])       # [(title, url)] web_search brought back
        object.__setattr__(self, "disk", None)      # diskmap.figure: the window draws it above the reply

    def __getattr__(self, name):                    # store, tools, schemas, focus…: the box's own
        return getattr(self._box, name)

    def __setattr__(self, name, value):             # focus and page_limit go to the box that uses them
        setattr(self._box, name, value)

    def run(self, name: str, arguments: str) -> str:
        if name == "pc_disk":
            from . import diskmap
            diskmap.take()                          # one left in this thread by a call outside an answer isn't this one
        out = self._box.run(name, arguments)
        if isinstance(out, str) and name == "read_page" and out.startswith("Page "):
            self.read.append(out.split("\n", 1)[0][5:].removesuffix(":"))
        elif isinstance(out, str) and name == "web_search" and out.startswith("Web results"):
            self.found += [(" ".join(title.split()), url) for title, url in _HIT.findall(out)]
        elif name == "pc_disk":
            from . import diskmap
            fig = diskmap.take()
            if fig:
                object.__setattr__(self, "disk", fig)
        return out

    def data(self) -> dict:
        """{"read": [{"title", "url"}], "found": [{"title", "url"}], "disk": figure}, or {} when no page was
        opened or found and the disk wasn't counted. A page that was found and then opened is under "read", with
        its title from the search."""
        titles: dict[str, str] = {}
        for title, url in self.found:
            titles.setdefault(_key(url), title)
        seen: set[str] = set()
        out: dict[str, list] = {"read": [], "found": []}
        for kind, items, most in (("read", [(titles.get(_key(u), ""), u) for u in self.read], MAX_READ),
                                  ("found", self.found, MAX_FOUND)):
            for title, url in items:
                if _ok(url) and _key(url) not in seen and len(out[kind]) < most:
                    seen.add(_key(url))
                    out[kind].append({"title": title[:200], "url": url})
        if self.disk:
            out["disk"] = self.disk
        return out if out["read"] or out["found"] or self.disk else {}


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False) if data else ""


def site(url: str) -> str:
    """The site's name as people write it: "uk.wikipedia.org", "сайт.укр" (not "xn--80aswg.xn--j1amh")."""
    host = urlsplit(url).hostname or ""
    try:
        host = host.encode("ascii").decode("idna")
    except UnicodeError:
        pass
    return host.removeprefix("www.")


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LABEL else text[:LABEL - 1].rstrip() + "…"


MAX_SAVED = 60                  # files (or a playlist's folder) a reply saved, shown under it


def saved(files: list, folder: str = "") -> list[dict]:
    """What a download saved, as it is kept with the reply: [{"path", "size"}], or one {"path", "folder": True}
    for a playlist's folder (the files are in it)."""
    if folder:
        return [{"path": str(folder), "folder": True, "count": len(files)}]
    out = []
    for p in files[:MAX_SAVED]:
        try:
            size = p.stat().st_size
        except (OSError, AttributeError):
            size = 0
        out.append({"path": str(p), "size": size})
    return out


def _saved_view(items) -> list[dict]:
    out = []
    for x in items if isinstance(items, list) else []:
        path = x.get("path") if isinstance(x, dict) else None
        if not isinstance(path, str) or not path or len(path) > 1000 or "\n" in path:
            continue
        name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        item = {"path": path, "label": _cut(name), "folder": x.get("folder") is True}
        for k in ("size", "count"):                     # only when known (a file that is gone has no size)
            if _size(x.get(k)) and x[k] > 0:
                item[k] = x[k]
        out.append(item)
    return out[:MAX_SAVED]


def view(raw: str) -> dict:
    """For display: {"read": [{"url", "site", "label"}], "found": [...], "saved": [{"path", "label", "size"…}]}; {}
    when nothing was noted (older replies). The scam check runs again, so a link a newer version knows as fake isn't
    shown either. "saved": files Lanterna itself saved for this reply (a downloaded video), opened by their path."""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list] = {"read": [], "found": []}
    for kind in ("read", "found"):
        for x in data.get(kind) or []:
            url = x.get("url") if isinstance(x, dict) else None
            if isinstance(url, str) and _ok(url):
                # a page without a title from the search: its address, readable ("/wiki/Львів", not "%D0%9B…")
                plain = site(url) + (unquote(urlsplit(url).path).rstrip("/") if kind == "read" else "")
                out[kind].append({"url": url, "site": site(url), "label": _cut(str(x.get("title") or "") or plain)})
    files = _saved_view(data.get("saved"))
    if files:
        out["saved"] = files
    return out if out["read"] or out["found"] or files else {}


def _size(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def disk(raw: str) -> dict:
    """pc_disk's figure of the disk kept with a reply, for the window; {} when there is none (older replies) or it
    doesn't look like one."""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    fig = data.get("disk") if isinstance(data, dict) else None
    if not isinstance(fig, dict) or not isinstance(fig.get("parts"), list):
        return {}
    parts = [{"size": p["size"], **({"name": p["name"][:LABEL]} if isinstance(p.get("name"), str) else {"kind": p["kind"]})}
             for p in fig["parts"][:8] if isinstance(p, dict) and _size(p.get("size"))
             and (isinstance(p.get("name"), str) or p.get("kind") in ("files", "other"))]
    out = {"disk": str(fig.get("disk") or "")[:LABEL], "parts": parts, "whole": fig.get("whole") is True,
           "low": fig.get("low") is True}
    out.update({k: fig[k] for k in ("total", "used", "free", "counted", "uncounted") if _size(fig.get(k))})
    return out if parts or "total" in out else {}
