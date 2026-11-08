import json
import re
from urllib.parse import urlsplit
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
               "openrouter.ai", "api.mistral.ai", "console.mistral.ai",
               # NVIDIA, Z.ai and Cohere: free tiers (keys made by the user)
               "integrate.api.nvidia.com", "build.nvidia.com", "api.z.ai", "z.ai", "api.cohere.ai",
               "dashboard.cohere.com",
               "git" "hub.com", "localhost", "127.0.0.1", "ollama.com",
               # keyless tools: weather (Open-Meteo) and web search (DuckDuckGo)
               "api.open-meteo.com", "geocoding-api.open-meteo.com", "air-quality-api.open-meteo.com",
               "html.duckduckgo.com",
               # official exchange rates (National Bank of Ukraine, keyless)
               "bank.gov.ua",
               # model sizes for the Download buttons (manifests only)
               "registry.ollama.ai",
               # local voice input: whisper.cpp models (pinned files, checked by SHA-256)
               "huggingface.co",
               # optional Google sign-in and sync to the user's own Drive (hidden app folder)
               "accounts.google.com", "oauth2.googleapis.com", "www.googleapis.com",
               # ready-made MCP servers: where to get Node.js or uv (links the user opens, never fetched)
               "nodejs.org", "docs.astral.sh",
               # the project's own pages (privacy policy)
               "mikybuilds.github.io", "api." "git" "hub.com",
               # the public MCP Registry (Connectors → Browse → search)
               "registry.modelcontextprotocol.io",
               # mail connector: where each mail service makes app passwords (links the user opens)
               "myaccount.google.com", "mail.ukr.net", "account.apple.com", "login.yahoo.com", "accounts.zoho.com"}
    # Connectors: each ready-made connector's own address (checked, made by that service) is reached only after the
    # user adds it; listed in one place, connectors.py, and nowhere else
    from lanterna import connectors
    allowed |= {urlsplit(c["url"]).hostname for c in connectors.CATALOG if c["url"]}
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


@pytest.mark.parametrize("chunks", [
    ["<thought>The user said hi</thought>Answer"],                 # Gemma 4 on Gemini
    ["<thou", "ght>plan</tho", "ught>\nAns", "wer"],
])
def test_thought_filter(chunks):
    f = _ThinkFilter()
    assert "".join(f.feed(c) for c in chunks) + f.flush() == "Answer"


def test_gemini_thought_signature_goes_back_with_the_tool_call():
    # Gemini 3 refuses the next turn ("missing a thought_signature") unless the call comes back with it
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            tc = {"index": 0, "id": "c1", "type": "function", "function": {"name": "calculate", "arguments": '{"expression":"2+2"}'},
                  "extra_content": {"google": {"thought_signature": "SIG"}}}
            return httpx.Response(200, content=f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [tc]}}]})}\n\ndata: [DONE]\n\n".encode())
        return httpx.Response(200, content=sse("4"))

    from lanterna.discovery import Candidate
    from lanterna.router import Router
    from lanterna.tools import Toolbox

    class NoStore:
        def facts(self):
            return []
    conv = Conversation(Router([Candidate("groq", "m", 50)], client_for=lambda pid: client_with(h)), "Anna",
                        toolbox=Toolbox(NoStore()))
    "".join(p for p in conv.ask("what is 2+2? use the calculator") if isinstance(p, str))
    sent = bodies[-1]["messages"][-2]["tool_calls"][0]
    assert sent["extra_content"] == {"google": {"thought_signature": "SIG"}} and conv.last_reply == "4"


def test_a_stuck_model_does_not_block_the_whole_service():
    from lanterna.discovery import Candidate
    from lanterna.router import Router, Switched

    def h(req):
        if json.loads(req.content)["model"] == "slow":
            raise httpx.ReadTimeout("The read operation timed out")
        return httpx.Response(200, content=sse("ok"))
    r = Router([Candidate("groq", "slow", 90), Candidate("groq", "fast", 80)], client_for=lambda pid: client_with(h))
    out = list(r.stream([{"role": "user", "content": "hi"}]))
    assert [p for p in out if isinstance(p, str)] == ["ok"] and isinstance(out[0], Switched)
    assert [c.model for c in r.available()] == ["fast"]            # only the stuck model rests


def test_thought_text_is_kept_for_the_thinking_line():
    f = _ThinkFilter()
    out, inner = "", ""
    for c in ["<thou", "ght>**Plan", "ning**\n\nok</tho", "ught>\nAns", "wer"]:
        out += f.feed(c)
        inner += f.thought()
    assert out + f.flush() == "Answer" and inner == "**Planning**\n\nok"


def test_reasoning_field_and_gemini_summaries_become_thoughts():
    from lanterna.providers import Thought
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        d = [{"reasoning": "Let me check."}, {"content": "Hi"}]
        return httpx.Response(200, content="".join(f"data: {json.dumps({'choices': [{'delta': x}]})}\n\n" for x in d).encode())
    out = list(Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)).stream_chat("m", [{"role": "user", "content": "hi"}]))
    assert out == [Thought("Let me check."), "Hi"] and "extra_body" not in bodies[0]
    list(Client(PROVIDERS["gemini"], "k", transport=httpx.MockTransport(h)).stream_chat("m", [{"role": "user", "content": "hi"}]))
    assert bodies[1]["extra_body"]["google"]["thinking_config"]["include_thoughts"] is True


def test_steps_line():
    from lanterna.thinking import Steps, tool_step
    assert tool_step("web_search", '{"query": "Ferrara news"}', "uk") == "Шукаю в інтернеті: Ferrara news"
    assert tool_step("read_page", '{"url": "https://www.ansa.it/x/y"}', "it") == "Leggo www.ansa.it"
    assert tool_step("weather", "{}", "uk") == "Дивлюсь погоду"
    assert tool_step("something_new", "not json", "en") == "Using something_new"
    s = Steps("en")
    s.thought("*   Problem 1: Calculate $17 \\times 23$.\n")
    assert s.live == "Problem 1: Calculate 17 \\times 23." and s.items == []          # raw thoughts: live line only
    s.thought("**Assessing**\n\nI am looking.\n**Checking the result**\n")
    assert [x["text"] for x in s.items] == ["Assessing", "Checking the result"] and s.live == "Checking the result"
    s.thought("more text")
    assert len(s.items) == 2                                      # the same headings are not added twice
    s.tool("calculate", '{"expression": "17*23"}')
    assert s.view()["live"] == "Calculating: 17*23" and len(s.items) == 3


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
    for lang in i18n.FILE_LANGS:
        table = i18n.catalog(lang)
        gaps = [s for s in used if s not in table]
        assert not gaps, (lang, gaps)


def _window_strings():
    js = Path(__file__).parents[1].joinpath("src/lanterna/ui/app.js").read_text(encoding="utf-8")
    body = js[js.index("const STR = {"):js.index("let LANG")]
    return [json.loads(m.group(1)) for m in re.finditer(r'^\s*("(?:[^"\\]|\\.)*")\s*:\s*\{\s*uk:', body, re.M)]


def test_new_languages_cover_every_string():
    ph = re.compile(r"\{[a-z_]+\}")
    wanted = set(i18n._T) | set(_window_strings())
    assert len(wanted) > 400
    for lang in i18n.FILE_LANGS:
        assert lang in i18n.LANGS
        table = i18n.catalog(lang)
        assert not wanted - set(table), (lang, sorted(wanted - set(table))[:10])
        bad = [k for k, v in table.items() if sorted(ph.findall(k)) != sorted(ph.findall(v)) or not v.strip()]
        assert not bad, (lang, bad[:5])
    assert i18n.t("Hi, {n}!", "de", n="Mia") == "Hallo, Mia!"
    assert i18n.t("Settings", "pl") == "Ustawienia"
    assert i18n.t("no such text", "fr") == "no such text"
