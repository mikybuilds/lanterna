"""0.5.0 stage 2: a fast side model for small jobs, chat names written by it. No real network."""
import json

import httpx
import pytest

from lanterna import keys
from lanterna.chat import FOLLOW_PROMPT, TITLE_PROMPT, chat_title, clean_follow_ups, clean_title, same_call
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


def _api(tmp_path, monkeypatch, titles=True, follow=False):
    import time

    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.ai_titles, a.settings.follow_ups = titles, follow
    bodies = []

    def h(req):
        body = json.loads(req.content)
        bodies.append(body)
        if body["messages"][0]["content"] == TITLE_PROMPT:
            return httpx.Response(200, content=_sse("Борщ на вечерю"))
        if body["messages"][0]["content"] == FOLLOW_PROMPT:
            return httpx.Response(200, content=_sse("1. А без м'яса?\n- Скільки варити?\n«Що подати до борщу?»\nзайве"))
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


# ---------------------------------------------------------------- follow-up buttons
def test_clean_follow_ups():
    assert clean_follow_ups("1. Як?\n2) А чому?\n- Ще\n\n• Далі\nP") == ["Як?", "А чому?", "Ще"]
    assert clean_follow_ups("") == []


def test_follow_ups_after_an_answer(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch, titles=False, follow=True)
    tid = a.new_thread()["id"]
    p = wait(a.send(tid, "як зварити борщ?")["stream"])
    assert p["suggesting"] is True
    assert a.wait_follow_ups(tid) == ["А без м'яса?", "Скільки варити?", "Що подати до борщу?"]
    assert len(bodies) == 2


def test_no_follow_ups_when_only_gemini_or_local_is_left(tmp_path, monkeypatch):
    for provider in ("gemini", "ollama"):
        a, bodies, wait = _api(tmp_path, monkeypatch, titles=False, follow=True)
        a._router.candidates = [Candidate(provider, "m", 70)]
        a._router.current = a._router.candidates[0]
        tid = a.new_thread()["id"]
        p = wait(a.send(tid, "привіт")["stream"])
        assert not p["suggesting"] and a.wait_follow_ups(tid) == []


# ---------------------------------------------------------------- "why" in the "what I'm doing" line
def test_intent_is_offered_on_web_tools_shown_and_never_passed_to_the_tool():
    from lanterna.thinking import tool_step
    from lanterna.tools import Tool, Toolbox, _obj

    got = []
    tb = Toolbox(store=None)
    tb._extra = lambda: [Tool("echo", "", _obj({"x": {"type": "string"}}), lambda x: got.append(x) or "ok", "e")]
    schemas = {s["function"]["name"]: s["function"]["parameters"]["properties"] for s in tb.schemas()}
    assert "intent" in schemas["web_search"] and "intent" not in schemas["calculate"]
    assert tb.run("echo", '{"x": "1", "intent": "щоб перевірити"}') == "ok" and got == ["1"]
    line = tool_step("web_search", '{"query": "Flowgorithm ToUpper", "intent": "щоб знайти точну назву"}', "uk")
    assert line.endswith("— щоб знайти точну назву") and "Flowgorithm ToUpper" in line
    assert same_call("web_search", '{"query": "a b c", "intent": "x"}', "web_search", '{"query": "a b c", "intent": "y"}')


# ---------------------------------------------------------------- long chats get a summary
def test_summary_is_due_every_ten_messages_past_the_recent_twenty():
    from lanterna.chat import summary_due
    assert not summary_due(29, 0) and summary_due(30, 0)
    assert not summary_due(39, 10) and summary_due(40, 10)


def test_summarize_sends_the_old_summary_and_the_messages():
    from lanterna.chat import SUMMARY_PROMPT, summarize
    seen = []
    out = summarize(lambda m: seen.append(m) or "  Новий підсумок ", "Старий підсумок",
                    [{"role": "user", "content": "Мене звати Міша"}, {"role": "assistant", "content": "Привіт!"}])
    assert out == "Новий підсумок"
    assert seen[0][0]["content"] == SUMMARY_PROMPT
    assert "Старий підсумок" in seen[0][1]["content"] and "user: Мене звати Міша" in seen[0][1]["content"]


def test_the_summary_stays_on_this_device(tmp_path):
    from lanterna.store import Store
    s = Store(tmp_path / "s.db")
    tid = s.new_thread()
    before = s.changes
    s.set_summary(tid, "підсумок", 10)
    assert s.summary(tid) == ("підсумок", 10) and s.changes == before    # no sync upload for it


def test_a_long_chat_is_summarized_and_the_summary_goes_to_the_model(tmp_path, monkeypatch):
    import time

    from lanterna.chat import SUMMARY_PROMPT
    a, bodies, wait = _api(tmp_path, monkeypatch, titles=False)
    tid = a.new_thread()["id"]
    for i in range(14):
        a.store.add(tid, "user", f"питання {i}")
        a.store.add(tid, "assistant", f"відповідь {i}")
    real = a._router._client_for

    def client_for(pid):                                   # the summary request gets its own answer
        c = real(pid)
        orig = c.chat
        c.chat = lambda model, msgs, temperature=0.7: ("Міша вчить Flowgorithm." if msgs[0]["content"] == SUMMARY_PROMPT
                                                        else orig(model, msgs, temperature))
        return c
    a._router._client_for, a._router._clients = client_for, {}
    p = wait(a.send(tid, "питання 14")["stream"])            # 28 + 2 = 30 messages: the first 10 get summarized
    for _ in range(200):
        if a.store.summary(tid)[1]:
            break
        time.sleep(0.02)
    assert a.store.summary(tid) == ("Міша вчить Flowgorithm.", 10)
    assert p["sent"]                                        # (the first answer had no summary yet)

    wait(a.send(tid, "питання 15")["stream"])
    body = bodies[-1]
    assert "Міша вчить Flowgorithm." in body["messages"][0]["content"]
    texts = [m["content"] for m in body["messages"][1:]]
    assert "питання 4" not in texts and "питання 5" in texts   # messages 0-9 are in the summary, not sent again
    shown = a.messages(tid)
    assert shown[10].get("after_summary") and not any(m.get("after_summary") for m in shown[:10] + shown[11:])


def test_what_went_to_the_model_counts_only_earlier_messages(tmp_path, monkeypatch):
    a, _, wait = _api(tmp_path, monkeypatch, titles=False)
    tid = a.new_thread()["id"]
    first = wait(a.send(tid, "привіт")["stream"])["sent"]
    second = wait(a.send(tid, "як справи?")["stream"])["sent"]
    assert not any("earlier" in str(x) or "поперед" in str(x) for x in first)
    assert any("2" in str(x) for x in second)
