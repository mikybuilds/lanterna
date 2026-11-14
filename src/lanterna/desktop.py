"""Adds Lanterna to the app menu on Linux desktops (GNOME, KDE, …): a .desktop launcher plus the icon.

    lanterna desktop             # add (or update) the launcher
    lanterna desktop --terminal  # the full-screen app in the terminal, also where the window would open
    lanterna desktop --remove    # take it away again

The launcher opens Lanterna's own window (lanterna-gui) when it can open here: pywebview with the system's GTK
WebKit (or Qt's WebEngine). Otherwise it opens the full-screen app in the terminal, and `lanterna desktop` says
which system parts give it the window. Only touches files in the user's own folder (~/.local/share). Nothing
needs sudo.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

ICON_SRC = Path(__file__).parent / "ui" / "logo.svg"
REPO = "git+https://github.com/mikybuilds/lanterna"

# the system's PyGObject and WebKitGTK 4.1, by the distribution (/etc/os-release ID, then ID_LIKE)
PARTS = {
    "fedora": "sudo dnf install python3-gobject webkit2gtk4.1",
    "ubuntu": "sudo apt install python3-gi gir1.2-webkit2-4.1",
    "debian": "sudo apt install python3-gi gir1.2-webkit2-4.1",
    "arch": "sudo pacman -S --needed python-gobject webkit2gtk-4.1",
}


def _share() -> Path:
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def paths() -> tuple[Path, Path]:
    share = _share()
    return share / "applications" / "lanterna.desktop", share / "icons" / "hicolor" / "scalable" / "apps" / "lanterna.svg"


def launcher_text(command: str, terminal: bool = True) -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Lanterna",
        "GenericName=AI assistant",
        "Comment=A friendly AI assistant on free cloud models or your own local models",
        "Comment[uk]=Дружній ШІ-асистент на безкоштовних хмарних або твоїх локальних моделях",
        "Comment[it]=Un assistente IA amichevole con modelli cloud gratuiti o locali",
        f"Exec={command}",
        "Icon=lanterna",
        # the full-screen app runs in the default terminal (GNOME Console/Terminal); the window needs none, and its
        # dock icon is this launcher's (gui.py names the window "lanterna")
        "Terminal=true" if terminal else "Terminal=false",
        *([] if terminal else ["StartupWMClass=lanterna"]),
        "Categories=Utility;Chat;",
        "Keywords=AI;assistant;chat;LLM;Ollama;",
        "StartupNotify=true",
        "",
    ])


def _qt_ready() -> bool:
    if importlib.util.find_spec("qtpy") is None:
        return False
    for qt in ("PyQt6", "PySide6", "PyQt5", "PySide2"):
        try:
            if importlib.util.find_spec(f"{qt}.QtWebEngineWidgets"):
                return True
        except ImportError:                      # (that Qt isn't there)
            pass
    return False


def window_ready() -> set[str]:
    """What Lanterna's own window still needs here; empty: it opens. "pywebview" (the Python package), "gi" (the
    system's PyGObject, as Lanterna's own Python sees it), "webkit" (the system's WebKitGTK)."""
    need = set() if importlib.util.find_spec("webview") else {"pywebview"}
    if _qt_ready():
        return need
    try:
        import gi
    except ImportError:
        return need | {"gi", "webkit"}           # (the system's packages bring both)
    try:
        gi.require_version("Gtk", "3.0")
        try:                                     # what pywebview's GTK part asks for
            gi.require_version("WebKit2", "4.1")
        except ValueError:
            gi.require_version("WebKit2", "4.0")
    except ValueError:
        need.add("webkit")
    return need


def distro(release: Path = Path("/etc/os-release")) -> list[str]:
    """This Linux's ID and the ones it is like: ["fedora"], ["linuxmint", "ubuntu", "debian"]…"""
    try:
        lines = release.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    info = dict(line.split("=", 1) for line in lines if "=" in line)
    ids = [info.get("ID", "")] + info.get("ID_LIKE", "").strip('"').split()
    return [i.strip().strip('"').lower() for i in ids if i.strip().strip('"')]


def window_steps(need: set[str], ids: list[str] | None = None) -> list[str]:
    """The commands that give Lanterna its own window (README → Linux → Its own window). A line starting with "#"
    is said, not run: the system's packages, where Lanterna doesn't know their names."""
    steps = []
    if need & {"gi", "webkit"}:
        known = [PARTS[i] for i in (distro() if ids is None else ids) if i in PARTS]
        steps.append(known[0] if known else "# PyGObject + WebKitGTK 4.1")
    if "gi" in need:                             # Lanterna's Python sees the system's PyGObject only this way
        steps += [f"pipx install --force --system-site-packages {REPO}", "pipx inject lanterna pywebview"]
    elif "pywebview" in need:
        steps.append("pipx inject lanterna pywebview")
    return [*steps, "lanterna desktop"] if steps else []


def install(window: bool = False) -> tuple[Path, Path]:
    """The launcher: Lanterna's own window (window) or the full-screen app in the terminal."""
    exe = shutil.which("lanterna-gui" if window else "lanterna")
    command = f'"{exe}"' if exe else f'"{sys.executable}" -m {"lanterna.gui" if window else "lanterna.cli"}'
    desk, icon = paths()
    desk.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    desk.write_text(launcher_text(command, terminal=not window), encoding="utf-8")
    desk.chmod(0o755)
    shutil.copyfile(ICON_SRC, icon)
    if shutil.which("update-desktop-database"):
        os.system(f'update-desktop-database "{desk.parent}" >/dev/null 2>&1')
    return desk, icon


def remove() -> bool:
    found = False
    for p in paths():
        if p.exists():
            p.unlink()
            found = True
    return found
