"""0.3.5: pipx self-update, the history with Undo, weekly tidy-up and disk space, “what went to the model”,
the local model as a spare and Install Ollama. Nothing real is installed, moved or changed."""
import os
import time
from collections import namedtuple
from pathlib import Path

import pytest

from lanterna import discovery, history, pcfiles, sent, updates
from lanterna.discovery import Candidate


def _file(p: Path, text="x", age_days=10):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


# ---------------------------------------------------------------- pipx self-update
def test_pipx_update_upgrades_or_reinstalls_the_release():
    calls = []

    def ok(args):
        calls.append(args)
        return 0, "upgraded package lanterna from 0.3.4 to 0.3.5"
    updates.pipx_update("0.3.5", ok)
    assert calls == [["upgrade", "lanterna"]]

    calls.clear()

    def pinned(args):
        calls.append(args)
        return (0, "lanterna is already at latest version 0.3.4") if args[0] == "upgrade" else (0, "installed")
    updates.pipx_update("0.3.5", pinned)
    assert calls[1][:2] == ["install", "--force"] and calls[1][2].endswith("@v0.3.5")

    with pytest.raises(RuntimeError, match="no space"):
        updates.pipx_update("0.3.5", lambda args: (2, "error\nno space left"))


def test_pipx_asset_only_for_pipx_installs():
    info = {"newer": True, "latest": "0.3.5"}
    assert updates.pipx_asset(info, "pipx", which=lambda n: "/usr/bin/pipx") == {"version": "0.3.5", "pipx": True}
    assert updates.pipx_asset(info, "pipx", which=lambda n: None) is None
    assert updates.pipx_asset(info, "setup", which=lambda n: "/usr/bin/pipx") is None
    assert updates.pipx_asset({"newer": False, "latest": "0.3.5"}, "pipx", which=lambda n: "x") is None


def test_updater_pipx_phases():
    u = updates.Updater(pipx_runner=lambda args: (0, "upgraded"), quit_app=lambda: None)
    assert u.start({"version": "0.3.5", "pipx": True}, wait=True)["phase"] == "restart"
    u = updates.Updater(pipx_runner=lambda args: (3, "network down"), quit_app=lambda: None)
    st = u.start({"version": "0.3.5", "pipx": True}, wait=True)
    assert st["phase"] == "error" and "network down" in st["error"]


# ---------------------------------------------------------------- history and undo
def test_history_keeps_the_newest_and_marks_undone(tmp_path):
    h = history.History(tmp_path / "h.json")
    first = h.add("pc_trash", {"files": ["a"], "preview": "big"}, "ok", {"type": "trash", "paths": ["a"]})
    h.add("pc_mkdir", {"path": "x"}, "ok", {"type": "nonsense"})
    items = h.items()
    assert [x["kind"] for x in items] == ["pc_mkdir", "pc_trash"]
    assert items[0]["undo"] is None and "preview" not in items[1]["details"]
    h.mark(first, "done")
    assert h.get(first)["undone"] is True
    for i in range(history.LIMIT + 5):
        h.add("pc_mkdir", {"path": str(i)})
    assert len(h.items()) == history.LIMIT
    h.clear()
    assert h.items() == []


def test_undo_moves_and_empty_folders(tmp_path):
    root = tmp_path / "Downloads"
    a = _file(root / "a.pdf")
    dst = root / "Docs" / "a.pdf"
    dst.parent.mkdir(parents=True)
    a.rename(dst)
    assert history.undo_moves([(str(a), str(dst))], {str(root)}) == (1, 0)
    assert a.exists() and not (root / "Docs").exists()
    assert history.undo_moves([(str(a), str(dst))], {str(root)}) == (0, 1)   # nothing to bring back now


def test_undo_rmdir_and_backup(tmp_path):
    d = tmp_path / "new"
    d.mkdir()
    (d / "f").write_text("x")
    assert history.undo_rmdir(str(d)) is False
    (d / "f").unlink()
    assert history.undo_rmdir(str(d)) is True and not d.exists()

    p, b = tmp_path / "note.txt", tmp_path / "old.txt"
    p.write_text("new")
    b.write_text("old")
    assert history.undo_restore_backup(str(p), str(b)) is True and p.read_text() == "old"
    assert history.undo_restore_backup(str(p), str(tmp_path / "missing")) is False


def test_freedesktop_trash_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    p = _file(tmp_path / "docs" / "a b.txt", "keep me")
    pcfiles._trash_freedesktop(p)
    assert not p.exists()
    assert pcfiles._restore_freedesktop(p) is True and p.read_text() == "keep me"
    assert not list((tmp_path / "share" / "Trash" / "info").glob("*"))
    assert pcfiles._restore_freedesktop(p) is False


# ---------------------------------------------------------------- weekly tidy-up and disk space
@pytest.fixture
def api(tmp_path, monkeypatch):
    from lanterna import app as app_mod
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(app_mod, "notify", lambda *a, **k: None)
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    home = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in home.values():
        f.mkdir()
    a.places._folders = lambda: home
    a._home = home
    return a


def test_tidy_and_space_are_off_by_default(api):
    from lanterna.config import Settings
    s = Settings()
    assert (s.tidy_weekly, s.space_help, s.local_fallback) == (False, False, True)
    api.settings.pc_access = True
    for i in range(8):
        _file(api._home["downloads"] / f"f{i}.pdf")
    assert api.maintenance() == []


def test_weekly_tidy_makes_a_chat_with_a_card(api):
    api.settings.pc_access, api.settings.tidy_weekly = True, True
    for i in range(6):
        _file(api._home["downloads"] / f"f{i}.pdf")
    _file(api._home["downloads"] / "new.pdf", age_days=0)            # still downloading: not counted
    out = api.maintenance(now=10 * 86400)
    assert len(out) == 1 and out[0]["kind"] == "tidy" and "6" in out[0]["text"]
    msgs = api.messages(out[0]["tid"])
    assert any("Downloads" in m["content"] for m in msgs if m["role"] == "assistant")
    assert api.maintenance(now=10 * 86400 + 3600) == []               # once a week
    assert (api._home["downloads"] / "f0.pdf").exists()               # nothing moved before Confirm


def test_space_note_when_the_disk_is_almost_full(api, monkeypatch):
    from lanterna import app as app_mod
    du = namedtuple("du", "total used free")
    monkeypatch.setattr(app_mod.shutil, "disk_usage", lambda p: du(500 * 1024 ** 3, 497 * 1024 ** 3, 3 * 1024 ** 3))
    api.settings.pc_access, api.settings.space_help = True, True
    out = api.maintenance(now=5 * 86400)
    assert [x["kind"] for x in out] == ["space"] and "3.0" in out[0]["text"]
    assert api.maintenance(now=5 * 86400 + 60) == []                  # once a day


# ---------------------------------------------------------------- what went to the model
def test_sent_names_kinds_of_data_never_contents():
    items = sent.build("groq · llama", False, 4, True, 2, ["cv.pdf"], 1,
                       [("pc_list", "{}"), ("pc_find", "{}"), ("pc_read", '{"path": "notes.txt"}'),
                        ("web_search", '{"query": "meteo"}'), ("read_page", '{"url": "https://example.org/a"}')])
    lines = sent.view(sent.dumps(items), "en")
    assert lines[0] == "Sent to groq · llama"
    assert "Your message and 4 earlier messages of this chat" in lines
    assert lines.count("Names and sizes of files in your folders") == 1
    assert "The text of the file notes.txt" in lines and "A web page was opened: example.org" in lines
    local = sent.view(sent.dumps(sent.build("qwen3", True, 0, False, 0, [], 0, [])), "de")
    assert local[0] == "Auf diesem Computer geblieben (qwen3)" and local[1] == "Deine Nachricht"
    assert sent.view("", "en") == [] and sent.view("not json", "en") == []


# ---------------------------------------------------------------- local model as a spare
def test_local_models_go_last_as_a_spare(monkeypatch):
    monkeypatch.setattr(discovery, "cloud_models", lambda pref, refresh: [Candidate("groq", "llama", 90)])
    monkeypatch.setattr(discovery, "local_models", lambda picks: [Candidate("ollama", "qwen3:8b", 50)])
    plain = discovery.get_models(mode="cloud")
    assert [c.model for c in plain] == ["llama"]
    spare = discovery.get_models(mode="cloud", fallback=True)
    assert [c.model for c in spare] == ["llama", "qwen3:8b"] and spare[1].fallback and not spare[0].fallback

    def broken(picks):
        raise OSError("ollama missing")
    monkeypatch.setattr(discovery, "local_models", broken)
    assert [c.model for c in discovery.get_models(mode="cloud", fallback=True)] == ["llama"]


def test_install_ollama_needs_winget_and_goes_to_the_history(api, monkeypatch):
    monkeypatch.setattr(api.apps, "managers", lambda: [])
    r = api.install_ollama()
    assert r["ok"] is False and "Ollama" in r["text"]

    class Done:
        state, kind, result = "done", "app_install", "installed"
        details = {"id": "Ollama.Ollama", "name": "Ollama"}
        undo = {"type": "app", "id": "Ollama.Ollama"}
    monkeypatch.setattr(api.apps, "managers", lambda: ["winget"])
    monkeypatch.setattr(api.actions, "run_now", lambda propose: Done())
    r = api.install_ollama()
    assert r["ok"] is True
    assert api.history.items()[0]["kind"] == "app_install"


# ---------------------------------------------------------------- Check Lanterna
def test_doctor_quick_checks_are_translated_and_go_into_bug_reports(api):
    r = api.doctor(network=False)
    assert r["checks"] and r["worst"] in ("ok", "warn", "fail")
    assert all(c["status"] in ("ok", "warn", "fail", "info") and c["title"] for c in r["checks"])
    assert "Lanterna" in r["text"]
    api.save_settings({"lang": "de"})
    titles = [c["title"] for c in api.doctor(network=False)["checks"]]
    assert "Datenordner" in titles or "Version" in titles
    body = api.bug_report("it crashed", True)["body"]
    assert "it crashed" in body
