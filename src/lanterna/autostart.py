"""Windows: start Lanterna (hidden in the tray) when the user signs in. Off until the user turns it on.

One value in the user's own Run key (HKCU, no admin rights); turning it off removes the value, and the
uninstaller removes it too.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Lanterna"


def command() -> str:
    """What Windows runs at sign-in: the installed Lanterna.exe, or pythonw -m lanterna.gui from a dev install."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.is_file() else exe}" -m lanterna.gui --tray'


def _reg():
    import winreg
    return winreg


def enabled() -> bool:
    if sys.platform != "win32":
        return False
    w = _reg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN) as k:
            return bool(w.QueryValueEx(k, NAME)[0])
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """Turns start-at-sign-in on or off; returns the state it ended up in."""
    if sys.platform != "win32":
        return False
    w = _reg()
    try:
        with w.CreateKey(w.HKEY_CURRENT_USER, RUN) as k:
            if on:
                w.SetValueEx(k, NAME, 0, w.REG_SZ, command())
            else:
                try:
                    w.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    return enabled()
