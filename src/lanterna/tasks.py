"""Regular tasks: things Lanterna does on its own on a schedule ("every morning at 8: the weather",
"in the evening: tell me if it rains tomorrow").

They run while Lanterna is open or in the tray, through the reminder loop. A run uses only safe tools
(weather, web search, reading pages, math, dates): no files, no programs, no PC settings. Tasks stay on this
device (they are not synced), so two computers never do the same task twice.
"""
from __future__ import annotations

import datetime as dt
import re

EVERY = ("day", "weekday", "week", "hour")
MAX_TASKS = 10
LATE_LIMIT = 6 * 3600              # a run missed by more than this (PC off) is skipped, not done late
SKIP = "SKIP"
SAFE_TOOLS = ("weather", "web_search", "read_page", "calculate", "date_calc")
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def clean_time(at: str, default: str = "08:00") -> str:
    m = _TIME.match((at or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else default


def next_run(every: str, at: str, day: int, after: dt.datetime) -> dt.datetime:
    """The first time after `after` that the task should run (local time).

    every: day | weekday (Mon-Fri) | week (on `day`, 0 = Monday) | hour (at minute `at`'s MM)."""
    hh, mm = (int(x) for x in clean_time(at).split(":"))
    if every == "hour":
        t = after.replace(minute=mm, second=0, microsecond=0)
        return t if t > after else t + dt.timedelta(hours=1)
    t = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t <= after:
        t += dt.timedelta(days=1)
    for _ in range(8):
        if every == "weekday" and t.weekday() >= 5 or every == "week" and t.weekday() != day % 7:
            t += dt.timedelta(days=1)
            continue
        break
    return t


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def describe(task: dict, t) -> str:
    """"Every day at 08:00" in the app's language (t = a translate function with the language bound)."""
    at = clean_time(task.get("at", ""))
    every = task.get("every", "day")
    if every == "hour":
        return t("Every hour at :{mm}", mm=at[3:])
    if every == "weekday":
        return t("On weekdays at {time}", time=at)
    if every == "week":
        return t("Every {day} at {time}", day=t(DAYS[int(task.get("day") or 0) % 7]), time=at)
    return t("Every day at {time}", time=at)


TASK_SYSTEM = ("Lanterna is now doing a regular task the user scheduled earlier; the user is not in the chat. "
               "Do the task now, using tools if needed (for weather use the weather tool), and write the result "
               "briefly: 1-5 sentences, the user's language, no questions back, no offers of more help.")


def prompt(task: dict, now: dt.datetime) -> str:
    text = f"Task: {task['text']}\nNow: {now:%A %Y-%m-%d %H:%M}"
    if task.get("only_if"):
        text += (f"\nOnly tell the user if this is true: {task['only_if']}. Check it first. If it is not true, "
                 f"reply with exactly {SKIP} and nothing else.")
    return text


def is_skip(reply: str) -> bool:
    return (reply or "").strip().strip(".!*` ").upper() == SKIP


def add(store, what: str, every: str, at: str, day: int, only_if: str, now: dt.datetime) -> tuple[int, dt.datetime]:
    """Checks and saves a new task; returns (its number, its first run). ValueError says what is wrong."""
    what = " ".join(str(what or "").split())[:300]
    if not what:
        raise ValueError("say what the task should do")
    if len(store.tasks()) >= MAX_TASKS:
        raise ValueError(f"there are already {MAX_TASKS} regular tasks; one has to go first")
    every = every if every in EVERY else "day"
    at, day = clean_time(at), int(day or 0) % 7
    when = next_run(every, at, day, now)
    return store.add_task(what, every, at, day, " ".join(str(only_if or "").split())[:200], when.timestamp()), when


def safe_toolbox(store, lang):
    """A toolbox with only the safe tools (no memory, reminders, tasks, files or PC actions)."""
    from .tools import Toolbox
    tb = Toolbox(store, lang=lang)
    tb._base = {k: v for k, v in tb._base.items() if k in SAFE_TOOLS}
    return tb
