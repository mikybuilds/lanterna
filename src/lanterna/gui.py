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
           "messages", "rename_thread", "delete_thread", "send", "poll", "facts", "add_fact", "delete_fact",
           "reminders", "cancel_reminder", "alerts", "hardware", "local_status", "set_local_model",
           "pull_model", "pulls", "cancel_pull", "check_update", "update_notice", "update_install", "update_status", "limits",
           "cards", "action_confirm", "action_cancel", "workdir", "pick_folder", "set_workdir",
           "drive_status", "drive_connect", "drive_cancel", "drive_disconnect", "bug_report", "open_mail",
           "sync_status", "sync_sign_in", "sync_cancel", "sync_password", "sync_now", "sync_sign_out"}
MAX_BODY = 64 * 1024 * 1024          # attachments travel in the request body


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
            if n > MAX_BODY:
                return self._send(413, b"{}")
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


def selfcheck(out: str) -> int:
    """Checks that a packaged build has everything inside; writes a JSON report (a windowed exe has no console)."""
    report: dict = {}
    for name in ("pypdf", "PIL", "webview", "keyring", "httpx"):
        try:
            __import__(name)
            report[name] = "ok"
        except Exception as e:                              # noqa: BLE001 - report anything
            report[name] = f"missing: {e}"
    report["ui"] = all((UI / f).is_file() for f in ("index.html", "app.js", "style.css", "logo.svg"))
    try:                                                    # sync encryption must work inside the build
        from . import sync
        salt, key = b"s" * 16, b"k" * 32
        report["crypto"] = "ok" if sync.decrypt(sync.encrypt({"x": 1}, key, salt), key) == {"x": 1} else "wrong"
    except Exception as e:                                  # noqa: BLE001
        report["crypto"] = f"missing: {e}"
    try:
        from . import __version__, hardware, local
        report["version"] = __version__
        report["hardware"] = hardware.detect().to_dict()
        report["ollama"] = local.version() or ""
    except Exception as e:                                  # noqa: BLE001
        report["error"] = str(e)
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all(v == "ok" for k, v in report.items() if k in ("pypdf", "PIL", "webview", "keyring", "httpx", "crypto")) and report["ui"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lanterna-gui")
    ap.add_argument("--browser", action="store_true", help="open the UI in a browser instead of a window")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--selfcheck", metavar="REPORT.json", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.selfcheck:
        return selfcheck(a.selfcheck)
    return run_browser(a.port, not a.no_open) if a.browser else run_window()


if __name__ == "__main__":
    sys.exit(main())
