"""1.0: MCP servers. A fake server script and a fake web server; no real outside servers."""
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from lanterna import keys, mcp

FAKE = str(Path(__file__).with_name("fake_mcp_server.py"))


@pytest.fixture
def vault(monkeypatch, tmp_path):
    box = {}
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "stored_key", lambda n: box.get(n, ""))
    monkeypatch.setattr(keys, "set_key", lambda n, v: box.__setitem__(n, v))
    monkeypatch.setattr(keys, "delete_key", lambda n: box.pop(n, None))
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    return box


def _api(tmp_path):
    from lanterna.app import Api
    from lanterna.store import Store
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


def _ready(api, sid, want="ready"):
    for _ in range(300):
        st = next(s for s in api.mcp_status()["servers"] if s["id"] == sid)
        if st["state"] == want:
            return st
        time.sleep(0.03)
    raise AssertionError(st)


def _cmd():
    return f'"{sys.executable}" "{FAKE}"' if sys.platform == "win32" else f"{sys.executable} {FAKE}"


# ---------------------------------------------------------------- pieces
def test_command_lines_split_like_the_user_typed_them():
    if sys.platform == "win32":
        assert mcp.split_command(r'npx -y @x/server "My Files\notes"') == ["npx", "-y", "@x/server", r"My Files\notes"]
    else:
        assert mcp.split_command("npx -y @x/server 'My Files/notes'") == ["npx", "-y", "@x/server", "My Files/notes"]
    assert mcp.split_command("  ") == []


def test_import_reads_the_usual_json():
    got = mcp.parse_import(json.dumps({"mcpServers": {
        "files": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/notes"]},
        "gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "t-123"}},
        "web": {"url": "https://example.org/mcp", "headers": {"Authorization": "Bearer abc"}}}}))
    assert [g["kind"] for g in got] == ["stdio", "stdio", "http"]
    assert got[0]["command"][:2] == ["npx", "-y"] and got[1]["env"] == {"GITHUB_TOKEN": "t-123"}
    with pytest.raises(mcp.McpError):
        mcp.parse_import("{not json")
    with pytest.raises(mcp.McpError):
        mcp.parse_import("{}")


def test_results_become_text():
    r = mcp.result_text({"content": [{"type": "text", "text": "a"}, {"type": "image", "data": "..."}]})
    assert r == "a\n[image not shown]"
    assert mcp.result_text({"content": [], "isError": True}).startswith("Error from the tool")
    assert "more characters cut" in mcp.result_text({"content": [{"type": "text", "text": "x" * 9000}]})


# ---------------------------------------------------------------- off until the user turns it on
def test_off_by_default_and_nothing_is_offered(vault, tmp_path):
    api = _api(tmp_path)
    st = api.mcp_status()
    assert st["enabled"] is False and st["warned"] is False and st["servers"] == []
    assert api.mcp_add({"name": "x", "kind": "stdio", "where": _cmd()})["ok"] is False
    assert not [t for t in api.toolbox.tools if t.startswith("mcp_")]


def test_a_program_server_works_and_asks_first(vault, tmp_path):
    api = _api(tmp_path)
    assert api.mcp_enable(True)["warned"] is True
    r = api.mcp_add({"name": "Fake tools", "kind": "stdio", "where": _cmd(), "secret_name": "FAKE_TOKEN", "secret": "sekret-token-42"})
    assert r["ok"], r
    sid = r["id"]
    st = _ready(api, sid)
    assert [t["name"] for t in st["tools"]] == ["echo", "secret_len", "boom"]      # both pages of the list
    assert st["has_secret"] and "sekret" not in (mcp._file().read_text(encoding="utf-8"))
    assert json.loads(vault[f"mcp-{sid}"])["env"] == {"FAKE_TOKEN": "sekret-token-42"}

    names = [n for n in api.toolbox.tools if n.startswith("mcp_")]
    assert names == ["mcp_fake_tools_echo", "mcp_fake_tools_secret_len", "mcp_fake_tools_boom"]
    schema = api.toolbox.tools["mcp_fake_tools_echo"].schema()["function"]
    assert schema["parameters"]["required"] == ["text"] and "MCP server 'Fake tools'" in schema["description"]

    # nobody to confirm (no chat) → not run
    assert "needs the user's OK" in api.toolbox.run("mcp_fake_tools_echo", '{"text": "hi"}')

    # in a chat: a card, then Confirm → the result goes back to the model
    sink: list = []
    out = {}

    def ask():
        api.actions.bind(sink, 7)
        out["r"] = api.toolbox.run("mcp_fake_tools_echo", '{"text": "привіт"}')
    th = threading.Thread(target=ask)
    th.start()
    for _ in range(100):
        if sink:
            break
        time.sleep(0.02)
    card = sink[0]
    assert card["kind"] == "mcp_call" and card["details"]["name"] == "Fake tools: echo" and "привіт" in card["details"]["preview"]
    done = api.action_confirm(card["id"])
    th.join(10)
    assert done["state"] == "done" and done["text"] == "Used Fake tools: echo"
    assert "echo: привіт" in out["r"] and "outside data" in out["r"]
    assert not [m for m in api.store.messages(7)]              # no extra note: the answer tells what came back

    # Cancel → the model is told, nothing runs
    sink.clear()
    th = threading.Thread(target=ask)
    th.start()
    for _ in range(100):
        if sink:
            break
        time.sleep(0.02)
    api.action_cancel(sink[0]["id"])
    th.join(10)
    assert "cancelled" in out["r"]

    # allowed tools run without a card; the secret reached the program only through its environment
    api.mcp_update(sid, {"allow": ["secret_len", "boom"]})
    _ready(api, sid)
    sink.clear()
    api.actions.bind(sink, 7)
    assert api.toolbox.run("mcp_fake_tools_secret_len", "{}").endswith("\n15") and sink == []
    assert "Error from the tool: it broke" in api.toolbox.run("mcp_fake_tools_boom", "{}")
    api.actions.bind(None)

    # off → its tools go; removed → its secret goes too
    api.mcp_update(sid, {"on": False})
    assert not [n for n in api.toolbox.tools if n.startswith("mcp_")]
    api.mcp_remove(sid)
    assert api.mcp_status()["servers"] == [] and f"mcp-{sid}" not in vault
    api.mcp.stop_all()


def test_a_broken_server_shows_why_without_the_token(vault, tmp_path):
    api = _api(tmp_path)
    api.mcp_enable(True)
    sid = api.mcp_add({"name": "bad", "kind": "stdio", "where": f'"{sys.executable}" -c "import sys; '
                       f'sys.stderr.write(\'token sekret-token-42 rejected\\n\'); sys.exit(3)"',
                       "secret_name": "FAKE_TOKEN", "secret": "sekret-token-42"})["id"]
    st = _ready(api, sid, "error")
    assert st["error"] and "sekret-token-42" not in st["error"]
    assert not [n for n in api.toolbox.tools if n.startswith("mcp_")]
    assert api.mcp_add({"name": "x", "kind": "stdio", "where": "  "})["ok"] is False
    assert api.mcp_add({"name": "x", "kind": "stdio", "where": "x", "secret": "s", "secret_name": "bad name"})["ok"] is False
    api.mcp.stop_all()


# ---------------------------------------------------------------- web address servers
def test_a_web_server_with_a_token(vault, tmp_path, monkeypatch):
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((req.headers.get("authorization"), req.headers.get("mcp-session-id"), body.get("method")))
        if "id" not in body:
            return httpx.Response(202)
        m = body["method"]
        res = ({"protocolVersion": mcp.PROTOCOL, "capabilities": {}} if m == "initialize" else
               {"tools": [{"name": "time", "description": "Now.", "inputSchema": {"type": "object"}}]} if m == "tools/list" else
               {"content": [{"type": "text", "text": "12:00"}]})
        msg = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": res})
        if m == "tools/call":                                 # streamable HTTP may answer as an event stream
            return httpx.Response(200, text=f"event: message\ndata: {msg}\n\n", headers={"content-type": "text/event-stream"})
        return httpx.Response(200, text=msg, headers={"content-type": "application/json", "mcp-session-id": "s-1"})

    api = _api(tmp_path)
    api.mcp._http = httpx.Client(transport=httpx.MockTransport(handler))
    api.mcp_enable(True)
    assert api.mcp_add({"name": "clock", "kind": "http", "where": "http://example.org/mcp"})["ok"] is False   # https only
    sid = api.mcp_add({"name": "clock", "kind": "http", "where": "https://example.org/mcp", "secret": "abc123"})["id"]
    _ready(api, sid)
    api.mcp_update(sid, {"allow": ["time"]})
    _ready(api, sid)
    assert api.toolbox.run("mcp_clock_time", "{}").endswith("12:00")
    assert seen[0] == ("Bearer abc123", None, "initialize")
    assert seen[-1][1] == "s-1" and seen[-1][2] == "tools/call"


def test_terminal_turns_it_on_after_the_warning_and_adds_a_server(vault, tmp_path):
    import asyncio

    from textual.widgets import Button, Input

    from lanterna.tui import ConfirmScreen, LanternaApp, SettingsScreen
    api = _api(tmp_path)
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True

    async def wait(pilot, cond):
        for _ in range(150):
            await pilot.pause(0.05)
            if cond():
                return
        raise AssertionError("timeout")

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(110, 60)) as pilot:
            await pilot.pause(0.3)
            app.screen.action_settings()
            await wait(pilot, lambda: isinstance(app.screen, SettingsScreen) and app.screen.query("#mcptoggle"))
            await pilot.pause(0.5)
            scr = app.screen
            assert not scr.query_one("#mcpaddrow").display
            scr.query_one("#mcptoggle", Button).press()
            await wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            assert "other people" in app.screen.question and api.mcp_status()["enabled"] is False
            app.screen.query_one("#yes", Button).press()
            await wait(pilot, lambda: api.mcp_status()["enabled"] and scr.query_one("#mcpaddrow").display)
            scr.query_one("#mcpwhere", Input).value = _cmd()
            scr.query_one("#mcpname", Input).value = "Fake"
            scr.query_one("#mcpadd", Button).press()
            await wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            assert FAKE in app.screen.question
            app.screen.query_one("#yes", Button).press()
            await wait(pilot, lambda: [s for s in api.mcp_status()["servers"] if s["state"] == "ready"])
            sid = api.mcp_status()["servers"][0]["id"]
            await wait(pilot, lambda: scr.query(f"#mcpdel-{sid}"))
            scr.query_one(f"#mcpdel-{sid}", Button).press()
            await wait(pilot, lambda: api.mcp_status()["servers"] == [])
    asyncio.run(go())
    api.mcp.stop_all()


def test_two_servers_named_alike_get_different_tool_names(vault, tmp_path):
    api = _api(tmp_path)
    api.mcp_enable(True)
    a = api.mcp_add({"name": "Пам'ять", "kind": "stdio", "where": _cmd()})["id"]
    b = api.mcp_add({"name": "Нотатки", "kind": "stdio", "where": _cmd()})["id"]
    _ready(api, a)
    _ready(api, b)
    names = [n for n in api.toolbox.tools if n.endswith("_echo")]
    assert len(names) == 2 and len(set(names)) == 2
    api.mcp.stop_all()


def test_tool_schemas_keep_only_the_plain_parts():
    s = mcp.clean_schema({"type": "object", "$schema": "x", "additionalProperties": False, "properties": {
        "path": {"type": ["string", "null"], "format": "uri", "description": "where"},
        "mode": {"enum": ["a", "b"], "type": "string", "default": "a"},
        "tags": {"type": "array", "items": {"anyOf": [{"type": "string"}]}},
        "opts": {"type": "object", "properties": {"deep": {"type": "boolean"}}, "required": ["deep", "nope"]}},
        "required": ["path"]})
    assert s == {"type": "object", "properties": {
        "path": {"type": "string", "description": "where"}, "mode": {"type": "string", "enum": ["a", "b"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "opts": {"type": "object", "properties": {"deep": {"type": "boolean"}}, "required": ["deep"]}},
        "required": ["path"]}
