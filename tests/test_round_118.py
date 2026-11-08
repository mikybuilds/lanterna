"""Round 118: ready-made MCP servers with pinned versions, and a warning for hand-added ones without a version."""
import sys
from pathlib import Path

import pytest

from lanterna import gui, keys, mcp

FAKE = str(Path(__file__).with_name("fake_mcp_server.py"))
UI = Path(gui.__file__).parent / "ui"


@pytest.fixture
def api(monkeypatch, tmp_path):
    box = {}
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "stored_key", lambda n: box.get(n, ""))
    monkeypatch.setattr(keys, "set_key", lambda n, v: box.__setitem__(n, v))
    monkeypatch.setattr(keys, "delete_key", lambda n: box.pop(n, None))
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    from lanterna.app import Api
    from lanterna.store import Store
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    yield a
    a.mcp.stop_all()


def _fake(monkeypatch, version="1.0.0", folder=False):
    p = {"id": "fake", "name": "Fake", "icon": "🧪", "needs": "node", "node": 0, "folder": folder, "about": "test",
         "command": [sys.executable, FAKE, f"--pkg=@x/fake@{version}", *(["{folder}"] if folder else [])]}
    monkeypatch.setitem(mcp._PRESET, "fake", p)
    monkeypatch.setattr(mcp, "PRESETS", (*[x for x in mcp.PRESETS if x["id"] != "fake"], p))
    monkeypatch.setattr(mcp, "runtime", lambda preset, *a: "")
    return p


def test_every_preset_is_pinned_and_known_safe():
    assert 3 <= len(mcp.PRESETS) <= 5
    for p in mcp.PRESETS:
        cmd = mcp.preset_command(p["id"], "C:/x")
        assert not mcp.unpinned(cmd), p["id"]
        assert mcp.pinned_version(p["id"]), p["id"]
        assert p["needs"] in mcp.RUNTIMES and p["about"] and p["name"]
        assert ("C:/x" in cmd) == bool(p.get("folder"))
    git = mcp.preset_command("git", "C:/repo")
    assert git[git.index("--repository") + 1] == "C:/repo"            # the git server is confined to that repository
    assert "--isolated" in mcp.preset_command("browser")              # no saved profile, none of your sign-ins


def test_unpinned_commands_are_spotted():
    assert mcp.unpinned(["npx", "-y", "@modelcontextprotocol/server-memory"])
    assert mcp.unpinned(["npx.cmd", "-y", "@a/b@latest"])
    assert mcp.unpinned(["uvx", "mcp-server-time"])
    assert not mcp.unpinned(["npx", "-y", "@modelcontextprotocol/server-memory@2.1.0"])
    assert not mcp.unpinned(["uvx", "mcp-server-time@2026.11.4"])
    assert not mcp.unpinned(["uvx", "--from", "x==1.0", "x"])
    assert not mcp.unpinned([sys.executable, "server.py"])              # a program, not a package runner


def test_runtime_missing(monkeypatch):
    monkeypatch.setattr(mcp.shutil, "which", lambda n: None)
    assert mcp.runtime(mcp._PRESET["thinking"]) == "node" and mcp.runtime(mcp._PRESET["git"]) == "uv"
    monkeypatch.setattr(mcp.shutil, "which", lambda n: "C:/node/" + n)
    assert mcp.runtime(mcp._PRESET["thinking"], lambda: 20) == "node-old"
    assert mcp.runtime(mcp._PRESET["browser"], lambda: 20) == ""


def test_add_preset_and_update_its_version(api, monkeypatch):
    _fake(monkeypatch)
    assert api.mcp_add_preset("fake")["error"] == "MCP servers are off."
    api.mcp_enable(True)
    r = api.mcp_add_preset("fake")
    assert r["ok"]
    sid = r["id"]
    st = next(s for s in api.mcp_status()["servers"] if s["id"] == sid)
    assert st["preset"] == "fake" and st["version"] == "1.0.0" and not st["newer"] and not st["unpinned"]
    assert next(p for p in api.mcp_presets()["presets"] if p["id"] == "fake")["added"]
    _fake(monkeypatch, "1.1.0")                                        # a newer Lanterna pins a newer version
    st = next(s for s in api.mcp_status()["servers"] if s["id"] == sid)
    assert st["newer"] == "1.1.0"
    api.mcp_update_preset(sid)
    st = next(s for s in api.mcp_status()["servers"] if s["id"] == sid)
    assert st["version"] == "1.1.0" and not st["newer"] and "@x/fake@1.1.0" in st["where"]
    assert api.mcp_add_preset("nope")["error"] == "Unknown server."


def test_folder_presets_need_a_good_folder(api, monkeypatch, tmp_path, tmp_path_factory):
    _fake(monkeypatch, folder=True)
    for v in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):              # pytest's temp folder is inside AppData
        monkeypatch.delenv(v, raising=False)
    api.mcp_enable(True)
    assert api.mcp_add_preset("fake", "")["error"] == "Pick a folder first."
    assert api.mcp_add_preset("fake", str(tmp_path / "missing"))["error"] == "Pick a folder first."
    assert "smaller folder" in api.mcp_add_preset("fake", str(Path.home()))["error"]
    assert "smaller folder" in api.mcp_add_preset("fake", str(tmp_path))["error"]   # Lanterna's own data folder
    notes = tmp_path_factory.mktemp("notes")
    r = api.mcp_add_preset("fake", str(notes))
    assert r["ok"]
    st = next(s for s in r["servers"] if s["id"] == r["id"])
    assert str(notes.resolve()) in st["where"]


def test_hand_added_unpinned_server_gets_a_warning(api):
    api.mcp_enable(True)
    sid = api.mcp_add({"kind": "stdio", "where": "npx -y @modelcontextprotocol/server-memory", "name": "Memory"})["id"]
    assert next(s for s in api.mcp_status()["servers"] if s["id"] == sid)["unpinned"]


def test_window_and_terminal():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert {"mcp_presets", "mcp_add_preset", "mcp_update_preset"} <= gui.METHODS
    assert 'id="mcp-presets"' in js and "api.mcp_add_preset(p.id, folder)" in js and "s.unpinned" in js
    from lanterna import tui
    assert hasattr(tui.SettingsScreen, "_mcp_preset")


def test_terminal_settings_list_the_presets(api, monkeypatch):
    import asyncio

    from lanterna import tui
    from lanterna.tui import LanternaApp
    _fake(monkeypatch)
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True
    api.mcp_enable(True)

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(140, 60)) as pilot:
            await pilot.pause(0.3)
            app.push_screen(tui.SettingsScreen())
            await pilot.pause(0.5)
            scr = app.screen
            ids = {b.id for b in scr.query("#mcppresets Button")}
            assert "mcppre-fake" in ids
            scr._mcp_preset("fake")                                   # asks first, with the exact command
            await pilot.pause(0.3)
            assert "fake@1.0.0" in str(app.screen.query_one("Static").render())  # noqa: E501
    asyncio.run(go())
