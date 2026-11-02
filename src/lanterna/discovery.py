"""Finds chat models that are free to use right now and ranks them.

- OpenRouter publishes prices: only models priced 0 (prompt and completion) are taken.
- Groq, Gemini, Cerebras, Mistral and GitHub Models have free tiers per account: their chat models are taken
  and the best few are pinged once, so models that are blocked or paid for this account drop out.
- Models nobody has heard of yet are scored by size and family, so new free models are picked up automatically.
Results are cached for a day.
"""
from __future__ import annotations

import datetime
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from . import keys
from .config import data_dir
from .providers import PROVIDERS, Client, ProviderError

CACHE_HOURS = 24
PING_PER_PROVIDER = 3

# Not chat models (speech, images, embeddings, safety filters…)
_SKIP = re.compile(r"whisper|tts|speech|transcri|audio-preview|guard|safeguard|content-safety|moderation|embed|imagen|"
                   r"image-generation|veo|lyria|aqa|orpheus|playai|allam|ocr|rerank|live-|-live$|"
                   r"-image(-|$)|native-audio|robotics|computer-use|customtools|nano-banana|omni", re.I)

# Known families: (pattern, score 0–100). First match wins; unknown models fall back to size.
_KNOWN = [
    (r"gemini-[\d.]+-pro", 94), (r"gemini-[\d.]+-flash-lite", 76), (r"gemini-[\d.]+-flash", 88),
    (r"gpt-oss-120b", 86), (r"gpt-oss-20b", 72), (r"gpt-[45]", 88),
    (r"deepseek-(r1|v3|chat|reasoner)", 86), (r"kimi-k2", 86), (r"glm-4\.[5-9]|glm-5", 84),
    (r"qwen3\.\d+-\d+b|qwen3-235b|qwen3-max", 84), (r"qwen3-32b", 78),
    (r"llama-4-maverick", 80), (r"llama-4-scout", 74), (r"llama-3\.3-70b", 76), (r"llama-3\.1-8b", 55),
    (r"mistral-large", 84), (r"mistral-medium", 80), (r"mistral-small", 70), (r"ministral", 58), (r"open-mistral-nemo", 60),
    (r"gemma-4-(26|27|31)b", 80), (r"gemma-3-27b", 72), (r"nemotron.*ultra", 84), (r"nemotron.*super", 80),
]


@dataclass
class Candidate:
    provider: str
    model: str
    score: int
    vision: bool = False
    status: str = "untested"        # untested | ok | limited | unavailable
    latency: float | None = None
    tools: bool = True              # False: the model can't call tools (Ollama tells us per model)
    photo: bool = False             # preferred for photos (the local photo model)

    @property
    def label(self) -> str:
        return f"{PROVIDERS[self.provider].name} · {self.model}"


def score(model: str) -> int:
    m = model.lower()
    for rx, s in _KNOWN:
        if re.search(rx, m):
            base = s
            break
    else:                                                   # unknown: bigger usually means smarter
        sizes = [float(x) for x in re.findall(r"(?<![a\d.])(\d+(?:\.\d+)?)b\b", m)]
        base = int(max(35, min(85, 55 + 10 * math.log2(max(sizes) / 8)))) if sizes else 60
    if re.search(r"code|coder", m) and not re.search(r"qwen3-coder", m):
        base -= 8                                           # good at code, weaker as a general chat
    if re.search(r"\b(nano|tiny|lite|lightning|mini|small)\b|-mini|-nano", m):
        base -= 4
    if "preview" in m or "experimental" in m or "-exp" in m:
        base -= 2
    return max(1, min(100, base))


def _free_openrouter(raw: list[dict]) -> list[Candidate]:
    out = []
    for m in raw:
        p = m.get("pricing") or {}
        arch = m.get("architecture") or {}
        if str(p.get("prompt")) != "0" or str(p.get("completion")) != "0":
            continue
        if arch.get("output_modalities") and arch["output_modalities"] != ["text"]:
            continue
        if _SKIP.search(m["id"]) or m["id"] == "openrouter/free":
            continue
        out.append(Candidate("openrouter", m["id"], score(m["id"]), "image" in (arch.get("input_modalities") or [])))
    # OpenRouter's own router that picks any free model — a last-resort fallback
    if any(m["id"] == "openrouter/free" for m in raw):
        out.append(Candidate("openrouter", "openrouter/free", 50))
    return out


def _vision_guess(model: str) -> bool:
    # qwen3.5 and newer are natively multimodal (checked live: qwen/qwen3.8-27b on Groq reads photos)
    return bool(re.search(r"gemini|vision|-vl|gemma-[34]|llama-4|pixtral|gpt-4o|gpt-4\.1|gpt-5|omni|qwen3\.[5-9]",
                          model, re.I))


def candidates_for(client: Client) -> list[Candidate]:
    raw = client.raw_models()
    pid = client.provider.id
    if pid == "openrouter":
        return _free_openrouter(raw)
    out = []
    for m in raw:
        mid = m["id"]
        if _SKIP.search(mid):
            continue
        if pid == "gemini" and not re.search(r"gemini|gemma", mid):
            continue
        out.append(Candidate(pid, mid, score(mid), _vision_guess(mid)))
    return out


def _check(c: Candidate, client: Client) -> Candidate:
    try:
        c.latency = round(client.ping(c.model), 2)
        c.status = "ok"
    except ProviderError as e:
        c.status = "limited" if e.kind == "rate" else "unavailable"
    return c


def discover(preferred: str = "", ping: bool = True, providers: list[str] | None = None,
             clients: dict[str, Client] | None = None) -> list[Candidate]:
    """All usable free models for the providers that have keys, best first (the user's chosen provider leads)."""
    clients = dict(clients or {})
    ids = providers or [p for p, P in PROVIDERS.items() if not P.local]
    for pid in ids:
        if pid not in clients and (key := keys.get_key(pid)):
            clients[pid] = Client(PROVIDERS[pid], key, timeout=20)
    found: list[Candidate] = []
    for pid, cl in clients.items():
        try:
            cands = sorted(candidates_for(cl), key=lambda c: -c.score)
        except ProviderError:
            continue
        if ping:
            top = cands[:PING_PER_PROVIDER]
            with ThreadPoolExecutor(max_workers=len(top) or 1) as ex:
                list(ex.map(lambda c: _check(c, cl), top))
        found += cands
    return rank(found, preferred)


def rank(cands: list[Candidate], preferred: str = "") -> list[Candidate]:
    usable = [c for c in cands if c.status != "unavailable"]
    order = {"ok": 0, "untested": 1, "limited": 2}
    return sorted(usable, key=lambda c: (c.provider != preferred, order.get(c.status, 3), -c.score, c.latency or 99))


# ---------------------------------------------------------------- cache
def _cache_file():
    return data_dir() / "models.json"


def load_cache(providers: list[str]) -> list[Candidate] | None:
    try:
        d = json.loads(_cache_file().read_text(encoding="utf-8"))
        at = datetime.datetime.fromisoformat(d["at"])
    except (OSError, ValueError, KeyError):
        return None
    if datetime.datetime.now() - at > datetime.timedelta(hours=CACHE_HOURS) or sorted(d.get("providers", [])) != sorted(providers):
        return None
    return [Candidate(**c) for c in d["candidates"] if not _SKIP.search(c.get("model", ""))]   # lists saved by older versions


def save_cache(cands: list[Candidate], providers: list[str]) -> None:
    d = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "providers": sorted(providers),
         "candidates": [asdict(c) for c in cands]}
    _cache_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def configured_providers() -> list[str]:
    return [p for p, P in PROVIDERS.items() if not P.local and keys.get_key(p)]


def cloud_models(preferred: str = "", refresh: bool = False) -> list[Candidate]:
    provs = configured_providers()
    if not provs:
        return []
    if not refresh and (cached := load_cache(provs)) is not None:
        return rank(cached, preferred)
    cands = discover(preferred, providers=provs)
    save_cache(cands, provs)
    return cands


def local_models(picks: dict | None = None) -> list[Candidate]:
    """Chat models installed in Ollama, the user's picks first (picks: {"chat": name, "vision": name})."""
    from . import local                                       # only touches localhost
    from .hardware import CATALOG
    picks = picks or {}
    known = {m.name: m for m in CATALOG}
    out = []
    for m in local.installed():
        if not m.chat:
            continue
        s = score(m.name)
        if m.name in known:                                   # models we recommend beat random ones
            s = 70 + int(known[m.name].min_vram)
        if m.vision and m.name not in known and "gemma" not in m.name:
            s -= 10                                           # photo-only models are weaker at plain chat
        if m.name == picks.get("chat"):
            s = 1000
        elif m.name == picks.get("vision"):
            s = 900 if not picks.get("chat") else 500
        out.append(Candidate("ollama", m.name, s, m.vision, "ok", None, m.tools))
    # photos go to the chosen photo model, else to the best recommended one (qwen3-vl beats gemma at reading images)
    photo = picks.get("vision") or next((m.name for m in sorted(CATALOG, key=lambda m: -m.min_vram)
                                         if m.role == "vision" and any(c.model == m.name for c in out)), "")
    for c in out:
        c.photo = c.model == photo
    return sorted(out, key=lambda c: -c.score)


def get_models(preferred: str = "", refresh: bool = False, mode: str = "cloud",
               picks: dict | None = None) -> list[Candidate]:
    """cloud: free online models. local: only Ollama on this computer. auto: local first, cloud as backup."""
    if mode == "local":
        return local_models(picks)
    if mode == "auto":
        return local_models(picks) + cloud_models(preferred, refresh)
    return cloud_models(preferred, refresh)
