"""What takes up the disk, wider than the user's own folders (pcfiles.space_report, pc_space): the biggest
folders of the user's profile (AppData on Windows, ~/.cache and the like on Linux), the biggest installed
programs, Ollama models and the system's own files (Windows.old, the hibernation file, update downloads).

It only looks. The cards next to it remove an Ollama model and turn on Help free up disk space.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .pcfiles import GB, MB, size_text, trash_size

BUDGET = 15.0                     # seconds for counting the profile: it can have a million files
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
PARTS = ("profile", "programs", "models", "system")
# A word about well-known big folders (paths below the profile, lower case, "/" between folders)
NOTES = {
    "appdata/local/temp": "temporary files: Disk Cleanup removes them",
    "appdata/local/packages": "data of Microsoft Store apps, each app's own",
    "appdata/local/docker": "Docker's images and containers: 'docker system prune' removes unused ones",
    "appdata/local/pip": "pip's download cache: 'pip cache purge' empties it",
    "appdata/local/npm-cache": "npm's cache: 'npm cache clean --force' empties it",
    "appdata/local/programs": "programs installed for this user only (see the programs below)",
    "appdata/local/microsoft/winget": "programs winget installed for this user",
    "appdata/local/crashdumps": "crash reports: safe to delete",
    "appdata/local/nvidia": "the graphics driver's shader cache: Disk Cleanup (DirectX Shader Cache) or the driver "
                            "rebuilds it",
    "appdata/local/d3dscache": "shader cache: Disk Cleanup (DirectX Shader Cache) removes it",
    "appdata/local/google": "Chrome's profile and cache: Chrome's own 'Delete browsing data' empties the cache",
    "appdata/local/microsoft/edge": "Edge's profile and cache: Edge's own 'Delete browsing data' empties the cache",
    "appdata/local/android": "the Android SDK and emulators",
    "appdata/roaming/code": "VS Code's settings, extensions data and caches",
    ".ollama": "Ollama models (see below)",
    ".gradle": "Gradle's cache (Java/Android builds): it downloads again what a build needs",
    ".m2": "Maven's cache (Java builds): it downloads again what a build needs",
    ".nuget": "NuGet packages (.NET builds): 'dotnet nuget locals all --clear' empties it",
    ".cache": "caches of programs: most of it is safe to delete, programs make it again",
    ".var/app": "data of Flatpak apps, each app's own",
    ".local/share/trash": "the Trash",
    ".local/share/steam": "Steam games",
}


class Counter:
    """Counts folder sizes until the time is up (then a size says 'at least')."""

    def __init__(self, budget: float = BUDGET, now: Callable[[], float] = time.monotonic):
        self.now, self.budget, self.deadline, self.cut = now, budget, None, False

    def size(self, root: str) -> tuple[int, bool]:
        """(bytes, complete). Links and junctions are skipped (AppData\\Application Data points at itself)."""
        if self.deadline is None:                      # the time starts with the first folder
            self.deadline = self.now() + self.budget
        total, stack, whole = 0, [root], True
        while stack:
            if self.now() > self.deadline:
                self.cut = True
                return total, False
            folder = stack.pop()
            try:
                with os.scandir(folder) as it:
                    for e in it:
                        try:
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if getattr(st, "st_file_attributes", 0) & REPARSE or stat.S_ISLNK(st.st_mode):
                            continue
                        if stat.S_ISDIR(st.st_mode):
                            stack.append(e.path)
                        else:
                            total += st.st_size
            except OSError:
                whole = False                          # a folder this user can't read (Windows.old has many)
        return total, whole


def _dirs(folder: Path) -> list[Path]:
    out = []
    try:
        for e in os.scandir(folder):
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode) and not (getattr(st, "st_file_attributes", 0) & REPARSE or stat.S_ISLNK(st.st_mode)):
                out.append(Path(e.path))
    except OSError:
        pass
    return out


def _sized(n: int, whole: bool) -> str:
    return size_text(n) if whole else f"at least {size_text(n)}"


def _note(rel: str) -> str:
    key = rel.replace("\\", "/").lower()
    hit = next((v for k, v in NOTES.items() if key == k or key.startswith(k + "/")), "")
    return f" ({hit})" if hit else ""


def profile(home: Path, counter: Counter, win: bool) -> list[str]:
    """The biggest folders of the profile, and the biggest folders inside AppData (or ~/.cache, ~/.local/share)."""
    inner = [home / "AppData" / "Local", home / "AppData" / "Roaming"] if win else \
        [home / ".cache", home / ".local" / "share", home / ".var" / "app", home / ".config"]
    inner = [p for p in inner if p.is_dir()]
    holders = {home / p.relative_to(home).parts[0] for p in inner}        # AppData, .local, .cache…
    tops = [p for p in _dirs(home) if p not in holders]
    # what else a holder has (AppData\LocalLow, ~/.local/bin): counted whole, next to the inner folders' children
    rest = [q for h in holders if h not in inner for q in _dirs(h)
            if q not in inner and not any(q in i.parents for i in inner)]
    parts = [q for p in inner for q in _dirs(p)] + rest
    jobs = tops + parts
    with ThreadPoolExecutor(max_workers=4) as ex:
        sizes = dict(zip(jobs, ex.map(lambda p: counter.size(str(p)), jobs)))
    totals: dict[Path, list] = {p: [*sizes[p]] for p in tops}
    for q in parts:                                    # a holder's size: the sum of what is inside it
        row = totals.setdefault(home / q.relative_to(home).parts[0], [0, True])
        row[0] += sizes[q][0]
        row[1] = row[1] and sizes[q][1]
    rows = sorted(((n, whole, p) for p, (n, whole) in totals.items() if n >= 100 * MB), reverse=True)[:10]
    lines = [f"Biggest folders of the profile {home}:"] if rows else []
    lines += [f"- {p.name} — {_sized(n, whole)}{_note(p.name)}" for n, whole, p in rows]
    deep = sorted(((sizes[q][0], sizes[q][1], q) for q in parts if sizes[q][0] >= 200 * MB), reverse=True)[:12]
    if deep:
        lines.append(f"Biggest inside {', '.join(str(p.relative_to(home)) for p in inner)}:")
        lines += [f"- {q.relative_to(home)} — {_sized(n, whole)}{_note(str(q.relative_to(home)))}"
                  for n, whole, q in deep]
    return lines


def win_programs(limit: int = 12) -> list[tuple[int, str]]:
    """The biggest installed programs as they tell Windows (EstimatedSize in the uninstall list)."""
    import winreg
    rows: dict[str, tuple[int, str]] = {}
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            k = winreg.OpenKey(root, key)
        except OSError:
            continue
        with k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                try:
                    with winreg.OpenKey(k, winreg.EnumKey(k, i)) as s:
                        vals = {}
                        for j in range(winreg.QueryInfoKey(s)[1]):
                            n, v, _ = winreg.EnumValue(s, j)
                            vals[n] = v
                except OSError:
                    continue
                name, size = str(vals.get("DisplayName") or "").strip(), vals.get("EstimatedSize")
                if not name or not isinstance(size, int) or size <= 0 or vals.get("SystemComponent") == 1 \
                        or vals.get("ParentKeyName"):
                    continue
                rows[name.lower()] = max(rows.get(name.lower(), (0, name)), (size * 1024, name))
    return sorted(rows.values(), reverse=True)[:limit]


def _flatpak_size(text: str) -> int:
    num, _, unit = text.replace("\xa0", " ").strip().partition(" ")
    try:
        return int(float(num.replace(",", ".")) * {"kB": 1e3, "MB": 1e6, "GB": 1e9, "bytes": 1}.get(unit, 1))
    except ValueError:
        return 0


def linux_programs(run: Callable, limit: int = 10) -> list[str]:
    lines = []
    code, out = run(["flatpak", "list", "--app", "--columns=name,size"], timeout=15)
    if code == 0:
        rows = sorted(((_flatpak_size(r.split("\t")[-1]), r.split("\t")[0]) for r in out.splitlines() if "\t" in r),
                      reverse=True)[:limit]
        if rows:
            lines.append("Biggest Flatpak apps:")
            lines += [f"- {name} — {size_text(n)}" for n, name in rows if n]
    code, out = run(["rpm", "-qa", "--queryformat", "%{SIZE}\\t%{NAME}\\n"], timeout=20)
    kb = 1
    if code != 0:
        code, out = run(["dpkg-query", "-W", "-f=${Installed-Size}\\t${Package}\\n"], timeout=20)
        kb = 1024
    if code == 0:
        rows = []
        for r in out.splitlines():
            n, _, name = r.partition("\t")
            if n.strip().isdigit() and name:
                rows.append((int(n) * kb, name.strip()))
        rows = sorted(rows, reverse=True)[:limit]
        if rows:
            lines.append("Biggest system packages:")
            lines += [f"- {name} — {size_text(n)}" for n, name in rows]
    return lines


def ollama_folder() -> Path | None:
    env = os.environ.get("OLLAMA_MODELS")
    for p in ([Path(env)] if env else []) + [Path.home() / ".ollama" / "models",
                                              Path("/usr/share/ollama/.ollama/models")]:
        if p.is_dir():
            return p
    return None


def models(installed: Callable[[], list], running: Callable[[], object], counter: Counter) -> list[str]:
    if running():
        found = sorted(installed(), key=lambda m: -m.size_gb)
        if not found:
            return ["Ollama models: none downloaded."]
        return ["Ollama models (pc_model_remove removes one, with a card; Settings > Local models downloads "
                "them again):"] + [f"- {m.name} — {m.size_gb:.1f} GB" for m in found]
    folder = ollama_folder()
    if not folder:
        return []
    n, whole = counter.size(str(folder))
    return [f"Ollama isn't running: its models folder {folder} has {_sized(n, whole)} (start Ollama to see and "
            "remove single models)."] if n >= 100 * MB else []


def win_system(counter: Counter) -> list[str]:
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    root: dict[str, int] = {}
    try:
        with os.scandir(drive) as it:                  # locked files: the listing still knows their size
            for e in it:
                if e.name.lower() in ("hiberfil.sys", "pagefile.sys", "swapfile.sys"):
                    try:
                        root[e.name.lower()] = e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
    except OSError:
        pass
    lines = []
    if root.get("hiberfil.sys", 0) >= 500 * MB:
        lines.append(f"- hiberfil.sys (for hibernation and Fast Startup) — {size_text(root['hiberfil.sys'])}: "
                     "turning hibernation off removes it ('powercfg /h off' in a terminal run as administrator; "
                     "hibernation and Fast Startup go with it). Lanterna doesn't change it.")
    for name, what in (("pagefile.sys", "virtual memory"), ("swapfile.sys", "for Store apps")):
        if root.get(name, 0) >= 500 * MB:
            lines.append(f"- {name} ({what}) — {size_text(root[name])}: Windows manages it, leave it.")
    old = Path(drive) / "Windows.old"
    if old.is_dir():
        n, whole = counter.size(str(old))
        lines.append(f"- Windows.old (the previous Windows, kept for about 10 days to go back) — {_sized(n, whole)}: "
                     "Disk Cleanup removes it ('Clean up system files' → 'Previous Windows installation(s)').")
    upd = Path(os.environ.get("SystemRoot", drive + "Windows")) / "SoftwareDistribution" / "Download"
    if upd.is_dir():
        n, whole = counter.size(str(upd))
        if n >= 500 * MB:
            lines.append(f"- Windows update downloads — {_sized(n, whole)}: Disk Cleanup removes them ('Clean up "
                         "system files' → 'Windows Update Cleanup').")
    return ["Windows' own files:"] + lines if lines else []


def report(part: str = "", *, home: Path | None = None, platform: str = sys.platform, run: Callable | None = None,
           installed: Callable[[], list] | None = None, running: Callable[[], object] | None = None,
           space_help: bool = True, programs: Callable[[], list] | None = None, budget: float = BUDGET) -> str:
    from . import local
    from .apps import run_cmd
    win = platform == "win32"
    home = home or Path.home()
    run = run or run_cmd
    part = part if part in PARTS else ""
    counter, small = Counter(budget), Counter(min(budget, 5.0))   # Windows.old, Temp, the models: their own time
    lines = ["What takes up the disk (only looked, nothing changed):"]
    try:
        du = shutil.disk_usage(home)
        low = " — almost full" if du.free < du.total * 0.1 or du.free < 10 * GB else ""
        lines.append(f"Disk with the profile: {size_text(du.free)} free of {size_text(du.total)}{low}")
    except OSError:
        pass
    if part in ("", "profile"):
        lines += profile(home, counter, win)
    if part in ("", "programs"):
        try:
            if win:
                rows = (programs or win_programs)()
                if rows:
                    lines.append("Biggest programs (as they report it; app_uninstall removes one, with a card):")
                    lines += [f"- {name} — {size_text(n)}" for n, name in rows]
            else:
                lines += linux_programs(run)
        except Exception:                              # noqa: BLE001  the rest of the report still helps
            pass
    if part in ("", "models"):
        lines += models(installed or local.installed, running or local.version, small)
    if part in ("", "system"):
        if win:
            lines += win_system(small)
        tmp, whole = small.size(tempfile.gettempdir())
        lines.append(f"Recycle Bin: {size_text(trash_size())}; temporary files: {_sized(tmp, whole)}.")
        if win:
            lines.append("Windows' Disk Cleanup removes temporary files, update leftovers and Windows.old: "
                         "pc_open_program with 'disk cleanup' opens it (then 'Clean up system files'). Settings > "
                         "System > Storage shows the same and has Storage Sense (pc_settings_page storage).")
    if not space_help:
        lines.append("Help free up disk space is off: with it on, Lanterna can look through the user's own folders "
                     "for big and old files and old installers (pc_space) and warns once a day when the disk is "
                     "almost full. pc_space_on offers to turn it on (a card).")
    if counter.cut or small.cut:
        lines.append("(Counting stopped to save time: sizes marked 'at least' may be bigger.)")
    return "\n".join(lines)
