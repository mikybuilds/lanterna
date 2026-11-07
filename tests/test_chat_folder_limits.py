"""Folder per chat (chip under the message box) and the limit bar."""
import datetime as dt
import json
import time

import httpx

from lanterna import keys, limits


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.ai_titles = a.settings.follow_ups = False   # these tests count the requests to the model one by one
    return a


def _sse_tool(name, args):
    tc = {"index": 0, "id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [tc]}}]})}\n\ndata: [DONE]\n\n".encode()


def _sse(text):
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


def _wait(a, sid):
    for _ in range(300):
        p = a.poll(sid)
        if p["done"]:
            return p
        time.sleep(0.02)
    raise AssertionError("no answer")


def test_each_chat_has_its_own_folder(tmp_path, monkeypatch):
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router
    a = _api(tmp_path, monkeypatch)
    home, mods = tmp_path / "proj", tmp_path / "mods"
    home.mkdir(), mods.mkdir()
    assert a.set_workdir(str(home))["ok"]
    t1, t2, t3 = (a.new_thread()["id"] for _ in range(3))
    assert a.chat_folder(t1)["name"] == "proj" and not a.chat_folder(t1)["own"]
    assert a.set_chat_folder(t2, str(mods))["name"] == "mods"
    assert a.set_chat_folder(t3, "")["path"] == "" and a.chat_folder(t3)["own"]
    assert a.set_chat_folder(t2, str(tmp_path.anchor))["error"] == "too_broad"
    assert a.chat_folder(t2)["name"] == "mods"                     # a refused folder changes nothing

    n = []

    def h(req):
        n.append(json.loads(req.content))
        if len(n) % 2 == 1:
            return httpx.Response(200, content=_sse_tool("folder_write", {"path": "a.txt", "text": "hi"}))
        return httpx.Response(200, content=_sse("Press Confirm."))
    a._router = Router([Candidate("groq", "m", 50)], client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))

    card = _wait(a, a.send(t2, "write a.txt")["stream"])["cards"][0]
    assert card["details"]["folder"] == str(mods.resolve())
    assert a.action_confirm(card["id"])["state"] == "done"        # confirmed from the UI thread: still the chat's folder
    assert (mods / "a.txt").exists() and not (home / "a.txt").exists()

    p = _wait(a, a.send(t3, "write a.txt")["stream"])            # a chat without a folder doesn't get folder tools
    assert not any(t["function"]["name"].startswith("folder_") for t in n[-1].get("tools", []) + n[-2].get("tools", []))
    assert p["cards"] == []

    card = _wait(a, a.send(t1, "write a.txt")["stream"])["cards"][0]
    a.set_chat_folder(t1, str(mods))                              # the folder changed after the card: refused
    r = a.action_confirm(card["id"])
    assert r["state"] == "failed" and not (home / "a.txt").exists()

    a.delete_thread(t2)
    assert str(t2) not in a.settings.chat_dirs


def test_gemini_day_follows_california_time():
    t = dt.datetime(2026, 11, 3, 7, 30, tzinfo=dt.timezone.utc).timestamp()     # 23:30 in California on the 2nd
    assert limits._day("gemini", t) == "2026-11-02"
    assert round(limits._next_day_in("gemini", t)) == 30 * 60
    summer = dt.datetime(2026, 7, 1, 7, 30, tzinfo=dt.timezone.utc).timestamp()  # PDT: 00:30 on the 1st
    assert limits._day("gemini", summer) == "2026-07-01"


def test_limit_bar_numbers(tmp_path):
    now = [dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc).timestamp()]
    L = limits.Limits(tmp_path / "l.json", clock=lambda: now[0])
    for _ in range(3):
        L.note("gemini", "gemini-3.5-flash", 200)
    c = L.current("gemini", "gemini-3.5-flash")
    assert (c["used"], c["limit"], c["left"], c["approx"]) == (3, 20, 17, True) and c["reset_in"] == 20 * 3600
    L.note("gemini", "gemini-3.5-flash", 429, message="Quota exceeded ... limit: 25, model: gemini-3.5-flash", retry_after=3600)
    c = L.current("gemini", "gemini-3.5-flash")
    assert (c["limit"], c["left"], c["approx"], c.get("resting")) == (25, 0, False, True) and c["reset_in"] == 3600
    assert L.current("gemini", "gemma-4-26b-a4b-it")["limit"] is None           # Gemma: not the Gemini daily 20
    now[0] += 1
    L.note("groq", "llama", 200, headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
                                          "x-ratelimit-reset-requests": "2m", "x-ratelimit-limit-tokens": "6000",
                                          "x-ratelimit-remaining-tokens": "10"})
    c = L.current("groq", "llama")
    assert (c["limit"], c["left"], c["period"], c["reset_in"]) == (1000, 990, "day", 120)
    assert L.last_used() == ("groq", "llama")
    now[0] += 21 * 3600                                                           # past midnight in California
    assert L.current("gemini", "gemini-3.5-flash")["used"] == 0


def test_limit_now_without_any_requests(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    assert a.limit_now() == {}
