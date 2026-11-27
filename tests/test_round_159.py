"""Round 159 (1.1.11b11): folders for chats in the list on the left.

Asked for «папки, щоб можна було групувати чати». A chat carries its folder (synced like its pin: the newer move
wins, and moving it on one computer while renaming it on another keeps both). A folder made here stays while it is
empty. Deleting a folder keeps its chats. The window has a «Folders» group with a +, a ⋯ menu per folder, «Move to
folder» in a chat's menu and drag and drop; the terminal shows the folders in its list and has the command too.
"""
import re
import time
from pathlib import Path

from lanterna import gui, i18n, keys, selfhelp, sync
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


def test_a_chat_carries_its_folder(tmp_path):
    st = Store(tmp_path / "a.db")
    a, b, c = st.new_thread("Алгебра"), st.new_thread("Фізика"), st.new_thread("Рецепти")
    st.set_folder(a, "Навчання")
    st.set_folder(b, "Навчання")
    assert st.folders() == {"Навчання": 2}
    assert {x["id"]: x["folder"] for x in st.threads()} == {a: "Навчання", b: "Навчання", c: ""}
    assert st.move_folder("Навчання", "Школа") == 2 and st.folders() == {"Школа": 2}
    assert st.move_folder("Школа", "") == 2 and st.folders() == {}
    st.set_folder(-3, "Навчання")                               # a private chat isn't kept: nothing happens
    assert st.folders() == {}


def test_folders_in_the_app(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    a, b = api.new_thread()["id"], api.new_thread()["id"]
    assert api.add_folder("  Робота  ")["name"] == "Робота"
    assert api.add_folder("")["ok"] is False
    assert api.folders() == [{"name": "Робота", "n": 0, "open": True}]          # empty, but it stays
    assert api.move_to_folder(a, "навчання   і   школа") == {"ok": True, "name": "навчання і школа"}
    assert api.move_to_folder(b, "НАВЧАННЯ І ШКОЛА")["name"] == "навчання і школа"   # the same folder, any case
    assert [f["name"] for f in api.folders()] == ["навчання і школа", "Робота"]       # by name
    assert api.folders()[0]["n"] == 2
    assert api.move_to_folder(999, "Робота")["ok"] is False and api.move_to_folder(0, "Робота")["ok"] is False
    assert api.move_to_folder(a, "x" * 90)["name"] == "x" * 40
    api.move_to_folder(a, "навчання і школа")
    assert {"name": "x" * 40, "n": 0, "open": True} in api.folders()   # made by the move: it stays, empty
    assert api.delete_folder("x" * 40) == {"ok": True, "chats": 0}
    # renamed: its chats go with it; only the case may change too
    assert api.rename_folder("навчання і школа", "Навчання")["name"] == "Навчання"
    assert api.rename_folder("Навчання", "НАВЧАННЯ")["name"] == "НАВЧАННЯ"
    assert {x["id"]: x["folder"] for x in api.threads()} == {a: "НАВЧАННЯ", b: "НАВЧАННЯ"}
    # renamed onto another folder: they join it
    assert api.rename_folder("НАВЧАННЯ", "робота")["name"] == "Робота"
    assert api.folders() == [{"name": "Робота", "n": 2, "open": True}]
    assert api.fold_folder("Робота", False) == {"ok": True} and api.folders()[0]["open"] is False
    api.fold_folder("Робота", True)
    assert api.folders()[0]["open"] is True
    # deleted: the chats stay, back in the list
    api.fold_folder("Робота", False)
    assert api.delete_folder("Робота") == {"ok": True, "chats": 2}
    assert api.folders() == [] and [x["folder"] for x in api.threads()] == ["", ""]
    assert api.settings.groups_closed == [] and len(api.threads()) == 2
    assert api.move_to_folder(a, "")["name"] == "" and api.folders() == []


def test_the_folder_goes_to_the_other_computer_like_a_pin(tmp_path):
    here, there = Store(tmp_path / "here.db"), Store(tmp_path / "there.db")
    tid = here.new_thread("Рецепти")
    there.import_sync(sync.merge(sync.empty(), here.export_sync()))
    tid2 = there.threads()[0]["id"]
    assert there.threads()[0]["folder"] == ""
    uid = next(iter(here.export_sync()["threads"]))
    assert "folder" not in here.export_sync()["threads"][uid]   # never moved: nothing extra goes
    here.set_folder(tid, "Кухня")
    time.sleep(0.01)
    there.rename(tid2, "Рецепти бабусі")                         # renamed there meanwhile: both stay
    merged = sync.merge(there.export_sync(), here.export_sync())
    assert merged["threads"][uid]["folder"] == "Кухня" and merged["threads"][uid]["title"] == "Рецепти бабусі"
    there.import_sync(merged)
    here.import_sync(merged)
    assert there.threads()[0]["folder"] == "Кухня" == here.threads()[0]["folder"]
    assert there.threads()[0]["title"] == "Рецепти бабусі"
    time.sleep(0.01)
    there.set_folder(tid2, "")                                   # taken out there: newer, so it wins
    merged = sync.merge(here.export_sync(), there.export_sync())
    here.import_sync(merged)
    assert here.threads()[0]["folder"] == ""
    # a backup brings the folder back with the chat
    snap = there.export_sync()
    there.set_folder(tid2, "Кухня")
    snap = there.export_sync()
    fresh = Store(tmp_path / "fresh.db")
    fresh.restore(snap)
    assert fresh.threads()[0]["folder"] == "Кухня"


def test_window_terminal_and_help_have_it():
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert {"folders", "add_folder", "move_to_folder", "rename_folder", "delete_folder", "fold_folder"} <= gui.METHODS
    for name in ("function groupMenu(", "function folderDialog(", "async function moveDialog(", "function openMenu(",
                 "b.draggable = true", 'data-act="move"', ".th-row:not(.fl-row)", 'id="i-chats"'):
        assert name in js + html, name
    assert ".fl-row.drop" in css and ".mv-opt" in css
    from lanterna import tui
    assert ("Move to folder", "move_to_folder", "") in tui.CHAT_COMMANDS and hasattr(tui._ChatScreen, "action_move_to_folder")
    rows = tui._by_folder([{"id": 1, "title": "a", "folder": "Школа"}, {"id": 2, "title": "b", "folder": ""},
                           {"id": 3, "title": "c", "folder": "Кухня"}, {"id": 4, "title": "d", "folder": "Школа"}])
    assert [r.get("head") or r["id"] for r in rows] == [2, "▸ Кухня", 3, "▸ Школа", 1, 4]
    for text in ("Folders", "New folder", "Move to folder", "Not in a folder", "Delete folder"):
        assert i18n.t(text, "uk") != text
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(text), (lang, text)
    about = selfhelp.about("uk")
    assert "«Перемістити в папку»" in about and "«Нова папка»" in about and "«Папки»" in about


def test_no_two_functions_of_the_window_share_a_name():
    """b11's first try had two folderMenu(): in a plain script the later one wins, so the chat folders' ⋯ opened the
    working folder's menu under the message box. Each top-level function of app.js has its own name."""
    js = (UI / "app.js").read_text(encoding="utf-8")
    names = re.findall(r"^(?:async )?function (\w+)\(", js, re.M)
    twice = sorted({n for n in names if names.count(n) > 1})
    assert not twice, twice
    assert len(names) > 100
