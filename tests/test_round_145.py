"""Round 145 (1.1.10b7), from a real chat: "sort what we agreed on" — and nothing happened, twice.

Gemini Flash-Lite called pc_move three times, every call failed, and it answered "I'll sort your downloads now,
let's confirm the move!" with no card. Asked again, it failed the same way, then wrote "Використовую `pc_folders`…"
without calling it, and a line of its own in Lanterna's form: "[Lanterna: 🔍 Шукаю шлях до папки Завантаження...]".
- pc_move understood the folder only by its key: "Завантаження", path="Downloads", "Downloads/*.jar" or a whole
  C:\\Users\\…\\Downloads\\x path failed, and a pattern with a folder ("Mods/*.jar") failed as a "hidden" folder.
  to="Downloads/видалення/…" would even have made a second Downloads inside Downloads. Now they all mean the same.
- A failed call is no change: words that lean on it ("I'll sort them now", "let's confirm") are withdrawn once and
  the model hears the error, to fix the call or say it didn't work.
- A promise of work after the reply ("одразу запущу сортування"), a tool it says it uses but didn't call, and a
  [Lanterna: …] line it wrote itself count as claims; such lines never stay in the reply.
"""
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import chat, i18n, pcfiles
from lanterna.chat import Conversation, Redo
from lanterna.workspace import WAITING, Actions, WorkError
from test_round_141 import _Router  # noqa: E402  (a pretend model that plays the given turns)

OLD = time.time() - 400 * 86400
TO = "видалення/Моди для Minecraft"


def _downloads(tmp_path):
    """The chat's Downloads: the folders made the day before, and files from long ago."""
    root = tmp_path / "Downloads"
    for sub in ("видалення/Архіви та інсталятори", "видалення/старі файли", TO):
        (root / sub).mkdir(parents=True)
    for name in ("fabric-api-0.92.jar", "sodium-0.5.jar", "OllamaSetup.exe", "Windows.iso", "notes.txt"):
        (root / name).write_bytes(b"x" * 10)
        os.utime(root / name, (OLD, OLD))
    (tmp_path / "Documents").mkdir()
    pl = pcfiles.Places(Actions(), folders=lambda: {"downloads": root, "documents": tmp_path / "Documents"})
    return pl, root


def _move(pl, **args):
    tool = next(t for t in pcfiles.place_tools(pl) if t.name == "pc_move")
    out = tool.run(**args)
    return out, list(pl.actions.items.values())[-1].details


# ---------------------------------------------------------------- the folder by any of its names
@pytest.mark.parametrize("args", [
    {"place": "Завантаження", "ext": [".jar"], "to": TO},                         # its name in Ukrainian
    {"place": "Downloads", "ext": [".jar"], "to": TO, "to_place": "Download"},     # its own name, Italian
    {"place": "downloads", "path": "Downloads", "ext": [".jar"], "to": TO},       # the folder named once more
    {"place": "downloads", "paths": ["Downloads/*.jar"], "to": "Downloads/" + TO},
    {"place": "downloads", "paths": ["*.jar"], "to": "Завантаження/" + TO},
    {"place": "downloads", "paths": ["Downloads/sodium-0.5.jar", "fabric-api-0.92.jar"], "to": TO},
    {"place": "downloads", "paths": ["{root}\\*.jar"], "to": "{root}\\" + TO.replace("/", "\\")},   # whole paths
    {"place": "{root}", "paths": ["./*.jar"], "to": "./" + TO},
])
def test_the_chats_arguments_make_the_right_card(tmp_path, args):
    pl, root = _downloads(tmp_path)
    args = {k: json.loads(json.dumps(v).replace("{root}", str(root).replace("\\", "\\\\"))) for k, v in args.items()}
    out, d = _move(pl, **args)
    assert out.startswith(WAITING)
    assert (d["place"], d["to_place"], d["to"]) == ("downloads", "downloads", TO)   # never Downloads/Downloads/…
    assert sorted(d["files"]) == ["fabric-api-0.92.jar", "sodium-0.5.jar"]
    assert not (root / "Downloads").exists()


def test_the_other_groups_of_the_chat(tmp_path):
    pl, root = _downloads(tmp_path)
    _, d = _move(pl, place="Завантаження", kinds=["Installers", "Archives"], to="Downloads/видалення/Архіви та інсталятори")
    assert d["to"] == "видалення/Архіви та інсталятори" and d["files"] == ["OllamaSetup.exe", "Windows.iso"]
    _, d = _move(pl, place="downloads", path=str(root), older_than_days=180, to="видалення/старі файли")
    assert d["files"] == ["fabric-api-0.92.jar", "notes.txt", "sodium-0.5.jar"]   # the others wait on a card already


def test_a_real_folder_with_that_name_stays(tmp_path):
    pl, root = _downloads(tmp_path)
    (root / "Downloads").mkdir()
    (root / "Downloads" / "old.jar").write_bytes(b"x")
    os.utime(root / "Downloads" / "old.jar", (OLD, OLD))
    _, d = _move(pl, place="downloads", paths=["Downloads/*.jar"], to=TO)
    assert d["files"] == ["Downloads/old.jar"]                          # the folder that is there is the one meant


def test_a_pattern_in_a_subfolder(tmp_path):
    """"Mods/*.jar" was "./Mods": a folder whose name starts with a dot, so it was refused as hidden."""
    pl, root = _downloads(tmp_path)
    (root / "Mods").mkdir()
    (root / "Mods" / "a.jar").write_bytes(b"x")
    os.utime(root / "Mods" / "a.jar", (OLD, OLD))
    _, d = _move(pl, place="downloads", paths=["Mods/*.jar"], to=TO)
    assert d["files"] == ["Mods/a.jar"]
    with pytest.raises(WorkError, match="Hidden files"):
        pl.path("downloads", ".git/config")


def test_errors_say_what_place_and_path_mean(tmp_path):
    pl, root = _downloads(tmp_path)
    with pytest.raises(WorkError, match=r"Unknown folder 'Робота'\. place is one of: downloads \(.+Downloads\), docum"):
        _move(pl, place="Робота", ext=[".jar"], to=TO)
    with pytest.raises(WorkError, match="There is no folder 'Ігри' in downloads. path is a folder inside downloads"):
        _move(pl, place="downloads", path="Ігри", ext=[".jar"], to=TO)
    with pytest.raises(WorkError, match="There is no 'game.jar' in downloads: names in paths are inside downloads"):
        _move(pl, place="downloads", paths=["game.jar"], to=TO)
    with pytest.raises(WorkError, match="is outside the downloads folder"):
        _move(pl, place="downloads", paths=[str(tmp_path / "Documents")], to=TO)
    place = next(t for t in pcfiles.place_tools(pl) if t.name == "pc_move").parameters["properties"]["place"]
    assert "without its name in front" in place["description"]


# ---------------------------------------------------------------- a failed call is no change
class _Box:
    """pc_move fails the way it did in the chat until the model fixes its call."""

    def __init__(self, fails=3):
        self.runs, self.fails = [], fails
        self.store = SimpleNamespace(facts=lambda: [])
        self.tools = {n: SimpleNamespace(label="🛠") for n in ("pc_folders", "pc_list", "pc_move", "pc_sort")}
        self.focus, self.page_limit = "", 6000

    def schemas(self, ctx=None):
        return [{"type": "function", "function": {"name": n, "description": "", "parameters": {}}} for n in self.tools]

    def run(self, name, args):
        self.runs.append((name, json.loads(args)))
        if name == "pc_move" and self.fails:
            self.fails -= 1
            return "Error: WorkError: 'Downloads' is not a folder."
        return WAITING if name == "pc_move" else f"ran {name}"


THREE = [("pc_move", {"place": "downloads", "path": "Downloads", "ext": [".jar"], "to": TO}),
         ("pc_move", {"place": "downloads", "path": "Downloads", "kinds": ["Installers"], "to": "видалення/Архіви"}),
         ("pc_move", {"place": "downloads", "path": "Downloads", "older_than_days": 180, "to": "видалення/старі файли"})]
SAID = ("Ой, друже, вибач — я знову трохи перемудрив з командами для системи. Я зараз відсортую твої завантаження, щоб "
        "все розлетілося по потрібних папках. Давай підтвердимо переміщення!")


def test_failed_calls_are_no_change_and_the_model_hears_the_error():
    fixed = [("pc_move", {"place": "downloads", "ext": [".jar"], "to": TO})]
    r, box = _Router([THREE, SAID, fixed, "Картка нижче: натисни «Підтвердити», і моди переїдуть у видалення."]), _Box()
    conv = Conversation(router=r, toolbox=box, lang="uk")
    out = list(conv.ask("посортуй те, про що ми домовлялись, і скажи, коли буде готово"))
    assert any(isinstance(p, Redo) for p in out)
    note = r.seen[2]["msgs"][-1]["content"]
    assert note.startswith("[Lanterna's check") and "your pc_move call failed" in note
    assert "The error: 'Downloads' is not a folder. Fix what it says and call pc_move again" in note
    assert [n for n, _ in box.runs] == ["pc_move"] * 4 and box.runs[-1][1] == fixed[0][1]
    assert conv.last_reply.startswith("Картка нижче") and "⚠️" not in conv.last_reply


def test_a_promise_and_its_own_lanterna_line_are_withdrawn():
    stuck = ("Ой, друже, вибач — я знову наплутав зі шляхами! Використовую `pc_folders`, щоб знайти правильний шлях. "
             "Після цього я одразу запущу сортування — я вже готовий, не вимикайся!\n\n"
             "[Lanterna: 🔍 Шукаю шлях до папки Завантаження...]")
    still = "Не вийшло: система не бачить папку.\n\n[Lanterna: ✅ Переміщено 3 файли]"
    r, box = _Router([THREE[:1], stuck, still]), _Box()
    conv = Conversation(router=r, toolbox=box, lang="uk")
    out = list(conv.ask("Я підтверджую, починай сортувати."))
    assert r.seen[0]["kw"]["tool_choice"] == "required"                  # "починай сортувати" asks for a tool
    assert any(isinstance(p, Redo) and p.said.startswith("Використовую `pc_folders") for p in out)
    assert "[Lanterna:" not in r.seen[2]["msgs"][-2]["content"]           # its own line isn't sent back to it
    reply = conv.last_reply
    assert "[Lanterna" not in reply and reply.startswith("Не вийшло: система не бачить папку.")
    assert reply.endswith("⚠️ " + i18n.t(chat.FAILED_RAN, "uk"))
    assert conv.history[-1]["content"] == reply


def test_what_counts_as_a_claim():
    claim = chat.claim_phrase
    assert claim("Використовую `pc_folders`, щоб знайти шлях.", []) == "Використовую `pc_folders"
    assert not claim("Використовую `pc_folders`, щоб знайти шлях.", ["pc_folders"])   # it did call it
    assert not claim("Я використовую snake_case для назв змінних.", [])
    assert claim("Після цього я одразу запущу сортування.", []) == "одразу запущу"
    assert not claim("Після цього я одразу запущу сортування.", ["pc_move"])
    assert claim("Давай підтвердимо переміщення!", []) == "Давай підтвердимо"
    assert claim("[Lanterna: 🔍 Шукаю шлях до папки Завантаження...]", []).startswith("[Lanterna")
    assert chat.must_use_tool("Я підтверджую, починай сортувати.") and not chat.must_use_tool("починай пояснювати")
    assert chat.strip_fake_notes("Добре.\n[Lanterna: ✅ Готово]\nДалі.") == "Добре.\nДалі."
    assert chat.strip_fake_notes("Ось [Lanterna: 🔍 шукаю] так.") == "Ось  так."
    assert chat.short_error("Error: WorkError: 'x' is not a folder.") == "'x' is not a folder."


def test_the_new_warning_is_translated():
    for lang in i18n.LANGS:
        assert i18n.t(chat.FAILED_RAN, lang), lang
    assert set(i18n._T[chat.FAILED_RAN]) >= {"uk", "it"}
    for lang in i18n.FILE_LANGS:
        assert i18n.catalog(lang).get(chat.FAILED_RAN), lang
