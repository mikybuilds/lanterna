"""Tools the model can call: weather, web search, reading a page, math, dates, memory and reminders.

All of them work without keys. Numbers and dates are computed here, never guessed by the model.
Text that comes back from the web is data for the model, not instructions (the system prompt says so).
"""
from __future__ import annotations

import ast
import datetime as dt
import html
import ipaddress
import json
import math
import operator
import re
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Callable

import httpx

from . import HOMEPAGE, __version__, convert

UA = f"Lanterna/{__version__} (+{HOMEPAGE}; open-source assistant)"  # sites like Wikipedia want a contact link
TIMEOUT = 15.0
PAGE_LIMIT = 4000                   # characters of a page given to the model (free tiers count tokens)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[..., str]
    label: str                       # short text the UI shows while it runs
    group: str = ""                  # "" = always offered; otherwise only when the talk is about it (see GROUPS)

    def schema(self) -> dict:
        params = self.parameters
        if self.group in INTENT_GROUPS or self.name in INTENT_TOOLS:   # the user sees why it searches or looks at their PC
            params = {**params, "properties": {**params.get("properties", {}), "intent": INTENT}}
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": params}}


# "Why" for the "what I'm doing" line. Only on web and computer tools: every extra word costs tokens on free plans.
INTENT_TOOLS = {"web_search", "read_page"}
INTENT_GROUPS = {"pc", "apps", "sys"}
INTENT = {"type": "string", "description": "optional: why you call it, 3-8 words in the user's language, "
                                           "e.g. 'to find the exact function name' (shown to the user)"}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


def _http(**kw) -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=False, **kw)


# ------------------------------------------------------------------------------------------- math
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log, "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
          "min": min, "max": max}
_CONST = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONST:
        return _CONST[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e6 and b > 10):
            raise ValueError("number too large")
        return _OPS[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("only numbers, + - * / // % ** ( ) and sqrt, round, abs, sin, cos, tan, log, exp, min, max")


def calculate(expression: str) -> str:
    expr = str(expression).replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", ".")
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr) if "%" in expr and not re.search(r"\d\s*%\s*\d", expr) else expr
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:                                            # noqa: BLE001
        return f"Error: {e}"
    if isinstance(value, float):
        value = round(value, 10)
        if value.is_integer() and abs(value) < 1e15:
            value = int(value)
    return f"{expression} = {value}"


# ------------------------------------------------------------------------------------------- dates
def _date(s: str | None, today: dt.date) -> dt.date:
    s = (s or "").strip().lower()
    if s in ("", "today", "сьогодні", "oggi"):
        return today
    if s in ("tomorrow", "завтра", "domani"):
        return today + dt.timedelta(days=1)
    return dt.date.fromisoformat(s[:10])


def date_calc(op: str, date: str = "", date2: str = "", days: int = 0, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    try:
        d1 = _date(date, today)
        if op == "between":
            d2 = _date(date2, today)
            n = (d2 - d1).days
            return f"From {d1:%A %Y-%m-%d} to {d2:%A %Y-%m-%d}: {n} days ({abs(n) // 7} weeks and {abs(n) % 7} days)."
        if op == "add":
            d2 = d1 + dt.timedelta(days=int(days))
            return f"{d1:%Y-%m-%d} {'+' if int(days) >= 0 else '-'} {abs(int(days))} days = {d2:%A %Y-%m-%d}."
        if op == "weekday":
            return f"{d1:%Y-%m-%d} is a {d1:%A}."
    except (ValueError, TypeError) as e:
        return f"Error: {e}. Use dates like 2026-12-25."
    return "Error: op must be between, add or weekday"


# ------------------------------------------------------------------------------------------- weather
_WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog", 51: "light drizzle",
        53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
        67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "showers",
        81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorm",
        96: "thunderstorm with hail", 99: "thunderstorm with hail"}
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def weather(place: str, days: int = 1, lang: str = "en", http: httpx.Client | None = None) -> str:
    days = max(1, min(7, int(days or 1)))
    c = http or _http()
    try:
        g = c.get(GEO_URL, params={"name": place, "count": 1, "language": lang, "format": "json"}).json()
        if not g.get("results"):
            return f"No place called {place!r} was found."
        p = g["results"][0]
        where = ", ".join(x for x in (p.get("name"), p.get("admin1"), p.get("country")) if x)
        f = c.get(FORECAST_URL, params={
            "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": days,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}).json()
        out = [f"Weather for {where} (Open-Meteo):"]
        cur = f.get("current") or {}
        if cur:
            out.append(f"Now: {cur.get('temperature_2m')}°C (feels {cur.get('apparent_temperature')}°C), "
                       f"{_WMO.get(cur.get('weather_code'), 'unknown')}, wind {cur.get('wind_speed_10m')} km/h, "
                       f"humidity {cur.get('relative_humidity_2m')}%.")
        d = f.get("daily") or {}
        for i, day in enumerate(d.get("time", [])):
            out.append(f"{day}: {d['temperature_2m_min'][i]}…{d['temperature_2m_max'][i]}°C, "
                       f"{_WMO.get(d['weather_code'][i], 'unknown')}, rain chance {d['precipitation_probability_max'][i]}%.")
        try:
            a = c.get(AIR_URL, params={"latitude": p["latitude"], "longitude": p["longitude"],
                                       "current": "european_aqi,pm2_5"}).json().get("current") or {}
            if a.get("european_aqi") is not None:
                aqi = a["european_aqi"]
                word = "good" if aqi <= 20 else "fair" if aqi <= 40 else "moderate" if aqi <= 60 else "poor" if aqi <= 80 else "very poor"
                out.append(f"Air quality: European AQI {aqi} ({word}), PM2.5 {a.get('pm2_5')} µg/m³.")
        except (httpx.HTTPError, ValueError):
            pass
        return "\n".join(out)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return f"Error: weather service unavailable ({e.__class__.__name__})."
    finally:
        if http is None:
            c.close()


# ------------------------------------------------------------------------------------------- web
SEARCH_URL = "https://html.duckduckgo.com/html/"
_RESULT = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=class="result__a"|$)', re.S)
_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s))).strip()


def _real_url(href: str) -> str:
    href = html.unescape(href)
    if "uddg=" in href:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        href = q.get("uddg", [href])[0]
    return "https:" + href if href.startswith("//") else href


def web_search(query: str, max_results: int = 5, http: httpx.Client | None = None) -> str:
    c = http or _http()
    try:
        r = c.post(SEARCH_URL, data={"q": query, "kl": "wt-wt"})
        if r.status_code != 200:
            return f"Error: search unavailable (HTTP {r.status_code})."
        out = []
        for m in _RESULT.finditer(r.text):
            url = _real_url(m.group(1))
            if not url.startswith("http") or "duckduckgo.com/y.js" in url:      # skip ads
                continue
            sn = _SNIPPET.search(m.group(3))
            out.append(f"{len(out) + 1}. {_clean(m.group(2))}\n   {url}\n   {(_clean(sn.group(1)) if sn else '')[:240]}")
            if len(out) >= max_results:
                break
        if out:
            return "Web results (DuckDuckGo):\n" + "\n".join(out)
        if "no-results" in r.text or "No results" in r.text:
            return "No results found."
        # not a results page: a "are you a robot" check, or the page changed — not the same as "nothing found"
        return ("Error: web search isn't working right now (the search page asked for a check or changed). "
                "Tell the user that search failed; don't present guesses as fresh facts.")
    except httpx.HTTPError as e:
        return f"Error: search unavailable ({e.__class__.__name__})."
    finally:
        if http is None:
            c.close()


def _public_host(host: str) -> bool:
    """Only public internet addresses: never this computer or the local network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head|nav|footer)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", raw)
    text = html.unescape(_TAG.sub(" ", raw))
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


_WORD = re.compile(r"\w{3,}", re.U)
HEAD_KEEP = 300                     # the start of a page (title, intro) is always kept
HEADING = 80                        # a shorter line is probably a heading: the lines after it come along
LONG_LINE = 500                     # longer paragraphs are split into sentences, so a part of one can be picked
_SENT_END = re.compile(r"(?<=[.!?])\s+")


def _sentences(line: str) -> list[str]:
    if len(line) <= LONG_LINE:
        return [line]
    out, cur = [], ""
    for s in _SENT_END.split(line):                     # pieces of about 250-500 characters
        if cur and len(cur) + len(s) > LONG_LINE // 2:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}" if cur else s
    return [*out, cur] if cur else out


def _stems(text: str) -> set[str]:
    """Rough word stems: the first 5 letters, so "flowgorithm"/"Flowgorithm's", "великої"/"великою" match."""
    return {w[:5] for w in _WORD.findall(text.lower()) if not w.isdigit()}


def focus_excerpt(text: str, focus: str, limit: int = PAGE_LIMIT) -> tuple[str, bool]:
    """The parts of a long page that fit the question, in page order, within `limit` characters.
    No model call: lines are scored by the question's words (rare words count more). Returns (text, was_cut)."""
    if len(text) <= limit:
        return text, False
    want = _stems(focus)
    lines = [part for ln in text.split("\n") for part in _sentences(ln)]
    stems = [_stems(ln) for ln in lines]
    df = {w: sum(w in s for s in stems) for w in want}
    # rare question words count more; short lines (headings) that match count more than long ones that touch a word
    score = [sum(math.log(1 + len(lines) / df[w]) for w in want & s if df[w]) / math.log(3 + len(s)) for s in stems]
    if not want or max(score, default=0) == 0:
        return text[:limit], True                       # nothing matches: the start of the page, as before
    keep, used = set(), 0
    for i, ln in enumerate(lines):                      # the head of the page
        if used >= HEAD_KEEP:
            break
        keep.add(i)
        used += len(ln) + 1
    for i in sorted(range(len(lines)), key=lambda i: -score[i]):
        if score[i] == 0 or used >= limit:
            break
        # the line with its neighbours; under a heading, the text that follows it
        near = (i, i + 1, i + 2, i + 3) if len(lines[i]) < HEADING else (i, i - 1, i + 1)
        for j in near:
            if 0 <= j < len(lines) and j not in keep and used + len(lines[j]) + 1 <= limit:
                keep.add(j)
                used += len(lines[j]) + 1
    out, prev = [], -1
    for i in sorted(keep):
        if i != prev + 1:
            out.append("[…]")
        out.append(lines[i])
        prev = i
    return "\n".join(out)[:limit], True


def read_page(url: str, http: httpx.Client | None = None, check_host: Callable[[str], bool] = _public_host,
              focus: str = "", limit: int = PAGE_LIMIT) -> str:
    c = http or _http()
    try:
        for _ in range(4):                                        # follow up to 3 redirects, checking each host
            parts = urllib.parse.urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                return "Error: only http(s) links can be opened."
            if not check_host(parts.hostname):
                return "Error: this address is not on the public internet."
            r = c.get(url)
            if r.is_redirect and r.headers.get("location"):
                url = urllib.parse.urljoin(url, r.headers["location"])
                continue
            break
        else:
            return "Error: too many redirects."
        if r.status_code != 200:
            return f"Error: the page answered HTTP {r.status_code}."
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype and "json" not in ctype:
            return f"Error: not a text page ({ctype or 'unknown type'})."
        text = page_text(r.text) if "html" in ctype else r.text
        text, cut = focus_excerpt(text, focus, limit)
        return f"Page {url}:\n{text}" + ("\n[…page cut: only the parts that fit the question are shown]" if cut else "")
    except httpx.HTTPError as e:
        return f"Error: could not open the page ({e.__class__.__name__})."
    finally:
        if http is None:
            c.close()


# ------------------------------------------------------------------------------------------- registry
def parse_when(at: str = "", in_minutes: float = 0, now: dt.datetime | None = None) -> dt.datetime | None:
    now = now or dt.datetime.now()
    if in_minutes:
        return now + dt.timedelta(minutes=float(in_minutes))
    at = (at or "").strip().replace("T", " ")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        if len(at) != n:
            continue
        try:
            when = dt.datetime.strptime(at, fmt)
        except ValueError:
            continue
        return when.replace(hour=9) if n == 10 else when          # a date alone means 9:00 that day
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", at)
    if m:
        when = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return when if when > now else when + dt.timedelta(days=1)
    return None


GROUPS = {
    # regular tasks: only offered when the talk is about doing something on a schedule
    "tasks": re.compile(r"щодн|щоранк|щовеч|щотижн|щогодин|щопонед|кожн\w* (ранк|ден|дня|веч|тижн|годин|понеділ|вівтор|серед|"
                        r"четвер|п.ятниц|субот|неділ)|по буднях|регулярн|завдан|розклад|нагад\w* кожн|"
                        r"every (day|morning|evening|night|week|hour|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                        r"daily|weekly|hourly|each (day|morning|evening|week)|regular|\btasks?\b|schedul|on weekdays|"
                        r"ogni (giorno|mattina|sera|settimana|ora|lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)|"
                        r"quotidian|settimanal|attivit|jeden (tag|morgen|abend|montag)|täglich|wöchentlich|stündlich|aufgabe|"
                        r"cada (día|mañana|noche|semana|hora|lunes)|diari|semanal|tarea|chaque (jour|matin|soir|semaine|heure|lundi)|"
                        r"quotidien|hebdomadaire|tâche|codzien|co (dzień|rano|wieczór|tydzień|godzin|poniedział)|zadani|"
                        r"каждый|ежеднев|расписан", re.I),
    # earlier chats: only when the user talks about something said before
    "chats": re.compile(r"раніше|минул\w* раз|того разу|говорил|обговорюв|розмовля|казав|казала|писав|писала|питав|питала|"
                        r"\bчат|розмов|переписк|ти (мені )?(радив|казав|писав)|we (talked|discussed|spoke|chatted)|"
                        r"you (told|said|wrote|suggested)|last time|earlier|previous|\bchats?\b|conversation|"
                        r"remember when|l.altra volta|abbiamo parlato|mi hai detto|\bchat\b|conversazion|letztes mal|"
                        r"haben wir|du hast mir|gespräch|la última vez|hablamos|me dijiste|conversaci|la dernière fois|"
                        r"on a parlé|tu m.as dit|conversation|ostatnio|rozmawiali|mówiłeś|rozmow|раньше|говорили|"
                        r"прошл\w* раз", re.I),
    "pc": re.compile(r"завантаж|скачан|download|робоч\w* стол|desktop|документ|document|зображен|картинк|фотк|pictures|"
                     r"відео|video|музик|music|папк|folder|файл|file|сорт|розклад|розбер|прибер|навед\w* поряд|дублікат|"
                     r"duplicate|кошик|trash|recycle|видали|delete|scaric|scrivania|cartell|ordina|immagini|musica|"
                     r"cestino|elimina|sort|organi[sz]e|clean ?up|tidy|місц|space|spazio|диск|disk|storage|звільн|free up|libera|"
                     r"сміт|junk|займа|takes up|occupa", re.I),
    "apps": re.compile(r"встанов|установ|інстал|install|програм|додат|застосун|\bapp|онов|update|upgrade|uninstall|winget|"
                       r"flatpak|dnf\b|installa|aggiorna|programm|applicazion|software|видали", re.I),
    "sys": re.compile(r"\bпк\b|\bpc\b|комп.ютер|computer|ноутбук|laptop|гальм|лаг|повільн|тормоз|slow|lent|"
                      r"автозапуск|startup|avvio|тем(а|у|н)|theme|dark|light|світл|живлен|power|energia|батаре|battery|"
                      r"диск|disk|місц|space|spazio|пам.ят|ram\b|memor|процесор|cpu|processor|налашт|настро|setting|"
                      r"impostaz|bluetooth|wi-?fi|звук|sound|audio|екран|display|schermo|характеристик|specs?\b|відеокарт|"
                      r"gpu|видеокарт|оновлен|windows|fedora|linux", re.I),
}


_CHAT_FILE = re.compile(r"\[File: ([^\]\n]+)\]\n```.*?```", re.S)
LOOKUP_TOOLS = ("calculate", "date_calc", "currency", "convert_units", "weather", "web_search", "read_page")


class LookupOnly:
    """The same toolbox, but only tools that look things up: a second opinion changes nothing (no memory,
    reminders, files, PC or outside tools)."""

    def __init__(self, box: "Toolbox"):
        self._box = box
        self.store = box.store
        self.focus = ""
        self.page_limit = PAGE_LIMIT

    @property
    def tools(self) -> dict:
        return {k: v for k, v in self._box.tools.items() if k in LOOKUP_TOOLS}

    def schemas(self, context: str | None = None) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def run(self, name: str, arguments: str) -> str:
        if name not in LOOKUP_TOOLS:
            return f"Error: there is no tool called {name}."
        self._box.focus, self._box.page_limit = self.focus, self.page_limit
        return self._box.run(name, arguments)


class Toolbox:
    """The tools for one app session. Memory and reminders live in the local database (store)."""

    def __init__(self, store, lang: Callable[[], str] = lambda: "en", now: Callable[[], dt.datetime] = dt.datetime.now,
                 extra: Callable[[], list[Tool]] | None = None):
        self.store, self._lang, self._now = store, lang, now
        self._base: dict[str, Tool] = {t.name: t for t in self._make()}
        self._extra = extra or (lambda: [])          # tools that come and go (working folder, Google Drive)
        self.focus = ""                              # the question being answered: read_page keeps the parts that fit it
        self.page_limit = PAGE_LIMIT                 # page characters for the current model (set by the chat)

    @property
    def tools(self) -> dict[str, Tool]:
        return {**self._base, **{t.name: t for t in self._extra()}}

    def schemas(self, context: str | None = None) -> list[dict]:
        """All tools, except groups (the user's folders, programs, the PC) the recent messages don't touch:
        every tool description costs tokens on free plans, and small models choose better from a short list."""
        on = None if context is None else {g for g, rx in GROUPS.items() if rx.search(context)}
        return [t.schema() for t in self.tools.values() if not t.group or on is None or t.group in on]

    def run(self, name: str, arguments: str) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"Error: there is no tool called {name}."
        try:
            args = json.loads(arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError
        except ValueError:
            return "Error: arguments must be a JSON object."
        args.pop("intent", None)                                     # only for the "what I'm doing" line
        try:
            return tool.run(**args)
        except TypeError as e:
            return f"Error: wrong arguments ({e})."
        except Exception as e:                                       # noqa: BLE001  never break the chat
            return f"Error: {e.__class__.__name__}: {e}"

    # memory --------------------------------------------------------------------------------
    def _remember(self, fact: str) -> str:
        fact = " ".join(str(fact).split())[:300]
        if not fact:
            return "Error: empty fact."
        got = self.store.add_fact(fact)
        if got == 0:
            return f"Already in memory: {fact}"
        if got < 0:
            return ("Memory is full, so nothing was saved. Tell the user, and ask which old things to forget "
                    "(they can also remove them in Settings → Memory).")
        return f"Saved to memory: {fact}"

    def _forget(self, fact: str) -> str:
        n = self.store.forget_facts(str(fact))
        return f"Removed {n} matching memory item(s)." if n else "Nothing matching was found in memory."

    # earlier chats -------------------------------------------------------------------------
    CHAT_LIMIT = 6000

    def _search_chats(self, words: str) -> str:
        words = " ".join(str(words).split())[:80]
        found = []
        for w in [words, *sorted(words.split(), key=len, reverse=True)[:3]] if words else []:
            for r in self.store.search(w, limit=8):          # the whole phrase first, then its longest words
                if r["id"] not in {f["id"] for f in found} and not r.get("private"):
                    found.append(r)
            if len(found) >= 8:
                break
        if not found:
            return f"No earlier chat has the words: {words}"
        lines = [f"#{r['id']} «{r['title'] or '…'}» ({dt.datetime.fromtimestamp(r['updated'] or 0):%Y-%m-%d}): "
                 f"{r['snippet']}" for r in found[:8]]
        return "Earlier chats (use read_chat with a number for more):\n" + "\n".join(lines)

    def _read_chat(self, id: int) -> str:
        th = self.store.thread(int(id))
        if not th or th.get("private"):
            return f"Error: there is no chat #{id}."
        parts = []
        for m in self.store.messages(int(id)):
            text = _CHAT_FILE.sub(r"[file \1]", m["content"] or "")
            parts.append(("User: " if m["role"] == "user" else "You: ") + " ".join(text.split()))
        body = "\n".join(parts)
        if len(body) > self.CHAT_LIMIT:                         # long chat: the end matters most
            body = "…" + body[-self.CHAT_LIMIT:]
        return f"Chat #{id} «{th['title'] or '…'}»:\n{body}"

    # reminders -----------------------------------------------------------------------------
    def _set_reminder(self, text: str, at: str = "", in_minutes: float = 0, repeat: str = "") -> str:
        from .store import REPEATS
        now = self._now()
        when = parse_when(at, in_minutes, now)
        if when is None:
            return "Error: give `at` as 'YYYY-MM-DD HH:MM' (local time) or `in_minutes`."
        if when <= now:
            return f"Error: {when:%Y-%m-%d %H:%M} is in the past (now is {now:%Y-%m-%d %H:%M})."
        repeat = str(repeat or "").strip().lower()
        if repeat in ("none", "once", "no"):
            repeat = ""
        if repeat and repeat not in REPEATS:
            return "Error: repeat must be day, weekday, week or month (or empty for once)."
        while repeat == "weekday" and when.weekday() >= 5:
            when += dt.timedelta(days=1)
        rid = self.store.add_reminder(str(text)[:300], when.timestamp(), repeat)
        again = {"day": "every day", "weekday": "on weekdays (Mon-Fri)", "week": "every week",
                 "month": "every month"}.get(repeat)
        return (f"Reminder #{rid} set for {when:%A %Y-%m-%d %H:%M}: {text}" +
                (f". It repeats {again} at {when:%H:%M}; the user can cancel it in Settings → Reminders." if again else ""))

    # regular tasks ---------------------------------------------------------------------------
    def _add_task(self, what: str, every: str = "day", at: str = "08:00", day: int = 0, only_if: str = "") -> str:
        from . import tasks
        try:
            tid, when = tasks.add(self.store, what, every, at, day, only_if, self._now())
        except ValueError as e:
            return f"Error: {e}."
        how = tasks.describe(self.store.task(tid), lambda s, **kw: s.format(**kw))
        return (f"Regular task #{tid} added: {what} — {how}" + (f", only if {only_if}" if only_if else "") +
                f". First run: {when:%A %Y-%m-%d %H:%M}. It runs while Lanterna is open or in the tray; "
                "the user can see, pause or delete it in Settings → Regular tasks.")

    def _list_tasks(self) -> str:
        from . import tasks
        items = self.store.tasks()
        if not items:
            return "No regular tasks."
        en = lambda s, **kw: s.format(**kw)                          # noqa: E731
        return "Regular tasks:\n" + "\n".join(
            f"#{x['id']} {x['text']} — {tasks.describe(x, en)}" + (" (paused)" if x["paused"] else "") for x in items)

    def _delete_task(self, id: int) -> str:                          # noqa: A002  (name the model sees)
        return f"Regular task #{id} deleted." if self.store.delete_task(int(id)) else f"No regular task #{id}."

    def _list_reminders(self) -> str:
        items = self.store.reminders()
        if not items:
            return "No upcoming reminders."
        return "Upcoming reminders:\n" + "\n".join(
            f"#{r['id']} {dt.datetime.fromtimestamp(r['due']):%a %Y-%m-%d %H:%M} — {r['text']}" +
            (f" (repeats: {r['repeat']})" if r.get("repeat") else "") for r in items)

    def _cancel_reminder(self, id: int) -> str:                       # noqa: A002  (name the model sees)
        return f"Reminder #{id} cancelled." if self.store.cancel_reminder(int(id)) else f"No reminder #{id}."

    def _make(self) -> list[Tool]:
        s = {"type": "string"}
        return [
            Tool("calculate", "Exact arithmetic. Always use this for any calculation instead of doing math yourself.",
                 _obj({"expression": {**s, "description": "e.g. (12.5*3)+7^2 or sqrt(2)"}}, ["expression"]),
                 calculate, "🧮"),
            Tool("date_calc", "Exact date math: days between two dates, adding days to a date, or the weekday of a date. "
                 "Dates as YYYY-MM-DD or 'today'.",
                 _obj({"op": {"type": "string", "enum": ["between", "add", "weekday"]}, "date": s, "date2": s,
                       "days": {"type": "integer"}}, ["op", "date"]),
                 lambda **a: date_calc(today=self._now().date(), **a), "📅"),
            Tool("currency", "Convert money between currencies at today's official National Bank of Ukraine rate "
                 "(about 60 currencies). Use it for any exchange-rate question instead of guessing. Codes like USD, EUR, "
                 "PLN, UAH, GBP.",
                 _obj({"amount": {"type": "number"}, "from": {**s, "description": "e.g. USD"},
                       "to": {**s, "description": "e.g. UAH"}}, ["amount", "from", "to"]),
                 lambda amount, **a: convert.currency(amount, a.get("from", ""), a.get("to", "")), "💱"),
            Tool("convert_units", "Exact unit conversion: length, weight, volume (incl. cups, tbsp, gallons), area "
                 "(m2, ha, a = 'sotka', acre), speed, time, data (kb, mb, gb, gib, mbit), energy (kcal, kwh), pressure "
                 "(hpa, mmhg, psi, bar) and temperature (c, f, k). Use short unit names.",
                 _obj({"value": {"type": "number"}, "from": {**s, "description": "e.g. mi"},
                       "to": {**s, "description": "e.g. km"}}, ["value", "from", "to"]),
                 lambda value, **a: convert.convert_units(value, a.get("from", ""), a.get("to", "")), "📏"),
            Tool("weather", "Current weather, forecast (up to 7 days) and air quality for a place.",
                 _obj({"place": {**s, "description": "city name, e.g. Ferrara"},
                       "days": {"type": "integer", "description": "1-7"}}, ["place"]),
                 lambda place, days=1: weather(place, days, self._lang()), "🌤"),
            Tool("web_search", "Search the internet for fresh facts, news, prices, opening hours and so on. "
                 "One short query of key words, not a whole sentence; search again only with really different words.",
                 _obj({"query": {**s, "description": "e.g. 'Flowgorithm uppercase string function' or "
                                                     "'Ferrara museum opening hours'"}}, ["query"]),
                 lambda query: web_search(query), "🔎"),
            Tool("read_page", "Read the text of a web page (for example a link from web_search or from the user). "
                 "Long pages come back as the parts that fit the question.",
                 _obj({"url": s}, ["url"]),
                 lambda url: read_page(url, focus=self.focus, limit=self.page_limit), "📄"),
            Tool("remember", "Save a lasting fact about the user when they share one or ask you to remember something. "
                 "Not for one-time things (today's plans, a single question) — those don't need saving.",
                 _obj({"fact": {**s, "description": "short fact in the language the user writes in, "
                                                    "e.g. 'Is allergic to peanuts' or 'Studies at ITI in Ferrara'"}},
                      ["fact"]),
                 self._remember, "🧠"),
            Tool("forget", "Remove facts from memory that contain this text.", _obj({"fact": s}, ["fact"]),
                 self._forget, "🧠"),
            Tool("set_reminder", "Set a reminder. Use `in_minutes` for 'in 20 minutes' or `at` as local "
                 "'YYYY-MM-DD HH:MM' for a time (the first time, for a repeating one). Examples: 'remind me in half an "
                 "hour to call mum' → text='Call mum', in_minutes=30; 'tomorrow at 8 the bus' → text='Bus', "
                 "at='<tomorrow's date> 08:00'; 'remind me every day at 9 to take my pills' → text='Take the pills', "
                 "at='<the next 09:00>', repeat='day'. repeat: day | weekday (Mon-Fri) | week | month; leave it out "
                 "for once.",
                 _obj({"text": s, "at": s, "in_minutes": {"type": "number"},
                       "repeat": {"type": "string", "enum": ["day", "weekday", "week", "month"]}}, ["text"]),
                 self._set_reminder, "⏰"),
            Tool("list_reminders", "List upcoming reminders.", _obj({}), self._list_reminders, "⏰"),
            Tool("add_task", "Schedule a REGULAR task Lanterna does on its own and then notifies the user. "
                 "every: day | weekday | week (with day 0=Monday..6=Sunday) | hour; at: 'HH:MM' local time. "
                 "Examples: 'every morning at 8 tell me the weather in Kyiv' → what='Short weather forecast for "
                 "today in Kyiv', every='day', at='08:00'; 'tell me in the evening if it will rain tomorrow' → "
                 "what='Check tomorrow's weather in Kyiv', every='day', at='19:00', only_if='it will rain tomorrow'; "
                 "'every Monday at 9 give me 3 tech news' → every='week', day=0, at='09:00'. For a one-time thing "
                 "use set_reminder instead, and for the same fixed words each time ('every day at 9 remind me to take "
                 "my pills') use set_reminder with repeat: it needs no model. Put the city or details the task needs "
                 "into `what`.",
                 _obj({"what": s, "every": {"type": "string", "enum": ["day", "weekday", "week", "hour"]}, "at": s,
                       "day": {"type": "integer"}, "only_if": s}, ["what", "every"]), self._add_task, "🔁", "tasks"),
            Tool("list_tasks", "List the regular tasks.", _obj({}), self._list_tasks, "🔁", "tasks"),
            Tool("delete_task", "Delete a regular task by its number.", _obj({"id": {"type": "integer"}}, ["id"]),
                 self._delete_task, "🔁", "tasks"),
            Tool("cancel_reminder", "Cancel a reminder by its number.", _obj({"id": {"type": "integer"}}, ["id"]),
                 self._cancel_reminder, "⏰"),
            Tool("search_chats", "Search the user's earlier chats with you (saved on this computer) for words, when "
                 "they refer to something talked about before ('what did you suggest last week about my bike?'). "
                 "Use one or two key words in the language of that chat; then read_chat for the details.",
                 _obj({"words": s}, ["words"]), self._search_chats, "💬", "chats"),
            Tool("read_chat", "Read an earlier chat found with search_chats (its number), most recent part first if long.",
                 _obj({"id": {"type": "integer"}}, ["id"]), self._read_chat, "💬", "chats"),
        ]
