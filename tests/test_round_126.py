"""More of the computer: open programs, websites and files; change the look (GNOME / Windows) with Undo;
and "do it on your own" in one chat after the user confirms it. Nothing real is opened or changed:
gsettings, the registry, the sound and the launcher are fakes."""
import json
from pathlib import Path

import pytest

from lanterna import pcfiles
from lanterna.app import action_title, card_text
from lanterna.pccontrol import Launcher, Look
from lanterna.workspace import Actions, WorkError
from test_tui import api  # noqa: F401  (Api with a fake vault in a temp home)


# ---------------------------------------------------------------- fakes
class FakeGnome:
    """gsettings / wpctl / fc-list with values in a dict."""

    def __init__(self, accent=True):
        self.v = {("org.gnome.desktop.interface", "color-scheme"): "'default'",
                  ("org.gnome.desktop.interface", "text-scaling-factor"): "1.0",
                  ("org.gnome.desktop.interface", "icon-theme"): "'Adwaita'",
                  ("org.gnome.desktop.interface", "cursor-theme"): "'Adwaita'",
                  ("org.gnome.desktop.interface", "cursor-size"): "24",
                  ("org.gnome.desktop.interface", "gtk-theme"): "'Adwaita'",
                  ("org.gnome.desktop.interface", "font-name"): "'Cantarell 11'",
                  ("org.gnome.desktop.interface", "clock-show-seconds"): "false",
                  ("org.gnome.desktop.interface", "clock-show-weekday"): "false",
                  ("org.gnome.desktop.interface", "show-battery-percentage"): "false",
                  ("org.gnome.desktop.interface", "enable-animations"): "true",
                  ("org.gnome.desktop.interface", "enable-hot-corners"): "true",
                  ("org.gnome.settings-daemon.plugins.color", "night-light-enabled"): "false",
                  ("org.gnome.desktop.notifications", "show-banners"): "true",
                  ("org.gnome.desktop.wm.preferences", "button-layout"): "'appmenu:close'",
                  ("org.gnome.desktop.background", "picture-uri"): "'file:///usr/share/backgrounds/f41.png'",
                  ("org.gnome.desktop.background", "picture-uri-dark"): "'file:///usr/share/backgrounds/f41-dark.png'"}
        if accent:
            self.v[("org.gnome.desktop.interface", "accent-color")] = "'blue'"
        self.volume, self.muted, self.calls = 0.40, False, []

    def __call__(self, args, timeout=20):
        self.calls.append(args)
        if args[0] == "gsettings":
            key = (args[2], args[3])
            if args[1] == "get":
                return (0, self.v[key] + "\n") if key in self.v else (1, "No such key\n")
            if args[1] == "range":
                if key == ("org.gnome.desktop.interface", "accent-color"):
                    return 0, "enum\n'blue'\n'teal'\n'green'\n'purple'\n'slate'\n"
                return 0, "type s\n"
            if args[1] == "set":
                assert key in self.v, key
                self.v[key] = args[4]
                return 0, ""
        if args[:2] == ["wpctl", "get-volume"]:
            return 0, f"Volume: {self.volume:.2f}" + (" [MUTED]" if self.muted else "") + "\n"
        if args[:2] == ["wpctl", "set-volume"]:
            self.volume = float(args[3])
            return 0, ""
        if args[:2] == ["wpctl", "set-mute"]:
            self.muted = args[3] == "1"
            return 0, ""
        if args[0] == "fc-list":
            return 0, "Cantarell\nNoto Sans,Noto Sans Regular\nJetBrainsMono Nerd Font\n"
        return 127, "not faked"


class FakeReg:
    def __init__(self):
        self.v = {}

    def get(self, hive, path, name):
        return self.v.get((path, name))

    def values(self, hive, path):
        return {}

    def set(self, hive, path, name, value, kind):
        assert hive == "HKEY_CURRENT_USER"
        self.v[(path, name)] = value


def _which(have):
    return lambda n: f"/usr/bin/{n}" if n in have else None


@pytest.fixture
def home(tmp_path):
    folders = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in folders.values():
        f.mkdir()
    return folders


def _gnome(tmp_path, home, accent=True):
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    places = pcfiles.Places(acts, folders=lambda: home, opener=lambda p: None)
    g = FakeGnome(accent)
    hh = tmp_path / "h"
    (hh / ".local/share/icons/Papirus/48x48").mkdir(parents=True)
    (hh / ".local/share/icons/Papirus/index.theme").write_text("[Icon Theme]")
    (hh / ".icons/Bibata/cursors").mkdir(parents=True)
    look = Look(acts, places, runner=g, platform_="linux", which=_which({"gsettings", "wpctl", "fc-list"}), home=hh)
    return look, g, acts, cards


# ---------------------------------------------------------------- the look on GNOME
def test_gnome_look_lists_changes_and_undoes(tmp_path, home):
    look, g, acts, cards = _gnome(tmp_path, home)
    text = look.options()
    for want in ("accent (Accent color): now blue; values: blue | teal | green | purple | slate", "icon_theme",
                 "Papirus", "Bibata", "volume (Volume): now 40", "window_buttons", "wallpaper"):
        assert want in text, want
    out = look.propose({"accent": "Purple", "clock_seconds": "on", "text_size": "125%", "icon_theme": "papirus",
                        "volume": 70, "window_buttons": "all", "font": "Noto Sans 11"})
    assert "Nothing has been changed yet" in out
    c = cards[-1]
    assert c["kind"] == "sys_look" and c["details"]["count"] == 7
    assert g.v[("org.gnome.desktop.interface", "accent-color")] == "'blue'"           # nothing before Confirm
    body = card_text("sys_look", c["details"], "uk")
    assert "Колір акценту: синій → фіолетовий" in body and "Гучність: 40 → 70" in body
    assert action_title("sys_look", c["details"], "", "uk") == "Змінити вигляд системи (налаштувань: 7)"
    a = acts.confirm(c["id"])
    assert a.state == "done", a.result
    assert g.v[("org.gnome.desktop.interface", "accent-color")] == "'purple'"
    assert g.v[("org.gnome.desktop.interface", "clock-show-seconds")] == "true"
    assert g.v[("org.gnome.desktop.interface", "text-scaling-factor")] == "1.25"
    assert g.v[("org.gnome.desktop.interface", "icon-theme")] == "'Papirus'"
    assert g.v[("org.gnome.desktop.wm.preferences", "button-layout")] == "'appmenu:minimize,maximize,close'"
    assert g.v[("org.gnome.desktop.interface", "font-name")] == "'Noto Sans 11'"
    assert round(g.volume, 2) == 0.70
    assert a.undo["type"] == "look"
    # Undo: the exact old values come back, through the same checks (run_now)
    back = acts.run_now(lambda: look.propose(a.undo["set"], restore=True))
    assert back.state == "done", back.result
    assert g.v[("org.gnome.desktop.interface", "accent-color")] == "'blue'"
    assert g.v[("org.gnome.desktop.interface", "text-scaling-factor")] == "1.0"
    assert g.v[("org.gnome.desktop.interface", "font-name")] == "'Cantarell 11'"
    assert round(g.volume, 2) == 0.40
    # already like that: no card
    n = len(cards)
    assert "already" in look.propose({"accent": "blue"}) and len(cards) == n


def test_gnome_look_refuses_what_is_not_there(tmp_path, home):
    look, g, acts, cards = _gnome(tmp_path, home, accent=False)
    assert "accent" not in look.table()                        # GNOME before 47 has no accent colors
    for bad, msg in (({"accent": "red"}, "can't be changed here"), ({"icon_theme": "Nope"}, "installed ones are"),
                     ({"text_size": "9"}, "from 0.75"), ({"font": "Comic Sans 11"}, "no font"),
                     ({"wallpaper": "pictures/none.jpg"}, "no picture"), ({"volume": "200"}, "0 to 100"),
                     ({"night_light": "maybe"}, "on or off"), ({"window_buttons": "rm -rf"}, "one of")):
        with pytest.raises(WorkError, match=msg):
            look.propose(bad)
    assert not cards


def test_gnome_wallpaper_from_the_users_pictures(tmp_path, home):
    look, g, acts, cards = _gnome(tmp_path, home)
    (home["pictures"] / "sea.jpg").write_bytes(b"\xff\xd8 fake jpeg")
    (home["pictures"] / "notes.txt").write_text("x")
    with pytest.raises(WorkError, match="not a picture"):
        look.propose({"wallpaper": "pictures/notes.txt"})
    look.propose({"wallpaper": "pictures/sea.jpg"})
    a = acts.confirm(cards[-1]["id"])
    assert a.state == "done", a.result
    uri = (home["pictures"] / "sea.jpg").resolve().as_uri()
    assert g.v[("org.gnome.desktop.background", "picture-uri")] == f"'{uri}'"
    assert g.v[("org.gnome.desktop.background", "picture-uri-dark")] == f"'{uri}'"
    assert a.undo["set"]["wallpaper"] == "/usr/share/backgrounds/f41.png"


def test_no_gnome_no_changes(tmp_path, home):
    acts = Actions()
    look = Look(acts, None, runner=lambda a, timeout=20: (127, ""), platform_="linux", which=_which(set()), home=tmp_path)
    assert look.table() == {} and "can't change the look" in look.options()


# ---------------------------------------------------------------- the look on Windows
def test_windows_look_with_the_registry(tmp_path, home):
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    reg, walls = FakeReg(), []
    places = pcfiles.Places(acts, folders=lambda: home, opener=lambda p: None)
    look = Look(acts, places, platform_="win32", reg=reg, which=_which(set()), home=tmp_path,
                wallpaper_win=lambda p: walls.append(p) or True)
    assert "text size" in look.options()                         # what isn't here is said
    (home["pictures"] / "m.png").write_bytes(b"png")
    look.propose({"taskbar_left": "on", "clock_seconds": True, "file_extensions": "on", "wallpaper": "pictures/m.png"})
    a = acts.confirm(cards[-1]["id"])
    assert a.state == "done", a.result
    adv = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    assert reg.v[(adv, "TaskbarAl")] == 0 and reg.v[(adv, "ShowSecondsInSystemClock")] == 1 and reg.v[(adv, "HideFileExt")] == 0
    assert walls == [str((home["pictures"] / "m.png").resolve())]
    with pytest.raises(WorkError, match="can't be changed here"):
        look.propose({"night_light": "on"})


# ---------------------------------------------------------------- opening things
def _desktop(d: Path, name, file, extra=""):
    (d / file).write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec=x\n{extra}", encoding="utf-8")


def test_open_programs_sites_and_files(tmp_path, home):
    apps = tmp_path / "apps"
    apps.mkdir()
    _desktop(apps, "Firefox", "org.mozilla.firefox.desktop", "Keywords=web;browser;internet;\n")
    _desktop(apps, "Files", "org.gnome.Nautilus.desktop")
    _desktop(apps, "Hidden helper", "helper.desktop", "NoDisplay=true\n")
    _desktop(apps, "LibreOffice Writer", "writer.desktop")
    _desktop(apps, "LibreOffice Calc", "calc.desktop")
    spawned, urls = [], []
    places = pcfiles.Places(Actions(), folders=lambda: home, opener=lambda p: None)
    ln = Launcher(places, platform_="linux", which=_which({"gio", "xdg-open"}), spawn=lambda a: spawned.append(a) or True,
                  open_url=lambda u: urls.append(u) or True, app_dirs=[apps])
    assert "Hidden helper" not in [p["name"] for p in ln.programs()]
    assert ln.open_program("firefox") == "Opened Firefox."
    assert spawned[-1] == ["gio", "launch", str(apps / "org.mozilla.firefox.desktop")]
    assert ln.open_program("browser") == "Opened Firefox."                  # by what it is
    assert "Several programs match" in ln.open_program("libreoffice")
    assert "isn't installed" in ln.open_program("photoshop") or "No program" in ln.open_program("photoshop")
    assert ln.open_site("google.com") == "Opened https://google.com in the browser."
    ln.open_site("https://www.google.com/search?q=fedora")
    assert urls == ["https://google.com", "https://www.google.com/search?q=fedora"]
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "ms-settings:", "~/x.sh"):
        with pytest.raises(WorkError):
            ln.open_site(bad)
    (home["documents"] / "plan.pdf").write_bytes(b"%PDF")
    (home["downloads"] / "setup.sh").write_text("echo")
    (home["downloads"] / "app.AppImage").write_text("x")
    assert ln.open_file("documents", "plan.pdf") == "Opened documents/plan.pdf."
    assert spawned[-1] == ["xdg-open", str((home["documents"] / "plan.pdf").resolve())]
    for bad in ("setup.sh", "app.AppImage"):
        with pytest.raises(WorkError, match="doesn't open"):
            ln.open_file("downloads", bad)


def test_windows_programs_from_the_start_menu(tmp_path):
    sm = tmp_path / "Start Menu"
    (sm / "Telegram").mkdir(parents=True)
    (sm / "Telegram" / "Telegram.lnk").write_bytes(b"lnk")
    (sm / "Telegram" / "Uninstall Telegram.lnk").write_bytes(b"lnk")
    started, spawned = [], []
    ln = Launcher(None, platform_="win32", spawn=lambda a: spawned.append(a) or True, open_url=lambda u: True,
                  startfile=started.append, app_dirs=[sm])
    assert ln.open_program("telegram") == "Opened Telegram."
    assert started == [str(sm / "Telegram" / "Telegram.lnk")]
    assert ln.open_program("calculator") == "Opened Calculator." and spawned == [["calc.exe"]]


# ---------------------------------------------------------------- acting on its own, in one chat
def test_on_its_own_only_after_confirm_and_only_safe_changes(api, home, tmp_path):  # noqa: F811
    api.settings.pc_access = True
    api.places = pcfiles.Places(api.actions, folders=lambda: home, opener=lambda p: None, trash=lambda ps: None)
    tid = api.new_thread()["id"]
    sink: list = []
    api.actions.bind(sink, tid)
    # without permission: a card that waits
    out = api.toolbox.run("pc_write", json.dumps({"place": "desktop", "path": "a.txt", "text": "one"}))
    assert "Nothing has been changed yet" in out and sink[-1]["state"] == "pending" and not (home["desktop"] / "a.txt").exists()
    # the model asks; nothing changes until the user confirms the card
    out = api.toolbox.run("pc_auto_ask", json.dumps({"minutes": 30, "plan": "Set up the desktop"}))
    ask = sink[-1]
    assert ask["kind"] == "auto_on" and ask["state"] == "pending" and not api.auto_status(tid)["on"]
    assert "Set up the desktop" in card_text("auto_on", ask["details"], "en")
    assert api.action_confirm(ask["id"])["state"] == "done"
    st = api.auto_status(tid)
    assert st["on"] and 29 * 60 < st["left"] <= 30 * 60
    # now a safe change happens at once, is logged with Undo, and the model is told it is done
    out = api.toolbox.run("pc_write", json.dumps({"place": "desktop", "path": "b.txt", "text": "two"}))
    assert "Done right away" in out and "Nothing has been changed yet" not in out
    assert (home["desktop"] / "b.txt").read_text(encoding="utf-8") == "two"
    c = sink[-1]
    assert c["state"] == "done" and c["auto"] and c["text"]
    assert any(h["kind"] == "pc_write" and h["undo"] for h in api.history.items())
    # mail, GitHub, Drive, outside tools and removing programs still ask
    for kind in ("mail_send", "github_push", "drive_text", "mcp_call", "app_uninstall"):
        a = api.actions.propose(kind, {"name": "x"}, lambda: "sent")
        assert a.state == "pending", kind
    assert api.actions.take_auto() == []
    # another chat is not affected
    api.actions.bind(sink, api.new_thread()["id"])
    api.toolbox.run("pc_write", json.dumps({"place": "desktop", "path": "c.txt", "text": "3"}))
    assert sink[-1]["state"] == "pending"
    # Stop: cards again
    api.actions.bind(sink, tid)
    api.auto_stop(tid)
    api.toolbox.run("pc_write", json.dumps({"place": "desktop", "path": "d.txt", "text": "4"}))
    assert sink[-1]["state"] == "pending" and not (home["desktop"] / "d.txt").exists()


def test_on_its_own_ends_and_never_in_a_private_chat(api, monkeypatch):  # noqa: F811
    api.settings.pc_access = True
    api.actions.bind([], -5)
    with pytest.raises(WorkError, match="private"):
        api._auto_propose(30)
    api.actions.auto_start(7, 500)
    assert api.auto_status(7)["left"] <= 120 * 60                    # two hours at most
    import time as _t
    real = _t.time
    monkeypatch.setattr("lanterna.workspace.time.time", lambda: real() + 3 * 3600)
    assert not api.auto_status(7)["on"]
    assert "pc_auto_ask" in {t.name for t in api._pc_tools()} and "pc_open_site" in {t.name for t in api._pc_tools()}
    api.settings.pc_access = False
    assert api._pc_tools() == []                                     # all of it only with "help with this computer" on


def test_the_window_and_terminal_know_the_new_cards():
    from lanterna import gui
    assert "auto_status" in gui.METHODS and "auto_stop" in gui.METHODS
    js = open(Path(gui.__file__).parent / "ui" / "app.js", encoding="utf-8").read()
    assert "auto_on:" in js and '"sys_look"' in js and "paintAuto" in js
    assert action_title("auto_on", {"minutes": 30}, "", "uk").endswith("30 хв")
