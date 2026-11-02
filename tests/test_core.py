import json
import re
from pathlib import Path

import httpx
import pytest

from lanterna import i18n, keys, soul
from lanterna.chat import Conversation
from lanterna.config import Settings
from lanterna.providers import PROVIDERS, Client, ProviderError, _ThinkFilter


def sse(*chunks: str) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def client_with(handler) -> Client:
    return Client(PROVIDERS["groq"], "test-key", transport=httpx.MockTransport(handler))


# --- providers -------------------------------------------------------------
def test_stream_and_auth_header():
    seen = {}

    def h(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=sse("Hel", "lo"), headers={"content-type": "text/event-stream"})

    c = client_with(h)
    assert c.chat("m", [{"role": "user", "content": "hi"}]) == "Hello"
    assert seen["auth"] == "Bearer test-key" and seen["body"]["stream"] is True


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate"), (400, "bad_request"), (500, "other")])
def test_error_kinds(status, kind):
    c = client_with(lambda r: httpx.Response(status, json={"error": {"message": "nope"}}, headers={"retry-after": "7"}))
    with pytest.raises(ProviderError) as e:
        c.chat("m", [])
    assert e.value.kind == kind and str(e.value) == "nope"
    if status == 429:
        assert e.value.retry_after == 7


def test_gemini_error_in_a_list():
    # Gemini answers errors as [{"error": {...}}]; this used to crash with "'list' object has no attribute 'get'"
    body = [{"error": {"code": 429, "message": "Quota exceeded for gemini-3.1-pro", "status": "RESOURCE_EXHAUSTED"}}]
    c = client_with(lambda r: httpx.Response(429, json=body))
    with pytest.raises(ProviderError) as e:
        c.chat("m", [])
    assert e.value.kind == "rate" and str(e.value) == "Quota exceeded for gemini-3.1-pro"
    for odd in ([], ["text"], "plain", None):
        c = client_with(lambda r, odd=odd: httpx.Response(500, json=odd))
        with pytest.raises(ProviderError) as e:
            c.chat("m", [])
        assert e.value.kind == "other"


def test_network_error():
    def h(req):
        raise httpx.ConnectError("offline")
    with pytest.raises(ProviderError) as e:
        client_with(h).list_models()
    assert e.value.kind == "network"


@pytest.mark.parametrize("pid", list(PROVIDERS))
def test_requests_stay_on_provider_host(pid):
    """Keys must only ever be sent to the provider's own host."""
    p = PROVIDERS[pid]
    hosts = []

    def h(req):
        hosts.append(req.url.host)
        if req.url.path.endswith("models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(200, content=sse("ok"))

    c = Client(p, "k", transport=httpx.MockTransport(h))
    c.list_models()
    c.chat("m", [])
    assert set(hosts) == {httpx.URL(p.base_url).host}


def test_no_unexpected_domains_in_sources():
    allowed = {"api.groq.com", "console.groq.com", "generativelanguage.googleapis.com", "aistudio.google.com",
               "openrouter.ai", "api.cerebras.ai", "cloud.cerebras.ai", "api.mistral.ai", "console.mistral.ai",
               "models.github.ai", "git" "hub.com", "localhost", "127.0.0.1", "ollama.com",
               # keyless tools: weather (Open-Meteo) and web search (DuckDuckGo)
               "api.open-meteo.com", "geocoding-api.open-meteo.com", "air-quality-api.open-meteo.com",
               "html.duckduckgo.com",
               # model sizes for the Download buttons (manifests only)
               "registry.ollama.ai",
               # optional Google sign-in and sync to the user's own Drive (hidden app folder)
               "accounts.google.com", "oauth2.googleapis.com", "www.googleapis.com",
               # the project's own pages (privacy policy)
               "mikybuilds.github.io"}
    root = Path(__file__).parents[1]
    files = [*root.joinpath("src").rglob("*.py"), *root.joinpath("src").rglob("*.js"), *root.joinpath("src").rglob("*.html"), root / "pyproject.toml", root / "README.md"]
    found = {h for f in files if f.exists() for h in re.findall(r"https?://([^/\s\"'`)>:]+)", f.read_text(encoding="utf-8"))}
    assert found <= allowed, found - allowed


def test_missing_key():
    with pytest.raises(ProviderError):
        Client(PROVIDERS["groq"], None)
    Client(PROVIDERS["ollama"], None).close()     # local needs no key


def test_pick_model_prefers_known_and_skips_non_chat():
    c = client_with(lambda r: httpx.Response(200, json={"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.3-70b-versatile"}]}))
    assert c.pick_model() == "llama-3.3-70b-versatile"
    assert c.pick_model(["whisper-large-v3", "some-new-model"]) == "some-new-model"
    with pytest.raises(ProviderError):
        c.pick_model(["whisper-large-v3"])


@pytest.mark.parametrize("chunks", [
    ["<think>plan</think>Answer"],
    ["<thi", "nk>plan", " more</th", "ink>\nAns", "wer"],
    ["Ans", "wer"],
])
def test_think_filter(chunks):
    f = _ThinkFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == "Answer"


def test_think_filter_keeps_plain_angle_brackets():
    f = _ThinkFilter()
    assert "".join(f.feed(c) for c in ["a < b and ", "x<y"]) + f.flush() == "a < b and x<y"


# --- soul ------------------------------------------------------------------
def test_humanize_trims_templates():
    assert soul.humanize("Of course! The capital of Italy is Rome, a lovely city.") == "The capital of Italy is Rome, a lovely city."
    assert soul.humanize("Ось відповідь на твоє питання про Рим. Якщо у тебе є ще питання — звертайся!") == "Ось відповідь на твоє питання про Рим."
    assert soul.humanize("```py\nprint(1)\n```\nLet me know if it works!").endswith("works!")


def test_mood_detection_three_languages():
    assert soul.mood("мені сьогодні дуже сумно") == "sad"
    assert soul.mood("sono stanco morto") == "stressed"
    assert soul.mood("thanks a lot") == "thanks"
    assert soul.mood("what's the weather") == ""


def test_persona_has_name_and_no_private_facts():
    p = soul.persona("Anna")
    assert "Anna" in p and "Lanterna" in p
    assert not re.search(r"Jarvis|Мікі|Miky|ClasseViva", p)


# --- chat ------------------------------------------------------------------
def test_conversation_keeps_history_and_system_prompt():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=sse("Of course! Rome is the capital of Italy, for sure."))

    from lanterna.discovery import Candidate
    from lanterna.router import Router
    conv = Conversation(Router([Candidate("groq", "m", 50)], client_for=lambda pid: client_with(h)), "Anna")
    "".join(conv.ask("capital of Italy?"))
    assert conv.last_reply == "Rome is the capital of Italy, for sure."
    "".join(conv.ask("and France?"))
    msgs = bodies[-1]["messages"]
    assert msgs[0]["role"] == "system" and "Anna" in msgs[0]["content"]
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant", "user"]


# --- settings & keys ------------------------------------------------------------
def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    s = Settings(lang="uk", name="Anna", provider="gemini", onboarded=True)
    s.save()
    assert Settings.load() == s
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    assert Settings.load() == Settings()
    assert "key" not in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_env_key_wins(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", " gsk_from_env ")
    assert keys.get_key("groq") == "gsk_from_env"
    assert keys.mask("gsk_1234567890abcd") == "gsk_…abcd"


# --- i18n ------------------------------------------------------------------
def test_every_cli_string_is_translated():
    root = Path(__file__).parents[1].joinpath("src/lanterna")
    src = "".join((root / f).read_text(encoding="utf-8") for f in ("cli.py", "tui.py"))
    used = set(re.findall(r'\bt\("([^"]+)"', src)) | set(re.findall(r"\bt\('([^']+)'", src))
    used |= {tag for _, tag, _ in __import__("lanterna.cli", fromlist=["x"]).FIRST_CHOICES}
    used |= {det for _, _, det in __import__("lanterna.cli", fromlist=["x"]).FIRST_CHOICES}
    missing = [s for s in used if s not in i18n._T or set(i18n._T[s]) != {"uk", "it"}]
    assert not missing, missing
