"""“Check Lanterna”: what works and what doesn't on this computer, in plain words.

Each check gives a title, a status (ok · warn · fail · info) and a detail. Titles and details are English
templates; the caller translates them. Nothing personal goes into the result (no paths, keys or e-mails), so
it can be pasted into a bug report as it is. Network checks only talk to the services the user already uses.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass, field

from . import __version__


@dataclass
class Check:
    title: str
    status: str                     # ok | warn | fail | info
    detail: str = ""
    vars: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"title": self.title, "status": self.status, "detail": self.detail, "vars": self.vars}


MARK = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f}"


def run(api, network: bool = True) -> list[Check]:
    """All checks. `network=False` skips the ones that ask a service (for a quick bug report)."""
    from . import keys, local, updates
    from .config import data_dir
    from .providers import PROVIDERS, Client, ProviderError
    out: list[Check] = []
    s = api.settings

    # version
    kind = updates.install_kind()
    out.append(Check("Version", "info", "Lanterna {v} · {kind}", {"v": __version__, "kind": kind}))
    if network:
        u = updates.check()
        if not u.get("latest"):
            out.append(Check("Updates", "warn", "Couldn't reach the release page. Are you online?"))
        elif u.get("newer"):
            out.append(Check("Updates", "warn", "Version {v} is out. Update to get the latest fixes.", {"v": u["latest"]}))
        else:
            out.append(Check("Updates", "ok", "This is the latest version."))

    # model services and keys
    with_key = [pid for pid, p in PROVIDERS.items() if p.needs_key and keys.get_key(pid)]
    if s.mode == "local":
        out.append(Check("Mode", "info", "Local models only: nothing leaves this computer."))
    elif not with_key:
        out.append(Check("API keys", "fail", "No key for any online service. Add one in Settings → Services."))
    results: dict[str, Check] = {}

    def probe(pid: str) -> None:
        p = PROVIDERS[pid]
        try:
            c = Client(p, keys.get_key(pid) or "", timeout=12)
            n = len(c.list_models())
            c.close()
            results[pid] = Check(p.name, "ok", "Key works, {n} models.", {"n": n})
        except ProviderError as e:
            hint = {"auth": "The key was refused. Paste a new one in Settings.",
                    "network": "Can't reach the service. Check the internet connection.",
                    "timeout": "The service didn't answer in time. Check the internet connection.",
                    "rate": "The free limit is reached for now; it resets by itself."}.get(e.kind, "Error: {error}")
            results[pid] = Check(p.name, "warn" if e.kind == "rate" else "fail", hint, {"error": str(e)[:120]})
        except Exception as e:                            # noqa: BLE001  one service never stops the others
            results[pid] = Check(p.name, "fail", "Error: {error}", {"error": e.__class__.__name__})

    if network and s.mode != "local":
        threads = [threading.Thread(target=probe, args=(pid,), daemon=True) for pid in with_key]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)
        out += [results.get(pid) or Check(PROVIDERS[pid].name, "fail", "No answer in 20 seconds.") for pid in with_key]
    else:
        out += [Check(PROVIDERS[pid].name, "info", "A key is saved.") for pid in with_key]

    resting = api._router.resting() if getattr(api, "_router", None) else {}
    if resting:
        out.append(Check("Limits", "warn", "{n} models are resting after a limit; Lanterna uses the others meanwhile.",
                         {"n": len(resting)}))

    # the system vault for keys and sign-ins
    try:
        import keyring
        backend = keyring.get_keyring()
        name = backend.__class__.__name__
        bad = "fail" in name.lower() or "null" in name.lower() or getattr(backend, "priority", 1) <= 0
        out.append(Check("Key vault", "fail" if bad else "ok",
                         "No system vault: keys and sign-ins can't be saved. On Linux install gnome-keyring or KWallet."
                         if bad else "{name}", {"name": name}))
    except Exception as e:                                # noqa: BLE001
        out.append(Check("Key vault", "fail", "Error: {error}", {"error": e.__class__.__name__}))

    # sync and connectors
    st = api.sync_status()
    if st["phase"] == "off":
        out.append(Check("Sync", "info", "Not signed in with Google: chats stay on this device."))
    elif st["phase"] == "error" or (st.get("error") and st["phase"] != "ready"):
        out.append(Check("Sync", "fail", "Sync error: {error}", {"error": str(st["error"])[:120]}))
    elif st["phase"] in ("ready", "syncing"):
        out.append(Check("Sync", "ok", "Signed in; chats sync between your devices."))
    else:
        out.append(Check("Sync", "warn", "Signed in, but the sync password is not entered yet."))
    for name, status in (("Google Drive", api.drive_status()), ("GitHub", api.github_status())):
        if status.get("phase") == "ready":
            out.append(Check(name, "ok", "Connected."))
        elif status.get("error") and status.get("error") != "not_configured":
            out.append(Check(name, "warn", "Problem: {error}", {"error": str(status["error"])[:100]}))

    # help with this computer
    if not s.pc_access:
        out.append(Check("Help with this computer", "info", "Turned off in Settings → Computer."))
    else:
        found = api.places.folders()
        out.append(Check("Your folders", "ok" if found else "warn", "{n} of 6 standard folders found.", {"n": len(found)}))
        have = api.apps.managers()
        out.append(Check("Programs", "ok" if have else "warn",
                         "Installs with {tools}." if have else "No winget, dnf, apt or Flatpak found: Lanterna can't install programs.",
                         {"tools": ", ".join(have)}))

    # local models
    v = local.version()
    if v:
        n = len(local.installed())
        out.append(Check("Ollama (local models)", "ok" if n else "warn",
                         "Ollama {v}, {n} models." if n else "Ollama {v} runs, but no model is downloaded yet.", {"v": v, "n": n}))
    else:
        out.append(Check("Ollama (local models)", "info", "Not installed or not running. Optional: for chatting without internet."))

    # Lanterna's own folder
    try:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        probe_file = d / ".write-test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        free = shutil.disk_usage(d).free
        out.append(Check("Data folder", "ok" if free > 1024 ** 3 else "warn",
                         "{gb} GB free." if free > 1024 ** 3 else "Only {gb} GB free on this disk; chats may stop saving.",
                         {"gb": _gb(free)}))
    except OSError as e:
        out.append(Check("Data folder", "fail", "Can't write: {error}", {"error": e.__class__.__name__}))

    # terminal (Linux terminal app)
    if sys.platform.startswith("linux") and sys.stdout.isatty():
        term = os.environ.get("TERM", "")
        colors = os.environ.get("COLORTERM", "")
        bad = term in ("", "dumb", "linux")
        out.append(Check("Terminal", "warn" if bad else "ok",
                         "{term}: the full-screen app may look wrong. Use a terminal app like GNOME Terminal or Konsole."
                         if bad else "{term}{colors}", {"term": term or "?", "colors": f" · {colors}" if colors else ""}))
    return out


def summary(checks: list[Check], tr=lambda s, **kw: s.format(**kw) if kw else s) -> list[str]:
    """Plain lines for a bug report or the terminal."""
    lines = []
    for c in checks:
        detail = tr(c.detail, **c.vars) if c.detail else ""
        lines.append(f"{MARK[c.status]} {tr(c.title)}: {detail}")
    return lines
