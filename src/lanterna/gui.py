"""The window app.

  lanterna-gui              native window (Windows: Edge WebView2)
  lanterna-gui --browser    same UI in your browser on 127.0.0.1 (for development and testing)
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import Api

UI = Path(__file__).with_name("ui")
METHODS = {"state", "save_settings", "check_key", "delete_key", "open_url", "models", "threads", "new_thread",
           "messages", "rename_thread", "delete_thread", "send", "poll"}


def run_window() -> int:
    import webview

    api = Api()
    webview.create_window("Lanterna", url=str(UI / "index.html"), js_api=api, width=1120, height=780,
                          min_size=(720, 540), background_color="#0B0E17", text_select=True)
    webview.start(private_mode=False, storage_path=str(api.store.path.parent / "webview"))
    return 0


def make_server(api: Api, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Dev server bound to localhost; every API call needs the random token from the URL."""
    token = secrets.token_urlsafe(16)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            name = self.path.split("?")[0].lstrip("/") or "index.html"
            f = (UI / name).resolve()
            if UI.resolve() not in f.parents or not f.is_file():
                return self._send(404, b"{}")
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if len(parts) != 2 or parts[0] != "api" or parts[1] not in METHODS or self.headers.get("X-Token") != token:
                return self._send(403, b"{}")
            n = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(n) or b"[]")
            result = getattr(api, parts[1])(*args)
            self._send(200, json.dumps(result, ensure_ascii=False).encode())

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html?token={token}"


def run_browser(port: int, open_browser: bool) -> int:
    srv, url = make_server(Api(), port)
    print(url, flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lanterna-gui")
    ap.add_argument("--browser", action="store_true", help="open the UI in a browser instead of a window")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    return run_browser(a.port, not a.no_open) if a.browser else run_window()


if __name__ == "__main__":
    sys.exit(main())
