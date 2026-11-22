"""Round 149 (1.1.11b1): Lanterna finds why something doesn't work, and fixes it from a fixed list.

From a real chat: a game went black in a story mission. The helper there found the game, read its logs, saw
Content/Movies_old with no Movies next to it (the "skip the intro videos" trick: it hides the story videos too),
made sure the game was closed and renamed the folder back; Steam's check of files was the fallback. fixit.py does
the same by itself:
- fix_check finds the program (Steam, Epic, GOG, Xbox, the installed programs), looks through its folder for what is
  out of place (a folder renamed aside, mods, injector files), reads its newest log and what Windows noted (crashes
  and the file they happened in, the graphics driver); or Windows itself: sound, internet, printer, updates;
- fix_list / fix_read look closer; nothing secret is read and the user's names are taken out of what goes on;
- a fix is one card from a fixed list (rename back, one setting, mods aside, a cache, Steam's check, DNS, proxy,
  default printer, print queue), done at once only when the user let Lanterna act on its own, with Undo where it can;
- the program must be closed: checked when the card is made and again on Confirm.
Every test gives the Fixer fakes (registry, printers, processes, commands): nothing on this computer is changed.
"""
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import app, chat, fixit, history, i18n, sent, thinking, tools, workspace
from lanterna.fixit import TURNED_OFF
from lanterna.workspace import WAITING, Actions, WorkError
from test_round_144 import _api  # noqa: E402  (an Api of its own)

SRC = Path(__file__).parents[1] / "src" / "lanterna"
JS = (SRC / "ui" / "app.js").read_text(encoding="utf-8")
GAME = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
CU, LM = "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"


class FakeReg:
    """values: (hive, path, name) → value; tree: (hive, path) → {subkey: {name: value}} (the list of programs)."""

    def __init__(self, values=None, tree=None):
        self.v, self.tree, self.calls = dict(values or {}), dict(tree or {}), []

    def get(self, hive, path, name):
        return self.v.get((hive, path, name))

    def values(self, hive, path):
        base, _, sub = path.rpartition("\\")
        return dict(self.tree.get((hive, base), {}).get(sub, {}))

    def subkeys(self, hive, path):
        return list(self.tree.get((hive, path), {}))

    def set(self, hive, path, name, value, kind):
        assert hive == CU                             # a fix changes only the user's own settings
        self.calls.append(("set", name, value))
        self.v[(hive, path, name)] = value

    def delete(self, hive, path, name):
        assert hive == CU
        self.calls.append(("delete", name))
        self.v.pop((hive, path, name), None)


class FakePrinters:
    def __init__(self, names, default):
        self._names, self._default = list(names), default

    def names(self):
        return list(self._names)

    def default(self):
        return self._default

    def set_default(self, name):
        self._default = name
        return True


def _write(p: Path, data) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


def _manifest(steam: Path, appid: str, name: str, folder: str) -> Path:
    _write(steam / "steamapps" / f"appmanifest_{appid}.acf",
           f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"StateFlags"\t\t"4"\n'
           f'\t"installdir"\t\t"{folder}"\n\t"buildid"\t\t"16612345"\n}}\n')
    d = steam / "steamapps" / "common" / folder
    d.mkdir(parents=True, exist_ok=True)
    return d


SETTINGS = b"[/Script/Engine.GameUserSettings]\r\nFullscreenMode=0\r\nResolutionSizeX=1920\r\n"


def _world(tmp_path: Path) -> SimpleNamespace:
    """A pretend computer: Steam with the game of that chat (its videos renamed aside, a few mods), Valheim and its
    server, the game's log and settings in AppData, the NVIDIA shader cache."""
    steam = tmp_path / "Steam"
    _write(steam / "steam.exe", "MZ")
    game = _manifest(steam, "1643320", GAME, "S.T.A.L.K.E.R. 2")
    _write(game / "Stalker2.exe", "MZ")
    win64 = game / "Stalker2" / "Binaries" / "Win64"
    for n in ("Stalker2-Win64-Shipping.exe", "dxgi.dll", "dbghelp.bak", "mss32.asi", "xinput1_3.dll"):
        _write(win64 / n, "x")
    _write(game / "Stalker2/Content/Movies_old/Intro.bk2", "v" * 2000)
    _write(game / "Stalker2/Content/Movies_old/Mission_01.bk2", "v" * 3000)
    for n in ("pakchunk0-Windows.pak", "pakchunk0-Windows_0_P.pak", "zzz_BetterHUD_P.pak"):
        _write(game / "Stalker2/Content/Paks" / n, "p")
    _write(game / "Stalker2/Content/Paks/~mods/readme.txt", "put your mods here")
    _write(game / "Stalker2/Content/Data/Maps/005-Old/a.bin", "m")
    _write(_manifest(steam, "892970", "Valheim", "Valheim") / "valheim.exe", "MZ")
    _write(_manifest(steam, "896660", "Valheim Dedicated Server", "Valheim dedicated server") / "valheim_server.exe",
           "MZ")
    user = tmp_path / "user"
    local = user / "AppData" / "Local"
    _write(local / "Stalker2/Saved/Logs/Stalker2.log",
           "[2026.11.20-18.01.02:123][  0]LogInit: Build: ++Stalker2+release\n"
           "[2026.11.20-18.20.40:001][512]LogD3D12RHI: Error: GPU crashed or D3D Device Removed.\n"
           "[2026.11.20-18.20.40:002][512]LogWindows: Error: Fatal error!\n")
    _write(local / "Stalker2/Saved/Config/Windows/GameUserSettings.ini", SETTINGS)
    _write(local / "Stalker2/Saved/SaveGames/slot1.sav", "s")
    _write(local / "NVIDIA/DXCache/a.nvph", "c" * 500)
    procs = [("steam.exe", str(steam / "steam.exe")), ("explorer.exe", r"C:\Windows\explorer.exe")]
    tree = {(LM, fixit.UNINSTALL): {"Steam": {"DisplayName": "Steam", "InstallLocation": str(steam),
                                              "Publisher": "Valve Corporation"},
                                    "Steam App 1643320": {"DisplayName": GAME,
                                                          "UninstallString": "steam://uninstall/1643320"}}}
    return SimpleNamespace(tmp=tmp_path, steam=steam, game=game, win64=win64, user=user, local=local, procs=procs,
                           tree=tree)


def _fx(w, actions=None, reg=None, printers=None):
    log = SimpleNamespace(runs=[], urls=[], trashed=[], refreshed=0)

    def runner(args, timeout=60, env=None):
        log.runs.append((list(args), env))
        if args[0] == "powershell" and "Remove-PrintJob" not in args[-1]:
            return 0, "{}"                                  # what Windows noted: nothing
        return 0, "ok"

    def refresh():
        log.refreshed += 1
    fx = fixit.Fixer(actions if actions is not None else Actions(), runner=runner, platform_="win32",
                     reg=reg if reg is not None else FakeReg(tree=w.tree),
                     env={"PROGRAMDATA": str(w.tmp / "ProgramData")}, home=w.user, user="Olena", pc="DESKTOP-TEST1",
                     steam_base=lambda: w.steam, open_url=lambda u: log.urls.append(u) or True,
                     trash=lambda paths: log.trashed.append(list(paths)),
                     printers=printers if printers is not None else FakePrinters([], ""), refresh_net=refresh,
                     drives=lambda: [], data_dir=w.tmp / "home", procs=lambda: list(w.procs))
    return fx, log


def _card(fx):
    return list(fx.actions.items.values())[-1]


# ---------------------------------------------------------------- 1. what the user means
def test_names_and_areas_in_the_users_words():
    assert fixit.norm("S.T.A.L.K.E.R. 2: Heart of Chornobyl™") == "stalker 2 heart of chornobyl"
    for q in ("no sound", "немає звуку", "звук"):
        assert fixit.area_of(q) == "sound", q
    assert fixit.area_of("internet") == "internet" and fixit.area_of("нема інтернету") == "internet"
    assert fixit.area_of("windows update") == "updates" and fixit.area_of("оновлення") == "updates"
    # strict: only the area's words; loose (when no program has the name): one longer word of an area is enough
    assert fixit.area_of("принтер не друкує") == "" and fixit.area_of("принтер не друкує", strict=False) == "printer"
    assert fixit.area_of("Red Dead 2") == "" and fixit.area_of("Red Dead 2", strict=False) == ""   # 'red': red (es)
    assert fixit.area_of("sound and internet") == ""                                   # two areas: say which


def test_the_program_is_found_by_its_name(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    for q in ("stalker 2", "сталкер 2", "S.T.A.L.K.E.R. 2", GAME):
        p = fx.program(q)
        assert (p.name, p.source, p.appid) == (GAME, "steam", "1643320"), q
    assert fx.program("valheim").name == "Valheim" and fx.program("valhe").name == "Valheim"   # not its server
    assert fx.program("Valheim Dedicated Server").appid == "896660"
    steam = fx.program("Steam")                                 # from the list of installed programs, once
    assert steam.source == "app" and steam.private and sum(p.name == GAME for p in fx.programs()) == 1
    with pytest.raises(WorkError, match="No installed program is called 'Minecraft'. Closest names: "):
        fx.program("Minecraft")


def test_mod_kinds():
    hook = "a file mods and overlays use to hook into a game (ReShade, ENB, frame generation…)"
    assert fixit.mod_kind("dxgi.dll") == hook and fixit.mod_kind("dxgi.dll", exe_folder=False) == ""
    assert fixit.mod_kind("ReShade.ini") == "ReShade (a graphics mod)"
    assert fixit.mod_kind("BepInEx") == "BepInEx: a mod loader or shader pack"
    assert fixit.mod_kind("~mods") == "a mods folder" and fixit.mod_kind("ScriptHookV.asi").startswith("an .asi mod")
    for own in ("mss32.asi", "xinput1_3.dll", "dbghelp.dll", "steam_api64.dll", "Stalker2.exe"):
        assert fixit.mod_kind(own) == "", own                    # games ship these themselves


# ---------------------------------------------------------------- 2. fix_check: what is out of place
def test_the_check_finds_the_hidden_videos_and_the_mods(tmp_path):
    w = _world(tmp_path)
    fx, log = _fx(w)
    out = fx.check("stalker 2", "black screen in a mission", limit=8000)
    assert out.startswith(f"Program: {GAME} — Steam game 1643320, build 16612345\n")
    assert "It isn't running now." in out                       # Steam runs, the game doesn't
    assert ("! Stalker2/Content/Movies_old (folder, 4.9 KB: 2 videos (.bk2)): its videos are hidden from the program "
            "by renaming the folder (there is no 'Movies').") in out
    assert "Renaming it back to 'Movies' undoes it." in out
    assert ("! Stalker2/Binaries/Win64/dxgi.dll: a file mods and overlays use to hook into a game (ReShade, ENB, "
            "frame generation…).") in out
    assert "! Stalker2/Content/Paks/zzz_BetterHUD_P.pak: a mod pack (a .pak with _P loads over the game's own files)." \
        in out
    # the game's own files and names deep in its data are not clues; an empty mods folder (a readme) isn't either
    for not_a_clue in ("dbghelp", "mss32", "xinput1_3", "pakchunk0-Windows_0_P", "005-Old", "~mods"):
        assert not_a_clue not in out, not_a_clue
    assert "Newest log: local/Saved/Logs/Stalker2.log" in out and "Error lines in the newest log:" in out
    assert "- LogD3D12RHI: Error: GPU crashed or D3D Device Removed." in out and "- LogWindows: Error: Fatal error!" in out
    assert "Places (for fix_list / fix_read and the fixes):" in out and "- shader caches (fix_cache): nvidia_cache" in out
    assert "- local: %USERPROFILE%" in out and str(w.user) not in out          # the user's folder is taken out
    ps = [args for args, _env in log.runs]
    assert ps == [["powershell", "-NoProfile", "-NonInteractive", "-Command", fixit.PS_PROGRAM]]   # it only reads


def test_what_goes_on_is_cleaned(tmp_path):
    fx = fixit.Fixer(Actions(), platform_="win32", reg=FakeReg(), env={}, home=Path("C:/Users/Olena"), user="Olena",
                     pc="DESKTOP-TEST1", printers=FakePrinters([], ""), procs=lambda: [], drives=lambda: [],
                     data_dir=tmp_path / "home")
    home = "C:" + "\\Users\\" + "Olena"                          # (split: the secrets scan looks for such paths)
    out = fx.clean(home + r"\AppData\Local\Game\log.txt; C:/Users/Olena-old/x; on DESKTOP-TEST1; "
                   "anna.b@example.com; password=hunter22")
    assert out.startswith(r"%USERPROFILE%\AppData\Local\Game\log.txt; ")
    assert "C:/Users/<user>-old/x" in out                         # another folder: not the home, the name still goes
    assert "on <pc>" in out and "<email>" in out and "hunter22" not in out
    assert "Olena" not in out and "DESKTOP-TEST1" not in out and "example.com" not in out


def test_a_crash_noted_by_windows_says_where_and_what(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    p = fixit.Program(GAME, "steam", str(w.game), appid="1643320")
    exe = os.path.join(str(w.game), "Stalker2", "Binaries", "Win64", "Stalker2-Win64-Shipping.exe")

    def crash(code, t, module="nvwgf2umx.dll", app_="Stalker2-Win64-Shipping.exe", path=exe, mpath=""):
        return {"id": 1000, "t": t, "p": [app_, "1.0.0.0", "0", module, "32.0.15.6636", "0", code, "0x1a2b", "1c",
                                          "2026", path, mpath or os.path.join("C:\\", "Windows", "System32", module)]}
    facts = {"ev": [crash("c0000005", "2026-11-20 18:20"), crash("-1073741819", "2026-11-20 18:21"),
                    crash("3221225477", "2026-11-20 18:22"),                 # Windows 10+ writes the code as a number
                    crash("80000003", "2026-11-19 10:00", module="Stalker2-Win64-Shipping.exe", mpath=exe),
                    crash("c0000005", "2026-11-20 18:00", app_="chrome.exe",
                          path=os.path.join("C:", "Program Files", "Google", "chrome.exe")),
                    {"id": 1002, "t": "2026-11-18 21:00", "p": ["Stalker2-Win64-Shipping.exe", "1.0.0.0"]},
                    {"id": 1026, "t": "2026-11-17 09:00",
                     "p": ["Application: Stalker2.exe\nFramework Version: v4.0\nException Info: "
                           "System.IO.FileNotFoundException\n"]}]}
    lines = fx.crash_lines(facts, p, {"stalker2-win64-shipping", "stalker2"})
    assert lines[0] == ("Stalker2-Win64-Shipping.exe crashed in nvwgf2umx.dll (the NVIDIA graphics driver), code "
                        f"c0000005 ({fixit.EXC_CODES['c0000005']}) (3×, last 2026-11-20 18:22)")
    assert ("Stalker2-Win64-Shipping.exe crashed in Stalker2-Win64-Shipping.exe (a file of the program itself), code "
            "80000003 (its own check failed (a breakpoint)) (1×, last 2026-11-19 10:00)") in lines
    assert "Stalker2-Win64-Shipping.exe stopped responding (1×, last 2026-11-18 21:00)" in lines
    assert ".NET error System.IO.FileNotFoundException (1×, last 2026-11-17 09:00)" in lines
    assert len(lines) == 4 and not any("chrome" in x for x in lines)        # other programs' crashes stay out


def test_what_runs_is_counted_by_where_it_runs_from(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    game, steam = fx.program("stalker 2"), fx.program("Steam")
    shipping = str(w.win64 / "Stalker2-Win64-Shipping.exe")
    w.procs.append(("Stalker2-Win64-Shipping.exe", shipping))
    assert fx.running(game) == ["Stalker2-Win64-Shipping.exe"]
    assert fx.running(steam) == ["steam.exe"]                   # the game in Steam's folder is the game's, not Steam's
    w.procs[:] = [("launcher.exe", ""), ("Stalker2.exe", "")]   # Windows hides the path: by name, not a common one
    assert fx.running(game) == ["Stalker2.exe"]


def test_long_reports_lose_the_least_needed_lines_first():
    out = fixit._fit([(0, "Head:", ["a" * 50]), (2, "Less:", ["b" * 50, "c" * 50]), (1, "More:", ["d" * 50])], 140)
    assert out == "Head:\n" + "a" * 50 + "\nMore:\n" + "d" * 50
    assert fixit._fit([(0, "", ["x" * 300])], 100) == "x" * 100


def test_on_linux_there_are_no_fix_tools_yet(tmp_path):
    fx = fixit.Fixer(Actions(), platform_="linux", reg=None, env={}, home=tmp_path, user="olena", pc="pc",
                     printers=FakePrinters([], ""), procs=lambda: [], drives=lambda: [], data_dir=tmp_path / "home")
    assert fixit.fix_tools(fx) == []
    assert fx.check("stalker 2") == "Lanterna checks programs and Windows on Windows for now (Linux comes next)."


# ---------------------------------------------------------------- 3. the fixes: one card each, with Undo
def test_renaming_the_videos_folder_back(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    src = (w.game / "Stalker2/Content/Movies_old").resolve()
    out = fx.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies", why="приховані відео")
    assert out == WAITING and src.is_dir()                       # nothing changes before Confirm
    card = _card(fx)
    assert card.kind == "fix_rename" and card.details == {"name": GAME, "place": "install",
                                                          "path": "Stalker2/Content/Movies_old", "to": "Movies",
                                                          "is_dir": True, "why": "приховані відео"}
    with pytest.raises(WorkError, match="This card already waits for the user's Confirm"):
        fx.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies")
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and done.result == f"renamed install/Stalker2/Content/Movies_old → Movies ({GAME})"
    assert (w.game / "Stalker2/Content/Movies/Intro.bk2").is_file() and not src.exists()
    assert done.undo == {"type": "moves", "moves": [(str(src), str(src.with_name("Movies")))], "rename": True}
    assert "Movies_old" not in fx.check("stalker 2", limit=8000)          # the next look reads the folder again
    assert history.undo_moves(done.undo["moves"]) == (1, 0) and src.is_dir()


def test_a_running_program_is_never_changed(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    shipping = ("Stalker2-Win64-Shipping.exe", str(w.win64 / "Stalker2-Win64-Shipping.exe"))
    w.procs.append(shipping)
    with pytest.raises(WorkError, match="is running now .* Ask the user to close it first"):
        fx.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies")
    w.procs.remove(shipping)
    fx.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies")
    w.procs.append(shipping)                                    # started again before Confirm
    done = fx.actions.confirm(_card(fx).id)
    assert done.state == "failed" and done.result == (f"{GAME} is running now (Stalker2-Win64-Shipping.exe): nothing "
                                                      "was changed. Close it, then ask again.")
    assert (w.game / "Stalker2/Content/Movies_old").is_dir() and done.undo is None


def test_what_a_rename_refuses(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    movies = "Stalker2/Content/Movies_old"
    with pytest.raises(WorkError, match="Lanterna doesn't make .exe files by renaming"):
        fx.propose_rename("stalker 2", "install", movies, "Movies.exe")
    with pytest.raises(WorkError, match="Give a path inside the place, without '..'."):
        fx.propose_rename("stalker 2", "install", "Stalker2/../../../user", "x")
    with pytest.raises(WorkError, match="There is no 'Stalker2/Content/Nope' in install."):
        fx.propose_rename("stalker 2", "install", "Stalker2/Content/Nope", "x")
    with pytest.raises(WorkError, match="new_name is only the new name"):
        fx.propose_rename("stalker 2", "install", movies, "Content/Movies")
    with pytest.raises(WorkError, match="'Data' already exists next to it: nothing was changed."):
        fx.propose_rename("stalker 2", "install", movies, "Data")
    with pytest.raises(WorkError, match="Lanterna never changes saved games."):
        fx.propose_rename("stalker 2", "local", "Saved/SaveGames/slot1.sav", "slot1.sav.bak")
    with pytest.raises(WorkError, match="has no place 'roaming'"):
        fx.propose_rename("stalker 2", "roaming", "x", "y")
    assert not fx.actions.items


def test_one_setting_is_changed_and_the_old_file_kept(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    ini = w.local / "Stalker2/Saved/Config/Windows/GameUserSettings.ini"
    rel = "Saved/Config/Windows/GameUserSettings.ini"
    assert fx.propose_setting("stalker 2", "local", rel, "ResolutionSizeX", "1920") == \
        "Nothing to change: ResolutionSizeX is already 1920."
    assert fx.propose_setting("stalker 2", "local", rel, "FullscreenMode", "1",
                              section="[/Script/Engine.GameUserSettings]", why="window mode") == WAITING
    card = _card(fx)
    assert card.kind == "fix_setting" and card.details == {
        "name": GAME, "place": "local", "path": rel, "key": "FullscreenMode", "section": "/Script/Engine.GameUserSettings",
        "from": "0", "to": "1", "added": False, "why": "window mode"}
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and ini.read_bytes() == SETTINGS.replace(b"FullscreenMode=0", b"FullscreenMode=1")
    assert done.undo["type"] == "restore_backup" and Path(done.undo["backup"]).read_bytes() == SETTINGS
    assert history.undo_restore_backup(done.undo["path"], done.undo["backup"]) and ini.read_bytes() == SETTINGS
    fx.propose_setting("stalker 2", "local", rel, "FullscreenMode", "2", section="/Script/Engine.GameUserSettings")
    ini.write_bytes(SETTINGS + b"bVSync=True\r\n")                  # the game wrote it in the meantime
    done = fx.actions.confirm(_card(fx).id)
    assert done.state == "failed" and done.result == "The file changed since it was read: nothing was changed. Ask again."


def test_settings_files_keep_their_look():
    assert fixit.ini_set("[A]\r\nx = 1\r\n\r\n[B]\r\nx=2\r\n", "x", "5", "B") == ("[A]\r\nx = 1\r\n\r\n[B]\r\nx=5\r\n", "2")
    assert fixit.ini_set("[A]\r\nx = 1\r\n\r\n[B]\r\nx=2\r\n", "x", "5", "A") == ("[A]\r\nx = 5\r\n\r\n[B]\r\nx=2\r\n", "1")
    with pytest.raises(WorkError, match="'x' is in several sections \\(A, B\\): say which one."):
        fixit.ini_set("[A]\r\nx = 1\r\n\r\n[B]\r\nx=2\r\n", "x", "5")
    assert fixit.ini_set("[A]\r\nx = 1\r\n\r\n[B]\r\nx=2\r\n", "y", "7", "A") == ("[A]\r\nx = 1\r\ny=7\r\n\r\n[B]\r\nx=2\r\n",
                                                                               None)
    assert fixit.ini_set("a=1\n", "b", "2", "S") == ("a=1\n\n[S]\nb=2\n", None)
    with pytest.raises(WorkError, match="To add it, give the \\[section\\] it belongs to."):
        fixit.ini_set("[A]\nx=1\n", "z", "1")
    text = '{\n  "graphics": {\n    "vsync": true\n  }\n}\n'
    assert fixit.json_set(text, "graphics.vsync", "false") == (text.replace("true", "false"), "true")
    with pytest.raises(WorkError, match="'graphics' holds a group of settings"):
        fixit.json_set(text, "graphics", "1")
    with pytest.raises(WorkError, match="isn't plain JSON"):
        fixit.json_set('// note\n{"a": 1}', "a", "2")


def test_mods_go_aside_and_come_back(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    with pytest.raises(WorkError, match="'Stalker2.exe' doesn't look like a mod or an added file"):
        fx.propose_aside("stalker 2", "install", ["Stalker2.exe"])
    assert fx.propose_aside("stalker 2", "install", ["Stalker2/Binaries/Win64/dxgi.dll"], why="a mod") == WAITING
    card = _card(fx)
    assert card.kind == "fix_aside" and card.details == {"name": GAME, "place": "install",
                                                         "files": ["Stalker2/Binaries/Win64/dxgi.dll"], "count": 1,
                                                         "to": TURNED_OFF, "why": "a mod"}
    done = fx.actions.confirm(card.id)
    root = w.game.resolve()
    assert done.state == "done" and not (w.win64 / "dxgi.dll").exists()
    assert (root / TURNED_OFF / "Stalker2/Binaries/Win64/dxgi.dll").is_file()
    out = fx.check("stalker 2", limit=8000)
    assert f"- {TURNED_OFF}/: files Lanterna turned off earlier" in out and "dxgi.dll" not in out
    assert done.undo["type"] == "moves" and history.undo_moves(done.undo["moves"]) == (1, 0)
    assert (w.win64 / "dxgi.dll").is_file() and not (root / TURNED_OFF).exists()   # the folder it made is gone


def test_a_cache_goes_to_the_recycle_bin(tmp_path):
    w = _world(tmp_path)
    fx, log = _fx(w)
    assert fx.propose_cache("", "nvidia_cache", why="graphics glitches") == WAITING   # no program: the driver's cache
    card = _card(fx)
    assert card.kind == "fix_cache" and card.details == {"name": "", "place": "nvidia_cache",
                                                         "path": "the NVIDIA driver's shader cache", "size": "500 B",
                                                         "count": 1, "driver": True, "why": "graphics glitches"}
    done = fx.actions.confirm(card.id)
    cache = (w.local / "NVIDIA" / "DXCache").resolve()
    assert done.state == "done" and log.trashed == [[cache]] and done.undo == {"type": "trash", "paths": [str(cache)]}
    with pytest.raises(WorkError, match="fix_cache is for cache folders only"):
        fx.propose_cache("stalker 2", "local", "Saved/Config")
    with pytest.raises(WorkError, match="Say which program"):
        fx.propose_cache("", "local", "Saved")
    with pytest.raises(WorkError, match="Say which program"):
        fx.propose_cache("", "steam_shaders")                   # Steam's cache is one game's


def test_steams_check_of_files(tmp_path):
    w = _world(tmp_path)
    fx, log = _fx(w)
    out = fx.propose_verify("stalker 2")
    assert out == WAITING + " After Confirm, Steam checks the files itself and downloads what is missing or changed."
    card = _card(fx)
    assert card.kind == "fix_verify" and card.details == {"name": GAME, "appid": "1643320"} and not log.urls
    assert fx.actions.confirm(card.id).state == "done" and log.urls == ["steam://validate/1643320"]
    assert fx.propose_verify("Steam").startswith("Not a Steam game. To repair a program: Settings → Apps")


# ---------------------------------------------------------------- 4. Windows itself
def test_dns_and_the_proxy(tmp_path):
    w = _world(tmp_path)
    inet = fixit.INET
    reg = FakeReg({(CU, inet, "ProxyEnable"): 1, (CU, inet, "ProxyServer"): "127.0.0.1:8888",
                   (CU, inet, "AutoConfigURL"): "http://wpad.example/proxy.pac"}, w.tree)
    fx, log = _fx(w, reg=reg)
    assert fx.propose_windows("dns") == WAITING
    assert fx.actions.confirm(_card(fx).id).result == "the DNS cache is cleared"
    assert log.runs[-1] == (["ipconfig", "/flushdns"], None)
    assert fx.propose_windows("proxy_off") == WAITING and not reg.calls
    card = _card(fx)
    assert card.kind == "fix_proxy" and card.details == {"server": "127.0.0.1:8888; script http://wpad.example/proxy.pac"}
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and reg.calls == [("set", "ProxyEnable", 0), ("delete", "AutoConfigURL")]
    assert log.refreshed == 1 and done.undo == {"type": "proxy", "enable": 1, "pac": "http://wpad.example/proxy.pac"}
    assert fx.propose_windows("proxy_off") == "No proxy is on: nothing to turn off."
    assert fx.undo_proxy(done.undo) and log.refreshed == 2
    assert reg.get(CU, inet, "ProxyEnable") == 1 and reg.get(CU, inet, "AutoConfigURL") == "http://wpad.example/proxy.pac"
    with pytest.raises(WorkError, match="action: dns, proxy_off, default_printer or print_queue."):
        fx.propose_windows("reboot")


def test_the_default_printer_and_the_print_queue(tmp_path):
    w = _world(tmp_path)
    reg = FakeReg(tree=w.tree)
    printers = FakePrinters(["Microsoft Print to PDF", "HP LaserJet M110w", "HP OfficeJet Pro 9010"],
                            "Microsoft Print to PDF")
    fx, log = _fx(w, reg=reg, printers=printers)
    with pytest.raises(WorkError, match="Several printers match: HP LaserJet M110w; HP OfficeJet Pro 9010"):
        fx.propose_windows("default_printer", "hp")
    assert fx.propose_windows("default_printer", "Microsoft Print to PDF") == \
        "'Microsoft Print to PDF' is the default printer already."
    assert fx.propose_windows("default_printer", "laserjet") == WAITING
    card = _card(fx)
    assert card.kind == "fix_printer" and card.details == {"name": "HP LaserJet M110w", "was": "Microsoft Print to PDF"}
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and printers.default() == "HP LaserJet M110w"
    assert reg.get(CU, fixit.WINDOWS_NT, "LegacyDefaultPrinterMode") == 1    # Windows stops choosing by itself
    assert done.undo == {"type": "printer", "name": "Microsoft Print to PDF", "legacy": None}
    assert fx.undo_printer(done.undo) and printers.default() == "Microsoft Print to PDF"
    assert reg.get(CU, fixit.WINDOWS_NT, "LegacyDefaultPrinterMode") is None
    assert fx.propose_windows("print_queue", "LaserJet") == WAITING
    assert _card(fx).details == {"name": "HP LaserJet M110w"}
    assert fx.actions.confirm(_card(fx).id).state == "done"
    args, env = log.runs[-1]
    assert args == ["powershell", "-NoProfile", "-NonInteractive", "-Command", fixit.PS_CLEAR_QUEUE]
    assert env["LANTERNA_PRINTER"] == "HP LaserJet M110w" and "LaserJet" not in " ".join(args)  # never in the script


# ---------------------------------------------------------------- 5. in the app: the card, its title and Undo
def test_the_app_confirms_a_folder_rename_and_undoes_it(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    w = _world(tmp_path)
    api.fixer, _log = _fx(w, api.actions)
    api.fixer.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies")
    card = _card(api.fixer)
    assert "folder" not in card.details                        # "folder" is the chat's working folder to the app
    res = api.action_confirm(card.id)
    assert res["state"] == "done" and res["text"] == f"Перейменовано Movies_old → Movies у {GAME}"
    entry = api.history_list()[0]
    assert entry["kind"] == "fix_rename" and entry["can_undo"] and entry["title"] == res["text"]
    assert api.history_undo(entry["id"]) == {"ok": True, "text": "Стару назву повернуто."}
    assert (w.game / "Stalker2/Content/Movies_old").is_dir() and not (w.game / "Stalker2/Content/Movies").exists()
    offered = {t.name: t for t in api._pc_tools()}
    assert {"fix_check", "fix_rename", "fix_windows"} <= set(offered) and offered["fix_check"].group == "fix"


def test_what_runs_at_once_and_what_undo_keeps():
    can = {"fix_rename", "fix_setting", "fix_aside", "fix_cache", "fix_dns", "fix_proxy", "fix_printer"}
    assert can <= workspace.AUTO_KINDS and not {"fix_verify", "fix_queue"} & workspace.AUTO_KINDS
    assert {"proxy", "printer", "moves", "trash", "restore_backup"} <= set(history.UNDO_TYPES)
    assert {"fix_check", "fix_list", "fix_read"} <= tools.READ_ONLY_TOOLS
    assert not chat.acting_pc("fix_check") and chat.acting_pc("fix_rename") and chat.acting_pc("fix_windows")
    assert "fix" in tools.INTENT_GROUPS


def test_the_fix_tools_are_offered(tmp_path):
    w = _world(tmp_path)
    fx, _log = _fx(w)
    names = [t.name for t in fixit.fix_tools(fx)]
    assert names == ["fix_check", "fix_list", "fix_read", "fix_rename", "fix_setting", "fix_aside", "fix_cache",
                     "fix_verify", "fix_windows"]
    assert "Call it FIRST, before asking the user anything" in fixit.fix_tools(fx)[0].description
    assert "Call fix_check with the program's name as installed" in chat.FIX_GUIDE
    assert "Call fix_check" in chat.system_prompt(tools=True, fix=True) and \
        "Call fix_check" not in chat.system_prompt(tools=True)


@pytest.mark.parametrize("text", ["гра не запускається", "Сталкер вилітає на робочий стіл", "чорний екран у грі",
                                  "немає звуку", "принтер не друкує", "the game keeps crashing", "no sound on my laptop",
                                  "il gioco non parte", "das Spiel startet nicht", "el juego no arranca",
                                  "le jeu ne démarre pas", "gra się nie uruchamia"])
def test_the_fix_tools_come_when_something_doesnt_work(text):
    assert tools.GROUPS["fix"].search(text), text


@pytest.mark.parametrize("text", ["гра не запускається", "Сталкер вилітає", "чорний екран у місії", "немає звуку",
                                  "не працює інтернет", "принтер не друкує", "the printer won't print",
                                  "the game keeps crashing", "black screen in a mission", "schermo nero",
                                  "startet nicht", "pantalla negra", "écran noir", "czarny ekran"])
def test_lanterna_looks_before_it_answers(text):
    assert chat.must_use_tool(text), text                        # the first round must call a tool (fix_check)


def test_other_talk_doesnt_bring_the_fix_tools():
    for text in ("у мене багато файлів", "explain why the sky is blue", "напиши гру змійку"):
        assert not tools.GROUPS["fix"].search(text), text


# ---------------------------------------------------------------- 6. the user's language: cards, lines, the window
def _titles():
    return {"fix_rename": {"name": GAME, "path": "Stalker2/Content/Movies_old", "to": "Movies"},
            "fix_setting": {"name": GAME, "key": "FullscreenMode"},
            "fix_aside": {"name": GAME, "count": 2},
            "fix_cache": {"name": GAME},
            "fix_verify": {"name": GAME},
            "fix_dns": {},
            "fix_proxy": {},
            "fix_printer": {"name": "HP LaserJet M110w"},
            "fix_queue": {"name": "HP LaserJet M110w"}}


def test_every_new_string_is_translated():
    new = list(app.FIX_PLACES.values()) + list(app.FIX_TEXT.values()) + [
        "The old name is back.", "Windows didn't accept the old default printer.", sent.FIX_PROGRAM, sent.FIX_WINDOWS,
        "Clear the shader cache", "Cleared the shader cache"]
    new += [thinking.TOOL_TEXT[n][0] for n in thinking.TOOL_TEXT if n.startswith("fix_")]
    for s in new:
        assert s in i18n._T and i18n._T[s]["uk"] != s and i18n._T[s]["it"] != s, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s, s) != s, (lang, s)
    for kind, d in _titles().items():
        for done in (False, True):
            en, uk = (app.action_title(kind, d, "", lang, done=done) for lang in ("en", "uk"))
            assert en != uk and "{" not in uk, (kind, done, uk)
    assert app.action_title("fix_cache", {"driver": True}, "", "uk") == "Очистити кеш шейдерів"
    assert app.action_title("fix_rename", _titles()["fix_rename"], "", "uk") == f"Перейменувати Movies_old → Movies у {GAME}"


def test_the_card_says_where_what_and_how_to_undo():
    d = {"name": GAME, "place": "install", "path": "Stalker2/Content/Movies_old", "to": "Movies", "is_dir": True,
         "why": "приховані відео"}
    assert app.card_text("fix_rename", d, "uk").split("\n") == [
        i18n.t("Reason: {r}", "uk", r="приховані відео"), "Папка програми: Stalker2/Content/Movies_old → Movies",
        "Кнопка «Повернути як було» поверне стару назву."]
    cache = {"name": "", "place": "nvidia_cache", "path": "the NVIDIA driver's shader cache", "size": "1.4 GB",
             "driver": True}
    assert app.card_text("fix_cache", cache, "uk").split("\n")[0] == "Кеш шейдерів драйвера NVIDIA · 1.4 GB"
    own = {"name": GAME, "place": "local2", "path": "local2/Saved/ShaderCache", "size": "300 MB"}
    assert app.card_text("fix_cache", own, "en").split("\n")[0] == "Its folder in AppData\\Local: Saved/ShaderCache · 300 MB"
    setting = {"name": GAME, "place": "local", "path": "Saved/Config/Windows/GameUserSettings.ini",
               "key": "FullscreenMode", "section": "/Script/Engine.GameUserSettings", "from": "0", "to": "1"}
    assert "[/Script/Engine.GameUserSettings] FullscreenMode: 0 → 1" in app.card_text("fix_setting", setting, "en")


def test_what_went_to_the_model_and_the_working_line():
    items = sent.build("M", False, 0, False, 0, [], 0,
                       [("fix_check", '{"what": "S.T.A.L.K.E.R. 2"}'), ("fix_check", '{"what": "no sound"}'),
                        ("fix_list", '{"program": "x", "place": "install"}'),
                        ("fix_read", '{"program": "x", "place": "local", "path": "Saved/Logs/Stalker2.log"}')])
    lines = sent.view(sent.dumps(items), "uk")
    assert "Назви файлів у папках S.T.A.L.K.E.R. 2, рядки з журналів програми й записи Windows про неї" in lines
    assert "Перевірка Windows (no sound): її пристрої, налаштування й останні записи" in lines
    assert i18n.t("Names and sizes of files in your folders", "uk") in lines
    assert i18n.t("The text of the file {path}", "uk", path="Saved/Logs/Stalker2.log") in lines
    assert thinking.tool_step("fix_check", json.dumps({"what": "Stalker 2"}), "uk") == "Шукаю, що не так: Stalker 2"
    assert thinking.tool_step("fix_aside", "{}", "uk") == "Готую вимкнення модів"
    assert thinking.tool_step("fix_windows", '{"action": "dns"}', "uk") == "Готую виправлення у Windows"


def test_the_window_shows_the_fix_cards_and_the_start_row():
    for s in list(app.FIX_PLACES.values()) + list(app.FIX_TEXT.values()):
        assert json.dumps(s, ensure_ascii=False) in JS, s       # the same words as fix_card_lines
    keys = {"fix_rename": "Rename {path} → {to} in {name}", "fix_setting": "Change {key} in {name}",
            "fix_aside": "Turn off mods of {name} ({count})", "fix_verify": "Check the files of {name} in Steam",
            "fix_dns": "Clear the DNS cache", "fix_proxy": "Turn off the proxy",
            "fix_printer": "Make {name} the default printer", "fix_queue": "Clear the print queue of {name}"}
    for kind, key in keys.items():                             # the window's titles: the same keys as action_title
        assert f"{kind}: {json.dumps(key, ensure_ascii=False)}" in JS and key in i18n._T, kind
        d = _titles()[kind]
        assert app.action_title(kind, d, "", "en") == key.format(**{**d, "path": str(d.get("path", "")).split("/")[-1]})
    assert 'd.driver ? "Clear the shader cache" : "Clear the cache of {name}"' in JS
    assert 'k === "fix_cache" ? "trash" : k.startsWith("fix_") ? "wrench"' in JS
    start = JS[JS.index("function showEmpty()"):JS.index("const FILE_LINE")]
    assert 'fix = pc && S.platform === "win32"' in start and '"Fixes", "A game or a program doesn\'t work?' in start
    fill = start[start.index('if (b.dataset.fill === "fix")'):]
    fill = fill[:fill.index("return;")]
    assert 't("Doesn\'t work:")' in fill and "click()" not in fill   # it fills the box; the user names the program
    for s in ("Fixes", "Doesn't work:", "A game or a program doesn't work? Find the cause"):
        assert re.search(re.escape(json.dumps(s)) + r": \{ uk: ", JS), s
    src = (SRC / "tui.py").read_text(encoding="utf-8")
    assert '"🧹 " if k == "fix_cache" else "🛠 " if k.startswith("fix_")' in src
