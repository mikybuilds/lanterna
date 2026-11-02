"""Adds Lanterna to the app menu on Linux desktops (GNOME, KDE, …): a .desktop launcher plus the icon.

    lanterna desktop           # add (or update) the launcher
    lanterna desktop --remove  # take it away again

Only touches files in the user's own folder (~/.local/share). Nothing needs sudo.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ICON_SRC = Path(__file__).parent / "ui" / "logo.svg"


def _share() -> Path:
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def paths() -> tuple[Path, Path]:
    share = _share()
    return share / "applications" / "lanterna.desktop", share / "icons" / "hicolor" / "scalable" / "apps" / "lanterna.svg"


def launcher_text(command: str) -> str:
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
        "Terminal=true",                     # the full-screen app runs in the default terminal (GNOME Console/Terminal)
        "Categories=Utility;Chat;",
        "Keywords=AI;assistant;chat;LLM;Ollama;",
        "StartupNotify=true",
        "",
    ])


def install() -> tuple[Path, Path]:
    exe = shutil.which("lanterna")
    command = f'"{exe}"' if exe else f'"{sys.executable}" -m lanterna.cli'
    desk, icon = paths()
    desk.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    desk.write_text(launcher_text(command), encoding="utf-8")
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
