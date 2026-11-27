"""Local models from Hugging Face: the GGUF models people use now (as on huggingface.co/models?sort=trending), with a
search, sizes and whether each one runs on this computer. Ollama downloads the chosen file itself
(`hf.co/<repo>:<file>.gguf`, see huggingface.co/docs/hub/ollama), so nothing new runs here.

Nothing is fetched on its own: only when the user opens the catalog, searches or picks a size. Only the search
words go to Hugging Face, no account and no key.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx

API = "https://huggingface.co"
PAGE = "https://huggingface.co/"
SORTS = {"trending": "trendingScore", "downloads": "downloads", "likes": "likes", "new": "lastModified"}
LIMIT = 30
TTL = 600                                       # seconds a page or a file list stays in memory

# Bits per weight of each kind of quantization (llama.cpp's own tables, rounded): sizes before the file list is
# known, and a check that a file is the model and not a small helper with the same quant in its name.
BITS = {"IQ1_S": 1.56, "IQ1_M": 1.75, "TQ1_0": 1.69, "IQ2_XXS": 2.06, "TQ2_0": 2.06, "IQ2_XS": 2.31, "IQ2_S": 2.5,
        "IQ2_M": 2.7, "Q2_K": 2.96, "Q2_K_S": 2.8, "Q2_K_L": 3.2, "Q2_K_XL": 3.1, "IQ3_XXS": 3.06, "IQ3_XS": 3.3,
        "IQ3_S": 3.44, "IQ3_M": 3.66, "Q3_K_S": 3.5, "Q3_K_M": 3.9, "Q3_K_L": 4.27, "Q3_K_XL": 4.1, "IQ4_XS": 4.25,
        "IQ4_NL": 4.5, "MXFP4": 4.25, "Q4_0": 4.55, "Q4_1": 5.0, "Q4_K_S": 4.58, "Q4_K_M": 4.85, "Q4_K_L": 5.1,
        "Q4_K_XL": 5.0, "Q5_0": 5.5, "Q5_1": 6.0, "Q5_K_S": 5.54, "Q5_K_M": 5.69, "Q5_K_L": 5.9, "Q5_K_XL": 5.9,
        "Q6_K": 6.56, "Q6_K_L": 6.8, "Q6_K_XL": 6.8, "Q8_0": 8.5, "Q8_K_XL": 9.0, "F16": 16.0, "BF16": 16.0,
        "F32": 32.0}
_QUANT = re.compile(r"(?:^|[-_.])((?:UD-)?(?:I?Q\d(?:_[A-Z0-9]+)*|TQ\d_\d|MXFP4|BF16|F16|F32))\.gguf$", re.I)
# Not the model itself: the picture part of a vision model, a draft model for speed, the imatrix data, a part of a
# split file (Ollama can't join them)
_HELPER = re.compile(r"(?i)mmproj|^(?:dspark|draft|imatrix)|[-_.]draft[-_.]|-\d{5}-of-\d{5}\.gguf$")
# Only models that write text (a chat or a chat with photos); no image, sound or search-index models
_TEXT = {"text-generation", "image-text-to-text", "text2text-generation", None, ""}
# Not in the list either: what Hugging Face itself marks as adult content, and search-index models (embeddings,
# rerankers) that turn text into numbers instead of answering
_SKIP_TAGS = {"not-for-all-audiences", "nsfw", "feature-extraction", "sentence-similarity", "text-ranking"}
_INDEX = re.compile(r"(?i)embed|rerank")
# Fits: the file plus room for the conversation (the KV cache) and Ollama itself
_ROOM, _OVER = 1.15, 0.6


@dataclass
class Model:
    id: str                       # author/name, as on Hugging Face
    params_b: float               # billions of parameters (0: the repo doesn't say)
    arch: str
    context: int
    downloads: int
    likes: int
    updated: str                  # ISO date
    photos: bool                  # made for chats with photos too
    est_gb: float                 # about how big the usual Q4_K_M file is (0: unknown)
    fit: str                      # gpu | ram | no | "" (unknown)
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class File:
    file: str
    quant: str
    size_gb: float
    fit: str
    name: str = ""                # what Ollama downloads: hf.co/<repo>:<file>

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Machine:
    vram_gb: float = 0.0
    ram_gb: float = 0.0


def fit(size_gb: float, m: Machine) -> str:
    """gpu: fast, all on the graphics card; ram: works, slower (in memory, or split between card and memory);
    no: too big for this computer."""
    if size_gb <= 0:
        return ""
    need = size_gb * _ROOM + _OVER
    if m.vram_gb >= 2 and need <= m.vram_gb:
        return "gpu"
    if need <= max(0.0, m.ram_gb - 6) * 0.9 + m.vram_gb * 0.9:
        return "ram"
    return "no"


def quant_of(file: str) -> str:
    q = _QUANT.search(file.rsplit("/", 1)[-1])
    return q.group(1).upper() if q else ""


_ROUGH = re.compile(r"^(I?)Q(\d)")


def _bits(quant: str) -> float:
    q = quant.upper().removeprefix("UD-")
    if q in BITS:
        return BITS[q]
    m = _ROUGH.match(q)                               # a new name (Q6_K_M, Q8_K_L…): by its number of bits
    if not m:
        return 0.0
    n = int(m.group(2))
    return {1: 1.7, 2: 2.6, 3: 3.6, 4: 4.6, 5: 5.6, 6: 6.6, 8: 8.6}.get(n, float(n)) - (0.3 if m.group(1) else 0.0)


def ollama_name(repo: str, file: str) -> str:
    return f"hf.co/{repo}:{file}"


_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class _Cached:
    at: float
    value: dict = field(default_factory=dict)


class Hub:
    """Pages of models and the files of one model, kept in memory for a while (opening the tab twice asks once)."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport
        self._cache: dict[tuple, _Cached] = {}
        self._lock = threading.Lock()

    def _get(self, path: str, params: list[tuple[str, str]]) -> httpx.Response:
        with httpx.Client(base_url=API, timeout=15, transport=self._transport,
                          headers={"User-Agent": "Lanterna", "Accept": "application/json"}) as c:
            return c.get(path, params=params)

    def _cached(self, key: tuple, make) -> dict:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit.at < TTL:
                return hit.value
        value = make()
        if value.get("ok"):
            with self._lock:
                self._cache[key] = _Cached(time.time(), value)
                if len(self._cache) > 200:                 # a long evening of searches: forget the oldest
                    for k in sorted(self._cache, key=lambda k: self._cache[k].at)[:100]:
                        self._cache.pop(k, None)
        return value

    def models(self, machine: Machine, query: str = "", sort: str = "trending", cursor: str = "",
               fits_only: bool = True) -> dict:
        """{"ok", "models": [...], "next": cursor or "", "hidden": how many didn't fit} — or {"ok": False, "error"}."""
        query = " ".join(str(query or "").split())[:80]
        sort = sort if sort in SORTS else "trending"
        cursor = str(cursor or "")[:400]
        page = self._cached(("models", query.lower(), sort, cursor), lambda: self._page(query, sort, cursor))
        if not page.get("ok"):
            return page
        out, hidden = [], 0
        for raw in page["rows"]:
            m = _model(raw, machine)
            if m is None:
                continue
            if fits_only and m.fit == "no":
                hidden += 1
                continue
            out.append(m.to_dict())
        return {"ok": True, "models": out, "next": page["next"], "hidden": hidden}

    def _page(self, query: str, sort: str, cursor: str) -> dict:
        params = [("filter", "gguf"), ("sort", SORTS[sort]), ("direction", "-1"), ("limit", str(LIMIT))]
        params += [("expand[]", x) for x in ("gguf", "downloads", "likes", "pipeline_tag", "gated", "lastModified", "tags")]
        if query:
            params.append(("search", query))
        if cursor:
            params.append(("cursor", cursor))
        try:
            r = self._get("/api/models", params)
        except httpx.HTTPError:
            return {"ok": False, "error": "net"}
        if r.status_code == 429:
            return {"ok": False, "error": "busy"}
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        try:
            rows = r.json()
        except ValueError:
            return {"ok": False, "error": "answer"}
        if not isinstance(rows, list):
            return {"ok": False, "error": "answer"}
        nxt = ""
        link = r.links.get("next", {}).get("url", "")
        if link:
            nxt = (parse_qs(urlparse(link).query).get("cursor") or [""])[0]
        return {"ok": True, "rows": [x for x in rows if isinstance(x, dict)], "next": nxt}

    def files(self, repo: str, machine: Machine) -> dict:
        """The model files of one repo that Ollama can download, smallest first, and the one to suggest."""
        repo = str(repo or "").strip()
        if not _REPO.match(repo):
            return {"ok": False, "error": "name"}
        got = self._cached(("files", repo), lambda: self._tree(repo))
        if not got.get("ok"):
            return got
        params = got["params"]
        files = []
        for path, size in got["rows"]:
            quant = quant_of(path)
            if "/" in path or not quant or _HELPER.search(path) or size <= 0:
                continue
            bits = _bits(quant)
            if params and bits and size < params * bits / 8 * 0.4:   # far too small for this model: a helper file
                continue
            gb = round(size / 1e9, 2)
            files.append(File(path, quant, gb, fit(gb, machine), ollama_name(repo, path)))
        files.sort(key=lambda f: f.size_gb)
        return {"ok": True, "files": [f.to_dict() for f in files], "pick": _pick(files), "url": PAGE + repo}

    def _tree(self, repo: str) -> dict:
        try:
            r = self._get(f"/api/models/{repo}", [("blobs", "true"), ("expand[]", "gguf"), ("expand[]", "siblings"),
                                                  ("expand[]", "gated")])
        except httpx.HTTPError:
            return {"ok": False, "error": "net"}
        if r.status_code == 404:
            return {"ok": False, "error": "gone"}
        if r.status_code in (401, 403):
            return {"ok": False, "error": "gated"}
        if r.status_code == 429:
            return {"ok": False, "error": "busy"}
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        try:
            d = r.json()
        except ValueError:
            return {"ok": False, "error": "answer"}
        if d.get("gated") not in (False, None, "false"):
            return {"ok": False, "error": "gated"}
        rows = [(str(s.get("rfilename") or ""), int(s.get("size") or (s.get("lfs") or {}).get("size") or 0))
                for s in d.get("siblings") or [] if isinstance(s, dict)]
        params = int((d.get("gguf") or {}).get("total") or 0)
        return {"ok": True, "rows": [x for x in rows if x[0].lower().endswith(".gguf")], "params": params}


def _model(raw: dict, machine: Machine) -> Model | None:
    rid = str(raw.get("id") or "")
    if not _REPO.match(rid) or raw.get("gated") not in (False, None, "false"):
        return None                                    # a gated model needs a Hugging Face sign-in in Ollama
    pipe = raw.get("pipeline_tag")
    if pipe not in _TEXT:
        return None
    tags = {x.lower() for x in raw.get("tags") or [] if isinstance(x, str)}
    if tags & _SKIP_TAGS or _INDEX.search(rid.split("/", 1)[1]):
        return None
    g = raw.get("gguf") if isinstance(raw.get("gguf"), dict) else {}
    params = int(g.get("total") or 0)
    if pipe in (None, "") and not g.get("chat_template"):
        return None                                    # no chat template: not a chat model (or not one Ollama knows)
    est = round(params * BITS["Q4_K_M"] / 8 / 1e9, 1) if params else 0.0
    return Model(rid, round(params / 1e9, 1), str(g.get("architecture") or ""), int(g.get("context_length") or 0),
                 int(raw.get("downloads") or 0), int(raw.get("likes") or 0), str(raw.get("lastModified") or "")[:10],
                 pipe == "image-text-to-text", est, fit(est, machine), PAGE + rid)


_USUAL = ("Q4_K_M", "Q4_K_XL", "Q4_K_S", "IQ4_XS", "Q4_0")


def _pick(files: list[File]) -> int:
    """Hugging Face's own default for Ollama is Q4_K_M; take it (or the closest) when it runs on the card, else the
    best file that does, else Q4_K_M in memory, else the smallest. -1: nothing to download."""
    if not files:
        return -1
    first: dict[str, int] = {}
    for i, f in enumerate(files):
        first.setdefault(f.quant.removeprefix("UD-"), i)
    usual = [first[q] for q in _USUAL if q in first]
    for i in usual:
        if files[i].fit == "gpu":
            return i
    on_card = [i for i, f in enumerate(files) if f.fit == "gpu" and _bits(f.quant) >= 3]
    if on_card:
        return on_card[-1]
    for i in usual:
        if files[i].fit == "ram":
            return i
    return 0
