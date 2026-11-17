"""Round 141: rules for how every model thinks, a task plan shown like Claude's task list, and Lanterna's own
project folder for games, little programs and game mods (Documents/Lanterna projects)."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import chat, plans, projects
from lanterna.chat import Conversation
from lanterna.projects import Projects, brackets, check_text, clean_name
from lanterna.providers import ToolCall, ToolCalls
from lanterna.store import Store
from lanterna.workspace import WorkError


# ---------------------------------------------------------------- the plan
def test_a_plan_is_made_marked_and_shown():
    p = plans.update({}, steps=["1. Придумати правила", "Написати гру", "  Перевірити  "], project="Змійка")
    assert [s["text"] for s in p["steps"]] == ["Придумати правила", "Написати гру", "Перевірити"]
    assert plans.current(p) == 1 and not plans.finished(p)
    p = plans.update(p, done=[1])
    v = plans.view(p)
    assert [s["state"] for s in v["steps"]] == ["done", "now", "todo"]
    assert (v["done"], v["total"], v["project"]) == (1, 3, "Змійка")
    text = plans.for_model(p)
    assert "1. [done] Придумати правила" in text and "2. [now] Написати гру" in text and "plan(done=[2])" in text
    p = plans.update(p, done=[2, 3])
    assert plans.finished(p) and "Every step is done" in plans.for_model(p)
    assert plans.load(plans.dumps(p)) == p


def test_changing_the_plan_keeps_what_is_done():
    p = plans.update({}, steps=["A", "B", "C"], done=[1])
    p = plans.update(p, steps=["A", "B2", "C", "D"])
    assert [s["done"] for s in p["steps"]] == [True, False, False, False]


@pytest.mark.parametrize("kw, words", [({"done": [1]}, "no plan yet"), ({"steps": []}, "at least one step"),
                                       ({"steps": [str(i) for i in range(11)]}, "At most 10"),
                                       ({"steps": ["A"], "done": [5]}, "no step 5"),
                                       ({"steps": ["A"], "done": ["x"]}, "isn't a step number")])
def test_plan_mistakes_are_told_to_the_model(kw, words):
    with pytest.raises(plans.PlanError, match=words):
        plans.update({}, **kw)


def test_a_broken_saved_plan_is_no_plan():
    assert plans.load("") == {} and plans.load("{oops") == {} and plans.load('{"steps": "x"}') == {}
    assert plans.view({}) == {} and plans.dumps({}) == ""


def test_the_plan_tool_saves_and_shows_each_change():
    saved, shown = {}, []

    def put(p):
        saved.update(p)
        shown.append(plans.view(p))
    tool = plans.plan_tool(lambda: dict(saved), put)
    assert tool.name == "plan" and "make" in tool.group.split()
    assert "Next: step 1" in tool.run(steps=["Написати", "Перевірити"])
    assert "Next: step 2" in tool.run(done=[1])
    assert tool.run(done=[9]).startswith("Error:")
    assert [s["state"] for s in shown[-1]["steps"]] == ["done", "now"]


def test_a_short_list_shows_the_step_before_and_the_next_ones():
    v = plans.view(plans.update({}, steps=[str(i) for i in range(1, 10)], done=[1, 2, 3, 4]))
    steps, before, after = plans.window(v)
    assert [s["text"] for s in steps] == ["4", "5", "6", "7", "8", "9"] and (before, after) == (3, 0)
    v = plans.view(plans.update({}, steps=[str(i) for i in range(1, 10)]))
    steps, before, after = plans.window(v)
    assert steps[0]["text"] == "1" and (before, after) == (0, 3)


def test_only_the_last_step_left_is_closed_by_the_answer():
    p = plans.update({}, steps=["A", "B", "C"], done=[1, 2])
    assert plans.finished(plans.close_last(p))
    assert plans.close_last(plans.update({}, steps=["A", "B", "C"], done=[1])) is None
    assert plans.close_last(plans.update({}, steps=["A", "B", "C"], done=[1, 3])) is None   # the middle one isn't done
    assert plans.close_last({}) is None


def test_project_tools_remind_the_model_of_the_step():
    p = plans.update({}, steps=["Написати гру", "Перевірити"])
    assert "step 1 of 2" in plans.reminder(p) and "plan(done=[1])" in plans.reminder(p)
    assert plans.reminder(plans.update(p, done=[1, 2])) == ""


# ---------------------------------------------------------------- the project folder
@pytest.fixture()
def pr(tmp_path):
    opened = []
    out = Projects(root=lambda: tmp_path / "Lanterna projects", opener=opened.append)
    out.opened = opened
    return out


def test_the_folder_is_in_documents_unless_told_otherwise(monkeypatch, tmp_path):
    assert projects.default_root() == Path(os.environ["LANTERNA_PROJECTS"])     # the tests never use the real one
    monkeypatch.delenv("LANTERNA_PROJECTS")
    from lanterna import pcfiles
    monkeypatch.setattr(pcfiles, "known_folders", lambda: {"documents": tmp_path / "Docs"})
    assert projects.default_root() == tmp_path / "Docs" / "Lanterna projects"


def test_project_names_are_made_safe():
    assert clean_name('  Гра: "Змійка" / v2. ') == "Гра Змійка v2"
    for bad in ("", "  ", "...", "con", "NUL.txt", '<>:"/\\|?*'):
        with pytest.raises(WorkError):
            clean_name(bad)


def test_files_are_written_at_once_only_inside_the_project(pr, tmp_path):
    out = pr.write("Змійка", "index.html", "<html><body>hi</body></html>")
    assert "Wrote Змійка/index.html" in out
    f = tmp_path / "Lanterna projects" / "Змійка" / "index.html"
    assert f.read_text(encoding="utf-8") == "<html><body>hi</body></html>"
    pr.write("Змійка", "data/levels.json", '{"a": 1}')
    assert (f.parent / "data" / "levels.json").is_file()
    for bad in ("../escape.txt", "a/../../escape.txt", "C:/Windows/x.txt", "", "con.txt"):
        with pytest.raises(WorkError):
            pr.write("Змійка", bad, "x")
    assert not (tmp_path / "Lanterna projects" / "escape.txt").exists() and not (tmp_path / "escape.txt").exists()


def test_files_that_could_run_a_program_are_never_written(pr):
    for name in ("game.exe", "start.bat", "run.cmd", "x.ps1", "game.js", "a.vbs", "app.hta", "x.lnk", "x.desktop",
                 "x.sh", "x.jar", "x.reg", "x.scr"):
        with pytest.raises(WorkError, match="could run a program"):
            pr.write("P", name, "x")
    with pytest.raises(WorkError, match="inside the HTML file"):
        pr.write("P", "game.js", "x")
    assert "Wrote" in pr.write("P", "main.js.txt", "let a = 1;")       # the user renames it if they need it
    with pytest.raises(WorkError, match="only text files"):
        pr.write("P", "sprite.png", "x")


def test_a_long_file_is_written_in_parts(pr, tmp_path):
    pr.write("P", "a.py", "print(1)\n")
    assert "Added to" in pr.write("P", "a.py", "print(2)\n", mode="append")
    assert (tmp_path / "Lanterna projects" / "P" / "a.py").read_text(encoding="utf-8") == "print(1)\nprint(2)\n"
    assert "Rewrote" in pr.write("P", "a.py", "print(3)\n")


def test_the_note_about_an_earlier_file_is_never_written_as_a_file(pr):
    with pytest.raises(WorkError, match="not a file's text"):
        pr.write("P", "index.html", chat.SHRUNK.format(n=5000, end="</html>"))


def test_a_quick_look_follows_each_write(pr):
    assert "quick look found" in pr.write("P", "a.py", "def f(:\n    pass\n").lower()
    assert "quick look" not in pr.write("P", "b.py", "def f():\n    pass\n").lower()


def test_a_piece_of_a_file_is_changed_only_when_it_is_there_once(pr):
    pr.write("P", "a.py", "x = 1\ny = 2\nx = 1\n")
    with pytest.raises(WorkError, match="2 times"):
        pr.edit("P", "a.py", "x = 1", "x = 3")
    with pytest.raises(WorkError, match="isn't in"):
        pr.edit("P", "a.py", "z = 9", "z = 3")
    assert "line 2" in pr.edit("P", "a.py", "y = 2", "y = 5")
    assert "y = 5" in pr.read("P", "a.py")


def test_reading_goes_in_parts_that_fit_the_model(pr):
    pr.write("P", "long.txt", "a" * 5000)
    first = pr.read("P", "long.txt", 0, 2000)
    assert "start=1700" in first and first.count("a") >= 1700
    assert "more characters" not in pr.read("P", "long.txt", 1700, 20000)


def test_projects_and_their_files_are_listed(pr):
    assert "no projects yet" in pr.list()
    pr.write("Змійка", "index.html", "<p>x</p>")
    pr.write("Тетріс", "game.py", "print(1)")
    assert "Змійка" in pr.list() and "Тетріс" in pr.list()
    assert "index.html" in pr.list("Змійка") and "There is no project" in pr.list("Нема")


def test_the_check_finds_mistakes_and_missing_files(pr):
    pr.write("P", "index.html", '<html><head><script src="game.js.txt"></script><link rel="stylesheet" href="style.css">'
                                "</head><body><div><p>x</div></body></html>")
    pr.write("P", "bad.py", "def f(:\n  pass\n")
    pr.write("P", "data.json", '{"a": 1,}')
    out = pr.check("P")
    assert "bad.py: line 1" in out and "data.json: line 1" in out
    assert "'style.css' isn't in the project" in out and "game.js.txt" in out
    assert "with mistakes" in out and "nothing was run" not in out
    pr.write("P", "style.css", "a { color: red; }")
    pr.write("P", "game.js.txt", "let a = 1;")
    pr.write("P", "bad.py", "def f():\n  pass\n")
    pr.write("P", "data.json", '{"a": 1}')
    out = pr.check("P")
    assert "no mistakes found" in out and "nothing was run" in out


def test_python_is_only_compiled_never_run(pr, tmp_path):
    flag = tmp_path / "ran.txt"
    pr.write("P", "x.py", f"open({str(flag)!r}, 'w').write('ran')\n")
    assert "no mistakes" in pr.check("P") and not flag.exists()


def test_a_cut_off_page_is_found():
    page = "<!DOCTYPE html>\n<html><body>\n<script>\nfunction step() {\n  if (a) {\n"
    problems = check_text("index.html", page)
    assert any("never closed" in p and "cut off" in p for p in problems)
    whole = page + "  }\n}\n</script>\n</body></html>\n"
    assert check_text("index.html", whole) == []


@pytest.mark.parametrize("code", [
    "const s = 'a { b'; const t = \"(\"; // ( {\n/* { [ */ let r = /[(]+\\//g; f(r);",
    "const t = `x ${a + `y ${b}`} z`; g({a: [1, 2]});",
    "let half = w / 2, q = (a) / (b); x = y / z / 2;",
    "if (a) {\n  b = [1, 2, 3].map(x => ({ x }));\n}\n",
])
def test_brackets_in_texts_comments_and_regexes_are_not_counted(code):
    assert brackets(code, "js") == ""


@pytest.mark.parametrize("code, style, words", [
    ("function f() {\n  if (a) {\n}\n", "js", "line 1: '{' is never closed"),
    ("f(a];", "js", "']' where ')' was expected"),
    ("x = 'abc\ny = 1", "js", "isn't closed on its line"),
    ("class A {\n  void f() { }\n", "c", "'{' is never closed"),
    ("a { color: red; } }", "css", "'}' closes nothing"),
    ("local t = {1, 2\nprint(t)", "lua", "'{' is never closed"),
])
def test_bracket_mistakes_are_found(code, style, words):
    assert words in brackets(code, style)


def test_other_languages_are_not_blamed_for_what_is_fine():
    assert brackets("fn f<'a>(x: &'a str) -> &'a str { x }", "c") == ""          # Rust lifetimes
    assert brackets("char c = '{'; String s = \"}\"; var p = @\"C:\\dir\\\";", "c") == ""   # C# verbatim string
    assert brackets('func f():\n    """a ( doc"""\n    print("(")  # )\n', "hash") == ""
    assert brackets("local s = [[ ( ]] -- (\n--[[ { ]]\nprint(s)", "lua") == ""
    assert check_text("x.svg", '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>') == []
    assert check_text("x.mcfunction", "say ( hi") == []                              # not looked at


def test_only_pages_pictures_and_texts_are_opened(pr, tmp_path):
    pr.write("P", "index.html", "<p>x</p>")
    pr.write("P", "game.py", "print(1)")
    assert "Opened" in pr.open("P") and "Opened" in pr.open("P", "index.html")
    assert pr.opened == [tmp_path / "Lanterna projects" / "P", tmp_path / "Lanterna projects" / "P" / "index.html"]
    with pytest.raises(WorkError, match="starting a program is for the user"):
        pr.open("P", "game.py")
    with pytest.raises(WorkError):
        pr.open("Нема")


# ---------------------------------------------------------------- tools and how the model is told
def test_the_make_group_comes_with_games_programs_and_mods():
    from lanterna.tools import GROUPS
    rx = GROUPS["make"]
    for q in ("зроби мені гру змійка", "створи міні-гру", "напиши програму для обліку", "зроби мод для майнкрафту",
              "make me a snake game", "write a python script", "a datapack for Minecraft", "crea un gioco",
              "schreib ein Spiel", "haz un juego", "fais un jeu", "zrób grę", "створи сайт-візитку", "html сторінка"):
        assert rx.search(q), q
    for q in ("привіт", "яка погода завтра?", "встанови Telegram", "відкрий сайт google", "що таке рекурсія?"):
        assert not rx.search(q), q


def test_every_answer_gets_the_thinking_rules_and_big_jobs_the_work_rules():
    plain = chat.system_prompt("Mia")
    assert chat.THINK_GUIDE in plain and chat.WORK_GUIDE not in plain and chat.PROJECT_GUIDE not in plain
    made = chat.system_prompt("Mia", tools=True, make=True)
    assert chat.WORK_GUIDE in made and chat.PROJECT_GUIDE in made and "12 tool rounds" in made


def test_the_user_asking_for_questions_gets_the_form_even_with_asking_off():
    assert chat.wants_questions("уточни в мене деталі") and chat.wants_questions("Ask me some questions first")
    assert not chat.wants_questions("яка погода?")
    assert chat.big_task("зроби мод для майнкрафту") and chat.big_task("make me a mini-game")


class _Router:
    """A pretend model: plays the given turns (a list of tool calls, or text)."""
    current = SimpleNamespace(label="test", provider="groq")
    candidates: list = []

    def __init__(self, turns):
        self.turns, self.seen = turns, []

    def lacks_tools(self):
        return False

    def quick_order(self):
        return []

    def stream(self, msgs, **kw):
        self.seen.append({"msgs": json.loads(json.dumps(msgs, default=str)), "kw": kw})
        a = self.turns[min(len(self.seen) - 1, len(self.turns) - 1)]
        if kw.get("tool_choice") == "none" and not isinstance(a, str):
            a = "Далі буде."                                  # no tools allowed: a real model answers in words
        if isinstance(a, str):
            yield a
        else:
            n = len(self.seen)
            yield ToolCalls([ToolCall(f"c{n}{i}", name, json.dumps(args, ensure_ascii=False))
                             for i, (name, args) in enumerate(a)])


class _Box:
    def __init__(self):
        self.runs = []
        self.store = SimpleNamespace(facts=lambda: [])
        self.tools = {n: SimpleNamespace(label="🛠") for n in ("plan", "project_write", "project_check", "web_search")}
        self.focus, self.page_limit = "", 6000

    def schemas(self, ctx=None):
        return [{"type": "function", "function": {"name": n, "description": "", "parameters": {}}} for n in self.tools]

    def run(self, name, args):
        self.runs.append(name)
        return f"ran {name}"


def test_a_plan_gets_twelve_tool_rounds():
    searches = [[("web_search", {"query": f"тема{i} слово{i}"})] for i in range(15)]   # all different searches
    turns = [[("plan", {"steps": ["a", "b"]})], *searches, "done"]
    r, box = _Router(turns), _Box()
    conv = Conversation(router=r, toolbox=box)
    "".join(p for p in conv.ask("зроби гру") if isinstance(p, str))
    assert box.runs.count("web_search") == chat.PLAN_ROUNDS - 1 and conv.out_of_rounds
    r2, box2 = _Router([*searches, "done"]), _Box()
    "".join(p for p in Conversation(router=r2, toolbox=box2).ask("питання") if isinstance(p, str))
    assert box2.runs.count("web_search") == chat.MAX_TOOL_ROUNDS                  # without a plan: still 4


def test_an_unfinished_plan_goes_into_the_prompt_and_keeps_its_rounds():
    r, box = _Router(["ок"]), _Box()
    conv = Conversation(router=r, toolbox=box, plan_text="Plan (1 of 2 done):\n1. [done] A\n2. [now] B")
    "".join(p for p in conv.ask("далі") if isinstance(p, str))
    system = r.seen[0]["msgs"][0]["content"]
    assert "Your task plan in this chat is not finished" in system and "2. [now] B" in system
    assert "(task plan)" in conv._context("далі") and not conv.out_of_rounds


def test_a_check_after_a_change_runs_again():
    write = ("project_write", {"project": "P", "path": "a.py", "text": "x"})
    fix = ("project_write", {"project": "P", "path": "a.py", "text": "y"})
    check = ("project_check", {"project": "P"})
    r, box = _Router([[write], [check], [write], [check], [fix], [check], [check], "ок"]), _Box()
    out = "".join(p for p in Conversation(router=r, toolbox=box).ask("зроби гру") if isinstance(p, str))
    assert box.runs == ["project_write", "project_check", "project_write", "project_check"] and out.endswith("ок")
    tool_texts = [m["content"] for m in r.seen[-1]["msgs"] if m.get("role") == "tool"]
    # the same text again changes nothing: neither it nor the check after it runs; the last check neither
    assert [t.startswith("Not run") for t in tool_texts] == [False, False, True, True, False, False, True]


def test_a_written_file_goes_to_the_model_once():
    big = "<html>" + "x" * 5000 + "</html>"
    r, box = _Router([[("project_write", {"project": "P", "path": "index.html", "text": big})], "ок"]), _Box()
    "".join(p for p in Conversation(router=r, toolbox=box).ask("зроби гру") if isinstance(p, str))
    later = json.dumps(r.seen[1]["msgs"], ensure_ascii=False)
    assert "x" * 5000 not in later and "[saved: 5013 characters" in later and "</html>" in later
    small = ToolCall("c", "project_write", json.dumps({"project": "P", "path": "a", "text": "x"}))
    assert chat.shrunk_call(small) == small.message()
    signed = ToolCall("c", "project_write", json.dumps({"text": big}), extra={"google": {"thought_signature": "s"}})
    assert chat.shrunk_call(signed) == signed.message()                          # Gemini 3's signed calls stay


def test_text_of_two_rounds_is_not_glued_together():
    r, box = _Router([[("plan", {"steps": ["a"]})], "Готово."]), _Box()

    def first(msgs, **kw):                                    # a few words before the tool call, then the answer
        r.seen.append(1)
        if len(r.seen) == 1:
            yield "Складаю план."
            yield ToolCalls([ToolCall("c1", "plan", json.dumps({"steps": ["a"]}))])
        else:
            yield "Готово."
    r.stream = first
    conv = Conversation(router=r, toolbox=box)
    "".join(p for p in conv.ask("зроби гру") if isinstance(p, str))
    assert conv.last_reply == "Складаю план.\n\nГотово."


def test_the_plan_budget_note_says_the_rest_waits():
    assert "next answer" in chat.budget_note(1, plan=True) and "go on" in chat.budget_note(0, plan=True)
    assert "broadening" in chat.budget_note(1)


# ---------------------------------------------------------------- the app: stored, streamed, cleared
def _api(tmp_path, monkeypatch):
    from lanterna import keys
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.ai_titles = api.settings.follow_ups = api.settings.auto_memory = False
    api.settings.compact_chats = False
    return api


def _answer(api, tid, text, turns):
    from lanterna.app import _Stream
    sid = os.urandom(4).hex()
    api._streams[sid] = _Stream("uk")
    api._run(sid, tid, text, [m for m in api.store.messages(tid)], router=_Router(turns))
    return api.poll(sid)


GAME = "<!DOCTYPE html>\n<html><body><canvas></canvas>\n<script>\nfunction f() { return 1; }\n</script>\n</body></html>\n"


def test_a_whole_job_with_the_real_tools(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tid = api.new_thread()["id"]
    p = _answer(api, tid, "зроби мені гру змійка", [
        [("plan", {"steps": ["Правила", "Написати гру", "Перевірити"], "project": "Змійка"})],
        [("plan", {"done": [1]}), ("project_write", {"project": "Змійка", "path": "index.html", "text": GAME})],
        [("project_check", {"project": "Змійка"}), ("plan", {"done": [2]})],
        "Гра готова: Documents/Lanterna projects/Змійка/index.html."])
    assert not p["error"] and p["final"].startswith("Гра готова")
    assert [s["state"] for s in p["plan"]["steps"]] == ["done", "done", "done"]   # the answer was the last step
    assert (Path(os.environ["LANTERNA_PROJECTS"]) / "Змійка" / "index.html").read_text(encoding="utf-8") == GAME
    assert api.plan(tid)["done"] == 3
    shown = [s["text"] for s in p["steps"]]
    assert shown.count("Складаю план") == 1 and "Пишу index.html" in shown        # marking a step isn't a line
    p2 = _answer(api, tid, "дякую", ["Будь ласка!"])                              # a finished plan goes away
    assert p2["plan"] == {} and api.plan(tid) == {}


def test_a_job_cut_by_the_round_limit_keeps_its_steps(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tid = api.new_thread()["id"]
    turns = [[("plan", {"steps": ["A", "B"]})], [("plan", {"done": [1]})],
             *([[("project_write", {"project": "P", "path": f"f{i}.txt", "text": "x"})] for i in range(20)]), "Далі буде."]
    p = _answer(api, tid, "зроби гру", turns)
    assert p["final"] and api.plan(tid)["done"] == 1                               # step B isn't marked for it
    r = _Router(["ок"])
    from lanterna.app import _Stream
    api._streams["x"] = _Stream("uk")
    api._run("x", tid, "далі", [], router=r)
    assert "2. [now] B" in r.seen[0]["msgs"][0]["content"]                          # the next answer goes on


def test_private_chats_keep_their_plan_only_in_memory(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tid = api.new_thread(private=True)["id"]
    assert tid < 0
    _answer(api, tid, "зроби гру", [[("plan", {"steps": ["A", "B"]})], "ок"])
    assert api.plan(tid)["total"] == 2
    api.clear_plan(tid)
    assert api.plan(tid) == {}


def test_the_plan_is_kept_with_the_chat_and_never_synced(tmp_path):
    s = Store(tmp_path / "a.db")
    tid = s.new_thread("Гра")
    s.set_plan(tid, plans.dumps(plans.update({}, steps=["A"])))
    again = Store(tmp_path / "a.db")
    assert plans.load(again.plan(tid))["steps"][0]["text"] == "A"
    assert "plan" not in json.dumps(s.export_sync(), ensure_ascii=False)
    s.delete_thread(tid)
    assert s.plan(tid) == ""


def test_the_window_may_call_the_plan_methods(tmp_path, monkeypatch):
    from lanterna import gui
    assert {"plan", "clear_plan", "open_project"} <= gui.METHODS
    api = _api(tmp_path, monkeypatch)
    opened = []
    api.projects._opener = opened.append
    assert api.open_project("Нема") == {"ok": False, "error": "There is no project 'Нема' yet."}
    api.projects.write("Гра", "a.txt", "x")
    assert api.open_project("Гра") == {"ok": True} and opened


def test_the_window_draws_the_plan_box():
    js = Path(__file__).parents[1].joinpath("src/lanterna/ui/app.js").read_text(encoding="utf-8")
    for bit in ("function paintPlan(", "api.plan(tid)", "api.clear_plan(tid)", "api.open_project(view.project)",
                'aria-current="step"', "p.plan !== undefined", "loadPlan();"):
        assert bit in js, bit
    css = Path(__file__).parents[1].joinpath("src/lanterna/ui/style.css").read_text(encoding="utf-8")
    assert ".plan-box.working li.now .plan-mk" in css and ".plan-box.folded .plan-list { display: none; }" in css


def test_new_strings_are_translated_everywhere():
    from lanterna import i18n
    for s in ("Plan: {done} of {total} done", "Plan done: {n} of {n}", "Task plan", "Open the project folder",
              "Hide the plan", "Now: {step}", "Making a plan", "Writing {x}", "Fixing {x}", "Looking at the projects",
              "Checking the project for mistakes", "Opening the project"):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
    from lanterna.thinking import tool_step
    assert tool_step("project_write", json.dumps({"path": "index.html"}), "uk") == "Пишу index.html"


# ---------------------------------------------------------------- the terminal app
pytest.importorskip("textual")
from textual.widgets import Static  # noqa: E402

from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api as tui_api, chat_ready, wait_for  # noqa: E402,F401


def test_the_terminal_shows_the_plan_over_the_message_box(tui_api):  # noqa: F811
    tui_api.save_settings({"onboarded": True, "name": "Bo", "lang": "uk", "provider": "groq"})
    tid = tui_api.new_thread()["id"]
    tui_api.store.add(tid, "user", "зроби гру")
    tui_api.store.set_plan(tid, plans.dumps(plans.update({}, steps=["Правила", "Гра", "Перевірка"], done=[1],
                                                         project="Змійка")))

    async def go():
        app = LanternaApp(api=tui_api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            scr = app.screen
            scr.open_thread(tid)
            await pilot.pause()
            box = scr.query_one("#planbox")
            assert box.display
            text = str(scr.query_one("#plansteps", Static).render())
            assert "Правила" in text and "Гра" in text and "Перевірка" in text
            assert "1 з 3" in str(scr.query_one("#plantitle").render())
            await pilot.click("#planx")
            await pilot.pause()
            assert not box.display and tui_api.plan(tid) == {}
    asyncio.run(go())
