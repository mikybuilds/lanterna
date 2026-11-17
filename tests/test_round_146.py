"""Round 146 (1.1.10b8), from a real chat: "I can't tell where my gigabytes went, and Lanterna can't either".

What went wrong there, and what these tests hold:
- pc_disk counted only the profile (for 15 s) and what programs tell Windows, so it never saw the biggest things on
  that disk: a 69 GB Steam game in Program Files (x86), Visual Studio and its download cache, the NVIDIA shader cache,
  Windows itself, ProgramData, a Telegram folder right on C:. Now one walk counts every folder of the whole disk on
  several threads (links, junctions and OneDrive's online-only files take no space and aren't counted), and the
  report names the biggest folders by what they are, Steam's games by name and disk, the biggest files, kinds of
  files and what couldn't be counted. With folder, pc_disk looks inside one folder or another disk.
- The first count of a full disk can take minutes: pc_disk waits two, says what it has so far ("at least"), and the
  count goes on for the next question. The line that shows what Lanterna is doing shows how much is counted.
- A Steam game is removed by Steam's own Uninstall, on a card.
- "Зараз гляну…" written above what pc_disk had found counted as a promise of work: the answer was taken back and
  the model apologized for it. «Ти вже прибрав завантаження» (what the user did) counted as the model's claim.
"""
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import chat, diskmap, diskuse, i18n, thinking
from lanterna.chat import Conversation, Redo
from lanterna.diskmap import GB, MB, Game, Part
from lanterna.tools import READ_ONLY_TOOLS
from lanterna.workspace import WAITING, WorkError
from test_round_141 import _Router  # noqa: E402  (a pretend model that plays the given turns)
from test_round_144 import _api, _box  # noqa: E402  (an Api of its own; a toolbox that only notes the calls)

WIN = sys.platform == "win32"
R = os.path.abspath(os.sep)          # a disk's root: "C:\\" (the current disk) on Windows, "/" elsewhere
UI = Path(chat.__file__).parent / "ui"


@pytest.fixture(autouse=True)
def _no_walks():
    """Each test starts with no walks of earlier ones (pc_disk keeps finished walks for a few minutes)."""
    diskmap._walks.clear()
    yield
    diskmap._walks.clear()


def _file(p: Path, n: int) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)
    return p


def _link(link: Path, target: Path) -> None:
    """A junction on Windows (no rights needed, like AppData\\Application Data), a link elsewhere."""
    if WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


# ---------------------------------------------------------------- 1. one walk of the whole disk
def test_one_walk_counts_every_folder_once(tmp_path, monkeypatch):
    monkeypatch.setattr(diskmap, "MB", 1)                               # sizes in bytes: every file is "big"
    root = tmp_path / "disk"
    _file(root / "Games" / "game.bin", 5000)
    film = _file(root / "Users" / "olena" / "Videos" / "film.mp4", 3000)
    _file(root / "Users" / "olena" / "notes.txt", 100)
    _file(root / "pagefile.sys", 700)
    _link(root / "Users" / "olena" / "Application Data", root / "Users")   # points back up: walked, it never ends
    w = diskmap.Walk(str(root), workers=3).start()
    assert w.wait(10) and w.whole and not w.cut
    s = w.sizes()
    assert s[str(root)] == 8800 and w.files == 4 and w.counted == 8800     # the link counts nothing
    assert s[str(root / "Users")] == 3100 and s[str(root / "Users" / "olena" / "Videos")] == 3000
    assert str(root / "Users" / "olena" / "Application Data") not in s
    assert w.loose() == 700                                             # the files right in the root
    assert w.biggest()[0] == (5000, str(root / "Games" / "game.bin"))
    assert w.kind_sizes() == {"videos": {str(film.parent): 3000}}


def test_deep_folders_count_in_the_folder_above(tmp_path, monkeypatch):
    monkeypatch.setattr(diskmap, "DEPTH", 2)
    root = tmp_path / "d"
    _file(root / "a" / "b" / "c" / "d" / "x.bin", 400)
    w = diskmap.Walk(str(root)).start()
    assert w.wait(10)
    s = w.sizes()
    assert s[str(root / "a" / "b")] == 400 and str(root / "a" / "b" / "c") not in s
    asked = []
    size = diskmap.size_lookup(w, lambda p: asked.append(p) or (7, False))
    assert size(str(root / "a")) == (400, True) and not asked             # the walk knows it
    assert size(str(root / "a" / "none")) == (0, True)                  # walked: nothing is there
    assert size(str(root / "a" / "b" / "c")) == (7, False)              # deeper than the walk keeps sizes
    assert size(str(tmp_path / "elsewhere")) == (7, False) and len(asked) == 2   # not on the walked disk


def test_a_walk_that_takes_too_long_says_what_it_has(tmp_path):
    root = tmp_path / "d"
    _file(root / "a" / "x.bin", 100)
    ticks = iter([0.0, 0.0])                                            # the start, the root; then it is late
    w = diskmap.Walk(str(root), workers=1, now=lambda: next(ticks, 1000.0), longest=10).start()
    assert w.wait(10) and w.cut and not w.whole
    assert w.sizes() == {str(root): 0}                                  # only the root was read
    parts = diskmap.drive_parts(w, win=WIN, disk=diskmap.Disk(100 * GB, 90 * GB, 10 * GB), games=[])
    head = "\n".join(parts[0].lines)
    assert "Still counting (0 files, 0 B so far): the sizes below are at least these" in head
    assert "asked again in a minute or two, pc_disk shows the whole disk. Tell the user that" in head
    assert not parts[2].lines                                           # nothing is "not counted" yet


def test_a_finished_walk_answers_again_while_the_free_space_stays(tmp_path):
    _file(tmp_path / "a" / "x.bin", 100)
    free, made = [50 * GB], []

    def make(root, skip=()):
        made.append(diskmap.Walk(root, skip=skip, free=lambda r: free[0]))
        return made[-1]

    def walk(**kw):
        w = diskmap.walk(str(tmp_path), make=make, free=lambda r: free[0], **kw)
        assert w.wait(10)
        return w

    first = walk()
    assert walk() is first and len(made) == 1                           # the same disk: no second walk
    free[0] -= 600 * MB                                                 # something big came or went
    second = walk()
    assert second is not first and len(made) == 2
    assert walk(keep=-1) is not second                                  # too old
    going = diskmap.Walk(str(tmp_path))                                 # not started: it is still going on
    diskmap._walks[os.path.normcase(os.path.normpath(str(tmp_path)))] = going
    assert diskmap.walk(str(tmp_path), make=make) is going              # a second question waits for the same one


# ---------------------------------------------------------------- 2. what the big folders are
def test_what_the_big_folders_are():
    def win(rel):
        return diskmap.note(rel, diskmap.WIN_RULES)

    assert win("program files (x86)/steam/steamapps/common/counter-strike global offensive") == "a Steam game"
    assert win("steamlibrary/steamapps/common/stalker2") == "a Steam game"          # a library on another disk
    assert win("users/olena/appdata/local/nvidia").startswith("the NVIDIA driver's shader cache (DXCache)")
    assert win("programdata/microsoft/visualstudio").startswith("Visual Studio's download cache: Visual Studio "
                                                                "Installer → Modify")
    assert win("program files/microsoft visual studio").startswith("Visual Studio: the Visual Studio Installer")
    assert win("program files/some app") == "a program (app_uninstall removes it)"
    assert win("telegram").startswith("Telegram (its tdata folder")
    assert win("users/olena/appdata/roaming/telegram desktop/tdata").startswith("Telegram's files and cache")
    assert win("windows").startswith("Windows itself: leave it. WinSxS shares many files with System32")
    assert win("users/olena/downloads") == "the Downloads folder (the user's own files)"
    assert diskmap.note_up("users/olena/appdata/local/nvidia/dxcache/x.bin", diskmap.WIN_RULES).startswith("the NVIDIA")

    def linux(rel):
        return diskmap.note(rel, diskmap.LINUX_RULES)

    assert linux("home/olena/.cache/pip").startswith("a program's cache") and linux("var/log").startswith("logs")
    assert linux("home/olena/.local/share/steam/steamapps/common/dota 2 beta") == "a Steam game"
    assert diskmap.disk_of(r"E:\SteamLibrary\steamapps", True) == "E:\\" and diskmap.disk_of("/home/olena", False) == "/"


def _p(rel: str = "") -> str:
    """A folder of the pretend disk: _p("Users/olena") is C:\\Users\\olena (or /Users/olena)."""
    return os.path.join(R, *rel.split("/")) if rel else R


STEAM = "Program Files (x86)/Steam/steamapps/common"
CS = STEAM + "/Counter-Strike Global Offensive"
SIZES = {_p(rel): int(gb * GB) for gb, rel in [
    (300, ""), (60, "Users"), (60, "Users/olena"), (45, "Users/olena/AppData"), (45, "Users/olena/AppData/Local"),
    (16, "Users/olena/AppData/Local/NVIDIA"), (15, "Users/olena/AppData/Local/Google"),
    (14, "Users/olena/AppData/Local/Temp"), (8, "Users/olena/Downloads"), (7, "Users/olena/Videos"),
    (80, "Program Files (x86)"), (79.5, "Program Files (x86)/Steam"), (79.5, "Program Files (x86)/Steam/steamapps"),
    (79.5, STEAM), (68.9, CS), (10.6, STEAM + "/Other Game"),
    (51, "Windows"), (24, "Windows/WinSxS"), (16, "Windows/Installer"), (11, "Windows/System32"),
    (5, "Program Files"), (0.5, "Program Files/A"), (0.6, "Program Files/B")]}
BIG = [(9 * GB, _p("Users/olena/Downloads/movie.mkv")), (6 * GB, _p("Users/olena/AppData/Local/NVIDIA/DXCache/a.bin")),
       (5 * GB, _p("Users/olena/AppData/Local/NVIDIA/DXCache/b.bin")), (4 * GB, _p("pagefile.sys")),
       (3 * GB, _p(CS + "/game/csgo/pak01.vpk"))]
KINDS = {"videos": {_p("Users/olena/Downloads"): 9 * GB, _p("Users/olena/Videos"): 6 * GB},
         "installers and programs": {_p("Program Files (x86)/Steam"): 2 * GB}}
GAMES = [Game("730", "Counter-Strike 2", _p(CS), int(68.9 * GB))]
PERSONAL = [Path(_p("Users/olena/Downloads")), Path(_p("Users/olena/Videos"))]


class _Walk:
    """A finished walk of the pretend disk."""

    def __init__(self, sizes=None, *, whole=True, loose=7 * GB, online=0):
        self.root, self._sizes, self.whole, self.files = R, sizes or SIZES, whole, 1_234_567
        self._loose, self.online, self.skip, self.waited = loose, online, set(), []

    def wait(self, seconds):
        self.waited.append(seconds)
        return self.whole

    def sizes(self):
        return self._sizes

    def seconds(self):
        return 14.0

    def loose(self):
        return self._loose

    def biggest(self):
        return sorted(BIG, reverse=True)

    def kind_sizes(self):
        return KINDS


def test_the_biggest_folders_by_what_they_are():
    found = diskmap.units(SIZES, R, diskmap.WIN_RULES, R)
    assert [(os.path.basename(f), rest) for _, f, rest in found] == [
        ("Counter-Strike Global Offensive", False), ("Windows", False), ("NVIDIA", False), ("Google", False),
        ("Temp", False), ("Other Game", False), ("Downloads", False), ("Videos", False), ("Program Files", True)]


def test_the_report_of_the_whole_disk(monkeypatch):
    monkeypatch.setattr(diskmap, "other_disks", lambda root, win=WIN: [("E:\\", 1000 * GB, 200 * GB)])
    disk = diskmap.Disk(476 * GB, 456 * GB, 20 * GB)
    text = diskmap.fit(diskmap.drive_parts(_Walk(), win=True, disk=disk, games=GAMES, personal=PERSONAL,
                                           space_note="pc_space lists them"), 0, ())
    lines = text.splitlines()
    assert lines[:4] == [
        f"Disk {R} — 20.0 GB free of 476.0 GB — almost full; 456.0 GB used.",
        "Lanterna counted 300.0 GB of it in 1,234,567 files (14 s).",
        "In short: Program Files (x86) 80.0 GB · Users 60.0 GB · Windows 51.0 GB · Program Files 5.0 GB · files "
        f"right in {R} 7.0 GB (hiberfil.sys, pagefile.sys…)",
        "Other disks (not counted here; pc_disk with folder looks at one): E:\\ 200.0 GB free of 1000.0 GB"]
    i = lines.index("The biggest, by what they are (to look inside one: pc_disk with folder):")
    assert lines[i + 1] == f"- {_p(CS)} — 68.9 GB: the Steam game Counter-Strike 2"
    assert lines[i + 2] == (f"- {_p('Windows')} — 51.0 GB: {diskmap.note('windows', diskmap.WIN_RULES)} (inside: "
                            "WinSxS 24.0 GB, Installer 16.0 GB, System32 11.0 GB)")
    assert lines[i + 3].startswith(f"- {_p('Users/olena/AppData/Local/NVIDIA')} — 16.0 GB: the NVIDIA driver's")
    assert f"- {_p('Users/olena/AppData/Local/Temp')} — 14.0 GB: temporary files: Disk Cleanup removes them" in lines
    assert f"- {_p('Program Files')} — 5.0 GB in folders smaller than 1.0 GB each" in lines
    assert any(x.startswith("Not counted: about 156.0 GB — restore points") and "'System Protection'" in x for x in lines)
    i = lines.index("The biggest files:")                               # one file of a folder that is listed
    assert lines[i + 1].startswith(f"- 6.0 GB — {_p('Users/olena/AppData/Local/NVIDIA/DXCache/a.bin')}: the NVIDIA")
    assert lines[i + 2] == "(The names of 1 big file in the user's own folders aren't shown here: pc_space lists them)"
    assert "b.bin" not in text and "pagefile.sys —" not in text and "pak01.vpk" not in text
    i = lines.index("Kinds of files (outside Windows, programs and games):")
    assert lines[i + 1] == (f"- videos — 15.0 GB, most in {_p('Users/olena/Downloads')} 9.0 GB, "
                            f"{_p('Users/olena/Videos')} 6.0 GB")
    assert "installers" not in text                                     # the ones in Steam count as Steam
    shown = diskmap.fit(diskmap.drive_parts(_Walk(), win=True, disk=disk, games=GAMES, personal=PERSONAL,
                                            show_files=True), 0, ())
    assert f"- 9.0 GB — {_p('Users/olena/Downloads/movie.mkv')}: the Downloads folder" in shown   # Help is on


def test_steam_games_by_disk():
    on = r"C:\Program Files (x86)\Steam\steamapps\common"
    games = [Game("1643320", "S.T.A.L.K.E.R. 2", r"E:\SteamLibrary\steamapps\common\Stalker2", 174 * GB),
             Game("730", "Counter-Strike 2", on + r"\Counter-Strike Global Offensive", int(68.9 * GB)),
             Game("570", "Dota 2", r"D:\SteamLibrary\steamapps\common\dota 2 beta", 60 * GB),
             Game("440", "Team Fortress 2", r"D:\SteamLibrary\steamapps\common\Team Fortress 2", 30 * GB),
             Game("1", "Tiny", on + r"\Tiny", 200 * MB)]
    p = diskmap.game_part(games, disk="C:\\", win=True)
    assert p.title == ("Steam games on C:\\ (sizes from Steam; pc_game_remove opens Steam's Uninstall for one, on a "
                       "card):")
    assert p.lines == ["- Counter-Strike 2 — 68.9 GB", "- 1 more, 200.0 MB together",
                       "- on D:\\ (not this disk): 2 games, 90.0 GB (the biggest: Dota 2 60.0 GB, Team Fortress 2 "
                       "30.0 GB)",
                       "- on E:\\ (not this disk): 1 game, 174.0 GB (the biggest: S.T.A.L.K.E.R. 2 174.0 GB)"]
    every = diskmap.game_part(games, win=True)                          # pc_disk part "games": all of them
    assert every.lines[0] == "- S.T.A.L.K.E.R. 2 — 174.0 GB (E:\\)" and every.title.startswith("Steam games (sizes")


def test_steam_games_are_read_from_steams_own_files(tmp_path):
    base, lib = tmp_path / "Steam", tmp_path / "SteamLibrary"
    (base / "steamapps").mkdir(parents=True)
    (lib / "steamapps").mkdir(parents=True)

    def vdf(p):
        return str(p).replace("\\", "\\\\")                             # Steam writes C:\\Program Files (x86)\\Steam

    (base / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"' + vdf(base) + '"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"'
        + vdf(lib) + '"\n\t\t"apps"\n\t\t{\n\t\t\t"570"\t\t"60000000000"\n\t\t}\n\t}\n}\n', encoding="utf-8")
    (base / "steamapps" / "appmanifest_730.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"730"\n\t"name"\t\t"Counter-Strike 2"\n\t"installdir"\t\t"Counter-Strike Global '
        'Offensive"\n\t"SizeOnDisk"\t\t"73986228712"\n\t"UserConfig"\n\t{\n\t\t"name"\t\t"not the name"\n\t}\n}\n',
        encoding="utf-8")
    (lib / "steamapps" / "appmanifest_570.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"570"\n\t"name"\t\t"Dota 2"\n\t"installdir"\t\t"dota 2 beta"\n\t"SizeOnDisk"'
        '\t\t"60000000000"\n}\n', encoding="utf-8")
    (lib / "steamapps" / "appmanifest_x.acf").write_text('"AppState" { "name" "no number" }', encoding="utf-8")
    games = diskmap.steam_games(base, win=WIN)
    assert [(g.appid, g.name, g.size) for g in games] == [("730", "Counter-Strike 2", 73986228712),
                                                          ("570", "Dota 2", 60000000000)]
    assert games[0].folder == str(base / "steamapps" / "common" / "Counter-Strike Global Offensive")
    assert games[1].folder == str(lib / "steamapps" / "common" / "dota 2 beta")
    assert diskmap.steam_games(tmp_path / "no steam", win=WIN) == []


def test_the_report_fits_and_the_least_needed_lines_go_first():
    def parts():
        return [Part("head", ["Disk C:\\ — 2.0 GB free of 476.0 GB"], keep=99),
                Part("units", [f"- unit {i}" for i in range(10)], "The biggest:", keep=3),
                Part("kinds", [f"- kind {i}" for i in range(5)], "Kinds:")]

    whole = diskmap.fit(parts(), 0, ("kinds", "units"))
    assert whole.count("\n") == 17 and "- kind 4" in whole
    out = diskmap.fit(parts(), 80, ("kinds", "units"))
    assert len(out) <= 80 and "Kinds:" not in out                       # a title goes with its last line
    assert out.startswith("Disk C:\\") and "- unit 0" in out and out.count("- unit") >= 3
    tiny = diskmap.fit(parts(), 30, ("kinds", "units"))
    assert len(tiny) == 30 and tiny.endswith("…")                       # what has to stay is cut at the end


# ---------------------------------------------------------------- 3. pc_disk itself
def _disk_usage(monkeypatch):
    monkeypatch.setattr(diskmap, "other_disks", lambda root, win=WIN: [])
    monkeypatch.setattr(diskuse.shutil, "disk_usage",
                        lambda p: SimpleNamespace(total=476 * GB, used=456 * GB, free=20 * GB))


def test_pc_disk_counts_the_whole_disk(monkeypatch):
    _disk_usage(monkeypatch)
    w, seen = _Walk(), []

    def walker(root, skip=()):
        seen.append((root, tuple(skip)))
        return w

    out = diskuse.report("drive", home=Path(_p("Users/olena")), root=R, platform="win32", walker=walker, wait=5,
                         games=lambda: GAMES, personal=lambda: PERSONAL, limit=3800)
    assert seen == [(R, ())] and 0 < w.waited[0] <= 5
    lines = out.splitlines()
    assert lines[0] == "What takes up the disk (only looked, nothing changed):"
    assert lines[1] == f"Disk {R} — 20.0 GB free of 476.0 GB — almost full; 456.0 GB used."
    assert f"- {_p(CS)} — 68.9 GB: the Steam game Counter-Strike 2" in lines and len(out) <= 3800
    assert "Biggest folders of the profile" not in out                  # the walk has it all
    short = diskuse.report("drive", home=Path(_p("Users/olena")), root=R, platform="win32", walker=walker,
                           wait=5, games=lambda: GAMES, personal=lambda: PERSONAL, limit=900)
    assert len(short) <= 900 and "In short:" in short and "Counter-Strike 2" in short
    diskuse.report("drive", home=Path(_p("Users/olena")), root=R, platform="linux", walker=walker, wait=5,
                   games=lambda: [], personal=lambda: [])
    assert seen[-1] == (R, diskmap.LINUX_SKIP)                          # /proc, /sys… are no files on a disk


def test_every_part_of_pc_disk_in_its_place(monkeypatch):
    _disk_usage(monkeypatch)
    monkeypatch.setattr(diskuse, "win_system", lambda counter, measure=None: [
        "Windows' own files:", f"- Windows update downloads — {diskuse._sized(*measure(_p('Windows/Installer')))}"])
    monkeypatch.setattr(diskuse, "trash_size", lambda: 2 * GB)
    monkeypatch.setattr(diskuse.tempfile, "gettempdir", lambda: _p("Users/olena/AppData/Local/Temp"))
    out = diskuse.report("", home=Path(_p("Users/olena")), root=R, platform=sys.platform, walker=lambda r, skip=(): _Walk(),
                         wait=5, games=lambda: GAMES, personal=lambda: PERSONAL, installed=lambda: [],
                         running=lambda: "0.9", programs=lambda: [(13 * GB, "Visual Studio Community 2026")],
                         run=lambda args, timeout=0: (1, ""))
    at = [out.index(s) for s in ("Lanterna counted 300.0 GB", "The biggest, by what they are", "Not counted: about",
                                 f"Steam games on {R}", "Recycle Bin: 2.0 GB; temporary files: 14.0 GB.",
                                 "Ollama models: none downloaded.", "The biggest files:", "Kinds of files")]
    assert at == sorted(at)                                             # the walk's sizes for Temp too
    if WIN:
        assert "- Windows update downloads — 16.0 GB" in out and out.index("Kinds of files") < out.index(
            "- Visual Studio Community 2026 — 13.0 GB")
    assert "(Counting stopped to save time" not in out


def test_pc_disk_says_when_it_is_still_counting(monkeypatch):
    _disk_usage(monkeypatch)
    out = diskuse.report("drive", home=Path(_p("Users/olena")), root=R, platform=sys.platform,
                         walker=lambda r, skip=(): _Walk(whole=False), wait=0.01, games=lambda: [],
                         personal=lambda: [])
    assert "Still counting (1,234,567 files, 300.0 GB so far)" in out and "Not counted" not in out


def test_pc_disk_looks_inside_a_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(diskmap, "MB", 1)
    common = tmp_path / "Steam" / "steamapps" / "common"
    _file(common / "Counter-Strike Global Offensive" / "game" / "pak01.vpk", 5000)
    _file(common / "Tiny" / "tiny.exe", 2000)
    _file(common / "readme.txt", 50)
    games = [Game("730", "Counter-Strike 2", str(common / "Counter-Strike Global Offensive"), 5000)]
    out = diskuse.report(folder=str(common), home=tmp_path, platform=sys.platform, games=lambda: games,
                         personal=lambda: [], wait=10)
    lines = out.splitlines()
    assert lines[0].startswith(f"{common} — 6.9 KB in 3 files (only looked, nothing changed)")
    assert lines[1:4] == ["Folders in it:", "- Counter-Strike Global Offensive — 4.9 KB: the Steam game Counter-Strike 2",
                          "- Tiny — 2.0 KB: a Steam game"]
    i = lines.index("The biggest files in it:")
    assert lines[i + 1] == f"- 4.9 KB — {os.path.join('Counter-Strike Global Offensive', 'game', 'pak01.vpk')}"
    assert "- installers and programs — 2.0 KB" in lines
    assert diskmap.folder_path("AppData/Local", tmp_path) == tmp_path / "AppData" / "Local"
    if WIN:
        assert diskmap.folder_path("D:", tmp_path) == Path("D:\\") and diskmap.folder_path('"E:\\"', tmp_path) == Path("E:\\")
    with pytest.raises(WorkError, match="There is no folder 'Nope' on this computer. folder is a whole path like"):
        diskuse.report(folder="Nope", home=tmp_path, platform=sys.platform)


def test_names_in_the_users_own_folders_wait_for_help_free_up_space(tmp_path, monkeypatch):
    monkeypatch.setattr(diskmap, "MB", 1)
    downloads = tmp_path / "Downloads"
    _file(downloads / "Old games" / "setup.exe", 5000)
    _file(downloads / "film.mkv", 3000)
    args = dict(folder=str(downloads), home=tmp_path, platform=sys.platform, games=lambda: [],
                personal=lambda: [downloads], wait=10)
    off = diskuse.report(space_help=False, **args)
    assert ("It is one of the user's own folders: the names in it aren't shown here (with Help free up disk space on "
            "(pc_space_on offers it on a card), pc_space lists them).") in off
    assert "Old games" not in off and "film" not in off and "- videos — 2.9 KB" in off
    on = diskuse.report(space_help=True, **args)
    assert "- Old games — 4.9 KB" in on and "film.mkv" in on


def test_pc_disk_is_offered_with_folder_and_only_looks(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tools = {t.name: t for t in api._disk_tools()}
    assert {"pc_disk", "pc_game_remove", "pc_model_remove"} <= set(tools)
    params = tools["pc_disk"].parameters["properties"]
    assert set(params) == {"part", "folder"} and "drive" in params["part"]["enum"]
    assert "pc_disk" in READ_ONLY_TOOLS and "pc_game_remove" not in READ_ONLY_TOOLS
    assert "pc_disk with folder looks inside one" in chat.PC_GUIDE
    assert thinking.tool_step("pc_game_remove", '{"name": "Dota 2"}', "uk") == "Готую прибирання гри Dota 2"


# ---------------------------------------------------------------- 4. a game goes with Steam's own Uninstall
def test_removing_a_steam_game_is_a_card(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    games = [Game("730", "Counter-Strike 2", r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global "
                                             "Offensive", int(68.9 * GB)),
             Game("570", "Dota 2", r"D:\SteamLibrary\steamapps\common\dota 2 beta", 60 * GB),
             Game("440", "Team Fortress 2", r"D:\SteamLibrary\steamapps\common\Team Fortress 2", 30 * GB)]
    opened = []
    out = api._game_remove("counter", games=games, open_url=lambda u: opened.append(u) or True)
    assert out == WAITING + " After Confirm, Steam asks the user once more and removes the game itself." and not opened
    card = list(api.actions.items.values())[-1]
    assert card.kind == "game_remove" and card.details == {"name": "Counter-Strike 2", "size": "68.9 GB",
                                                           "appid": "730", "disk": "C:\\" if WIN else "/"}
    with pytest.raises(WorkError, match="A card to remove Counter-Strike 2 already waits"):
        api._game_remove("Counter-Strike 2", games=games)
    with pytest.raises(WorkError, match="Several games match: Dota 2, Team Fortress 2"):
        api._game_remove("2", games=games[1:])
    with pytest.raises(WorkError, match="Steam has no game called Minecraft. It has: Counter-Strike 2, Dota 2"):
        api._game_remove("Minecraft", games=games)
    with pytest.raises(WorkError, match="Steam isn't installed here"):
        api._game_remove("Dota 2", games=[])
    done = api.actions.confirm(card.id)
    assert done.state == "done" and opened == ["steam://uninstall/730"]
    from lanterna.app import action_title, card_text
    assert action_title("game_remove", card.details, "", "uk") == "Прибрати гру Counter-Strike 2 (Steam)"
    assert action_title("game_remove", card.details, "", "uk", done=True) == "Відкрито Steam, щоб прибрати Counter-Strike 2"
    assert ("Steam перепитає ще раз і сам прибере гру: звільниться близько 68.9 GB. Пізніше Steam може завантажити її "
            "знову.") in card_text("game_remove", card.details, "uk")


def test_steam_that_doesnt_open_is_said(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api._game_remove("Dota 2", games=[Game("570", "Dota 2", "", 60 * GB)], open_url=lambda u: False)
    done = api.actions.confirm(list(api.actions.items.values())[-1].id)
    assert done.state == "failed" and "Steam didn't open." in done.result


# ---------------------------------------------------------------- 5. "Зараз гляну…" above what it found
def test_a_reply_that_looked_may_say_it_looks():
    claim = chat.claim_phrase
    said = "Зараз гляну, що займає місце.\n\nОсь що я знайшов: Counter-Strike 2 — 68.9 GB."
    assert claim(said, ["pc_disk"]) == "" and chat.false_claim(said, ["pc_disk"]) == ""
    assert claim("Зараз гляну, що займає місце.", []) == "Зараз гляну"           # with nothing looked at: a promise
    assert claim("Тепер подивлюся глибше в AppData.", []) == "Тепер подивлюся"
    assert chat.claims_action("Зараз гляну, що займає місце.")
    r = _Router([[("pc_disk", {})], said])
    conv = Conversation(router=r, toolbox=_box("pc_disk", "pc_move"), lang="uk")
    out = list(conv.ask("куди поділося місце на диску?"))
    assert not any(isinstance(p, Redo) for p in out) and len(r.seen) == 2     # no second request for it
    assert conv.last_reply.startswith("Зараз гляну") and "⚠️" not in conv.last_reply
    r = _Router(["Зараз гляну, що займає місце.", "Ось що займає місце."])
    out = list(Conversation(router=r, toolbox=_box("pc_disk", "pc_move"), lang="uk").ask("куди поділося місце?"))
    assert any(isinstance(p, Redo) and p.said == "Зараз гляну" for p in out)


def test_what_the_user_did_is_not_the_models_claim():
    claim = chat.claim_phrase
    assert claim("Ти вже прибрав завантаження, молодець!", []) == ""
    assert claim("Вона вже прибрала файли з робочого столу.", []) == ""
    assert claim("Я прибрав завантаження.", []) == "прибрав завантаження"
    assert claim("Готово, я прибрала файли з робочого столу.", []).startswith("прибрала файли")


def test_a_reply_written_again_doesnt_apologize():
    for note in (chat.REDO_NOTE, chat.FAILED_NOTE):
        assert note.endswith("Your new reply takes the place of that one: don't apologize for it or mention this "
                             "check.]")


# ---------------------------------------------------------------- 6. old restore points, and what is counted
def test_system_protection_opens_though_it_asks_for_administrator_rights():
    from lanterna.pccontrol import WIN_BUILTIN, Launcher
    assert WIN_BUILTIN["system protection"] == "SystemPropertiesProtection.exe"
    started = []
    launcher = Launcher(platform_="win32", spawn=lambda args: False, startfile=started.append, app_dirs=[])
    assert launcher.open_program("system protection") == "Opened System Protection."
    assert started == ["SystemPropertiesProtection.exe"]

    def refused(path):
        raise OSError("The operation was canceled by the user.")

    with pytest.raises(WorkError, match="System Protection didn't start."):
        Launcher(platform_="win32", spawn=lambda args: False, startfile=refused, app_dirs=[]).open_program(
            "system protection")


def test_the_line_shows_what_pc_disk_has_counted(tmp_path, monkeypatch):
    from lanterna.app import _counted, _Stream
    st = _Stream("uk")
    assert _counted(st, now=100.0) == "" and diskmap.counting() is None     # nothing is counted now
    w = diskmap.Walk(str(tmp_path))                                     # not started: it is "going on"
    w.files, w.counted = 412_000, 120 * GB
    diskmap._walks["x"] = w
    assert diskmap.counting() == (412_000, 120 * GB)
    assert _counted(st, now=200.0) == " — пораховано: 120.0 GB, файлів: 412 000"
    w.files = 500_000
    assert _counted(st, now=201.0).endswith("412 000")                  # read again every 2 s, not every poll
    assert _counted(st, now=202.5).endswith("500 000")
    api = _api(tmp_path, monkeypatch)
    api._streams["s"] = live = _Stream("uk")
    live.steps.tool("pc_disk", "{}")
    p = api.poll("s")
    assert p["live"] == "Дивлюсь, що займає диск — пораховано: 120.0 GB, файлів: 500 000"
    live.steps.thought("**Що займає місце**\n")                         # the model goes on: no count in its line
    assert api.poll("s")["live"] == "Що займає місце"


def test_every_new_string_is_translated():
    from lanterna.app import COUNTED, GAME_TEXT
    new = ["Remove the game {name} (Steam)", "Opened Steam to remove {name}", GAME_TEXT,
           "Preparing to remove the game {x}", COUNTED]
    for s in new:
        assert set(i18n._T[s]) >= {"uk", "it"}, s
        for lang in i18n.LANGS:
            said = i18n.t(s, lang)
            assert said and sorted(re.findall(r"\{\w+\}", said)) == sorted(re.findall(r"\{\w+\}", s)), (lang, s)
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'game_remove: "Remove the game {name} (Steam)"' in js and f't("{GAME_TEXT}", {{ s: d.size || "" }})' in js
    assert 'k === "model_remove" || k === "game_remove" ? "🗑"' in js
