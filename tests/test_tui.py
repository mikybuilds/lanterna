"""Drives the full-screen terminal app headless (Textual pilot) with a fake model and a fake key vault."""
import asyncio
import json

import httpx
import pytest

from lanterna import keys
from lanterna.app import Api
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router
from lanterna.store import Store

pytest.importorskip("textual")
from textual.widgets import Input, ListView, Markdown, Static  # noqa: E402

from lanterna.tui import LanternaApp  # noqa: E402


def sse(*chunks):
    return ("".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
            + "data: [DONE]\n\n").encode()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    vault = {}
    monkeypatch.setattr(keys, "get_key", lambda p: vault.get(p))
    monkeypatch.setattr(keys, "set_key", lambda p, k: vault.__setitem__(p, k))
    monkeypatch.setattr(keys, "delete_key", lambda p: vault.pop(p, None))
    monkeypatch.setattr(keys, "stored_key", lambda p: vault.get(p) or "")
    a = Api(store=Store(tmp_path / "t.db"))
    a.settings.sync_asked = True          # the Google step has its own test (test_sync.py)
    a._vault = vault

    def h(req):
        return httpx.Response(200, content=sse("Ciao ", "**Anna**", "!"))

    router = Router([Candidate("groq", "fake-model", 50)], client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))
    router.current = router.candidates[0]
    monkeypatch.setattr(a, "_get_router", lambda refresh=False: router)

    def fake_check(provider, key):
        if key == "good":
            vault[provider] = key
            return {"ok": True, "masked": "go…od"}
        return {"ok": False, "error": "auth", "message": "invalid key"}

    monkeypatch.setattr(a, "check_key", fake_check)
    monkeypatch.setattr(a, "check_update", lambda: {"current": "0.1.0", "latest": "0.2.0", "newer": True, "url": "https://x",
                                                    "notes": ["Update notice"], "steps": ["Close Lanterna.", "Open a terminal and run:"],
                                                    "command": "pipx upgrade lanterna", "download": ""})
    a.settings.update_check = False                    # the notice at start has its own test
    return a


def chat_ready(app) -> bool:
    """The chat screen is shown and fully built (slow CI machines need a moment after the switch)."""
    return type(app.screen).__name__ == "ChatScreen" and bool(app.screen.query("#composer"))


async def wait_for(pilot, cond, timeout=10.0):
    for _ in range(int(timeout / 0.05)):
        await pilot.pause(0.05)
        if cond():
            return True
    return False


def test_onboarding_then_chat(api):
    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert type(app.screen).__name__ == "OnboardScreen"
            await pilot.click("#lang-uk")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#name")))
            assert api.settings.lang == "uk"
            app.screen.query_one("#name", Input).value = "Anna"
            await pilot.click("#next")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#mode-cloud")))
            await pilot.click("#mode-cloud")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#pick-groq")))
            await pilot.click("#pick-groq")
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "KeyScreen")
            app.screen.query_one("#key", Input).value = "bad"
            await pilot.click("#check")
            assert await wait_for(pilot, lambda: "invalid" in str(app.screen.query_one("#keystatus").render()))
            app.screen.query_one("#key", Input).value = "good"
            await pilot.pause(0.3)          # a Button ignores a second click while its press effect runs
            await pilot.click("#check")
            assert await wait_for(pilot, lambda: chat_ready(app))
            assert api.settings.onboarded and api.settings.name == "Anna" and api.settings.provider == "groq"
            assert api._vault["groq"] == "good"

            # send a message, the reply streams into a Markdown block and is saved
            box = app.screen.query_one("#composer", Input)
            box.value = "привіт"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: app.screen._stream is None and app.screen._text)
            assert app.screen._text == "Ciao **Anna**!"
            tid = app.screen.tid
            assert [m["role"] for m in api.messages(tid)] == ["user", "assistant"]
            await app.workers.wait_for_complete()
            await pilot.pause(0.1)
            assert len(app.screen.query_one("#threads", ListView).children) == 1
            assert "fake-model" in str(app.screen.query_one("#model").render())
    asyncio.run(go())


def test_threads_reload_delete_and_language_switch(api):
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "en", "provider": "groq"})
    tid = api.new_thread()["id"]
    api.store.add(tid, "user", "hello")
    api.store.add(tid, "assistant", "Hi **Bo**")
    api.store.rename(tid, "hello")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app) and len(app.screen.query(Markdown)) == 1)
            scr = app.screen
            assert scr.tid == tid
            assert len(scr.query(Markdown)) == 1 and len(scr.query(".msg-user")) == 1
            # new chat clears the log, then delete the old one through the confirm dialog
            await pilot.press("ctrl+n")
            assert scr.tid is None and scr.query(".welcome")
            scr.open_thread(tid)
            await pilot.press("ctrl+d")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#yes")))
            await pilot.click("#yes")
            assert await wait_for(pilot, lambda: api.threads() == [])
            assert api.threads() == []
            # settings: switch language rebuilds the chat screen in Italian
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#lang-it")))
            await pilot.click("#lang-it")
            assert await wait_for(pilot, lambda: chat_ready(app) and app.screen is not scr)
            assert api.settings.lang == "it"
            assert app.screen.query_one("#composer", Input).placeholder == "Scrivi a Lanterna…"
    asyncio.run(go())


def test_error_is_shown_not_raised(api, monkeypatch):
    from lanterna.providers import ProviderError

    def boom(refresh=False):
        raise ProviderError("rate", "429")

    monkeypatch.setattr(api, "_get_router", boom)
    api.save_settings({"onboarded": True})

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            app.screen.query_one("#composer", Input).value = "hi"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: bool(app.screen.query(".msg-err")))
            err = app.screen.query_one(".msg-err", Static)
            assert "busy" in str(err.render())
            assert app.screen._stream is None
    asyncio.run(go())


def test_attach_file_and_reminder_alert(api, tmp_path, monkeypatch):
    monkeypatch.setattr("lanterna.app.notify", lambda title, msg: True)
    api.save_settings({"onboarded": True, "lang": "en"})
    note = tmp_path / "notes.txt"
    note.write_text("Budget: 4200 EUR", encoding="utf-8")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            box = app.screen.query_one("#composer", Input)
            box.value = f"/file {note}"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: "notes.txt" in str(app.screen.query_one("#attached").render()))
            box.value = "what is the budget?"
            await pilot.press("enter")
            assert await wait_for(pilot, lambda: app.screen._stream is None and app.screen._text)
            stored = api.store.messages(app.screen.tid)[0]["content"]
            assert "Budget: 4200 EUR" in stored                       # the model got the file text
            assert api.messages(app.screen.tid)[0]["content"].endswith("📎 notes.txt")   # the chat shows a short line
            assert str(app.screen.query_one("#attached").render()) == ""
            api.store.add_reminder("drink water", 1.0)
            api.check_reminders()
            app._alerts()
            assert await wait_for(pilot, lambda: any("drink water" in str(n.message) for n in app._notifications))
    asyncio.run(go())


def fake_local(api, monkeypatch):
    """Ollama running with one of three recommended models installed; downloads advance 50% per poll."""
    state = {"pulls": []}
    hw = {"hw": {"gpu": "NVIDIA GeForce RTX 5060", "vram_gb": 8.0, "vram_exact": True, "ram_gb": 16.0,
                 "disk_free_gb": 60.0, "os": "win32"},
          "advice": {"tier": "medium", "mode": "auto", "models": [
              {"name": "gemma4:e4b-it-qat", "role": "chat", "size_gb": 6.15, "min_vram": 6},
              {"name": "qwen3:8b", "role": "think", "size_gb": 5.23, "min_vram": 6},
              {"name": "qwen3-vl:8b-instruct", "role": "vision", "size_gb": 6.19, "min_vram": 6}]},
          "download_page": "https://ollama.com/download"}
    models = [{"name": "gemma4:e4b-it-qat", "size_gb": 6.15, "vision": True, "tools": True, "chat": True}]

    def pulls():
        for p in state["pulls"]:
            if p["status"] == "downloading":
                p["percent"] = min(100, p["percent"] + 50)
                if p["percent"] == 100:
                    p["status"] = "done"
                    models.append({"name": p["name"], "size_gb": 5, "vision": False, "tools": True, "chat": True})
        return [dict(p) for p in state["pulls"]]

    def pull_model(name):
        state["pulls"].append({"name": name, "status": "downloading", "percent": 0, "done_bytes": 0,
                               "total_bytes": 5e9, "error": ""})
        return {"ok": True}

    monkeypatch.setattr(api, "hardware", lambda: hw)
    monkeypatch.setattr(api, "local_status", lambda: {"running": True, "version": "0.40.13", "models": list(models),
                                                      "picks": api.settings.local_models,
                                                      "download_page": hw["download_page"], "pulls": pulls()})
    monkeypatch.setattr(api, "pulls", pulls)
    monkeypatch.setattr(api, "pull_model", pull_model)
    return state


def test_onboarding_auto_mode_with_local_download(api, monkeypatch, tmp_path):
    state = fake_local(api, monkeypatch)

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.click("#lang-uk")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#name")))
            await pilot.click("#next")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#mode-auto")))
            await pilot.click("#mode-auto")
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "LocalScreen")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#pull-1")))
            assert "RTX 5060" in str(app.screen.query_one("#hwinfo").render())
            from textual.widgets import Button
            assert "Встановлено" in str(app.screen.query_one("#pull-0", Button).label)
            assert "5.2" in str(app.screen.query_one("#pull-1", Button).label)
            app.save_screenshot("local_screen.svg", path=str(tmp_path))
            app.screen.query_one("#pull-1", Button).press()
            assert await wait_for(pilot, lambda: state["pulls"] and state["pulls"][0]["status"] == "done", 6)
            assert await wait_for(pilot, lambda: "Встановлено" in str(app.screen.query_one("#pull-1", Button).label), 4)
            app.screen.query_one("#close", Button).press()
            assert await wait_for(pilot, lambda: bool(app.screen.query("#pick-groq")))   # auto still needs a cloud key
            assert api.settings.mode == "auto"

    asyncio.run(go())


def test_settings_mode_switch_and_auto_cloud_toggle(api, monkeypatch):
    fake_local(api, monkeypatch)
    api.save_settings({"onboarded": True, "lang": "en"})

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 50)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#mode-auto")))
            app.screen.query_one("#mode-auto").press()
            assert await wait_for(pilot, lambda: bool(app.screen.query("#autocloud")))
            assert api.settings.mode == "auto"
            from textual.widgets import Checkbox
            app.screen.query_one("#autocloud", Checkbox).value = False
            assert await wait_for(pilot, lambda: api.settings.auto_cloud is False)
            app.screen.query_one("#localmodels").press()
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "LocalScreen")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#pick-chat")) and bool(app.screen.query("#pick-vision")))
            await pilot.pause(0.3)                         # let the selects finish composing before the app closes
            app.screen.query_one("#close").press()
            assert await wait_for(pilot, lambda: type(app.screen).__name__ != "LocalScreen")

    asyncio.run(go())


def test_update_notice_at_start_and_settings_switch(api):
    api.save_settings({"onboarded": True, "lang": "en", "update_check": True})

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 50)) as pilot:
            assert await wait_for(pilot, lambda: type(app.screen).__name__ == "UpdateScreen")
            text = str(app.screen.query_one("#updsteps", Static).render())
            assert "1. Close Lanterna." in text and "2. Open a terminal and run:" in text
            assert "pipx upgrade lanterna" in str(app.screen.query_one("#updcmd", Static).render())
            app.screen.query_one("#updlater").press()
            assert await wait_for(pilot, lambda: chat_ready(app))
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: bool(app.screen.query("#updcheck")))
            from textual.widgets import Checkbox
            app.screen.query_one("#updcheck", Checkbox).value = False
            assert await wait_for(pilot, lambda: api.settings.update_check is False)

    asyncio.run(go())
