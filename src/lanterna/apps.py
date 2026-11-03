"""Programs: find, install, update and remove them with the system's own package manager.

- Windows: winget, only its official catalog (source "winget").
- Linux: Flatpak (Flathub, installed for this user, no password) and the distribution's dnf/apt (through pkexec,
  which asks for the password itself).
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
RUN_TIMEOUT = 30 * 60
LOOK_TIMEOUT = 90
WINGET_COMMON = ["--source", "winget", "--accept-source-agreements", "--disable-interactivity"]


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

    @staticmethod
    def _check_id(pid: str) -> str:
        pid = str(pid or "").strip()
        if not PKG_ID.match(pid):
            raise WorkError(f"'{pid}' is not a valid package id.")
        return pid

    # -- looking up
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
        if m == "flatpak":
            code, out = self.run(["flatpak", "search", "--columns=name,application,version,description", q])
            rows = [line.split("\t") for line in out.splitlines() if line.count("\t") >= 2]
            if not rows:
                return f"Nothing found on Flathub for '{q}'."
            return "Flathub:\n" + "\n".join(f"- {r[0]} — id {r[1]}, version {r[2] or '?'}: {r[3] if len(r) > 3 else ''}"
                                             for r in rows[:15])
        code, out = self.run([m, "search", q] if m == "dnf" else ["apt", "search", "--names-only", q])
        lines = [x for x in out.splitlines() if x.strip() and not x.startswith(("Last metadata", "Sorting", "Full Text",
                                                                                   "WARNING", "Updating", "Repositories"))]
        return f"{m}:\n" + "\n".join(lines[:25]) if lines else f"Nothing found with {m} for '{q}'."

    def details(self, pid: str, source: str = "") -> dict:
        pid, m = self._check_id(pid), self._need(source)
        if m == "winget":
            code, out = self.run(["winget", "show", "--id", pid, "--exact", *WINGET_COMMON])
            d = parse_show(out)
            if not d.get("id"):
                raise WorkError(f"There is no '{pid}' in the winget catalog. Search first.")
            return {"source": m, "id": d["id"], "name": d.get("name", pid), "version": d.get("version", ""),
                    "publisher": d.get("publisher", ""), "description": d.get("description", ""),
                    "homepage": d.get("homepage", ""), "license": d.get("license", "")}
        if m == "flatpak":
            code, out = self.run(["flatpak", "remote-info", "flathub", pid])
            if code != 0:
                raise WorkError(f"There is no '{pid}' on Flathub. Search first.")
            info = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines()) if v}
            title = next((ln.strip() for ln in out.splitlines() if " - " in ln), pid)
            return {"source": m, "id": pid, "name": title.split(" - ")[0], "version": info.get("version", ""),
                    "publisher": "Flathub", "description": title.split(" - ", 1)[-1], "homepage": "", "license": info.get("license", "")}
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
        m = self._need(source)
        q = str(query or "").strip()[:80]
        if q.startswith("-"):
            raise WorkError("Bad name.")
        if m == "winget":
            code, out = self.run(["winget", "list", *(["--query", q] if q else []), "--accept-source-agreements",
                                  "--disable-interactivity"])
            rows = parse_table(out)
            if not rows:
                return f"Nothing installed matches '{q}'." if q else "Couldn't read the list of installed programs."
            return f"Installed ({len(rows)}):\n" + "\n".join(
                f"- {r['name']} — id {r['id']}, version {r.get('version', '?')}" for r in rows[:60])
        if m == "flatpak":
            code, out = self.run(["flatpak", "list", "--app", "--columns=name,application,version"])
        else:
            code, out = self.run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}\n"] if m == "dnf" else ["apt", "list", "--installed"])
        lines = [x for x in out.splitlines() if x.strip() and (not q or q.lower() in x.lower())]
        return f"Installed with {m} ({len(lines)}):\n" + "\n".join(lines[:60])

    def updates(self, source: str = "") -> str:
        m = self._need(source)
        if m == "winget":
            code, out = self.run(["winget", "upgrade", *WINGET_COMMON], timeout=180)
            rows = parse_table(out, ("name", "id", "version", "available", "source"))
            if not rows:
                return "Every program from the winget catalog is up to date."
            return f"Updates available ({len(rows)}):\n" + "\n".join(
                f"- {r['name']} — id {r['id']}: {r.get('version', '?')} → {r.get('available', '?')}" for r in rows[:60])
        if m == "flatpak":
            code, out = self.run(["flatpak", "remote-ls", "--updates", "--columns=name,application,version"])
        else:
            code, out = self.run(["dnf", "check-update", "--quiet"] if m == "dnf" else ["apt", "list", "--upgradable"])
        lines = [x for x in out.splitlines() if x.strip()]
        return f"Updates with {m}:\n" + "\n".join(lines[:60]) if lines else f"Everything from {m} is up to date."

    # -- changes (cards)
    def command(self, op: str, pid: str, m: str) -> list[str]:
        if m == "winget":
            base = {"install": ["winget", "install"], "upgrade": ["winget", "upgrade"], "uninstall": ["winget", "uninstall"]}[op]
            extra = ["--accept-package-agreements"] if op != "uninstall" else []
            src = WINGET_COMMON if op != "uninstall" else ["--accept-source-agreements", "--disable-interactivity"]
            return [*base, "--id", pid, "--exact", "--silent", *extra, *src]
        if m == "flatpak":
            return {"install": ["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", pid],
                    "upgrade": ["flatpak", "update", "--user", "-y", "--noninteractive", pid],
                    "uninstall": ["flatpak", "uninstall", "--user", "-y", "--noninteractive", pid]}[op]
        verb = {"install": "install", "upgrade": "upgrade", "uninstall": "remove"}[op]
        return ["pkexec", m, verb, "-y", pid]

    def propose(self, op: str, pid: str, source: str = "") -> str:
        if op not in ("install", "upgrade", "uninstall"):
            raise WorkError("op must be install, upgrade or uninstall.")
        pid, m = self._check_id(pid), self._need(source)
        if op == "install":
            d = self.details(pid, m)                         # the card shows what the catalog says
        else:
            d = {"source": m, "id": pid, "name": pid, "version": "", "publisher": "", "description": "", "homepage": "", "license": ""}
        cmd = self.command(op, d["id"], m)
        details = {**d, "op": op, "command": " ".join(cmd), "admin": m in ("dnf", "apt") or (m == "winget" and op != "uninstall")}

        def run() -> str:
            code, out = self.run(cmd, timeout=RUN_TIMEOUT)
            tail = "\n".join(line for line in _clean(out) if line.strip())[-600:]
            if code != 0:
                raise WorkError(f"{m} stopped with code {code}: {tail[-300:]}")
            return {"install": "Installed", "upgrade": "Updated", "uninstall": "Removed"}[op] + f" {d['name']}"
        self.actions.propose(f"app_{op}", details, run)
        return WAITING + (" Windows may also ask for administrator rights during the install." if m == "winget" and op != "uninstall" else
                          " The system will ask for the password." if m in ("dnf", "apt") else "")


def app_tools(apps: Apps) -> list:
    from .tools import Tool, _obj
    have = apps.managers()
    if not have:
        return []
    s = {"type": "string"}
    src = {"type": "string", "enum": have}
    card = "The user confirms it on a card that shows the program and the exact command, so don't ask in text first."
    return [
        Tool("app_search", f"Find a program to install in the system's official catalog ({', '.join(have)}). Use it when "
             "the user wants to install or get a program. Returns names and ids.",
             _obj({"query": s, "source": src}, ["query"]), lambda query, source="": apps.search(query, source), "🔎"),
        Tool("app_info", "Details of one program in the catalog by its id: publisher, version, description, homepage, license.",
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.info(id, source), "📦"),
        Tool("app_installed", "Programs installed on this computer (optionally only those matching a name).",
             _obj({"query": s, "source": src}), lambda query="", source="": apps.installed(query, source), "📦"),
        Tool("app_updates", "Programs on this computer that have a newer version in the catalog.",
             _obj({"source": src}), lambda source="": apps.updates(source), "⬆️"),
        Tool("app_install", "Install a program by its exact catalog id (find it with app_search first). " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("install", id, source), "⬇️"),
        Tool("app_update", "Update an installed program to the newest version by its id. " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("upgrade", id, source), "⬆️"),
        Tool("app_uninstall", "Remove an installed program by its id (see app_installed). " + card,
             _obj({"id": s, "source": src}, ["id"]), lambda id, source="": apps.propose("uninstall", id, source), "🗑"),
    ]
