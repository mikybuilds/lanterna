"""Round 143 (1.1.10b5), from a real chat: "sort my downloads into my folders, step by step".

The model made two folder cards, then wrote "починаю переміщення…", "✅ Виконано переміщення" and "Я перемістив
усе", and sent the user to press Confirm on cards that were never made: no file moved.
- A card's line (✅ / ✖ / ⚠️) goes to the model as Lanterna's note on the user's side, not as its own answer (shown
  as "a second opinion" it was copied); the rules say that only Lanterna writes these lines.
- A reply that says it moved, installed or made a card while no tool of it did is withdrawn once: the model gets
  Lanterna's check and calls the tool, or says it can't. Still saying it → the ⚠️ line, and no more requests.
- pc_move takes a rule: kinds, endings, age, words in the name, patterns like *.exe. One card lists the files; ones
  still downloading or already on a waiting card are left out; the card says which files it takes.
- A job in steps on this computer gets the task plan and its 12 tool rounds too.
"""
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import chat, i18n, pcfiles, plans
from lanterna.chat import Conversation, Redo
from lanterna.store import Store
from lanterna.tools import Tool, Toolbox
from lanterna.workspace import Actions, WorkError
from test_round_141 import _Router  # noqa: E402  (a pretend model that plays the given turns)

UI = Path(chat.__file__).parent / "ui"


class _Box:
    """Tools by name; every run is noted."""

    def __init__(self, *names):
        self.runs, self.args = [], []
        self.store = SimpleNamespace(facts=lambda: [])
        self.tools = {n: SimpleNamespace(label="🛠") for n in names}
        self.focus, self.page_limit = "", 6000

    def schemas(self, ctx=None):
        return [{"type": "function", "function": {"name": n, "description": "", "parameters": {}}} for n in self.tools]

    def run(self, name, args):
        self.runs.append(name)
        self.args.append(json.loads(args or "{}"))
        return f"ran {name}"


PC = ("pc_list", "pc_overview", "pc_make_folder", "pc_move", "pc_sort", "remember")
MOVE = ("pc_move", {"place": "downloads", "to": "Програми", "kinds": ["Installers"]})


def _ask(conv, text):
    out = list(conv.ask(text))
    return out, "".join(p for p in out if isinstance(p, str))


# ---------------------------------------------------------------- a card's line is Lanterna's, not the model's
def test_a_cards_line_goes_to_the_model_as_lanterna_note():
    history = [{"role": "user", "content": "створи папки Програми і Документи"},
               {"role": "assistant", "content": "Готую дві картки."},
               {"role": "assistant", "content": "✅ Створено папку Downloads/Програми", "note": True},
               {"role": "assistant", "content": "✅ Створено папку Downloads/Документи", "note": True}]
    r = _Router(["ок"])
    _ask(Conversation(router=r, toolbox=_Box(*PC), history=history), "а тепер перенеси файли")
    msgs = r.seen[0]["msgs"][1:]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]           # never two answers in a row
    assert msgs[1]["content"] == "Готую дві картки." and chat.SECOND_NOTE not in json.dumps(msgs, ensure_ascii=False)
    assert msgs[2]["content"] == ("[Lanterna: ✅ Створено папку Downloads/Програми]\n\n"
                                  "[Lanterna: ✅ Створено папку Downloads/Документи]\n\nа тепер перенеси файли")
    assert all("note" not in m for m in msgs)                                    # nothing extra goes to the service
    assert "only Lanterna writes them" in r.seen[0]["msgs"][0]["content"]


def test_a_note_right_after_a_question_and_a_second_opinion_still_work():
    out = chat.join_answers([{"role": "user", "content": "питання"},
                             {"role": "assistant", "content": "✖ Скасовано: перемістити 3 файли", "note": True},
                             {"role": "assistant", "content": "Відповідь"}, {"role": "assistant", "content": "Друга"}])
    assert out == [{"role": "user", "content": "питання\n\n[Lanterna: ✖ Скасовано: перемістити 3 файли]"},
                   {"role": "assistant", "content": f"Відповідь\n\n{chat.SECOND_NOTE}\nДруга"}]


def test_only_lines_without_a_model_are_card_notes(tmp_path):
    from lanterna.app import _history
    store = Store(tmp_path / "t.db")
    tid = store.new_thread()
    store.add(tid, "user", "перенеси")
    store.add(tid, "assistant", "✅ Виконано переміщення", "groq · llama")      # the model wrote it: not a note
    store.add(tid, "assistant", "✅ Moved 3 items to Downloads/Програми", "")     # Lanterna wrote it
    h = _history(store.messages(tid))
    assert [bool(m.get("note")) for m in h] == [False, False, True]
    assert set(h[0]) == {"role", "content"}


# ---------------------------------------------------------------- saying it moved, but no tool did
def test_said_it_moved_everything_but_nothing_ran_is_asked_again():
    r, box = _Router(["Я перемістив усе з Завантажень у твої папки.", [MOVE],
                      "Картка готова: натисни «Підтвердити», і інсталятори переїдуть у Програми."]), _Box(*PC)
    conv = Conversation(router=r, toolbox=box, lang="uk")
    out, _ = _ask(conv, "перенеси файли із завантажень у мої папки")
    redo = [p for p in out if isinstance(p, Redo)]
    assert len(redo) == 1 and "перемістив усе з Завантаж" in redo[0].said
    assert box.runs == ["pc_move"] and len(r.seen) == 3
    check = r.seen[1]["msgs"][-1]
    assert check["role"] == "user" and "Lanterna's check" in check["content"] and redo[0].said in check["content"]
    assert r.seen[1]["msgs"][-2] == {"role": "assistant", "content": "Я перемістив усе з Завантажень у твої папки."}
    assert conv.last_reply.startswith("Картка готова") and "⚠️" not in conv.last_reply
    assert "перемістив" not in conv.history[-1]["content"]                       # the withdrawn words aren't kept


def test_still_saying_it_after_the_check_gets_the_warning_and_no_more_requests():
    r = _Router(["Я переніс усі файли з Завантажень.", "Я переніс усі файли з Завантажень."])
    conv = Conversation(router=r, toolbox=_Box(*PC), lang="uk")
    out, text = _ask(conv, "перенеси файли")
    assert len(r.seen) == 2 and sum(isinstance(p, Redo) for p in out) == 1
    assert conv.last_reply.endswith("⚠️ " + i18n.t(chat.NOTHING_RAN, "uk"))


def test_a_folder_card_doesnt_make_moving_true():
    folder = ("pc_make_folder", {"place": "downloads", "path": "Програми"})
    r, box = _Router([[folder], "Папку буде створено. Починаю переміщення файлів…", [MOVE], "Ось картка з файлами."]), _Box(*PC)
    conv = Conversation(router=r, toolbox=box)
    out, _ = _ask(conv, "створи папку і перенеси туди інсталятори")
    assert box.runs == ["pc_make_folder", "pc_move"] and any(isinstance(p, Redo) for p in out)
    assert conv.last_reply == "Ось картка з файлами."
    # with no tool that moves, asking again can't help: the line says only the cards will happen
    r2 = _Router([[folder], "Папку буде створено. Починаю переміщення файлів…"])
    conv2 = Conversation(router=r2, toolbox=_Box("pc_make_folder", "pc_list"), lang="uk")
    out2, _ = _ask(conv2, "створи папку і перенеси туди інсталятори")
    assert not any(isinstance(p, Redo) for p in out2) and len(r2.seen) == 2
    assert conv2.last_reply.endswith(i18n.t(chat.LESS_DONE, "uk"))


def test_its_own_done_line_and_a_card_that_isnt_there_are_caught():
    assert chat.claim_phrase("Папки є.\n✅ Виконано переміщення файлів", ["pc_make_folder"]) == "✅ Виконано"
    assert chat.claim_phrase("✅ Виконано переміщення файлів", [], done_before=True) == ""
    press = "Натисни «Підтвердити» на картці, і все переїде."
    assert chat.claim_phrase(press, []) == "Натисни «Підтвердити"                  # whole words, for the check
    assert chat.claim_phrase("Готово, я перемістив усе в папку Програми.", []) == "перемістив усе в папку"
    assert chat.claim_phrase(press, [], waiting=True) == ""                       # a card of this chat waits
    assert chat.claim_phrase(press, ["pc_move"]) == ""                            # this reply made the card
    assert chat.claim_phrase("Як тільки підтвердиш, я все перенесу.", ["pc_list"]) == "Як тільки підтвердиш"
    assert chat.claim_phrase("Press Confirm on the card.", []) and chat.claim_phrase("Premi «Conferma».", [])
    assert chat.claim_phrase("Я перемістив абзац вище, щоб текст читався краще.", []) == ""   # about text, not files
    assert chat.claim_phrase("Я встановив Visual Studio.", ["app_search"]) == "встановив"
    assert chat.claim_phrase("Я встановив Visual Studio.", ["pc_move"]) == "встановив"        # the wrong card
    assert chat.claim_phrase("Я встановив Visual Studio.", ["app_install"]) == ""


def test_a_card_waiting_makes_press_confirm_right():
    r = _Router(["Натисни «Підтвердити» на картці вище, і файли переїдуть."])
    conv = Conversation(router=r, toolbox=_Box(*PC), cards_waiting=True)
    out, _ = _ask(conv, "що мені зробити далі?")
    assert len(r.seen) == 1 and not any(isinstance(p, Redo) for p in out) and "⚠️" not in conv.last_reply


def test_after_a_confirmed_card_saying_it_is_done_is_true():
    history = [{"role": "user", "content": "перенеси інсталятори"}, {"role": "assistant", "content": "Ось картка."},
               {"role": "assistant", "content": "✅ Moved 3 items to Downloads/Програми", "note": True}]
    r = _Router(["Так, я переніс інсталятори з Завантажень у Програми."])
    conv = Conversation(router=r, toolbox=_Box(*PC), history=history)
    out, _ = _ask(conv, "ти переніс?")
    assert len(r.seen) == 1 and not any(isinstance(p, Redo) for p in out) and "⚠️" not in conv.last_reply


def test_after_a_folder_card_moving_is_still_not_done():
    history = [{"role": "user", "content": "створи папку Програми"}, {"role": "assistant", "content": "Ось картка."},
               {"role": "assistant", "content": "✅ Створено папку Downloads/Програми", "note": True}]
    r, box = _Router(["Я переніс файли з Завантажень у Програми.", [MOVE], "Ось картка."]), _Box(*PC)
    conv = Conversation(router=r, toolbox=box, history=history)
    assert conv._done_before() == "✅ Створено папку Downloads/Програми"
    out, _ = _ask(conv, "а файли?")
    assert any(isinstance(p, Redo) for p in out) and box.runs == ["pc_move"]
    assert chat.claim_phrase("Я встановив Steam.", [], done_before="✅ Встановлено Steam") == ""
    assert chat.claim_phrase("Я відсортував файли в Завантаженнях.", [], done_before="✅ Розкладено файли в папці Downloads (9)") == ""
    assert chat.claim_phrase("Я відсортував файли в Завантаженнях.", [], done_before="✅ Встановлено Steam")


def test_set_is_also_installed_in_ukrainian():
    """«Встановив» is also «set»: a reminder, a theme or a wallpaper with its tool is true, a new folder isn't."""
    for said, ran in (("Встановив нагадування на 9:00.", ["set_reminder"]), ("Встановив темну тему.", ["pc_theme"]),
                      ("Встановив шпалери з морем.", ["pc_look_set"]), ("Готово, встановив.", ["mcp_notion_add"]),
                      ("Я встановив Python.", ["app_install"])):
        assert chat.false_claim(said, ran) == "", said
    for ran in (["pc_make_folder"], ["remember"], ["pc_open_site"]):
        assert chat.false_claim("Я встановив Python.", ran) == chat.LESS_DONE, ran
    # after the card is confirmed, in any app language; a folder card doesn't install anything
    assert chat.claim_phrase("Готово, встановив темну тему.", [], done_before="✅ Увімкнено темну тему") == ""
    assert chat.claim_phrase("Встановив темну тему.", [], done_before="✅ Zum dunklen Design gewechselt") == ""
    assert chat.claim_phrase("Я встановив Python.", [], done_before="✅ Створено папку Downloads/Програми") == "встановив"
    # asking again is worth it with a card that can set it, not with one that makes folders, and not for reminders
    # (they are in every chat: "I'm installing the packages" mustn't cost a second request for them)
    assert chat.claim_tools("Встановив темну тему", ["pc_theme", "pc_make_folder"]) == {"pc_theme"}
    assert chat.claim_tools("Я встановив Python", ["pc_make_folder", "remember", "set_reminder"]) == set()
    assert chat.claim_tools("✅ Готово", ["remember", "pc_make_folder"]) == {"pc_make_folder"}


def test_no_second_try_without_tools_that_act():
    r = _Router(["Я перемістив усі файли з Завантажень."])
    conv = Conversation(router=r, toolbox=_Box("web_search", "calculate"), lang="uk")     # a second opinion's tools
    out, _ = _ask(conv, "перенеси файли")
    assert len(r.seen) == 1 and not any(isinstance(p, Redo) for p in out)
    assert conv.last_reply.endswith(i18n.t(chat.NOTHING_RAN, "uk"))


# ---------------------------------------------------------------- moving files by a rule: one card for the group
@pytest.fixture
def home(tmp_path):
    folders = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in folders.values():
        f.mkdir()
    return folders


def _file(p: Path, age_days=40):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x" * 10)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


@pytest.fixture
def downloads(home):
    d = home["downloads"]
    for n in ("setup.exe", "VSCodeSetup.msi", "Minecraft-1.20.jar", "mod-b.JAR", "report.pdf", "photo.png", "game.zip"):
        _file(d / n)
    _file(d / "new.exe", age_days=0)                                    # just downloaded: maybe not finished
    _file(d / "big.zip.crdownload", age_days=0)
    _file(d / "Old stuff" / "inside.exe")
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    return d, acts, cards, pcfiles.Places(acts, lambda: "uk", folders=lambda: home, opener=lambda p: None)


def test_one_card_moves_every_file_of_a_kind(downloads):
    d, acts, cards, pl = downloads
    out = pl.propose_move("downloads", None, "Моди", ext=["jar"])
    c = cards[-1]["details"]
    assert c["files"] == ["Minecraft-1.20.jar", "mod-b.JAR"] and c["count"] == 2 and c["rule"] == ".jar"
    assert "Nothing has been changed yet" in out and "Minecraft-1.20.jar, mod-b.JAR" in out and "skipped" not in c
    acts.confirm(cards[-1]["id"])
    assert sorted(p.name for p in (d / "Моди").iterdir()) == ["Minecraft-1.20.jar", "mod-b.JAR"]
    assert (d / "setup.exe").exists()                                   # nothing else moved


def test_the_next_rule_leaves_out_files_already_on_a_waiting_card(downloads):
    d, acts, cards, pl = downloads
    pl.propose_move("downloads", [], "Моди", ext=[".jar"])
    out = pl.propose_move("downloads", ["*.zip", "*.jar"], "Архіви")
    c = cards[-1]["details"]
    assert c["files"] == ["game.zip"] and c["claimed"] == 2 and "2 already on another card" in out
    assert pl.propose_sort("downloads").count("already on another card") == 1
    sort = cards[-1]["details"]
    assert all(f not in g["files"] for g in sort["groups"] for f in ("game.zip", "mod-b.JAR"))
    acts.cancel(cards[1]["id"])                                         # the zip card is cancelled: free again
    acts.cancel(cards[2]["id"])
    pl.propose_move("downloads", ["*.zip"], "Архіви")
    assert cards[-1]["details"]["files"] == ["game.zip"]


def test_kinds_in_the_users_language_and_files_still_downloading(downloads):
    d, acts, cards, pl = downloads
    pl.propose_move("downloads", [], "Програми", kinds=["Інсталятори"])
    c = cards[-1]["details"]
    assert c["files"] == ["setup.exe", "VSCodeSetup.msi"] and c["skipped"] == 1 and c["rule"] == "Інсталятори"
    with pytest.raises(WorkError, match="Unknown kind"):
        pl.propose_move("downloads", [], "X", kinds=["Ракети"])


def test_age_and_words_in_the_name(downloads):
    d, acts, cards, pl = downloads
    _file(d / "report-2019.pdf", age_days=400)
    pl.propose_move("downloads", [], "Старе", older_than_days=365, name_has="REPORT")
    c = cards[-1]["details"]
    assert c["files"] == ["report-2019.pdf"] and c["rule"] == "старші за 365 дн. · у назві «report»"
    from lanterna.app import card_text
    assert card_text("pc_move", c, "uk").startswith("Які файли: старші за 365 дн.")
    with pytest.raises(WorkError, match="No files match"):
        pl.propose_move("downloads", [], "Старе", older_than_days=3650)


def test_a_rule_takes_files_only_a_named_folder_moves_whole(downloads):
    d, acts, cards, pl = downloads
    pl.propose_move("downloads", ["*"], "Усе")
    assert "Old stuff" not in cards[-1]["details"]["files"] and "new.exe" not in cards[-1]["details"]["files"]
    pl.propose_move("downloads", ["Old stuff"], "Архів")
    assert cards[-1]["details"]["files"] == ["Old stuff"] and "rule" not in cards[-1]["details"]
    pl.propose_move("downloads", ["*.exe"], "Програми", path="Old stuff")        # a rule inside a subfolder
    assert cards[-1]["details"]["files"] == ["Old stuff/inside.exe"]
    with pytest.raises(WorkError, match="Name the files"):
        pl.propose_move("downloads", [], "Програми")
    with pytest.raises(WorkError, match="outside|Hidden"):
        pl.propose_move("downloads", ["../*.exe"], "Програми")
    with pytest.raises(WorkError, match="outside"):
        pl.propose_move("downloads", ["*.exe"], "Програми", path=str(d.parent))


def test_named_files_that_dont_fit_the_rule_are_left_out(downloads):
    d, acts, cards, pl = downloads
    out = pl.propose_move("downloads", ["setup.exe", "report.pdf"], "Програми", kinds=["Installers"])
    assert cards[-1]["details"]["files"] == ["setup.exe"] and "1 named ones that don't fit" in out


def test_the_model_gets_the_rule_tool(downloads, tmp_path):
    d, acts, cards, pl = downloads
    box = Toolbox(Store(tmp_path / "t.db"), extra=lambda: pcfiles.place_tools(pl))
    schema = next(s for s in box.schemas() if s["function"]["name"] == "pc_move")["function"]["parameters"]
    assert {"kinds", "ext", "older_than_days", "name_has", "path"} <= set(schema["properties"])
    assert schema["required"] == ["place", "to"] and "Installers" in schema["properties"]["kinds"]["items"]["enum"]
    out = box.run("pc_move", json.dumps({"place": "downloads", "to": "Моди", "ext": ".jar"}))   # one string is fine
    assert "The card moves 2 item(s)" in out and cards[-1]["details"]["count"] == 2


# ---------------------------------------------------------------- a job in steps on this computer: the task plan
def test_the_plan_comes_with_the_pc_tools():
    box = Toolbox(None, extra=lambda: [plans.plan_tool(lambda: {}, lambda p: None),
                                       Tool("pc_move", "", {"type": "object", "properties": {}}, lambda: "", "📦", "pc"),
                                       Tool("app_install", "", {"type": "object", "properties": {}}, lambda: "", "📦",
                                            "apps")])
    names = lambda ctx: {s["function"]["name"] for s in box.schemas(ctx)}   # noqa: E731
    assert {"plan", "pc_move"} <= names("розсортуй мої завантаження по кроках")
    assert {"plan", "app_install"} <= names("встанови мені програми")
    assert not {"plan", "pc_move", "app_install"} & names("як справи?")
    assert "plan" in names("(task plan) Plan (0 of 2 done)")
    assert "pc_move" in names("перенеси інсталятори у Програми")              # no "file" or "folder" in it


def test_moving_words_turn_the_file_tools_on():
    from lanterna.tools import GROUPS
    for text in ("перенеси інсталятори у Програми", "перемісти моди", "move the installers", "sposta i file"):
        assert GROUPS["pc"].search(text), text


def test_a_pc_job_gets_the_plan_rules_but_not_the_project_ones():
    r = _Router(["ок"])
    conv = Conversation(router=r, toolbox=_Box("plan", *PC), plan_text="Plan (1 of 2 done):\n1. [done] A\n2. [now] B")
    _ask(conv, "далі")
    system = r.seen[0]["msgs"][0]["content"]
    assert chat.PC_GUIDE in system and "call plan first" in system and chat.PROJECT_GUIDE not in system
    assert "Your task plan in this chat is not finished" in system
    assert conv._context("далі").endswith("(task plan) Plan (1 of 2 done):\n1. [done] A\n2. [now] B")


def test_a_pc_job_with_a_plan_gets_twelve_rounds():
    steps = ("plan", {"steps": ["Картка: інсталятори → Програми", "Картка: .jar → Моди"]})
    moves = [[("pc_move", {"place": "downloads", "to": f"Тека{i}", "ext": [f".x{i}"]})] for i in range(8)]
    r, box = _Router([[steps], *moves, "Готово: картки чекають на «Підтвердити»."]), _Box("plan", *PC)
    _ask(Conversation(router=r, toolbox=box), "розклади завантаження по моїй схемі")
    assert box.runs.count("pc_move") == 8                              # more than the usual 4 rounds


# ---------------------------------------------------------------- the app: the answer starts again on the screen
def _api(tmp_path, monkeypatch, home):
    from lanterna import keys
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.settings.ai_titles = api.settings.follow_ups = api.settings.auto_memory = False
    api.settings.compact_chats, api.settings.pc_access, api.settings.lang = False, True, "uk"
    api.places = pcfiles.Places(api.actions, lambda: "uk", folders=lambda: home, opener=lambda p: None,
                                trash=lambda ps: None)
    return api


def test_the_app_withdraws_the_words_and_shows_the_real_card(tmp_path, monkeypatch, home):
    from lanterna.app import _history, _Stream
    for n in ("setup.exe", "VSCodeSetup.msi", "report.pdf"):
        _file(home["downloads"] / n)
    api = _api(tmp_path, monkeypatch, home)
    tid = api.new_thread()["id"]
    sid = "s1"
    api._streams[sid] = _Stream("uk")
    turns = ["Я перемістив усі інсталятори із Завантажень.", [MOVE], "Картка готова: підтверди її, і вони переїдуть."]
    api._run(sid, tid, "перенеси інсталятори із завантажень у Програми", _history(api.store.messages(tid)),
             router=_Router(turns))
    p = api.poll(sid)
    assert p["final"] == "Картка готова: підтверди її, і вони переїдуть." and not p["error"]
    assert [c["kind"] for c in p["cards"]] == ["pc_move"] and p["cards"][0]["details"]["rule"] == "Інсталятори"
    assert any("Lanterna попросила модель ще раз" in s["text"] for s in p["steps"])
    assert api.cards(tid)[0]["details"]["files"] == ["setup.exe", "VSCodeSetup.msi"]
    # the next answer knows a card waits: "press Confirm" is right then
    r = _Router(["Натисни «Підтвердити» на картці вище."])
    api._streams["s2"] = _Stream("uk")
    api._run("s2", tid, "що далі?", _history(api.store.messages(tid)), router=r)
    assert api.poll("s2")["final"] == "Натисни «Підтвердити» на картці вище." and len(r.seen) == 1


def test_poll_sends_the_whole_text_once_after_a_new_start():
    from lanterna.app import Api, _Stream
    api = Api.__new__(Api)
    api._streams, api.settings = {}, SimpleNamespace(lang="uk")
    st = _Stream("uk")
    api._streams["s"] = st
    st.pieces = ["Я перемістив усе."]
    assert api.poll("s", 0)["text"] == "Я перемістив усе."
    st.pieces, st.redo = ["Ось "], True                                # Lanterna's check: it starts again
    p = api.poll("s", 17)
    assert p["replace"] and p["text"] == "Ось " and p["offset"] == 4
    st.pieces.append("картка.")
    p = api.poll("s", 4)
    assert "replace" not in p and p["text"] == "картка." and p["offset"] == 11


def test_both_screens_replace_the_text():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'else if (p.replace) { text_ = p.text || ""; offset = p.offset;' in js
    tui = (Path(chat.__file__).parent / "tui.py").read_text(encoding="utf-8")
    assert 'elif r.get("replace"):' in tui


def test_a_cards_line_doesnt_count_as_a_second_opinion(tmp_path, monkeypatch, home):
    from lanterna.providers import ProviderError
    api = _api(tmp_path, monkeypatch, home)
    tid = api.new_thread()["id"]
    api.store.add(tid, "user", "перенеси")
    api.store.add(tid, "assistant", "Ось картка.", "groq · a")
    api.store.add(tid, "assistant", "✅ Moved 2 items to Downloads/Програми", "")
    api.store.add(tid, "assistant", "Друга думка.", "gemini · b")

    def no_router():
        raise ProviderError("auth", "no keys")
    api._get_router = no_router
    assert api.second_opinion(tid)["error"] == "auth"                   # not "enough": two answers so far


def test_the_new_lines_are_in_every_language():
    for text in ("The answer said «{said}», but nothing was done: Lanterna asked the model again", chat.LESS_DONE,
                 "Which files: {r}", "Already on another card: {n}", "older than {n} days", "name has «{x}»"):
        for lang in ("uk", "it", "de", "es", "fr", "pl"):
            assert i18n.t(text, lang) != text, (text, lang)
