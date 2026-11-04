"""Start a browser or another program without letting it write into Lanterna's terminal.

On Linux, webbrowser.open and a plain Popen hand the browser our terminal, so its
log lines (Chrome, Electron…) land on top of the terminal app. Here the child gets
no terminal at all: its own session, and stdin/stdout/stderr go to /dev/null.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser

_QUIET = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def spawn(args: list[str]) -> bool:
    """Starts a program detached from the terminal. False when it couldn't be started."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(args, close_fds=True, **_QUIET)
        else:
            subprocess.Popen(args, close_fds=True, start_new_session=True, **_QUIET)
        return True
    except OSError:
        return False


def open_url(url: str) -> bool:
    """Opens a link (https, mailto…) in the user's browser or mail app."""
    if sys.platform in ("win32", "darwin"):
        return bool(webbrowser.open(url))
    for opener in (["xdg-open"], ["gio", "open"]):
        if shutil.which(opener[0]) and spawn([*opener, url]):
            return True
    return bool(webbrowser.open(url))             # nothing else found: better noisy than not opening
