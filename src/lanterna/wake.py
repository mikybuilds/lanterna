"""Reminders when Lanterna is closed: the system starts it for a moment at the next reminder's time.

Windows: one task of the user's own in Task Scheduler (\\Lanterna\\Reminders, no administrator rights) starts
`Lanterna.exe --remind` once at the next reminder's time, or as soon as it can after it if the computer was off or
asleep then. Linux: a systemd user timer (~/.config/systemd/user/lanterna-reminders.timer) does the same; it is
Persistent, so a time missed while the computer was off comes when it starts again.

That run shows what is due as a system notification, sets the alarm for the next reminder and quits; if Lanterna
is open, it leaves the reminders to it. A reminder never comes twice: the database hands each one out once, also
between two programs. With no reminders left, the task or timer is taken away; Settings → Memory and reminders
turns all of it off. Nothing runs in between.

Only for the usual data folder: with LANTERNA_HOME set (tests, a second profile, a preview) the system is never
touched, since its run wouldn't find that folder.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape

from .config import data_dir

TASK = r"Lanterna\Reminders"
UNIT = "lanterna-reminders"
RETRY = 3600                        # an alarm that couldn't be set is tried again after an hour, not every 15 s
ALIVE = 45                          # Lanterna is open if its reminder loop said so within this many seconds
LATE = 120                          # a reminder shown this much after its time says when it was due
SOON = 5                            # a reminder due within this many seconds counts as due now

# what Settings → Memory and reminders says about it (the window has the same two in app.js)
NOTES = {
    "win32": "At a reminder's time Windows starts Lanterna for a moment (Task Scheduler) to show it; if the computer "
             "was off, right after you sign in. Nothing runs in between.",
    "linux": "At a reminder's time the system starts Lanterna for a moment (a systemd timer) to show it; if the "
             "computer was off, right after it starts. Nothing runs in between.",
}

_state: dict | None = None


def allowed() -> bool:
    """The alarm is only for the usual data folder (see above)."""
    return not os.getenv("LANTERNA_HOME")


def due_line(r: dict, now: float) -> str:
    """A reminder's notification text; one shown late (the computer was off) says when it was due."""
    late = now - r["due"] > LATE
    return r["text"] + (f" ({time.strftime('%H:%M', time.localtime(r['due']))})" if late else "")


# ---------------------------------------------------------------- is Lanterna open?
def _alive_file() -> Path:
    return data_dir() / "alive"


def still_here() -> None:
    """The open Lanterna's reminder loop says so every few seconds (a run at a reminder's time then leaves it)."""
    try:
        p = _alive_file()
        p.touch()
    except OSError:
        pass


def gone() -> None:
    """Lanterna is quitting: from now on a run at a reminder's time shows them (also one due in a moment)."""
    try:
        _alive_file().unlink(missing_ok=True)
    except OSError:
        pass


def running(now: float | None = None) -> bool:
    try:
        return ((time.time() if now is None else now) - _alive_file().stat().st_mtime) < ALIVE
    except OSError:
        return False


# ---------------------------------------------------------------- the run at a reminder's time
def remind_now() -> int:
    """`Lanterna.exe --remind` / `lanterna remind`: shows what is due and sets the next alarm."""
    if running():                   # Lanterna is open: its own loop shows them, in the app too
        return 0
    from .config import Settings
    from .notify import notify
    from .store import Store
    on = Settings.load().remind_closed      # turned off: nothing is shown, the alarm goes away
    store = Store()
    try:
        now = time.time()
        for _ in range(10 if on else 0):    # also what comes due while these are shown
            now = time.time()
            due = store.take_due(now + SOON)                # the alarm may ring a moment early
            for r in due:
                notify("Lanterna ⏰", due_line(r, now))
            if not due:
                break
        sync(store, on, now, closing=True)
    finally:
        store.close()
    return 0


# ---------------------------------------------------------------- the alarm
def command() -> list[str]:
    """What the system runs at the reminder's time."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--remind"]
    exe = Path(sys.executable)
    if sys.platform == "win32":
        pyw = exe.with_name("pythonw.exe")                  # no black window for a moment
        return [str(pyw if pyw.is_file() else exe), "-m", "lanterna.gui", "--remind"]
    found = shutil.which("lanterna")
    return [found, "remind"] if found else [str(exe), "-m", "lanterna.cli", "remind"]


def _run(args: list[str], timeout: float = 30) -> int:
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


def task_xml(when: float, cmd: list[str]) -> str:
    """The Task Scheduler task: once at `when` (local time), as soon as possible after it if it was missed, only
    while the user is signed in (a notification needs them), on battery too."""
    start = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(when))
    exe = cmd[0] if " " not in cmd[0] else f'"{cmd[0]}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>Lanterna</Author>
    <Description>Shows Lanterna's next reminder when Lanterna is closed. Lanterna removes this task when no reminders are left; Settings, Memory and reminders turns it off.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{escape(exe)}</Command><Arguments>{escape(subprocess.list2cmdline(cmd[1:]))}</Arguments></Exec>
  </Actions>
</Task>
"""


def _units() -> Path:
    return Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"


def _stamp() -> Path:
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "systemd" / "timers" / f"stamp-{UNIT}.timer"


def _sd_quote(arg: str) -> str:
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def service_text(cmd: list[str]) -> str:
    return ("[Unit]\nDescription=Lanterna: shows a reminder when Lanterna is closed\n\n"
            f"[Service]\nType=oneshot\nExecStart={' '.join(_sd_quote(a) for a in cmd)}\n")


def timer_text(when: float) -> str:
    """Once at `when` (local time); Persistent: missed while the computer was off, it comes when it starts."""
    return ("[Unit]\nDescription=Lanterna's next reminder (Lanterna removes it when no reminders are left)\n\n"
            f"[Timer]\nOnCalendar={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(when))}\nPersistent=true\n"
            "AccuracySec=1s\n\n[Install]\nWantedBy=timers.target\n")


def arm(when: float | None) -> bool:
    """Sets the system's alarm to `when` (None takes it away). True when that worked."""
    try:
        if sys.platform == "win32":
            if when is None:
                _run(["schtasks", "/Delete", "/TN", TASK, "/F"])    # (not there: nothing to take away)
                return True
            with tempfile.TemporaryDirectory(prefix="lanterna-") as d:
                xml = Path(d) / "task.xml"
                xml.write_text(task_xml(when, command()), encoding="utf-16")
                return _run(["schtasks", "/Create", "/TN", TASK, "/XML", str(xml), "/F"]) == 0
        if sys.platform.startswith("linux") and shutil.which("systemctl"):
            units = _units()
            timer, service = units / f"{UNIT}.timer", units / f"{UNIT}.service"
            if when is None:
                if timer.exists() or service.exists():
                    _run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"])
                    for p in (timer, service, _stamp()):
                        p.unlink(missing_ok=True)
                    _run(["systemctl", "--user", "daemon-reload"])
                return True
            units.mkdir(parents=True, exist_ok=True)
            service.write_text(service_text(command()), encoding="utf-8")
            timer.write_text(timer_text(when), encoding="utf-8")
            return all(_run(["systemctl", "--user", *a]) == 0 for a in
                       (["daemon-reload"], ["enable", f"{UNIT}.timer"], ["restart", f"{UNIT}.timer"]))
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def _state_file() -> Path:
    return data_dir() / "wake.json"


def _load() -> dict:
    global _state
    if _state is None:
        try:
            _state = json.loads(_state_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _state = {}
    return _state


def sync(store, on: bool = True, now: float | None = None, closing: bool = False) -> bool:
    """Sets the alarm to the next reminder (on), or takes it away (off, or no reminders). Cheap when nothing
    changed: the system is asked only when the time does, and a failure waits an hour before the next try.
    `closing`: no Lanterna is left to show one that is due now, so the system shows it in a moment."""
    global _state
    if not allowed():
        return False
    now = time.time() if now is None else now
    nxt = store.next_reminder() if on else None
    st = _load()
    if nxt is not None and nxt <= now + SOON:
        if not closing:             # the open Lanterna shows it in a moment, then the alarm moves on
            return bool(st.get("ok"))
        nxt = now + SOON
    when = None if nxt is None else math.ceil(nxt)          # never before the reminder's time
    cmd = command()                 # (a moved or newly installed Lanterna gets the alarm too)
    if ("armed" in st and st["armed"] == when and st.get("cmd") == cmd
            and (st.get("ok") or now - st.get("tried", 0) < RETRY)):
        return bool(st.get("ok"))
    ok = arm(when)
    _state = {"armed": when, "cmd": cmd, "ok": ok, "tried": now}
    try:
        _state_file().write_text(json.dumps(_state), encoding="utf-8")
    except OSError:
        pass
    return ok


def forget() -> None:
    """Takes the alarm away for good (Lanterna is being removed)."""
    global _state
    arm(None)
    _state = None
    try:
        _state_file().unlink(missing_ok=True)
    except OSError:
        pass
