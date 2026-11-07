"""Windows: the tray icon, the global hotkey and "only one Lanterna at a time".

Plain Win32 through ctypes (nothing to install). One background thread owns a hidden window: it gets the
tray clicks, the hotkey and the "show yourself" message from a second copy of Lanterna. Callbacks run on
their own short threads, so a slow one never freezes the tray.

On other systems Shell.start() returns False and nothing happens.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path
from typing import Callable

CLASS = "LanternaShellWindow"
WM_APP = 0x8000
WM_TRAY, WM_SHOW_ME, WM_REHOOK, WM_BALLOON = WM_APP + 1, WM_APP + 2, WM_APP + 3, WM_APP + 4
NIN_BALLOONUSERCLICK = 0x0405
WM_CLOSE, WM_DESTROY, WM_COMMAND, WM_HOTKEY = 0x0010, 0x0002, 0x0111, 0x0312
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
WM_CLIPBOARDUPDATE = 0x031D
CF_UNICODETEXT = 13
# formats that password managers (and Windows' own clipboard history) use to say "don't look at this copy"
_PRIVATE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing", "Clipboard Viewer Ignore")
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 1

# the hotkeys Settings offers ("" = off); Ctrl+Shift+Space is free in Windows and in most apps
HOTKEYS = ("ctrl+shift+space", "ctrl+alt+space", "alt+shift+l", "ctrl+shift+l", "")
_MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_KEYS = {"space": 0x20, **{chr(c): c for c in range(ord("a"), ord("z") + 1)}}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """"ctrl+shift+space" -> (modifiers, virtual key); None if empty or not understood."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2 or parts[-1] not in _KEYS or not all(p in _MODS for p in parts[:-1]):
        return None
    mods = 0
    for p in parts[:-1]:
        mods |= _MODS[p]
    key = parts[-1]
    return mods | MOD_NOREPEAT, (ord(key.upper()) if len(key) == 1 else _KEYS[key])


def pretty_hotkey(text: str) -> str:
    """"ctrl+shift+space" -> "Ctrl+Shift+Space"."""
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in (text or "").split("+") if p)


def clipboard_text(limit: int = 20000) -> str:
    """The text on the clipboard now ("" for none, pictures, files, or a copy marked private by a password manager)."""
    if sys.platform != "win32":
        return ""
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.OpenClipboard.argtypes = [ctypes.c_void_p]
    u.GetClipboardData.restype = ctypes.c_void_p
    u.GetClipboardData.argtypes = [ctypes.c_uint]
    u.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    u.RegisterClipboardFormatW.restype = ctypes.c_uint
    u.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    for _ in range(5):                                   # another app may hold the clipboard for a moment
        if u.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return ""
    try:
        if any(u.IsClipboardFormatAvailable(u.RegisterClipboardFormatW(f)) for f in _PRIVATE_FORMATS):
            return ""
        if not u.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        h = u.GetClipboardData(CF_UNICODETEXT)
        p = k.GlobalLock(h) if h else None
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)[:limit]
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_private() -> bool:
    """True when the copy on the clipboard is marked "don't look" (a password manager, private clipboard history)."""
    if sys.platform != "win32":
        return True
    u = ctypes.windll.user32
    u.OpenClipboard.argtypes = [ctypes.c_void_p]
    u.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    u.RegisterClipboardFormatW.restype = ctypes.c_uint
    u.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    for _ in range(5):
        if u.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return True                                      # can't look: treat it as private
    try:
        return any(u.IsClipboardFormatAvailable(u.RegisterClipboardFormatW(f)) for f in _PRIVATE_FORMATS)
    finally:
        u.CloseClipboard()


def clipboard_image(max_side: int = 1600) -> bytes:
    """A picture on the clipboard now (a snip from Win+Shift+S, a copied image) as PNG; b"" for none or private."""
    if sys.platform != "win32" or clipboard_private():
        return b""
    import io

    from PIL import Image, ImageGrab
    try:
        img = ImageGrab.grabclipboard()
    except Exception:                                    # noqa: BLE001  an odd clipboard format
        return b""
    if not isinstance(img, Image.Image) or img.width < 8 or img.height < 8:
        return b""                                       # nothing, or copied files (a list of names)
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def tell_running_copy() -> bool:
    """If Lanterna already runs, asks it to show its window and returns True (this copy should then quit)."""
    if sys.platform != "win32":
        return False
    u = ctypes.windll.user32
    u.FindWindowW.restype = ctypes.c_void_p
    u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    hwnd = u.FindWindowW(CLASS, None)
    if not hwnd:
        return False
    u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    return bool(u.PostMessageW(hwnd, WM_SHOW_ME, 0, 0))


class Shell:
    """The tray icon with its menu and the global hotkey.

    menu: [(label, callback)], or a function that returns it (asked on every right click, so the language can
    change) — None in place of a pair adds a separator line. on_click: a left click on the icon.
    on_hotkey: the hotkey. All callbacks get no arguments.
    """

    def __init__(self, tip: str, icon: Path | None, menu: list, on_click: Callable[[], None],
                 on_hotkey: Callable[[], None], hotkey: str = ""):
        self.tip, self.icon, self.menu = tip[:120], icon, menu
        self.on_click, self.on_hotkey = on_click, on_hotkey
        self.hotkey = hotkey
        self.hotkey_ok = False            # the hotkey is registered (another app may hold it)
        self.copied_at = 0.0              # when something was last copied anywhere (only the time, never what)
        self._balloons: list[tuple[str, str]] = []
        self._balloon_lock = threading.Lock()
        self.hwnd = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- public
    def start(self, timeout: float = 5) -> bool:
        if sys.platform != "win32":
            return False
        self._thread = threading.Thread(target=self._loop, name="lanterna-shell", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return bool(self.hwnd)

    def set_hotkey(self, hotkey: str) -> None:
        """Changes the hotkey ("" turns it off); hotkey_ok says if Windows gave it to us."""
        self.hotkey = hotkey
        if self.hwnd:
            done = threading.Event()
            self._rehook_done = done
            self._post(WM_REHOOK)
            done.wait(2)

    def balloon(self, title: str, message: str) -> bool:
        """A Windows notification from Lanterna's own tray icon (a click on it opens Lanterna)."""
        if not self.hwnd:
            return False
        with self._balloon_lock:
            self._balloons.append((title[:63], message[:255]))
        self._post(WM_BALLOON)
        return True

    def stop(self) -> None:
        if self.hwnd:
            self._post(WM_CLOSE)
            if self._thread:
                self._thread.join(3)

    # ---------------------------------------------------------------- the Win32 part
    def _post(self, msg: int) -> None:
        self._u.PostMessageW(self.hwnd, msg, 0, 0)

    def _fire(self, cb: Callable[[], None] | None) -> None:
        if cb:
            threading.Thread(target=self._safe, args=(cb,), daemon=True).start()

    @staticmethod
    def _safe(cb: Callable[[], None]) -> None:
        try:
            cb()
        except Exception:                                   # noqa: BLE001  a menu click never kills the tray
            pass

    def _loop(self) -> None:
        from ctypes import wintypes as W
        u, k, sh = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
        self._u = u
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                        ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                        ("lpszClassName", W.LPCWSTR)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                        ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                        ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                        ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", W.HICON)]

        u.DefWindowProcW.restype = LRESULT
        u.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u.CreateWindowExW.restype = W.HWND
        u.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
        u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u.LoadImageW.restype = W.HANDLE
        u.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
        u.LoadIconW.restype = W.HICON
        u.LoadIconW.argtypes = [W.HINSTANCE, ctypes.c_void_p]
        u.CreatePopupMenu.restype = W.HMENU
        u.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
        u.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, ctypes.c_void_p]
        u.DestroyMenu.argtypes = [W.HMENU]
        u.SetForegroundWindow.argtypes = [W.HWND]
        u.RegisterHotKey.argtypes = [W.HWND, ctypes.c_int, W.UINT, W.UINT]
        u.UnregisterHotKey.argtypes = [W.HWND, ctypes.c_int]
        u.DestroyWindow.argtypes = [W.HWND]
        u.RegisterWindowMessageW.restype = W.UINT
        u.AddClipboardFormatListener.argtypes = [W.HWND]
        u.RemoveClipboardFormatListener.argtypes = [W.HWND]
        k.GetModuleHandleW.restype = W.HMODULE
        sh.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.c_void_p]

        hinst = k.GetModuleHandleW(None)
        taskbar_created = u.RegisterWindowMessageW("TaskbarCreated")   # Explorer restarted: add the icon again
        hicon = None
        if self.icon and Path(self.icon).is_file():
            hicon = u.LoadImageW(None, str(self.icon), 1, 0, 0, 0x10 | 0x40)    # IMAGE_ICON, LR_LOADFROMFILE|DEFAULTSIZE
        hicon = hicon or u.LoadIconW(None, ctypes.c_void_p(32512))             # IDI_APPLICATION

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.uID, nid.uFlags, nid.uCallbackMessage, nid.hIcon = 1, 0x1 | 0x2 | 0x4, WM_TRAY, hicon   # MESSAGE|ICON|TIP
        nid.szTip = self.tip

        def add_icon() -> None:
            sh.Shell_NotifyIconW(0, ctypes.byref(nid))                          # NIM_ADD

        def hook() -> None:
            u.UnregisterHotKey(self.hwnd, HOTKEY_ID)
            parsed = parse_hotkey(self.hotkey)
            self.hotkey_ok = bool(parsed) and bool(u.RegisterHotKey(self.hwnd, HOTKEY_ID, *parsed))

        def show_menu(hwnd) -> None:
            items = self.menu() if callable(self.menu) else self.menu
            m = u.CreatePopupMenu()
            for i, item in enumerate(items):
                if item is None:
                    u.AppendMenuW(m, 0x800, 0, None)                            # MF_SEPARATOR
                else:
                    u.AppendMenuW(m, 0, 100 + i, item[0])
            pt = W.POINT()
            u.GetCursorPos(ctypes.byref(pt))
            u.SetForegroundWindow(hwnd)                                         # so the menu closes on a click away
            cmd = u.TrackPopupMenu(m, 0x100 | 0x80, pt.x, pt.y, 0, hwnd, None)  # RETURNCMD | NONOTIFY
            u.DestroyMenu(m)
            if 100 <= cmd < 100 + len(items) and items[cmd - 100]:
                self._fire(items[cmd - 100][1])

        def proc(hwnd, msg, wp, lp):
            if msg == WM_TRAY:
                if lp in (WM_LBUTTONUP, NIN_BALLOONUSERCLICK):
                    self._fire(self.on_click)
                elif lp in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    show_menu(hwnd)
                return 0
            if msg == WM_HOTKEY and wp == HOTKEY_ID:
                self._fire(self.on_hotkey)
                return 0
            if msg == WM_BALLOON:
                with self._balloon_lock:
                    todo, self._balloons = self._balloons, []
                for title, text in todo:
                    nid.uFlags = 0x10                                           # NIF_INFO: just the notification
                    nid.szInfoTitle, nid.szInfo = title, text
                    nid.dwInfoFlags, nid.hBalloonIcon = 0x4 | 0x20, hicon       # NIIF_USER | NIIF_LARGE_ICON: our icon
                    sh.Shell_NotifyIconW(1, ctypes.byref(nid))                  # NIM_MODIFY
                nid.uFlags = 0x1 | 0x2 | 0x4
                return 0
            if msg == WM_CLIPBOARDUPDATE:
                self.copied_at = time.time()
                return 0
            if msg == WM_SHOW_ME:
                self._fire(self.on_click)
                return 0
            if msg == WM_REHOOK:
                hook()
                ev = getattr(self, "_rehook_done", None)
                if ev:
                    ev.set()
                return 0
            if msg == taskbar_created:
                add_icon()
                return 0
            if msg == WM_CLOSE:
                u.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                sh.Shell_NotifyIconW(2, ctypes.byref(nid))                      # NIM_DELETE
                u.UnregisterHotKey(hwnd, HOTKEY_ID)
                u.RemoveClipboardFormatListener(hwnd)
                u.PostQuitMessage(0)
                return 0
            return u.DefWindowProcW(hwnd, msg, wp, lp)

        self._proc = WNDPROC(proc)                    # keep a reference: Windows calls it for the window's life
        wc = WNDCLASSW()
        wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = self._proc, hinst, CLASS
        u.RegisterClassW(ctypes.byref(wc))
        self.hwnd = u.CreateWindowExW(0, CLASS, "Lanterna", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            self._ready.set()
            return
        nid.hWnd = self.hwnd
        add_icon()
        hook()
        u.AddClipboardFormatListener(self.hwnd)       # "something was copied" (for the quick window's copied text)
        self._ready.set()
        msg = W.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
        self.hwnd = None
