"""0.6.0 stage 3: edit the last message, answer again, export, memory that updates itself. No real network."""
import json
import time

import httpx

from lanterna import keys
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router


def _sse(text):
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


def _api(tmp_path, monkeypatch, answer=lambda body, n: f"Відповідь {n}"):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.settings.ai_titles = a.settings.follow_ups = a.settings.compact_chats = False
    bodies = []

    def h(req):
        body = json.loads(req.content)
        bodies.append(body)
        return httpx.Response(200, content=_sse(answer(body, len(bodies))))
    a._router = Router([Candidate("groq", "m", 70)],
                       client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))

    def wait(sid):
        for _ in range(300):
            p = a.poll(sid)
            if p["done"]:
                return p
            time.sleep(0.02)
        raise AssertionError("no answer")
    return a, bodies, wait


def _roles(a, tid):
    return [(m["role"], m["content"]) for m in a.store.messages(tid)]


# ---------------------------------------------------------------- edit / answer again
def test_trim_tail_leaves_a_note_for_other_devices(tmp_path):
    from lanterna.store import Store
    s = Store(tmp_path / "s.db")
    tid = s.new_thread()
    for i in range(3):
        s.add(tid, "user", f"q{i}")
    s.trim_tail(tid, 2)
    assert [m["content"] for m in s.messages(tid)] == ["q0"]
    assert s._q("SELECT COUNT(*) AS n FROM deleted")[0]["n"] == 2


def test_answer_again_replaces_the_last_answer(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    wait(a.send(tid, "привіт")["stream"])
    wait(a.send(tid, "як справи?")["stream"])
    p = wait(a.send(tid, "", [], again=True)["stream"])
    assert p["final"] == "Відповідь 3"
    assert _roles(a, tid) == [("user", "привіт"), ("assistant", "Відповідь 1"),
                              ("user", "як справи?"), ("assistant", "Відповідь 3")]
    assert bodies[-1]["messages"][-1]["content"] == "як справи?"          # the same question went again, once
    assert [m["content"] for m in bodies[-1]["messages"][1:]].count("як справи?") == 1


def test_retry_after_an_error_does_not_repeat_the_question(tmp_path, monkeypatch):
    a, bodies, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    a.store.add(tid, "user", "питання без відповіді")              # what an error leaves behind
    wait(a.send(tid, "питання без відповіді", [], again=True)["stream"])
    assert _roles(a, tid) == [("user", "питання без відповіді"), ("assistant", "Відповідь 1")]


def test_edit_last_gives_the_question_back(tmp_path, monkeypatch):
    a, _, wait = _api(tmp_path, monkeypatch)
    tid = a.new_thread()["id"]
    wait(a.send(tid, "привіт")["stream"])
    wait(a.send(tid, "скільки буде 2+2?")["stream"])
    assert a.edit_last(tid) == {"ok": True, "text": "скільки буде 2+2?"}
    assert _roles(a, tid) == [("user", "привіт"), ("assistant", "Відповідь 1")]
    assert a.edit_last(a.new_thread()["id"]) == {"ok": True, "text": ""}   # an empty chat: nothing to take back


# ---------------------------------------------------------------- export
def test_export_chat_writes_markdown_to_downloads(tmp_path, monkeypatch):
    a, _, wait = _api(tmp_path, monkeypatch)
    down = tmp_path / "Downloads"
    down.mkdir()
    monkeypatch.setattr(a.places, "folders", lambda: {"downloads": down})
    tid = a.new_thread()["id"]
    a.store.rename(tid, "План: подорож / Львів?")
    wait(a.send(tid, "привіт")["stream"])
    r = a.export_chat(tid)
    assert r["ok"] and r["name"] == "План подорож Львів.md"
    text = (down / r["name"]).read_text(encoding="utf-8")
    assert text.startswith("# План: подорож / Львів?") and "привіт" in text and "Відповідь 1" in text
    assert a.export_chat(tid)["name"] == "План подорож Львів (2).md"     # never overwrites
    assert a.export_chat(99999) == {"ok": False}
    assert a.export_chat(a.new_thread()["id"]) == {"ok": False}            # an empty chat: nothing to save


def test_backup_has_chats_memory_and_reminders(tmp_path, monkeypatch):
    a, _, _ = _api(tmp_path, monkeypatch)
    monkeypatch.setattr(a.places, "folders", lambda: {"downloads": tmp_path})
    tid = a.new_thread()["id"]
    a.store.add(tid, "user", "питання")
    a.store.add_fact("любить каву")
    a.store.add_reminder("подзвонити", time.time() + 3600)
    r = a.export_all()
    data = json.loads((tmp_path / r["name"]).read_text(encoding="utf-8"))
    assert data["app"] == "Lanterna" and data["memory"] == ["любить каву"]
    assert data["threads"][0]["messages"][0]["content"] == "питання"
    assert data["reminders"][0]["text"] == "подзвонити"


def test_show_saved_opens_only_files_it_saved(tmp_path, monkeypatch):
    from lanterna import pcfiles
    a, _, _ = _api(tmp_path, monkeypatch)
    monkeypatch.setattr(a.places, "folders", lambda: {"downloads": tmp_path})
    opened = []
    monkeypatch.setattr(pcfiles, "_open_in_file_manager", lambda p: opened.append(p))
    assert a.show_saved(r"C:\Windows\System32\cmd.exe") is False
    r = a.export_all()
    assert a.show_saved(r["path"]) is True and str(opened[0]) == r["path"]


# ---------------------------------------------------------------- memory that updates itself
def test_about_me_and_clean_facts():
    from lanterna.chat import about_me, clean_facts
    assert about_me("Я працюю медсестрою у Львові") and about_me("I study physics") and about_me("J'aime le thé")
    assert not about_me("Яка погода завтра?") and not about_me("Jaka jest pogoda i wiatr?")
    raw = "- Works as a nurse.\nNONE\nHer password is hunter2\nPhone 0671234567\nLives in Lviv.\nLikes tea.\nHas a cat."
    assert clean_facts(raw, ["lives in lviv"]) == ["Works as a nurse.", "Likes tea."]
    assert clean_facts("NONE", []) == []


def _memory_api(tmp_path, monkeypatch, on=True):
    from lanterna.chat import MEMORY_PROMPT
    seen = []

    def answer(body, n):
        if body["messages"][0]["content"] == MEMORY_PROMPT:
            seen.append(body["messages"][1]["content"])
            return "Працює медсестрою.\nЖиве у Львові."
        return "Гарно!"
    a, bodies, wait = _api(tmp_path, monkeypatch, answer)
    a.settings.auto_memory = on
    return a, seen, wait


def test_memory_learns_facts_and_undo_removes_them(tmp_path, monkeypatch):
    a, seen, wait = _memory_api(tmp_path, monkeypatch)
    a.store.add_fact("Живе у Львові.")
    tid = a.new_thread()["id"]
    p = wait(a.send(tid, "я медсестра, живу у Львові, порадь книжку")["stream"])
    assert p["learning"] is True
    got = a.wait_memory(tid)
    assert [f["text"] for f in got] == ["Працює медсестрою."]          # what was known isn't added twice
    assert "Живе у Львові." in seen[0]                                   # the side model saw what is known
    assert [f["text"] for f in a.store.facts()] == ["Живе у Львові.", "Працює медсестрою."]
    a.delete_fact(got[0]["id"])                                          # Undo
    assert [f["text"] for f in a.store.facts()] == ["Живе у Львові."]


def test_memory_stays_quiet_when_off_or_not_about_me(tmp_path, monkeypatch):
    a, seen, wait = _memory_api(tmp_path, monkeypatch, on=False)
    tid = a.new_thread()["id"]
    assert wait(a.send(tid, "я медсестра")["stream"])["learning"] is False
    a.settings.auto_memory = True
    assert wait(a.send(tid, "скільки буде 2+2?")["stream"])["learning"] is False
    assert seen == [] and a.wait_memory(tid) == [] and a.store.facts() == []


def test_memory_is_off_by_default_and_synced():
    from lanterna import sync
    from lanterna.config import Settings
    assert Settings().auto_memory is False and "auto_memory" in sync.PREFS
