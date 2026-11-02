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
    Provider("github", "GitHub Models", "https://models.github.ai/inference", "https://github.com/settings/personal-access-tokens"),
    Provider("ollama", "Ollama (local)", "http://localhost:11434/v1", "https://ollama.com/download", needs_key=False, local=True),
]}

# Good default chat models per provider, best first. Stage 1 replaces this with live discovery.
PREFERRED: dict[str, list[str]] = {
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"],
    "gemini": ["gemini-2.5-flash", "gemini-2.0-flash"],
}
_NOT_CHAT = re.compile(r"whisper|tts|guard|safeguard|embed|moderation|playai|orpheus|allam|vision-only", re.I)


class ProviderError(Exception):
    """kind: auth | rate | network | bad_request | other"""

    def __init__(self, kind: str, message: str, status: int = 0, retry_after: float | None = None):
        super().__init__(message)
        self.kind, self.status, self.retry_after = kind, status, retry_after


def _error(resp: httpx.Response) -> ProviderError:
    try:
        msg = resp.json().get("error", {})
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
    except ValueError:
        msg = resp.text[:200]
    s = resp.status_code
    kind = "auth" if s in (401, 403) else "rate" if s == 429 else "bad_request" if s in (400, 404, 422) else "other"
    ra = resp.headers.get("retry-after")
    return ProviderError(kind, msg or f"HTTP {s}", s, float(ra) if ra and ra.replace(".", "", 1).isdigit() else None)


class Client:
    def __init__(self, provider: Provider, key: str | None = None, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 60.0):
        if provider.needs_key and not key:
            raise ProviderError("auth", f"No API key for {provider.name}")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        headers["User-Agent"] = "Lanterna"
        self.provider = provider
        self._http = httpx.Client(base_url=provider.base_url, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def raw_models(self) -> list[dict]:
        """The provider's model list as returned (OpenRouter includes prices; others just ids)."""
        # GitHub Models keeps its catalog next to the inference endpoint, on the same host.
        path = "../catalog/models" if self.provider.id == "github" else "models"
        try:
            r = self._http.get(path)
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise _error(r)
        data = r.json()
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
            r = self._http.post("chat/completions", json=body, timeout=25)
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

    def stream_chat(self, model: str, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        """Yields text pieces as they arrive. Hidden reasoning (<think>…</think>) is dropped."""
        body = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
        think = _ThinkFilter()
        try:
            with self._http.stream("POST", "chat/completions", json=body) as r:
                if r.status_code != 200:
                    r.read()
                    raise _error(r)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta", {}).get("content") or ""
                    except (ValueError, KeyError, IndexError):
                        continue
                    out = think.feed(delta)
                    if out:
                        yield out
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        tail = think.flush()
        if tail:
            yield tail

    def chat(self, model: str, messages: list[dict], temperature: float = 0.7) -> str:
        return "".join(self.stream_chat(model, messages, temperature)).strip()


class _ThinkFilter:
    """Removes <think>…</think> blocks from a token stream (some models show their reasoning)."""

    def __init__(self):
        self.buf, self.inside = "", False

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            if self.inside:
                end = self.buf.find("</think>")
                if end < 0:
                    self.buf = self.buf[-8:]
                    return "".join(out)
                self.buf, self.inside = self.buf[end + 8:].lstrip("\n"), False
            else:
                start = self.buf.find("<think>")
                if start < 0:
                    lt = self.buf.rfind("<", max(0, len(self.buf) - 6))   # a tag may be split between chunks
                    cut = lt if lt >= 0 else len(self.buf)
                    out.append(self.buf[:cut])
                    self.buf = self.buf[cut:]
                    return "".join(out)
                out.append(self.buf[:start])
                self.buf, self.inside = self.buf[start + 7:], True

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest
