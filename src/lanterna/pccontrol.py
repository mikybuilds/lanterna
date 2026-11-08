"""This computer, more of it: opening programs, websites and files, and the look of the system.

Opening changes nothing, so it happens right away (only programs the system lists, only http/https links,
never a program file). The look and quick settings come from a fixed list; each change is proposed on a card
(or, when the user let Lanterna act on its own in a chat, done at once) and remembers the old value for Undo.
No other commands are ever run.

GNOME (Fedora, Ubuntu…) through gsettings and wpctl; Windows through current-user settings only.
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable

from . import quiet
from .pcsys import PERSONALIZE, run
from .workspace import WAITING, WorkError

IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jxl", ".avif", ".heic", ".svg", ".tif", ".tiff"}
# files Lanterna never opens: the system would run them
NEVER_OPEN = {".exe", ".msi", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
              ".scr", ".pif", ".lnk", ".reg", ".hta", ".cpl", ".jar", ".sh", ".bash", ".zsh", ".run", ".bin",
              ".appimage", ".desktop", ".py", ".pyw", ".pl", ".rb", ".command", ".deb", ".rpm", ".flatpakref", ".msix",
              ".appx", ".dll", ".sys", ".inf", ".application", ".url", ".scf", ".iso", ".img", ".vhd", ".vhdx"}

ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
DESKTOP = r"Control Panel\Desktop"
IFACE = "org.gnome.desktop.interface"

# id → (label, how). GNOME: ("gs", schema, key, kind, extra); Windows: ("reg", path, name, kind)
GNOME = {
    "accent": ("Accent color", ("gs", IFACE, "accent-color", "enum", None)),
    "text_size": ("Text size", ("gs", IFACE, "text-scaling-factor", "double", (0.75, 2.0))),
    "night_light": ("Night light", ("gs", "org.gnome.settings-daemon.plugins.color", "night-light-enabled", "bool", None)),
    "do_not_disturb": ("Do not disturb", ("gs", "org.gnome.desktop.notifications", "show-banners", "notbool", None)),
    "icon_theme": ("Icons", ("gs", IFACE, "icon-theme", "theme", "icons")),
    "cursor_theme": ("Mouse pointer", ("gs", IFACE, "cursor-theme", "theme", "cursors")),
    "cursor_size": ("Pointer size", ("gs", IFACE, "cursor-size", "int", (16, 128))),
    "app_theme": ("Theme of older apps", ("gs", IFACE, "gtk-theme", "theme", "gtk")),
    "font": ("Interface font", ("gs", IFACE, "font-name", "font", None)),
    "clock_seconds": ("Seconds on the clock", ("gs", IFACE, "clock-show-seconds", "bool", None)),
    "clock_weekday": ("Weekday on the clock", ("gs", IFACE, "clock-show-weekday", "bool", None)),
    "battery_percent": ("Battery percentage", ("gs", IFACE, "show-battery-percentage", "bool", None)),
    "animations": ("Animations", ("gs", IFACE, "enable-animations", "bool", None)),
    "hot_corner": ("Hot corner", ("gs", IFACE, "enable-hot-corners", "bool", None)),
    "window_buttons": ("Window buttons", ("gs", "org.gnome.desktop.wm.preferences", "button-layout", "choice",
                                          {"close": "appmenu:close", "minimize_close": "appmenu:minimize,close",
                                           "all": "appmenu:minimize,maximize,close",
                                           "all_left": "close,maximize,minimize:appmenu"})),
    "wallpaper": ("Wallpaper", ("wallpaper",)),
    "volume": ("Volume", ("volume",)),
    "mute": ("Sound off", ("mute",)),
}
WINDOWS = {
    "transparency": ("Transparency effects", ("reg", PERSONALIZE, "EnableTransparency", "bool")),
    "accent_on_taskbar": ("Accent color on Start and taskbar", ("reg", PERSONALIZE, "ColorPrevalence", "bool")),
    "taskbar_left": ("Taskbar icons on the left", ("reg", ADVANCED, "TaskbarAl", "notbool")),
    "clock_seconds": ("Seconds on the clock", ("reg", ADVANCED, "ShowSecondsInSystemClock", "bool")),
    "file_extensions": ("Show file name extensions", ("reg", ADVANCED, "HideFileExt", "notbool")),
    "hidden_files": ("Show hidden files", ("reg", ADVANCED, "Hidden", "bool12")),
    "wallpaper": ("Wallpaper", ("wallpaper",)),
}
TRUE = {"true", "on", "yes", "1", "так", "увімкни", "sì", "si", "ja", "oui", "tak"}
FALSE = {"false", "off", "no", "0", "ні", "вимкни", "nein", "non", "nie"}


def _gv_str(s: str) -> str:
    """A string as GVariant text for gsettings (passed as one argument, never through a shell)."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _gv_unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1].replace("\\'", "'").replace("\\\\", "\\")
    return v


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise WorkError(f"'{value}' should be on or off.")


def _uri_path(uri: str) -> str:
    from urllib.parse import unquote, urlparse
    return unquote(urlparse(uri).path) if uri.startswith("file://") else uri


class Look:
    """The look of the system and a few quick settings."""

    def __init__(self, actions, places=None, runner: Callable[..., tuple[int, str]] = run, platform_: str = sys.platform,
                 reg=None, which: Callable[[str], str | None] = shutil.which, home: Path | None = None,
                 wallpaper_win: Callable[[str], bool] | None = None):
        from .pcsys import WinReg
        self.actions, self.places, self.run, self.platform, self.which = actions, places, runner, platform_, which
        self.reg = reg if reg is not None else (WinReg() if platform_ == "win32" else None)
        self.home = home or Path.home()
        self._set_wall_win = wallpaper_win or _set_wallpaper_windows

    # ---------------------------------------------------------------- what can be changed here
    def table(self) -> dict:
        if self.platform == "win32":
            return WINDOWS
        if not self.which("gsettings"):
            return {k: v for k, v in GNOME.items() if v[1][0] in ("volume", "mute")} if self._vol_tool() else {}
        out = {}
        for k, v in GNOME.items():
            how = v[1]
            if how[0] == "gs" and self._gs_get(how[1], how[2]) is None:
                continue                                  # this desktop doesn't have it (e.g. accent before GNOME 47)
            if how[0] in ("volume", "mute") and not self._vol_tool():
                continue
            out[k] = v
        return out

    def _gs_get(self, schema: str, key: str) -> str | None:
        code, out = self.run(["gsettings", "get", schema, key])
        return out.strip() if code == 0 and out.strip() else None

    def _gs_choices(self, schema: str, key: str) -> list[str]:
        code, out = self.run(["gsettings", "range", schema, key])
        lines = [x.strip() for x in out.splitlines() if x.strip()]
        if code or not lines or lines[0] != "enum":
            return []
        return [_gv_unquote(x) for x in lines[1:]]

    def themes(self, kind: str) -> list[str]:
        """Installed icon / pointer / app themes (folder names)."""
        dirs = {"icons": ["/usr/share/icons", "~/.local/share/icons", "~/.icons"],
                "cursors": ["/usr/share/icons", "~/.local/share/icons", "~/.icons"],
                "gtk": ["/usr/share/themes", "~/.local/share/themes", "~/.themes"]}[kind]
        out = set()
        for d in dirs:
            base = Path(d.replace("~", str(self.home), 1))
            try:
                for x in base.iterdir():
                    if not x.is_dir():
                        continue
                    if kind == "gtk":
                        ok = (x / "gtk-3.0").is_dir() or (x / "gtk-4.0").is_dir()
                    elif kind == "cursors":
                        ok = (x / "cursors").is_dir()
                    else:                                     # icons: not a pointer-only theme
                        ok = (x / "index.theme").exists() and any(c.is_dir() and c.name != "cursors" for c in x.iterdir())
                    if ok:
                        out.add(x.name)
            except OSError:
                continue
        return sorted(out, key=str.lower)

    def _vol_tool(self) -> str:
        return "wpctl" if self.which("wpctl") else "pactl" if self.which("pactl") else ""

    def _volume(self) -> tuple[int, bool] | None:
        tool = self._vol_tool()
        if tool == "wpctl":
            code, out = self.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
            m = re.search(r"Volume:\s*([\d.]+)", out)
            return (round(float(m.group(1)) * 100), "MUTED" in out) if code == 0 and m else None
        if tool == "pactl":
            code, out = self.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            m = re.search(r"(\d+)%", out)
            code2, mute = self.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
            return (int(m.group(1)), "yes" in mute.lower()) if code == 0 and m else None
        return None

    def current(self, sid: str) -> str:
        """The value now, as Lanterna shows it (and takes it back)."""
        how = self.table()[sid][1]
        if how[0] == "gs":
            raw = self._gs_get(how[1], how[2]) or ""
            kind = how[3]
            if kind == "bool":
                return "on" if raw == "true" else "off"
            if kind == "notbool":
                return "off" if raw == "true" else "on"
            if kind == "choice":
                v = _gv_unquote(raw)
                return next((k for k, x in how[4].items() if x == v), v)
            return _gv_unquote(raw.split()[-1] if kind == "int" and raw.startswith(("int", "uint")) else raw)
        if how[0] == "reg":
            v = self.reg.get("HKEY_CURRENT_USER", how[1], how[2])
            if how[3] == "bool12":
                return "on" if v == 1 else "off"
            on = bool(v) if v is not None else (how[2] in ("EnableTransparency", "TaskbarAl", "HideFileExt"))
            return ("off" if on else "on") if how[3] == "notbool" else ("on" if on else "off")
        if how[0] == "wallpaper":
            if self.platform == "win32":
                return str(self.reg.get("HKEY_CURRENT_USER", DESKTOP, "WallPaper") or "")
            return _uri_path(_gv_unquote(self._gs_get("org.gnome.desktop.background", "picture-uri") or ""))
        vol = self._volume()
        if not vol:
            return ""
        return str(vol[0]) if how[0] == "volume" else ("on" if vol[1] else "off")

    def options(self) -> str:
        tab = self.table()
        if not tab:
            return ("Lanterna can't change the look of this desktop (it knows GNOME and Windows). Open the system "
                    "settings for the user with pc_settings_page.")
        lines = []
        for sid, (label, how) in tab.items():
            try:
                now = self.current(sid)
            except Exception:                              # noqa: BLE001  one odd setting doesn't hide the others
                now = "?"
            allowed = ""
            if how[0] == "gs":
                kind = how[3]
                allowed = ("on | off" if kind in ("bool", "notbool") else
                           " | ".join(self._gs_choices(how[1], how[2])) if kind == "enum" else
                           f"{how[4][0]}–{how[4][1]}" if kind in ("double", "int") else
                           " | ".join(how[4]) if kind == "choice" else
                           ", ".join(self.themes(how[4])[:40]) if kind == "theme" else
                           "a font name and size, e.g. 'Noto Sans 11'")
            elif how[0] == "reg" or how[0] == "mute":
                allowed = "on | off"
            elif how[0] == "volume":
                allowed = "0–100"
            elif how[0] == "wallpaper":
                allowed = "an image in the user's folders: 'pictures/sea.jpg' (place/path)"
            lines.append(f"- {sid} ({label}): now {now or '—'}; values: {allowed}")
        extra = ("\nNot here (open the page with pc_settings_page): text size, night light, accent color, sounds."
                 if self.platform == "win32" else "")
        return "What Lanterna can change (pc_look_set):\n" + "\n".join(lines) + extra + \
            "\nLight / dark theme: pc_theme. Power plan: pc_power_set."

    # ---------------------------------------------------------------- checking a new value
    def _image(self, value: str) -> Path:
        v = str(value or "").strip()
        p = None
        if self.places is not None and "/" in v.replace("\\", "/") and not os.path.isabs(v):
            place, _, rel = v.replace("\\", "/").partition("/")
            if place.lower() in self.places.folders():
                p = self.places.path(place.lower(), rel)
        if p is None:
            p = Path(_uri_path(v)).expanduser()
            if not p.is_absolute():
                raise WorkError("Give the picture as place/path, e.g. 'pictures/sea.jpg'.")
        if not p.is_file():
            raise WorkError(f"There is no picture '{value}'.")
        if p.suffix.lower() not in IMAGES | {".xml"}:
            raise WorkError(f"'{p.name}' is not a picture.")
        return p

    def check(self, sid: str, value) -> tuple[str, str]:
        """→ (the value to set, the value to show). Raises WorkError with what is allowed."""
        tab = self.table()
        if sid not in tab:
            raise WorkError(f"'{sid}' can't be changed here. It can: {', '.join(tab) or 'nothing'}.")
        how = tab[sid][1]
        if how[0] == "gs":
            kind = how[3]
            if kind in ("bool", "notbool"):
                on = _bool(value)
                return ("true" if on != (kind == "notbool") else "false"), ("on" if on else "off")
            if kind == "enum":
                v, ok = str(value).strip().lower(), self._gs_choices(how[1], how[2])
                if v not in ok:
                    raise WorkError(f"{sid}: one of {', '.join(ok)}.")
                return _gv_str(v), v
            if kind in ("double", "int"):
                try:
                    x = float(str(value).strip().rstrip("%x×"))
                except ValueError:
                    raise WorkError(f"{sid}: a number from {how[4][0]} to {how[4][1]}.") from None
                if kind == "double" and x > 5:                      # "125%" → 1.25
                    x /= 100
                if not how[4][0] <= x <= how[4][1]:
                    raise WorkError(f"{sid}: a number from {how[4][0]} to {how[4][1]}.")
                return (f"{x:.2f}" if kind == "double" else str(int(x))), (f"{x:.2f}" if kind == "double" else str(int(x)))
            if kind == "choice":
                v = str(value).strip().lower()
                if v not in how[4]:
                    raise WorkError(f"{sid}: one of {', '.join(how[4])}.")
                return _gv_str(how[4][v]), v
            if kind == "theme":
                names = self.themes(how[4])
                v = next((n for n in names if n.lower() == str(value).strip().lower()), "")
                if not v:
                    raise WorkError(f"{sid}: installed ones are {', '.join(names[:40]) or 'none'}.")
                return _gv_str(v), v
            if kind == "font":
                v = " ".join(str(value).split())
                if not re.fullmatch(r"[\w .,+&'-]{2,60} \d{1,2}(\.\d)?", v):
                    raise WorkError("font: a font name and a size, e.g. 'Noto Sans 11'.")
                fam = v.rsplit(" ", 1)[0].lower()
                if self.which("fc-list"):
                    code, out = self.run(["fc-list", ":", "family"])
                    have = {f.strip().lower() for line in out.splitlines() for f in line.split(",")}
                    if code == 0 and have and fam not in have:
                        raise WorkError(f"There is no font '{v.rsplit(' ', 1)[0]}' on this computer.")
                return _gv_str(v), v
        if how[0] == "reg":
            on = _bool(value)
            bit = on != (how[3] == "notbool")
            return (str(1 if bit else 2) if how[3] == "bool12" else str(int(bit))), ("on" if on else "off")
        if how[0] == "wallpaper":
            p = self._image(value)
            return str(p), str(p)
        if how[0] == "volume":
            try:
                x = int(float(str(value).strip().rstrip("%")))
            except ValueError:
                raise WorkError("volume: a number from 0 to 100.") from None
            if not 0 <= x <= 100:
                raise WorkError("volume: a number from 0 to 100.")
            return str(x), str(x)
        on = _bool(value)                                          # mute
        return ("1" if on else "0"), ("on" if on else "off")

    # ---------------------------------------------------------------- applying
    def _apply(self, sid: str, raw: str) -> None:
        how = self.table()[sid][1]
        if how[0] == "gs":
            code, out = self.run(["gsettings", "set", how[1], how[2], raw])
            if code:
                raise WorkError(out.strip()[:200] or "gsettings failed")
        elif how[0] == "reg":
            self.reg.set("HKEY_CURRENT_USER", how[1], how[2], int(raw), "REG_DWORD")
            _broadcast()
        elif how[0] == "wallpaper":
            if self.platform == "win32":
                if not self._set_wall_win(raw):
                    raise WorkError("Windows didn't accept the picture.")
            else:
                uri = raw if raw.startswith("file://") else Path(raw).as_uri()
                for key in ("picture-uri", "picture-uri-dark"):
                    if self._gs_get("org.gnome.desktop.background", key) is not None:
                        code, out = self.run(["gsettings", "set", "org.gnome.desktop.background", key, _gv_str(uri)])
                        if code:
                            raise WorkError(out.strip()[:200] or "gsettings failed")
        elif how[0] == "volume":
            tool = self._vol_tool()
            args = (["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{int(raw) / 100:.2f}"] if tool == "wpctl" else
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(raw)}%"])
            code, out = self.run(args)
            if code:
                raise WorkError(out.strip()[:200] or "the sound system refused")
        elif how[0] == "mute":
            tool = self._vol_tool()
            code, out = self.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", raw] if tool == "wpctl" else
                                 ["pactl", "set-sink-mute", "@DEFAULT_SINK@", raw])
            if code:
                raise WorkError(out.strip()[:200] or "the sound system refused")

    def _raw_now(self, sid: str) -> str:
        """The exact value now, to put back on Undo."""
        how = self.table()[sid][1]
        if how[0] == "gs":
            return self._gs_get(how[1], how[2]) or ""
        if how[0] == "reg":
            v = self.reg.get("HKEY_CURRENT_USER", how[1], how[2])
            return "" if v is None else str(int(v))
        if how[0] == "wallpaper":
            return self.current(sid)
        vol = self._volume()
        if not vol:
            return ""
        return str(vol[0]) if how[0] == "volume" else ("1" if vol[1] else "0")

    def propose(self, changes: dict, restore: bool = False) -> str:
        """One card for a few changes. restore=True: exact old values from the history (Undo)."""
        if not isinstance(changes, dict) or not changes:
            raise WorkError("Say what to change, e.g. {\"accent\": \"green\"}. pc_look lists what can be changed.")
        tab = self.table()
        plan = []
        for sid, value in list(changes.items())[:12]:
            sid = str(sid).strip().lower()
            if sid not in tab:
                raise WorkError(f"'{sid}' can't be changed here. It can: {', '.join(tab) or 'nothing'}.")
            if restore:
                raw, show = str(value), _uri_path(_gv_unquote(str(value)))
            else:
                raw, show = self.check(sid, value)
            was = self.current(sid)
            if not restore and was == show:
                continue
            plan.append({"id": sid, "label": tab[sid][0], "from": was, "to": show, "raw": raw})
        if not plan:
            return "Nothing to change: it is already like that."

        def go() -> str:
            done, old = [], {}
            for c in plan:
                before = self._raw_now(c["id"])
                try:
                    self._apply(c["id"], c["raw"])
                except Exception as e:                       # noqa: BLE001  what is done stays undoable
                    if done:
                        self.actions.note_undo({"type": "look", "set": old})
                    raise WorkError(f"{c['label']}: {e}" + (f" (done before it: {', '.join(done)})" if done else "")) from None
                if before != "":
                    old[c["id"]] = before
                done.append(c["label"])
            if old:
                self.actions.note_undo({"type": "look", "set": old})
            return "; ".join(f"{c['label']}: {c['to']}" for c in plan)
        self.actions.propose("sys_look", {"changes": [{k: c[k] for k in ("id", "label", "from", "to")} for c in plan],
                                          "count": len(plan), "name": plan[0]["label"]}, go)
        return WAITING


def _broadcast() -> None:
    """Tells Windows a setting changed, so the taskbar and Explorer pick it up now."""
    if sys.platform != "win32":
        return
    try:
        r = ctypes.c_ulong()
        for what in ("ImmersiveColorSet", "TraySettings", None):
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, what, 0x0002, 1000, ctypes.byref(r))
    except (OSError, AttributeError):
        pass


def _set_wallpaper_windows(path: str) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, str(path), 0x01 | 0x02))


# ---------------------------------------------------------------- opening things
WIN_BUILTIN = {"calculator": "calc.exe", "notepad": "notepad.exe", "paint": "mspaint.exe", "file explorer": "explorer.exe",
               "explorer": "explorer.exe", "task manager": "taskmgr.exe", "terminal": "wt.exe", "command prompt": "cmd.exe",
               "settings": "ms-settings:", "control panel": "control.exe", "snipping tool": "snippingtool.exe"}


class Launcher:
    def __init__(self, places=None, platform_: str = sys.platform, which: Callable[[str], str | None] = shutil.which,
                 spawn: Callable[[list], bool] = quiet.spawn, open_url: Callable[[str], bool] = quiet.open_url,
                 startfile: Callable[[str], None] | None = None, app_dirs: list[Path] | None = None):
        self.places, self.platform, self.which, self.spawn, self.open_url = places, platform_, which, spawn, open_url
        self._startfile = startfile or (getattr(os, "startfile", None))
        self._dirs = app_dirs

    def _app_dirs(self) -> list[Path]:
        if self._dirs is not None:
            return self._dirs
        h = Path.home()
        if self.platform == "win32":
            return [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                    Path(os.environ.get("APPDATA", str(h / "AppData/Roaming"))) / r"Microsoft\Windows\Start Menu\Programs"]
        data = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
        return [h / ".local/share/applications", h / ".local/share/flatpak/exports/share/applications",
                Path("/var/lib/flatpak/exports/share/applications"), Path("/var/lib/snapd/desktop/applications")] + \
            [Path(d) / "applications" for d in data if d]

    def programs(self) -> list[dict]:
        """Programs the system menu shows: [{"name", "id", "path"}]."""
        out, seen = [], set()
        if self.platform == "win32":
            for name, exe in WIN_BUILTIN.items():
                out.append({"name": name.title(), "id": exe, "path": exe})
            for d in self._app_dirs():
                for p in sorted(d.rglob("*.lnk")) if d.is_dir() else []:
                    low = p.stem.lower()
                    if low in seen or "uninstall" in low or "readme" in low:
                        continue
                    seen.add(low)
                    out.append({"name": p.stem, "id": p.stem, "path": str(p)})
            return out
        for d in self._app_dirs():
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.desktop")):
                if p.name in seen:
                    continue
                seen.add(p.name)
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                entry = text.split("[Desktop Entry]", 1)[-1].split("\n[", 1)[0]
                if re.search(r"^(NoDisplay|Hidden)=true", entry, re.M | re.I) or not re.search(r"^Type=Application", entry, re.M):
                    continue
                name = re.search(r"^Name=(.+)$", entry, re.M)
                generic = re.search(r"^GenericName=(.+)$", entry, re.M)
                keywords = re.search(r"^Keywords=(.+)$", entry, re.M)
                out.append({"name": name.group(1).strip() if name else p.stem, "id": p.name, "path": str(p),
                            "also": " ".join(x.group(1) for x in (generic, keywords) if x)})
        return out

    def find(self, name: str) -> list[dict]:
        q = " ".join(str(name or "").lower().split())
        if not q:
            return []
        progs = self.programs()
        for test in (lambda p: p["name"].lower() == q,
                     lambda p: p["name"].lower().startswith(q),
                     lambda p: all(w in p["name"].lower() for w in q.split()),
                     lambda p: all(w in (p["name"] + " " + p.get("also", "") + " " + p["id"]).lower() for w in q.split())):
            hits = [p for p in progs if test(p)]
            if hits:
                return hits
        return []

    def open_program(self, name: str) -> str:
        hits = self.find(name)
        if not hits:
            return (f"No program called '{name}' is installed. To install one, use app_search; or open its website "
                    "with pc_open_site.")
        if len(hits) > 1 and len({h["name"].lower() for h in hits}) > 1 and not any(h["name"].lower() == str(name).lower() for h in hits):
            return "Several programs match: " + ", ".join(h["name"] for h in hits[:12]) + ". Call again with the exact name."
        p = next((h for h in hits if h["name"].lower() == str(name).lower()), hits[0])
        if self.platform == "win32":
            if p["path"] == "ms-settings:":
                self.open_url("ms-settings:")
            elif p["path"].lower().endswith(".lnk"):
                if not self._startfile:
                    raise WorkError("Can't start programs here.")
                self._startfile(p["path"])
            elif not self.spawn([p["path"]]):
                raise WorkError(f"{p['name']} didn't start.")
            return f"Opened {p['name']}."
        ok = False
        if self.which("gio"):
            ok = self.spawn(["gio", "launch", p["path"]])
        if not ok and self.which("gtk-launch"):
            ok = self.spawn(["gtk-launch", p["id"][:-8] if p["id"].endswith(".desktop") else p["id"]])
        if not ok:
            raise WorkError(f"{p['name']} didn't start.")
        return f"Opened {p['name']}."

    def open_site(self, url: str) -> str:
        u = str(url or "").strip()
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I):
            u = "https://" + u
        if not re.match(r"^https?://[^\s/]+", u, re.I):
            raise WorkError("Only web addresses (http or https) are opened.")
        if not self.open_url(u):
            raise WorkError("No browser opened.")
        return f"Opened {u} in the browser."

    def open_file(self, place: str, path: str) -> str:
        if self.places is None:
            raise WorkError("The user's folders aren't available.")
        p = self.places.path(place, path)
        if not p.exists():
            raise WorkError(f"There is no '{path}' in {place}.")
        if p.is_file() and (p.suffix.lower() in NEVER_OPEN or os.access(p, os.X_OK) and self.platform != "win32"
                            and p.suffix.lower() not in IMAGES | {".pdf", ".txt", ".md", ".docx", ".odt", ".xlsx", ".csv"}):
            raise WorkError(f"Lanterna doesn't open {p.suffix or 'program'} files: they could run a program. "
                            "Show it with pc_show instead.")
        if self.platform == "win32":
            if not self._startfile:
                raise WorkError("Can't open files here.")
            self._startfile(str(p))
        else:
            opener = ["xdg-open"] if self.which("xdg-open") else ["gio", "open"]
            if not self.spawn([*opener, str(p)]):
                raise WorkError("No program opened it.")
        return f"Opened {place}/{self.places.rel(place, p)}."


# ---------------------------------------------------------------- tools
def control_tools(look: Look, launcher: Launcher, places) -> list:
    from .tools import Tool, _obj
    s = {"type": "string"}
    out = [
        Tool("pc_open_program", "Open (start) a program installed on this computer by its name: browser, Files, "
             "Calculator, Settings, Terminal, Firefox, Telegram… Immediate: it changes nothing.",
             _obj({"name": s}, ["name"]), lambda name: launcher.open_program(name), "🚀"),
        Tool("pc_open_site", "Open a website in the user's browser: 'open Google' → https://www.google.com , a search "
             "→ https://www.google.com/search?q=… Immediate. Only for what the user asked to open.",
             _obj({"url": s}, ["url"]), lambda url: launcher.open_site(url), "🌐"),
        Tool("pc_look", "The look of the system and quick settings that Lanterna can change, with the values now and "
             "the allowed ones: wallpaper, accent color, icons, pointer, fonts, text size, night light, do not "
             "disturb, clock, window buttons, volume… Call it before pc_look_set.",
             _obj({}), lambda: look.options(), "🎨"),
        Tool("pc_look_set", "Change the look or quick settings: several at once, e.g. {\"accent\": \"purple\", "
             "\"icon_theme\": \"Papirus\", \"wallpaper\": \"pictures/sea.jpg\"}. Names and values from pc_look. "
             "The old values are kept for Undo. The user confirms it on a card, so don't ask in text first.",
             _obj({"changes": {"type": "object", "description": "setting id → new value"}}, ["changes"]),
             lambda changes: look.propose(changes if isinstance(changes, dict) else {}), "🎨"),
    ]
    if places is not None and places.folders():
        out.append(Tool("pc_open_file", "Open a file from the user's folders in its usual program (a document, a "
                        "photo, a video). Program files are never opened.",
                        _obj({"place": {"type": "string", "enum": list(places.folders())}, "path": s}, ["place", "path"]),
                        lambda place, path: launcher.open_file(place, path), "📂"))
    return out
