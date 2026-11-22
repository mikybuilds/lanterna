"""Why doesn't it work, on Linux: the parts of fixit that differ from Windows.

Programs come from Steam (a game runs natively or through Proton), Heroic (Epic and GOG), Lutris, Flatpak and the
.desktop files of installed apps. A Windows game keeps its own folders (AppData, Documents) inside its Proton or Wine
prefix, so they are looked through the same way as on Windows. What the system noted: crashes (systemd-coredump, or
apport on Ubuntu), the kernel's lines about the graphics card and memory, and systemd-oomd. The areas: sound
(PipeWire or PulseAudio), internet (NetworkManager), printers (CUPS) and updates (dnf, apt, pacman, rpm-ostree).

Every command here is fixed and runs with LC_ALL=C, so its words are the same in every language. Looking only reads.
The fixes change this user's own settings only (the sound output and its volume, a restart of the user's own sound
service, the desktop's proxy, the default printer, the user's own print jobs): nothing that needs the computer's
password.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path

from .fixit import GB, GENERIC_EXE, MB, Program, _cut, _pick_name, _size, compact, vdf_tree
from .workspace import WAITING, WorkError

LC = {"LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}
HEROIC = (".config/heroic", ".var/app/com.heroicgameslauncher.hgl/config/heroic")
LUTRIS = ((".local/share/lutris/pga.db", (".config/lutris/games", ".local/share/lutris/games")),
          (".var/app/net.lutris.Lutris/data/lutris/pga.db", (".var/app/net.lutris.Lutris/config/lutris/games",
                                                            ".var/app/net.lutris.Lutris/data/lutris/games")))
DESKTOP_DIRS = ("usr/share/applications", "usr/local/share/applications", "var/lib/snapd/desktop/applications")
BIN_DIRS = ("usr/local/bin", "usr/bin", "bin", "usr/games", "usr/local/games", "snap/bin")
SYSTEM_TOPS = ("usr", "etc", "var", "boot", "proc", "sys", "dev", "bin", "sbin", "lib", "lib64", "lib32", "snap", "tmp",
               "srv")
STEAM_FLATPAK = "com.valvesoftware.Steam"
GPU_VENDORS = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel"}
MESA_DRIVERS = {"amdgpu", "radeon", "i915", "xe", "nouveau"}
WINDOWS_FS = {"ntfs": "NTFS", "ntfs3": "NTFS", "fuseblk": "NTFS", "exfat": "exFAT", "vfat": "FAT32", "msdos": "FAT"}
OVERLAYS = {"discord": "Discord", "obs": "OBS", "gamescope": "Gamescope", "mangohud": "MangoHud",
            "corectrl": "CoreCtrl (it can change the graphics card's clocks)",
            "lact": "LACT (it can change the graphics card's clocks)",
            "gwe": "GreenWithEnvy (it can change the NVIDIA card's clocks)"}
SIGNALS = {11: "SIGSEGV", 6: "SIGABRT", 4: "SIGILL", 7: "SIGBUS", 8: "SIGFPE", 5: "SIGTRAP", 31: "SIGSYS", 3: "SIGQUIT"}
SIGNAL_TEXT = {"SIGSEGV": "it touched memory it shouldn't (often a mod, an overlay, the graphics driver or damaged files)",
               "SIGABRT": "it stopped itself on an error it couldn't handle",
               "SIGILL": "an instruction this processor doesn't have (the program needs a newer processor)",
               "SIGBUS": "a memory or file error (often a file it uses changed, or the disk is full)",
               "SIGFPE": "a calculation error inside it",
               "SIGTRAP": "its own check failed",
               "SIGSYS": "a blocked system call (often a sandbox)"}
GPU_ERR = re.compile(r"(?:amdgpu|radeon|nouveau|NVRM|i915|\bxe\b).{0,200}?(?:ring \S+ timeout|timed? ?out|GPU HANG|"
                     r"\bhang\b|GPU reset|reset (?:begin|succeeded|failed)|\bXid\b|fallen off the bus|page fault)", re.I)
OOM_LINE = re.compile(r"Out of memory: Killed process \d+ \(([^)]*)\)")
CUPS_ALERTS = (("offline", "offline"), ("media-jam", "paper is jammed"), ("media-empty", "no paper"),
               ("media-needed", "no paper"), ("toner-empty", "no toner or ink"),
               ("marker-supply-empty", "no toner or ink"), ("toner-low", "little toner or ink"),
               ("marker-supply-low", "little toner or ink"), ("door-open", "a door is open"),
               ("cover-open", "a door is open"), ("output-area-full", "the output tray is full"))
LPSTAT_KEYS = {"Form mounted", "Content types", "Printer types", "Description", "Alerts", "Location", "Connection",
               "Interface", "On fault", "After fault", "Users allowed", "Forms allowed", "Banner required",
               "Charset sets", "Default pitch", "Default page size", "Default port settings"}
BUSY = {"dnf", "dnf5", "dnf-3", "yum", "rpm", "apt", "apt-get", "aptitude", "dpkg", "unattended-upgr", "pacman",
        "zypper", "rpm-ostree"}
UPDATE_LOGS = ("var/log/dnf5.log", "var/log/dnf.log", "var/log/apt/history.log", "var/log/apt/term.log",
               "var/log/pacman.log")
UPDATE_ERRORS = [
    (r"no space left on device|not enough free space|needs \S+ more space", "the disk is full"),
    (r"curl error \(6\)|could not resolve host|couldn't resolve host|temporary failure resolving",
     "there was no internet (or site names didn't work) during the update"),
    (r"gpg check failed|no_pubkey|public key .{0,80}is not installed|signatures? (?:couldn't|could not|were not) "
     r"(?:be )?verified|expkeysig|invalid signature", "a repository's signing key is missing or has expired"),
    (r"could not get lock|is held by process|waiting for (?:cache )?lock|unable to lock database",
     "another update was running at the same time"),
    (r"dpkg was interrupted|dpkg --configure -a", "an earlier update was interrupted: 'sudo dpkg --configure -a' "
                                                  "finishes it"),
    (r"conflicting requests|nothing provides|cannot install both|problem with installed package|none of the "
     r"providers can be installed|unmet dependencies|held broken packages",
     "packages conflict (often an extra repository is behind the system, e.g. after a system upgrade)"),
    (r"curl error|failed to download|cannot download|all mirrors were (?:already )?tried|status code: 40[34]|"
     r"failed to fetch|cannot retrieve repository|failed to synchronize cache|failed to retrieve",
     "a repository didn't answer or has moved (often an extra repository after a system upgrade)"),
    (r"transaction check error|conflicts between attempted installs|trying to overwrite", "two packages want the same "
                                                                                          "file"),
    (r"sub-process /usr/bin/dpkg returned an error code|error processing package", "a package failed to install"),
    (r"failed to commit transaction|failed to prepare transaction|transaction test error|transaction failed",
     "the update couldn't be applied"),
]


# ---------------------------------------------------------------- small helpers
def cmd(fx, args: list[str], timeout: float = 15) -> tuple[int, str]:
    """A fixed command with English output: its words are what this code reads."""
    return fx.run(list(args), timeout=timeout, env={**os.environ, **LC})


def _read(p: Path, limit: int = 64 * 1024) -> str:
    try:
        with open(p, "rb") as f:
            return f.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def _tail(p: Path, size: int = 256 * 1024) -> str:
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - size))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _terse(line: str) -> list[str]:
    """One line of nmcli -t: fields split by ':', a ':' inside a field written as '\\:'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur, esc = cur + ch, False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def _stamp(line: str) -> str:
    """'2026-11-20T21:04:11+02:00 host kernel: …' → '2026-11-20 21:04'."""
    return line[:16].replace("T", " ") if re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d", line) else ""


def _msg(line: str) -> str:
    """The message of a journal line, without its time, the computer's name and the unit."""
    return re.sub(r"^\S+\s+\S+\s+[^:\s]+(?:\[\d+\])?:\s*", "", line).strip()


def _vkey(v: str) -> list:
    return [(0, int(x)) if x.isdigit() else (1, x) for x in re.split(r"(\d+)", v) if x]


def os_release(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in (root / "etc" / "os-release", root / "usr" / "lib" / "os-release"):
        for line in _read(f).splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() and not k.startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
        if out:
            break
    return out


def mounts(root: Path) -> list[tuple[str, str]]:
    """(mount point, file system) of every mounted disk."""
    out = []
    for line in _read(root / "proc" / "self" / "mounts", 512 * 1024).splitlines():
        f = line.split()
        if len(f) >= 3:
            out.append((f[1].replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\"), f[2]))
    return out


def fs_type(root: Path, path: str) -> str:
    """The file system of the disk a path is on ('ntfs3', 'ext4'…)."""
    p = Path(path).as_posix()
    best, kind = "", ""
    for mnt, fs in mounts(root):
        m = mnt.rstrip("/")
        if (p == mnt or p.startswith(m + "/")) and len(mnt) >= len(best):
            best, kind = mnt, fs
    return kind


# ---------------------------------------------------------------- what runs now
_FLATPAK_SCOPE = re.compile(r"app-flatpak-([A-Za-z0-9_.-]+?)-\d+\.scope")


def processes(proc: Path = Path("/proc")) -> list[tuple[str, str]]:
    """(name, path) of what runs now. A Windows program under Wine or Proton also comes with the path its command line
    gives (Z:\\home\\… → /home/…); a game Steam started as ("steam game", "steam-app:<appid>"), a Flatpak app as
    (its id, "flatpak:<id>")."""
    out: list[tuple[str, str]] = []
    try:
        pids = [e.name for e in os.scandir(proc) if e.name.isdigit()]
    except OSError:
        return out
    for pid in pids:
        d = proc / pid
        try:
            comm = (d / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        try:
            exe = os.readlink(d / "exe")
        except OSError:
            exe = ""
        out.append((comm, exe.removesuffix(" (deleted)")))
        try:
            args = [a.decode("utf-8", "replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a][:60]
        except OSError:
            args = []
        if args and re.match(r"^[zZ]:\\", args[0]):                 # Wine shows the Windows path: Z: is /
            unix = "/" + args[0][3:].replace("\\", "/")
            out.append((unix.rsplit("/", 1)[-1], unix))
        elif args and re.match(r"^[a-yA-Y]:\\", args[0]):           # C: is in its prefix: known by its name only
            out.append((args[0].rsplit("\\", 1)[-1], ""))
        if "SteamLaunch" in args:
            app = next((a.split("=", 1)[1] for a in args if a.startswith("AppId=")), "")
            if app.isdigit():
                out.append(("steam game", f"steam-app:{app}"))
            # the game comes last: before it are Steam's runtime and Proton (they are in steamapps/common too)
            game = next((a for a in reversed(args[1:]) if a.startswith("/") and "/steamapps/common/" in a and
                         not re.search(r"/steamapps/common/(?:Proton|SteamLinuxRuntime)", a)), "")
            if game:
                out.append((game.rsplit("/", 1)[-1], game))
        m = _FLATPAK_SCOPE.search(_read(d / "cgroup", 4096))
        if m:
            out.append((m.group(1), f"flatpak:{m.group(1)}"))
    return out


# ---------------------------------------------------------------- the installed programs
def steam_prefix(game_folder: str, appid: str) -> str:
    """A Windows game's Proton prefix: steamapps/compatdata/<appid>/pfx, next to the game's library."""
    if not game_folder or not appid:
        return ""
    pfx = Path(game_folder).parent.parent / "compatdata" / appid / "pfx"
    return str(pfx) if (pfx / "drive_c").is_dir() else ""


def steam_home(base: Path | None) -> Path | None:
    """Flatpak Steam keeps its games' Linux home folders (.config, .local/share) inside its own folder."""
    if base is None or STEAM_FLATPAK not in base.parts:
        return None
    return Path(*base.parts[:base.parts.index(STEAM_FLATPAK) + 1])


def heroic_games(home: Path) -> list[Program]:
    out = []
    for rel in HEROIC:
        base = home / rel
        if not base.is_dir():
            continue
        epic = _json(base / "legendaryConfig" / "legendary" / "installed.json")
        for app, g in (epic.items() if isinstance(epic, dict) else []):
            if isinstance(g, dict) and g.get("install_path") and not g.get("is_dlc"):
                out.append(Program(str(g.get("title") or app), "heroic-epic", str(g["install_path"]), appid=str(app),
                                   version=str(g.get("version") or ""), prefix=_heroic_prefix(base, str(app), home)))
        gog = _json(base / "gog_store" / "installed.json")
        items = gog.get("installed") if isinstance(gog, dict) else gog
        for g in items if isinstance(items, list) else []:
            if isinstance(g, dict) and g.get("install_path"):
                app = str(g.get("appName") or "")
                out.append(Program(Path(str(g["install_path"])).name, "heroic-gog", str(g["install_path"]), appid=app,
                                   version=str(g.get("version") or ""), prefix=_heroic_prefix(base, app, home)))
    return out


def _heroic_prefix(base: Path, app: str, home: Path) -> str:
    cfg = _json(base / "GamesConfig" / f"{app}.json") if app else None
    node = cfg.get(app) if isinstance(cfg, dict) else None
    pre = str(node.get("winePrefix") or "") if isinstance(node, dict) else ""
    return str(home / pre[2:]) if pre.startswith("~/") else pre


def lutris_games(home: Path) -> list[Program]:
    import sqlite3
    out = []
    for db, cfgs in LUTRIS:
        f = home / db
        if not f.is_file():
            continue
        try:
            con = sqlite3.connect(f.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1)
            try:
                rows = con.execute("SELECT name, slug, runner, directory, configpath FROM games WHERE installed = 1"
                                   ).fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            continue
        for name, slug, runner, directory, configpath in rows:
            yml = next((home / c / f"{configpath}.yml" for c in cfgs if (home / c / f"{configpath}.yml").is_file()),
                       None) if configpath else None
            exe, prefix = _lutris_config(yml) if yml else ("", "")
            if prefix and exe and not exe.startswith("/"):
                exe = str(Path(prefix) / exe)
            folder = str(directory or "")
            if exe and (not folder or (prefix and os.path.normpath(folder) == os.path.normpath(prefix))):
                folder = str(Path(exe).parent)                 # a Wine game's directory is often its whole prefix
            out.append(Program(str(name or slug or ""), "lutris", folder, appid=str(slug or ""), exe=exe,
                               prefix=prefix if str(runner or "") == "wine" else ""))
    return out


def _lutris_config(f: Path) -> tuple[str, str]:
    text = _read(f)

    def key(k: str) -> str:
        m = re.search(rf"(?m)^\s+{k}:\s*(.+?)\s*$", text)
        return m.group(1).strip("'\"") if m else ""
    return key("exe"), key("prefix")


def desktop_entry(f: Path) -> dict[str, str]:
    """The [Desktop Entry] keys of a .desktop file, in lower case (plain keys only, not Name[uk])."""
    out: dict[str, str] = {}
    section = ""
    for line in _read(f, 256 * 1024).splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s
        elif section == "[Desktop Entry]" and "=" in s and not s.startswith("#"):
            k, v = s.split("=", 1)
            if "[" not in k:
                out.setdefault(k.strip().lower(), v.strip())
    return out


def flatpak_apps(root: Path, home: Path) -> list[Program]:
    out: dict[str, Program] = {}
    for base in (home / ".local" / "share" / "flatpak", root / "var" / "lib" / "flatpak"):
        try:
            ids = sorted(e.name for e in os.scandir(base / "app") if e.is_dir())
        except OSError:
            continue
        for app in ids:
            if app in out or app.endswith((".BaseApp", ".Debug", ".Locale", ".Sources")):
                continue
            name = desktop_entry(base / "exports" / "share" / "applications" / f"{app}.desktop").get("name")
            out[app] = Program(name or app.rsplit(".", 1)[-1], "flatpak", "", appid=app)
    return list(out.values())


def exec_path(ex: str, root: Path, home: Path) -> str:
    """The program file a .desktop file starts (its Exec line, without env, settings and %u)."""
    try:
        words = shlex.split(ex)
    except ValueError:
        words = ex.split()
    words = [w for w in words if not w.startswith("%")]
    while words and (words[0] == "env" or words[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
        words.pop(0)
    if not words:
        return ""
    w = words[0]
    if Path(w).name in ("gapplication", "gio") and len(words) > 2 and words[1] == "launch":
        # started through D-Bus (GNOME's Maps, Weather…): the service file names the program
        m = re.search(r"(?m)^Exec=(\S+.*)$", _read(root / "usr" / "share" / "dbus-1" / "services" / f"{words[2]}.service"))
        return exec_path(m.group(1), root, home) if m and Path(m.group(1).split()[0]).name not in ("gapplication", "gio") \
            else ""
    if Path(w).name in ("sh", "bash", "dash", "xdg-open", "dbus-send"):     # a shell or a helper: not the program
        return ""
    if w.startswith("~/"):
        return str(home / w[2:])
    if w.startswith("/"):
        return str(root / w.lstrip("/"))
    for b in BIN_DIRS:
        if (root / b / w).exists():
            return str(root / b / w)
    return str(home / ".local" / "bin" / w) if (home / ".local" / "bin" / w).exists() else ""


def app_folder(exe: str, root: Path, home: Path) -> str:
    """The program's own folder, when it has one (/opt/<name>, or a folder in the home folder); '' for one of the
    system's (/usr/bin)."""
    if not exe:
        return ""
    p = Path(exe)
    try:
        rel = p.relative_to(root / "opt")
        return str(root / "opt" / rel.parts[0]) if len(rel.parts) > 1 else ""
    except ValueError:
        pass
    try:
        p.relative_to(home)
    except ValueError:
        return ""
    if p.parent in (home, home / ".local" / "bin", home / "bin", home / "Applications", home / "Desktop",
                    home / "Downloads"):
        return ""
    return str(p.parent)


def desktop_apps(root: Path, home: Path) -> list[Program]:
    out = []
    seen: set[str] = set()
    for d in [home / ".local" / "share" / "applications"] + [root / x for x in DESKTOP_DIRS]:
        try:
            files = sorted(d.glob("*.desktop"))[:800]
        except OSError:
            continue
        for f in files:
            if f.name in seen:                                   # the user's own copy hides the system's
                continue
            seen.add(f.name)
            e = desktop_entry(f)
            ex = e.get("exec", "")
            if (not e.get("name") or e.get("type", "Application") != "Application" or
                    e.get("nodisplay", "").lower() == "true" or e.get("hidden", "").lower() == "true" or
                    re.search(r"steam://|heroic://|lutris:|\bflatpak run\b", ex)):   # games of a launcher come from it
                continue
            exe = exec_path(ex, root, home)
            snap = re.search(r"[\\/]snap[\\/]bin[\\/]([\w.-]+)$", exe)
            if snap:
                out.append(Program(e["name"], "snap", "", appid=snap.group(1), exe=exe))
            else:
                out.append(Program(e["name"], "app", app_folder(exe, root, home), exe=exe))
    return out


def programs(fx) -> list:
    """The sources of the installed programs on Linux, in order (Steam's games first)."""
    return [lambda: heroic_games(fx.home), lambda: lutris_games(fx.home), lambda: flatpak_apps(fx.root, fx.home),
            lambda: desktop_apps(fx.root, fx.home)]


# ---------------------------------------------------------------- its folders
def prefix_user(prefix: str, user: str = "") -> Path | None:
    """The Windows user folder in a Proton or Wine prefix (drive_c/users/steamuser, or the user's own name)."""
    if not prefix:
        return None
    for c in (Path(prefix) / "drive_c", Path(prefix) / "pfx" / "drive_c"):
        users = c / "users"
        if not users.is_dir():
            continue
        for name in ("steamuser", user):
            if name and (users / name).is_dir():
                return users / name
        try:
            kids = sorted(x for x in users.iterdir() if x.is_dir() and x.name.lower() != "public")
        except OSError:
            kids = []
        if kids:
            return kids[0]
    return None


def bases(fx, p) -> list[tuple[str, Path, str]]:
    """Where its own folders may be: (label, folder, how). how: 'nested' = a folder named like it, or one level
    deeper; 'flat' = a folder named like it; 'self' = that folder itself."""
    out: list[tuple[str, Path, str]] = []
    users = prefix_user(p.prefix, fx.user)
    if users is not None:                          # a Windows game: its AppData and Documents are in its prefix
        docs = users / "Documents" if (users / "Documents").is_dir() else users / "My Documents"
        out += [("local", users / "AppData" / "Local", "nested"), ("roaming", users / "AppData" / "Roaming", "nested"),
                ("locallow", users / "AppData" / "LocalLow", "nested"), ("mygames", docs / "My Games", "flat"),
                ("documents", docs, "flat"), ("saved", users / "Saved Games", "nested")]
    if p.source == "flatpak":
        app = fx.home / ".var" / "app" / p.appid
        return out + [("config", app / "config", "self"), ("data", app / "data", "self"), ("cache", app / "cache", "self")]
    if p.source == "snap":
        return out + [("data", fx.home / "snap" / p.appid / "current", "self")]
    homes = [(fx.home, ".config", ".local/share", ".cache")]
    sh = steam_home(fx.steam_base()) if p.source == "steam" else None
    if sh is not None:
        homes += [(sh, ".config", ".local/share", ".cache"), (sh, "config", "data", "cache")]
    for h, conf, data, cache in homes:
        out += [("config", h / conf, "nested"), ("config", h / conf / "unity3d", "nested"), ("data", h / data, "nested"),
                ("cache", h / cache, "flat")]
    return out


def driver_caches(fx) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for label, rels in (("mesa_cache", (".cache/mesa_shader_cache_db", ".cache/mesa_shader_cache")),
                        ("nvidia_cache", (".cache/nvidia/GLCache", ".nv/GLCache"))):
        for rel in rels:
            if (fx.home / rel).is_dir():
                out[label] = fx.home / rel
                break
    return out


def proton_log(fx, p) -> Path | None:
    """The log Proton writes when the game starts with PROTON_LOG=1."""
    if p is None or p.source != "steam" or not p.appid:
        return None
    for h in [fx.home] + [x for x in [steam_home(fx.steam_base())] if x is not None]:
        f = h / f"steam-{p.appid}.log"
        if f.is_file():
            return f
    return None


def bad_root(fx, p: Path) -> bool:
    """A folder too big or too important to be one program's folder (the system's, the home folder…)."""
    try:
        p = p.resolve()
        root, h = fx.root.resolve(), fx.home.resolve()
    except OSError:
        return True
    if p.parent == p:
        return True
    whole = {root, root / "opt", root / "home", root / "media", root / "mnt", root / "run" / "media", h} | {
        h / x for x in (".local", ".local/share", ".local/bin", ".config", ".cache", ".var", ".var/app", "Applications",
                        "Games", "bin", "Desktop", "Documents", "Downloads", "snap")}
    if p in whole:
        return True
    try:
        return any(p.is_relative_to(root / t) for t in SYSTEM_TOPS) or p.is_relative_to(fx.data_dir().resolve())
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- what the system noted
def facts(fx) -> dict:
    return {"gpu": gpus(fx), "dumps": coredumps(fx), "kernel": journal(fx, ["-k", "-p", "0..5"]),
            "oomd": [x for x in journal(fx, ["-u", "systemd-oomd"]) if "Killed " in x]}


def journal(fx, args: list[str]) -> list[str]:
    code, out = cmd(fx, ["journalctl", *args, "--since=-7d", "--no-pager", "-q", "-o", "short-iso", "-n", "3000"], 20)
    return [x for x in out.splitlines() if re.match(r"\d{4}-\d\d-\d\dT", x)] if code == 0 else []


def gpu_name(vendor: str, device: str) -> str:
    m = re.search(r"\[([^\]]+)\]\s*$", device)
    short = ("NVIDIA" if "nvidia" in vendor.lower() else "AMD" if re.search(r"\bamd\b|\bati\b|advanced micro", vendor, re.I)
             else "Intel" if "intel" in vendor.lower() else vendor)
    return f"{short} {m.group(1) if m else device}".strip()


def package_version(fx, names: tuple[str, ...]) -> str:
    """The version of an installed package, by the system's own package tool."""
    for tool in (["rpm", "-q", "--qf", "%{VERSION}\\n"], ["dpkg-query", "-W", "-f=${Version}\\n"], ["pacman", "-Q"]):
        for n in names:
            code, out = cmd(fx, tool + [n], 10)
            if code == 127:
                break                                       # this package tool isn't here
            if code == 0 and out.strip():
                v = out.strip().splitlines()[0].split()[-1]
                return re.sub(r"^\d+:", "", v).split("-")[0].split("+")[0]
    return ""


def gpus(fx) -> dict:
    cards = []
    try:
        dirs = sorted(x for x in (fx.root / "sys" / "class" / "drm").iterdir() if re.fullmatch(r"card\d+", x.name))
    except OSError:
        dirs = []
    for c in dirs:
        ue = dict(x.split("=", 1) for x in _read(c / "device" / "uevent").splitlines() if "=" in x)
        vendor = ue.get("PCI_ID", "").split(":")[0].lower()
        if vendor:                                          # not a USB display adapter or a virtual one
            cards.append({"vendor": GPU_VENDORS.get(vendor, vendor), "driver": ue.get("DRIVER", ""),
                          "slot": ue.get("PCI_SLOT_NAME", ""), "name": ""})
    if cards:
        code, text = cmd(fx, ["lspci", "-mm"], 10)
        for line in text.splitlines() if code == 0 else []:
            try:
                f = shlex.split(line)
            except ValueError:
                continue
            if len(f) >= 4 and re.search(r"VGA|3D|Display", f[1]):
                for c in cards:
                    if c["slot"] and c["slot"].endswith(f[0]):
                        c["name"] = gpu_name(f[2], f[3])
    m = re.search(r"Kernel Module(?: for \S+)?\s+(\d+\.\d+(?:\.\d+)?)", _read(fx.root / "proc" / "driver" / "nvidia" /
                                                                            "version"))
    mesa = package_version(fx, ("mesa-dri-drivers", "libgl1-mesa-dri", "mesa")) if any(
        c["driver"] in MESA_DRIVERS for c in cards) else ""
    return {"cards": cards, "nvidia": m.group(1) if m else "", "mesa": mesa}


def coredumps(fx) -> list[dict]:
    """The crashes systemd-coredump (or Ubuntu's apport) kept from the last 30 days: {exe, sig, t}."""
    code, out = cmd(fx, ["coredumpctl", "--json=short", "--no-pager", "-q", "--since=-30d", "list"], 20)
    if code == 127:
        return _apport(fx)
    found: list[dict] = []
    try:
        data = json.loads(out[out.find("["):]) if code == 0 and "[" in out else None
    except ValueError:
        data = None
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict) or not d.get("exe"):
                continue
            sig, t = d.get("sig"), d.get("time")
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(t / 1e6)) if isinstance(t, (int, float)) else \
                str(t or "")[:16]
            found.append({"exe": str(d["exe"]), "sig": SIGNALS.get(sig, f"signal {sig}") if isinstance(sig, int)
                          else str(sig or ""), "t": when})
        return found
    code, out = cmd(fx, ["coredumpctl", "--no-pager", "--no-legend", "--since=-30d", "list"], 20)
    for line in out.splitlines() if code == 0 else []:
        m = re.match(r"^\w{3} (\d{4}-\d\d-\d\d \d\d:\d\d):\d\d \S+\s+\d+\s+\d+\s+\d+\s+(SIG\w+|\d+)\s+\S+\s+(.+?)\s+\S+\s*$",
                     line)
        if m:
            sig = m.group(2)
            found.append({"exe": m.group(3), "sig": SIGNALS.get(int(sig), f"signal {sig}") if sig.isdigit() else sig,
                          "t": m.group(1)})
    return found


def _apport(fx) -> list[dict]:
    found = []
    for f in sorted((fx.root / "var" / "crash").glob("*.crash"))[:60]:
        try:
            if fx.now() - f.stat().st_mtime > 30 * 86400:
                continue
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        except OSError:
            continue
        head = _read(f, 16 * 1024)
        exe, sig = re.search(r"(?m)^ExecutablePath: (.+)$", head), re.search(r"(?m)^Signal: (\d+)$", head)
        if exe:
            found.append({"exe": exe.group(1).strip(), "sig": SIGNALS.get(int(sig.group(1)), f"signal {sig.group(1)}")
                          if sig else "", "t": when})
    return found


def crash_lines(fx, facts_: dict, p, exes: set[str], scan=None) -> list[str]:
    folder = Path(p.folder).as_posix().rstrip("/") + "/" if p.folder else ""
    own = {x for x in exes if x not in GENERIC_EXE}
    if p.exe:
        own |= {Path(p.exe).name.lower(), Path(p.exe).stem.lower()}
    files = {Path(r).name.lower() for r in (scan.exes if scan else [])[:60]}      # hollow_knight.x86_64

    def ours(exe: str) -> bool:
        e = Path(exe).as_posix()
        return bool((folder and e.startswith(folder)) or (p.exe and e == Path(p.exe).as_posix())
                    or Path(e).name.lower() in own or Path(e).stem.lower() in own)
    groups: dict[tuple, list] = {}
    for d in facts_.get("dumps") or []:
        if ours(str(d.get("exe") or "")):
            g = groups.setdefault((Path(d["exe"]).name, d.get("sig") or ""), [0, ""])
            g[0] += 1
            g[1] = max(g[1], str(d.get("t") or ""))
    out = []
    for (name, sig), (n, last) in sorted(groups.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True):
        what = SIGNAL_TEXT.get(sig, "")
        out.append(f"{name} crashed {n}× (last {last}): {sig or 'a crash'}" + (f" — {what}" if what else ""))
    short = {x[:15] for x in own | files}                  # the kernel writes a program's name cut to 15 letters
    ooms: list[str] = [_stamp(x) for x in facts_.get("kernel") or []
                       if (m := OOM_LINE.search(x)) and m.group(1).lower()[:15] in short]
    if ooms:
        out.append(f"! Linux ran out of memory and stopped it ({len(ooms)}×, last {ooms[-1]}): close other programs "
                   "while it runs; more memory or a bigger swap helps.")
    key = compact(p.name)[:12]
    killed = []
    for x in facts_.get("oomd") or []:
        m = re.search(r"Killed (\S+)", x)
        scope = (m.group(1) if m else "").lower()
        if (p.source == "steam" and "steam" in scope) or (p.source == "flatpak" and p.appid and
                                                          f"app-flatpak-{p.appid.lower()}" in scope) or \
                (len(key) >= 4 and key in compact(scope)):
            killed.append(_stamp(x))
    if killed:
        out.append(f"! systemd-oomd closed {'Steam with the game' if p.source == 'steam' else 'it'} when memory ran low "
                   f"({len(killed)}×, last {killed[-1]}): close other programs while it runs (the browser too); more "
                   "memory or a bigger swap helps.")
    return out[:8]


def gpu_lines(fx, facts_: dict, game: bool = True) -> list[str]:
    """The graphics cards, their drivers, hangs and memory. game: for a game (for another program a second card or
    NVIDIA's slow open driver is seldom the cause: they are only mentioned)."""
    g = facts_.get("gpu") or {}
    cards = g.get("cards") or []
    out = []
    for c in cards:
        name, drv = c.get("name") or f"{c.get('vendor')} graphics card", c.get("driver") or ""
        if c.get("vendor") == "NVIDIA" and drv in ("nouveau", ""):
            how = "the open nouveau driver" if drv else "no driver"
            if game or len(cards) == 1:
                out.append(f"! {name}: it runs on {how}, so games run very slowly or not at all. NVIDIA's own driver "
                           "fixes it (Fedora: from RPM Fusion; Ubuntu: Software & Updates → Additional Drivers). "
                           "Installing it needs the computer's password, so the user does it.")
            else:
                out.append(f"- {name}: it runs on {how}; that matters for games and 3D, less for other programs.")
            continue
        if not drv:
            out.append(f"! {name}: no driver is loaded for it.")
            continue
        ver = g.get("nvidia") if drv == "nvidia" else g.get("mesa") if drv in MESA_DRIVERS else ""
        what = "NVIDIA's driver" if drv == "nvidia" else f"the {drv} driver (Mesa)" if drv in MESA_DRIVERS else \
            f"the {drv} driver"
        out.append(f"Graphics: {name}, {what}" + (f" {ver}" if ver else ""))
    if game and len(cards) > 1 and any(c.get("vendor") == "NVIDIA" for c in cards):
        out.append("- Two graphics cards: a game may run on the weaker built-in one. GNOME: right-click the app → Launch "
                   "using Discrete Graphics Card; Steam: the launch option __NV_PRIME_RENDER_OFFLOAD=1 "
                   "__GLX_VENDOR_LIBRARY_NAME=nvidia %command%.")
    lines = [x for x in facts_.get("kernel") or [] if GPU_ERR.search(x)]
    times = sorted({_stamp(x) for x in lines})
    if lines:
        out.append(f"! The graphics card hung or was reset in the last 7 days ({len(times)}×, last {times[-1]}): "
                   f"{_cut(_msg(lines[-1]), 150).rstrip('.!')}. Usually the driver, an overclock or the card's "
                   "power; if it happens with one game, lower its settings (or try another Proton version).")
    ooms = [m.group(1) for x in facts_.get("kernel") or [] if (m := OOM_LINE.search(x))]
    if ooms:
        out.append(f"- Linux ran out of memory {len(ooms)}× this week (it stopped: {', '.join(sorted(set(ooms))[:5])}).")
    return out


def compat_tool(fx, appid: str) -> tuple[str, bool]:
    """(the Proton version Steam runs the game with, chosen for this game). '' = Steam's default."""
    base = fx.steam_base()
    if not base or not appid:
        return "", False
    node = vdf_tree(_read(base / "config" / "config.vdf", 8 * MB))
    for k in ("installconfigstore", "software", "valve", "steam", "compattoolmapping"):
        node = node.get(k, {}) if isinstance(node, dict) else {}
    own = node.get(appid) if isinstance(node, dict) else None
    if isinstance(own, dict) and own.get("name"):
        return str(own["name"]), True
    default = node.get("0") if isinstance(node, dict) else None
    return (str(default.get("name") or "") if isinstance(default, dict) else ""), False


def tool_name(name: str) -> str:
    """proton_9 → Proton 9, proton_experimental → Proton Experimental (others as they are)."""
    m = re.fullmatch(r"proton_(\w+)", name)
    return "Proton " + m.group(1).replace("_", " ").title() if m else name


def install_line(fx, p) -> str:
    """A program with no folder of its own: where its files are."""
    if p.source in ("flatpak", "snap"):
        return (f"A {'Flatpak' if p.source == 'flatpak' else 'Snap'} app ({p.appid}): its installed files are "
                f"{'Flatpak' if p.source == 'flatpak' else 'Snap'}'s own (fix_verify says how to "
                f"{'repair them' if p.source == 'flatpak' else 'go back to the version before'}).")
    if not p.exe:
        return "Its install folder isn't known."
    try:
        Path(p.exe).relative_to(fx.home)
        return f"Its program file: {p.exe}"
    except ValueError:
        return (f"A program from the system's packages ({p.exe}): its installed files aren't changed (fix_verify says "
                "how to install it again).")


def program_lines(fx, p, scan) -> list[str]:
    """Linux only: how the game runs (Proton), its anti-cheat, a Windows disk, Proton's log."""
    out = []
    windows = bool(p.prefix) or bool(scan and any(x.lower().endswith(".exe") for x in scan.exes))
    if p.source == "steam":
        tool, own = compat_tool(fx, p.appid)
        if windows or own:
            out.append(f"Runs through {tool_name(tool) if tool else 'Proton'}" +
                       (" (chosen for this game in Steam)" if own else " (Steam's default)" if tool else "") +
                       ". Another version: Steam → the game → Properties → Compatibility.")
        else:
            out.append("A Linux version of the game (no Proton).")
    elif p.source.startswith("heroic") or (p.source == "lutris" and p.prefix):
        out.append("A Windows game: it runs through Wine or Proton (the launcher's game settings choose the version).")
    if scan and scan.anticheat:
        out.append(f"It has {' and '.join(sorted(scan.anticheat))}: online play works on Linux only when the game's "
                   "makers allow it (ProtonDB or areweanticheatyet.com say).")
    kind = fs_type(fx.root, p.folder) if p.folder else ""
    if kind in WINDOWS_FS:
        out.append(f"! It is on a disk with {WINDOWS_FS[kind]} (a Windows file system): games through Proton often don't "
                   "start, crash or lose saves there. " + ("Steam can move it to a Linux disk: Properties → Installed "
                                                           "Files → Move install folder." if p.source == "steam" else
                                                           "Move it to a Linux disk."))
    if p.source == "steam" and windows and proton_log(fx, p) is None:
        out.append("- For more details: Steam → the game → Properties → Launch options: PROTON_LOG=1 %command% — then "
                   f"Proton writes ~/steam-{p.appid}.log, and fix_check reads it.")
    return out


# ---------------------------------------------------------------- sound
def parse_pa(text: str) -> list[dict]:
    """pactl list sinks / sources: {kind, name, description, state, mute, volume, active port, ports}."""
    items: list[dict] = []
    cur: dict | None = None
    in_ports = False
    for line in text.splitlines():
        m = re.match(r"^(Sink|Source) #(\d+)", line)
        if m:
            cur = {"kind": m.group(1).lower(), "id": m.group(2), "ports": {}}
            items.append(cur)
            in_ports = False
            continue
        if cur is None:
            continue
        if re.match(r"^\t\S", line):
            s = line.strip()
            key, _, val = s.partition(":")
            key, val = key.strip().lower(), val.strip()
            in_ports = key == "ports"
            if key in ("name", "description", "state", "mute", "active port", "driver"):
                cur[key] = val
            elif key == "volume":
                v = re.search(r"(\d+)%", val)
                cur["volume"] = int(v.group(1)) if v else None
        elif in_ports and line.startswith("\t\t"):
            pm = re.match(r"^\t\t([^:]+):\s*(.*)$", line)
            if pm:
                cur["ports"][pm.group(1).strip()] = "not available" not in pm.group(2)
    return items


def _dev_name(d: dict) -> str:
    return str(d.get("description") or d.get("name") or "?")


def _dummy(d: dict) -> bool:
    return str(d.get("name", "")).startswith("auto_null") or "dummy output" in _dev_name(d).lower()


def _audio(fx) -> dict:
    code, info = cmd(fx, ["pactl", "info"])
    out = {"ok": code == 0, "missing": code == 127, "server": "", "sinks": [], "sources": [], "sink": "", "source": ""}
    if code == 0:
        m = re.search(r"(?m)^Server Name:\s*(.+)$", info)
        out["server"] = m.group(1).strip() if m else ""
        for k, label in (("sink", "Default Sink"), ("source", "Default Source")):
            m = re.search(rf"(?m)^{label}:\s*(\S+)", info)
            out[k] = m.group(1) if m else ""
        out["sinks"] = parse_pa(cmd(fx, ["pactl", "list", "sinks"])[1])
        out["sources"] = [s for s in parse_pa(cmd(fx, ["pactl", "list", "sources"])[1])
                          if not str(s.get("name", "")).endswith(".monitor")]
    return out


def _units(fx) -> dict[str, str]:
    units = ["pipewire.service", "pipewire-pulse.service", "wireplumber.service", "pulseaudio.service"]
    code, out = cmd(fx, ["systemctl", "--user", "is-active", *units])
    states = [x.strip() for x in out.splitlines() if x.strip()] if code != 127 else []
    return dict(zip(units, states)) if len(states) == len(units) else {}


def _pipewire(a: dict, units: dict[str, str]) -> bool:
    if a["server"]:
        return "pipewire" in a["server"].lower()
    return units.get("pulseaudio.service") != "active"


def sound(fx) -> list:
    a, units = _audio(fx), _units(fx)
    cards_text = _read(fx.root / "proc" / "asound" / "cards")
    cards = [x.split(" - ", 1)[1].strip() for x in cards_text.splitlines() if re.match(r"^\s*\d+ \[", x) and " - " in x]
    pw = _pipewire(a, units)
    wanted = ["pipewire.service", "pipewire-pulse.service", "wireplumber.service"] if pw else ["pulseaudio.service"]
    found, lines = [], []
    if units:
        lines.append(f"- Sound service: {'PipeWire' if pw else 'PulseAudio'} (" +
                     ", ".join(f"{u.removesuffix('.service')} {units.get(u, '?')}" for u in wanted) + ")")
        bad = [u.removesuffix(".service") for u in wanted if units.get(u) in ("failed", "inactive")]
        if bad:
            found.append(f"! The sound service isn't running ({', '.join(bad)}): there is no sound without it. "
                         "fix_system sound_restart starts it again.")
    if a["missing"]:
        lines.append("- pactl isn't installed, so Lanterna can't see the outputs (it comes with the package "
                     "pulseaudio-utils, or pipewire-pulseaudio).")
    elif not a["ok"]:
        found.append("! The sound service doesn't answer: fix_system sound_restart starts it again.")
    if "no soundcards" in cards_text:
        found.append("! Linux sees no sound card: its driver or firmware is missing. On new laptops it is usually the "
                     "sound firmware package (with 'sof-firmware' in its name): the user installs it and restarts.")
    elif cards:
        lines.append(f"- Sound cards: {'; '.join(cards[:4])}")
    sinks = [s for s in a["sinks"] if not _dummy(s)]
    if a["ok"] and not sinks:
        found.append("! There is no sound output, only a dummy one: the sound service found no device. fix_system "
                     "sound_restart often brings it back; if not, it is the driver (a restart of the computer after an "
                     "update often helps).")
    default = next((s for s in a["sinks"] if s.get("name") == a["sink"]), None)
    for s in sinks:
        lines.append(f"- Output: {_dev_name(s)}{' (default)' if s is default else ''} — " +
                     f"{str(s.get('state') or '?').lower()}, volume {s.get('volume', '?')}%" +
                     (", muted" if s.get("mute") == "yes" else ""))
    if default is not None and not _dummy(default):
        name = _dev_name(default)
        if default.get("mute") == "yes":
            found.append(f"! '{name}' (the default output) is muted: fix_system sound_on turns it on.")
        elif default.get("volume") is not None and default["volume"] < 10:
            found.append(f"! '{name}' (the default output) is at {default['volume']}%: fix_system sound_on turns it "
                         "up to 50%.")
        port = default.get("active port", "")
        if port and default.get("ports", {}).get(port) is False:
            found.append(f"! '{name}' plays to '{port}', which isn't plugged in: plug it in, or choose another output "
                         "(fix_system sound_output).")
        others = [_dev_name(s) for s in sinks if s is not default]
        if re.search(r"hdmi|displayport|\bdp\b", f"{default.get('name')} {name}", re.I) and others:
            found.append(f"- The sound goes to '{name}' (a monitor or TV over HDMI or DisplayPort). If it has no "
                         f"speakers: fix_system sound_output with one of: {'; '.join(others[:4])}.")
    mic = next((s for s in a["sources"] if s.get("name") == a["source"]), None)
    for s in a["sources"][:4]:
        lines.append(f"- Input: {_dev_name(s)}{' (default)' if s is mic else ''}" +
                     (", muted" if s.get("mute") == "yes" else f", volume {s.get('volume', '?')}%"))
    if mic is not None and mic.get("mute") == "yes":
        found.append(f"- The microphone '{_dev_name(mic)}' is muted (if the microphone is the problem: fix_system "
                     "mic_on turns it on).")
    elif mic is not None and mic.get("volume") is not None and mic["volume"] < 10:
        found.append(f"- The microphone '{_dev_name(mic)}' is at {mic['volume']}% (if the microphone is the problem: "
                     "fix_system mic_on turns it up to 50%).")
    hint = ["(Lanterna: if everything here works, the sound may go to another output or be turned down in one "
            "program: open the sound settings with pc_settings_page sound for the user to check.)"]
    return [(0, "Sound:", found or ["- No problem found in the sound devices and the sound service."]),
            (1, "", lines), (0, "", hint)]


# ---------------------------------------------------------------- internet
def proxy(fx) -> dict:
    """The desktop's proxy: {on, shown, desktop: gnome | kde | env, old: what Undo puts back}."""
    code, out = cmd(fx, ["gsettings", "get", "org.gnome.system.proxy", "mode"])
    mode = out.strip().strip("'") if code == 0 else ""
    if mode in ("manual", "auto"):
        if mode == "auto":
            url = cmd(fx, ["gsettings", "get", "org.gnome.system.proxy", "autoconfig-url"])[1].strip().strip("'")
            shown = f"script {url}" if url else "automatic"
        else:
            parts = []
            for kind in ("http", "https", "socks"):
                host = cmd(fx, ["gsettings", "get", f"org.gnome.system.proxy.{kind}", "host"])[1].strip().strip("'")
                port = cmd(fx, ["gsettings", "get", f"org.gnome.system.proxy.{kind}", "port"])[1].strip()
                if host:
                    parts.append(f"{host}:{port}" if port.isdigit() and port != "0" else host)
            shown = "; ".join(dict.fromkeys(parts)) or "manual"
        return {"on": True, "shown": fx.clean(shown), "desktop": "gnome", "old": mode}
    if "kde" in fx._env("XDG_CURRENT_DESKTOP").lower():
        sec = re.search(r"(?ms)^\[Proxy Settings\]\s*$(.*?)(?=^\[|\Z)", _read(fx.home / ".config" / "kioslaverc"))
        ptype = re.search(r"(?m)^ProxyType=(\d+)", sec.group(1)) if sec else None
        if ptype and ptype.group(1) in ("1", "2", "3"):
            http = re.search(r"(?m)^httpProxy=(.+)$", sec.group(1))
            shown = http.group(1).strip() if ptype.group(1) == "1" and http else "automatic"
            return {"on": True, "shown": fx.clean(shown), "desktop": "kde", "old": ptype.group(1)}
    env = [f"{k}={fx._env(k)}" for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY") if fx._env(k)]
    if env:
        return {"on": True, "shown": fx.clean("; ".join(env)), "desktop": "env", "old": ""}
    return {"on": False, "shown": "", "desktop": "", "old": ""}


def kde_proxy(fx, value: str) -> tuple[int, str]:
    for tool in ("kwriteconfig6", "kwriteconfig5"):
        code, out = cmd(fx, [tool, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "ProxyType", value])
        if code != 127:
            return code, out
    return 127, "kwriteconfig isn't installed"


def internet(fx) -> list:
    found, lines = [], []
    code, gen = cmd(fx, ["nmcli", "-t", "-f", "STATE,CONNECTIVITY,WIFI-HW,WIFI,NETWORKING", "general"])
    nm = code == 0 and bool(gen.strip())
    g = dict(zip(("state", "conn", "wifihw", "wifi", "net"), _terse(gen.strip().splitlines()[0]))) if nm else {}
    devs = [dict(zip(("dev", "type", "state", "con"), _terse(x)))
            for x in (cmd(fx, ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])[1].splitlines() if nm
                      else []) if x.strip()]
    real = [d for d in devs if d.get("type") in ("ethernet", "wifi", "gsm", "bt", "wwan")]
    up = [d for d in real if d.get("state", "").startswith("connected")]
    for d in real:
        lines.append(f"- {d.get('dev')} ({d.get('type')}): {d.get('state')}")
    if nm and g.get("net") == "disabled":
        found.append("! Networking is turned off: the user turns it on in the system menu (top right) or the network "
                     "icon.")
    elif nm and not up:
        if g.get("wifihw") == "disabled":
            found.append("! Wi-Fi is turned off by a key or a switch on the computer (airplane mode): press it.")
        elif g.get("wifi") == "disabled":
            found.append("! Wi-Fi is turned off: the user turns it on in the system menu (top right) → Wi-Fi.")
        else:
            found.append("! The computer isn't connected to any network: no Wi-Fi network chosen, or the cable is out.")
    if nm and any(d.get("type") == "wifi" for d in up):
        sig = [x for x in cmd(fx, ["nmcli", "-t", "-f", "IN-USE,SIGNAL", "device", "wifi", "list", "--rescan", "no"]
                              )[1].splitlines() if x.startswith("*")]
        level = _terse(sig[0])[1] if sig and len(_terse(sig[0])) > 1 else ""
        if level.isdigit():
            lines.append(f"- Wi-Fi signal: {level}%" + (" — weak" if int(level) < 40 else ""))
            if int(level) < 40:
                found.append(f"! The Wi-Fi signal is weak ({level}%): closer to the router, or a cable.")
    if g.get("conn") == "portal":
        found.append("! This network wants its sign-in page first (hotels, trains, cafés): open any site in the browser "
                     "to get it.")
    vpn = [_terse(x)[0] for x in (cmd(fx, ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])[1]
                                  .splitlines() if nm else [])
           if len(_terse(x)) > 1 and _terse(x)[1] in ("vpn", "wireguard", "tun")]
    addrs, gws = [], []
    code, out = cmd(fx, ["ip", "-j", "-4", "addr", "show"])
    try:
        for i in json.loads(out) if code == 0 else []:
            if i.get("ifname") != "lo" and (not real or i.get("ifname") in {d.get("dev") for d in real}):
                addrs += [a.get("local") for a in i.get("addr_info") or [] if a.get("local")]
    except (ValueError, AttributeError, TypeError):
        pass
    code, out = cmd(fx, ["ip", "-j", "-4", "route", "show", "default"])
    try:
        gws = [r.get("gateway") for r in (json.loads(out) if code == 0 else []) if r.get("gateway")]
    except (ValueError, AttributeError, TypeError):
        gws = []
    lines.append(f"- Addresses: {', '.join(addrs) or 'none'}; router: {', '.join(gws) or 'none'}")
    if addrs and all(x.startswith("169.254.") for x in addrs):
        found.append("! The computer got no address from the router (169.254…): restart the router; on Wi-Fi forget the "
                     "network and connect again.")
    gw_ok = cmd(fx, ["ping", "-c", "1", "-W", "2", gws[0]], 6)[0] == 0 if gws else None
    dns_ok = any(cmd(fx, ["getent", "ahostsv4", host], 8)[0] == 0
                 for host in ("one.one.one.one", "www.msftconnecttest.com"))
    tcp_ok = bool(fx.probe("1.1.1.1", 443))
    if gws:
        lines.append(f"- The router answers: {'yes' if gw_ok else 'no'}")
    lines.append(f"- Names of sites (DNS): {'work' if dns_ok else 'do not work'}")
    lines.append(f"- The internet by a direct address: {'works' if tcp_ok else 'does not work'}")
    if not dns_ok and tcp_ok:
        found.append("! The internet works, but site names don't (DNS). The user can set the DNS server 1.1.1.1 in "
                     "Settings → Network → the connection → IPv4. Clearing the DNS cache needs the computer's password, "
                     "so the user runs 'sudo resolvectl flush-caches' in Terminal.")
    elif not tcp_ok and gw_ok:
        found.append("! The router answers but the internet doesn't: the router or the provider. Restart the router; if "
                     "it stays, call the provider.")
    elif gws and gw_ok is False and not tcp_ok:
        found.append("! Even the router doesn't answer: check the cable or Wi-Fi, and restart the router.")
    if vpn and not (dns_ok and tcp_ok):
        found.append(f"! A VPN is on: {'; '.join(vpn)}. It can block the internet: try with it off.")
    elif vpn:
        lines.append(f"- A VPN is on: {'; '.join(vpn)} (it can slow some sites or games down)")
    px = proxy(fx)
    if px["on"] and px["desktop"] == "env":
        found.append(f"! A proxy is set in the environment: {px['shown']}. The user removes it from the file that sets "
                     "it (~/.bashrc, ~/.profile or /etc/environment), then signs out and in.")
    elif px["on"]:
        found.append(f"! A proxy is on: {px['shown']}. If the user didn't set it on purpose (some programs leave one), "
                     "fix_system proxy_off turns it off.")
    lines.append(f"- Proxy: {px['shown'] if px['on'] else 'off'}")
    hint = ["(Lanterna: if everything works here, the problem is one site or program (or its firewall rule).)"]
    return [(0, "Internet:", found or ["- Everything answers: the internet works on this computer."]),
            (1, "", lines), (0, "", hint)]


# ---------------------------------------------------------------- printers
class CupsPrinters:
    """This user's printers (CUPS). Only the user's own default printer (~/.cups/lpoptions) is ever changed."""

    def __init__(self, run, home: Path):
        self._run, self.home = run, home

    def _cmd(self, args: list[str]) -> tuple[int, str]:
        return self._run(args, timeout=15, env={**os.environ, **LC})

    def names(self) -> list[str]:
        code, out = self._cmd(["lpstat", "-e"])
        return [x.strip() for x in out.splitlines() if x.strip() and " " not in x.strip()] if code == 0 else []

    def default(self) -> str:
        code, out = self._cmd(["lpstat", "-d"])
        m = re.search(r"destination:\s*(\S+)", out)
        return m.group(1) if code == 0 and m else ""

    def set_default(self, name: str) -> bool:
        return self._cmd(["lpoptions", "-d", str(name)])[0] == 0

    def clear_default(self) -> bool:
        """Back to the system's default printer: this user's own choice goes."""
        f = self.home / ".cups" / "lpoptions"
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            return True
        new = re.sub(r"(?m)^Default ", "Dest ", text)
        if new != text:
            f.write_text(new, encoding="utf-8")
        return True


def parse_printers(text: str) -> list[dict]:
    """lpstat -l -p: {name, state: idle | printing | disabled, reason, alerts, desc}."""
    out: list[dict] = []
    cur: dict | None = None
    first = False
    for line in text.splitlines():
        m = re.match(r"^printer (\S+) (.*)$", line)
        if m:
            rest = m.group(2)
            cur = {"name": m.group(1), "state": "disabled" if rest.startswith("disabled") else "printing" if
                   rest.startswith("now printing") else "idle", "reason": "", "alerts": "", "desc": ""}
            out.append(cur)
            first = True
            continue
        if cur is None or not line[:1].isspace():
            continue
        s = line.strip()
        key, sep, val = s.partition(":")
        if first and cur["state"] == "disabled" and (not sep or key not in LPSTAT_KEYS):
            cur["reason"] = s
        elif key == "Description":
            cur["desc"] = val.strip()
        elif key == "Alerts":
            cur["alerts"] = val.strip()
        first = False
    return out


def jobs(fx, printer: str = "") -> list[tuple[str, str, str]]:
    """(job id, printer, owner) of the jobs waiting."""
    code, out = cmd(fx, ["lpstat", "-o"] + ([printer] if printer else []))
    found = []
    for line in out.splitlines() if code == 0 else []:
        f = line.split()
        if len(f) >= 2 and re.search(r"-\d+$", f[0]):
            found.append((f[0], f[0].rsplit("-", 1)[0], f[1]))
    return found


def printer(fx) -> list:
    from .fixit import VIRTUAL_PRINTERS
    code, sched = cmd(fx, ["lpstat", "-r"])
    if code == 127:
        return [(0, "Printers:", ["! Printing isn't set up on this computer: CUPS, the printing service, isn't installed "
                                  "(the package 'cups'). Installing it needs the computer's password."])]
    found, lines = [], []
    if "not running" in sched:
        found.append("! The printing service (CUPS) isn't running: nothing prints without it. Starting it needs the "
                     "computer's password, so the user runs 'sudo systemctl enable --now cups' in Terminal (or restarts "
                     "the computer).")
    prs = parse_printers(cmd(fx, ["lpstat", "-l", "-p"])[1])
    default = fx.printers.default()
    waiting = jobs(fx)
    real = [x for x in prs if not VIRTUAL_PRINTERS.search(x["name"]) and not VIRTUAL_PRINTERS.search(x["desc"])]
    for x in prs:
        alerts = [txt for key, txt in CUPS_ALERTS if key in x["alerts"]]
        n = sum(1 for j in waiting if j[1] == x["name"])
        state = {"disabled": "paused", "printing": "printing", "idle": "ready"}[x["state"]]
        lines.append(f"- {x['name']}{' (default)' if x['name'] == default else ''}: {state}" +
                     (f" ({x['reason']})" if x["reason"] and x["reason"].lower() not in ("reason unknown", "paused")
                      else "") +
                     (f", {', '.join(dict.fromkeys(alerts))}" if alerts else "") +
                     (f", {n} job{'s' if n != 1 else ''} waiting" if n else ""))
        if x not in real:
            continue
        if x["state"] == "disabled":
            found.append(f"! {x['name']} is paused: in Settings → Printers, open it and resume it (it may ask for the "
                         "computer's password).")
        if "offline" in alerts:
            found.append(f"! {x['name']} is offline: check that it is on and connected (cable or the same Wi-Fi).")
        for a in dict.fromkeys(a for a in alerts if a != "offline"):
            found.append(f"! {x['name']}: {a}.")
    if waiting and (len(waiting) >= 3 or any(x["state"] == "disabled" for x in prs)):
        found.append(f"! {len(waiting)} print jobs wait in the queue: stuck jobs block the next ones; fix_system "
                     "print_queue clears them.")
    if not prs and "not running" not in sched:
        found.append("! No printer is set up: add it in Settings → Printers (pc_settings_page printers).")
    if real and default and default not in {x["name"] for x in real} and default in {x["name"] for x in prs}:
        found.append(f"! The default printer is '{default}' (not a real printer): fix_system default_printer makes the "
                     "right one the default.")
    elif real and not default:
        found.append("! No printer is the default: programs may not know where to print; fix_system default_printer "
                     "chooses one.")
    return [(0, "Printers:", found or ["- No problem found with the printers."]), (1, "", lines)]


# ---------------------------------------------------------------- updates
def _meaning(line: str) -> str:
    low = line.lower()
    return next((m for rx, m in UPDATE_ERRORS if re.search(rx, low)), "")


def updates(fx) -> list:
    osr = os_release(fx.root)
    found, lines = [], []
    if osr.get("PRETTY_NAME"):
        lines.append(f"- System: {osr['PRETTY_NAME']}")
    atomic = (fx.root / "run" / "ostree-booted").exists()
    if (fx.root / "run" / "reboot-required").exists():
        found.append("! The system waits for a restart to finish updates: restart the computer first.")
    # dnf5 (Fedora 41+, also GNOME Software's) keeps a downloaded update for the next restart here
    st = dict(re.findall(r'(?m)^(\w+)\s*=\s*"?([^"\n]*?)"?\s*$',
                         _read(fx.root / "usr" / "lib" / "sysimage" / "libdnf5" / "offline" /
                               "offline-transaction-state.toml")))
    target = st.get("target_releasever", "")
    if st.get("status") in ("download-complete", "ready") and (
            st.get("verb") == "system-upgrade" or (target and target != st.get("system_releasever", target))):
        found.append(f"! An upgrade to {osr.get('NAME') or 'the system'} {target} is downloaded and waits for a restart: "
                     "it installs while the computer restarts (Software → Restart & Upgrade).")
    elif (st.get("status") in ("download-complete", "ready") or (fx.root / "system-update").exists() or
          (fx.root / "var" / "lib" / "PackageKit" / "prepared-update").exists()):
        found.append("! Updates are downloaded and wait for a restart: they install while the computer restarts "
                     "(Software → Updates → Restart & Update).")
    if atomic:
        code, out = cmd(fx, ["rpm-ostree", "status", "--json"], 20)
        try:
            deps = json.loads(out).get("deployments") or [] if code == 0 else []
        except (ValueError, AttributeError):
            deps = []
        if any(d.get("staged") for d in deps) or (deps and not deps[0].get("booted")):
            found.append("! A system update is ready and waits for a restart.")
    running = fx.uname()
    mods = []
    for d in (fx.root / "lib" / "modules", fx.root / "usr" / "lib" / "modules"):
        try:
            mods += [x.name for x in d.iterdir() if x.is_dir() and re.match(r"\d", x.name)]
        except OSError:
            continue
    newest = max(set(mods), key=_vkey) if mods else ""
    if running and newest and newest != running and _vkey(newest) > _vkey(running):
        lines.append(f"- A newer Linux kernel is installed ({newest}): it starts after a restart (now: {running}).")
    try:
        names = {n.lower() for n, _path in fx.procs()}
    except OSError:
        names = set()
    busy = sorted(names & BUSY)
    if busy:
        found.append(f"! An update is running now ({', '.join(busy)}): wait until it finishes; a second one can't start "
                     "meanwhile.")
    boot = any(m == "/boot" for m, _fs in mounts(fx.root))
    for label, path, need in (("the system disk", fx.root, 5 * GB), ("/boot", fx.root / "boot", 150 * MB)):
        if label == "/boot" and not boot:
            continue
        try:
            free = shutil.disk_usage(path).free
        except OSError:
            continue
        lines.append(f"- Free on {label}: {_size(free)}")
        if free < need:
            found.append(f"! Only {_size(free)} is free on {label}: " + (
                "updates need several GB. Free up space first (pc_disk)." if label != "/boot" else
                "new kernels won't fit. Removing old kernels frees it (Fedora: 'sudo dnf remove --oldinstallonly')."))
    errors: dict[str, str] = {}
    for rel in UPDATE_LOGS:
        f = fx.root / rel
        try:
            if fx.now() - f.stat().st_mtime > 30 * 86400:
                continue
        except OSError:
            continue
        for line in _tail(f).splitlines():
            meaning = _meaning(line)
            if meaning:
                errors.pop(meaning, None)
                errors[meaning] = f"{rel.rsplit('/', 1)[-1]}: {_cut(line.strip(), 170)}"
    for line in journal(fx, ["-u", "packagekit", "-p", "0..3"]):
        meaning = _meaning(line)
        if meaning:
            errors.pop(meaning, None)
            errors[meaning] = f"PackageKit: {_cut(_msg(line), 170)}"
    for meaning, line in list(errors.items())[-5:]:
        found.append(f"! Failed: {meaning} — {line}")
    ids = f"{osr.get('ID', '')} {osr.get('ID_LIKE', '')}".lower()
    command = ("rpm-ostree upgrade" if atomic else "sudo dnf upgrade --refresh" if re.search(r"fedora|rhel|centos", ids)
               else "sudo apt update && sudo apt full-upgrade" if re.search(r"debian|ubuntu", ids) else
               "sudo pacman -Syu" if "arch" in ids else "sudo zypper update" if "suse" in ids else "")
    how = (f"'{command}' in Terminal (it shows the exact error) or Software → Updates" if command else
           "Software → Updates (KDE: Discover), or the system's own update command in Terminal")
    hint = ["(Lanterna: installing updates needs the computer's password, so the user runs them: " + how +
            "; Flatpak apps: 'flatpak update'. " +
            ("Explain what is above in plain words and give the one step that fits it.)" if found else
             "If an update still fails, running it in Terminal shows the exact error.)")]
    return [(0, "Updates:", found or ["- No failed updates and nothing blocking them."]), (1, "", lines), (0, "", hint)]


AREAS = {"sound": sound, "internet": internet, "printer": printer, "updates": updates}


# ---------------------------------------------------------------- the fixes
def propose(fx, action: str, name: str = "") -> str:
    a = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
    name = fx.unmask(name)                         # "<user>'s AirPods": the name as clean() showed it
    if a in ("proxy_off", "proxy", "no_proxy"):
        return _proxy_off(fx)
    if a in ("default_printer", "printer", "default"):
        return _default_printer(fx, name)
    if a in ("print_queue", "queue", "clear_queue", "jobs"):
        return _queue(fx, name)
    if a in ("sound_output", "output", "default_output"):
        return _sound_output(fx, name)
    if a in ("sound_on", "unmute", "volume"):
        return _sound_on(fx, name)
    if a in ("mic_on", "mic", "microphone", "unmute_mic"):
        return _sound_on(fx, name, mic=True)
    if a in ("sound_restart", "restart_sound", "restart"):
        return _sound_restart(fx)
    raise WorkError("action: sound_output, sound_on, mic_on, sound_restart, proxy_off, default_printer or "
                    "print_queue.")


def _proxy_off(fx) -> str:
    px = proxy(fx)
    if not px["on"]:
        return "No proxy is on: nothing to turn off."
    if px["desktop"] == "env":
        raise WorkError("This proxy is set in the environment (HTTP_PROXY and the like), not in the desktop's settings, "
                        "so Lanterna can't turn it off. The user removes it from the file that sets it (~/.bashrc, "
                        "~/.profile or /etc/environment), then signs out and in.")
    fx._no_twin("fix_proxy")
    desktop, old = px["desktop"], px["old"]

    def go() -> str:
        code, out = (cmd(fx, ["gsettings", "set", "org.gnome.system.proxy", "mode", "'none'"]) if desktop == "gnome"
                     else kde_proxy(fx, "0"))
        if code:
            raise WorkError("The system didn't change it: " + (_cut(out, 160) or "no answer"))
        fx.actions.note_undo({"type": "proxy", "linux": desktop, "old": old})
        return "the proxy is off"
    fx.actions.propose("fix_proxy", {"server": px["shown"], "linux": True}, go)
    return WAITING


def undo_proxy(fx, u: dict) -> bool:
    old = str(u.get("old") or "")
    if u.get("linux") == "gnome" and old in ("manual", "auto"):
        return cmd(fx, ["gsettings", "set", "org.gnome.system.proxy", "mode", f"'{old}'"])[0] == 0
    if u.get("linux") == "kde" and old.isdigit():
        return kde_proxy(fx, old)[0] == 0
    return False


def _default_printer(fx, name: str) -> str:
    want = _pick_name(name, fx.printers.names())
    was = fx.printers.default()
    if want == was:
        return f"'{want}' is the default printer already."
    fx._no_twin("fix_printer")

    def go() -> str:
        if not fx.printers.set_default(want):
            raise WorkError("The system didn't accept it as the default printer.")
        fx.actions.note_undo({"type": "printer", "name": was, "linux": True})
        return f"{want} is the default printer"
    fx.actions.propose("fix_printer", {"name": fx.clean(want), "was": fx.clean(was), "linux": True}, go)
    return WAITING


def undo_printer(fx, u: dict) -> bool:
    return fx.printers.set_default(u["name"]) if u.get("name") else fx.printers.clear_default()


def _queue(fx, name: str) -> str:
    want = _pick_name(name, fx.printers.names())
    if not jobs(fx, want):
        return f"No print jobs wait for {want}: nothing to clear."
    fx._no_twin("fix_queue", name=fx.clean(want))

    def go() -> str:
        waiting = jobs(fx, want)
        mine = [j for j, _p, owner in waiting if not fx.user or owner == fx.user]
        if not mine:
            raise WorkError("These print jobs belong to another user: removing them needs the computer's password "
                            "(Settings → Printers)." if waiting else "No print jobs wait any more.")
        code, out = cmd(fx, ["cancel", *mine], 30)
        if code:
            raise WorkError("CUPS didn't remove them: " + (_cut(out, 160) or "no answer"))
        left = len(waiting) - len(mine)
        return f"removed {len(mine)} print job{'s' if len(mine) != 1 else ''} of {want}" + (
            f"; {left} of other users stayed" if left else "")
    fx.actions.propose("fix_queue", {"name": fx.clean(want), "linux": True}, go)
    return WAITING


def _pick_device(want: str, devs: list[dict], what: str) -> dict:
    q = str(want or "").strip().lower()
    names = "; ".join(_dev_name(d) for d in devs) or "none"
    if not q:
        raise WorkError(f"Say which {what}: {names}")
    exact = [d for d in devs if q in (_dev_name(d).lower(), str(d.get("name", "")).lower())]
    hits = exact or [d for d in devs if q in _dev_name(d).lower() or q in str(d.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise WorkError(f"No {what} is called that. There are: {names}")
    twins = len({_dev_name(d) for d in hits}) < len(hits)        # two of one model: their system names differ
    raise WorkError("Several match: " + "; ".join(f"{_dev_name(d)} ({d.get('name')})" if twins else _dev_name(d)
                                                  for d in hits) + (". Give the name in brackets." if twins else ""))


def _sound_output(fx, name: str) -> str:
    a = _audio(fx)
    if not a["ok"]:
        raise WorkError("The sound service doesn't answer: fix_system sound_restart first.")
    sinks = [s for s in a["sinks"] if not _dummy(s)]
    want = _pick_device(name, sinks, "output")
    if want.get("name") == a["sink"]:
        return f"'{_dev_name(want)}' is the sound output already."
    was = next((s for s in a["sinks"] if s.get("name") == a["sink"]), {})
    fx._no_twin("fix_sound")
    target, old = str(want.get("name")), str(a["sink"])

    def go() -> str:
        code, out = cmd(fx, ["pactl", "set-default-sink", target])
        if code:
            raise WorkError("The sound service didn't take it: " + (_cut(out, 160) or "no answer"))
        fx.actions.note_undo({"type": "sound", "default": old})
        return f"the sound goes to {_dev_name(want)}"
    fx.actions.propose("fix_sound", {"name": fx.clean(_dev_name(want)), "was": fx.clean(_dev_name(was)) if was else ""},
                       go)
    return WAITING


def _sound_on(fx, name: str, mic: bool = False) -> str:
    """A muted or very quiet output (or, with mic, microphone) on again. They are apart: on PipeWire an output and
    a microphone of one sound card often have the same name."""
    a = _audio(fx)
    if not a["ok"]:
        raise WorkError("The sound service doesn't answer: fix_system sound_restart first.")
    devs = a["sources"] if mic else [s for s in a["sinks"] if not _dummy(s)]
    what = "microphone" if mic else "output"
    dev = _pick_device(name, devs, what) if str(name or "").strip() else \
        next((s for s in devs if s.get("name") == a["source" if mic else "sink"]), None)
    if dev is None:
        raise WorkError(f"There is no default {what}: say which one.")
    muted, vol = dev.get("mute") == "yes", dev.get("volume")
    louder = vol is not None and vol < 10
    if not muted and not louder:
        return f"'{_dev_name(dev)}' is on already ({vol}%)."
    kind, target = dev["kind"], str(dev.get("name"))
    fx._no_twin("fix_unmute", name=fx.clean(_dev_name(dev)), mic=mic)

    def go() -> str:
        if muted and cmd(fx, ["pactl", f"set-{kind}-mute", target, "0"])[0]:
            raise WorkError("The sound service didn't turn it on.")
        if louder:
            cmd(fx, ["pactl", f"set-{kind}-volume", target, "50%"])
        fx.actions.note_undo({"type": "sound", "device": target, "kind": kind, "mute": muted,
                              "volume": vol if louder else None})
        return f"{_dev_name(dev)} is on" + (" at 50%" if louder else "")
    fx.actions.propose("fix_unmute", {"name": fx.clean(_dev_name(dev)), "muted": muted, "volume": vol,
                                      "to": 50 if louder else None, "mic": mic}, go)
    return WAITING


def undo_sound(fx, u: dict) -> bool:
    if u.get("default"):
        return cmd(fx, ["pactl", "set-default-sink", str(u["default"])])[0] == 0
    dev, kind = str(u.get("device") or ""), "source" if u.get("kind") == "source" else "sink"
    if not dev:
        return False
    ok = True
    if u.get("volume") is not None:
        ok = cmd(fx, ["pactl", f"set-{kind}-volume", dev, f"{int(u['volume'])}%"])[0] == 0
    if u.get("mute"):
        ok = cmd(fx, ["pactl", f"set-{kind}-mute", dev, "1"])[0] == 0 and ok
    return ok


def _sound_restart(fx) -> str:
    a, units = _audio(fx), _units(fx)
    pw = _pipewire(a, units)
    names = ["pipewire.service", "pipewire-pulse.service", "wireplumber.service"] if pw else ["pulseaudio.service"]
    fx._no_twin("fix_sound_restart")

    def go() -> str:
        code, out = cmd(fx, ["systemctl", "--user", "restart", *names], 45)
        if code:
            raise WorkError("It didn't start again: " + (_cut(out, 200) or "no answer"))
        return "the sound service started again"
    fx.actions.propose("fix_sound_restart", {"name": "PipeWire" if pw else "PulseAudio"}, go)
    return WAITING
