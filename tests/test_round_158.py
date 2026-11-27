"""Round 158 (1.1.11b11): how long the model thinks in one chat: Quick, Medium (as usual) or Long.

Asked for «бліц, середнє, і довгі роздуми для тяжкіших завдань». A chat keeps its level like its role. Each service
is told in its own words (Gemini's thinking budget or level, Groq's and Ollama's reasoning effort, OpenRouter's
reasoning, Z.ai's thinking); Medium sends nothing, as before. A model that refuses the level answers as usual and
isn't told again. Long thinking also gets a note to check itself, more tool rounds and, in Auto mode, the online
models first; Quick skips the follow-up buttons. No real model is called here.
"""
import json
import time
from pathlib import Path

import httpx
import pytest

from lanterna import gui, i18n, keys, roles, selfhelp
from lanterna.chat import DEEP_ROUNDS, MAX_TOOL_ROUNDS, Conversation
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client, ProviderError, depth_params
from lanterna.router import Router
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"
OK = b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n'
HI = [{"role": "user", "content": "hi"}]


def test_each_service_is_told_in_its_own_words():
    assert depth_params("groq", "openai/gpt-oss-120b", "quick") == ({"reasoning_effort": "low"}, {})
    assert depth_params("groq", "openai/gpt-oss-120b", "deep") == ({"reasoning_effort": "high"}, {})
    assert depth_params("groq", "qwen/qwen3.8-27b", "quick") == ({"reasoning_effort": "none"}, {})
    assert depth_params("groq", "llama-3.3-70b-versatile", "deep") == ({}, {})          # it doesn't think
    assert depth_params("gemini", "gemini-2.5-flash", "quick") == ({}, {"thinking_budget": 0})
    assert depth_params("gemini", "gemini-2.5-pro", "quick") == ({}, {"thinking_budget": 128})   # Pro can't stop
    assert depth_params("gemini", "gemini-2.5-flash-lite", "deep") == ({}, {"thinking_budget": 24576})
    assert depth_params("gemini", "gemini-3-flash-preview", "quick") == ({}, {"thinking_level": "low"})
    assert depth_params("gemini", "gemini-3.6-flash", "deep") == ({}, {"thinking_level": "high"})
    assert depth_params("gemini", "gemini-2.0-flash", "deep") == ({}, {})
    assert depth_params("openrouter", "openai/gpt-oss-20b:free", "deep") == ({"reasoning": {"effort": "high"}}, {})
    assert depth_params("zai", "glm-4.7-flash", "quick") == ({"thinking": {"type": "disabled"}}, {})
    assert depth_params("ollama", "qwen3:8b", "quick") == ({"reasoning_effort": "none"}, {})
    assert depth_params("ollama", "qwen3:8b", "deep") == ({"reasoning_effort": "high"}, {})
    assert depth_params("cloudflare", "@cf/openai/gpt-oss-120b", "deep") == ({}, {})    # its meter counts the body
    for pid in PROVIDERS:                                       # Medium: as usual, nothing is sent
        for model in ("openai/gpt-oss-120b", "gemini-2.5-flash", "qwen3:8b"):
            assert depth_params(pid, model, "") == ({}, {}) and depth_params(pid, model, "normal") == ({}, {})


def _client(pid, handler):
    return Client(PROVIDERS[pid], None if PROVIDERS[pid].local else "k", transport=httpx.MockTransport(handler))


def test_the_level_goes_with_the_request_and_gemini_keeps_its_thought_summaries():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=OK)
    c = _client("gemini", h)
    assert "".join(p for p in c.stream_chat("gemini-2.5-flash", HI, depth="quick") if isinstance(p, str)) == "ok"
    assert bodies[-1]["extra_body"]["google"]["thinking_config"] == {"include_thoughts": True, "thinking_budget": 0}
    assert "reasoning_effort" not in bodies[-1]                 # never both: Gemini refuses that
    list(c.stream_chat("gemini-2.5-flash", HI))
    assert bodies[-1]["extra_body"]["google"]["thinking_config"] == {"include_thoughts": True}
    g = _client("groq", h)
    list(g.stream_chat("openai/gpt-oss-120b", HI, depth="deep"))
    assert bodies[-1]["reasoning_effort"] == "high" and bodies[-1]["model"] == "openai/gpt-oss-120b"
    list(g.stream_chat("openai/gpt-oss-120b", HI, depth=""))
    assert "reasoning_effort" not in bodies[-1]


def test_a_model_that_refuses_it_answers_as_usual_and_is_not_told_again():
    bodies = []

    def h(req):
        b = json.loads(req.content)
        bodies.append(b)
        if "reasoning_effort" in b:                             # Ollama's words, word for word (checked on 0.40)
            return httpx.Response(400, json={"error": {"message": '"qwen2.5:7b" does not support thinking'}})
        return httpx.Response(200, content=OK)
    c = _client("ollama", h)
    out = [p for p in c.stream_chat("qwen2.5:7b", HI, depth="deep") if isinstance(p, str)]
    assert out == ["ok"] and len(bodies) == 2 and "reasoning_effort" not in bodies[1]
    list(c.stream_chat("qwen2.5:7b", HI, depth="deep"))
    assert len(bodies) == 3 and "reasoning_effort" not in bodies[2]               # not told again
    list(c.stream_chat("qwen3:8b", HI, depth="quick"))                            # another model still is
    assert bodies[3]["reasoning_effort"] == "none"

    def busy(req):
        return httpx.Response(429, json={"error": {"message": "slow down"}})
    with pytest.raises(ProviderError) as e:                     # not about the level: up to the router, as before
        list(_client("ollama", busy).stream_chat("qwen3:8b", HI, depth="quick"))
    assert e.value.kind == "rate"


def test_long_thinking_goes_online_first_in_auto_mode_and_says_how_to_think():
    seen, systems = [], []

    def client_for(pid):
        def h(req):
            seen.append(pid)
            systems.append(json.loads(req.content)["messages"][0]["content"])
            return httpx.Response(200, content=OK)
        return _client(pid, h)
    router = Router([Candidate("ollama", "qwen3:8b", 95), Candidate("groq", "openai/gpt-oss-120b", 80)],
                    client_for=client_for)
    conv = Conversation(router, lang="uk", auto_cloud=True)
    list(conv.ask("Привіт"))
    assert seen[-1] == "ollama" and "long thinking" not in systems[-1] and "quick answers" not in systems[-1]
    conv.depth = "deep"
    list(conv.ask("Привіт"))
    assert seen[-1] == "groq" and roles.DEPTHS["deep"][1] in systems[-1]
    conv.depth = "quick"
    list(conv.ask("Привіт"))
    assert seen[-1] == "ollama" and roles.DEPTHS["quick"][1] in systems[-1]
    assert DEEP_ROUNDS > MAX_TOOL_ROUNDS


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.follow_ups = api.settings.ai_titles = api.settings.auto_memory = False
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=OK)
    router = Router([Candidate("groq", "openai/gpt-oss-120b", 90)],
                    client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(h)))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    return api, bodies


def _ask(api, tid, text):
    sid = api.send(tid, text)["stream"]
    for _ in range(300):
        if api.poll(sid)["done"]:
            return
        time.sleep(0.03)
    raise AssertionError("no answer")


def test_each_chat_keeps_its_own_level(tmp_path, monkeypatch):
    api, bodies = _api(tmp_path, monkeypatch)
    a, b = api.new_thread()["id"], api.new_thread()["id"]
    assert api.set_chat_depth(a, "deep") == {"ok": True, "depth": "deep"}
    assert api.chat_depth(a) == {"depth": "deep"} and api.chat_depth(b) == {"depth": ""}
    _ask(api, a, "Розв'яжи рівняння x^2 - 5x + 6 = 0")
    assert bodies[-1]["reasoning_effort"] == "high" and roles.DEPTHS["deep"][1] in bodies[-1]["messages"][0]["content"]
    _ask(api, b, "Привіт")
    assert "reasoning_effort" not in bodies[-1] and roles.DEPTHS["deep"][1] not in bodies[-1]["messages"][0]["content"]
    api.set_chat_depth(b, "quick")
    _ask(api, b, "Привіт")
    assert bodies[-1]["reasoning_effort"] == "low"
    assert api.set_chat_depth(b, "slowest") == {"ok": True, "depth": ""} and str(b) not in api.settings.chat_depths
    assert api.set_chat_depth(999, "deep")["ok"] is False and api.set_chat_depth(0, "deep")["ok"] is False
    api.delete_thread(a)
    assert str(a) not in api.settings.chat_depths


def test_quick_answers_come_without_follow_up_buttons(tmp_path, monkeypatch):
    api, bodies = _api(tmp_path, monkeypatch)
    api.settings.follow_ups = True
    tid = api.new_thread()["id"]
    api.set_chat_depth(tid, "quick")
    _ask(api, tid, "Привіт")
    assert tid not in api._follow and len(bodies) == 1          # no side request for the buttons
    api.set_chat_depth(tid, "")
    _ask(api, tid, "Привіт")
    assert tid in api._follow


def test_window_terminal_and_help_have_it_in_every_language():
    js = (UI / "app.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert {"chat_depth", "set_chat_depth"} <= gui.METHODS
    assert 'id="depth-btn"' in js and "function depthMenu()" in js and 'id="i-hourglass"' in html
    for d, (name, _) in roles.DEPTHS.items():
        assert f'["{d}", "{name}"' in js
    assert '["", "Medium", "bulb"' in js
    from lanterna import tui
    assert hasattr(tui._ChatScreen, "action_next_depth") and ("How long to think", "next_depth", "F5") in tui.CHAT_COMMANDS
    names = ("Thinking", "Quick", "Medium", "Long thinking", "How long to think")
    for text in names:
        assert i18n.t(text, "uk") != text
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(text), (lang, text)
    about = selfhelp.about("uk")
    assert "«Роздуми»" in about and "«Бліц»" in about and "«Довгі роздуми»" in about and "F5" in about
