"""Bug reports: exact text the user sees, nothing private added, links that open safely."""
import asyncio
import time
from pathlib import Path
from urllib.parse import unquote

import pytest

from lanterna import HOMEPAGE, __version__, bugreport
from lanterna.app import Api
from lanterna.store import Store


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("LANTERNA_BUG_EMAIL", raising=False)
    bugreport._errors.clear()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.name = "Anna"
    return a


def test_report_without_mailbox_offers_github_only(api):
    r = api.bug_report("The chat list is empty\nafter I rename a chat", True)
    assert r["ok"] and r["email"] == "" and r["mailto"] == ""
    assert r["subject"] == f"Lanterna {__version__} bug: The chat list is empty"
    assert r["body"].startswith("The chat list is empty\nafter I rename a chat\n\n---\nLanterna ")
    assert "Python " in r["body"] and "mode: cloud" in r["body"]
    assert "Anna" not in r["body"]                                   # never the user's name
    assert r["issue"].startswith(HOMEPAGE + "/issues/new?title=")
    assert "chat list is empty" in unquote(r["issue"])


def test_info_can_be_left_out_and_empty_text_is_refused(api):
    assert api.bug_report("  just this  ", False)["body"] == "just this"
    assert api.bug_report("   ", True)["ok"] is False


def test_letter_to_the_project_mailbox(api, monkeypatch):
    monkeypatch.setenv("LANTERNA_BUG_EMAIL", "bugs@example.com")
    r = api.bug_report("Crash when I attach a PDF", True)
    assert r["email"] == "bugs@example.com" and not r["cut"]
    assert r["mailto"].startswith("mailto:bugs@example.com?subject=")
    assert "Crash when I attach a PDF" in unquote(r["mailto"])
    assert bugreport.valid_mailto(r["mailto"])
    # only the project's own address can be opened
    assert not bugreport.valid_mailto("mailto:someone@example.org?subject=x")
    assert not bugreport.valid_mailto(r["mailto"] + "\n")


def test_long_text_shortens_the_letter_but_keeps_the_system_info(api, monkeypatch):
    monkeypatch.setenv("LANTERNA_BUG_EMAIL", "bugs@example.com")
    r = api.bug_report("Привіт, щось зламалося. " * 150, True)       # Cyrillic: every letter is 6 characters in a link
    assert r["cut"] and len(r["mailto"]) <= bugreport.MAIL_LIMIT
    body = unquote(r["mailto"].split("&body=", 1)[1])
    assert "shortened" in body and f"Lanterna {__version__}" in body
    assert len(r["body"]) > 3000                                      # the full text stays for copying
    assert bugreport.valid_mailto(r["mailto"])


def test_errors_are_added_without_paths_keys_or_mails(api):
    home = str(Path.home())
    bugreport.remember_error("auth", f"bad key {'gsk'}_abcdef1234567890ABCDEF12 for me@example.org in {home}\\x.txt")
    body = api.bug_report("reply failed", True)["body"]
    assert "Last errors:" in body and "auth: bad key [hidden] for [e-mail] in ~" in body
    assert "gsk_abcdef" not in body and home not in body


def test_failed_reply_is_remembered(api, monkeypatch):
    from lanterna.providers import ProviderError

    def boom(refresh=False):
        raise ProviderError("rate", "limit reached")
    monkeypatch.setattr(api, "_get_router", boom)
    tid = api.new_thread()["id"]
    sid = api.send(tid, "hi")["stream"]
    for _ in range(250):
        if api.poll(sid)["done"]:
            break
        time.sleep(0.02)
    assert any("rate: limit reached" in e for e in bugreport.recent_errors())


def test_open_links(api, monkeypatch):
    opened = []
    monkeypatch.setattr("lanterna.quiet.open_url", opened.append)
    issue = api.bug_report("x" * 3000, True)["issue"]
    assert len(issue) > 2000 and api.open_url(issue)                 # a long issue link is allowed
    assert not api.open_url("https://example.com/?" + "a" * 3000)     # other long links are not
    assert not api.open_mail("mailto:bugs@example.com?subject=x")     # no mailbox set yet
    monkeypatch.setenv("LANTERNA_BUG_EMAIL", "bugs@example.com")
    assert api.open_mail(api.bug_report("x", True)["mailto"])
    assert opened[0] == issue and opened[1].startswith("mailto:bugs@example.com?")


def test_bug_screen_in_terminal_app(api, monkeypatch):
    pytest.importorskip("textual")
    from textual.widgets import Static, TextArea
    from lanterna.tui import BugScreen, LanternaApp

    opened = []
    monkeypatch.setattr(api, "open_url", lambda u: opened.append(u) or True)
    monkeypatch.setattr(api, "open_mail", lambda u: opened.append(u) or True)
    api.settings.onboarded, api.settings.update_check, api.settings.mode = True, False, "local"

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(110, 44)) as pilot:
            app.push_screen(BugScreen())
            for _ in range(100):
                await pilot.pause(0.05)
                if isinstance(app.screen, BugScreen) and app.screen.query("#bugpreview"):
                    break
            scr = app.screen
            assert not scr.query_one("#bugmail").display              # no mailbox yet: GitHub and copy only
            await pilot.click("#buggh")
            await pilot.pause(0.1)
            assert opened == [] and "Write a few words" in str(scr.query_one("#bugnote", Static).render())
            scr.query_one("#bugtext", TextArea).text = "Settings do not save"
            await pilot.pause(0.2)
            assert "Settings do not save" in str(scr.query_one("#bugpreview", Static).render())
            await pilot.click("#buggh")
            await pilot.pause(0.1)
            assert opened and opened[0].startswith(HOMEPAGE + "/issues/new?")
    asyncio.run(go())
