"""The window app.

  lanterna-gui              native window (Windows: Edge WebView2)
  lanterna-gui --tray       Windows: start hidden in the tray (used by "Start with Windows")
  lanterna-gui --browser    same UI in your browser on 127.0.0.1 (for development and testing)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import Api

UI = Path(__file__).with_name("ui")
METHODS = {"state", "save_settings", "check_key", "delete_key", "open_url", "models", "threads", "search_chats", "snooze_reminder", "new_thread",
           "messages", "rename_thread", "wait_title", "wait_follow_ups", "edit_last", "export_chat", "wait_memory", "export_all", "show_saved", "delete_thread", "send", "poll", "facts", "add_fact", "delete_fact",
           "reminders", "cancel_reminder", "alerts", "hardware", "local_status", "set_local_model",
           "pull_model", "pulls", "cancel_pull", "check_update", "update_notice", "update_install", "update_status", "limits",
           "cards", "pc_undo", "chat_folder", "set_chat_folder", "choose_folder", "check_folder", "limit_now", "action_confirm", "action_cancel", "workdir", "pick_folder", "set_workdir",
           "github_status", "github_connect", "github_cancel", "github_disconnect", "drive_status", "drive_connect", "drive_cancel", "drive_disconnect", "bug_report", "open_mail",
           "sync_status", "sync_sign_in", "sync_cancel", "sync_password", "sync_now", "sync_sign_out",
           "doctor", "history_list", "history_undo", "history_clear", "install_ollama",
           "desktop_status", "quick_hide", "open_in_main", "screenshot",
           "task_list", "task_add", "task_delete", "task_pause", "task_run",
           "voice_status", "voice_start", "voice_stop", "voice_cancel", "voice_setup", "voice_setup_cancel",
           "mcp_status", "mcp_enable", "mcp_add", "mcp_import", "mcp_update", "mcp_remove", "mcp_restart"}
MAX_BODY = 64 * 1024 * 1024          # attachments travel in the request body


class Desk:
    """Windows: the tray icon, the hotkey, the small quick-question window and screenshots.

    Closing the main window hides it while "Keep Lanterna in the tray" is on; Quit in the tray menu ends the app.
    """

    def __init__(self, api: Api, main, quick):
        self.api, self.main, self.quick = api, main, quick
        self.shell = None
        self.quitting = False
        self.quick_shown = False
        self.main_shown = True

    def start(self) -> None:
        """Runs once the windows exist: puts the icon in the tray and takes the hotkey."""
        from . import shell
        self.shell = shell.Shell("Lanterna", UI / "lanterna.ico", self._menu, on_click=self.show_main,
                                 on_hotkey=self.toggle_quick, hotkey=self.api.settings.hotkey)
        if not self.shell.start():
            self.shell = None
        else:
            from . import notify
            notify.TRAY = self.shell.balloon                  # notifications come from Lanterna's own icon
        self.free_hotkey()
        self.api.updater.quit_app = self.quit_now        # an update closes Lanterna: take the tray icon away first

    def free_hotkey(self) -> str:
        """The default hotkey is taken by another app (for example another assistant): take the first free one,
        once, and say which. A hotkey the user picked is never changed. Returns the hotkey now in use, or ""."""
        from . import shell
        sh, s = self.shell, self.api.settings
        if not sh or sh.hotkey_ok or s.hotkey_moved or s.hotkey != shell.HOTKEYS[0]:
            return ""
        for hk in shell.HOTKEYS[1:]:
            if not hk:
                continue
            sh.set_hotkey(hk)
            if sh.hotkey_ok:
                self.api.save_settings({"hotkey": hk, "hotkey_moved": True})
                from . import notify
                from .i18n import t
                msg = t("Another app already uses {old}, so the quick question opens with {new}. You can change it in Settings.",
                        s.lang, old=shell.pretty_hotkey(shell.HOTKEYS[0]), new=shell.pretty_hotkey(hk))
                threading.Thread(target=notify.notify, args=("Lanterna", msg), daemon=True).start()
                return hk
        sh.set_hotkey(s.hotkey)                          # none free: keep the default, Settings shows the warning
        return ""

    def _menu(self) -> list:
        from .i18n import t
        from .shell import pretty_hotkey
        lang, hk = self.api.settings.lang, self.api.settings.hotkey
        quick = t("Quick question", lang) + (f"\t{pretty_hotkey(hk)}" if hk and self.shell and self.shell.hotkey_ok else "")
        return [(t("Open Lanterna", lang), self.show_main), (quick, self.toggle_quick),
                (t("Ask about my screen", lang), self.ask_screen), None, (t("Quit", lang), self.quit)]

    @property
    def in_tray(self) -> bool:
        return bool(self.shell and self.shell.hwnd and self.api.settings.tray)

    # ---------------------------------------------------------------- closing
    def main_closing(self) -> bool:
        """The main window's X: hide to the tray (False = don't close) or end the app."""
        if self.quitting or not self.in_tray:
            self.quitting = True
            threading.Thread(target=self._end, daemon=True).start()
            return True
        self.main.hide()
        self.main_shown = False
        if not self.api.settings.tray_told:
            from . import notify
            from .i18n import t
            msg = t("Lanterna keeps running in the tray. To quit, right-click its icon and choose Quit.", self.api.settings.lang)
            threading.Thread(target=notify.notify, args=("Lanterna", msg), daemon=True).start()
            self.api.save_settings({"tray_told": True})
        return False

    def quick_closing(self) -> bool:
        if self.quitting:
            return True
        self.hide_quick()
        return False

    def _end(self) -> None:
        """The main window is going: close the quick window and the tray too, so the app really ends."""
        from . import notify
        notify.TRAY = None
        if self.shell:
            self.shell.stop()
        self.api.mcp.stop_all()                         # MCP programs end with Lanterna
        try:
            self.quick.destroy()
        except Exception:                                   # noqa: BLE001  already gone
            pass

    def quit(self) -> None:
        self.quitting = True
        self._end()
        try:
            self.main.destroy()
        except Exception:                                   # noqa: BLE001
            pass

    def quit_now(self) -> None:
        """For the updater: the icon goes away before the process ends."""
        if self.shell:
            self.shell.stop()
        self.api.mcp.stop_all()
        import os
        os._exit(0)

    # ---------------------------------------------------------------- windows
    def show_main(self, tid: int | None = None) -> None:
        self.main.show()
        self.main.restore()
        self.main_shown = True
        self.main.evaluate_js(f"window.onShown && onShown({json.dumps(tid)})")

    def hide_quick(self) -> None:
        self.quick.hide()
        self.quick_shown = False

    COPIED_FRESH = 90                                    # seconds: text copied this recently is offered in the quick window

    def copied_text(self) -> str:
        """Text the user copied a moment ago (once per copy), for Translate / Explain / Fix in the quick window.
        The clipboard is read only now, when the user opens the quick window, and nothing is sent until they choose."""
        sh = self.shell
        if not sh or not self.api.settings.copied_text or time.time() - getattr(sh, "copied_at", 0.0) > self.COPIED_FRESH:
            return ""
        sh.copied_at = 0.0                               # offered once: opening the window again doesn't repeat it
        from .shell import clipboard_text
        text = clipboard_text().strip()
        return text if len(text) >= 2 else ""

    def toggle_quick(self, file: dict | None = None) -> None:
        if self.quick_shown and not file:
            return self.hide_quick()
        copied = "" if file else self.copied_text()
        self.quick.evaluate_js(f"window.quickOpen && quickOpen({json.dumps(file)}, {json.dumps(copied)})")
        self.quick.show()
        self.quick.restore()
        self.quick_shown = True

    def open_in_main(self, tid: int | None) -> None:
        """"Open in Lanterna": the quick chat goes on in the big window."""
        self.hide_quick()
        self.show_main(tid)

    # ---------------------------------------------------------------- screenshots
    @staticmethod
    def grab() -> dict:
        """The screen as a PNG attachment ({name, size, data}); {} if it can't be taken."""
        import base64
        import io

        from PIL import ImageGrab
        try:
            box = _cursor_monitor()                         # the screen you are looking at, not always the main one
            img = ImageGrab.grab(all_screens=True) if box else ImageGrab.grab()
            if box:
                l_, t_, r_, b_ = box
                if 0 <= l_ < r_ <= img.width and 0 <= t_ < b_ <= img.height:
                    img = img.crop(box)
                else:                                       # scaling we can't map: the main screen as before
                    img = ImageGrab.grab()
        except OSError:
            return {}
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        data = buf.getvalue()
        return {"name": time.strftime("screen-%H%M%S.png"), "size": len(data), "data": base64.b64encode(data).decode()}

    def screenshot(self) -> dict:
        """The quick window's camera button: hide it for a moment, take the screen, come back."""
        was = self.quick_shown
        if was:
            self.quick.hide()
            time.sleep(0.35)                               # let the window really disappear first
        try:
            return self.grab()
        finally:
            if was:
                self.quick.show()

    def ask_screen(self) -> None:
        """Tray: take the screen as it is now and open a quick question with it attached."""
        file = self.grab()
        if file:
            self.toggle_quick(file)


def _cursor_monitor() -> tuple[int, int, int, int] | None:
    """The monitor under the mouse, as a box inside the picture of all screens; None with one screen or off Windows."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes as W
    u = ctypes.windll.user32
    if u.GetSystemMetrics(80) < 2:                          # SM_CMONITORS: one screen, nothing to choose
        return None

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]
    pt = W.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    u.MonitorFromPoint.restype = ctypes.c_void_p
    u.MonitorFromPoint.argtypes = [W.POINT, W.DWORD]
    u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    mon = u.MonitorFromPoint(pt, 2)                         # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not mon or not u.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)   # where the picture of all screens starts
    r = info.rcMonitor
    return r.left - vx, r.top - vy, r.right - vx, r.bottom - vy


class WindowApi:
    """What the page may call: only the methods in METHODS, as plain bound methods.
    pywebview hands the page every public attribute of js_api and walks into them, so passing the whole Api
    would also expose the store, MCP, the Confirm cards and more. This keeps the page to its own list."""

    def __init__(self, api: Api):
        for name in sorted(METHODS):
            setattr(self, name, getattr(api, name))


def run_window(start_hidden: bool = False) -> int:
    import webview

    if sys.platform == "win32":
        from . import shell
        if shell.tell_running_copy():                       # Lanterna already runs: it shows its window instead
            return 0
    api = Api()
    fresh_ui_cache(api.store.path.parent / "webview")
    page = WindowApi(api)
    desk_ok = sys.platform == "win32"
    hidden = start_hidden and desk_ok and api.settings.tray
    main = webview.create_window("Lanterna", url=str(UI / "index.html"), js_api=page, width=1120, height=780,
                                 min_size=(720, 540), background_color="#0B0E17", text_select=True, hidden=hidden)
    storage = str(api.store.path.parent / "webview")
    if not desk_ok:
        webview.start(private_mode=False, storage_path=storage)
        return 0
    try:                                                    # the quick window opens in the upper middle of the screen
        scr = webview.screens[0]
        x, y = max(0, (scr.width - 640) // 2), max(0, scr.height // 5)
    except Exception:                                       # noqa: BLE001
        x = y = None
    quick = webview.create_window("Lanterna", url=str(UI / "index.html") + "#quick", js_api=page, width=640,
                                  height=470, x=x, y=y, min_size=(420, 320), background_color="#0B0E17",
                                  text_select=True, hidden=True, on_top=True)
    desk = Desk(api, main, quick)
    desk.main_shown = not hidden
    api._desk = desk
    main.events.closing += desk.main_closing
    quick.events.closing += desk.quick_closing
    webview.start(desk.start, private_mode=False, storage_path=storage)
    return 0


def ui_stamp() -> str:
    h = hashlib.sha1()
    for f in ("index.html", "app.js", "style.css", "logo.svg"):
        p = UI / f
        h.update(p.read_bytes() if p.is_file() else b"")
    return h.hexdigest()


def fresh_ui_cache(storage: Path) -> bool:
    """The window's HTTP cache can keep the old app.js after an update. When the UI files change,
    drop only the cache folders (chats, settings and sign-ins live elsewhere)."""
    stamp, mark = ui_stamp(), storage / "ui-stamp"
    try:
        if mark.is_file() and mark.read_text(encoding="utf-8").strip() == stamp:
            return False
        for sub in ("Cache", "Code Cache", "GPUCache"):
            shutil.rmtree(storage / "EBWebView" / "Default" / sub, ignore_errors=True)
        storage.mkdir(parents=True, exist_ok=True)
        mark.write_text(stamp, encoding="utf-8")
        return True
    except OSError:
        return False


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
        from .quiet import open_url
        threading.Timer(0.5, open_url, args=(url,)).start()
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
    ap.add_argument("--tray", action="store_true", help="Windows: start hidden in the tray")
    ap.add_argument("--selfcheck", metavar="REPORT.json", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.selfcheck:
        return selfcheck(a.selfcheck)
    return run_browser(a.port, not a.no_open) if a.browser else run_window(start_hidden=a.tray)


if __name__ == "__main__":
    sys.exit(main())
