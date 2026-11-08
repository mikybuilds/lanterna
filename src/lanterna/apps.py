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

import re
import shutil
import subprocess
import sys
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


def match_score(query: str, name: str, pid: str, about: str = "") -> int:
    """0 = this is the program asked for, 1 = its name or id has the words, 2 = only its description has them,
    3 = none of that (a loose match: a different program)."""
    q = " ".join(str(query or "").lower().split())
    n, i, a = (name or "").lower(), (pid or "").lower(), (about or "").lower()
    if q in (n, i, i.rsplit(".", 1)[-1]) or n.replace(" ", "") == q.replace(" ", ""):
        return 0
    words = q.split()
    if words and all(w in n or w in i for w in words):
        return 1
    if words and all(w in n or w in i or w in a for w in words):
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
                 which: Callable[[str], str | None] = shutil.which):
        self.actions, self.run, self.platform, self.which = actions, runner, platform, which

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
    def _found(self, m: str, q: str) -> list[dict]:
        """One manager's search, as rows: name, id, version, source, where (the remote or repository), about."""
        if m == "flatpak":
            code, out = self.run(["flatpak", "search", "--columns=name,application,version,remotes,description", q])
            rows = []
            for line in out.splitlines():
                c = [x.strip() for x in line.split("\t")]
                if len(c) >= 3 and PKG_ID.match(c[1]):
                    rows.append({"name": c[0], "id": c[1], "version": c[2], "source": m,
                                 "where": c[3] if len(c) > 3 and c[3] else "Flatpak", "about": c[4] if len(c) > 4 else ""})
            return rows
        if m == "dnf":
            code, out = self.run(["dnf", "search", q])
            rows, seen = [], set()
            for line in out.splitlines():
                r = DNF_ROW.match(line)
                if r and r.group(1) not in seen:
                    seen.add(r.group(1))
                    rows.append({"name": r.group(1), "id": r.group(1), "version": "", "source": m,
                                 "where": "system packages", "about": r.group(3).strip()})
            return rows
        code, out = self.run(["apt", "search", "--names-only", q])
        lines, rows = out.splitlines(), []
        for i, line in enumerate(lines):
            r = APT_ROW.match(line)
            if r:
                about = lines[i + 1].strip() if i + 1 < len(lines) else ""
                rows.append({"name": r.group(1), "id": r.group(1), "version": r.group(2), "source": m,
                             "where": "system packages", "about": about})
        return rows

    def search(self, query: str, source: str = "") -> str:
        q = str(query or "").strip()[:80]
        if not q or q.startswith("-"):
            raise WorkError("Say what program to look for.")
        m = self._need(source)
        if m == "winget":
            code, out = self.run(["winget", "search", "--query", q, *WINGET_COMMON])
            rows = parse_table(out)
            if not rows:
                return f"Nothing found in the winget catalog for '{q}'." + (
                    "" if code == 0 or "No package" in out else f" (winget said: {out.strip()[-200:]})")
            return "winget catalog:\n" + "\n".join(f"- {r['name']} — id {r['id']}, version {r.get('version', '?')}"
                                                     for r in rows[:15])
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
        lines = [f"- {r['name']} — id {r['id']}, source {r['source']} ({r['where']})"
                 + (f", version {r['version']}" if r["version"] else "") + (f": {r['about'][:100]}" if r["about"] else "")
                 for r in good[:SHOW_MAX]]
        return (f"Found for '{q}' in {', '.join(looked)}, closest first. To install one, pass its id and source to "
                "app_install:\n" + "\n".join(lines)
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
    def command(self, op: str, pid: str, m: str, where: str = "user", remote: str = "flathub") -> list[str]:
        if m == "winget":
            base = {"install": ["winget", "install"], "upgrade": ["winget", "upgrade"], "uninstall": ["winget", "uninstall"]}[op]
            extra = ["--accept-package-agreements"] if op != "uninstall" else []
            src = WINGET_COMMON if op != "uninstall" else ["--accept-source-agreements", "--disable-interactivity"]
            return [*base, "--id", pid, "--exact", "--silent", *extra, *src]
        if m == "flatpak":                      # --user or --system: the installation the remote (or the app) is in
            inst = "--system" if where == "system" else "--user"
            return {"install": ["flatpak", "install", inst, "-y", "--noninteractive", remote, pid],
                    "upgrade": ["flatpak", "update", inst, "-y", "--noninteractive", pid],
                    "uninstall": ["flatpak", "uninstall", inst, "-y", "--noninteractive", pid]}[op]
        verb = {"install": "install", "upgrade": "upgrade", "uninstall": "remove"}[op]
        return ["pkexec", m, verb, "-y", pid]

    def propose(self, op: str, pid: str, source: str = "") -> str:
        if op not in ("install", "upgrade", "uninstall"):
            raise WorkError("op must be install, upgrade or uninstall.")
        pid, m = self._check_id(pid), self._pick(source, pid)
        if op == "install":
            d = self.details(pid, m)                         # the card shows what the catalog says
            if self.is_installed(d["id"], m):
                # installing it "again" would put its removal in Undo: the user's own copy would go
                raise WorkError(f"{d['name']} ({d['id']}) is already installed with {m}. To get a newer version, use app_update.")
        else:
            d = {"source": m, "id": pid, "name": pid, "version": "", "publisher": "", "description": "", "homepage": "", "license": ""}
            if m == "flatpak":
                d["installation"] = self._flatpak_where(pid)
                if not d["installation"]:
                    raise WorkError(f"'{pid}' is not installed with Flatpak (see app_installed).")
        where = d.get("installation", "user")
        cmd = self.command(op, d["id"], m, where, d.get("remote", "flathub"))
        admin = m in ("dnf", "apt") or (m == "winget" and op != "uninstall") or (m == "flatpak" and where == "system")
        details = {**d, "op": op, "command": " ".join(cmd), "admin": admin}

        def run() -> str:
            code, out = self.run(cmd, timeout=RUN_TIMEOUT)
            tail = "\n".join(line for line in _clean(out) if line.strip())[-600:]
            if code != 0:
                raise WorkError(f"{m} stopped with code {code}: {tail[-300:]}")
            if op in ("install", "uninstall"):
                self.actions.note_undo({"type": "app", "op": "uninstall" if op == "install" else "install",
                                        "id": d["id"], "source": m})
            return {"install": "Installed", "upgrade": "Updated", "uninstall": "Removed"}[op] + f" {d['name']}"
        self.actions.propose(f"app_{op}", details, run)
        return WAITING + (" Windows may also ask for administrator rights during the install." if m == "winget" and op != "uninstall" else
                          " The system will ask for the password." if admin else "")


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
             + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("install", id, source), "⬇️"),
        Tool("app_update", "Update an installed program to the newest version by its id. " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("upgrade", id, source), "⬆️"),
        Tool("app_uninstall", "Remove an installed program by its id (see app_installed). " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("uninstall", id, source), "🗑"),
    ]
