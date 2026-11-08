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


PROVIDERS: dict[str, Provider] = {p.id: p for p in [
    Provider("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys"),
    Provider("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "https://aistudio.google.com/apikey"),
    Provider("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/settings/keys"),
    Provider("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "https://cloud.cerebras.ai"),
    Provider("mistral", "Mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys"),
    Provider("ollama", "Ollama (local)", "http://127.0.0.1:11434/v1", "https://ollama.com/download", needs_key=False, local=True),
]}

# Services that closed: settings, caches and synced keys that still name them are ignored.
# GitHub Models was shut down by GitHub on 30 July 2026 (its address now answers "OK" to everything).
RETIRED: dict[str, str] = {"github": "GitHub Models"}

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

    def __init__(self, kind: str, message: str, status: int = 0, retry_after: float | None = None):
        super().__init__(message)
        self.kind, self.status, self.retry_after = kind, status, retry_after


def _error(resp: httpx.Response) -> ProviderError:
    try:
        data = resp.json()
        if isinstance(data, list) and data:                  # Gemini wraps errors in a list: [{"error": {...}}]
            data = data[0]
        msg = data.get("error", {}) if isinstance(data, dict) else data
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg or "")
    except ValueError:
        msg = resp.text[:200]
    s = resp.status_code
    kind = "auth" if s in (401, 403) else "rate" if s == 429 else "bad_request" if s in (400, 404, 422) else "other"
    ra = resp.headers.get("retry-after")
    wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
    # Groq: "Please try again in 2.4s" / "in 7m12.5s"; Gemini: "Please retry in 1h31m43.18s" (daily limit)
    m = re.search(r"(?:try again|retry) in ((?:\d+h)?(?:\d+m)?[\d.]+s)", msg or "")
    if wait is None and m:
        h, mi, sec = re.match(r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", m.group(1)).groups()
        wait = int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec)
    return ProviderError(kind, msg or f"HTTP {s}", s, wait)


# An online model that hasn't started answering by now is stuck (some new Gemini models hang for minutes):
# the router moves on to the next one. Once the answer flows, the usual timeout applies between pieces.
FIRST_WAIT = 30.0
PING_WAIT = 25.0          # a tiny test request (model checks)


class Client:
    def __init__(self, provider: Provider, key: str | None = None, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 60.0):
        if provider.needs_key and not key:
            raise ProviderError("auth", f"No API key for {provider.name}")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        headers["User-Agent"] = "Lanterna"
        self.provider = provider
        self._timeout = timeout
        self._http = httpx.Client(base_url=provider.base_url, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def raw_models(self) -> list[dict]:
        """The provider's model list as returned (OpenRouter includes prices; others just ids)."""
        try:
            r = self._http.get("models")
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise _error(r)
        try:
            data = r.json()
        except ValueError:                                   # a page or a plain "OK": the service changed or closed
            raise ProviderError("other", f"{self.provider.name} didn't send a list of models: {r.text[:80].strip()!r}",
                                r.status_code) from None
        items = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
        out = []
        for m in items if isinstance(items, list) else []:
            if isinstance(m, dict) and (m.get("id") or m.get("name")):
                m = dict(m)
                m["id"] = str(m.get("id") or m.get("name")).removeprefix("models/")
                out.append(m)
        return out

    def list_models(self) -> list[str]:
        return [m["id"] for m in self.raw_models()]

    def ping(self, model: str) -> float:
        """Tiny request to check that a model answers right now. Returns seconds; raises ProviderError."""
        body = {"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 8, "stream": False}
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
            raise _error(r)
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
                        d = json.loads(payload)["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    for tc in d.get("tool_calls") or []:
                        slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": "", "extra": None})
                        slot["id"] = tc.get("id") or slot["id"]
                        if isinstance(tc.get("extra_content"), dict):     # Gemini 3 wants this back as is
                            slot["extra"] = tc["extra_content"]
                        fn = tc.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
                    out = think.feed(d.get("content") or "")
                    inner = think.thought() + str(d.get("reasoning") or d.get("reasoning_content") or "")
                    if inner:
                        yield Thought(inner)
                    if out:
                        yield out
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:   # no way to reach the service at all
            raise ProviderError("network", str(e)) from e
        except httpx.TimeoutException as e:                  # this model is stuck; others may be fine
            raise ProviderError("timeout", str(e) or "The model did not answer in time") from e
        except httpx.HTTPError as e:                         # one answer broke off: only this model rests a bit
            raise ProviderError("dropped", str(e) or e.__class__.__name__) from e
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
