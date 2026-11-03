"""How much of each free limit is left.

Two sources, both local:
- what the service itself says in its answer headers (Groq, Cerebras, Mistral, GitHub Models send
  "x-ratelimit-remaining-…"; Google Gemini sends nothing);
- Lanterna's own count of requests per model today, and the limit a service named in its "limit reached" message
  (Gemini: "… limit: 20, model: …").
Nothing is sent anywhere: the numbers are only shown in Settings → Limits. Kept in limits.json next to the settings.
"""
from __future__ import annotations

import json
import re
import threading
import time

from .config import data_dir

_HDR = re.compile(r"^x-ratelimit-(limit|remaining|reset)-(requests|tokens)(?:-(minute|hour|day|month))?$")
# When a header has no period in its name, the service's documented one.
_DEFAULT_PERIOD = {"groq": {"requests": "day", "tokens": "minute"}, "github": {"requests": "day", "tokens": "minute"}}
_LIMIT_IN_MSG = re.compile(r"\blimit:\s*(\d+)", re.I)
LONG_REST = 10 * 60          # longer waits are kept in limits.json, so a restart doesn't try that model again


def _seconds(v: str) -> float | None:
    """'7.66s', '2m59.5s', '1h2m', '12', '850ms' -> seconds."""
    v = (v or "").strip().lower()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        pass
    total, found = 0.0, False
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", v):
        found = True
        total += float(num) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if found else None


class Limits:
    def __init__(self, path=None, clock=time.time):
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._data: dict | None = None

    # -- storage
    def _file(self):
        return self._path or data_dir() / "limits.json"

    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self._file().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}
            self._data.setdefault("models", {})
        day = time.strftime("%Y-%m-%d", time.localtime(self._clock()))
        if self._data.get("day") != day:                 # a new day: the counts start again
            self._data["day"] = day
            for m in self._data["models"].values():
                m["requests"], m["refused"] = 0, 0
        return self._data

    def _save(self) -> None:
        try:
            f = self._file()
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
        except OSError:
            pass

    # -- recording
    def note(self, provider: str, model: str, status: int, headers=None, message: str = "",
             retry_after: float | None = None) -> None:
        """Called for every answer from a cloud service (success or error)."""
        now = self._clock()
        with self._lock:
            d = self._load()
            m = d["models"].setdefault(f"{provider}/{model}", {"provider": provider, "model": model,
                                                                 "requests": 0, "refused": 0, "headers": {}})
            m["at"] = now
            if status == 200:
                m["requests"] += 1
            elif status == 429:
                m["refused"] += 1
                m["limited_at"] = now
                hit = _LIMIT_IN_MSG.search(message or "")
                if hit:
                    m["limit"] = int(hit.group(1))
                if retry_after and retry_after > LONG_REST:      # e.g. the daily limit: remember it across restarts
                    m["rest_until"] = now + retry_after
            hs = {}
            for k, v in (headers or {}).items():
                g = _HDR.match(k.lower())
                if not g:
                    continue
                what, kind, period = g.groups()
                period = period or _DEFAULT_PERIOD.get(provider, {}).get(kind, "")
                key = f"{kind}:{period}"
                slot = hs.setdefault(key, {"kind": kind, "period": period})
                if what == "reset":
                    secs = _seconds(v)
                    if secs is not None:
                        slot["reset_at"] = secs if secs > 1e9 else now + secs
                else:
                    try:
                        slot[what] = int(float(v))
                    except ValueError:
                        pass
            if hs:
                m["headers"] = hs
            self._save()

    # -- reading
    def rest_until(self, provider: str, model: str) -> float:
        """Wall-clock time until which the service said this model is out of its limit (0 = not resting)."""
        with self._lock:
            m = self._load()["models"].get(f"{provider}/{model}")
            return float(m.get("rest_until", 0)) if m else 0.0

    def view(self, resting: dict | None = None) -> list[dict]:
        """Per model: used today, what the service says is left, and whether it is resting after a limit."""
        now = self._clock()
        resting = resting or {}
        with self._lock:
            d = self._load()
            out = []
            for key, m in d["models"].items():
                left = []
                for h in m.get("headers", {}).values():
                    if "remaining" not in h:
                        continue
                    reset = h.get("reset_at")
                    if reset and reset < now:            # the window has passed since we saw it: it is full again
                        continue
                    left.append({"kind": h["kind"], "period": h["period"], "remaining": h["remaining"],
                                 "limit": h.get("limit"), "reset_in": round(reset - now) if reset else None})
                limit = m.get("limit")
                out.append({"provider": m["provider"], "model": m["model"], "used": m.get("requests", 0),
                            "refused": m.get("refused", 0), "limit": limit,
                            "left": left, "resting": _rest(resting.get(key), m.get("rest_until", 0) - now),
                            "at": m.get("at", 0)})
        out.sort(key=lambda x: (x["provider"], -x["at"]))
        return [x for x in out if x["used"] or x["refused"] or x["left"] or x["resting"]]


def _rest(a: float | None, b: float) -> int | None:
    best = max(a or 0, b or 0)
    return round(best) if best > 0 else None


TRACKER = Limits()
