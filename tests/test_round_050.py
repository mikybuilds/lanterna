"""0.5.0 stage 2: a fast side model for small jobs, chat names written by it. No real network."""
import json

import httpx
import pytest

from lanterna import keys
from lanterna.chat import TITLE_PROMPT, chat_title, clean_title
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client, ProviderError
from lanterna.router import Router


# ---------------------------------------------------------------- the side model
def test_quick_order_prefers_a_mid_size_online_model_and_keeps_gemini_for_answers():
    r = Router([Candidate("gemini", "gemini-3.6-flash", 88), Candidate("groq", "openai/gpt-oss-120b", 86),
                Candidate("groq", "openai/gpt-oss-20b", 72), Candidate("ollama", "qwen3:8b", 60)])
    order = [c.model for c in r.quick_order()]
    assert order[0] == "openai/gpt-oss-20b"
    assert order[-1] == "gemini-3.6-flash"
    assert "qwen3:8b" not in order                      # online models exist: the local one is not used for side jobs


def test_quick_order_uses_local_models_in_local_mode():
    r = Router([Candidate("ollama", "qwen3:8b", 60)])
    assert [c.model for c in r.quick_order()] == ["qwen3:8b"]


class _Fake:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def chat(self, model, messages, temperature=0.7):
        self.asked.append(model)
        a = self.answers[model]
        if isinstance(a, Exception):
            raise a
        return a


def test_quick_moves_on_after_an_error_and_never_changes_the_answering_model():
    fake = _Fake({"small": ProviderError("rate", "limit"), "big": "Ok"})
    r = Router([Candidate("groq", "big", 86), Candidate("groq", "small", 70)], client_for=lambda pid: fake)
    before = r.current
    assert r.quick([{"role": "user", "content": "x"}]) == "Ok"
    assert fake.asked == ["small", "big"] and r.current is before


def test_quick_gives_empty_text_when_nothing_answers():
    fake = _Fake({"m": ProviderError("network", "offline")})
    assert Router([Candidate("groq", "m", 70)], client_for=lambda pid: fake).quick([]) == ""
    assert Router([]).quick([]) == ""


# ---------------------------------------------------------------- chat names
@pytest.mark.parametrize("raw, want", [
    ("Погода у Феррарі", "Погода у Феррарі"),
    ('"Flowgorithm: ім\'я з великої."', "Flowgorithm: ім'я з великої"),
    ("Title: **Trip to Rome**\nmore text", "Trip to Rome"),
    ("\n\n  Назва: Рецепт борщу  ", "Рецепт борщу"),
    ("", ""),
    ("x", ""),
    ("word " * 40, ""),
])
def test_clean_title(raw, want):
    assert clean_title(raw) == want


def test_chat_title_asks_with_the_title_prompt():
    seen = []
    title = chat_title(lambda msgs: seen.append(msgs) or "Рецепт борщу.", "як зварити борщ?", "Ось рецепт…")
    assert title == "Рецепт борщу"
    assert seen[0][0]["content"] == TITLE_PROMPT and "як зварити борщ?" in seen[0][1]["content"]


def _sse(text):
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


def _api(tmp_path, monkeypatch, titles=True):
    import time

    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.ai_titles = titles
    bodies = []

    def h(req):
        body = json.loads(req.content)
        bodies.append(body)
        if body["messages"][0]["content"] == TITLE_PROMPT:
            return httpx.Response(200, content=_sse("Борщ на вечерю"))
        return httpx.Response(200, content=_sse("Ось рецепт борщу."))
    a._router = Router([Candidate("groq", "m", 70)],
                       client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))

    def wait(sid):
        for _ in range(300):
            p = a.poll(sid)
            if p["done"]:
                return p
            time.sleep(0.02)
        raise AssertionError("no answer")
    return a, bodies, wait


def test_a_new_chat_gets_a_name_after_the_first_answer(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    p = wait(a.send(tid, "як зварити борщ на вечерю для трьох людей?")["stream"])
    assert p["titling"] is True
    assert a.wait_title(tid) == "Борщ на вечерю"
    assert len(bodies) == 2                              # the answer + one small request for the name

    p = wait(a.send(tid, "а без м'яса?")["stream"])        # later answers don't rename the chat
    assert not p["titling"] and a.wait_title(tid) == "Борщ на вечерю" and len(bodies) == 3


def test_no_name_request_when_switched_off(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch, titles=False)
    tid = a.new_thread()["id"]
    p = wait(a.send(tid, "як зварити борщ?")["stream"])
    assert not p["titling"] and len(bodies) == 1
    assert a.wait_title(tid) == "як зварити борщ?"


def test_a_name_the_user_typed_meanwhile_is_kept(tmp_path, monkeypatch):
    a, _, _ = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    a.store.rename(tid, "Мій чат")
    a._name_chat(tid, a._router, "питання", "відповідь", auto="питання")
    assert a.store.thread(tid)["title"] == "Мій чат"


def test_ai_titles_setting_is_saved_and_synced():
    from lanterna.sync import PREFS
    assert "ai_titles" in PREFS
