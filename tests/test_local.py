"""Stage 5: hardware advice, Ollama client, local/auto modes. No real downloads: Ollama is mocked."""
import json

import httpx
import pytest

from lanterna import discovery, hardware, local
from lanterna.chat import Conversation, is_hard
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router, Switched


# ------------------------------------------------------------------------------ hardware advice
def names(adv):
    return [m.name for m in adv.models]


def test_advice_8gb_card_gets_the_8b_trio():
    a = hardware.advise(hardware.Hardware(vram_gb=8.0, ram_gb=16))
    assert a.tier == "medium" and a.mode == "auto"
    assert names(a) == ["gemma4:e4b-it-qat", "qwen3:8b", "qwen3-vl:8b-instruct"]


def test_advice_small_big_and_none():
    assert names(hardware.advise(hardware.Hardware(vram_gb=4, ram_gb=16))) == \
        ["gemma4:e2b-it-qat", "qwen3:4b", "qwen3-vl:4b-instruct"]
    big = hardware.advise(hardware.Hardware(vram_gb=12, ram_gb=32))
    assert big.mode == "local" and "qwen3:14b" in names(big)
    weak = hardware.advise(hardware.Hardware(vram_gb=0, ram_gb=8))
    assert weak.tier == "none" and weak.mode == "cloud" and names(weak) == ["qwen3:1.7b"]
    assert names(hardware.advise(hardware.Hardware(vram_gb=0, ram_gb=4))) == []


def test_catalog_uses_instruct_vision_models():
    vision = [m.name for m in hardware.CATALOG if m.role == "vision"]
    assert vision and all("instruct" in n for n in vision)        # the thinking variants are slow


def test_detect_returns_something_sane():
    hw = hardware.detect()
    assert hw.ram_gb > 0 and hw.disk_free_gb >= 0


# ------------------------------------------------------------------------------ Ollama client
def pull_lines(*objs):
    return ("\n".join(json.dumps(o) for o in objs) + "\n").encode()


def test_download_progress_adds_up_layers():
    seen = []

    def h(req):
        assert req.url.path == "/api/pull" and json.loads(req.content)["model"] == "qwen3:4b"
        seen.append(req.url.host)
        return httpx.Response(200, content=pull_lines(
            {"status": "pulling manifest"},
            {"status": "pulling a", "digest": "sha256:a", "total": 1000, "completed": 500},
            {"status": "pulling b", "digest": "sha256:b", "total": 1000, "completed": 1000},
            {"status": "pulling a", "digest": "sha256:a", "total": 1000, "completed": 1000},
            {"status": "verifying sha256 digest"},
            {"status": "success"}))

    d = local.Downloads(transport=httpx.MockTransport(h))
    job = d.run_sync("qwen3:4b")
    assert job.status == "done" and job.total_bytes == 2000 and job.percent == 100
    assert seen == ["127.0.0.1"]                                   # only ever talks to Ollama on this PC


def test_download_error_is_reported():
    def h(req):
        return httpx.Response(200, content=pull_lines({"error": "pull model manifest: file does not exist"}))

    job = local.Downloads(transport=httpx.MockTransport(h)).run_sync("nope:1b")
    assert job.status == "error" and "does not exist" in job.error


def test_download_stops_when_stream_ends_early():
    def h(req):
        return httpx.Response(200, content=pull_lines({"status": "pulling a", "digest": "a", "total": 10, "completed": 3}))

    job = local.Downloads(transport=httpx.MockTransport(h)).run_sync("x:1b")
    assert job.status == "error"


def test_pull_needs_a_valid_name_and_running_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna.app import Api
    from lanterna.store import Store
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    started = []
    monkeypatch.setattr(api._downloads, "start", lambda n: started.append(n))
    assert api.pull_model("rm -rf /")["error"] == "name"
    assert api.pull_model("qwen3:4b; echo")["error"] == "name"
    monkeypatch.setattr(local, "version", lambda: None)
    assert api.pull_model("qwen3:4b")["error"] == "ollama"
    monkeypatch.setattr(local, "version", lambda: "0.40")
    assert api.pull_model("qwen3:4b")["ok"] and started == ["qwen3:4b"]


# ------------------------------------------------------------------------------ modes
INSTALLED = [local.LocalModel("gemma4:e4b-it-qat", 6.1, vision=True), local.LocalModel("qwen3:8b", 5.2),
             local.LocalModel("bge-m3:latest", 1.1, tools=False, chat=False),
             local.LocalModel("llava:latest", 4.7, vision=True, tools=False)]


def test_local_models_skip_embeddings_and_respect_picks(monkeypatch):
    monkeypatch.setattr(local, "installed", lambda: INSTALLED)
    cs = discovery.local_models()
    assert [c.model for c in cs][:2] == ["gemma4:e4b-it-qat", "qwen3:8b"] and "bge-m3:latest" not in [c.model for c in cs]
    assert all(c.provider == "ollama" for c in cs)
    llava = next(c for c in cs if c.model == "llava:latest")
    assert llava.vision and not llava.tools
    assert discovery.local_models({"chat": "qwen3:8b"})[0].model == "qwen3:8b"


def test_get_models_by_mode(monkeypatch):
    monkeypatch.setattr(local, "installed", lambda: INSTALLED)
    monkeypatch.setattr(discovery, "cloud_models", lambda p="", r=False: [Candidate("groq", "big", 86, status="ok")])
    assert [c.provider for c in discovery.get_models(mode="cloud")] == ["groq"]
    assert {c.provider for c in discovery.get_models(mode="local")} == {"ollama"}
    auto = discovery.get_models(mode="auto")
    assert auto[0].provider == "ollama" and auto[-1].provider == "groq"


def sse(text):
    return (f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n").encode()


def mixed_router():
    def client_for(pid):
        def h(req):
            return httpx.Response(200, content=sse(f"from {pid}"))
        key = None if PROVIDERS[pid].local else "k"
        return Client(PROVIDERS[pid], key, transport=httpx.MockTransport(h))
    return Router([Candidate("ollama", "gemma4:e4b-it-qat", 1000), Candidate("ollama", "llava:latest", 60, vision=True, tools=False),
                   Candidate("groq", "big", 86)], client_for=client_for)


def test_router_knows_models_without_tools():
    assert ("ollama", "llava:latest") in mixed_router().no_tools


def test_auto_mode_sends_hard_questions_to_the_cloud():
    r = mixed_router()
    conv = Conversation(r, "Anna", auto_cloud=True)
    easy = "".join(p for p in conv.ask("Ciao!") if isinstance(p, str))
    assert easy == "from ollama"
    out = list(conv.ask("Доведи покроково, що корінь з 2 ірраціональний"))
    assert any(isinstance(p, Switched) and p.to.provider == "groq" for p in out)
    assert "".join(p for p in out if isinstance(p, str)) == "from groq"
    back = "".join(p for p in conv.ask("Дякую!") if isinstance(p, str))
    assert back == "from ollama"                                  # easy questions return to the local model


def test_auto_cloud_off_keeps_everything_local():
    conv = Conversation(mixed_router(), "Anna", auto_cloud=False)
    assert "".join(p for p in conv.ask("Prove that sqrt(2) is irrational") if isinstance(p, str)) == "from ollama"


def test_local_failure_falls_back_to_cloud():
    def client_for(pid):
        def h(req):
            if PROVIDERS[pid].local:
                raise httpx.ConnectError("Ollama is not running")
            return httpx.Response(200, content=sse("cloud"))
        return Client(PROVIDERS[pid], None if PROVIDERS[pid].local else "k", transport=httpx.MockTransport(h))
    r = Router([Candidate("ollama", "gemma4:e4b-it-qat", 1000), Candidate("groq", "big", 86)], client_for=client_for)
    assert "".join(p for p in r.stream([{"role": "user", "content": "hi"}]) if isinstance(p, str)) == "cloud"


@pytest.mark.parametrize("text,hard", [
    ("Ciao!", False), ("Яка погода в Феррарі?", False), ("What time is it in Tokyo?", False),
    ("Доведи, що сума кутів трикутника 180°", True), ("Analizza questo testo", True),
    ("Explain step by step how RSA works", True), ("```python\nprint(1)\n```", True), ("x" * 800, True),
])
def test_is_hard(text, hard):
    assert is_hard(text) is hard


def test_photos_go_to_the_photo_model(monkeypatch):
    monkeypatch.setattr(local, "installed", lambda: INSTALLED + [local.LocalModel("qwen3-vl:8b-instruct", 6.1, vision=True)])
    cs = discovery.local_models({"chat": "gemma4:e4b-it-qat"})
    assert cs[0].model == "gemma4:e4b-it-qat"
    assert [c.model for c in cs if c.photo] == ["qwen3-vl:8b-instruct"]
    assert [c.model for c in discovery.local_models({"vision": "llava:latest"}) if c.photo] == ["llava:latest"]
    seen = []

    def client_for(pid):
        def h(req):
            seen.append(json.loads(req.content)["model"])
            return httpx.Response(200, content=sse("ok"))
        return Client(PROVIDERS[pid], None, transport=httpx.MockTransport(h))
    r = Router(cs, client_for=client_for)
    list(r.stream([{"role": "user", "content": "photo"}], need_vision=True))
    list(r.stream([{"role": "user", "content": "text"}]))
    assert seen[0] == "qwen3-vl:8b-instruct" and seen[-1] == "gemma4:e4b-it-qat"
