"""The whole disk at once, for pc_disk: one walk of every folder of the disk the profile is on, then the biggest
folders by what they are (a game, a program, a cache, Windows itself), Steam's games by name, the biggest files,
kinds of files (videos, archives, disk images…) and what can't be counted (restore points, closed folders).

It only looks. The walk runs in the background on several threads: on a full disk it takes from seconds (folders
read before) to a few minutes (the first time after the computer starts). pc_disk waits a while and says what it
has so far; the walk goes on, so the next question gets the whole disk.
"""
from __future__ import annotations

import heapq
import ntpath
import os
import re
import shutil
import stat
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable, Iterable

from .pcfiles import GB, MB, size_text

REPARSE = 0x400
ONLINE_ONLY = 0x1000 | 0x40000 | 0x400000    # offline, recall on open, recall on data access: a OneDrive file online
MOUNT_POINT = 0xA0000003                     # junctions and mounted folders: what they point at counts where it is
DEPTH = 8                                    # sizes are kept for folders this deep; deeper files count in their parent
BIG_FILES = 60
WORKERS = 12                                 # folders are read at once: a disk not read since the start is slow
KEEP = 600.0                                 # a finished walk of the disk answers again for 10 minutes…
SLACK = 500 * MB                             # …while the free space stays within this
WAIT = 120.0                                 # how long pc_disk waits for the walk before it says what it has
LONGEST = 900.0                              # a walk stops after 15 minutes (its sizes then say "at least")
FLOOR = GB                                   # the list of the biggest: folders this big and bigger
LINUX_SKIP = ("/proc", "/sys", "/dev", "/run", "/mnt", "/media", "/snap", "/tmp", "/.snapshots", "/lost+found")

KINDS = {
    "videos": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".flv", ".mpg", ".mpeg", ".ts", ".3gp"),
    "photos and pictures": (".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".raw", ".cr2",
                            ".cr3", ".nef", ".arw", ".dng", ".psd"),
    "music and sound": (".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus"),
    "archives": (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".xz", ".bz2", ".zst"),
    "disk images and virtual disks": (".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2"),
    "installers and programs": (".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle", ".rpm", ".deb",
                                ".appimage", ".flatpak", ".dmg", ".pkg"),
}
KIND_OF = {ext: kind for kind, exts in KINDS.items() for ext in exts}


# ---------------------------------------------------------------- one walk of a folder tree
class Walk:
    """One walk of a folder tree by several threads: bytes per folder, the biggest files, files of each kind.
    Links, junctions and files kept only online (OneDrive) are not counted: they take no space here."""

    def __init__(self, root: str, *, skip: Iterable[str] = (), workers: int = WORKERS,
                 now: Callable[[], float] = time.monotonic, longest: float = LONGEST,
                 free: Callable[[str], int] | None = None):
        self.root = os.path.normpath(root)
        self.skip = {os.path.normcase(os.path.normpath(s)) for s in skip}
        self.now, self.longest, self.workers = now, longest, workers
        self._free = free or (lambda r: shutil.disk_usage(r).free)
        self.own: dict[str, int] = defaultdict(int)       # folder → bytes of its files (and of deeper ones)
        self.files = self.closed = self.online = self.counted = 0
        self.big: list[tuple[int, str]] = []              # the biggest files: a heap of (bytes, path)
        self.kinds: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))   # kind → folder → bytes
        self.started = now()
        self.finished: float | None = None
        self.cut = False                                  # stopped before the end (LONGEST)
        self.free_after: int | None = None
        self.done = threading.Event()
        self._cv = threading.Condition()
        self._todo: deque = deque([(self.root, 0, self.root)])
        self._busy = 0
        self._sizes: dict[str, int] | None = None

    def start(self) -> "Walk":
        for _ in range(self.workers):
            threading.Thread(target=self._work, name="lanterna-disk", daemon=True).start()
        return self

    def wait(self, seconds: float) -> bool:
        return self.done.wait(max(0.0, seconds))

    @property
    def whole(self) -> bool:
        return self.done.is_set() and not self.cut

    def seconds(self) -> float:
        return (self.finished if self.finished is not None else self.now()) - self.started

    def _work(self) -> None:
        while True:
            with self._cv:
                while not self._todo and self._busy:
                    self._cv.wait()
                if not self._todo:
                    self._cv.notify_all()
                    return
                if self.now() - self.started > self.longest:
                    self.cut = True
                    self._todo.clear()
                    if not self._busy:
                        self._finish()
                    self._cv.notify_all()
                    return
                folder, depth, account = self._todo.popleft()
                self._busy += 1
            try:
                got = self._scan(folder, depth, account)
            except Exception:                              # noqa: BLE001  one odd folder never stops the walk
                got = ([], 0, 0, [], [], 1, 0)
            with self._cv:
                self._busy -= 1
                self._add(account, got)
                if not self._todo and not self._busy and not self.done.is_set():
                    self._finish()
                self._cv.notify_all()

    def _finish(self) -> None:
        self.finished = self.now()
        try:
            self.free_after = self._free(self.root)
        except OSError:
            self.free_after = None
        self.done.set()

    def _scan(self, folder: str, depth: int, account: str):
        subs, bigs, kinds = [], [], []
        own = n = closed = online = 0
        try:
            with os.scandir(folder) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    attrs = getattr(st, "st_file_attributes", 0)
                    if stat.S_ISDIR(st.st_mode):
                        if attrs & REPARSE and getattr(st, "st_reparse_tag", 0) == MOUNT_POINT:
                            continue                       # AppData\Application Data points at itself
                        if self.skip and os.path.normcase(e.path) in self.skip:
                            continue
                        subs.append((e.path, depth + 1, e.path if depth < DEPTH else account))
                    elif stat.S_ISREG(st.st_mode):
                        if attrs & ONLINE_ONLY:
                            online += st.st_size
                            continue
                        own += st.st_size
                        n += 1
                        if st.st_size >= MB:
                            bigs.append((st.st_size, e.path))
                            kind = KIND_OF.get(os.path.splitext(e.name)[1].lower())
                            if kind:
                                kinds.append((kind, st.st_size))
        except OSError:
            closed = 1                                     # a folder this user can't open
        return subs, own, n, bigs, kinds, closed, online

    def _add(self, account: str, got) -> None:
        subs, own, n, bigs, kinds, closed, online = got
        if not self.cut:
            self._todo.extend(subs)
        if own:
            self.own[account] += own
            self.counted += own
        self.files += n
        self.closed += closed
        self.online += online
        for b in bigs:
            if len(self.big) < BIG_FILES:
                heapq.heappush(self.big, b)
            elif b > self.big[0]:
                heapq.heapreplace(self.big, b)
        for kind, size in kinds:
            self.kinds[kind][account] += size
        self._sizes = None

    def sizes(self) -> dict[str, int]:
        """Bytes in each folder with everything inside it (folders up to DEPTH levels deep)."""
        with self._cv:
            if self._sizes is not None:
                return self._sizes
            own = list(self.own.items())
            final = self.done.is_set()
        out: dict[str, int] = defaultdict(int)
        for folder, n in own:
            p = folder
            while True:
                out[p] += n
                if p == self.root:
                    break
                up = os.path.dirname(p)
                if up == p:
                    break
                p = up
        out = dict(out)
        out.setdefault(self.root, 0)
        if final:
            with self._cv:
                self._sizes = out
        return out

    def loose(self) -> int:
        """Bytes of the files right in the root (hiberfil.sys, pagefile.sys…)."""
        with self._cv:
            return self.own.get(self.root, 0)

    def biggest(self) -> list[tuple[int, str]]:
        with self._cv:
            return sorted(self.big, reverse=True)

    def kind_sizes(self) -> dict[str, dict[str, int]]:
        with self._cv:
            return {k: dict(v) for k, v in self.kinds.items()}


_walks: dict[str, Walk] = {}
_walks_lock = threading.Lock()


def walk(root: str, *, skip: Iterable[str] = (), keep: float = KEEP, slack: int = SLACK,
         make: Callable[..., Walk] = Walk, free: Callable[[str], int] | None = None) -> Walk:
    """The walk of this folder: the one going on, a finished one that is still right (a few minutes old, and the
    free space is about the same), or a new one."""
    key = os.path.normcase(os.path.normpath(root))
    free = free or (lambda r: shutil.disk_usage(r).free)
    with _walks_lock:
        w = _walks.get(key)
        if w is not None and not w.done.is_set():
            return w
        if w is not None and w.whole and w.finished is not None and w.now() - w.finished <= keep:
            try:
                same = w.free_after is not None and abs(free(root) - w.free_after) < slack
            except OSError:
                same = False
            if same:
                return w
        for k in [k for k, x in _walks.items() if x.done.is_set() and k != key][:-5]:
            _walks.pop(k, None)                            # keep a few finished walks, not all of them
        w = _walks[key] = make(root, skip=skip).start()
        return w


def counting() -> tuple[int, int] | None:
    """(files, bytes) counted so far by the walk going on (the biggest one), or None: the window shows it while
    pc_disk waits, so a long first count doesn't look stuck."""
    with _walks_lock:
        going = [w for w in _walks.values() if not w.done.is_set()]
    if not going:
        return None
    w = max(going, key=lambda x: x.files)
    with w._cv:
        return w.files, w.counted


# ---------------------------------------------------------------- what the folders are
@dataclass(frozen=True)
class Rules:
    open: tuple[str, ...]           # folders shown by what is in them (Users, Program Files, AppData…)
    notes: tuple[tuple[str, str], ...]
    no_kinds: tuple[str, ...]       # kinds of files are counted outside these (Windows, programs, games)


_GAMES_OPEN = ("**/steamlibrary", "**/steamapps", "**/steamapps/common", "**/epic games", "**/riot games",
               "**/gog galaxy", "**/gog galaxy/games")
_GAME_NOTES = (
    ("**/steamapps/common/*", "a Steam game"),
    ("**/steamapps/shadercache", "Steam's shader cache: Steam makes it again"),
    ("**/steamapps/downloading", "unfinished Steam downloads"),
    ("**/steamapps/workshop", "Steam Workshop items (mods)"),
    ("**/steamapps", "Steam's games, their downloads and Workshop items"),
    ("**/epic games/*", "an Epic Games game: the Epic Games Launcher removes it"),
    ("**/riot games/*", "a Riot game: the Riot Client removes it"),
    ("**/gog galaxy/games/*", "a GOG game: GOG Galaxy removes it"),
)
_OWN = "the user's own files"
WIN_RULES = Rules(
    open=("users", "users/*", "users/*/appdata", "users/*/appdata/local", "users/*/appdata/roaming",
          "users/*/appdata/locallow", "users/*/appdata/local/microsoft", "users/*/appdata/local/packages",
          "program files", "program files (x86)", "programdata", "programdata/microsoft",
          "program files/steam", "program files (x86)/steam", "xboxgames", "games", *_GAMES_OPEN),
    notes=(
        ("users/*/.ollama", "Ollama's models (see Ollama models)"),
        ("users/*/appdata/local/temp", "temporary files: Disk Cleanup removes them"),
        ("users/*/appdata/local/nvidia", "the NVIDIA driver's shader cache (DXCache): safe to empty when no game "
                                         "runs, games make it again"),
        ("users/*/appdata/local/amd", "AMD's shader cache: AMD Software → Graphics → Reset Shader Cache"),
        ("users/*/appdata/local/d3dscache", "DirectX shader cache: Disk Cleanup removes it"),
        ("users/*/appdata/local/google/chrome/user data/optguideondevicemodel", "Chrome's built-in AI model"),
        ("users/*/appdata/local/google", "Chrome's profile and cache: Chrome → Delete browsing data → Cached "
                                         "images and files"),
        ("users/*/appdata/local/microsoft/edge", "Edge's profile and cache: Edge → Delete browsing data"),
        ("users/*/appdata/local/microsoft/windows", "Windows' own data of this user (search, thumbnails)"),
        ("users/*/appdata/local/microsoft/winget", "programs winget installed for this user"),
        ("users/*/appdata/local/packages/canonicalgroup*", "WSL Ubuntu: its Linux disk, which grows and doesn't "
                                                           "shrink by itself"),
        ("users/*/appdata/local/packages", "data of Microsoft Store apps"),
        ("users/*/appdata/local/packages/*", "a Microsoft Store app's data"),
        ("users/*/appdata/local/docker", "Docker's images and containers: 'docker system prune' removes unused "
                                         "ones"),
        ("users/*/appdata/local/pip", "pip's download cache: 'pip cache purge' empties it"),
        ("users/*/appdata/local/npm-cache", "npm's cache: 'npm cache clean --force' empties it"),
        ("users/*/appdata/local/programs", "programs installed for this user only (app_uninstall removes one)"),
        ("users/*/appdata/local/crashdumps", "crash reports: safe to delete"),
        ("users/*/appdata/local/android", "the Android SDK"),
        ("users/*/.android", "Android emulators: Android Studio → Device Manager removes them"),
        ("users/*/appdata/local/roblox", "Roblox and its cache"),
        ("users/*/appdata/local/spotify", "Spotify's cache: Spotify → Settings → Storage → Clear cache"),
        ("users/*/appdata/local/steam", "Steam's web cache"),
        ("users/*/appdata/roaming/telegram desktop", "Telegram's files and cache: Telegram → Settings → Advanced "
                                                     "→ Manage local storage"),
        ("**/tdata", "Telegram's files and cache: Telegram → Settings → Advanced → Manage local storage"),
        ("telegram*", "Telegram (its tdata folder keeps downloaded files and cache: Telegram → Settings → Advanced "
                      "→ Manage local storage)"),
        ("users/*/appdata/roaming/discord", "Discord and its cache"),
        ("users/*/appdata/roaming/code", "VS Code's data and caches"),
        ("users/*/appdata/roaming/prismlauncher", "Prism Launcher: Minecraft versions, instances and mods"),
        ("users/*/appdata/roaming/.minecraft", "Minecraft: versions, worlds and mods"),
        ("users/*/appdata/roaming/.tlauncher", "TLauncher (Minecraft)"),
        ("users/*/appdata/local", "programs' data and caches of this user"),
        ("users/*/appdata/roaming", "programs' data and settings of this user"),
        ("users/*/.gradle", "Gradle's cache: it downloads again what a build needs"),
        ("users/*/.m2", "Maven's cache: it downloads again what a build needs"),
        ("users/*/.nuget", "NuGet packages: 'dotnet nuget locals all --clear' empties them"),
        ("users/*/.cache", "caches of programs: most of it is safe to delete"),
        ("users/*/onedrive*", "OneDrive: files kept on this computer (OneDrive's 'Free up space' keeps them "
                              "online only)"),
        ("users/*/downloads", "the Downloads folder (" + _OWN + ")"),
        ("users/*/documents", _OWN), ("users/*/desktop", _OWN), ("users/*/pictures", _OWN),
        ("users/*/videos", _OWN), ("users/*/music", _OWN),
        *_GAME_NOTES,
        ("xboxgames/*", "an Xbox app game: the Xbox app removes it"),
        ("program files*/microsoft visual studio", "Visual Studio: the Visual Studio Installer removes parts "
                                                   "(Modify) or all of it"),
        ("programdata/microsoft/visualstudio", "Visual Studio's download cache: Visual Studio Installer → Modify → "
                                               "Installation locations → untick 'Keep download cache'"),
        ("programdata/package cache", "installers kept to repair and remove programs: leave it"),
        ("programdata/nvidia corporation", "NVIDIA's driver and app files, with downloaded driver updates"),
        ("programdata/microsoft/windows/wer", "Windows error reports: Disk Cleanup removes them"),
        ("programdata/microsoft/windows defender", "Microsoft Defender: leave it"),
        ("program files*/windowsapps", "Microsoft Store apps: Settings → Apps removes them"),
        ("program files*/steam", "Steam itself"),
        ("program files*/*", "a program (app_uninstall removes it)"),
        ("programdata/*", "programs' shared data"),
        ("windows", "Windows itself: leave it. WinSxS shares many files with System32, so it counts bigger here "
                    "than it is; Disk Cleanup → Clean up system files → Windows Update Cleanup trims it"),
        ("windows.old", "the previous Windows: Disk Cleanup → Clean up system files → Previous Windows "
                        "installation(s) removes it"),
        ("$windows.~bt", "left by a Windows upgrade: Disk Cleanup (Clean up system files) removes it"),
        ("$windows.~ws", "left by a Windows upgrade: Disk Cleanup (Clean up system files) removes it"),
        ("$winreagent", "files of a Windows update of the recovery tools"),
        ("$recycle.bin", "the Recycle Bin"),
        ("system volume information", "restore points and Windows' own files (closed)"),
        ("msys64", "MSYS2: compilers and tools"),
        ("mingw64", "MinGW: a C/C++ compiler"),
    ),
    no_kinds=("windows", "program files", "program files (x86)", "programdata", "$*", "system volume information",
              "windows.old", "xboxgames", "**/steamapps", "**/epic games", "**/riot games", "**/gog galaxy",
              "users/*/.ollama", "users/*/appdata/local/programs"),
)
LINUX_RULES = Rules(
    open=("home", "home/*", "home/*/.local", "home/*/.local/share", "home/*/.cache", "home/*/.var",
          "home/*/.var/app", "home/*/.config", "var", "var/lib", "opt", "home/*/.local/share/steam", *_GAMES_OPEN),
    notes=(
        ("home/*/.ollama", "Ollama's models (see Ollama models)"),
        ("home/*/.cache/*", "a program's cache: safe to delete, it makes it again"),
        ("home/*/.local/share/trash", "the Trash: emptying it frees the space"),
        ("home/*/.local/share/flatpak", "Flatpak apps installed for this user: 'flatpak uninstall --unused' "
                                        "removes runtimes no app needs"),
        ("home/*/.local/share/containers", "Podman's images: 'podman system prune' removes unused ones"),
        ("home/*/.var/app/*", "a Flatpak app's data"),
        ("home/*/.local/share/steam", "Steam"),
        ("home/*/.config/*", "a program's settings and data"),
        ("home/*/downloads", "the Downloads folder (" + _OWN + ")"),
        ("home/*/documents", _OWN), ("home/*/desktop", _OWN), ("home/*/pictures", _OWN),
        ("home/*/videos", _OWN), ("home/*/music", _OWN),
        *_GAME_NOTES,
        ("usr", "programs and the system (packages): removing programs frees it"),
        ("var/lib/flatpak", "Flatpak apps and runtimes: 'flatpak uninstall --unused' removes runtimes no app needs"),
        ("var/cache", "downloaded packages and caches: the package manager empties them ('sudo dnf clean all')"),
        ("var/log", "logs: 'sudo journalctl --vacuum-size=200M' trims them"),
        ("var/lib/*", "programs' data"),
        ("opt/*", "a program installed by hand"),
        ("boot", "the system's kernels: leave it"),
    ),
    no_kinds=("usr", "var", "opt", "boot", "**/steamapps", "home/*/.ollama", "home/*/.local/share/flatpak"),
)


def rules(win: bool) -> Rules:
    return WIN_RULES if win else LINUX_RULES


def disk_of(path: str, win: bool) -> str:
    """The root of the disk a path is on ("C:\\", or "/" on Linux)."""
    return (ntpath.splitdrive(ntpath.normpath(path))[0] or "C:") + "\\" if win else "/"


def _rel(path: str, disk: str) -> str:
    """The path below the disk's root, in lower case with "/" ("users/olena/appdata")."""
    low = path.replace("\\", "/").lower()
    top = disk.replace("\\", "/").lower().rstrip("/") + "/"
    return low[len(top):] if low.startswith(top) else low.lstrip("/")


def _match(rel: str, pattern: str) -> bool:
    parts, pats = rel.split("/"), pattern.split("/")
    if pats[0] == "**":
        pats = pats[1:]
        if len(parts) < len(pats):
            return False
        parts = parts[len(parts) - len(pats):]
    return len(parts) == len(pats) and all(fnmatchcase(a, b) for a, b in zip(parts, pats))


def _within(rel: str, patterns: Iterable[str]) -> bool:
    """The path or a folder above it matches one of the patterns."""
    parts = rel.split("/")
    heads = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    return any(_match(h, p) for p in patterns for h in heads)


def note(rel: str, r: Rules) -> str:
    return next((text for pattern, text in r.notes if _match(rel, pattern)), "")


def note_up(rel: str, r: Rules) -> str:
    """The note of this path or of the nearest folder above it that has one."""
    parts = rel.split("/")
    for i in range(len(parts), 0, -1):
        text = note("/".join(parts[:i]), r)
        if text:
            return text
    return ""


def children(sizes: dict[str, int]) -> dict[str, list[str]]:
    kids: dict[str, list[str]] = defaultdict(list)
    for p in sizes:
        up = os.path.dirname(p)
        if up != p:
            kids[up].append(p)
    return kids


def units(sizes: dict[str, int], root: str, r: Rules, disk: str, floor: int = FLOOR,
          kids: dict | None = None) -> list[tuple[int, str, bool]]:
    """The folders that say what takes the space, biggest first: (bytes, folder, rest). Open folders (Users,
    Program Files, AppData…) are shown by what is in them; rest=True is what an open folder has in folders
    smaller than floor."""
    kids = kids if kids is not None else children(sizes)
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        listed = 0
        for c in kids.get(p, ()):
            n = sizes.get(c, 0)
            if n < floor:
                continue
            listed += n
            if any(_match(_rel(c, disk), pat) for pat in r.open):
                todo.append(c)
            else:
                out.append((n, c, False))
        if p != root and sizes.get(p, 0) - listed >= floor:
            out.append((sizes[p] - listed, p, True))
    return sorted(out, reverse=True)


def _inside(sizes: dict[str, int], kids: dict, folder: str, n: int) -> str:
    """The biggest folders in a big one ("WinSxS 23.6 GB, System32 10.6 GB"), when it splits into a few."""
    if n < 2 * GB:
        return ""
    big = sorted(((sizes[c], c) for c in kids.get(folder, ()) if sizes[c] >= max(FLOOR, n * 0.15)), reverse=True)[:3]
    if not big or (len(big) == 1 and big[0][0] >= n * 0.9):
        return ""
    return " (inside: " + ", ".join(f"{os.path.basename(c)} {size_text(s)}" for s, c in big) + ")"


# ---------------------------------------------------------------- Steam's games
@dataclass(frozen=True)
class Game:
    appid: str
    name: str
    folder: str
    size: int


_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"')


def _vdf(text: str) -> list[tuple[str, str]]:
    """Steam's key-value files: ("path", "D:\\SteamLibrary") pairs, in order."""
    return [(k.lower(), v.replace("\\\\", "\\")) for k, v in _PAIR.findall(text)]


def steam_base(win: bool = sys.platform == "win32") -> Path | None:
    tries: list[Path] = []
    if win:
        try:
            import winreg
            for hive, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        tries.append(Path(str(winreg.QueryValueEx(k, name)[0])))
                except OSError:
                    continue
        except ImportError:
            pass
        tries.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
    else:
        h = Path.home()
        tries += [h / ".local/share/Steam", h / ".steam/steam", h / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    return next((p for p in tries if (p / "steamapps").is_dir()), None)


def steam_games(base: Path | None = None, win: bool = sys.platform == "win32") -> list[Game]:
    """Steam's installed games with the size Steam knows, biggest first (read from Steam's own files)."""
    base = base or steam_base(win)
    if not base:
        return []
    libs = [base]
    for f in (base / "steamapps" / "libraryfolders.vdf", base / "config" / "libraryfolders.vdf"):
        try:
            libs += [Path(v) for k, v in _vdf(f.read_text(encoding="utf-8", errors="replace")) if k == "path"]
        except OSError:
            continue
    seen: set[str] = set()
    games: dict[str, Game] = {}
    for lib in libs:
        key = os.path.normcase(os.path.normpath(str(lib)))
        if key in seen:
            continue
        seen.add(key)
        apps = lib / "steamapps"
        try:
            manifests = sorted(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for m in manifests:
            kv: dict[str, str] = {}
            try:
                for k, v in _vdf(m.read_text(encoding="utf-8", errors="replace")):
                    kv.setdefault(k, v)                    # the game's own name, not a name further down
            except OSError:
                continue
            appid, name, folder = kv.get("appid", ""), kv.get("name", ""), kv.get("installdir", "")
            if not appid.isdigit() or not name or appid in games:
                continue
            try:
                size = int(kv.get("sizeondisk") or 0)
            except ValueError:
                size = 0
            games[appid] = Game(appid, name, str(apps / "common" / folder) if folder else "", size)
    return sorted(games.values(), key=lambda g: -g.size)


# ---------------------------------------------------------------- the report
@dataclass
class Part:
    """A part of a report: its lines go away from the end, least needed parts first, when the text is too long."""
    name: str
    lines: list[str]
    title: str = ""
    keep: int = 0                   # lines that stay however long the text is


def fit(parts: list[Part], limit: int, order: Iterable[str]) -> str:
    """The parts as one text no longer than limit: lines go from the ends of the parts named in order (the least
    needed first) down to what each keeps; a title goes with its part's last line."""
    def text() -> str:
        out = []
        for p in parts:
            if p.lines:
                out += ([p.title] if p.title else []) + p.lines
        return "\n".join(out)

    if limit > 0:
        for name in order:
            for p in parts:
                while p.name == name and len(p.lines) > p.keep and len(text()) > limit:
                    p.lines.pop()
    out = text()
    return out if limit <= 0 or len(out) <= limit else out[:limit - 1] + "…"


def _under(path: str, folders: Iterable[str]) -> bool:
    low = os.path.normcase(path)
    return any(low == f or low.startswith(f.rstrip("\\/") + os.sep) for f in folders)


def _place_of(account: str, places: set[str], root: str) -> str:
    """The folder of the list that holds this one (or the folder right below the root)."""
    p = account
    while p not in places:
        up = os.path.dirname(p)
        if up == p or up == root or p == root:
            return p
        p = up
    return p


def game_disk(g: Game, win: bool) -> str:
    return disk_of(g.folder, win) if g.folder else ""


def game_part(games: list[Game], disk: str = "", win: bool = sys.platform == "win32", limit: int = 10) -> Part:
    """Steam's games on this disk by name, and a line for each other disk (they don't take space here)."""
    here = [g for g in games if not disk or os.path.normcase(game_disk(g, win)) == os.path.normcase(disk)]
    shown = [g for g in here if g.size >= 300 * MB][:limit]
    lines = [f"- {g.name} — {size_text(g.size)}" + ("" if disk else f" ({game_disk(g, win)})") for g in shown]
    rest = here[len(shown):]
    if shown and sum(g.size for g in rest) >= 100 * MB:
        lines.append(f"- {len(rest)} more, {size_text(sum(g.size for g in rest))} together")
    if disk:
        elsewhere: dict[str, list[Game]] = defaultdict(list)
        for g in games:
            if g not in here:
                elsewhere[game_disk(g, win) or "?"].append(g)
        for d, gs in sorted(elsewhere.items()):
            top = ", ".join(f"{g.name} {size_text(g.size)}" for g in gs[:2])
            lines.append(f"- on {d} (not this disk): {len(gs)} game{'' if len(gs) == 1 else 's'}, "
                         f"{size_text(sum(g.size for g in gs))} (the biggest: {top})")
    where = f" on {disk}" if disk else ""
    return Part("games", lines, f"Steam games{where} (sizes from Steam; pc_game_remove opens Steam's Uninstall for "
                                "one, on a card):", keep=3)


def other_disks(root: str, win: bool = sys.platform == "win32") -> list[tuple[str, int, int]]:
    """The computer's other fixed disks: (root, total, free). Only Windows has drive letters to list."""
    if not win:
        return []
    out = []
    try:
        import ctypes
        import string
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            d = f"{letter}:\\"
            if mask >> i & 1 and k32.GetDriveTypeW(d) == 3 and os.path.normcase(d) != os.path.normcase(root):
                try:
                    du = shutil.disk_usage(d)
                except OSError:
                    continue
                out.append((d, du.total, du.free))
    except (AttributeError, OSError):
        return []
    return out


def size_lookup(w: Walk, fallback: Callable[[str], tuple[int, bool]]) -> Callable[[str], tuple[int, bool]]:
    """(bytes, whole) of a folder from the walk (Temp, Windows.old…), or from fallback when the walk can't tell."""
    sizes = w.sizes()
    low: dict[str, int] = {}

    def get(path: str) -> tuple[int, bool]:
        try:
            real = os.path.realpath(path)               # Temp often comes in short 8.3 names (a user folder OLENA~1)
        except OSError:
            real = path
        rel = _rel(real, w.root)
        if not _under(real, [os.path.normcase(w.root)]) or _under(real, w.skip) or rel.count("/") + 1 > DEPTH:
            return fallback(path)                       # not walked (/tmp on Linux), or deeper than the sizes go
        if real in sizes:
            return sizes[real], w.whole
        if not low:
            low.update({os.path.normcase(k): v for k, v in sizes.items()})
        return low.get(os.path.normcase(real), 0), w.whole
    return get


def kind_part(w: Walk, sizes: dict[str, int], r: Rules, disk: str, kids: dict, title: str) -> Part:
    places = {c for _, c, rest in units(sizes, w.root, r, disk, floor=100 * MB, kids=kids) if not rest}
    rows = []
    for kind, where in w.kind_sizes().items():
        spots: dict[str, int] = defaultdict(int)
        for account, n in where.items():
            if r.no_kinds and _within(_rel(account, disk), r.no_kinds):
                continue                                   # program and game files count as programs and games
            spots[_place_of(account, places, w.root)] += n
        total = sum(spots.values())
        if total >= GB:
            most = sorted(((n, p) for p, n in spots.items() if n >= 100 * MB), reverse=True)[:3]
            rows.append((total, kind, most))
    lines = []
    for total, kind, most in sorted(rows, reverse=True):
        where = ", ".join(f"{p} {size_text(n)}" for n, p in most)
        lines.append(f"- {kind} — {size_text(total)}" + (f", most in {where}" if where else ""))
    return Part("kinds", lines, title)


def _listed_above(path: str, listed: set[str], root: str) -> str:
    p = os.path.dirname(path)
    while True:
        if os.path.normcase(p) in listed:
            return os.path.normcase(p)
        up = os.path.dirname(p)
        if up == p or p == root:
            return ""
        p = up


def file_part(w: Walk, r: Rules, disk: str, personal: list[str], show_files: bool, space_note: str,
              smallest: int = GB, rel_to: str = "", listed: Iterable[str] = ()) -> list[Part]:
    """The biggest files; a folder of the list above gets one of them at most (its cache files say no more)."""
    shown, hidden = [], 0
    listed = {os.path.normcase(p) for p in listed}
    had: set[str] = set()
    for n, path in w.biggest():
        if n < smallest:
            break
        rel = _rel(path, disk)
        if not rel_to and os.path.dirname(path) == w.root:
            continue                                       # hiberfil.sys and the like: Windows' own files
        if not rel_to and ("/.ollama/" in f"/{rel}" or "/steamapps/common/" in f"/{rel}"):
            continue                                       # models and games are listed whole
        if not show_files and _under(path, personal):
            hidden += 1
            continue
        unit = _listed_above(path, listed, w.root) if listed else ""
        if unit:
            if unit in had:
                continue
            had.add(unit)
        text = note_up(rel, r)
        shown.append(f"- {size_text(n)} — {os.path.relpath(path, rel_to) if rel_to else path}"
                     + (f": {text}" if text and not rel_to else ""))
        if len(shown) >= (10 if rel_to else 8):
            break
    parts = [Part("files", shown, "The biggest files" + (" in it:" if rel_to else ":"))]
    if hidden:
        parts.append(Part("hidden", [f"(The names of {hidden} big file{'' if hidden == 1 else 's'} in the user's own "
                                     f"folders aren't shown here: {space_note})"]))
    return parts


@dataclass
class Disk:
    total: int
    used: int
    free: int


def almost_full(disk: Disk) -> bool:
    return disk.free < disk.total * 0.1 or disk.free < 10 * GB


def uncounted(disk: Disk | None, counted: int, whole: bool) -> int:
    """Bytes the disk says are used that a whole walk couldn't count (restore points, closed folders), when that is
    a lot; else 0."""
    if not disk or not whole:
        return 0
    gap = disk.used - counted
    return gap if gap >= max(2 * GB, disk.used * 0.03) else 0


# ---------------------------------------------------------------- the window's figure of the disk
FIGURE_PARTS = 5                             # the biggest this many get a row of their own, the rest one together
_figures: dict[int, dict] = {}               # the last figure per thread: pc_disk runs in the answer's own thread


def figure(root: str, disk: Disk | None, tops: list[tuple[int, str]], loose: int, counted: int,
           whole: bool) -> dict:
    """What the window draws above the reply after a walk of the whole disk (and keeps with it on this computer):
    how full the disk is and what takes it — the biggest folders right on the disk and the files lying right in it
    (kind "files"), the rest together (kind "other"). Sizes in bytes; only the names of the folders on the disk."""
    items = [(n, {"name": os.path.basename(os.path.normpath(c)) or c, "size": n}) for n, c in tops if n > 0]
    if loose > 0:
        items.append((loose, {"kind": "files", "size": loose}))
    items.sort(key=lambda x: x[0], reverse=True)
    parts = [p for _, p in items[:FIGURE_PARTS]]
    rest = sum(n for n, _ in items[FIGURE_PARTS:])
    if rest:
        parts.append({"kind": "other", "size": rest})
    out = {"disk": root, "parts": parts, "counted": counted, "whole": whole}
    if disk:
        out.update(total=disk.total, used=disk.used, free=disk.free, low=almost_full(disk),
                   uncounted=uncounted(disk, counted, whole))
    return out


def keep(fig: dict) -> None:
    if len(_figures) > 16:                   # nobody took them (the terminal app, a regular task): not kept forever
        _figures.clear()
    _figures[threading.get_ident()] = fig


def take() -> dict | None:
    """The figure the last pc_disk of the whole disk made in this thread, once (sources.Noted takes it)."""
    return _figures.pop(threading.get_ident(), None)


def drive_parts(w: Walk, *, win: bool, disk: Disk | None, games: list[Game], personal: Iterable[Path] = (),
                show_files: bool = False, space_note: str = "") -> list[Part]:
    """pc_disk's report of a walk of the whole disk: the head, the biggest folders by what they are, what wasn't
    counted, the biggest files and kinds of files. The window's figure of it is kept for the answer (take)."""
    r = rules(win)
    root = w.root
    sizes = w.sizes()
    kids = children(sizes)
    counted = sizes.get(root, 0)
    head = []
    if disk:
        low = " — almost full" if almost_full(disk) else ""
        head.append(f"Disk {root} — {size_text(disk.free)} free of {size_text(disk.total)}{low}; "
                    f"{size_text(disk.used)} used.")
    if w.whole:
        head.append(f"Lanterna counted {size_text(counted)} of it in {w.files:,} files ({w.seconds():.0f} s).")
    else:
        head.append(f"Still counting ({w.files:,} files, {size_text(counted)} so far): the sizes below are at least "
                    "these. The count goes on by itself: asked again in a minute or two, pc_disk shows the whole "
                    "disk. Tell the user that, and don't guess the rest.")
    tops = sorted(((sizes[c], c) for c in kids.get(root, ())), reverse=True)
    short = [f"{os.path.basename(c)} {size_text(n)}" for n, c in tops if n >= GB]
    small = sum(n for n, _ in tops if n < GB)
    if small >= GB:
        short.append(f"other folders {size_text(small)}")
    loose = w.loose()
    if loose >= GB:
        short.append(f"files right in {root} {size_text(loose)}" + (" (hiberfil.sys, pagefile.sys…)" if win else ""))
    if short:
        head.append("In short: " + " · ".join(short))
    keep(figure(root, disk, tops, loose, counted, w.whole))
    others = other_disks(root, win)
    if others:
        head.append("Other disks (not counted here; pc_disk with folder looks at one): " +
                    " · ".join(f"{d} {size_text(free)} free of {size_text(total)}" for d, total, free in others))

    names = {os.path.normcase(os.path.normpath(g.folder)): g.name for g in games if g.folder}
    found = []
    biggest = units(sizes, root, r, root, kids=kids)[:25]
    for n, folder, rest in biggest:
        rel = _rel(folder, root)
        if rest:
            text = note(rel, r)
            found.append(f"- {folder} — {size_text(n)} in folders smaller than {size_text(FLOOR)} each"
                         + (f" ({text})" if text else ""))
            continue
        game = names.get(os.path.normcase(folder))
        text = f"the Steam game {game}" if game else note(rel, r)
        found.append(f"- {folder} — {size_text(n)}" + (f": {text}" if text else "") + _inside(sizes, kids, folder, n))

    missing = []
    gap = uncounted(disk, counted, w.whole)
    if gap:
        what = ("restore points and folders Windows keeps closed (System Volume Information), other users' files and "
                "files in use. Old restore points: pc_open_program 'System Protection' → Configure → Delete" if win
                else "folders only the administrator can open (/root, parts of /var) and other users' files")
        missing.append(f"Not counted: about {size_text(gap)} — {what}.")
    if w.online >= GB:
        missing.append(f"Files kept only online (OneDrive): {size_text(w.online)}, taking no space here.")
    return [Part("head", head, keep=99),
            Part("units", found, "The biggest, by what they are (to look inside one: pc_disk with folder):", keep=8),
            Part("uncounted", missing, keep=1),
            *file_part(w, r, root, [os.path.normcase(str(p)) for p in personal], show_files, space_note,
                       listed=[f for _, f, rest in biggest if not rest]),
            kind_part(w, sizes, r, root, kids, "Kinds of files (outside Windows, programs and games):")]


def folder_path(folder: str, home: Path) -> Path:
    """A folder the model names: a whole path, a drive ("D:"), or a path below the profile ("AppData\\Local")."""
    raw = str(folder or "").strip().strip("\"'")
    if re.fullmatch(r"[A-Za-z]:[\\/]?", raw):
        raw = raw[:2] + "\\"
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else home / p


def folder_parts(w: Walk, *, win: bool, games: list[Game], personal: Iterable[Path] = (),
                 show_files: bool = False, space_note: str = "") -> list[Part]:
    """pc_disk with folder: what is in one folder, biggest first."""
    r = rules(win)
    root = w.root
    disk = disk_of(root, win)
    sizes = w.sizes()
    kids = children(sizes)
    total = sizes.get(root, 0)
    text = note_up(_rel(root, disk), r)
    head = [f"{root} — {size_text(total)}" + ("" if w.whole else " so far (still counting: the sizes are at least "
                                                                 "these; asked again in a minute, pc_disk shows all)")
            + f" in {w.files:,} files (only looked, nothing changed)" + (f": {text}" if text else "") + "."]
    personal = [os.path.normcase(str(p)) for p in personal]
    if not show_files and _under(root, personal):      # the user's own folder: its sizes, not the names in it
        head.append(f"It is one of the user's own folders: the names in it aren't shown here ({space_note}).")
        kinds = sorted(((sum(where.values()), kind) for kind, where in w.kind_sizes().items()), reverse=True)
        return [Part("head", head, keep=99),
                Part("kinds", [f"- {k} — {size_text(n)}" for n, k in kinds if n >= 100 * MB], "Kinds of files in it:")]
    names = {os.path.normcase(os.path.normpath(g.folder)): g.name for g in games if g.folder}
    floor = max(10 * MB, total * 0.005)
    lines = []
    for n, c in sorted(((sizes[c], c) for c in kids.get(root, ()) if sizes[c] >= floor), reverse=True)[:20]:
        game = names.get(os.path.normcase(c))
        t = f"the Steam game {game}" if game else note(_rel(c, disk), r)
        lines.append(f"- {os.path.basename(c)} — {size_text(n)}" + (f": {t}" if t else "") + _inside(sizes, kids, c, n))
    if w.loose() >= 10 * MB:
        lines.append(f"- files right in it — {size_text(w.loose())}")
    kinds = sorted(((sum(where.values()), kind) for kind, where in w.kind_sizes().items()), reverse=True)
    return [Part("head", head, keep=99), Part("units", lines, "Folders in it:", keep=8),
            *file_part(w, r, disk, personal, show_files, space_note, smallest=20 * MB, rel_to=root),
            Part("kinds", [f"- {k} — {size_text(n)}" for n, k in kinds if n >= 100 * MB], "Kinds of files in it:")]
