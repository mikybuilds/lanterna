"""«Sources» under a reply: the web pages its tools really opened, and the search results the model saw.

Taken only from what the tools brought back (read_page, web_search), never from links the model wrote, so a
made-up address can't pass for a source. Kept with the reply on this computer only (not synced). A link that
looks like a scam is never shown.
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
    """One answer's toolbox: the same tools, and it notes which web pages they really opened or found."""

    def __init__(self, box):
        object.__setattr__(self, "_box", box)
        object.__setattr__(self, "read", [])        # [url] of pages read_page opened (after redirects)
        object.__setattr__(self, "found", [])       # [(title, url)] web_search brought back

    def __getattr__(self, name):                    # store, tools, schemas, focus…: the box's own
        return getattr(self._box, name)

    def __setattr__(self, name, value):             # focus and page_limit go to the box that uses them
        setattr(self._box, name, value)

    def run(self, name: str, arguments: str) -> str:
        out = self._box.run(name, arguments)
        if isinstance(out, str) and name == "read_page" and out.startswith("Page "):
            self.read.append(out.split("\n", 1)[0][5:].removesuffix(":"))
        elif isinstance(out, str) and name == "web_search" and out.startswith("Web results"):
            self.found += [(" ".join(title.split()), url) for title, url in _HIT.findall(out)]
        return out

    def data(self) -> dict:
        """{"read": [{"title", "url"}], "found": [{"title", "url"}]}, or {} when no page was opened or found.
        A page that was found and then opened is under "read", with its title from the search."""
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
        return out if out["read"] or out["found"] else {}


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


def view(raw: str) -> dict:
    """For display: {"read": [{"url", "site", "label"}], "found": [...]}; {} when nothing was noted (older replies).
    The scam check runs again, so a link a newer version knows as fake isn't shown either."""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list] = {"read": [], "found": []}
    for kind in out:
        for x in data.get(kind) or []:
            url = x.get("url") if isinstance(x, dict) else None
            if isinstance(url, str) and _ok(url):
                # a page without a title from the search: its address, readable ("/wiki/Львів", not "%D0%9B…")
                plain = site(url) + (unquote(urlsplit(url).path).rstrip("/") if kind == "read" else "")
                out[kind].append({"url": url, "site": site(url), "label": _cut(str(x.get("title") or "") or plain)})
    return out if out["read"] or out["found"] else {}
