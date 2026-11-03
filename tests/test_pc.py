"""This computer: the user's folders, programs and safe settings (no real installs or settings are touched)."""
import os
import time
from pathlib import Path

import pytest

from lanterna import apps, pcfiles, pcsys
from lanterna.workspace import Actions, WorkError


@pytest.fixture
def home(tmp_path):
    folders = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in folders.values():
        f.mkdir()
    return folders


def _file(p: Path, text="x", age_days=10):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def _places(home, lang="en", trashed=None):
    acts, cards = Actions(), []
    acts.bind(cards, 1)

    def trash(paths):
        for p in paths:
            trashed.append(p.name)
            p.unlink() if p.is_file() else __import__("shutil").rmtree(p)
    return pcfiles.Places(acts, lambda: lang, folders=lambda: home, trash=trash if trashed is not None else pcfiles.to_trash,
                          opener=lambda p: None), acts, cards


# ---------------------------------------------------------------- folders
def test_sort_downloads_by_type_and_undo(home):
    d = home["downloads"]
    for n in ("report.pdf", "photo.JPG", "setup.exe", "music.mp3", "notes.txt", "weird.xyz"):
        _file(d / n)
    _file(d / "big.zip.crdownload")                          # still downloading
    _file(d / "fresh.pdf", age_days=0)                       # changed just now: maybe still downloading
    (d / "Old stuff").mkdir()
    pl, acts, cards = _places(home, lang="uk")
    assert "Installers: 1" in pl.overview("downloads") or "Installers" in pl.overview("downloads")
    out = pl.propose_sort("downloads")
    assert "Nothing has been changed yet" in out and len(cards) == 1
    c = cards[0]
    assert c["kind"] == "pc_sort" and c["details"]["count"] == 6 and c["details"]["skipped"] == 2
    assert {g["to"] for g in c["details"]["groups"]} == {"Документи", "Картинки", "Інсталятори", "Музика", "Інше"}
    assert (d / "report.pdf").exists()                        # nothing moved before Confirm
    a = acts.confirm(c["id"])
    assert a.state == "done", a.result
    assert (d / "Документи" / "report.pdf").exists() and (d / "Документи" / "notes.txt").exists()
    assert (d / "Інсталятори" / "setup.exe").exists() and (d / "fresh.pdf").exists() and (d / "big.zip.crdownload").exists()
    assert (d / "Old stuff").is_dir()
    msg = pl.undo_sort(c["details"]["undo"])
    assert "6 files are back" in msg and (d / "report.pdf").exists() and not (d / "Документи").exists()
    with pytest.raises(WorkError):
        pl.undo_sort(c["details"]["undo"])


def test_sort_keeps_both_files_when_a_name_is_taken(home):
    d = home["downloads"]
    _file(d / "a.pdf", "new")
    _file(d / "Documents" / "a.pdf", "old")
    pl, acts, cards = _places(home)
    pl.propose_sort("downloads")
    acts.confirm(cards[0]["id"])
    assert (d / "Documents" / "a.pdf").read_text() == "old" and (d / "Documents" / "a (2).pdf").read_text() == "new"


def test_paths_stay_inside_the_users_folders(home, tmp_path):
    _file(tmp_path / "secret.txt")
    _file(home["documents"] / ".hidden" / "x.txt")
    pl, acts, cards = _places(home)
    for bad in ("../secret.txt", "..\\secret.txt", ".hidden/x.txt", "/etc/passwd"):
        with pytest.raises(WorkError):
            pl.read("documents", bad)
    with pytest.raises(WorkError):
        pl.overview("windows")
    with pytest.raises(WorkError):
        pl.propose_move("documents", ["../secret.txt"], "x")
    assert ".hidden" not in pl.list("documents")


def test_secret_looking_files_are_not_read(home):
    _file(home["downloads"] / "client_secret_123.json", '{"client_secret": "GOCSPX-abc"}')
    _file(home["downloads"] / "notes.txt", "token " + "AI" + "zaSyA1234567890abcdefghijklmnopqrstuv inside")
    _file(home["downloads"] / "plan.txt", "buy milk")
    pl, *_ = _places(home)
    assert "doesn't read it" in pl.read("downloads", "client_secret_123.json")
    assert "doesn't read it" in pl.read("downloads", "notes.txt")
    assert "buy milk" in pl.read("downloads", "plan.txt")


def test_trash_and_move_only_after_confirm(home):
    d = home["downloads"]
    _file(d / "old-setup.exe")
    _file(d / "dup.pdf", "same")
    _file(d / "dup (1).pdf", "same")
    trashed = []
    pl, acts, cards = _places(home, trashed=trashed)
    assert "dup.pdf = dup (1).pdf" in pl.duplicates("downloads") or "dup (1).pdf = dup.pdf" in pl.duplicates("downloads")
    pl.propose_trash("downloads", ["old-setup.exe", "dup (1).pdf"], "old installer and a copy")
    assert cards[-1]["kind"] == "pc_trash" and cards[-1]["details"]["count"] == 2 and trashed == []
    assert acts.confirm(cards[-1]["id"]).state == "done" and sorted(trashed) == ["dup (1).pdf", "old-setup.exe"]
    pl.propose_move("downloads", ["dup.pdf"], "Work", to_place="documents")
    assert acts.confirm(cards[-1]["id"]).state == "done"
    assert (home["documents"] / "Work" / "dup.pdf").exists() and not (d / "dup.pdf").exists()
    pl.propose_rename("documents", "Work/dup.pdf", "contract.pdf")
    acts.confirm(cards[-1]["id"])
    assert (home["documents"] / "Work" / "contract.pdf").exists()
    with pytest.raises(WorkError):
        pl.propose_rename("documents", "Work/contract.pdf", "run.bat")


@pytest.mark.skipif(os.name != "nt" or not os.getenv("LANTERNA_TEST_TRASH"),
                    reason="puts a file in the real Windows Recycle Bin: set LANTERNA_TEST_TRASH=1")
def test_windows_recycle_bin(tmp_path):
    p = _file(tmp_path / "lanterna-trash-test.txt", "bye")
    pcfiles.to_trash([p])
    assert not p.exists()


def test_freedesktop_trash(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    p = _file(tmp_path / "a.txt", "bye")
    pcfiles._trash_freedesktop(p)
    files = tmp_path / "share" / "Trash"
    assert not p.exists() and (files / "files" / "a.txt").read_text() == "bye"
    assert "Path=" in (files / "info" / "a.txt.trashinfo").read_text()


def test_xdg_user_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Scaricati"\n')
    assert pcfiles._xdg_folder("downloads") == Path.home() / "Scaricati"


# ---------------------------------------------------------------- programs
SEARCH = """\r   - \r   \\ \rName                               Id                        Version         Match
------------------------------------------------------------------------------------------
7-Zip                              7zip.7zip                 26.05           Moniker: 7zip
NanaZip                            M2Team.NanaZip            7.0.1882.0      Tag: 7zip
"""
SHOW = """Found 7-Zip [7zip.7zip]
Version: 26.05
Publisher: Igor Pavlov
Description: A file archiver with a high compression ratio.
Homepage: https://7-zip.org/download.html
License: LGPL-2.1
Tags:
  zip
"""
UPGRADE = """Name            Id                 Version  Available Source
-------------------------------------------------------------
VLC media player VideoLAN.VLC      3.0.21   3.0.24    winget
2 upgrades available.
"""


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, args, timeout=0):
        self.calls.append(args)
        if args[:2] == ["winget", "search"]:
            return 0, SEARCH
        if args[:2] == ["winget", "show"]:
            return (0, SHOW) if "7zip.7zip" in args else (-1978335212, "No package found")
        if args[:2] == ["winget", "upgrade"] and "--id" not in args:
            return 0, UPGRADE
        if args[:2] == ["winget", "install"]:
            return 0, "Successfully installed"
        return 1, "unexpected"


def test_winget_search_details_and_install_card():
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    run = FakeRunner()
    a = apps.Apps(acts, runner=run, platform="win32", which=lambda n: "C:/winget.exe" if n == "winget" else None)
    assert "7-Zip — id 7zip.7zip, version 26.05" in a.search("7zip")
    assert "VideoLAN.VLC: 3.0.21 → 3.0.24" in a.updates()
    a.propose("install", "7zip.7zip")
    c = cards[-1]
    assert c["kind"] == "app_install" and c["details"]["publisher"] == "Igor Pavlov"
    assert c["details"]["command"].startswith("winget install --id 7zip.7zip --exact")
    assert not any(x[:2] == ["winget", "install"] for x in run.calls)         # nothing ran before Confirm
    assert acts.confirm(c["id"]).state == "done"
    assert run.calls[-1][:5] == ["winget", "install", "--id", "7zip.7zip", "--exact"]
    with pytest.raises(WorkError):
        a.propose("install", "nope.Missing")
    for bad in ("--force", "a b", "x;rm -rf", ""):
        with pytest.raises(WorkError):
            a.propose("install", bad)


def test_linux_uses_flatpak_for_this_user():
    a = apps.Apps(Actions(), runner=lambda *a_, **k: (0, ""), platform="linux", which=lambda n: n if n in ("flatpak", "dnf") else None)
    assert a.managers() == ["flatpak", "dnf"]
    assert a.command("install", "org.videolan.VLC", "flatpak")[:4] == ["flatpak", "install", "--user", "-y"]
    assert a.command("install", "vlc", "dnf")[:2] == ["pkexec", "dnf"]


# ---------------------------------------------------------------- settings
class FakeReg:
    def __init__(self, data):
        self.data = data

    def get(self, hive, path, name):
        return self.data.get((hive, path), {}).get(name)

    def values(self, hive, path):
        return dict(self.data.get((hive, path), {}))

    def set(self, hive, path, name, value, kind):
        assert hive == "HKEY_CURRENT_USER"
        self.data.setdefault((hive, path), {})[name] = value


def test_windows_startup_theme_and_power(tmp_path):
    cu, lm = "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"
    reg = FakeReg({(cu, pcsys.RUN_KEY): {"Discord": "Update.exe --processStart Discord.exe", "Steam": "steam.exe -silent"},
                   (cu, pcsys.APPROVED + r"\Run"): {"Discord": b"\x03" + b"\0" * 11},
                   (lm, pcsys.RUN_KEY): {"SecurityHealth": "SecurityHealthSystray.exe"},
                   (cu, pcsys.PERSONALIZE): {"AppsUseLightTheme": 1}})
    plans = "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *\n" \
            "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\n"
    ran, opened = [], []

    def runner(args, timeout=0):
        ran.append(args)
        return (0, plans) if "powercfg /list" in " ".join(args) else (0, "")
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    s = pcsys.System(acts, runner=runner, platform_="win32", reg=reg, home=tmp_path, opener=opened.append)
    listing = s.startup()
    assert "ON   Steam" in listing and "off  Discord" in listing and "SecurityHealth (for all users" in listing
    s.propose_startup("Steam", False)
    assert reg.get(cu, pcsys.APPROVED + r"\Run", "Steam") is None              # not before Confirm
    acts.confirm(cards[-1]["id"])
    assert reg.get(cu, pcsys.APPROVED + r"\Run", "Steam")[:1] == b"\x03"
    s.propose_startup("Discord", True)
    acts.confirm(cards[-1]["id"])
    assert reg.get(cu, pcsys.APPROVED + r"\Run", "Discord")[:1] == b"\x02"
    assert "administrator" in s.propose_startup("SecurityHealth", False) and opened == ["ms-settings:startupapps"]
    s.propose_theme("dark")
    assert cards[-1]["details"]["was"] == "light"
    acts.confirm(cards[-1]["id"])
    assert reg.get(cu, pcsys.PERSONALIZE, "AppsUseLightTheme") == 0 and reg.get(cu, pcsys.PERSONALIZE, "SystemUsesLightTheme") == 0
    assert "(active) Balanced" in s.power()
    s.propose_power("High performance")
    acts.confirm(cards[-1]["id"])
    assert ran[-1] == ["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"]
    with pytest.raises(WorkError):
        s.propose_power("rm -rf /")
    with pytest.raises(WorkError):
        s.open_page("javascript:alert(1)")


def test_linux_autostart_off_and_on(tmp_path):
    auto = tmp_path / ".config" / "autostart"
    auto.mkdir(parents=True)
    (auto / "discord.desktop").write_text("[Desktop Entry]\nName=Discord\nExec=discord\n")
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    s = pcsys.System(acts, runner=lambda *a, **k: (0, ""), platform_="linux", home=tmp_path, which=lambda n: None)
    assert "ON   Discord" in s.startup()
    s.propose_startup("Discord", False)
    acts.confirm(cards[-1]["id"])
    assert "Hidden=true" in (auto / "discord.desktop").read_text() and "off  Discord" in s.startup()
    s.propose_startup("Discord", True)
    acts.confirm(cards[-1]["id"])
    assert "Hidden" not in (auto / "discord.desktop").read_text()


# ---------------------------------------------------------------- the app
def test_tools_only_when_the_talk_is_about_the_pc(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna.app import Api, action_title, card_text
    from lanterna.store import Store
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    names = lambda q: {s["function"]["name"] for s in api.toolbox.schemas(q)}   # noqa: E731
    assert not any(n.startswith(("pc_", "app_")) for n in names("what's the weather in Ferrara?"))
    assert "pc_sort" in names("відсортуй мені завантаження") and "app_install" in names("встанови vlc")
    assert "pc_load" in names("чому мій ПК гальмує?")
    api.save_settings({"pc_access": False})
    assert not any(n.startswith(("pc_", "app_")) for n in names("відсортуй мені завантаження"))
    d = {"place": "downloads", "count": 3, "groups": [{"to": "Документи", "count": 3, "files": ["a", "b", "c"]}], "skipped": 1}
    assert action_title("pc_sort", d, "", "uk") == "Розкласти 3 файлів у папці Завантаження"
    assert "Документи" in card_text("pc_sort", d, "uk")
    assert action_title("sys_theme", {"theme": "dark"}, "", "it") == "Passare al tema scuro"


def test_confirm_and_undo_through_the_app(tmp_path, monkeypatch, home):
    """The window's path: the card is confirmed through Api (not mistaken for a working-folder card) and undone."""
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path / "lh"))
    from lanterna.app import Api
    from lanterna.store import Store
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    api.save_settings({"lang": "uk"})
    api.places._folders = lambda: home
    _file(home["downloads"] / "a.pdf")
    _file(home["downloads"] / "b.jpg")
    tid, cards = api.new_thread()["id"], []
    api.actions.bind(cards, tid)
    api.toolbox.run("pc_sort", '{"place": "downloads"}')
    r = api.action_confirm(cards[-1]["id"])
    assert r["state"] == "done" and r["text"] == "Розкладено 2 файлів у папці Завантаження"
    assert (home["downloads"] / "Документи" / "a.pdf").exists()
    u = api.pc_undo(cards[-1]["details"]["undo"])
    assert u == {"ok": True, "text": "Файлів повернуто на місце: 2."} and (home["downloads"] / "a.pdf").exists()
    assert api.pc_undo(cards[-1]["details"]["undo"])["ok"] is False
