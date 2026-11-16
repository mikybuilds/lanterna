"""Model providers. Every supported service speaks the OpenAI-compatible chat API, so one client fits all."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Iterator

import httpx


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str
    key_url: str = ""                     # where the user creates a free key
    needs_key: bool = True
    local: bool = False
    note: str = ""                        # what to know before signing up (Settings → Services), translated by the UI
    models_url: str = ""                  # where the model list is, when it isn't <base_url>/models
    keep: str = ""                        # only models matching this are used (the free ones on a mixed service)
    drop: str = ""                        # models to leave out on this service (not chat, old base models)
    known: tuple[str, ...] = ()           # used when the service has no model list
    pings: int = 3                        # models tried once a day (few for small monthly limits)
    key_hint: str = ""                    # what to paste, when it isn't just "the key" (the box's hint, translated)


CF_API = "https://api.cloudflare.com/client/v4"

PROVIDERS: dict[str, Provider] = {p.id: p for p in [
    Provider("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys",
             note="Quick sign-up with Google or GitHub."),
    Provider("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "https://aistudio.google.com/apikey",
             note="Needs a Google account. On the free plan Google may use what you send to improve its models."),
    Provider("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/settings/keys",
             note="Only its free models are used: 50 requests a day."),
    Provider("mistral", "Mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys",
             note="Needs a phone number. On the free plan Mistral may use what you send to train its models."),
    Provider("nvidia", "NVIDIA", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com/settings/api-keys",
             note="Needs a phone number. Free for personal use and testing, about 40 requests a minute.",
             drop=r"reward|nemotron-parse|detector|deplot|kosmos|fuyu|neva-|/vila|clip|riva-|diffusion|calibration|cosmos|"
                  r"muse-|chatqa|codegemma|starcoder|codellama|recurrentgemma|llama2-|-v0\.1$|gemma-2b$|palmyra-(fin|med)"),
    Provider("zai", "Z.ai (GLM)", "https://api.z.ai/api/paas/v4", "https://z.ai/manage-apikey/apikey-list",
             note="Only its free GLM Flash models are used, so nothing is ever charged.",
             keep=r"^glm-[\d.]+v?-flash$", known=("glm-4.7-flash", "glm-4.6v-flash", "glm-4.5-flash")),
    Provider("cohere", "Cohere", "https://api.cohere.ai/compatibility/v1", "https://dashboard.cohere.com/api-keys",
             note="1,000 free requests a month, for personal use only.",
             models_url="https://api.cohere.ai/v1/models?endpoint=chat", pings=1),
    # Workers AI: the key is "<account ID>:<API token>" (cloudflare_key); 10,000 free neurons a day per account,
    # counted by Lanterna itself (neurons.py), so a Workers Paid account isn't billed either
    Provider("cloudflare", "Cloudflare Workers AI", CF_API + "/accounts/{account}/ai/v1",
             "https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
             note="10,000 free neurons a day, a few dozen answers. Lanterna stops before they run out, so nothing is charged, even on a paid plan.",
             models_url=CF_API + "/accounts/{account}/ai/models/search?task=Text%20Generation&per_page=50",
             drop=r"lora|moonshotai/kimi|zai-org/glm-5|@hf/|llama-2|tinyllama|phi-2|qwen1\.5|-v0\.1$",
             pings=2, key_hint="Paste the API token (Workers AI template)"),
    Provider("ollama", "Ollama (local)", "http://127.0.0.1:11434/v1", "https://ollama.com/download", needs_key=False, local=True),
]}

# Services that closed: settings, caches and synced keys that still name them are ignored.
# GitHub Models was shut down by GitHub on 30 July 2026 (its address now answers "OK" to everything).
# Cerebras ended its free plan on 21 July 2026 (a card trial, then pay per use): Lanterna never spends money.
RETIRED: dict[str, str] = {"github": "GitHub Models", "cerebras": "Cerebras"}

# Good default chat models per provider, best first. Stage 1 replaces this with live discovery.
PREFERRED: dict[str, list[str]] = {
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"],
    "gemini": ["gemini-2.5-flash", "gemini-2.0-flash"],
}
_NOT_CHAT = re.compile(r"whisper|tts|guard|safeguard|embed|moderation|playai|orpheus|allam|vision-only", re.I)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str                        # JSON text, as the model wrote it
    extra: dict | None = None             # provider data that must go back with the call (Gemini 3: thought_signature)

    def message(self) -> dict:
        """The call as it goes back in the assistant message of the history."""
        out = {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments}}
        if self.extra:
            out["extra_content"] = self.extra
        return out


@dataclass
class ToolCalls:
    """The model wants these tools run before it answers."""
    calls: list[ToolCall]


@dataclass
class Thought:
    """A piece of the model's reasoning (<think>/<thought> blocks, a `reasoning` field, Gemini thought summaries).
    Never part of the reply: the UI shows it as a short "what I'm thinking about" line."""
    text: str


class ProviderError(Exception):
    """kind: auth | rate | network | timeout | bad_request | other"""

    def __init__(self, kind: str, message: str, status: int = 0, retry_after: float | None = None,
                 whole: bool = False):
        super().__init__(message)
        self.kind, self.status, self.retry_after = kind, status, retry_after
        self.whole = whole              # the whole service is out (Cloudflare's daily neurons), not just this model


# Cloudflare Workers AI's error codes: this model needs Workers Paid (5035), its terms aren't accepted (5016) or it
# is private (5018, 3041): only that model is out, the key is fine. 3036: the account's free neurons for today are used.
CF_MODEL_REFUSED = {5035, 5016, 5018, 3041}
CF_DAY_USED = 3036


def _error(resp: httpx.Response) -> ProviderError:
    code = 0
    try:
        data = resp.json()
        if isinstance(data, list) and data:                  # Gemini wraps errors in a list: [{"error": {...}}]
            data = data[0]
        if isinstance(data, dict) and not data.get("error") and isinstance(data.get("errors"), list) and data["errors"]:
            data = {"error": data["errors"][0]}             # Cloudflare: {"errors": [{"code": 3036, "message": …}]}
        msg = data.get("error", {}) if isinstance(data, dict) else data
        if isinstance(msg, dict) and str(msg.get("code", "")).isdigit():
            code = int(msg["code"])
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg or "")
    except ValueError:
        msg = resp.text[:200]
    s = resp.status_code
    kind = "auth" if s in (401, 403) else "rate" if s == 429 else "bad_request" if s in (400, 404, 410, 422) else "other"
    ra = resp.headers.get("retry-after")
    wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
    # Groq: "Please try again in 2.4s" / "in 7m12.5s"; Gemini: "Please retry in 1h31m43.18s" (daily limit)
    m = re.search(r"(?:try again|retry) in ((?:\d+h)?(?:\d+m)?[\d.]+s)", msg or "")
    if wait is None and m:
        h, mi, sec = re.match(r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", m.group(1)).groups()
        wait = int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec)
    whole = False
    if s == 403 and code in CF_MODEL_REFUSED:
        kind = "bad_request"
    elif code == CF_DAY_USED or "daily free allocation" in (msg or "").lower():
        from .neurons import till_tomorrow
        kind, wait, whole = "rate", wait or till_tomorrow(), True
    return ProviderError(kind, msg or f"HTTP {s}", s, wait, whole)


CF_NEED_ACCOUNT = ("Lanterna couldn't find your Account ID. Paste it after the token, with a space: "
                   "it is on Cloudflare's Workers AI page.")
_CF_ID = re.compile(r"^[0-9a-f]{32}$")
_CF_ID_IN = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")


def cloudflare_key(text: str, transport: httpx.BaseTransport | None = None) -> tuple[str, str]:
    """What the user pasted for Cloudflare as Lanterna keeps it: ("<account ID>:<API token>", "").
    The API token alone is enough when Cloudflare names its one account; the Account ID (32 hex digits) can be
    pasted too, before or after the token, or both inside a copied command. On a problem ("", why): "need_account"
    (no single account found: the user adds it), "auth", "network". The token goes only to Cloudflare's API."""
    found_id = _CF_ID_IN.search((text or "").lower())
    account = found_id.group(0) if found_id else ""
    parts = [x.strip("\"'<>") for x in re.split(r"[\s:,;=]+", text or "")]
    parts = [x for x in parts if x and x.lower() != account and "/" not in x]
    tokens = [x for x in parts if re.fullmatch(r"[A-Za-z0-9_\-]{20,}", x)]      # API tokens are 40 such characters
    token = max(tokens or parts, key=len, default="")
    if not token:
        return "", "auth"
    if account:
        return f"{account}:{token}", ""
    try:
        with httpx.Client(timeout=20, transport=transport, headers={"User-Agent": "Lanterna"}) as h:
            r = h.get(CF_API + "/accounts", params={"per_page": 50}, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        return "", "network"
    if r.status_code == 401:
        return "", "auth"
    try:
        found = [a.get("id") for a in r.json().get("result") or [] if isinstance(a, dict)]
    except (ValueError, AttributeError):
        found = []
    found = [a for a in found if isinstance(a, str) and _CF_ID.match(a)]
    if r.status_code == 200 and len(found) == 1:
        return f"{found[0]}:{token}", ""
    return "", "need_account"


def cf_property(m: dict, name: str):
    """One of a Cloudflare model's properties ("price", "context_window", …) as listed, or None."""
    for prop in m.get("properties") or []:
        if isinstance(prop, dict) and prop.get("property_id") == name:
            return prop.get("value")
    return None


def _cf_price(m: dict) -> tuple[float, float] | None:
    """USD per million tokens (input, output) from a Cloudflare model's price
    ([{"unit": "per M input tokens", "price": 0.35, "currency": "USD"}, …]). Anything else (other units, a price of 0,
    only one of the two): None, so the counter uses a known price or the dearest one instead."""
    listed, got = cf_property(m, "price"), {}
    for v in listed if isinstance(listed, list) else []:
        if not isinstance(v, dict) or isinstance(v.get("price"), bool) or str(v.get("currency") or "USD").upper() != "USD":
            continue
        unit = str(v.get("unit") or "").lower()
        if not re.search(r"\b(m|million)\b.*\btokens?\b", unit) or ("input" in unit) == ("output" in unit):
            continue
        try:
            p = float(v["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if p > 0 and p != float("inf"):
            got["out" if "output" in unit else "in"] = p
    return (got["in"], got["out"]) if len(got) == 2 else None


def _pages(data) -> int:
    """How many pages a Cloudflare list has (its result_info), at most 5; 1 for the other services."""
    info = data.get("result_info") if isinstance(data, dict) else None
    if not isinstance(info, dict):
        return 1
    try:
        n = int(info.get("total_pages") or 0)
        if not n and info.get("total_count") and info.get("per_page"):
            n = -(-int(info["total_count"]) // max(1, int(info["per_page"])))
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, n))


def _usage(r: httpx.Response) -> dict | None:
    """The token counts in an answer ({"prompt_tokens": …, "completion_tokens": …}), if it has them."""
    try:
        d = r.json()
    except ValueError:
        return None
    return d["usage"] if isinstance(d, dict) and isinstance(d.get("usage"), dict) else None


# An online model that hasn't started answering by now is stuck (some new Gemini models hang for minutes):
# the router moves on to the next one. Once the answer flows, the usual timeout applies between pieces.
FIRST_WAIT = 30.0
PING_WAIT = 25.0          # a tiny test request (model checks)


class Client:
    def __init__(self, provider: Provider, key: str | None = None, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 60.0):
        if provider.needs_key and not key:
            raise ProviderError("auth", f"No API key for {provider.name}")
        base, self._models_url = provider.base_url, provider.models_url
        if "{account}" in base:                  # Cloudflare: the key is "<account ID>:<API token>" (cloudflare_key)
            account, _, key = (key or "").partition(":")
            if not _CF_ID.match(account.lower()) or not key:
                raise ProviderError("auth", f"{provider.name} needs the Account ID together with the API token")
            base, self._models_url = base.format(account=account.lower()), self._models_url.format(account=account.lower())
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        headers["User-Agent"] = "Lanterna"
        self.provider = provider
        self.guessed = False                 # True when the model list came from Provider.known (the service has none)
        self._timeout = timeout
        self._http = httpx.Client(base_url=base, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def raw_models(self) -> list[dict]:
        """The provider's model list as returned (OpenRouter includes prices; others just ids)."""
        url = self._models_url or "models"
        try:
            r = self._http.get(url)
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code in (400, 404, 405) and self.provider.known:     # no model list there: the known ones
            self.guessed = True
            return [{"id": m} for m in self.provider.known]
        if r.status_code != 200:
            raise _error(r)
        try:
            data = r.json()
        except ValueError:                                   # a page or a plain "OK": the service changed or closed
            raise ProviderError("other", f"{self.provider.name} didn't send a list of models: {r.text[:80].strip()!r}",
                                r.status_code) from None
        # Cloudflare: {"result": [...], "result_info": {...}}, in pages
        items = data.get("data", data.get("models", data.get("result", []))) if isinstance(data, dict) else data
        items = list(items) if isinstance(items, list) else []
        for page in range(2, _pages(data) + 1):
            try:
                more = self._http.get(url, params={"page": page})
                got = more.json().get("result") if more.status_code == 200 else None
            except (httpx.HTTPError, ValueError, AttributeError):
                break
            if not isinstance(got, list) or not got:
                break
            items += got
        out = []
        for m in items:
            if isinstance(m, dict) and (m.get("id") or m.get("name")):
                m = dict(m)
                name = str(m.get("name") or "")
                # Cloudflare's "id" is a number of its own: the model is called by its name ("@cf/…")
                m["id"] = (name if name.startswith("@") else str(m.get("id") or name)).removeprefix("models/")
                out.append(m)
        if self.provider.id == "cloudflare":
            self._cf_prices(out)
        keep = re.compile(self.provider.keep, re.I) if self.provider.keep else None
        if self.provider.known and keep and not any(keep.search(m["id"]) for m in out):   # its free ones aren't listed
            self.guessed = True
            return [{"id": m} for m in self.provider.known]
        return out

    def list_models(self) -> list[str]:
        """The models Lanterna may use here (a service with paid models too gives only its free ones)."""
        keep = re.compile(self.provider.keep, re.I) if self.provider.keep else None
        return [m["id"] for m in self.raw_models() if keep is None or keep.search(m["id"])]

    def _cf_prices(self, models: list[dict]) -> None:
        """Cloudflare lists each model's price: the neuron counter goes by it (neurons.py)."""
        try:
            from . import neurons
            neurons.remember_prices({m["id"]: p for m in models if (p := _cf_price(m))})
        except Exception:                                   # noqa: BLE001  known prices (or the dearest) still work
            pass

    def _meter(self, model: str, body: dict):
        """Cloudflare: puts aside the neurons this request can cost, or raises when today's free ones can't cover it
        (neurons.py). The answer's length is capped too: Cloudflare's own cap cuts answers short. Others: None."""
        if self.provider.id != "cloudflare":
            return None
        from . import neurons
        body.setdefault("max_tokens", neurons.MAX_OUT)
        return neurons.Call(model, body)

    def ping(self, model: str) -> float:
        """Tiny request to check that a model answers right now. Returns seconds; raises ProviderError."""
        body = {"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 8, "stream": False}
        meter = self._meter(model, body)                    # (when it breaks off, its hold stays: under a neuron)
        t0 = time.monotonic()
        try:
            r = self._http.post("chat/completions", json=body, timeout=PING_WAIT)
        except httpx.TimeoutException as e:                 # reached the service, but the model said nothing
            if isinstance(e, (httpx.ConnectTimeout, httpx.PoolTimeout)):
                raise ProviderError("network", str(e)) from e
            raise ProviderError("timeout", str(e) or "The model did not answer in time") from e
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            err = _error(r)
            if meter:
                meter.done(None, 0, "out" if err.whole else "refused")
            raise err
        if meter:
            meter.done(_usage(r), len(r.text), "ok")
        return time.monotonic() - t0

    def pick_model(self, available: list[str] | None = None) -> str:
        available = available if available is not None else self.list_models()
        for m in PREFERRED.get(self.provider.id, []):
            if m in available:
                return m
        chat = [m for m in available if not _NOT_CHAT.search(m)]
        if not chat:
            raise ProviderError("other", f"{self.provider.name}: no chat models available")
        return chat[0]

    def stream_chat(self, model: str, messages: list[dict], temperature: float = 0.7,
                    tools: list[dict] | None = None, tool_choice: str = "auto") -> Iterator["str | ToolCalls"]:
        """Yields text pieces as they arrive. Hidden reasoning (<think>…</think>) is dropped.

        With tools, the model may ask to call some: then the last item yielded is a ToolCalls.
        """
        body = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
        # "none" = answer now. Gemini needs the tool list kept for that (without it, after tool calls, it sends
        # nothing); other services simply get no tools, as some (Ollama) ignore tool_choice
        if tools and (tool_choice != "none" or self.provider.id == "gemini"):
            body["tools"], body["tool_choice"] = tools, tool_choice
        if self.provider.id == "gemini":                # short thought summaries, shown while it thinks
            body["extra_body"] = {"google": {"thinking_config": {"include_thoughts": True}}}
        meter = self._meter(model, body)
        # for the meter: the token counts the service sends, the characters that came, and how the answer ended
        # ("broken" unless it ran to the end or was refused: a cut-off answer may have cost the most it can)
        usage, chars, outcome = None, 0, "broken"
        think = _ThinkFilter()
        calls: dict[int, dict] = {}
        # online services send the headers together with the first piece: a short wait for them, then the usual one
        first = {} if self.provider.local else {"timeout": httpx.Timeout(self._timeout, read=min(FIRST_WAIT, self._timeout))}
        try:
            with self._http.stream("POST", "chat/completions", json=body, **first) as r:
                limits = r.request.extensions.get("timeout")
                if first and isinstance(limits, dict):       # read before the body starts, so the body gets the usual wait
                    limits["read"] = self._timeout
                if r.status_code != 200:
                    r.read()
                    err = _error(r)
                    outcome = "out" if err.whole else "refused"
                    self._note(model, r, str(err), err.retry_after)
                    raise err
                self._note(model, r)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        if isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict):
                            usage = chunk["usage"]               # (the last piece, on services that send it)
                        d = chunk["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                        continue
                    for tc in d.get("tool_calls") or []:
                        slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": "", "extra": None})
                        slot["id"] = tc.get("id") or slot["id"]
                        if isinstance(tc.get("extra_content"), dict):     # Gemini 3 wants this back as is
                            slot["extra"] = tc["extra_content"]
                        fn = tc.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
                        chars += len(fn.get("name") or "") + len(fn.get("arguments") or "")
                    text = d.get("content") or ""
                    reasoning = str(d.get("reasoning") or d.get("reasoning_content") or "")
                    chars += len(text) + len(reasoning)
                    out = think.feed(text)
                    inner = think.thought() + reasoning
                    if inner:
                        yield Thought(inner)
                    if out:
                        yield out
            outcome = "ok"
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:   # no way to reach the service at all
            outcome = "refused"
            raise ProviderError("network", str(e)) from e
        except httpx.TimeoutException as e:                  # this model is stuck; others may be fine
            raise ProviderError("timeout", str(e) or "The model did not answer in time") from e
        except httpx.HTTPError as e:                         # one answer broke off: only this model rests a bit
            raise ProviderError("dropped", str(e) or e.__class__.__name__) from e
        finally:
            if meter:
                meter.done(usage, chars, outcome)
        tail = think.flush()
        if tail:
            yield tail
        if calls:
            yield ToolCalls([ToolCall(c["id"] or f"call_{i}", c["name"], c["arguments"] or "{}", c["extra"])
                             for i, c in sorted(calls.items()) if c["name"]])

    def _note(self, model: str, r: httpx.Response, message: str = "", retry_after: float | None = None) -> None:
        """Remembers what the service said about its limits (Settings → Limits). Local models have none."""
        if self.provider.local:
            return
        try:
            from .limits import TRACKER
            TRACKER.note(self.provider.id, model, r.status_code, r.headers, message, retry_after)
        except Exception:                                   # noqa: BLE001  never break a reply over a counter
            pass

    def chat(self, model: str, messages: list[dict], temperature: float = 0.7) -> str:
        return "".join(p for p in self.stream_chat(model, messages, temperature) if isinstance(p, str)).strip()


class _ThinkFilter:
    """Removes <think>…</think> and <thought>…</thought> blocks from a token stream (some models show their reasoning)."""

    OPEN = ("<think>", "<thought>")

    def __init__(self):
        self.buf, self.close = "", ""          # close: the tag that ends the block we are inside, "" = outside
        self.inner: list[str] = []             # the hidden text, for the "thinking" line (take it with thought())

    def thought(self) -> str:
        out, self.inner = "".join(self.inner), []
        return out

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            if self.close:
                end = self.buf.find(self.close)
                if end < 0:
                    keep = len(self.close)             # a closing tag may be split between chunks
                    if len(self.buf) > keep:
                        self.inner.append(self.buf[:-keep])
                    self.buf = self.buf[-keep:]
                    return "".join(out)
                self.inner.append(self.buf[:end])
                self.buf, self.close = self.buf[end + len(self.close):].lstrip("\n"), ""
            else:
                found = [(i, tag) for tag in self.OPEN if (i := self.buf.find(tag)) >= 0]
                if not found:
                    lt = self.buf.rfind("<", max(0, len(self.buf) - 8))   # a tag may be split between chunks
                    cut = lt if lt >= 0 and any(t.startswith(self.buf[lt:]) for t in self.OPEN) else len(self.buf)
                    out.append(self.buf[:cut])
                    self.buf = self.buf[cut:]
                    return "".join(out)
                i, tag = min(found)
                out.append(self.buf[:i])
                self.buf, self.close = self.buf[i + len(tag):], "</" + tag[1:]

    def flush(self) -> str:
        rest, self.buf = ("" if self.close else self.buf), ""
        return rest
