"""This computer: what it has and what is slowing it down, plus a short list of safe settings.

Looking (specs, disks, memory, busy programs, startup programs, power plans) is immediate and read locally.
Changes come only from this fixed list and each one is proposed on a card first:
- light / dark theme,
- power plan (one of the plans the system lists),
- a program starting with the computer: off / on again (the same switch as Task Manager or the autostart folder),
plus opening a page of the system Settings. No other commands are ever run.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from . import quiet
from .workspace import WAITING, WorkError

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Settings pages: Windows ms-settings: and GNOME Settings panels
PAGES = {
    "display": ("display", "display"), "sound": ("sound", "sound"), "bluetooth": ("bluetooth", "bluetooth"),
    "wifi": ("network-wifi", "wifi"), "network": ("network", "network"), "updates": ("windowsupdate", None),
    "default_apps": ("defaultapps", "default-apps"), "startup": ("startupapps", None),
    "storage": ("storagesense", None), "power": ("powersleep", "power"), "colors": ("colors", "background"),
    "privacy": ("privacy", "privacy"), "mouse": ("mousetouchpad", "mouse"), "keyboard": ("keyboard", "keyboard"),
    "datetime": ("dateandtime", "datetime"), "language": ("regionlanguage", "region"),
    "notifications": ("notifications", "notifications"), "printers": ("printers", "printers"),
    "apps": ("appsfeatures", "applications"), "battery": ("batterysaver", "power"),
}


def _decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        cp = f"cp{ctypes.windll.kernel32.GetOEMCP()}" if sys.platform == "win32" else "latin-1"
        return b.decode(cp, "replace")


def run(args: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, _decode(r.stdout or b"") + (_decode(r.stderr) if r.stderr else "")


class WinReg:
    """The few registry places used here (current user only, except reading the machine Run list)."""

    def get(self, hive: str, path: str, name: str):
        import winreg
        try:
            with winreg.OpenKey(getattr(winreg, hive), path) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None

    def values(self, hive: str, path: str) -> dict:
        import winreg
        out = {}
        try:
            with winreg.OpenKey(getattr(winreg, hive), path) as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    out[n] = v
                    i += 1
        except OSError:
            pass
        return out

    def set(self, hive: str, path: str, name: str, value, kind: str) -> None:
        import winreg
        if hive != "HKEY_CURRENT_USER":
            raise WorkError("Lanterna only changes settings of the current user.")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
            winreg.SetValueEx(k, name, 0, getattr(winreg, kind), value)


def _filetime_now() -> bytes:
    return struct.pack("<Q", int((time.time() + 11644473600) * 10_000_000))


class System:
    def __init__(self, actions, runner: Callable[..., tuple[int, str]] = run, platform_: str = sys.platform,
                 reg=None, home: Path | None = None, which: Callable[[str], str | None] = shutil.which,
                 opener: Callable[[str], None] | None = None):
        self.actions, self.run, self.platform, self.which = actions, runner, platform_, which
        self.reg = reg if reg is not None else (WinReg() if platform_ == "win32" else None)
        self.home = home or Path.home()
        self._open = opener or _open_uri

    # ---------------------------------------------------------------- looking
    def info(self) -> str:
        from .hardware import detect
        hw = detect()
        lines = [f"System: {platform.system()} {platform.release()} ({platform.version()[:60]}), {platform.machine()}",
                 f"Processor: {_cpu_name()} — {os.cpu_count()} threads",
                 f"Memory: {hw.ram_gb} GB" + (f", {mem_free_gb():.1f} GB free now" if mem_free_gb() else ""),
                 f"Graphics: {hw.gpu or 'not found'}" + (f", {hw.vram_gb} GB" if hw.vram_gb else "")]
        for d, total, free in disks():
            lines.append(f"Disk {d}: {free / 1024 ** 3:.0f} GB free of {total / 1024 ** 3:.0f} GB"
                         + (" — almost full" if free / max(total, 1) < 0.1 else ""))
        up = uptime_hours()
        if up:
            lines.append(f"On for: {up:.0f} hours" + (" (a restart often helps when it has been days)" if up > 72 else ""))
        bat = battery()
        if bat:
            lines.append(f"Battery: {bat}")
        return "\n".join(lines)

    def load(self) -> str:
        """What is busy right now: memory and processor per program."""
        rows = self._processes()
        if not rows:
            return "Couldn't read the running programs."
        by_mem = sorted(rows, key=lambda r: -r["mem"])[:10]
        by_cpu = sorted(rows, key=lambda r: -r["cpu"])[:8]
        free = mem_free_gb()
        out = [f"Free memory now: {free:.1f} GB." if free else ""]
        out.append("Most memory: " + "; ".join(f"{r['name']} {r['mem'] / 1024 ** 2:.0f} MB" for r in by_mem))
        if any(r["cpu"] > 0 for r in by_cpu):
            out.append("Most processor now: " + "; ".join(f"{r['name']} {r['cpu']:.0f}%" for r in by_cpu if r["cpu"] > 0.5))
        return "\n".join(x for x in out if x)

    def _processes(self) -> list[dict]:
        if self.platform == "win32":
            # two looks one second apart: processor seconds used in between = how busy each program is now
            ps = ("$a=@{}; Get-Process | ForEach-Object { $a[$_.Id]=$_.CPU }; Start-Sleep -Milliseconds 1000; "
                  "Get-Process | Where-Object { $_.Id -ne 0 } | ForEach-Object { [pscustomobject]@{n=$_.ProcessName; "
                  "c=[double]($_.CPU - $a[$_.Id]); m=[int64]$_.WorkingSet64} } | ConvertTo-Json -Compress")
            code, out = self.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=30)
            try:
                data = json.loads(out[out.index("["):]) if "[" in out else []
            except ValueError:
                return []
            cores = os.cpu_count() or 1
            agg: dict[str, dict] = {}
            for r in data:
                name = str(r.get("n") or "")
                a = agg.setdefault(name, {"name": name, "cpu": 0.0, "mem": 0})
                a["cpu"] += max(0.0, float(r.get("c") or 0)) * 100 / cores
                a["mem"] += int(r.get("m") or 0)
            return list(agg.values())
        code, out = self.run(["ps", "-eo", "comm=,pcpu=,rss="])
        agg = {}
        for line in out.splitlines():
            parts = line.rsplit(None, 2)
            if len(parts) != 3:
                continue
            try:
                cpu, rss = float(parts[1]), int(parts[2]) * 1024
            except ValueError:
                continue
            a = agg.setdefault(parts[0], {"name": parts[0], "cpu": 0.0, "mem": 0})
            a["cpu"] += cpu
            a["mem"] += rss
        return list(agg.values())

    # -- startup programs
    def startup_items(self) -> list[dict]:
        items = []
        if self.platform == "win32":
            approved = self.reg.values("HKEY_CURRENT_USER", APPROVED + r"\Run")
            approved_m = self.reg.values("HKEY_LOCAL_MACHINE", APPROVED + r"\Run")
            for hive, sub, appr, mine in (("HKEY_CURRENT_USER", RUN_KEY, approved, True),
                                          ("HKEY_LOCAL_MACHINE", RUN_KEY, approved_m, False)):
                for name, cmd in self.reg.values(hive, sub).items():
                    flag = appr.get(name)
                    on = not (isinstance(flag, (bytes, bytearray)) and flag[:1] in (b"\x03", b"\x01", b"\x07"))
                    items.append({"name": name, "on": on, "command": str(cmd)[:160], "user": mine, "where": "run"})
            folder = self.home / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
            appr_f = self.reg.values("HKEY_CURRENT_USER", APPROVED + r"\StartupFolder")
            if folder.is_dir():
                for f in folder.iterdir():
                    if f.name.lower() == "desktop.ini":
                        continue
                    flag = appr_f.get(f.name)
                    on = not (isinstance(flag, (bytes, bytearray)) and flag[:1] in (b"\x03", b"\x01", b"\x07"))
                    items.append({"name": f.name, "on": on, "command": str(f), "user": True, "where": "folder"})
            return items
        user_dir = self.home / ".config" / "autostart"
        seen = set()
        for d, mine in ((user_dir, True), (Path("/etc/xdg/autostart"), False)):
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.desktop")):
                if f.name in seen:
                    continue
                seen.add(f.name)
                text = _read((user_dir / f.name) if (user_dir / f.name).exists() else f)
                name = re.search(r"^Name=(.+)$", text, re.M)
                hidden = re.search(r"^Hidden=true", text, re.M | re.I)
                off_gnome = re.search(r"^X-GNOME-Autostart-enabled=false", text, re.M | re.I)
                items.append({"name": f.name, "title": name.group(1) if name else f.stem, "on": not (hidden or off_gnome),
                              "command": (re.search(r"^Exec=(.+)$", text, re.M) or [None, ""])[1][:160],
                              "user": True, "where": "autostart"})
        return items

    def startup(self) -> str:
        items = self.startup_items()
        if not items:
            return "No programs start with the computer (that Lanterna can see)."
        lines = [f"- {'ON ' if i['on'] else 'off'}  {i.get('title') or i['name']}" + ("" if i["user"] else " (for all users: change it in Task Manager)")
                 for i in items]
        return "Programs that start with the computer:\n" + "\n".join(lines)

    def power_plans(self) -> list[dict]:
        if self.platform == "win32":
            code, out = self.run(["cmd", "/d", "/c", "chcp 65001 >nul & powercfg /list"])   # names in UTF-8
            plans = []
            for m in re.finditer(r"([0-9a-f]{8}-[0-9a-f-]{27})\s+\((.+?)\)\s*(\*)?", out, re.I):
                if m.group(1).lower() not in {p["id"] for p in plans}:
                    plans.append({"id": m.group(1).lower(), "name": m.group(2), "active": bool(m.group(3))})
            return plans
        if self.which("powerprofilesctl"):
            code, out = self.run(["powerprofilesctl", "list"])
            return [{"id": m.group(2), "name": m.group(2), "active": bool(m.group(1))}
                    for m in re.finditer(r"^(\*)?\s*([a-z-]+):\s*$", out, re.M)]
        return []

    def power(self) -> str:
        plans = self.power_plans()
        if not plans:
            return "Couldn't read the power plans."
        return "Power plans:\n" + "\n".join(f"- {'(active) ' if p['active'] else ''}{p['name']} — id {p['id']}" for p in plans)

    def theme_now(self) -> str:
        if self.platform == "win32":
            v = self.reg.get("HKEY_CURRENT_USER", PERSONALIZE, "AppsUseLightTheme")
            return "light" if v in (None, 1) else "dark"
        code, out = self.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
        return "dark" if "dark" in out else "light"

    def _theme_is(self, theme: str) -> bool:
        """Already like that everywhere a switch would change (on Windows the apps' part and the system's part)."""
        if self.platform == "win32":
            want = 1 if theme == "light" else 0
            vals = [self.reg.get("HKEY_CURRENT_USER", PERSONALIZE, k) for k in ("AppsUseLightTheme", "SystemUsesLightTheme")]
            return all((1 if v is None else v) == want for v in vals)
        return self.theme_now() == theme

    # ---------------------------------------------------------------- changes (cards)
    def propose_theme(self, theme: str) -> str:
        theme = str(theme or "").lower()
        if theme not in ("dark", "light"):
            raise WorkError("theme must be dark or light.")
        if self.platform != "win32" and not self.which("gsettings"):
            raise WorkError("This desktop can't be switched by Lanterna; change it in the system settings.")
        was = self.theme_now()
        if self._theme_is(theme):           # a card that changes nothing only confuses (and Undo would do nothing)
            return f"Nothing to change: the theme is already {theme}."

        def go() -> str:
            if self.platform == "win32":
                v = 1 if theme == "light" else 0
                self.reg.set("HKEY_CURRENT_USER", PERSONALIZE, "AppsUseLightTheme", v, "REG_DWORD")
                self.reg.set("HKEY_CURRENT_USER", PERSONALIZE, "SystemUsesLightTheme", v, "REG_DWORD")
            else:
                code, out = self.run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme",
                                      "prefer-dark" if theme == "dark" else "default"])
                if code:
                    raise WorkError(out.strip()[:200] or "gsettings failed")
            if was in ("dark", "light") and was != theme:
                self.actions.note_undo({"type": "theme", "to": was})
            return f"theme {theme}"
        self.actions.propose("sys_theme", {"theme": theme, "was": was}, go)
        return WAITING

    def propose_power(self, plan_id: str) -> str:
        plans = self.power_plans()
        plan = next((p for p in plans if p["id"] == str(plan_id).strip().lower() or p["name"].lower() == str(plan_id).strip().lower()), None)
        if not plan:
            raise WorkError("Unknown power plan. Available: " + ", ".join(f"{p['name']} ({p['id']})" for p in plans))
        was = next((p["name"] for p in plans if p["active"]), "")

        def go() -> str:
            if self.platform == "win32":
                if not GUID.match(plan["id"]):
                    raise WorkError("Bad plan id.")
                code, out = self.run(["powercfg", "/setactive", plan["id"]])
            else:
                code, out = self.run(["powerprofilesctl", "set", plan["id"]])
            if code:
                raise WorkError(out.strip()[:200] or "the system refused")
            if was and was != plan["name"]:
                self.actions.note_undo({"type": "power", "to": was})
            return f"power plan {plan['name']}"
        self.actions.propose("sys_power", {"name": plan["name"], "id": plan["id"], "was": was}, go)
        return WAITING

    def propose_startup(self, name: str, on: bool) -> str:
        items = self.startup_items()
        it = next((i for i in items if i["name"] == name or (i.get("title") or "").lower() == str(name).lower()
                   or i["name"].lower() == str(name).lower()), None)
        if not it:
            raise WorkError("No such startup program. Ask pc_startup for the list.")
        if not it["user"]:
            self._open("ms-settings:startupapps" if self.platform == "win32" else "")
            return ("This program starts for all users; changing it needs administrator rights. The Startup apps page "
                    "of Settings was opened for the user to switch it there.")
        if it["on"] == bool(on):
            return f"'{it['name']}' is already {'on' if on else 'off'}."

        def go() -> str:
            if self.platform == "win32":
                sub = APPROVED + (r"\StartupFolder" if it["where"] == "folder" else r"\Run")
                value = (b"\x02" + b"\x00" * 11) if on else (b"\x03\x00\x00\x00" + _filetime_now())
                self.reg.set("HKEY_CURRENT_USER", sub, it["name"], value, "REG_BINARY")
            else:
                _autostart_switch(self.home, it["name"], bool(on))
            self.actions.note_undo({"type": "startup", "name": it["name"], "on": not bool(on)})
            return f"{it['name']} {'on' if on else 'off'} at startup"
        self.actions.propose("sys_startup", {"name": it.get("title") or it["name"], "on": bool(on),
                                             "command": it["command"]}, go)
        return WAITING

    def open_page(self, page: str) -> str:
        page = str(page or "").strip().lower()
        if page not in PAGES:
            raise WorkError("Unknown page. Pages: " + ", ".join(PAGES))
        win, gnome = PAGES[page]
        if self.platform == "win32":
            self._open(f"ms-settings:{win}")
        else:
            if not gnome or not self.which("gnome-control-center"):
                raise WorkError("This settings page can't be opened from Lanterna on this system.")
            quiet.spawn(["gnome-control-center", gnome])
        return f"Opened the {page} settings page."


# ---------------------------------------------------------------- helpers
def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _autostart_switch(home: Path, name: str, on: bool) -> None:
    """freedesktop autostart: a copy in ~/.config/autostart with Hidden=true turns it off."""
    user = home / ".config" / "autostart" / name
    src = user if user.exists() else Path("/etc/xdg/autostart") / name
    text = _read(src)
    if not text:
        raise WorkError(f"Can't read {name}.")
    text = re.sub(r"^Hidden=.*\n?", "", text, flags=re.M | re.I)
    text = re.sub(r"^X-GNOME-Autostart-enabled=.*\n?", "", text, flags=re.M | re.I)
    if not on:
        text = text.rstrip("\n") + "\nHidden=true\n"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(text, encoding="utf-8")


def _open_uri(uri: str) -> None:
    if not uri:
        return
    if sys.platform == "win32" and uri.startswith("ms-settings:"):
        os.startfile(uri)  # noqa: S606  (a fixed ms-settings: page)


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            return platform.processor()
    try:
        m = re.search(r"^model name\s*:\s*(.+)$", Path("/proc/cpuinfo").read_text(), re.M)
        return m.group(1).strip() if m else platform.processor()
    except OSError:
        return platform.processor()


def mem_free_gb() -> float:
    if sys.platform == "win32":
        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("t", "a", "tp", "ap", "tv", "av", "ae")]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        return m.a / 1024 ** 3 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else 0.0
    try:
        m = re.search(r"^MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)
        return int(m.group(1)) / 1024 ** 2 if m else 0.0
    except OSError:
        return 0.0


def disks() -> list[tuple[str, int, int]]:
    out = []
    if sys.platform == "win32":
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if mask & (1 << i):
                d = f"{chr(65 + i)}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(d) != 3:        # fixed disks only
                    continue
                try:
                    u = shutil.disk_usage(d)
                    out.append((d, u.total, u.free))
                except OSError:
                    pass
        return out
    for d in ("/", str(Path.home())):
        try:
            u = shutil.disk_usage(d)
            if not any(u.total == x[1] and u.free == x[2] for x in out):
                out.append((d, u.total, u.free))
        except OSError:
            pass
    return out


def uptime_hours() -> float:
    if sys.platform == "win32":
        return ctypes.windll.kernel32.GetTickCount64() / 3_600_000
    try:
        return float(Path("/proc/uptime").read_text().split()[0]) / 3600
    except (OSError, ValueError, IndexError):
        return 0.0


def battery() -> str:
    if sys.platform == "win32":
        class SPS(ctypes.Structure):
            _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("pct", ctypes.c_ubyte),
                        ("saver", ctypes.c_ubyte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
        s = SPS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.flag == 128 or s.pct == 255:
            return ""
        return f"{s.pct}%" + (", charging" if s.ac == 1 else "")
    for b in Path("/sys/class/power_supply").glob("BAT*"):
        cap, st = _read(b / "capacity").strip(), _read(b / "status").strip()
        if cap:
            return f"{cap}%" + (f", {st.lower()}" if st else "")
    return ""


# ---------------------------------------------------------------- tools
def system_tools(sy: System) -> list:
    from .tools import Tool, _obj
    s = {"type": "string"}
    card = "The user confirms it on a card, so don't ask in text first."
    return [
        Tool("pc_info", "This computer: system, processor, memory, graphics, free disk space, how long it has been on, "
             "battery. Use it when the user asks about their PC or why it is slow.", _obj({}), lambda: sy.info(), "💻"),
        Tool("pc_load", "What is using memory and processor right now (per program).", _obj({}), lambda: sy.load(), "📈"),
        Tool("pc_startup", "Programs that start together with the computer, and which are on or off.",
             _obj({}), lambda: sy.startup(), "🚀"),
        Tool("pc_startup_switch", "Turn a program's start with the computer off (or on again) — by its name from "
             "pc_startup. Reversible. " + card,
             _obj({"name": s, "on": {"type": "boolean"}}, ["name", "on"]),
             lambda name, on=False: sy.propose_startup(name, bool(on)), "🚀"),
        Tool("pc_power", "The power plans of this computer and which one is active.", _obj({}), lambda: sy.power(), "🔋"),
        Tool("pc_power_set", "Switch to another power plan (id or name from pc_power). " + card,
             _obj({"plan": s}, ["plan"]), lambda plan: sy.propose_power(plan), "🔋"),
        Tool("pc_theme", "Switch the system between the dark and light theme. " + card,
             _obj({"theme": {"type": "string", "enum": ["dark", "light"]}}, ["theme"]),
             lambda theme: sy.propose_theme(theme), "🌓"),
        Tool("pc_settings_page", "Open a page of the system Settings for the user (for things Lanterna doesn't change "
             "itself): " + ", ".join(PAGES) + ".",
             _obj({"page": {"type": "string", "enum": list(PAGES)}}, ["page"]), lambda page: sy.open_page(page), "⚙️"),
    ]
