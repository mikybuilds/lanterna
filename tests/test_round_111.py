"""Round 111: a second opinion — the last question to another model, shown under the first answer."""
import json
import time
from pathlib import Path

import httpx

from lanterna import gui, keys, tools
from lanterna.chat import SECOND_NOTE, join_answers
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


def sse(*chunks: str) -> bytes:
    return ("".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
            + "data: [DONE]\n\n").encode()


def _setup(tmp_path, monkeypatch, cands):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.follow_ups = api.settings.ai_titles = api.settings.auto_memory = False
    calls = []

    def handler(pid):
        def h(req):
            body = json.loads(req.content)
            calls.append((pid, body["model"], body))
            return httpx.Response(200, content=sse(f"answer from {body['model']}"))
        return h
    router = Router(cands, client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(handler(pid))))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    return api, calls


def _wait(api, sid):
    for _ in range(200):
        p = api.poll(sid)
        if p["done"]:
            return p
        time.sleep(0.03)
    raise AssertionError("never finished")


def test_second_opinion_goes_to_another_service(tmp_path, monkeypatch):
    cands = [Candidate("groq", "g1", 90), Candidate("groq", "g2", 85), Candidate("mistral", "m1", 80)]
    api, calls = _setup(tmp_path, monkeypatch, cands)
    tid = api.new_thread()["id"]
    assert _wait(api, api.send(tid, "Яка столиця Австралії?")["stream"])["final"] == "answer from g1"
    r = api.second_opinion(tid)
    p = _wait(api, r["stream"])
    assert p["final"] == "answer from m1" and p["second"] is True          # another service first, not groq/g2
    pid, model, body = calls[-1]
    assert pid == "mistral"
    # it sees the question, not the first answer, and may only look things up
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user"] and "answer from g1" not in json.dumps(body, ensure_ascii=False)
    names = {t["function"]["name"] for t in body.get("tools", [])}
    assert names and names <= set(tools.LOOKUP_TOOLS) and "remember" not in names and "set_reminder" not in names
    msgs = api.messages(tid)
    assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]
    assert msgs[2].get("second") and not msgs[1].get("second")
    assert any("second opinion" in x.lower() for x in msgs[2]["sent"])
    # the next question: both answers go as one turn
    _wait(api, api.send(tid, "А населення?")["stream"])
    nxt = calls[-1][2]["messages"]
    assert [m["role"] for m in nxt] == ["system", "user", "assistant", "user"]
    assert "answer from g1" in nxt[2]["content"] and "answer from m1" in nxt[2]["content"]


def test_retry_and_edit_take_both_answers_back(tmp_path, monkeypatch):
    api, _ = _setup(tmp_path, monkeypatch, [Candidate("groq", "g1", 90), Candidate("mistral", "m1", 80)])
    tid = api.new_thread()["id"]
    _wait(api, api.send(tid, "питання")["stream"])
    _wait(api, api.second_opinion(tid)["stream"])
    assert api.second_opinion(tid) == {"ok": False, "error": "no_other"}      # both models already answered
    assert api.edit_last(tid) == {"ok": True, "text": "питання"}
    assert api.messages(tid) == []


def test_nothing_to_compare(tmp_path, monkeypatch):
    api, _ = _setup(tmp_path, monkeypatch, [Candidate("groq", "g1", 90)])
    tid = api.new_thread()["id"]
    assert api.second_opinion(tid)["error"] == "empty"
    _wait(api, api.send(tid, "привіт")["stream"])
    assert api.second_opinion(tid)["error"] == "no_other"


def test_lookups_only_toolbox(tmp_path):
    box = tools.Toolbox(Store(tmp_path / "t.db"))
    safe = tools.LookupOnly(box)
    assert set(safe.tools) == set(tools.LOOKUP_TOOLS) & set(box.tools)
    assert safe.run("remember", '{"fact": "x"}').startswith("Error: there is no tool")
    assert box.store.facts() == []
    assert safe.run("calculate", '{"expression": "2+2"}') == "2+2 = 4"


def test_two_answers_in_a_row_are_joined():
    h = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}, {"role": "assistant", "content": "b"}]
    assert join_answers(h) == [{"role": "user", "content": "q"}, {"role": "assistant", "content": f"a\n\n{SECOND_NOTE}\nb"}]


def test_the_window_and_terminal_have_the_button():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "second_opinion" in gui.METHODS and "api.second_opinion(thread)" in js and 'id="i-users"' in (UI / "index.html").read_text(encoding="utf-8")
    from lanterna import tui
    assert hasattr(tui._ChatScreen, "action_second_opinion")
