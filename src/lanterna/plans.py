"""The plan of a bigger task: its steps, and which one Lanterna is doing now.

A game, a little program, a mod, a long text: the model first makes a plan with the plan tool (3-8 short steps in
the user's language), then works through it and marks each step as soon as it is finished. The window and the
terminal show it as a list over the message box (done, now, next), the way Claude shows its tasks. The plan is kept
with the chat, so a big task goes on in the next answer when the user writes "go on".

Kept as {"steps": [{"text": …, "done": bool}], "project": "<folder in Lanterna projects>" or ""}; the step being
done now is the first one that isn't done.
"""
from __future__ import annotations

import json
from typing import Callable

MAX_STEPS = 10
STEP_LEN = 120

DESCRIPTION = (
    "Your task list for a bigger job (a game, a program, a mod, a website, a plan, a long text), shown to the user "
    "as a checklist that updates while you work (also for several changes on this computer: one step per card). "
    "Start such a job with plan(steps=[3-8 short steps in the user's "
    "language]); then do the steps in order, and right after finishing one call plan(done=[its number]) "
    "(you may do that together with the next step's tool call). The first step that isn't done is the one "
    "the user sees as being done now. To change the plan, call plan(steps=[...]) again. project: the folder in "
    "Lanterna projects the job is for, if any. Steps are the work itself: telling the user the result is your "
    "final answer, not a step. Not for small questions.")
SCHEMA = {"type": "object", "properties": {
    "steps": {"type": "array", "items": {"type": "string"}, "description": "the whole list, to make or change the plan"},
    "done": {"type": "array", "items": {"type": "integer"}, "description": "numbers of the steps now finished (1 = first)"},
    "project": {"type": "string", "description": "the project folder this plan is for (optional)"}}}


class PlanError(Exception):
    pass


def load(raw: str) -> dict:
    """The plan as saved with the chat ("" or broken = no plan)."""
    try:
        d = json.loads(raw or "{}")
    except ValueError:
        return {}
    steps = [{"text": str(s.get("text") or "")[:STEP_LEN], "done": bool(s.get("done"))}
             for s in (d.get("steps") or []) if isinstance(s, dict) and str(s.get("text") or "").strip()] \
        if isinstance(d, dict) else []
    return {"steps": steps[:MAX_STEPS], "project": str(d.get("project") or "")[:80]} if steps else {}


def dumps(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False) if plan and plan.get("steps") else ""


def _numbers(done) -> list[int]:
    if done is None or done == "":
        return []
    items = done if isinstance(done, list) else [done]
    out = []
    for x in items:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            raise PlanError(f"'{x}' isn't a step number: pass the numbers of the finished steps, e.g. done=[2].") from None
    return out


def update(plan: dict, steps=None, done=None, project: str | None = None) -> dict:
    """The plan after one plan() call: steps make or change it (a step whose words stay the same keeps being done),
    done marks steps finished. Raises PlanError with words for the model."""
    plan = {"steps": [dict(s) for s in (plan or {}).get("steps", [])], "project": (plan or {}).get("project", "")}
    if steps is not None:
        if isinstance(steps, str):
            steps = [x for x in steps.splitlines()]
        if not isinstance(steps, list):
            raise PlanError("steps must be a list of short texts.")
        texts = [" ".join(str(s).split())[:STEP_LEN] for s in steps]
        texts = [x.lstrip("0123456789.) -•*").strip() or x for x in texts if x]
        if not texts:
            raise PlanError("The plan needs at least one step.")
        if len(texts) > MAX_STEPS:
            raise PlanError(f"At most {MAX_STEPS} steps: join some of them.")
        was_done = {s["text"] for s in plan["steps"] if s["done"]}
        plan["steps"] = [{"text": x, "done": x in was_done} for x in texts]
    if not plan["steps"]:
        raise PlanError("There is no plan yet: call plan with steps first.")
    for n in _numbers(done):
        if not 1 <= n <= len(plan["steps"]):
            raise PlanError(f"There is no step {n}: the plan has {len(plan['steps'])} steps.")
        plan["steps"][n - 1]["done"] = True
    if project is not None and str(project).strip():
        plan["project"] = " ".join(str(project).split())[:80]
    return plan


def current(plan: dict) -> int:
    """The number of the step being done now (1 = first); 0 when every step is done or there is no plan."""
    for i, s in enumerate((plan or {}).get("steps", []), 1):
        if not s["done"]:
            return i
    return 0


def finished(plan: dict) -> bool:
    return bool(plan and plan.get("steps")) and current(plan) == 0


def view(plan: dict) -> dict:
    """For the window and the terminal: {"steps": [{"text", "state": done | now | todo}], "done", "total", "project"};
    {} without a plan."""
    if not plan or not plan.get("steps"):
        return {}
    now = current(plan)
    steps = [{"text": s["text"], "state": "done" if s["done"] else "now" if i == now else "todo"}
             for i, s in enumerate(plan["steps"], 1)]
    return {"steps": steps, "done": sum(s["done"] for s in plan["steps"]), "total": len(steps),
            "project": plan.get("project", "")}


def window(view: dict, most: int = 6) -> tuple[list[dict], int, int]:
    """The steps a short list shows (the terminal has few lines): the step before the current one and the next
    ones. → (steps, hidden before, hidden after)."""
    steps = (view or {}).get("steps", [])
    if len(steps) <= most:
        return steps, 0, 0
    now = next((i for i, s in enumerate(steps) if s["state"] == "now"), len(steps) - 1)
    start = max(0, min(now - 1, len(steps) - most))
    return steps[start:start + most], start, len(steps) - start - most


def for_model(plan: dict) -> str:
    """The plan as the model reads it (the plan tool's answer, and the system prompt while it isn't finished)."""
    if not plan or not plan.get("steps"):
        return "There is no plan."
    now = current(plan)
    lines = [f"Plan ({sum(s['done'] for s in plan['steps'])} of {len(plan['steps'])} done"
             + (f", project folder: {plan['project']}" if plan.get("project") else "") + "):"]
    for i, s in enumerate(plan["steps"], 1):
        lines.append(f"{i}. [{'done' if s['done'] else 'now' if i == now else ' '}] {s['text']}")
    if now:
        lines.append(f"Next: step {now}. Mark it with plan(done=[{now}]) as soon as it is finished.")
    else:
        lines.append("Every step is done. Check the result once more if you haven't, then tell the user briefly what "
                     "was made, where it is and how to start or use it.")
    return "\n".join(lines)


def close_last(plan: dict) -> dict | None:
    """After an answer that ended on its own (not stopped, not out of tool rounds, with text): when only the plan's
    last step is left, that answer was it (models describe the result in the answer and forget to mark it).
    → the finished plan, or None when it doesn't apply."""
    steps = (plan or {}).get("steps", [])
    left = [i for i, s in enumerate(steps) if not s["done"]]
    if not steps or left != [len(steps) - 1]:
        return None
    return {**plan, "steps": [*steps[:-1], {**steps[-1], "done": True}]}


def reminder(plan: dict) -> str:
    """One line added to a project tool's answer while a plan is going: models forget to mark their steps."""
    now = current(plan)
    if not now:
        return ""
    return (f"\n[Plan: step {now} of {len(plan['steps'])} now: “{plan['steps'][now - 1]['text']}”. When it is "
            f"finished, call plan(done=[{now}]).]")


def plan_tool(get: Callable[[], dict], put: Callable[[dict], None]):
    """The plan tool. get/put: the plan of the chat whose answer is running (put also shows it to the user)."""
    from .tools import Tool

    def run(steps=None, done=None, project=None) -> str:
        try:
            p = update(get(), steps, done, project)
        except PlanError as e:
            return f"Error: {e}"
        put(p)
        return for_model(p)
    # a big job: making things, or several changes on this computer (sorting, moving, programs)
    return Tool("plan", DESCRIPTION, SCHEMA, run, "📋", "make pc apps plan")
