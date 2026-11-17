"""Programming tools on this computer: where the compilers and runtimes are (g++, python, node, java…), whether
a terminal opened now finds them (PATH) and what is known to break them. The usual one on Windows: GCC (MinGW)
in a folder whose path has non-English letters fails with "Illegal byte sequence" or "cannot find -lmingw32"
(winget puts WinLibs into the user's folder, and C:\\Users\\Олена is such a path).

It only looks: it runs each tool's --version and changes nothing.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .apps import VS_PARTS, VS_YEARS, run_cmd
from .tools import Tool, _obj

# (command, what it is, other commands for the same thing)
CHECKS = (
    ("g++", "C++ compiler, GCC/MinGW", ()),
    ("gcc", "C compiler, GCC/MinGW", ()),
    ("gdb", "debugger for GCC, VS Code uses it", ()),
    ("clang++", "C++ compiler, Clang", ("clang",)),
    ("python", "Python", ("python3", "py")),
    ("node", "Node.js, JavaScript", ()),
    ("java", "Java, runs programs", ()),
    ("javac", "Java compiler, JDK", ()),
    ("dotnet", ".NET, C#", ()),
    ("git", "Git", ()),
    ("code", "VS Code", ()),
)
GCC = ("g++", "gcc", "gdb")                  # MinGW: non-English letters in its folder, TEMP or the code's folder break it
ONLY = {"c++": GCC + ("clang++", "msvc"), "cpp": GCC + ("clang++", "msvc"), "c": ("gcc", "clang++"),
        "mingw": GCC, "msvc": ("msvc",), "cl": ("msvc",), "visual studio": ("msvc",), "js": ("node",),
        "javascript": ("node",), "npm": ("node",), "python3": ("python",), "py": ("python",), "jdk": ("java", "javac"),
        "java": ("java", "javac"), "c#": ("dotnet",), "vscode": ("code",), "vs code": ("code",), "clang": ("clang++",)}
# Where they are usually installed on Windows: found there but not in PATH = "add this folder to Path"
WIN_PLACES = {
    "g++": (r"C:\mingw64\bin", r"C:\mingw32\bin", r"C:\MinGW\bin", r"C:\msys64\ucrt64\bin", r"C:\msys64\mingw64\bin",
            r"C:\msys64\clang64\bin", r"C:\TDM-GCC-64\bin", r"%PROGRAMFILES%\CodeBlocks\MinGW\bin",
            r"%PROGRAMFILES(X86)%\CodeBlocks\MinGW\bin", r"C:\ProgramData\mingw64\mingw64\bin",
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs*\mingw64\bin",
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs*\mingw32\bin"),
    "python": (r"%LOCALAPPDATA%\Programs\Python\Python3*", r"%PROGRAMFILES%\Python3*", r"C:\Python3*"),
    "node": (r"%PROGRAMFILES%\nodejs",),
    "java": (r"%PROGRAMFILES%\Java\*\bin", r"%PROGRAMFILES%\Eclipse Adoptium\*\bin", r"%PROGRAMFILES%\Microsoft\jdk-*\bin",
             r"%PROGRAMFILES%\Zulu\*\bin", r"%PROGRAMFILES%\Amazon Corretto\*\bin"),
    "dotnet": (r"%PROGRAMFILES%\dotnet",),
    "git": (r"%PROGRAMFILES%\Git\cmd",),
    "code": (r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin", r"%PROGRAMFILES%\Microsoft VS Code\bin"),
}
WIN_PLACES["gcc"] = WIN_PLACES["gdb"] = WIN_PLACES["g++"]
WIN_PLACES["javac"] = WIN_PLACES["java"]
VERSION_ARGS = {"java": ["-version"], "javac": ["-version"]}       # Java 8 doesn't know --version
TIMEOUT = 8.0
WIN_CODES = {0xC0000135: "a file it needs (a DLL) is missing: install it again, as a whole folder",
             0xC000007B: "its files are mixed up (32-bit and 64-bit): install it again"}
SAFE_MINGW = "C:\\mingw64"


def _expand(s: str, env: dict[str, str]) -> str:
    return re.sub(r"%([^%;]+)%", lambda m: env.get(m.group(1).upper(), m.group(0)), s)


def _registry() -> tuple[dict[str, str], dict[str, str]]:
    """The system and the user variables as Windows keeps them now (values not expanded)."""
    import winreg
    out = []
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        values: dict[str, str] = {}
        try:
            with winreg.OpenKey(root, key) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    if isinstance(value, str):
                        values[name.upper()] = value
        except OSError:
            pass
        out.append(values)
    return out[0], out[1]


def current_env(platform: str = sys.platform) -> dict[str, str]:
    """PATH, TEMP and the rest as a terminal opened now gets them. Lanterna's own copy is from when it started,
    and the user may have changed Path since (Windows: the system Path first, then the user's)."""
    env = {k.upper(): v for k, v in os.environ.items()}
    if platform != "win32":
        return env
    try:
        system, user = _registry()
    except Exception:                                    # noqa: BLE001  no registry: Lanterna's own copy
        return env
    names = {**env, **system, **user}
    names = {k: _expand(v, names) for k, v in names.items()}
    path = ";".join(p for p in (_expand(system.get("PATH", ""), names), _expand(user.get("PATH", ""), names)) if p)
    return {**names, "PATH": path or env.get("PATH", "")}


def _is_win(platform: str) -> bool:
    return platform == "win32"


def path_dirs(env: dict[str, str], win: bool) -> list[str]:
    return [d.strip().strip('"') for d in env.get("PATH", "").split(";" if win else os.pathsep) if d.strip().strip('"')]


def find_all(cmd: str, dirs: list[str], env: dict[str, str], win: bool) -> list[str]:
    """Every match in PATH, in its order (the first one is what a terminal runs)."""
    exts = [e.lower() for e in env.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e] if win else [""]
    out, seen = [], set()
    for d in dirs:
        for e in exts:
            p = os.path.join(d, cmd + e)
            key = os.path.normcase(os.path.abspath(p))
            if key not in seen and os.path.exists(p) and not os.path.isdir(p):
                seen.add(key)
                out.append(p)
                break
    return out


STUB = ("only the Microsoft Store shortcut, not the program itself (without arguments it opens the Store; "
        "Settings > Apps > Advanced app settings > App execution aliases turns it off)")


def version(exe: str, cmd: str, run: Callable) -> str:
    code, out = run([exe, *VERSION_ARGS.get(cmd, ["--version"])], timeout=TIMEOUT)
    u = code & 0xFFFFFFFF if isinstance(code, int) else code
    if u == 124 and "took too long" in out:
        return "doesn't answer (took too long)"
    if u == 9009 and re.search(r"[\\/]microsoft[\\/]windowsapps[\\/]", exe, re.I):
        return STUB                       # WindowsApps\python.exe without that Python: with --version it only says so
    if u in WIN_CODES:
        return f"doesn't start: {WIN_CODES[u]} (0x{u:08X})"
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    first = lines[0][:120] if lines else ""
    if code == 0:
        return first or "runs"
    return f"doesn't start (code {code})" + (f": {first}" if first else "")


def _show(p: str) -> str:
    real = os.path.realpath(p)
    return p if os.path.normcase(real) == os.path.normcase(p) else f"{real} (through the link {p})"


def _vs_id(inst: dict) -> str:
    year = {v: k for k, v in VS_YEARS.items()}.get(inst.get("major", 0))
    return f"Microsoft.VisualStudio.{year + '.' if year else ''}{inst.get('edition') or 'Community'}"


def check(only: str = "", *, env: dict[str, str] | None = None, run: Callable = run_cmd, platform: str = sys.platform,
          vs: Callable[[str], list[dict]] | None = None, home: str | None = None, places: dict | None = None) -> str:
    win = _is_win(platform)
    env = current_env(platform) if env is None else {k.upper(): v for k, v in env.items()}
    places = WIN_PLACES if places is None else places
    key = " ".join(str(only or "").lower().split())
    wanted = set(ONLY.get(key, ())) or {c for c, _, alts in CHECKS if key in (c, *alts)}
    rows = [r for r in CHECKS if not wanted or r[0] in wanted]
    dirs = path_dirs(env, win)
    hits = {c: find_all(c, dirs, env, win) for cmd, _, alts in rows for c in (cmd, *alts)}
    runs = {c: h[0] for c, h in hits.items() if h}
    with ThreadPoolExecutor(max_workers=6) as ex:
        ver = dict(zip(runs, ex.map(lambda c: version(os.path.realpath(runs[c]), c, run), runs)))

    lines = ["Programming tools on this computer (Windows; PATH as a terminal opened now gets it). Only looked, "
             "nothing changed:" if win else "Programming tools on this computer. Only looked, nothing changed:"]
    missing, problems, gcc_dirs = [], [], []
    for cmd, what, alts in rows:
        said = []
        for c in (cmd, *alts):
            h = hits[c]
            if not h:
                continue
            if ver[c] == STUB:
                said.append(f"{c} → {h[0]}: {STUB}")
                continue
            more = [os.path.dirname(x) for x in h[1:3]]
            said.append(f"{c} → {_show(h[0])} — {ver[c]}" +
                        (f" (PATH also has it in {', '.join(more)}: the first one is used)" if more else ""))
            if cmd in GCC:
                gcc_dirs.append((c, h))
        if said:
            lines.append(f"- {cmd} ({what}): " + "; ".join(said))
            continue
        hint = _not_in_path(cmd, dirs, env, win, places)
        if hint:
            lines.append(f"- {cmd} ({what}): {hint}")
        else:
            missing.append(cmd)
    if win and (not wanted or "msvc" in wanted) and vs is not None:
        lines += [x for x in (_msvc(vs),) if x]
    if missing:
        lines.append("- not found: " + ", ".join(missing))
    if win and gcc_dirs:
        problems += _gcc_problems(gcc_dirs, env, home if home is not None else str(Path.home()))
    gone = [d for d in dirs if not os.path.exists(_expand(d, env))]
    files = [d for d in dirs if os.path.isfile(d)]
    if files:
        problems.append("Path has a file instead of a folder: " + ", ".join(files[:3]) +
                        ". Path needs the folder (without the file name at the end).")
    if gone and not wanted:
        problems.append("Path has folders that don't exist (harmless, unless one is a typo for a program above): " +
                        ", ".join(gone[:5]))
    if problems:
        lines.append("What breaks them:")
        lines += [f"- {p}" for p in problems]
    if win:
        lines.append("After any change to Path or TEMP: close and open again VS Code and every terminal (they keep "
                     "the old values).")
    return "\n".join(lines)


def _not_in_path(cmd: str, dirs: list[str], env: dict[str, str], win: bool, places: dict) -> str:
    """Installed, but a new terminal doesn't find it (a common mistake: Path has the folder above bin)."""
    exts = (".exe", ".cmd", ".bat") if win else ("",)
    for d in dirs:
        for e in exts:
            if os.path.isfile(os.path.join(d, "bin", cmd + e)):
                return (f"installed in {os.path.join(d, 'bin')}, but Path has {d} (the folder above): put "
                        f"{os.path.join(d, 'bin')} in Path instead")
    if not win:
        return ""
    for place in places.get(cmd, ()):
        for folder in sorted(glob.glob(_expand(place, env)), reverse=True):
            for e in exts:
                if os.path.isfile(os.path.join(folder, cmd + e)):
                    return (f"installed in {folder}, but a terminal doesn't find it (not in Path): add {folder} "
                            "to Path (the user variables)")
    return ""


def _msvc(vs: Callable[[str], list[dict]]) -> str:
    try:
        with_cpp = vs(VS_PARTS["cpp"][3])
        every = with_cpp or vs("")
    except Exception:                                    # noqa: BLE001  vswhere doesn't answer: nothing to say
        return ""
    if with_cpp:
        names = ", ".join(i["name"] for i in with_cpp)
        return (f"- MSVC (cl.exe, the C++ compiler of Visual Studio): in {names}. It isn't in the usual PATH, "
                "on purpose: build in Visual Studio, or open 'Developer PowerShell for VS' from the Start menu and "
                "run cl there. It has no trouble with non-English letters in paths.")
    if every:
        i = every[0]
        return (f"- MSVC (the C++ compiler of Visual Studio): {i['name']} is installed without C++. "
                f"app_install {_vs_id(i)} with parts ['cpp'] adds it.")
    return "- MSVC (the C++ compiler of Visual Studio): Visual Studio isn't installed"


def _latin(p: str) -> bool:
    """Only English letters, digits and signs: GCC (MinGW) works from such a path."""
    return p.isascii()


def _gcc_problems(found: list[tuple[str, list[str]]], env: dict[str, str], home: str) -> list[str]:
    out = []
    used = os.path.realpath(found[0][1][0])
    bin_dir = os.path.dirname(used)
    if not _latin(used):
        root = os.path.dirname(bin_dir) if os.path.basename(bin_dir).lower() == "bin" else bin_dir
        good = next((os.path.dirname(x) for _, h in found for x in h[1:] if _latin(os.path.realpath(x))), "")
        safe_bin = os.path.join(SAFE_MINGW, "bin")
        if good:
            fix = f"in Path (the user variables), move {good} above that folder, or remove that folder from Path"
        elif os.path.isfile(os.path.join(safe_bin, "g++.exe")):
            fix = f"{safe_bin}\\g++.exe is already there: put {safe_bin} at the top of Path and remove that folder"
        else:
            fix = (f"copy the whole folder {root} to {SAFE_MINGW} (so it is {safe_bin}\\g++.exe), put {safe_bin} at "
                   "the top of Path (the user variables) and remove that folder from it")
        out.append(f"The GCC that runs is in a folder whose path has non-English letters: {bin_dir}. GCC can't work "
                   f"from there: it fails with 'Illegal byte sequence' or 'cannot find -lmingw32'. Fix: {fix}. Or use "
                   "Visual Studio with C++ instead (app_install with parts ['cpp']): it has no such problem.")
    temp = next((env[n] for n in ("TEMP", "TMP") if env.get(n) and not _latin(env[n])), "")
    if temp:
        out.append(f"The folder for temporary files ({temp}) has non-English letters: GCC writes its temporary "
                   "files there and can fail with the same errors. Fix: make the folder C:\\Temp and set the user "
                   "variables TEMP and TMP to C:\\Temp.")
    if home and not _latin(home):
        out.append(f"The user folder {home} has non-English letters: with GCC keep the code in a folder with English "
                   "letters only, like D:\\code or C:\\code (not in Documents or on the Desktop), or GCC can't "
                   "write the program ('cannot open output file').")
    return out


def dev_tools(vs: Callable[[str], list[dict]] | None = None) -> list[Tool]:
    return [Tool("pc_dev", "Programming tools on this computer: where g++/gcc (MinGW), gdb, clang, python, node, "
                 "java, dotnet, git and VS Code are, their versions, whether a terminal finds them (PATH), the C++ "
                 "compiler of Visual Studio, and what is known to break them (GCC in a folder with non-English "
                 "letters, TEMP, mistakes in Path). Only looks. Call it first when a compiler or tool 'doesn't "
                 "work', 'isn't found', 'is not recognized' or gives 'Illegal byte sequence' / 'cannot find -l…', "
                 "and before you suggest installing a compiler.",
                 _obj({"only": {"type": "string", "description": "optional: one thing to check, e.g. c++, python, "
                                                                 "node, java, vscode (default: all)"}}),
                 lambda only="": check(only, vs=vs), "🧰")]
