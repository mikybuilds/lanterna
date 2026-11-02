import json

import httpx
import pytest

from lanterna import discovery
from lanterna.discovery import Candidate, candidates_for, rank, score
from lanterna.providers import PROVIDERS, Client, ProviderError
from lanterna.router import AllFailed, Router, Switched


def sse(text: str) -> bytes:
    return (f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n").encode()


def mock_client(pid: str, handler) -> Client:
    return Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(handler))


# --- scoring & filtering ------------------------------------------------------------
def test_score_known_and_unknown_models():
    assert score("gemini-2.5-pro") > score("gemini-2.5-flash") > score("gemini-2.5-flash-lite")
    assert score("openai/gpt-oss-120b") > score("openai/gpt-oss-20b")
    # unknown future models are judged by size
    assert score("acme/brainy-550b-a55b:free") > score("acme/brainy-30b:free") > score("acme/tiny-2.6b:free")
    assert score("cohere/north-mini-code:free") < score("acme/brainy-30b:free")


OPENROUTER_RAW = [
    {"id": "big/model-120b:free", "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
    {"id": "paid/model-400b", "pricing": {"prompt": "0.000001", "completion": "0.000002"}, "architecture": {"output_modalities": ["text"]}},
    {"id": "google/lyria-3-pro-preview", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"output_modalities": ["text", "audio"]}},
    {"id": "nvidia/nemotron-3.5-content-safety:free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"output_modalities": ["text"]}},
    {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"output_modalities": ["text"]}},
]


def test_openrouter_only_free_text_chat_models():
    c = mock_client("openrouter", lambda r: httpx.Response(200, json={"data": OPENROUTER_RAW}))
    got = {x.model: x for x in candidates_for(c)}
    assert set(got) == {"big/model-120b:free", "openrouter/free"}            # no paid, no audio, no safety filter
    assert got["big/model-120b:free"].vision is True
    assert got["openrouter/free"].score < got["big/model-120b:free"].score   # router is a last resort


def test_groq_skips_speech_and_guards():
    raw = {"data": [{"id": i} for i in ["whisper-large-v3", "openai/gpt-oss-120b", "meta-llama/llama-prompt-guard-2-86m",
                                        "openai/gpt-oss-safeguard-20b", "canopylabs/orpheus-v1-english", "qwen/qwen3.8-27b"]]}
    c = mock_client("groq", lambda r: httpx.Response(200, json=raw))
    assert {x.model for x in candidates_for(c)} == {"openai/gpt-oss-120b", "qwen/qwen3.8-27b"}


def test_discover_pings_top_models_and_drops_unavailable():
    def h(req):
        if req.url.path.endswith("models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "qwen/qwen3.8-27b"}, {"id": "openai/gpt-oss-20b"}]})
        model = json.loads(req.content)["model"]
        if model == "openai/gpt-oss-120b":
            return httpx.Response(429, json={"error": {"message": "limit"}})
        if model == "qwen/qwen3.8-27b":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    found = discovery.discover("groq", clients={"groq": mock_client("groq", h)})
    assert [(c.model, c.status) for c in found] == [("openai/gpt-oss-20b", "ok"), ("openai/gpt-oss-120b", "limited")]


def test_rank_puts_chosen_provider_first():
    cs = [Candidate("gemini", "gemini-2.5-pro", 94, status="ok"), Candidate("groq", "openai/gpt-oss-120b", 86, status="ok"),
          Candidate("groq", "x", 99, status="limited")]
    assert [c.model for c in rank(cs, "groq")] == ["openai/gpt-oss-120b", "x", "gemini-2.5-pro"]
    assert rank(cs, "gemini")[0].model == "gemini-2.5-pro"


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    cs = [Candidate("groq", "m", 80, status="ok", latency=0.4)]
    discovery.save_cache(cs, ["groq"])
    assert discovery.load_cache(["groq"]) == cs
    assert discovery.load_cache(["groq", "gemini"]) is None                  # new key -> search again


# --- router ------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def router_with(behaviour: dict, clock=None) -> Router:
    """behaviour: model -> status code or text."""
    def h(req):
        b = behaviour[json.loads(req.content)["model"]]
        if isinstance(b, int):
            return httpx.Response(b, json={"error": {"message": f"err {b}"}})
        return httpx.Response(200, content=sse(b))

    cands = [Candidate("groq", m, 80 - i) for i, m in enumerate(behaviour)]
    return Router(cands, client_for=lambda pid: mock_client(pid, h), clock=clock or Clock())


def test_router_falls_back_on_limit_and_remembers():
    clock = Clock()
    r = router_with({"a": 429, "b": "from b"}, clock)
    out = list(r.stream([]))
    assert isinstance(out[0], Switched) and out[0].to.model == "b" and out[0].reason == "rate"
    assert out[1:] == ["from b"]
    assert list(r.stream([])) == ["from b"]                 # "a" is cooling down, no new switch notice
    clock.t += 61
    r2 = list(r.stream([]))
    assert isinstance(r2[0], Switched) and r2[0].to.model == "a"   # back to the best one after cooldown, which fails again
    assert r2[-1] == "from b"


def test_router_all_failed():
    r = router_with({"a": 429, "b": 503})
    with pytest.raises(AllFailed) as e:
        list(r.stream([]))
    assert e.value.kind == "other"


def test_router_vision_filter():
    r = router_with({"a": "text only", "b": "sees images"})
    r.candidates[1].vision = True
    assert [p for p in r.stream([], need_vision=True) if isinstance(p, str)] == ["sees images"]


def test_router_does_not_switch_mid_answer():
    def h(req):
        def gen():
            yield f"data: {json.dumps({'choices': [{'delta': {'content': 'half'}}]})}\n\n".encode()
            raise httpx.ReadError("cut")
        return httpx.Response(200, content=gen())

    r = Router([Candidate("groq", "a", 80), Candidate("groq", "b", 70)], client_for=lambda pid: mock_client(pid, h))
    got = []
    with pytest.raises(ProviderError):
        for p in r.stream([]):
            got.append(p)
    assert got == ["half"]
