"""Programs: find, install, update and remove them with the system's own package manager.

- Windows: winget, only its official catalog (source "winget").
- Linux: Flatpak (the remotes this computer already has: a user remote needs no password, a system one - like
  Flathub and Fedora's on Fedora - asks for it) and the distribution's dnf/apt (through pkexec, which asks for the
  password itself). A search looks in all of them and keeps only programs that have the words asked for: Flatpak's
  own search is loose and used to offer unrelated apps.
Looking up is immediate. Installing, updating and removing are only proposed: the user sees a card with the
program, its publisher and version and the exact command, and presses Confirm. Lanterna never downloads installers
from web pages and never runs other commands.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .workspace import WAITING, WorkError

PKG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")   # never starts with "-": can't become an option
APP_ID = re.compile(r"^[A-Za-z][\w-]*(\.[\w-]+){2,}$")         # reverse-DNS, like org.videolan.VLC: a Flatpak app
ARCHES = "x86_64|noarch|i686|aarch64|armv7hl|ppc64le|s390x"
# dnf5 into a pipe: " htop.x86_64\tInteractive process viewer"; on a terminal ": "; dnf4: "htop.x86_64 : Interactive…"
DNF_ROW = re.compile(rf"^\s*([A-Za-z0-9][\w.+-]*?)\.({ARCHES})(?:\s*:\s*|\t+\s*|\s{{2,}})(.*)$")
APT_ROW = re.compile(r"^([a-z0-9][a-z0-9.+-]*)/\S+\s+(\S+)")                # "htop/stable 3.2.2-2 amd64"
RUN_TIMEOUT = 30 * 60
LOOK_TIMEOUT = 90
WINGET_COMMON = ["--source", "winget", "--accept-source-agreements", "--disable-interactivity"]
SHOW_MAX = 15

# Visual Studio alone is only an editor: what it builds comes in parts ("workloads"), chosen when it is installed
# (winget --override) or added later by its own installer (setup.exe modify). Without the C++ part there is no
# compiler. Ids: 2026 is Microsoft.VisualStudio.Community, older ones have the year (Microsoft.VisualStudio.2022.Community).
VS_ID = re.compile(r"^Microsoft\.VisualStudio\.(?:(\d{4})\.)?(Community|Professional|Enterprise|BuildTools)$", re.I)
VS_YEARS = {"2017": 15, "2019": 16, "2022": 17}           # no year in the id: the newest (2026 is 18)
# part → (its name, the workload in the IDE, the workload in Build Tools, what shows that it is there)
VS_PARTS = {
    "cpp": ("Desktop development with C++", "Microsoft.VisualStudio.Workload.NativeDesktop",
            "Microsoft.VisualStudio.Workload.VCTools", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"),
    "dotnet": (".NET desktop development", "Microsoft.VisualStudio.Workload.ManagedDesktop",
               "Microsoft.VisualStudio.Workload.ManagedDesktopBuildTools", ""),
    "web": ("ASP.NET and web development", "Microsoft.VisualStudio.Workload.NetWeb",
            "Microsoft.VisualStudio.Workload.WebBuildTools", ""),
}
VS_TIMEOUT = 3 * 3600                                     # several GB to download
APP_KINDS = ("app_install", "app_upgrade", "app_uninstall", "app_add")

# After a change Lanterna looks whether it really happened (the card's ✅ line says so)
CHECKED = "checked: it is installed"
CHECKED_CPP = "checked: the C++ compiler is there"
NO_CPP = "but the C++ compiler isn't there"
UNLISTED = "but it isn't in the list of installed programs yet: restart the computer and check again"
RESTART = "restart the computer to finish"
RESTART_CODES = {3010, 1641, 0x8A150109, 0x8A15010B}      # done, a restart finishes it

# What an error means, in plain words (winget's own codes, then the installer's exit code)
OPEN_NOW = "The program is open right now: close it and try again."
MISSING = "Something this program needs is missing on this computer."
CANCELLED = "The installation was cancelled (maybe the window asking for administrator rights was closed)."
ADMIN = "It needs administrator rights: say yes in the Windows window that asks for them."
BUSY = "Another installation is running right now: wait until it finishes, then try again."
OFFLINE = "There is no internet connection."
WINGET_SAYS = {
    0x8A150008: "The installer couldn't be downloaded: check the internet connection and try again.",
    0x8A150010: "This program has no installer for this computer (its Windows version or processor).",
    0x8A150011: "The downloaded installer didn't pass the safety check, so it wasn't started. Try again later.",
    0x8A150014: "The catalog has no such program.", 0x8A150019: ADMIN,
    0x8A15002B: "There is no newer version to update to.", 0x8A150101: OPEN_NOW, 0x8A150102: BUSY,
    0x8A150103: OPEN_NOW, 0x8A150104: MISSING, 0x8A150105: "There isn't enough free space on the disk.",
    0x8A150106: "There isn't enough free memory: close other programs and try again.", 0x8A150107: OFFLINE,
    0x8A15010A: "Restart the computer, then try again.", 0x8A15010C: CANCELLED,
    0x8A15010D: "Another version of this program is already installed.",
    0x8A15010E: "A newer version of this program is already installed.",
    0x8A15010F: "This computer's rules don't allow installing it.", 0x8A150110: MISSING, 0x8A150111: OPEN_NOW,
    0x8A150113: "This program doesn't work on this system.",
}
VS_OPEN = "Visual Studio is open: close it, then try again."
VS_SAYS = {1001: "The Visual Studio Installer is already open: close it (or let it finish), then try again.",
           1003: VS_OPEN, 8006: VS_OPEN, 1602: CANCELLED, 5004: CANCELLED, 1618: BUSY, 740: ADMIN,
           5007: "This computer doesn't meet Visual Studio's requirements.",
           8010: "This computer doesn't meet Visual Studio's requirements.", -1073720687: OFFLINE,
           -1073741510: "The Visual Studio Installer was closed before it finished."}
VS_FAILED = ("The Visual Studio installer stopped with an error (code {n}). This often happens while another Visual "
             "Studio installation is still running or has just finished: wait a few minutes or restart the computer, "
             "then try again.")
INSTALLER_FAILED = ("The program's own installer stopped with an error (code {n}). Restarting the computer and trying "
                    "again often helps.")
TOO_LONG = "It took too long, so Lanterna stopped waiting (the installer may still be working: check again later)."
NO_PASSWORD = "The password window was closed or the password wasn't accepted, so nothing was installed."
FAILED = "{m} stopped with an error (code {n})."
_BOILERPLATE = re.compile(r"licensed to you by its owner|not responsible for, nor does it grant|^Found .+ \[|"
                          r"^Successfully verified installer hash|^Starting package install", re.I)


def _say(text: str, lang: str, **kw) -> str:
    from .i18n import t
    return t(text, lang, **kw)


def explain(code: int, out: str, m: str, vs: bool = False, lang: str = "en") -> str:
    """Why a package manager (or the installer it started) stopped, in plain words, then its last lines whole."""
    u = code & 0xFFFFFFFF
    inst = re.search(r"exit code:?\s*(-?\d+)", out or "", re.I)
    n = int(inst.group(1)) if inst else None
    if code == 124:
        why = _say(TOO_LONG, lang)
    elif m == "winget" and u in WINGET_SAYS:
        why = _say(WINGET_SAYS[u], lang)
    elif n is not None and vs and n in VS_SAYS:
        why = _say(VS_SAYS[n], lang)
    elif n is not None:
        why = _say(VS_FAILED if vs else INSTALLER_FAILED, lang, n=n)
    elif vs and code in VS_SAYS:                           # the Visual Studio Installer itself (setup.exe modify)
        why = _say(VS_SAYS[code], lang)
    elif vs:
        why = _say(VS_FAILED, lang, n=code)
    elif m in ("dnf", "apt") and code in (126, 127) and "not installed" not in (out or ""):
        why = _say(NO_PASSWORD, lang)                     # pkexec: the password window was closed or refused
    else:
        why = _say(FAILED, lang, m=m, n=code)
    shown = f"0x{u:08X}" if u > 0xFFFF else str(code)
    lines = [ln.strip()[:160] for ln in _clean(out or "") if ln.strip() and not _BOILERPLATE.search(ln.strip())]
    return f"{why} ({m}: {shown})" + ("\n" + "\n".join(lines[-5:]) if lines else "")


def vs_parts(names) -> list[str]:
    """The parts of Visual Studio asked for, known ones only."""
    items = names if isinstance(names, (list, tuple)) else re.split(r"[,;\s]+", str(names or ""))
    out = []
    for x in items:
        k = str(x).strip().lower().replace("c++", "cpp").replace(".net", "dotnet")
        if not k:
            continue
        if k not in VS_PARTS:
            raise WorkError(f"Unknown part '{x}'. Parts: {', '.join(VS_PARTS)}.")
        if k not in out:
            out.append(k)
    return out


def _vswhere() -> str:
    p = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)") / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    return str(p) if sys.platform == "win32" and p.is_file() else ""


def _words(text: str) -> list[str]:
    """The words of a name, id or description: "LibreOffice" and "NeoHtop" are two words each, "Splashtop" one."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text or "")
    return re.findall(r"[^\W_]+", text.lower())


def match_score(query: str, name: str, pid: str, about: str = "") -> int:
    """0 = this is the program asked for, 1 = its name or id has the words, 2 = only its description has them,
    3 = none of that (a loose match: a different program). A word counts only at the start of a word: "htop" is
    in pcp-htop, but not in org.dupot.beatmatchtopass ("Beat And Match To Pass", which Flatpak finds for it)."""
    q = " ".join(str(query or "").lower().split())
    n, i = (name or "").lower(), (pid or "").lower()
    joined = "".join(_words(q))                          # "gnome tweaks" is gnome-tweaks, "libre office" LibreOffice
    if q in (n, i, i.rsplit(".", 1)[-1]) or (joined and joined in ("".join(_words(n)), "".join(_words(i.rsplit(".", 1)[-1])))):
        return 0
    words, own = _words(q), _words(name) + _words(pid)
    if words and all(any(t.startswith(w) for t in own) for w in words):
        return 1
    told = own + _words(about)
    if words and all(any(t.startswith(w) for t in told) for w in words):
        return 2
    return 3


def run_cmd(args: list[str], timeout: float = LOOK_TIMEOUT) -> tuple[int, str]:
    """Runs a program (no shell) and returns (exit code, output as text)."""
    try:
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        r = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, **kw)
    except FileNotFoundError:
        return 127, f"{args[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "took too long"
    out = (r.stdout or b"") + (b"\n" + r.stderr if r.stderr else b"")
    return r.returncode, out.decode("utf-8", "replace")


def _clean(text: str) -> list[str]:
    """winget prints a spinner (\\r - \\ | /) and progress bars before the table."""
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.split("\r")[-1].rstrip()
        if line.strip() in ("-", "\\", "|", "/") or "█" in line or "▒" in line:
            continue
        lines.append(line)
    return lines


def parse_table(text: str, cols: tuple = ("name", "id", "version", "extra", "source")) -> list[dict]:
    """winget's fixed-width tables (search, list, upgrade): columns start where the header words start."""
    lines = _clean(text)
    for i, line in enumerate(lines[:-1]):
        if set(lines[i + 1].strip()) == {"-"} and len(lines[i + 1].strip()) > 10:
            header = line
            starts = [m.start() for m in re.finditer(r"(?<!\S)\S", header)]
            if len(starts) < 3:
                continue
            names = list(cols)[:len(starts)]           # headers are translated: go by position
            rows = []
            for row in lines[i + 2:]:
                if not row.strip() or re.match(r"^\d+ (upgrades?|package)", row.strip()) or len(row) < starts[1]:
                    if rows and not row.strip():
                        break
                    continue
                cells = [row[a:b].strip() if b else row[a:].strip() for a, b in zip(starts, starts[1:] + [None])]
                d = dict(zip(names, cells))
                if d.get("id") and PKG_ID.match(d["id"]):
                    rows.append(d)
            return rows
    return []


def parse_show(text: str) -> dict:
    """winget show: 'Key: value' lines at the top level."""
    out = {}
    for line in _clean(text):
        m = re.match(r"^Found (.+) \[([^\]]+)\]$", line.strip())
        if m:
            out["name"], out["id"] = m.group(1), m.group(2)
            continue
        m = re.match(r"^([A-Z][A-Za-z ]{1,30}):\s+(.+)$", line)
        if m and not line.startswith(" "):
            out.setdefault(m.group(1).strip().lower(), m.group(2).strip())
    return out


class Apps:
    def __init__(self, actions, runner: Callable[..., tuple[int, str]] = run_cmd, platform: str = sys.platform,
                 which: Callable[[str], str | None] = shutil.which, lang: Callable[[], str] = lambda: "en",
                 vswhere: str | None = None):
        self.actions, self.run, self.platform, self.which, self.lang = actions, runner, platform, which, lang
        self._vswhere = vswhere

    @property
    def vswhere_exe(self) -> str:
        """Visual Studio's own finder (Windows). It comes with the Visual Studio Installer, so it can appear later."""
        return (_vswhere() if self.platform == "win32" else "") if self._vswhere is None else self._vswhere

    # -- Visual Studio: which ones are here and what parts they have
    def vs_instances(self, requires: str = "") -> list[dict]:
        """Visual Studio installations (path, name, edition, major version); with `requires`, only those that have
        that workload or component."""
        if not self.vswhere_exe:
            return []
        code, out = self.run([self.vswhere_exe, "-all", "-products", "*", *(["-requires", requires] if requires else []),
                              "-format", "json", "-utf8", "-nologo"])
        try:
            data = json.loads(out[out.index("["):out.rindex("]") + 1])
        except ValueError:
            return []
        rows = []
        for x in data if isinstance(data, list) else []:
            ver = str(x.get("installationVersion", ""))
            rows.append({"path": str(x.get("installationPath", "")), "name": str(x.get("displayName", "")),
                         "edition": str(x.get("productId", "")).rsplit(".", 1)[-1],
                         "major": int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else 0})
        return [r for r in rows if r["path"]]

    def vs_for(self, pid: str) -> dict | None:
        """The installation of this winget id (Microsoft.VisualStudio.Community = the newest Community)."""
        m = VS_ID.match(pid or "")
        if not m:
            return None
        same = [r for r in self.vs_instances() if r["edition"].lower() == m.group(2).lower()]
        major = VS_YEARS.get(m.group(1) or "")
        mine = [r for r in same if r["major"] == major] if major else [r for r in same if r["major"] >= 18] or same
        return max(mine, key=lambda r: r["major"], default=None)

    def vs_has(self, inst: dict, part: str) -> bool:
        """This installation has the part (for C++: the compiler itself, not only the workload's name)."""
        name, ide, tools, sign = VS_PARTS[part]
        need = sign or (tools if inst.get("edition", "").lower() == "buildtools" else ide)
        return any(r["path"] == inst["path"] for r in self.vs_instances(need))

    def _busy(self, pid: str) -> tuple[str, str]:
        """A card for this program (or, for Visual Studio, any Visual Studio) that waits or runs now: (state, name)."""
        vs = bool(VS_ID.match(pid))
        for a in list(getattr(self.actions, "items", {}).values()):
            other = str(a.details.get("id", ""))
            if a.kind in APP_KINDS and (other.lower() == pid.lower() or (vs and VS_ID.match(other))):
                now = self.actions.get(a.id) if hasattr(self.actions, "get") else a
                if now is not None and now.state in ("pending", "running"):
                    return now.state, str(a.details.get("name") or other)
        return "", ""

    # -- what this computer has
    def managers(self) -> list[str]:
        if self.platform == "win32":
            return ["winget"] if self.which("winget") else []
        out = [m for m in ("flatpak", "dnf", "apt") if self.which(m)]
        return out

    def _need(self, source: str = "") -> str:
        have = self.managers()
        if not have:
            raise WorkError("No package manager found (Windows: winget from the Microsoft Store 'App Installer'; "
                            "Linux: flatpak, dnf or apt).")
        if source:
            if source not in have:
                raise WorkError(f"{source} is not available here. Available: {', '.join(have)}.")
            return source
        return have[0]

    def _pick(self, source: str = "", pid: str = "") -> str:
        """The manager for one program: the one asked for, else by the id (org.videolan.VLC is a Flatpak app,
        htop is a system package)."""
        m = self._need(source)
        if source or self.platform == "win32":
            return m
        have = self.managers()
        if "flatpak" in have and APP_ID.match(pid or ""):
            return "flatpak"
        return next((x for x in have if x != "flatpak"), m)

    def _sources(self, source: str = "") -> list[str]:
        """Where a search or a list looks: the one asked for, else every manager this computer has."""
        return [self._need(source)] if source or self.platform == "win32" else self.managers() or [self._need()]

    @staticmethod
    def _check_id(pid: str) -> str:
        pid = str(pid or "").strip()
        if not PKG_ID.match(pid):
            raise WorkError(f"'{pid}' is not a valid package id.")
        return pid

    # -- Flatpak: which remotes and installations this computer has
    def _remotes(self) -> list[tuple[str, str, str]]:
        """(name, title, installation) of each enabled Flatpak remote: the user's first (no password), Flathub first."""
        code, out = self.run(["flatpak", "remotes", "--columns=name,title,options"])
        found = []
        for line in out.splitlines():
            cells = [c.strip() for c in line.split("\t")]
            if not cells[0] or not PKG_ID.match(cells[0]):
                continue
            opts = cells[-1].split(",") if len(cells) > 1 else []
            if "disabled" in opts:
                continue
            title = cells[1] if len(cells) > 2 and cells[1] else cells[0]
            found.append((cells[0], title, "user" if "user" in opts else "system"))
        return sorted(found, key=lambda r: (r[2] != "user", r[0].lower() != "flathub"))

    def _flatpaks(self) -> list[tuple[str, str]]:
        """(id, "user" or "system") of each installed Flatpak app."""
        code, out = self.run(["flatpak", "list", "--app", "--columns=application,installation"])
        rows = [[c.strip() for c in line.split("\t")] for line in out.splitlines()]
        return [(r[0], "user" if len(r) > 1 and r[1] == "user" else "system") for r in rows if r[0]]

    def _flatpak_where(self, pid: str) -> str:
        """The installation ("user" or "system") a Flatpak app is installed in, "" if it isn't."""
        return next((where for app, where in self._flatpaks() if app == pid), "")

    def is_installed(self, pid: str, m: str) -> bool:
        if m == "winget":
            code, out = self.run(["winget", "list", "--id", pid, "--exact", "--accept-source-agreements",
                                  "--disable-interactivity"])
            return any(r["id"].lower() == pid.lower() for r in parse_table(out))
        if m == "flatpak":          # one program, two ids: Fedora's org.videolan.vlc is Flathub's org.videolan.VLC
            return any(app.lower() == pid.lower() for app, _ in self._flatpaks())
        if m == "dnf":
            return self.run(["rpm", "-q", pid])[0] == 0
        code, out = self.run(["dpkg-query", "-W", "-f=${Status}", pid])
        return code == 0 and "install ok installed" in out

    # -- looking up
    def _flatpak_found(self, text: str) -> list[dict]:
        code, out = self.run(["flatpak", "search", "--columns=name,application,version,remotes,description", text])
        rows = []
        for line in out.splitlines():
            c = [x.strip() for x in line.split("\t")]
            if len(c) >= 3 and PKG_ID.match(c[1]):
                rows.append({"name": c[0], "id": c[1], "version": c[2], "source": "flatpak",
                             "where": c[3] if len(c) > 3 and c[3] else "Flatpak", "about": c[4] if len(c) > 4 else ""})
        return rows

    def _found(self, m: str, q: str) -> list[dict]:
        """One manager's search, as rows: name, id, version, source, where (the remote or repository), about.
        dnf and apt get each word on its own: gnome-tweaks has "gnome" and "tweaks", not the phrase "gnome tweaks".
        Flatpak takes one text: the phrase, else its longest word (search() keeps what has all the words)."""
        words = q.split()
        if m == "flatpak":
            rows = self._flatpak_found(" ".join(words))
            if not rows and len(words) > 1:
                rows = self._flatpak_found(max(words, key=len))
            return rows
        if m == "dnf":
            code, out = self.run(["dnf", "search", *words])
            rows, seen = [], set()
            for line in out.splitlines():
                r = DNF_ROW.match(line)
                if r and r.group(1) not in seen:
                    seen.add(r.group(1))
                    rows.append({"name": r.group(1), "id": r.group(1), "version": "", "source": m,
                                 "where": "system packages", "about": r.group(3).strip()})
            return rows
        code, out = self.run(["apt", "search", "--names-only", *words])
        lines, rows = out.splitlines(), []
        for i, line in enumerate(lines):
            r = APT_ROW.match(line)
            if r:
                about = lines[i + 1].strip() if i + 1 < len(lines) else ""
                rows.append({"name": r.group(1), "id": r.group(1), "version": r.group(2), "source": m,
                             "where": "system packages", "about": about})
        return rows

    def _winget_found(self, text: str) -> tuple[int, str, list[dict]]:
        code, out = self.run(["winget", "search", "--query", text, *WINGET_COMMON])
        # its Match column says why a row came up ("Tag: htop", "Moniker: 7zip"), like a description; an empty
        # one means a part of the name or id ("htop" in Splashtop), so the words decide as they do on Linux
        return code, out, [{**r, "about": r.get("extra", "")} for r in parse_table(out)]

    def search(self, query: str, source: str = "") -> str:
        q = " ".join(w for w in str(query or "").split() if not w.startswith("-"))[:80].strip()  # never an option
        if not q:
            raise WorkError("Say what program to look for.")
        m = self._need(source)
        if m == "winget":
            code, out, rows = self._winget_found(q)
            if " " in q and not any(match_score(q, r["name"], r["id"], r["about"]) == 0 for r in rows):
                seen = {r["id"] for r in rows}       # winget looks for the phrase: "libre office" missed LibreOffice
                rows += [r for r in self._winget_found(q.replace(" ", ""))[2] if r["id"] not in seen]
            if not rows:
                return f"Nothing found in the winget catalog for '{q}'." + (
                    "" if code == 0 or "No package" in out else f" (winget said: {out.strip()[-200:]})")
            looked = ["winget"]
        else:
            looked = self._sources(source)
            rows = [r for s in looked for r in self._found(s, q)]
        for r in rows:
            r["score"] = match_score(q, r["name"], r["id"], r["about"])
        good = sorted((r for r in rows if r["score"] < 3), key=lambda r: r["score"])   # stable: Flatpak, then the system's
        loose = len(rows) - len(good)
        if not good:
            return (f"Nothing found for '{q}' ({', '.join(looked)}). " + (
                f"{loose} loose matches were left out: their name and description don't have these words, so they are "
                "other programs. " if loose else "") + "Tell the user; don't install a different program instead.")
        if m == "winget":
            head = "winget catalog, closest first:"
            lines = [f"- {r['name']} — id {r['id']}, version {r.get('version') or '?'}"
                     + (f" ({r['about']})" if r["about"] else "") for r in good[:SHOW_MAX]]
        else:
            head = (f"Found for '{q}' in {', '.join(looked)}, closest first. To install one, pass its id and source "
                    "to app_install:")
            lines = [f"- {r['name']} — id {r['id']}, source {r['source']} ({r['where']})"
                     + (f", version {r['version']}" if r["version"] else "") + (f": {r['about'][:100]}" if r["about"] else "")
                     for r in good[:SHOW_MAX]]
        return (head + "\n" + "\n".join(lines)
                + (f"\n({len(good) - SHOW_MAX} more not shown.)" if len(good) > SHOW_MAX else "")
                + (f"\n({loose} loose matches without these words were left out.)" if loose else ""))

    def details(self, pid: str, source: str = "") -> dict:
        pid, m = self._check_id(pid), self._pick(source, pid)
        if m == "winget":
            code, out = self.run(["winget", "show", "--id", pid, "--exact", *WINGET_COMMON])
            d = parse_show(out)
            if not d.get("id"):
                raise WorkError(f"There is no '{pid}' in the winget catalog. Search first.")
            return {"source": m, "id": d["id"], "name": d.get("name", pid), "version": d.get("version", ""),
                    "publisher": d.get("publisher", ""), "description": d.get("description", ""),
                    "homepage": d.get("homepage", ""), "license": d.get("license", "")}
        if m == "flatpak":
            remotes = self._remotes()
            if not remotes:
                raise WorkError("Flatpak has no remotes on this computer, so there is nowhere to install it from.")
            for name, title, where in remotes:
                code, out = self.run(["flatpak", "remote-info", f"--{where}", name, pid])
                if code != 0:
                    continue
                info = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines()) if v}
                head = next((ln.strip() for ln in out.splitlines() if " - " in ln), pid)
                return {"source": m, "id": pid, "name": head.split(" - ")[0], "version": info.get("version", ""),
                        "publisher": title, "description": head.split(" - ", 1)[-1], "homepage": "",
                        "license": info.get("license", ""), "remote": name, "installation": where}
            raise WorkError(f"There is no '{pid}' in this computer's Flatpak remotes "
                            f"({', '.join(r[0] for r in remotes)}). Search first.")
        code, out = self.run(["dnf", "info", pid] if m == "dnf" else ["apt", "show", pid])
        if code != 0:
            raise WorkError(f"There is no package '{pid}' in {m}.")
        info = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines()) if v}
        return {"source": m, "id": pid, "name": info.get("name", info.get("package", pid)), "version": info.get("version", ""),
                "publisher": info.get("vendor", info.get("maintainer", m)), "description": info.get("summary", info.get("description", "")),
                "homepage": info.get("url", info.get("homepage", "")), "license": info.get("license", "")}

    def info(self, pid: str, source: str = "") -> str:
        d = self.details(pid, source)
        return "\n".join(f"{k}: {v}" for k, v in d.items() if v)

    def installed(self, query: str = "", source: str = "") -> str:
        q = str(query or "").strip()[:80]
        if q.startswith("-"):
            raise WorkError("Bad name.")
        if self._need(source) == "winget":
            code, out = self.run(["winget", "list", *(["--query", q] if q else []), "--accept-source-agreements",
                                  "--disable-interactivity"])
            rows = parse_table(out)
            if not rows:
                return f"Nothing installed matches '{q}'." if q else "Couldn't read the list of installed programs."
            return f"Installed ({len(rows)}):\n" + "\n".join(
                f"- {r['name']} — id {r['id']}, version {r.get('version', '?')}" for r in rows[:60])
        parts = []
        for m in self._sources(source):
            if m == "flatpak":
                code, out = self.run(["flatpak", "list", "--app", "--columns=name,application,version,installation"])
            else:
                code, out = self.run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}\n"] if m == "dnf" else ["apt", "list", "--installed"])
            lines = [x for x in out.splitlines() if x.strip() and (not q or q.lower() in x.lower())]
            parts.append(f"Installed with {m} ({len(lines)}):\n" + "\n".join(lines[:60]) if lines
                         else f"Nothing installed with {m}" + (f" matches '{q}'." if q else "."))
        return "\n\n".join(parts)

    def updates(self, source: str = "") -> str:
        if self._need(source) == "winget":
            code, out = self.run(["winget", "upgrade", *WINGET_COMMON], timeout=180)
            rows = parse_table(out, ("name", "id", "version", "available", "source"))
            if not rows:
                return "Every program from the winget catalog is up to date."
            return f"Updates available ({len(rows)}):\n" + "\n".join(
                f"- {r['name']} — id {r['id']}: {r.get('version', '?')} → {r.get('available', '?')}" for r in rows[:60])
        parts = []
        for m in self._sources(source):
            if m == "flatpak":
                code, out = self.run(["flatpak", "remote-ls", "--updates", "--columns=name,application,version"])
            else:
                code, out = self.run(["dnf", "check-update", "--quiet"] if m == "dnf" else ["apt", "list", "--upgradable"])
            lines = [x for x in out.splitlines() if x.strip() and not x.startswith(("Listing", "WARNING"))]
            parts.append(f"Updates with {m}:\n" + "\n".join(lines[:60]) if lines else f"Everything from {m} is up to date.")
        return "\n\n".join(parts)

    # -- changes (cards)
    def command(self, op: str, pid: str, m: str, where: str = "user", remote: str = "flathub",
                override: str = "") -> list[str]:
        if m == "winget":
            base = {"install": ["winget", "install"], "upgrade": ["winget", "upgrade"], "uninstall": ["winget", "uninstall"]}[op]
            extra = ["--accept-package-agreements"] if op != "uninstall" else []
            src = WINGET_COMMON if op != "uninstall" else ["--accept-source-agreements", "--disable-interactivity"]
            if override:                        # the installer's own switches instead of the silent ones (Visual Studio)
                return [*base, "--id", pid, "--exact", *extra, *src, "--override", override]
            return [*base, "--id", pid, "--exact", "--silent", *extra, *src]
        if m == "flatpak":                      # --user or --system: the installation the remote (or the app) is in
            inst = "--system" if where == "system" else "--user"
            return {"install": ["flatpak", "install", inst, "-y", "--noninteractive", remote, pid],
                    "upgrade": ["flatpak", "update", inst, "-y", "--noninteractive", pid],
                    "uninstall": ["flatpak", "uninstall", inst, "-y", "--noninteractive", pid]}[op]
        verb = {"install": "install", "upgrade": "upgrade", "uninstall": "remove"}[op]
        return ["pkexec", m, verb, "-y", pid]

    def _vs_check(self, inst: dict | None, parts: list[str], restart: bool = False) -> str:
        """What a look after a Visual Studio change finds (the card's ✅ line)."""
        if restart:
            return RESTART
        if inst is None:
            return UNLISTED
        if "cpp" in parts:
            return CHECKED_CPP if self.vs_has(inst, "cpp") else NO_CPP
        return CHECKED

    def _propose_add(self, d: dict, inst: dict | None, parts: list[str]) -> str:
        """Visual Studio is already here: the parts it lacks are added by its own installer, on a card."""
        name = (inst or {}).get("name") or d["name"]
        if not parts:
            raise WorkError(f"{name} is already installed. To add parts (cpp for C++, which brings the compiler), "
                            "call app_install again with parts; for a newer version, use app_update.")
        if inst is None:
            raise WorkError(f"{name} is already installed, but its installer wasn't found to add parts. The user can "
                            "open the Visual Studio Installer, press Modify and tick: "
                            + ", ".join(VS_PARTS[p][0] for p in parts) + ".")
        missing = [p for p in parts if not self.vs_has(inst, p)]
        if not missing:
            return (f"{name} already has: {', '.join(VS_PARTS[p][0] for p in parts)}. Nothing to install."
                    + (" The C++ compiler (MSVC, cl.exe) is there: build in Visual Studio, or run cl from "
                       "'Developer PowerShell for VS' (it isn't in the usual PATH)." if "cpp" in parts else ""))
        tools = inst["edition"].lower() == "buildtools"
        cmd = [str(Path(self.vswhere_exe).with_name("setup.exe")), "modify", "--installPath", inst["path"],
               *(a for p in missing for a in ("--add", VS_PARTS[p][2 if tools else 1])),
               "--includeRecommended", "--passive", "--norestart"]
        details = {"source": "winget", "id": d["id"], "name": name, "version": "", "publisher": d.get("publisher", ""),
                   "description": "", "op": "add", "parts": [VS_PARTS[p][0] for p in missing],
                   "command": subprocess.list2cmdline(cmd), "admin": True,
                   "notes": ["Close Visual Studio before you confirm.", "It takes a while: Visual Studio shows its progress."]}

        def run() -> str:
            code, out = self.run(cmd, timeout=VS_TIMEOUT)
            if code != 0 and (code & 0xFFFFFFFF) not in RESTART_CODES:
                raise WorkError(explain(code, out, "Visual Studio Installer", vs=True, lang=self.lang()))
            details["checked"] = self._vs_check(inst, missing, restart=code != 0)
            return f"Added {', '.join(details['parts'])} to {name}"
        self.actions.propose("app_add", details, run)
        return WAITING + (f" The card adds {', '.join(details['parts'])} to {name}, which is already installed. "
                          "Visual Studio must be closed; Windows will ask for administrator rights.")

    def propose(self, op: str, pid: str, source: str = "", parts=None) -> str:
        if op not in ("install", "upgrade", "uninstall"):
            raise WorkError("op must be install, upgrade or uninstall.")
        pid, m = self._check_id(pid), self._pick(source, pid)
        parts = vs_parts(parts)
        vs = m == "winget" and bool(VS_ID.match(pid))
        if parts and not vs:
            raise WorkError("parts are only for Visual Studio (its workloads): install this program without them.")
        state, busy = self._busy(pid)                        # never two cards for one program (or two Visual Studios)
        if state == "pending":
            raise WorkError(f"A card for {busy} already waits for the user's Confirm: don't make another one. Tell the "
                            "user to press Confirm on that card.")
        if state == "running":
            raise WorkError(f"{busy} is being installed or changed right now (the user confirmed its card): don't make "
                            "another card. Its result comes as Lanterna's ✅ or ⚠️ note.")
        if op == "install":
            d = self.details(pid, m)                         # the card shows what the catalog says
            if vs:
                inst = self.vs_for(d["id"])
                if inst is not None or self.is_installed(d["id"], m):
                    return self._propose_add(d, inst, parts)
                if not parts:
                    raise WorkError("Visual Studio needs its parts: pass parts (cpp for C++, which brings the compiler; "
                                    "dotnet for C# desktop apps; web for ASP.NET). Without them it installs only the "
                                    "editor, which can't build anything.")
            elif self.is_installed(d["id"], m):
                # installing it "again" would put its removal in Undo: the user's own copy would go
                raise WorkError(f"{d['name']} ({d['id']}) is already installed with {m}. To get a newer version, use app_update.")
        else:
            d = {"source": m, "id": pid, "name": pid, "version": "", "publisher": "", "description": "", "homepage": "", "license": ""}
            if m == "flatpak":
                d["installation"] = self._flatpak_where(pid)
                if not d["installation"]:
                    raise WorkError(f"'{pid}' is not installed with Flatpak (see app_installed).")
        where = d.get("installation", "user")
        override = ""
        if vs and op == "install":                           # with its parts: the compiler comes with C++
            tools = VS_ID.match(d["id"]).group(2).lower() == "buildtools"
            override = " ".join(["--wait", "--passive", "--norestart",
                                 *(f"--add {VS_PARTS[p][2 if tools else 1]}" for p in parts), "--includeRecommended"])
        cmd = self.command(op, d["id"], m, where, d.get("remote", "flathub"), override)
        admin = m in ("dnf", "apt") or (m == "winget" and op != "uninstall") or (m == "flatpak" and where == "system")
        details = {**d, "op": op, "command": " ".join(cmd) if not override else subprocess.list2cmdline(cmd),
                   "admin": admin}
        if override:
            details["parts"] = [VS_PARTS[p][0] for p in parts]
            details["notes"] = ["It takes a while: Visual Studio shows its progress."]

        def run() -> str:
            code, out = self.run(cmd, timeout=VS_TIMEOUT if vs else RUN_TIMEOUT)
            restart = code != 0 and (code & 0xFFFFFFFF) in RESTART_CODES
            if code != 0 and not restart:
                raise WorkError(explain(code, out, m, vs=vs, lang=self.lang()))
            if op in ("install", "uninstall"):
                self.actions.note_undo({"type": "app", "op": "uninstall" if op == "install" else "install",
                                        "id": d["id"], "source": m})
            if op == "install":                              # did it really happen? (the ✅ line says)
                details["checked"] = (self._vs_check(self.vs_for(d["id"]), parts, restart) if vs else RESTART if restart
                                      else CHECKED if self.is_installed(d["id"], m) else UNLISTED)
            return {"install": "Installed", "upgrade": "Updated", "uninstall": "Removed"}[op] + f" {d['name']}"
        self.actions.propose(f"app_{op}", details, run)
        return WAITING + (" Windows may also ask for administrator rights during the install." if m == "winget" and op != "uninstall" else
                          " The system will ask for the password." if admin else "") + (
            " Visual Studio is big (several GB): the installation can take half an hour or more, and Visual Studio "
            "shows its progress." if override else "")


def app_tools(apps: Apps) -> list:
    from .tools import Tool, _obj
    have = apps.managers()
    if not have:
        return []
    s = {"type": "string"}
    src = {"type": "string", "enum": have}
    card = "The user confirms it on a card that shows the program and the exact command, so don't ask in text first."
    return [
        Tool("app_search", f"Find a program to install in the system's official catalogs ({', '.join(have)}; without a "
             "source it looks in all of them). Use it when the user wants to install or get a program. Lists only "
             "programs that have the words asked for, closest first, each with its id and source. Search for the "
             "program's name (htop, VLC) or, when the user names none, for what it does in English (video editor).",
             _obj({"query": s, "source": src}, ["query"]), lambda query, source="": apps.search(query, source), "🔎"),
        Tool("app_info", "Details of one program in the catalog by its id: publisher, version, description, homepage, license.",
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.info(id, source), "📦"),
        Tool("app_installed", "Programs installed on this computer (optionally only those matching a name).",
             _obj({"query": s, "source": src}), lambda query="", source="": apps.installed(query, source), "📦"),
        Tool("app_updates", "Programs on this computer that have a newer version in the catalog.",
             _obj({"source": src}), lambda source="": apps.updates(source), "⬆️"),
        Tool("app_install", "Install a program by its exact id and source from app_search (search first). Install only "
             "the program the user asked for: if no result is that program, say so instead of installing a different one. "
             "Visual Studio needs parts: cpp for C++ (it brings the compiler), dotnet for C# desktop apps, web for "
             "ASP.NET; without them it is only an editor. If that Visual Studio is already installed, the same call "
             "adds the parts it lacks. One card per program: never call it again while its card waits or runs. " + card,
             _obj({"id": s, "source": src,
                   "parts": {"type": "array", "items": {"type": "string", "enum": list(VS_PARTS)},
                             "description": "Visual Studio only: what it is for"}}, ["id"]),
             lambda id, source="", parts=None: apps.propose("install", id, source, parts), "⬇️"),
        Tool("app_update", "Update an installed program to the newest version by its id. " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("upgrade", id, source), "⬆️"),
        Tool("app_uninstall", "Remove an installed program by its id (see app_installed). " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("uninstall", id, source), "🗑"),
    ]
