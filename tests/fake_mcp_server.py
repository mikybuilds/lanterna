"""A tiny MCP server for the tests (stdio, newline-delimited JSON-RPC)."""
import json
import os
import sys

TOOLS = [
    {"name": "echo", "description": "Says the text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "secret_len", "description": "Length of the token it was given.", "inputSchema": {"type": "object"}},
    {"name": "boom", "description": "Always fails.", "inputSchema": {"type": "object"}},
]

print("a log line that is not JSON", flush=True)
sys.stderr.write("starting with token " + os.environ.get("FAKE_TOKEN", "") + "\n")
sys.stderr.flush()
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    m, p = msg.get("method"), msg.get("params") or {}
    if m == "initialize":
        res = {"protocolVersion": p.get("protocolVersion"), "capabilities": {"tools": {}},
               "serverInfo": {"name": "fake", "version": "1"}}
    elif m == "tools/list":
        if p.get("cursor"):
            res = {"tools": TOOLS[2:]}
        else:
            res = {"tools": TOOLS[:2], "nextCursor": "page2"}
    elif m == "tools/call":
        a = p.get("arguments") or {}
        if p["name"] == "echo":
            res = {"content": [{"type": "text", "text": "echo: " + str(a.get("text"))}]}
        elif p["name"] == "secret_len":
            res = {"content": [{"type": "text", "text": str(len(os.environ.get("FAKE_TOKEN", "")))}]}
        else:
            res = {"content": [{"type": "text", "text": "it broke"}], "isError": True}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no such method"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}), flush=True)
