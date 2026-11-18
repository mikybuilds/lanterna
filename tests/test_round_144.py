"""Round 144 (1.1.10b6), from a real chat: "can you install me a C++ compiler, VS Code gives me an error".

What went wrong there, and what these tests hold:
- g++ came from winget's WinLibs in C:\\Users\\Олена\\…: "cannot find -lmingw32: Illegal byte sequence". The model
  guessed for an hour. pc_dev now looks: where g++, python, node and java are, what PATH runs first, and that GCC
  can't work from a folder with non-English letters (and what to do about it).
- Visual Studio was installed without C++ (only the editor), then a second card for it was made while the first
  one ran; the second failed with "…third-party packages." cut from its error. Now: Visual Studio comes with its
  parts (cpp brings the compiler), an installed one gets a card that adds C++, one card per program, the error is
  whole and in plain words, and after the install Lanterna looks whether the compiler is really there.
- The disk was almost full: pc_disk shows the profile's big folders (AppData), programs, Ollama models and
  Windows' own files; a card removes an Ollama model, another turns on Help free up disk space.
- In the middle of the installs Gemini 3 Flash hit its limit and Flash-Lite went on: now a strong model's short
  limit is waited out once, and a weaker model that makes changes on the computer is said in one line.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import apps, chat, devtools, diskuse, i18n, local
from lanterna.apps import Apps, explain
from lanterna.chat import Conversation
from lanterna.discovery import Candidate
from lanterna.providers import ProviderError
from lanterna.router import WEAK_TEXT, Router, Switched, Waiting, Weak
from lanterna.store import Store
from lanterna.tools import GROUPS, READ_ONLY_TOOLS, Tool
from lanterna.workspace import Actions, WorkError
from test_round_141 import _Router  # noqa: E402  (a pretend model that plays the given turns)

UI = Path(chat.__file__).parent / "ui"
VS = "Microsoft.VisualStudio.Community"
SHOW = ("Found Visual Studio Community 2026 [Microsoft.VisualStudio.Community]\nVersion: 18.0.1\n"
        "Publisher: Microsoft Corporation\nDescription: The IDE\n")
# the chat's own failed install: winget's code, then the installer's
FAIL_OUT = ("This application is licensed to you by its owner.\nMicrosoft is not responsible for, nor does it grant any "
            "licenses to, third-party packages.\nDownloading https://download.visualstudio.microsoft.com/download/pr/"
            "x/vs_Community.exe\nSuccessfully verified installer hash\nStarting package install...\n"
            "Installer failed with exit code: 1\n")
INST = {"installationPath": "C:\\Program Files\\Microsoft Visual Studio\\18\\Community",
        "displayName": "Visual Studio Community 2026", "productId": "Microsoft.VisualStudio.Product.Community",
        "installationVersion": "18.0.11205.157"}


class _Winget:
    """winget and vswhere as the chat had them; every command is noted."""

    def __init__(self, vs=None, cpp=False, code=0, out="Successfully installed"):
        self.vs, self.cpp, self.code, self.out, self.calls = vs, cpp, code, out, []

    def __call__(self, args, timeout=0):
        self.calls.append(list(args))
        if args[0] == "vswhere":
            found = [self.vs] if self.vs and (self.cpp or "-requires" not in args) else []
            return 0, json.dumps(found)
        if args[:2] == ["winget", "show"]:
            return 0, SHOW
        if args[:2] == ["winget", "list"]:
            return 0, "No installed package found matching input criteria."
        return self.code, self.out


def _apps(w, lang="uk"):
    return Apps(Actions(), runner=w, platform="win32", which=lambda n: "C:/winget.exe", lang=lambda: lang,
                vswhere="vswhere")


def _last(a):
    return list(a.actions.items.values())[-1]


# ---------------------------------------------------------------- 4. installing programs
def test_visual_studio_needs_its_parts():
    a = _apps(_Winget())
    with pytest.raises(WorkError, match="cpp for C\\+\\+"):
        a.propose("install", VS)
    assert not a.actions.items                                          # no card for an editor without a compiler


def test_visual_studio_comes_with_cpp_and_its_compiler():
    a = _apps(_Winget())
    out = a.propose("install", VS, parts=["c++"])
    card = _last(a)
    assert card.kind == "app_install" and card.details["parts"] == ["Desktop development with C++"]
    assert card.details["command"].endswith(
        '--override "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.NativeDesktop '
        '--includeRecommended"')                                       # the compiler is only "recommended"
    assert "--silent" not in card.details["command"] and "half an hour" in out


def test_one_card_per_program():
    a = _apps(_Winget())
    a.propose("install", VS, parts=["cpp"])
    with pytest.raises(WorkError, match="already waits for the user's Confirm"):
        a.propose("install", VS, parts=["cpp"])
    with pytest.raises(WorkError, match="already waits"):
        a.propose("install", "Microsoft.VisualStudio.2022.Community", parts=["cpp"])   # any Visual Studio
    _last(a).state = "running"
    with pytest.raises(WorkError, match="being installed or changed right now"):
        a.propose("install", VS, parts=["cpp"])
    assert len(a.actions.items) == 1


def test_the_error_is_whole_and_in_plain_words():
    a = _apps(_Winget(code=2316632070, out=FAIL_OUT))
    a.propose("install", VS, parts=["cpp"])
    c = a.actions.confirm(_last(a).id)
    assert c.state == "failed"
    assert c.result.startswith("Інсталятор Visual Studio зупинився з помилкою (код 1). Так часто буває, коли інше "
                               "встановлення Visual Studio ще йде")
    assert "(winget: 0x8A150006)" in c.result and c.result.endswith("Installer failed with exit code: 1")
    assert "third-party" not in c.result and "verified installer hash" not in c.result     # winget's boilerplate


def test_winget_codes_and_installer_codes_in_plain_words():
    assert explain(0x8A150102 - 2 ** 32, "", "winget", lang="uk").startswith("Зараз уже йде інше встановлення")
    assert explain(0x8A15010C, "", "winget").startswith("The installation was cancelled")
    assert explain(1, "x\nInstaller failed with exit code: 1618", "winget", vs=True).startswith(
        "Another installation is running right now")
    assert explain(5007, "", "Visual Studio Installer", vs=True).startswith("This computer doesn't meet")
    assert explain(124, "took too long", "winget").startswith("It took too long")
    long = "x" * 400
    assert long[:160] in explain(1, long, "winget")                    # a line is never cut to its last 300 chars


def test_an_installed_visual_studio_gets_cpp_added():
    w = _Winget(vs=INST)
    a = _apps(w)
    out = a.propose("install", VS, parts=["cpp"])
    card = _last(a)
    assert card.kind == "app_add" and "Visual Studio must be closed" in out
    assert card.details["command"] == ('setup.exe modify --installPath "C:\\Program Files\\Microsoft Visual Studio\\18'
                                       '\\Community" --add Microsoft.VisualStudio.Workload.NativeDesktop '
                                       '--includeRecommended --passive --norestart')
    assert card.details["notes"][0] == "Close Visual Studio before you confirm."
    w.cpp = True                                                          # the look afterwards finds the compiler
    done = a.actions.confirm(card.id)
    assert done.state == "done" and done.details["checked"] == apps.CHECKED_CPP
    from lanterna.app import action_title, card_text
    assert action_title("app_add", done.details, done.result, "uk", done=True) == (
        "Додано до Visual Studio Community 2026: Розробка на C++ (Desktop development with C++) · перевірено: "
        "компілятор C++ є")
    text = card_text("app_add", card.details, "uk")
    assert "Частини: Розробка на C++" in text and "Закрий Visual Studio, перш ніж підтвердити." in text


def test_nothing_to_add_when_cpp_is_there():
    a = _apps(_Winget(vs=INST, cpp=True))
    out = a.propose("install", VS, parts=["cpp"])
    assert "already has: Desktop development with C++. Nothing to install." in out and not a.actions.items


def test_after_the_install_lanterna_looks_for_the_compiler():
    w = _Winget()
    a = _apps(w)
    a.propose("install", VS, parts=["cpp"])
    w.vs = INST                                                          # installed, but without the compiler
    done = a.actions.confirm(_last(a).id)
    assert done.state == "done" and done.details["checked"] == apps.NO_CPP
    from lanterna.app import action_title
    assert action_title("app_install", done.details, done.result, "uk", done=True).endswith(
        " · але компілятора C++ немає")
    a2 = _apps(_Winget(code=3010))                                       # done, a restart finishes it
    a2.propose("install", VS, parts=["cpp"])
    assert a2.actions.confirm(_last(a2).id).details["checked"] == apps.RESTART


def test_a_done_install_counts_in_every_language():
    from lanterna.app import action_title
    for lang in i18n.LANGS:
        note = "✅ " + action_title("app_add", {"name": "Visual Studio", "parts": ["Desktop development with C++"]},
                                    "", lang, done=True)
        assert chat._set_done(note), lang


# ---------------------------------------------------------------- 5. the programming tools
def _exe(folder: Path, *names) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for n in names:
        (folder / n).write_bytes(b"MZ")
    return folder


def _run(args, timeout=0):
    name = os.path.basename(args[0]).lower()
    if name.startswith(("python", "py")) and "windowsapps" in args[0].lower():
        return 9009, "Python was not found; run without arguments to install from the Microsoft Store"
    return 0, {"g++.exe": "g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r2) 16.2.0",
               "node.exe": "v24.14.1"}.get(name, f"{name} 1.0")


@pytest.fixture
def base(tmp_path, monkeypatch):
    """The test's folder with its real name (Windows gives TEMP a short 8.3 name). That folder itself may have
    non-English letters (the user's name is in it on some computers): only what a test adds after it counts."""
    b = Path(os.path.realpath(tmp_path))
    monkeypatch.setattr(devtools, "_latin", lambda p: p.replace(str(b), "", 1).isascii())
    return b


def _check(base, dirs, only="", vs=lambda r: [], places=None, **env):
    e = {"PATH": ";".join(str(d) for d in dirs), "PATHEXT": ".EXE;.CMD", "TEMP": str(base / "Temp"), **env}
    return devtools.check(only, env=e, run=_run, platform="win32", vs=vs, home=str(base / "home"),
                          places=places or {})


def test_gcc_in_a_folder_with_cyrillic_and_the_fix(base):
    """The chat's computer: WinLibs from winget under C:\\Users\\Олена, and C:\\mingw64 that came after it."""
    bad = _exe(base / "Users" / "Олена" / "WinGet" / "Packages" / "WinLibs" / "mingw64" / "bin", "g++.exe",
               "gcc.exe", "gdb.exe")
    good = _exe(base / "mingw64" / "bin", "g++.exe", "gcc.exe")
    out = _check(base, [bad, good], only="c++", TEMP=str(base / "Users" / "Олена" / "Temp"))
    assert f"g++ → {bad / 'g++.exe'} — g++.exe (MinGW-W64" in out
    assert f"(PATH also has it in {good}: the first one is used)" in out
    assert f"The GCC that runs is in a folder whose path has non-English letters: {bad}." in out
    assert "'Illegal byte sequence' or 'cannot find -lmingw32'" in out
    assert f"Fix: in Path (the user variables), move {good} above that folder, or remove that folder from Path" in out
    assert "The folder for temporary files" in out and "set the user variables TEMP and TMP to C:\\Temp" in out
    assert "nothing changed" in out and "The user folder" not in out


def test_only_gcc_with_cyrillic_copy_it_to_mingw64(base, monkeypatch):
    monkeypatch.setattr(devtools, "SAFE_MINGW", str(base / "nothing here"))
    bad = _exe(base / "Олена" / "mingw64" / "bin", "g++.exe")
    out = _check(base, [bad], only="g++")
    assert f"copy the whole folder {bad.parent} to {base / 'nothing here'}" in out
    assert "The folder for temporary files" not in out
    _exe(base / "nothing here" / "bin", "g++.exe")                      # C:\mingw64 is there already
    assert f"{base / 'nothing here' / 'bin'}\\g++.exe is already there" in _check(base, [bad], only="g++")
    out = devtools.check("g++", env={"PATH": str(bad), "PATHEXT": ".EXE"}, run=_run, platform="win32",
                         home=str(base / "Олена"), places={})
    assert "The user folder" in out and "like D:\\code" in out


def test_python_store_shortcut_and_programs_not_in_path(base):
    store = _exe(base / "Microsoft" / "WindowsApps", "python.exe", "python3.exe")
    node = _exe(base / "nodejs", "node.exe")
    java = _exe(base / "jdk-21" / "bin", "java.exe", "javac.exe")
    out = _check(base, [store, base / "jdk-21"], places={"node": (str(node),)})
    assert f"python → {store / 'python.exe'}: only the Microsoft Store shortcut, not the program itself" in out
    assert f"node (Node.js, JavaScript): installed in {node}, but a terminal doesn't find it (not in Path): add " \
           f"{node} to Path" in out
    assert f"installed in {java}, but Path has {base / 'jdk-21'} (the folder above): put {java} in Path" in out
    assert "- not found: g++, gcc, gdb, clang++, dotnet, git, code" in out


def test_path_mistakes(base):
    f = base / "mingw64" / "bin" / "g++.exe"
    _exe(f.parent, "g++.exe")
    out = _check(base, [f, base / "gone" / "bin"])
    assert f"Path has a file instead of a folder: {f}" in out
    assert f"Path has folders that don't exist (harmless, unless one is a typo for a program above): {f}" not in out
    assert str(base / "gone" / "bin") in out


def test_the_cpp_compiler_of_visual_studio(base):
    with_cpp = _check(base, [], only="c++", vs=lambda requires: [{"name": "Visual Studio Community 2026"}])
    assert "MSVC (cl.exe, the C++ compiler of Visual Studio): in Visual Studio Community 2026" in with_cpp
    assert "'Developer PowerShell for VS'" in with_cpp
    without = _check(base, [], only="c++", vs=lambda requires: [] if requires else
                     [{"name": "Visual Studio Community 2026", "edition": "Community", "major": 18}])
    assert "installed without C++. app_install Microsoft.VisualStudio.Community with parts ['cpp'] adds it" in without
    old = _check(base, [], only="msvc", vs=lambda requires: [] if requires else
                 [{"name": "Visual Studio Community 2022", "edition": "Community", "major": 17}])
    assert "app_install Microsoft.VisualStudio.2022.Community with parts" in old


def test_linux_is_a_plain_list(base):
    b = _exe(base / "usr" / "bin", "g++", "python3")
    out = devtools.check("", env={"PATH": str(b)}, run=lambda a, timeout=0: (0, "1.0"), platform="linux",
                         home="/home/міша")
    assert f"g++ → {b / 'g++'} — 1.0" in out and f"python3 → {b / 'python3'}" in out
    assert "non-English" not in out and "Windows" not in out and "VS Code and every terminal" not in out


def test_pc_dev_is_offered_for_the_chats_words_and_only_looks():
    for said in ("можеш мені поставити компілятор для с++ бо visual studio code дає мені помилку",
                 "C:/Users/?: cannot find -lmingw32: Illegal byte sequence", "g++ не працює", "python не знаходить"):
        assert GROUPS["dev"].search(said), said
    assert "pc_dev" in READ_ONLY_TOOLS and "pc_disk" in READ_ONLY_TOOLS
    tool = devtools.dev_tools(lambda r: [])[0]
    tool.group = "apps dev"
    assert "intent" in tool.schema()["function"]["parameters"]["properties"]   # the user sees why it looks
    assert "pc_dev" in chat.PC_GUIDE and "One card per program" in chat.PC_GUIDE


# ---------------------------------------------------------------- 6. what takes up the disk
def _file(p: Path, n: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)


def test_the_profile_with_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr(diskuse, "MB", 1)                               # sizes in bytes: small files are "big"
    home = tmp_path / "Олена"
    _file(home / "AppData" / "Local" / "Docker" / "disk.vhdx", 5000)
    _file(home / "AppData" / "Local" / "Temp" / "a.tmp", 900)
    _file(home / "AppData" / "Roaming" / "Code" / "Cache" / "c", 700)
    _file(home / "AppData" / "LocalLow" / "Game" / "save", 300)
    _file(home / "Documents" / "big.mp4", 2000)
    _file(home / ".ollama" / "models" / "blob", 4000)
    out = diskuse.report("profile", home=home, platform="win32")
    lines = out.splitlines()
    assert lines[0] == "What takes up the disk (only looked, nothing changed):"
    assert f"Biggest folders of the profile {home}:" in out
    assert lines.index("- AppData — 6.7 KB") < lines.index("- .ollama — 3.9 KB (Ollama models (see below))")
    assert "- Documents — 2.0 KB" in out
    i = lines.index("Biggest inside AppData\\Local, AppData\\Roaming:" if os.sep == "\\" else
                    "Biggest inside AppData/Local, AppData/Roaming:")
    deep = lines[i + 1:]
    assert deep[0].startswith(f"- {Path('AppData', 'Local', 'Docker')} — 4.9 KB (Docker's images")
    assert any(x.startswith(f"- {Path('AppData', 'Local', 'Temp')} — 900 B (temporary files: Disk Cleanup") for x in deep)
    assert any(x.startswith(f"- {Path('AppData', 'LocalLow')} — 300 B") for x in deep)   # counted whole


def test_the_time_is_short_and_says_at_least(tmp_path, monkeypatch):
    monkeypatch.setattr(diskuse, "MB", 1)
    home = tmp_path / "h"
    _file(home / "Videos" / "a.mp4", 500)
    clock = iter([0.0, 0.0, 999.0, 999.0, 999.0, 999.0])
    c = diskuse.Counter(1.0, now=lambda: next(clock, 999.0))
    n, whole = c.size(str(home))
    assert not whole and c.cut                                          # it stopped: the size is "at least"
    assert diskuse._sized(n, whole).startswith("at least")


def test_programs_models_and_the_offer_to_turn_on_help(tmp_path, monkeypatch):
    monkeypatch.setattr(diskuse, "MB", 1)
    models = [local.LocalModel("gemma3:4b", 3.3), local.LocalModel("qwen3:8b", 5.2)]
    out = diskuse.report("models", home=tmp_path, platform="win32", installed=lambda: models, running=lambda: "0.9",
                         space_help=False)
    assert "Ollama models (pc_model_remove removes one, with a card" in out
    assert out.index("- qwen3:8b — 5.2 GB") < out.index("- gemma3:4b — 3.3 GB")
    assert "pc_space_on offers to turn it on (a card)" in out
    progs = diskuse.report("programs", home=tmp_path, platform="win32",
                           programs=lambda: [(13 * 2 ** 30, "Visual Studio Community 2026")])
    assert "- Visual Studio Community 2026 — 13.0 GB" in progs and "app_uninstall removes one" in progs
    assert "pc_space_on" not in progs                                   # it is on (the default here)


def _api(tmp_path, monkeypatch):
    from lanterna import keys
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.ai_titles = api.settings.follow_ups = api.settings.auto_memory = False
    api.settings.compact_chats, api.settings.pc_access, api.settings.lang = False, True, "uk"
    return api


def test_removing_an_ollama_model_is_a_card(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    gone = []
    monkeypatch.setattr(local, "installed", lambda: [local.LocalModel("gemma3:latest", 3.3)])
    monkeypatch.setattr(local, "remove", lambda name: gone.append(name) or "")
    api.settings.local_models["chat"] = "gemma3:latest"
    assert "pc_model_remove" in {t.name for t in api._disk_tools()}
    out = api._model_remove("gemma3")
    assert out.startswith("Prepared. Nothing has been changed yet") and not gone
    card = list(api.actions.items.values())[-1]
    assert card.kind == "model_remove" and card.details == {"name": "gemma3:latest", "size": "3.3 GB"}
    with pytest.raises(WorkError, match="already waits"):
        api._model_remove("gemma3:latest")
    with pytest.raises(WorkError, match="It has: gemma3:latest"):
        api._model_remove("llama3")
    done = api.actions.confirm(card.id)
    assert done.state == "done" and gone == ["gemma3:latest"] and "chat" not in api.settings.local_models
    from lanterna.app import action_title, card_text
    assert action_title("model_remove", card.details, "", "uk") == "Прибрати модель gemma3:latest з Ollama"
    assert card_text("model_remove", card.details, "uk").startswith("Звільнить 3.3 GB.")


def test_help_free_up_space_is_offered_on_a_card(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api.settings.space_help = False
    assert "pc_space_on" in {t.name for t in api._disk_tools()}
    api._space_on()
    card = list(api.actions.items.values())[-1]
    assert card.kind == "space_on" and not api.settings.space_help        # nothing changes before Confirm
    api.actions.confirm(card.id)
    assert api.settings.space_help and "pc_space_on" not in {t.name for t in api._disk_tools()}
    from lanterna.app import action_title
    assert action_title("space_on", {}, "", "uk", done=True) == "«Допомога зі звільненням місця» увімкнена"


def test_the_new_tools_are_on_the_computer_list(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tools = {t.name: t for t in api._pc_tools()}
    assert {"pc_dev", "pc_disk", "pc_model_remove"} <= set(tools)
    assert tools["pc_dev"].group == "apps dev" and tools["pc_disk"].group == "pc"
    from lanterna.pccontrol import WIN_BUILTIN
    assert WIN_BUILTIN["disk cleanup"] == "cleanmgr.exe"                # pc_open_program opens Disk Cleanup
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'k === "model_remove" || k === "game_remove" ? "trash"' in js and 'c.kind === "space_on"' in js


# ---------------------------------------------------------------- 7. a weaker model in the middle of the work
class _Client:
    def __init__(self, plan):
        self.plan, self.calls = plan, []

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        self.calls.append(model)
        todo = self.plan[model]
        step = todo.pop(0) if len(todo) > 1 else todo[0]
        if isinstance(step, ProviderError):
            raise step
        yield step


def _flash(plan):
    c, slept = _Client(plan), []
    r = Router([Candidate("gemini", "gemini-3-flash-preview", 86), Candidate("gemini", "gemini-3.1-flash-lite", 72)],
               client_for=lambda pid: c, sleep=slept.append)
    return r, c, slept


def _rate(s):
    return ProviderError("rate", "Please retry in a few seconds", 429, retry_after=s)


def _kinds(out):
    return [p if isinstance(p, str) else type(p).__name__ for p in out]


def test_a_strong_models_short_limit_is_waited_out_for_changes():
    r, c, slept = _flash({"gemini-3-flash-preview": [_rate(8), "strong"], "gemini-3.1-flash-lite": ["weak"]})
    out = list(r.stream([], tools=[{}], careful=True))
    assert _kinds(out) == ["Waiting", "strong"] and out[0].seconds == 8 and slept == [8.5]
    assert c.calls == ["gemini-3-flash-preview"] * 2


def test_a_plain_answer_does_not_wait():
    r, c, slept = _flash({"gemini-3-flash-preview": [_rate(8), "strong"], "gemini-3.1-flash-lite": ["weak"]})
    assert _kinds(r.stream([], tools=[{}])) == ["Switched", "weak"] and not slept


def test_a_weaker_model_that_goes_on_is_said():
    r, c, slept = _flash({"gemini-3-flash-preview": [_rate(50)], "gemini-3.1-flash-lite": ["weak"]})
    out = list(r.stream([], tools=[{}], careful=True))
    assert _kinds(out) == ["Switched", "Weak", "weak"] and out[1].to.model == "gemini-3.1-flash-lite" and not slept
    r, c, slept = _flash({"gemini-3-flash-preview": [_rate(5), _rate(5)], "gemini-3.1-flash-lite": ["weak"]})
    assert _kinds(r.stream([], tools=[{}], careful=True)) == ["Waiting", "Switched", "Weak", "weak"]   # once only
    assert r.weak(r.candidates[1]) and not r.weak(r.candidates[0])


def test_close_models_are_not_weak():
    r = Router([Candidate("gemini", "a", 92), Candidate("groq", "b", 85), Candidate("ollama", "c", 60)])
    assert not r.weak(r.candidates[1]) and r.weak(r.candidates[2])
    alone = Router([Candidate("ollama", "small", 50)])
    assert not alone.weak(alone.candidates[0])                          # nothing better here: no warning


def _box(*names):
    box = SimpleNamespace(store=SimpleNamespace(facts=lambda: []), focus="", page_limit=6000, runs=[],
                          tools={n: SimpleNamespace(label="🛠") for n in names})
    box.schemas = lambda ctx=None: [{"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
                                    for n in names]
    box.run = lambda name, args: box.runs.append(name) or f"ran {name}"
    return box


def test_changes_on_the_computer_are_careful():
    names = ["app_search", "app_install", "pc_open_program"]
    assert chat.careful_turn(names, "встанови мені visual studio для c++", False, [])
    assert not chat.careful_turn(names, "що таке visual studio?", False, [])
    assert chat.careful_turn(names, "ок", True, [])                         # a card waits
    assert chat.careful_turn(names, "далі", False, [{"role": "assistant", "content": "✅ Встановлено VS", "note": True}])
    assert not chat.careful_turn(["app_search", "pc_open_program"], "встанови", False, [])   # nothing that changes
    r = _Router([[("app_install", {"id": VS, "parts": ["cpp"]})], "Картка нижче: натисни «Підтвердити»."])
    conv = Conversation(r, toolbox=_box("app_search", "app_install"), lang="uk")
    list(conv.ask("що таке visual studio?"))
    assert r.seen[0]["kw"]["careful"] is False and r.seen[1]["kw"]["careful"] is True   # it acted: careful now


class _WeakRouter:
    candidates: list = []

    def __init__(self, wait=False):
        self.c = Candidate("gemini", "gemini-3.1-flash-lite", 72)
        self.current, self.wait = self.c, wait

    def lacks_tools(self):
        return False

    def quick_order(self):
        return []

    def stream(self, msgs, **kw):
        if self.wait:
            yield Waiting(Candidate("gemini", "gemini-3-flash-preview", 86), 8.2)
        yield Switched(self.c, "rate")
        yield Weak(self.c)
        yield "Ось що я бачу на комп'ютері."


def _answer(api, tid, router):
    from lanterna.app import _Stream
    sid = os.urandom(4).hex()
    api._streams[sid] = _Stream("uk")
    api._run(sid, tid, "встанови visual studio", [], router=router)
    return api.poll(sid)


def test_the_weak_line_comes_once_per_chat(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tid = api.new_thread()["id"]
    p = _answer(api, tid, _WeakRouter(wait=True))
    assert not p["error"] and p["weak"] == "Google Gemini · gemini-3.1-flash-lite"
    assert any(s["text"].startswith("Чекаю 8 с на Google Gemini · gemini-3-flash-preview: її безкоштовний ліміт")
               for s in p["steps"])
    assert _answer(api, tid, _WeakRouter())["weak"] == ""                 # said once in this chat
    assert _answer(api, api.new_thread()["id"], _WeakRouter())["weak"]   # a new chat hears it again
    assert i18n.t(WEAK_TEXT, "uk", m="Flash-Lite").startswith("Flash-Lite — слабша модель: у змінах на комп'ютері")


def test_the_window_and_the_terminal_show_the_line():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'if (p.weak && p.weak !== weak && bot.isConnected)' in js and 'class="weak-model"' in js
    assert WEAK_TEXT in js
    tui = (Path(chat.__file__).parent / "tui.py").read_text(encoding="utf-8")
    assert 't(WEAK_TEXT, lang, m=r["weak"])' in tui


def test_every_new_string_is_translated():
    new = [*(p[0] for p in apps.VS_PARTS.values()), apps.CHECKED, apps.CHECKED_CPP, apps.NO_CPP, apps.UNLISTED,
           apps.RESTART, apps.OPEN_NOW, apps.MISSING, apps.CANCELLED, apps.ADMIN, apps.BUSY, apps.OFFLINE,
           *apps.WINGET_SAYS.values(), *apps.VS_SAYS.values(), apps.VS_FAILED, apps.INSTALLER_FAILED, apps.TOO_LONG,
           apps.NO_PASSWORD, apps.FAILED, "Close Visual Studio before you confirm.",
           "It takes a while: Visual Studio shows its progress.", "Parts: {p}", "Add {to} to {name}",
           "Added {to} to {name}", "Remove the model {name} from Ollama", "Removed the model {name} from Ollama",
           "Turn on Help free up disk space", "Help free up disk space is on",
           "Frees {s}. It can be downloaded again later in Settings → Local models.",
           "Checking the programming tools", "Looking at what takes up the disk", "Preparing to remove the model {x}",
           "Preparing to turn on Help free up disk space",
           "Waiting {n} s for {m}: its free limit for this minute is used up", WEAK_TEXT]
    for s in new:
        assert set(i18n._T.get(s, {})) >= {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
    assert isinstance(Tool, type)
