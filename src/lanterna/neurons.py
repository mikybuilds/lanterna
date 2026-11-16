"""Cloudflare Workers AI's free neurons, counted on this computer.

Cloudflare gives every account 10,000 free "neurons" a day, shared by all its models; its day starts at 00:00 UTC.
On the free plan it refuses more; on Workers Paid it simply bills them ($0.011 per 1,000), without asking. So
Lanterna counts every answer itself, from the model's price per token, and stops a little under the free amount
(CAP): Cloudflare never costs anything, on either plan. Before an answer the most it can cost is put aside; when it
ends, what it really used is counted instead (Cloudflare's own numbers, or about 3 characters a token).
Kept in cloudflare.json next to the settings, so a restart and other Lanterna windows on this computer count on.
"""
from __future__ import annotations

import json
import threading
import time

from .config import data_dir
from .providers import ProviderError

FREE = 10_000
CAP = 9_000                    # what Lanterna uses of it: room for estimates and for answers running at once
PER_USD = 1000 / 0.011         # neurons a dollar buys (Workers AI: $0.011 per 1,000 neurons)
DEAR = (1.4, 4.9)              # USD per million tokens (input, output) for a model whose price isn't known
MAX_OUT = 8192                 # max_tokens sent with every answer: Cloudflare's own default cuts answers short
ANSWER = (6000, 800)           # tokens of an ordinary answer: the request (instructions, tools, chat) and the reply
MOST_PER_ANSWER = 300          # dearer models are left out: the free neurons would last only a few answers
PICTURE = 1500                 # tokens a photo counts as (its data is sent as base64, which isn't read as text)
# Prices of the usual models (USD per million tokens: input, output), from Cloudflare's pricing page (November 2026).
# The prices in Cloudflare's live model list win; these are for when it gives none.
KNOWN = {
    "@cf/openai/gpt-oss-120b": (0.35, 0.75),
    "@cf/google/gemma-4-26b-a4b-it": (0.1, 0.3),
    "@cf/qwen/qwen3-30b-a3b-fp8": (0.0509, 0.3352),
    "@cf/mistralai/mistral-small-3.1-24b-instruct": (0.3506, 0.5554),
    "@cf/google/gemma-3-12b-it": (0.345, 0.556),
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": (0.2933, 2.2529),
    "@cf/qwen/qwen3.8-27b": (0.45, 3.2),
    "@cf/qwen/qwq-32b": (0.66, 1.0),
}

_lock = threading.Lock()


def _file():
    return data_dir() / "cloudflare.json"


def _load() -> dict:
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def _save(d: dict) -> None:
    try:
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


def today(now: float | None = None) -> str:
    """Cloudflare's day (UTC)."""
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() if now is None else now))


def till_tomorrow(now: float | None = None) -> float:
    """Seconds until Cloudflare's next day starts (00:00 UTC)."""
    return 86400 - (time.time() if now is None else now) % 86400


def tokens(chars: int) -> int:
    """About how many tokens a text of this length is (3 characters a token: more than usual, to be safe)."""
    return chars // 3 + 1


def request_tokens(body: dict) -> int:
    """About how many tokens a request is: its messages and tools as text, and PICTURE for each photo."""
    photos = 0

    def text_only(x):
        nonlocal photos
        if isinstance(x, dict):
            if x.get("type") in ("image_url", "input_image", "image", "input_audio"):
                photos += 1
                return None
            return {k: text_only(v) for k, v in x.items()}
        if isinstance(x, list):
            return [text_only(v) for v in x]
        if isinstance(x, str) and x.startswith("data:") and ";base64," in x[:80]:
            photos += 1
            return ""
        return x
    sent = json.dumps(text_only(body.get("messages")), ensure_ascii=False)
    return tokens(len(sent) + len(json.dumps(body.get("tools") or [], ensure_ascii=False))) + photos * PICTURE


def price(model: str, d: dict | None = None) -> tuple[float, float]:
    """USD per million tokens (input, output): from Cloudflare's model list, a known one, or the dearest."""
    p = ((d if d is not None else _load()).get("prices") or {}).get(model) or KNOWN.get(model)
    return (float(p[0]), float(p[1])) if p else DEAR


def cost(model: str, tokens_in: float, tokens_out: float, d: dict | None = None) -> float:
    """Neurons an answer of that size costs on that model."""
    p_in, p_out = price(model, d)
    return (tokens_in * p_in + tokens_out * p_out) / 1e6 * PER_USD


def cheap_enough(model: str) -> bool:
    """An ordinary answer costs at most MOST_PER_ANSWER neurons, so the free ones last for a few dozen."""
    return cost(model, *ANSWER) <= MOST_PER_ANSWER


def remember_prices(prices: dict[str, tuple[float, float]]) -> None:
    """The prices in Cloudflare's model list (they change now and then)."""
    if not prices:
        return
    with _lock:
        d = _load()
        d["prices"] = {**(d.get("prices") or {}), **{m: [p[0], p[1]] for m, p in prices.items()}}
        _save(d)


def used(now: float | None = None) -> float:
    """Neurons counted today (answers still running included at the most they can cost; CAP once Cloudflare said
    they are gone)."""
    d = _load()
    if d.get("day") != today(now):
        return 0.0
    return max(float(d.get("used", 0)), float(CAP)) if d.get("out") else float(d.get("used", 0))


class Call:
    """One request to Cloudflare. Puts aside the most it can cost, or refuses (like Cloudflare's own "daily free
    allocation" answer) when today's free neurons can't cover it. done() then counts what it really cost.
    Refused because the day is over: the whole service rests until tomorrow. Refused because this request is big
    (a long document) while an ordinary answer still fits: only this model rests, for a minute."""

    def __init__(self, model: str, body: dict, now: float | None = None):
        self.model, self.day = model, today(now)
        self.tokens_in = request_tokens(body)
        with _lock:
            d = _load()
            if d.get("day") != self.day:
                d.update(day=self.day, used=0.0, calls=0, out=False)
            self.held = cost(model, self.tokens_in, body.get("max_tokens") or MAX_OUT, d)
            used = float(d.get("used", 0))
            if d.get("out") or used + self.held > CAP:
                if d.get("out") or CAP - used < cost(model, *ANSWER, d):
                    raise ProviderError("rate", "Cloudflare's free neurons for today are used up (counted by Lanterna).",
                                        429, till_tomorrow(now), whole=True)
                raise ProviderError("rate", "This request needs more of Cloudflare's free neurons than are left today.",
                                    429, 60)
            d["used"] = used + self.held
            d["calls"] = int(d.get("calls", 0)) + 1
            _save(d)

    def done(self, usage: dict | None, chars_out: int, outcome: str) -> None:
        """outcome: "ok" (counted from Cloudflare's usage numbers or the text), "refused" (an error answer or no
        connection: nothing ran, nothing is billed), "out" (Cloudflare itself said today's free neurons are gone,
        maybe used outside Lanterna: nothing more today), "broken" (cut off: the most it could cost stays counted)."""
        if outcome == "broken":
            return
        real = 0.0
        if outcome == "ok":
            u = usage if isinstance(usage, dict) else {}
            t_in = u.get("prompt_tokens") if _number(u.get("prompt_tokens")) else self.tokens_in
            t_out = u.get("completion_tokens") if _number(u.get("completion_tokens")) else tokens(chars_out)
            real = cost(self.model, t_in, t_out)
        with _lock:
            d = _load()
            if d.get("day") == self.day:                 # (an answer across midnight: the new day starts at 0)
                d["used"] = max(0.0, float(d.get("used", 0)) + real - self.held)
                if outcome == "out":
                    d["out"] = True
                _save(d)


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
