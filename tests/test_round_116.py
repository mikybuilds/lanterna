"""Round 116: a private chat lives only in memory: not saved, not synced or backed up, no memory used, gone when left."""
import json
import sqlite3
import time
from pathlib import Path

import httpx

from lanterna import gui, keys, tools
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.follow_ups = api.settings.ai_titles = True
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=b'data: {"choices": [{"delta": {"content": "Gotcha"}}]}\n\ndata: [DONE]\n\n')
    router = Router([Candidate("groq", "g1", 90), Candidate("mistral", "m1", 80)],
                    client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(h)))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    return api, bodies


def _ask(api, tid, text):
    sid = api.send(tid, text)["stream"]
    for _ in range(200):
        p = api.poll(sid)
        if p["done"]:
            return p
        time.sleep(0.03)


def test_nothing_reaches_the_database(tmp_path, monkeypatch):
    api, bodies = _api(tmp_path, monkeypatch)
    api.store.add_fact("Has a cat named Murzik")
    tid = api.new_thread(private=True)["id"]
    assert tid < 0
    p = _ask(api, tid, "Мій діагноз — гастрит, що їсти?")
    assert p["final"] == "Gotcha" and not p["titling"] and not p["suggesting"] and not p.get("learning")
    assert any("Private chat" in x for x in p["sent"])
    system = bodies[0]["messages"][0]["content"]
    assert "Murzik" not in system and "private chat" in system
    names = {t["function"]["name"] for t in bodies[0].get("tools", [])}
    assert not names & set(tools.PRIVATE_HIDDEN)
    assert [m["role"] for m in api.messages(tid)] == ["user", "assistant"]
    _wait = api.second_opinion(tid)                                  # works in a private chat too
    for _ in range(200):
        if api.poll(_wait["stream"])["done"]:
            break
        time.sleep(0.03)
    assert len(api.messages(tid)) == 3
    # the database, the chat list, search, sync and backups never see it
    raw = (tmp_path / "t.db").read_bytes()
    assert "гастрит".encode() not in raw
    with sqlite3.connect(tmp_path / "t.db") as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert api.threads() == [] and api.search_chats("гастрит") == []
    assert api.store.export_sync()["messages"] == {}
    assert "Error" in api.toolbox.run("read_chat", json.dumps({"id": tid}))


def test_leaving_drops_it_for_good(tmp_path, monkeypatch):
    api, _ = _api(tmp_path, monkeypatch)
    a = api.new_thread(private=True)["id"]
    _ask(api, a, "секрет")
    api.set_chat_role(a, "tutor")
    b = api.new_thread(private=True)["id"]
    api.forget_private(keep=b)                                       # opened another private chat: the first goes
    assert api.store.thread(a) is None and api.store.thread(b) is not None
    assert str(a) not in api.settings.chat_roles
    api.forget_private()
    assert api.store.thread(b) is None and api.messages(b) == []


def test_retry_and_edit_work_in_memory(tmp_path, monkeypatch):
    api, _ = _api(tmp_path, monkeypatch)
    tid = api.new_thread(private=True)["id"]
    _ask(api, tid, "питання")
    assert api.edit_last(tid) == {"ok": True, "text": "питання"} and api.messages(tid) == []


def test_window_and_terminal():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "forget_private" in gui.METHODS and 'id="new-private"' in js and "api.new_thread(privateNext)" in js
    assert 'id="i-incog"' in (UI / "index.html").read_text(encoding="utf-8")
    from lanterna import tui
    assert hasattr(tui._ChatScreen, "action_private_chat")


def test_terminal_f7(tmp_path, monkeypatch):
    import asyncio

    from lanterna.tui import LanternaApp
    api, _ = _api(tmp_path, monkeypatch)
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True
    keep = api.new_thread()["id"]
    api.store.add(keep, "user", "звичайний чат")

    async def wait(pilot, cond):
        for _ in range(150):
            await pilot.pause(0.05)
            if cond():
                return
        raise AssertionError("timeout")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("f7")
            scr = app.screen
            scr.query_one("#composer").value = "таємниця"
            await pilot.press("enter")
            await wait(pilot, lambda: scr.tid is not None and scr.tid < 0 and len(api.messages(scr.tid)) == 2)
            await wait(pilot, lambda: scr._stream is None)
            priv = scr.tid
            assert [t["id"] for t in api.threads()] == [keep]
            scr.open_thread(keep)                                    # leaving it: gone
            assert api.store.thread(priv) is None
    asyncio.run(go())
