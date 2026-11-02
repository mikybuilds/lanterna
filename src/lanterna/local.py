"""Talks to Ollama on this computer: is it running, which models are installed, download a model with progress.

Downloads start only when the user presses a button; nothing is fetched on its own.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
DOWNLOAD_PAGE = "https://ollama.com/download"
REGISTRY = "https://registry.ollama.ai"
_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"

# Not chat models
_NOT_CHAT = re.compile(r"embed|bge-|minilm|rerank|nomic|e5-|gte-", re.I)
# Fallback guess when Ollama is too old to report capabilities
_VISION = re.compile(r"-vl|vision|llava|gemma3|gemma4|minicpm-v|moondream|bakllava|qwen2\.5vl|mistral-small3", re.I)


def _client(timeout: float = 5.0) -> httpx.Client:
    return httpx.Client(base_url=OLLAMA_URL, timeout=timeout, headers={"User-Agent": "Lanterna"})


def version() -> str | None:
    """Ollama's version, or None when it is not installed or not running."""
    try:
        with _client(2.0) as c:
            r = c.get("api/version")
        return r.json().get("version") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


@dataclass
class LocalModel:
    name: str
    size_gb: float
    vision: bool = False
    tools: bool = True
    chat: bool = True


def _caps(c: httpx.Client, name: str) -> list[str] | None:
    try:
        r = c.post("api/show", json={"model": name})
        return r.json().get("capabilities") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def installed() -> list[LocalModel]:
    """Models already downloaded into Ollama. Empty when Ollama is not running."""
    try:
        with _client() as c:
            r = c.get("api/tags")
            items = r.json().get("models", []) if r.status_code == 200 else []
            out = []
            for m in items:
                name = m.get("name") or m.get("model") or ""
                if not name:
                    continue
                caps = _caps(c, name)
                if caps is not None:
                    lm = LocalModel(name, round(m.get("size", 0) / 1e9, 2), "vision" in caps, "tools" in caps,
                                    "completion" in caps and "embedding" not in caps)
                else:
                    lm = LocalModel(name, round(m.get("size", 0) / 1e9, 2), bool(_VISION.search(name)), True,
                                    not _NOT_CHAT.search(name))
                out.append(lm)
            return out
    except (httpx.HTTPError, ValueError):
        return []


def download_size(name: str) -> float | None:
    """Download size in GB, read from the public Ollama registry (only the model's manifest, a few KB)."""
    model, _, tag = name.partition(":")
    path = model if "/" in model else "library/" + model
    try:
        with httpx.Client(base_url=REGISTRY, timeout=8, headers={"Accept": _MANIFEST, "User-Agent": "Lanterna"}) as c:
            r = c.get(f"v2/{path}/manifests/{tag or 'latest'}")
        if r.status_code != 200:
            return None
        return round(sum(l.get("size", 0) for l in r.json().get("layers", [])) / 1e9, 2)
    except (httpx.HTTPError, ValueError):
        return None


# ---------------------------------------------------------------------------------- downloads
@dataclass
class Pull:
    name: str
    status: str = "starting"     # starting | downloading | verifying | done | error | cancelled
    done_bytes: int = 0
    total_bytes: int = 0
    error: str = ""
    started: float = field(default_factory=time.time)

    @property
    def percent(self) -> int:
        return int(self.done_bytes * 100 / self.total_bytes) if self.total_bytes else 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["percent"] = self.percent
        return d


class Downloads:
    """Runs Ollama pulls in the background; the UI polls `state()`."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._jobs: dict[str, Pull] = {}
        self._stop: set[str] = set()
        self._lock = threading.Lock()
        self._transport = transport

    def start(self, name: str) -> Pull:
        with self._lock:
            job = self._jobs.get(name)
            if job and job.status in ("starting", "downloading", "verifying"):
                return job
            job = self._jobs[name] = Pull(name)
            self._stop.discard(name)
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def cancel(self, name: str) -> None:
        self._stop.add(name)

    def state(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()]

    def run_sync(self, name: str) -> Pull:
        """Same as start() but waits (used by the terminal command and tests)."""
        job = self._jobs[name] = Pull(name)
        self._run(job)
        return job

    def _run(self, job: Pull) -> None:
        # Each layer reports its own total/completed; add them up per digest.
        layers: dict[str, tuple[int, int]] = {}
        try:
            with httpx.Client(base_url=OLLAMA_URL, timeout=httpx.Timeout(30, read=600),
                              transport=self._transport) as c:
                with c.stream("POST", "api/pull", json={"model": job.name, "stream": True}) as r:
                    if r.status_code != 200:
                        r.read()
                        job.status, job.error = "error", _ollama_error(r)
                        return
                    for line in r.iter_lines():
                        if job.name in self._stop:
                            job.status = "cancelled"
                            return
                        if not line.strip():
                            continue
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("error"):
                            job.status, job.error = "error", str(d["error"])
                            return
                        st = d.get("status", "")
                        if d.get("digest") and d.get("total"):
                            layers[d["digest"]] = (d.get("completed", 0), d["total"])
                            job.done_bytes = sum(a for a, _ in layers.values())
                            job.total_bytes = sum(b for _, b in layers.values())
                            job.status = "downloading"
                        elif st.startswith("verifying") or st.startswith("writing"):
                            job.status = "verifying"
                        elif st == "success":
                            job.status = "done"
                            job.done_bytes = job.total_bytes
            if job.status != "done":
                job.status, job.error = "error", job.error or "Ollama stopped before the download finished"
        except httpx.HTTPError as e:
            job.status, job.error = "error", f"Ollama is not reachable: {e}"


def _ollama_error(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error") or f"HTTP {r.status_code}")
    except ValueError:
        return f"HTTP {r.status_code}"
