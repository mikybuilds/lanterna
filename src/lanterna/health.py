"""Model health: online models that hang or have gone are remembered across restarts, and checked again quietly.

A model that doesn't start answering (some new Gemini models hang for minutes) or that the service no longer
has gets a rest that grows each time: 1 hour, 6 hours, a day, three days. Once a day Lanterna quietly tries the
first few untested models in its queue, and the ones whose rest is over, with one tiny request each — so a
question never waits on a silent model, and a model that works again comes back by itself.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from .config import data_dir

RESTS = (3600, 6 * 3600, 24 * 3600, 72 * 3600)   # the rest after the 1st, 2nd, 3rd, 4th+ time in a row
CHECK_EVERY = 24 * 3600                            # the quiet check, at most once a day
CHECK_MAX = 6                                      # tiny requests per check (each uses one of that model's free requests)
GAP = {"gemini": 13.0}                             # seconds between two requests (Gemini allows 5 a minute)
DEFAULT_GAP = 2.0


class Health:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()

    @staticmethod
    def _file():
        return data_dir() / "health.json"

    def _load(self) -> dict:
        try:
            d = json.loads(self._file().read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("models"), dict):
                return d
        except (OSError, ValueError):
            pass
        return {"models": {}, "checked": 0}

    def _save(self, d: dict) -> None:
        try:
            f = self._file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
        except OSError:
            pass

    # -- what happened
    def bad(self, provider: str, model: str, reason: str) -> float:
        """The model hung or is gone: it rests (longer each time in a row). Returns the seconds of rest."""
        now = self._clock()
        with self._lock:
            d = self._load()
            m = d["models"].get(f"{provider}/{model}") or {"strikes": 0}
            if m.get("until", 0) > now:                       # already resting: one failure, not a new strike
                return m["until"] - now
            m["strikes"] = min(int(m.get("strikes", 0)) + 1, len(RESTS))
            rest = RESTS[m["strikes"] - 1]
            m.update(until=now + rest, reason=reason, at=now)
            d["models"][f"{provider}/{model}"] = m
            self._save(d)
            return rest

    def good(self, provider: str, model: str) -> None:
        """The model answered: whatever it did before is forgotten."""
        with self._lock:
            d = self._load()
            if d["models"].pop(f"{provider}/{model}", None) is not None:
                self._save(d)

    # -- reading
    def rest_until(self, provider: str, model: str) -> float:
        with self._lock:
            m = self._load()["models"].get(f"{provider}/{model}")
        return float(m.get("until", 0)) if m else 0.0

    def resting(self) -> dict[str, float]:
        """"provider/model" -> seconds of rest left."""
        now = self._clock()
        with self._lock:
            ms = self._load()["models"]
        return {k: m["until"] - now for k, m in ms.items() if m.get("until", 0) > now}

    def due(self) -> bool:
        with self._lock:
            return self._clock() - float(self._load().get("checked", 0)) >= CHECK_EVERY

    def _checked(self) -> None:
        with self._lock:
            d = self._load()
            d["checked"] = self._clock()
            self._save(d)

    # -- the quiet daily check
    def to_check(self, candidates: list) -> list:
        """The models worth one tiny request now, in queue order: online, and untested or with the rest over."""
        now = self._clock()
        with self._lock:
            ms = self._load()["models"]
        from .providers import PROVIDERS
        out = []
        for c in candidates:
            if PROVIDERS[c.provider].local or getattr(c, "fallback", False):
                continue
            m = ms.get(f"{c.provider}/{c.model}")
            if (m and m.get("until", 0) <= now) or (not m and c.status == "untested"):
                out.append(c)
            if len(out) >= CHECK_MAX:
                break
        return out

    def check(self, router, sleep: Callable[[float], None] = time.sleep) -> dict[str, str]:
        """One tiny request to each model due. Runs in the background; returns "provider/model" -> ok | bad | busy.
        No internet: stops and tries again next time."""
        from .limits import TRACKER
        from .providers import ProviderError
        out: dict[str, str] = {}
        last = ""
        for c in self.to_check(router.candidates):
            if TRACKER.rest_until(c.provider, c.model) > time.time():
                continue                                   # out of its daily limit: nothing to learn today
            if last:
                sleep(GAP.get(c.provider, DEFAULT_GAP) if last == c.provider else DEFAULT_GAP)
            last = c.provider
            key = f"{c.provider}/{c.model}"
            try:
                c.latency = round(router.client(c.provider).ping(c.model), 2)
                c.status = "ok"
                self.good(c.provider, c.model)
                out[key] = "ok"
            except ProviderError as e:
                if e.kind == "network":                   # our internet, not the model
                    return out
                if e.kind in ("rate", "auth"):            # busy right now, or a key problem: not the model's fault
                    out[key] = "busy"
                    continue
                if e.kind == "timeout" or e.status == 404:
                    self.bad(c.provider, c.model, e.kind if e.kind == "timeout" else "gone")
                    out[key] = "bad"
                else:
                    out[key] = "busy"
        self._checked()
        return out


HEALTH = Health()
