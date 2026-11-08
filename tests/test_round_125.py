"""The terminal app made easier: a menu with every command (Ctrl+P), a short footer, sidebar buttons,
Settings in tabs, and Connectors (Yours / Browse) with mail, like the window."""
import asyncio

import pytest

pytest.importorskip("textual")
from textual.command import CommandPalette  # noqa: E402
from textual.widgets import Input, OptionList, Select, TabbedContent  # noqa: E402

from lanterna import connectors, tui  # noqa: E402
from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)


@pytest.fixture
def ready(api, monkeypatch):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "en", "provider": "groq"})
    monkeypatch.setattr(connectors, "search_registry", lambda q, cursor="": {"items": [], "next": "", "ok": True})   # no network
    return api


def run(api, body, size=(120, 44)):
    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=size) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            await body(app, pilot)
    asyncio.run(go())


def test_footer_shows_few_keys_and_every_command_has_one_place():
    labels = [c[0] for c in tui.CHAT_COMMANDS]
    assert len(labels) == len(set(labels))
    keys = [c[2] for c in tui.CHAT_COMMANDS if c[2]]
    assert len(keys) == len(set(keys)), "two commands on one key"
    assert "Ctrl+H" not in keys and "F9" in keys          # Ctrl+H is Backspace in many Linux terminals
    scr = tui.make_chat_screen("en")
    shown = [b for b in scr.BINDINGS if b.show]
    assert {b.action for b in shown} == tui.FOOTER_KEYS and len(shown) == 5
    assert all(b.key_display for b in shown)
    hidden = {b.key: b.action for b in scr.BINDINGS if not b.show}
    assert hidden["ctrl+h"] == "history" and hidden["f1"] == "app.command_palette" and hidden["f9"] == "history"


def test_menu_lists_every_command_in_order_and_runs_one(ready):
    async def body(app, pilot):
        names = [c.title for c in app.get_system_commands(app.screen)]
        assert names[0] == "New chat" and names[-1] == "Quit"
        assert "Connectors" in names and "Connect mail" in names and "What Lanterna did" in names
        assert "Settings → Voice" in names and "All commands" not in names
        assert names.index("Delete chat") > names.index("Save chat")      # not first, as an A–Z sort would put it
        await pilot.press("ctrl+p")
        assert await wait_for(pilot, lambda: CommandPalette.is_open(app))
        await pilot.press("escape")
        assert await wait_for(pilot, lambda: not CommandPalette.is_open(app))
        await pilot.press("f1")                                 # the second key for the menu
        assert await wait_for(pilot, lambda: CommandPalette.is_open(app))
        await pilot.press(*"connectors")
        await pilot.pause(0.5)
        await pilot.press("enter")
        assert await wait_for(pilot, lambda: isinstance(app.screen, tui.ConnectorsScreen))
    run(ready, body)


def test_menu_is_in_the_users_language(ready):
    ready.save_settings({"lang": "uk"})

    async def body(app, pilot):
        names = [c.title for c in app.get_system_commands(app.screen)]
        assert names[0] == "Нова розмова" and "Конектори" in names
        assert not [n for n in names if n.isascii()]
    run(ready, body)


def test_menu_does_not_open_over_a_dialog(ready):
    async def body(app, pilot):
        app.screen.action_about()
        await pilot.pause(0.3)
        about = app.screen
        app.action_command_palette()
        await pilot.pause(0.3)
        assert app.screen is about and not CommandPalette.is_open(app)
        assert list(app.get_system_commands(about)) == []
    run(ready, body)


def test_settings_in_tabs_open_on_a_tab_and_remember_it(ready):
    async def body(app, pilot):
        app.screen.action_settings("voice")
        assert await wait_for(pilot, lambda: isinstance(app.screen, tui.SettingsScreen) and app.screen.query("#settabs"))
        await pilot.pause(0.3)
        tabs = app.screen.query_one("#settabs", TabbedContent)
        assert tabs.active == "st-voice"
        assert len(tabs.query("TabPane")) == len(tui.SET_TABS)
        tabs.active = "st-pc"
        await pilot.pause(0.3)
        assert app.screen.query("#openconn")
        await pilot.press("escape")
        assert await wait_for(pilot, lambda: chat_ready(app))
        await pilot.press("ctrl+s")                             # opens where it was left
        assert await wait_for(pilot, lambda: isinstance(app.screen, tui.SettingsScreen) and app.screen.query("#settabs"))
        await pilot.pause(0.3)
        assert app.screen.query_one("#settabs", TabbedContent).active == "st-pc"
    run(ready, body, size=(120, 50))


def test_sidebar_buttons_open_the_main_places(ready):
    async def body(app, pilot):
        for btn, want in (("#sb-set", tui.SettingsScreen), ("#sb-conn", tui.ConnectorsScreen)):
            await pilot.click(btn)
            assert await wait_for(pilot, lambda: isinstance(app.screen, want)), btn
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: chat_ready(app))
        await pilot.click("#sb-menu")
        assert await wait_for(pilot, lambda: CommandPalette.is_open(app))
    run(ready, body)


def test_connectors_browse_lists_filters_and_describes(ready):
    async def body(app, pilot):
        app.screen.action_connectors("browse")
        assert await wait_for(pilot, lambda: isinstance(app.screen, tui.ConnectorsScreen) and app.screen.query("#cn-list"))
        await pilot.pause(0.3)
        scr = app.screen
        ol = scr.query_one("#cn-list", OptionList)
        total = len(ready.connectors()["catalog"])
        assert ol.option_count == total > 20                    # nothing picked in the category list: all of them
        assert ol.highlighted == 0 and str(scr.query_one("#cn-about").render()).strip()
        scr.query_one("#cn-q", Input).value = "notion"
        await pilot.pause(0.3)
        assert 1 <= ol.option_count < total and "Notion" in str(ol.get_option_at_index(0).prompt)
        scr.query_one("#cn-q", Input).value = ""
        cat = next(iter(ready.connectors()["categories"]))
        scr.query_one("#cn-cat", Select).value = cat
        await pilot.pause(0.3)
        want = sum(1 for c in ready.connectors()["catalog"] if c["cat"] == cat)
        assert ol.option_count == want < total
        scr.query_one("#cn-q", Input).value = "zzqqxx"
        await pilot.pause(0.3)
        assert ol.option_count == 1 and ol.get_option_at_index(0).disabled
        scr.query_one("#cntabs", TabbedContent).active = "cn-yours"
        await pilot.pause(0.3)
        assert scr.query_one("#cn-mine", OptionList).option_count >= 3        # mail, Google Drive, GitHub
    run(ready, body)


def test_mail_dialog_enter_moves_on_and_errors_are_plain(ready, monkeypatch):
    seen = []
    monkeypatch.setattr(ready, "mail_connect", lambda form: seen.append(form) or {"ok": False, "error": "auth"})

    async def body(app, pilot):
        app.push_screen(tui.MailScreen())
        assert await wait_for(pilot, lambda: isinstance(app.screen, tui.MailScreen) and app.screen.query("#mladdr"))
        await pilot.pause(0.2)
        scr = app.screen
        assert not scr.query_one("#mlservers").display        # Gmail needs no server names
        await pilot.press(*"bo@example.com")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert seen == [] and app.focused is scr.query_one("#mlpw")
        await pilot.press(*"abcd")
        await pilot.press("enter")
        assert await wait_for(pilot, lambda: bool(seen) and "app password" in str(scr.query_one("#mlerr").render()))
        assert seen[0]["address"] == "bo@example.com" and seen[0]["preset"] == "gmail"
        scr.query_one("#mlpreset", Select).value = "other"
        await pilot.pause(0.2)
        assert scr.query_one("#mlservers").display
    run(ready, body, size=(120, 50))


# ---------------------------------------------------------------- "make a text file on my desktop"
from lanterna import gdrive, pcfiles  # noqa: E402
from lanterna.app import action_title  # noqa: E402
from lanterna.chat import PC_GUIDE  # noqa: E402
from lanterna.workspace import WorkError  # noqa: E402
from test_pc import _places, home  # noqa: E402,F401


def test_a_text_file_on_the_desktop_not_in_google_drive(home, tmp_path):  # noqa: F811
    trashed = []
    pl, acts, cards = _places(home, lang="uk", trashed=trashed)
    tool = next(t for t in pcfiles.place_tools(pl) if t.name == "pc_write")
    cmd = "mkdir -p ~/.local/share/fonts && cd /tmp && curl -L https://example.com/f.zip -o f.zip"
    out = tool.run(place="desktop", path="Font_Install_Command", text=cmd)
    assert "Nothing has been changed yet" in out and str(home["desktop"]) in out
    assert not list(home["desktop"].iterdir())                  # nothing written before Confirm
    c = cards[0]
    assert c["kind"] == "pc_write" and c["details"]["path"] == "Font_Install_Command.txt" and c["details"]["preview"] == cmd
    assert action_title("pc_write", c["details"], "", "uk") == "Створити Font_Install_Command.txt у папці Робочий стіл"
    a = acts.confirm(c["id"])
    assert a.state == "done", a.result
    f = home["desktop"] / "Font_Install_Command.txt"
    assert f.read_text(encoding="utf-8") == cmd
    with pytest.raises(WorkError, match="already exists"):     # never overwrites
        pl.propose_write("desktop", "Font_Install_Command.txt", "other")
    for bad in ("run.sh.exe", "../x.txt", ".hidden.txt", ""):
        with pytest.raises(WorkError):
            pl.propose_write("desktop", bad, "x")
    assert f.read_text(encoding="utf-8") == cmd


def test_the_model_is_told_where_files_go():
    assert "pc_write" in PC_GUIDE and "never Google Drive" in PC_GUIDE
    src = open(gdrive.__file__, encoding="utf-8").read()
    assert "not on this computer" in src and "pc_write" in src
