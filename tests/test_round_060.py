"""0.6.0 stage 3: edit the last message, answer again, export, memory that updates itself. No real network."""
import json
import time

import httpx

from lanterna import keys
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router


def _sse(text):
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


def _api(tmp_path, monkeypatch, answer=lambda body, n: f"Відповідь {n}"):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.ai_titles = a.settings.follow_ups = a.settings.compact_chats = False
    bodies = []

    def h(req):
        body = json.loads(req.content)
        bodies.append(body)
        return httpx.Response(200, content=_sse(answer(body, len(bodies))))
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


def _roles(a, tid):
    return [(m["role"], m["content"]) for m in a.store.messages(tid)]


# ---------------------------------------------------------------- edit / answer again
def test_trim_tail_leaves_a_note_for_other_devices(tmp_path):
    from lanterna.store import Store
    s = Store(tmp_path / "s.db")
    tid = s.new_thread()
    for i in range(3):
        s.add(tid, "user", f"q{i}")
    s.trim_tail(tid, 2)
    assert [m["content"] for m in s.messages(tid)] == ["q0"]
    assert s._q("SELECT COUNT(*) AS n FROM deleted")[0]["n"] == 2


def test_answer_again_replaces_the_last_answer(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    wait(a.send(tid, "привіт")["stream"])
    wait(a.send(tid, "як справи?")["stream"])
    p = wait(a.send(tid, "", [], again=True)["stream"])
    assert p["final"] == "Відповідь 3"
    assert _roles(a, tid) == [("user", "привіт"), ("assistant", "Відповідь 1"),
                              ("user", "як справи?"), ("assistant", "Відповідь 3")]
    assert bodies[-1]["messages"][-1]["content"] == "як справи?"          # the same question went again, once
    assert [m["content"] for m in bodies[-1]["messages"][1:]].count("як справи?") == 1


def test_retry_after_an_error_does_not_repeat_the_question(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    a.store.add(tid, "user", "питання без відповіді")              # what an error leaves behind
    wait(a.send(tid, "питання без відповіді", [], again=True)["stream"])
    assert _roles(a, tid) == [("user", "питання без відповіді"), ("assistant", "Відповідь 1")]


def test_edit_last_gives_the_question_back(tmp_path, monkeypatch):
    a, _, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    wait(a.send(tid, "привіт")["stream"])
    wait(a.send(tid, "скільки буде 2+2?")["stream"])
    assert a.edit_last(tid) == {"ok": True, "text": "скільки буде 2+2?"}
    assert _roles(a, tid) == [("user", "привіт"), ("assistant", "Відповідь 1")]
    assert a.edit_last(a.new_thread()["id"]) == {"ok": True, "text": ""}   # an empty chat: nothing to take back
