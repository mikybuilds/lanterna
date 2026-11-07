"""Round 113: the user's own instructions for every chat, and a role (Tutor, Translator, Proofreader) for one chat."""
import json
import time
from pathlib import Path

import httpx

from lanterna import gui, keys, roles
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
    api.settings.follow_ups = api.settings.ai_titles = api.settings.auto_memory = False
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, content=b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n')
    router = Router([Candidate("groq", "g1", 90)], client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(h)))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    return api, bodies


def _ask(api, tid, text):
    sid = api.send(tid, text)["stream"]
    for _ in range(200):
        if api.poll(sid)["done"]:
            return
        time.sleep(0.03)


def test_instructions_and_role_reach_the_model(tmp_path, monkeypatch):
    api, bodies = _api(tmp_path, monkeypatch)
    api.save_settings({"instructions": "  Відповідай коротко.\r\nЯ студент.  " + "x" * 3000})
    assert api.settings.instructions.startswith("Відповідай коротко.\nЯ студент.") and len(api.settings.instructions) == 1500
    a, b = api.new_thread()["id"], api.new_thread()["id"]
    assert api.set_chat_role(a, "translator") == {"ok": True, "role": "translator"}
    assert api.chat_role(a) == {"role": "translator"} and api.chat_role(b) == {"role": ""}
    _ask(api, a, "Добрий день")
    system = bodies[-1]["messages"][0]["content"]
    assert "translator" in system and "from Українська into English" not in system   # the app is in English here
    assert "Відповідай коротко." in system
    _ask(api, b, "Привіт")
    system_b = bodies[-1]["messages"][0]["content"]
    assert "translator" not in system_b and "Відповідай коротко." in system_b


def test_unknown_roles_and_missing_chats(tmp_path, monkeypatch):
    api, _ = _api(tmp_path, monkeypatch)
    tid = api.new_thread()["id"]
    assert api.set_chat_role(tid, "hacker") == {"ok": True, "role": ""}
    assert api.set_chat_role(999, "tutor")["ok"] is False
    api.set_chat_role(tid, "tutor")
    api.delete_thread(tid)
    assert str(tid) not in api.settings.chat_roles


def test_the_translator_uses_the_app_language():
    note = roles.system_note("", "translator", "uk")
    assert "from Українська into English" in note
    assert roles.system_note("", "", "uk") == "" and "tutor" in roles.system_note("", "tutor")


def test_window_and_terminal_have_the_controls():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert {"chat_role", "set_chat_role"} <= gui.METHODS
    assert 'id="role-btn"' in js and "function roleMenu()" in js and 'id="instructions"' in js
    for r in roles.ROLES:
        assert f'["{r}", "{roles.ROLES[r][0]}"' in js
    from lanterna import tui
    assert hasattr(tui._ChatScreen, "action_next_role")


def test_terminal_f6_and_f4(tmp_path, monkeypatch):
    import asyncio

    from lanterna.discovery import Candidate as C
    from lanterna.tui import LanternaApp
    api, bodies = _api(tmp_path, monkeypatch)
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True

    def h(req):
        model = json.loads(req.content)["model"]
        bodies.append(model)
        return httpx.Response(200, content=('data: {"choices": [{"delta": {"content": "from %s"}}]}\n\ndata: [DONE]\n\n' % model).encode())
    router = Router([C("groq", "g1", 90), C("mistral", "m1", 80)],
                    client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(h)))
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)

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
            await pilot.press("f6")                      # a new chat: the role waits for the first message
            await pilot.press("f6")
            box = app.screen.query_one("#composer")
            box.value = "Hello"
            await pilot.press("enter")
            await wait(pilot, lambda: len(api.store.threads()) == 1 and api.store.messages(api.store.threads()[0]["id"])[-1:] and api.store.messages(api.store.threads()[0]["id"])[-1]["role"] == "assistant")
            tid = api.store.threads()[0]["id"]
            assert api.chat_role(tid)["role"] == "translator"
            await wait(pilot, lambda: app.screen._stream is None)
            await pilot.press("f4")                      # second opinion from the other model
            await wait(pilot, lambda: len(api.store.messages(tid)) == 3)
            assert api.store.messages(tid)[-1]["content"] == "from m1"
            await wait(pilot, lambda: app.screen._stream is None)
            await pilot.press("f6")
            assert api.chat_role(tid)["role"] == "proofreader"
    asyncio.run(go())
