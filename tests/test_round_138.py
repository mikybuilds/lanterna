"""Round 138 (1.1.8b8): Lanterna's own window on Linux (Fedora and the others).

- `lanterna desktop` puts Lanterna's own window in the app menu (lanterna-gui, no terminal) when it can open
  here: pywebview with the system's GTK WebKit, or Qt's WebEngine. Otherwise the menu opens the full-screen app in
  the terminal as before, and the command says exactly what gives it the window on this distribution (Fedora,
  Ubuntu/Debian/Mint, Arch), or what to look for elsewhere. `--terminal` keeps the terminal app.
- The window is "lanterna" to the desktop, so the dock and Alt+Tab show it with the launcher's name and icon.
- Started from the menu without what it needs, the window says so in a notification (no terminal to read it in)
  instead of failing silently; the terminal app works meanwhile.

Checked on Fedora 44 Workstation (GNOME, Wayland), which changed three things:
- it already has PyGObject and WebKitGTK, so no `sudo dnf install` is asked for where the system has them (the
  system's own Python is asked); only the two pipx commands are left;
- GTK 3 drew the window's frame light over the dark app (also in GNOME's dark style): it follows Lanterna's theme
  now, and "system" follows GNOME's style;
- Update now reinstalls an install pinned to a tag (as test versions are) with --system-site-packages and pywebview
  again, so the window keeps working after it.
"""
import io
import sys
import types
from pathlib import Path

import pytest
from rich.console import Console

from lanterna import cli, desktop, gui, i18n, keys, updates

ROOT = Path(__file__).resolve().parents[1]
FEDORA = ["sudo dnf install python3-gobject webkit2gtk4.1",
          "pipx install --force --system-site-packages git+https://github.com/mikybuilds/lanterna",
          "pipx inject lanterna pywebview", "lanterna desktop"]


def finder(monkeypatch, have: set[str]):
    """importlib.util.find_spec as if only these modules were installed."""
    def find(name):
        if name in have:
            return object()
        if "." in name and name.split(".")[0] not in have:
            raise ModuleNotFoundError(name)
        return None
    monkeypatch.setattr(desktop.importlib.util, "find_spec", find)


def fake_gi(monkeypatch, typelibs: set[str] | None):
    """The system's PyGObject with these namespaces ("Gtk-3.0", "WebKit2-4.1"…); None: no PyGObject at all."""
    if typelibs is None:
        monkeypatch.setitem(sys.modules, "gi", None)
        return

    def require_version(ns, version):
        if f"{ns}-{version}" not in typelibs:
            raise ValueError(f"Namespace {ns} not available for version {version}")
    monkeypatch.setitem(sys.modules, "gi", types.SimpleNamespace(require_version=require_version))


# ---------------------------------------------------------------- the launcher
def test_the_window_launcher_needs_no_terminal_and_owns_its_dock_icon(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(desktop.shutil, "which", {"lanterna-gui": "/usr/local/bin/lanterna-gui",
                                                  "lanterna": "/usr/local/bin/lanterna"}.get)
    desk, icon = desktop.install(window=True)
    text = desk.read_text(encoding="utf-8")
    assert 'Exec="/usr/local/bin/lanterna-gui"\n' in text and "Terminal=false\n" in text and icon.is_file()
    assert "StartupWMClass=lanterna\n" in text                         # gui.py names the window "lanterna"
    desk, _ = desktop.install()                                         # as before: the terminal app
    text = desk.read_text(encoding="utf-8")
    assert 'Exec="/usr/local/bin/lanterna"\n' in text and "Terminal=true\n" in text and "StartupWMClass" not in text
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)     # not on PATH: through this Python
    desk, _ = desktop.install(window=True)
    assert f'Exec="{sys.executable}" -m lanterna.gui\n' in desk.read_text(encoding="utf-8")
    assert desktop.remove()


# ---------------------------------------------------------------- can the window open here?
def test_what_the_window_still_needs(monkeypatch):
    finder(monkeypatch, set())
    fake_gi(monkeypatch, None)
    monkeypatch.setattr(desktop, "_system_has_parts", lambda: False)
    assert desktop.window_ready() == {"pywebview", "gi", "webkit"}      # a fresh pipx install
    monkeypatch.setattr(desktop, "_system_has_parts", lambda: True)
    assert desktop.window_ready() == {"pywebview", "gi"}                # Fedora Workstation: the system has them
    monkeypatch.setattr(desktop, "_system_has_parts", lambda: False)
    finder(monkeypatch, {"webview"})
    fake_gi(monkeypatch, {"Gtk-3.0", "WebKit2-4.1"})
    assert desktop.window_ready() == set()                              # Fedora with the two packages: it opens
    fake_gi(monkeypatch, {"Gtk-3.0", "WebKit2-4.0"})
    assert desktop.window_ready() == set()                              # an older WebKitGTK is fine too
    fake_gi(monkeypatch, {"Gtk-3.0"})
    assert desktop.window_ready() == {"webkit"}
    finder(monkeypatch, set())
    fake_gi(monkeypatch, {"Gtk-3.0", "WebKit2-4.1"})
    assert desktop.window_ready() == {"pywebview"}
    finder(monkeypatch, {"webview", "qtpy", "PyQt6", "PyQt6.QtWebEngineWidgets"})
    fake_gi(monkeypatch, None)
    assert desktop.window_ready() == set()                              # KDE with Qt's WebEngine
    finder(monkeypatch, {"webview", "qtpy", "PyQt6"})                   # Qt without its WebEngine: no
    assert desktop.window_ready() == {"gi", "webkit"}


def test_which_linux_this_is(tmp_path):
    rel = tmp_path / "os-release"
    rel.write_text('NAME="Fedora Linux"\nVERSION_ID=41\nID=fedora\n', encoding="utf-8")
    assert desktop.distro(rel) == ["fedora"]
    rel.write_text('NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n', encoding="utf-8")
    assert desktop.distro(rel) == ["linuxmint", "ubuntu", "debian"]
    assert desktop.distro(tmp_path / "missing") == []


def test_the_steps_for_the_window():
    everything = {"pywebview", "gi", "webkit"}
    assert desktop.window_steps(everything, ["fedora"]) == FEDORA
    assert desktop.window_steps(everything, ["linuxmint", "ubuntu", "debian"])[0] == \
        "sudo apt install python3-gi gir1.2-webkit2-4.1"
    assert desktop.window_steps(everything, ["endeavouros", "arch"])[0] == \
        "sudo pacman -S --needed python-gobject webkit2gtk-4.1"
    assert desktop.window_steps(everything, ["gentoo"])[0].startswith("#")       # said, not run
    assert desktop.window_steps({"pywebview", "gi"}, ["fedora"]) == FEDORA[1:]      # no sudo: the system has them
    assert desktop.window_steps({"gi"}, ["fedora"]) == FEDORA[1:]
    assert desktop.window_steps({"pywebview"}, ["fedora"]) == ["pipx inject lanterna pywebview", "lanterna desktop"]
    assert desktop.window_steps({"webkit"}, ["fedora"]) == [FEDORA[0], "lanterna desktop"]
    assert desktop.window_steps(set(), ["fedora"]) == []


def test_the_system_python_is_asked_whether_it_has_the_parts(monkeypatch, tmp_path):
    ran = []

    def run(args, **kw):
        ran.append(args)
        return types.SimpleNamespace(returncode=code)
    system_py = tmp_path / "python3"
    system_py.write_text("")
    monkeypatch.setattr(desktop, "SYSTEM_PY", str(system_py))
    monkeypatch.setattr(desktop.subprocess, "run", run)
    code = 0
    assert desktop._system_has_parts()
    assert ran[0][:3] == [str(system_py), "-I", "-c"] and "WebKit2" in ran[0][3]   # not Lanterna's own Python
    compile(ran[0][3], "probe", "exec")
    code = 1
    assert not desktop._system_has_parts()                              # (no PyGObject or no WebKitGTK there)

    def fails(args, **kw):
        raise OSError("no such file")
    monkeypatch.setattr(desktop.subprocess, "run", fails)
    assert not desktop._system_has_parts()
    monkeypatch.setattr(desktop, "SYSTEM_PY", str(tmp_path / "missing"))
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    assert not desktop._system_has_parts()


def test_readme_says_the_same():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for line in FEDORA[1:]:
        assert f"\n{line}\n" in readme, line
    for cmd in desktop.PARTS.values():
        assert f"`{cmd}`" in readme, cmd
    assert "lanterna desktop --terminal" in readme


# ---------------------------------------------------------------- lanterna desktop
@pytest.fixture
def linux_cli(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, width=200, no_color=True))
    monkeypatch.setattr(sys, "platform", "linux")
    made = []
    monkeypatch.setattr(desktop, "install", lambda window=False: made.append(window) or (Path("lanterna.desktop"),
                                                                                            Path("lanterna.svg")))
    return buf, made


def test_lanterna_desktop_puts_the_window_in_the_menu_where_it_opens(linux_cli, monkeypatch):
    buf, made = linux_cli
    monkeypatch.setattr(desktop, "window_ready", lambda: set())
    assert cli.main(["desktop"]) == 0
    assert made == [True] and "in its own window" in buf.getvalue()


def test_lanterna_desktop_says_what_gives_it_the_window(linux_cli, monkeypatch):
    buf, made = linux_cli
    monkeypatch.setattr(desktop, "window_ready", lambda: {"pywebview", "gi", "webkit"})
    monkeypatch.setattr(desktop, "distro", lambda: ["fedora"])
    assert cli.main(["desktop"]) == 0
    out = buf.getvalue()
    assert made == [False] and "Lanterna opens in the terminal. For its own window:" in out
    assert all(f"  {line}\n" in out for line in FEDORA)
    monkeypatch.setattr(desktop, "distro", lambda: ["gentoo"])
    cli.main(["desktop"])
    assert "Install PyGObject and WebKitGTK 4.1 with your system's package manager, then:" in buf.getvalue()
    buf.truncate(0)
    buf.seek(0)
    monkeypatch.setattr(desktop, "window_ready", lambda: {"pywebview", "gi"})   # Fedora Workstation
    monkeypatch.setattr(desktop, "distro", lambda: ["fedora"])
    cli.main(["desktop"])
    out = buf.getvalue()
    assert "sudo" not in out and all(f"  {line}\n" in out for line in FEDORA[1:])


def test_lanterna_desktop_terminal_keeps_the_terminal_app(linux_cli, monkeypatch):
    buf, made = linux_cli
    monkeypatch.setattr(desktop, "window_ready", lambda: pytest.fail("not asked"))
    assert cli.main(["desktop", "--terminal"]) == 0
    assert made == [False] and "For its own window" not in buf.getvalue()


# ---------------------------------------------------------------- the window without what it needs
def test_the_window_says_what_it_needs_instead_of_failing_silently(monkeypatch, capsys):
    shown = []
    monkeypatch.setattr("lanterna.notify.notify", lambda title, msg: shown.append(msg) or True)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "webview", None)                   # installed without pywebview
    monkeypatch.setattr(desktop, "window_ready", lambda: {"pywebview"})
    assert gui.run_window() == 1
    assert shown and "Lanterna's own window needs a few parts of the system" in shown[0]
    assert "pipx inject lanterna pywebview" in capsys.readouterr().err


def test_no_gtk_webkit_says_so_too_and_the_window_is_named_lanterna(monkeypatch, tmp_path):
    for name in ("get_key", "stored_key"):
        monkeypatch.setattr(keys, name, lambda p: None)

    class NoGui(Exception):
        pass
    started = {}

    def start(func=None, private_mode=True, storage_path=None, icon=None):
        started.update(icon=icon)
        raise NoGui("You must have either QT or GTK with Python extensions installed in order to use pywebview.")
    named = []
    glib = types.SimpleNamespace(set_prgname=named.append, set_application_name=named.append)
    monkeypatch.setitem(sys.modules, "gi.repository", types.SimpleNamespace(GLib=glib))
    monkeypatch.setitem(sys.modules, "gi", types.SimpleNamespace(repository=sys.modules["gi.repository"]))
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(
        create_window=lambda *a, **k: object(), start=start, WebViewException=NoGui))
    shown = []
    monkeypatch.setattr("lanterna.notify.notify", lambda title, msg: shown.append(msg) or True)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(desktop, "window_ready", lambda: {"gi", "webkit"})
    assert gui.run_window() == 1 and shown
    assert named == ["lanterna", "Lanterna"]                            # the dock shows the launcher's icon
    assert started["icon"].endswith("logo.svg") and Path(started["icon"]).is_file()
    monkeypatch.setattr(desktop, "window_ready", lambda: set())         # it should open: a real error, not hidden
    with pytest.raises(NoGui):
        gui.run_window()


# ---------------------------------------------------------------- the frame follows the theme
PREFER_DARK = "gtk-application-prefer-dark-theme"


class FakeSettings:
    def __init__(self, dark: bool):
        self.props = {PREFER_DARK: dark}

    def get_property(self, key):
        return self.props[key]

    def set_property(self, key, value):
        self.props[key] = value


class FakeGnome:
    def __init__(self, scheme: str):
        self.scheme, self.handlers = scheme, []

    def get_string(self, key):
        assert key == "color-scheme"
        return self.scheme

    def connect(self, signal, callback):
        self.handlers.append((signal, callback))


def test_the_window_frame_follows_lanterna_s_theme(monkeypatch):
    gnome = FakeGnome("prefer-dark")
    schema = types.SimpleNamespace(has_key=lambda key: key == "color-scheme")
    source = types.SimpleNamespace(lookup=lambda name, recursive: schema if name == "org.gnome.desktop.interface" else None)
    gio = types.SimpleNamespace(SettingsSchemaSource=types.SimpleNamespace(get_default=lambda: source),
                                Settings=types.SimpleNamespace(new=lambda name: gnome))
    repo = types.SimpleNamespace(Gio=gio, GLib=types.SimpleNamespace(idle_add=lambda func: func()))
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    monkeypatch.setitem(sys.modules, "gi", types.SimpleNamespace(repository=repo))
    settings = FakeSettings(dark=False)                                 # GTK 3's Adwaita: light, also in GNOME's dark style
    gtk = types.SimpleNamespace(Settings=types.SimpleNamespace(get_default=lambda: settings))
    gui.Frame(gtk, "dark")
    assert settings.props[PREFER_DARK] is True
    gui.Frame(gtk, "light")
    assert settings.props[PREFER_DARK] is False
    frame = gui.Frame(gtk, "system")                                    # GNOME's dark style
    assert settings.props[PREFER_DARK] is True
    signal, changed = gnome.handlers[-1]
    gnome.scheme = "default"                                            # switched to light in GNOME's Settings
    changed(gnome, "color-scheme")
    assert signal == "changed::color-scheme" and settings.props[PREFER_DARK] is False
    frame.follow("dark")                                                # switched in Lanterna's Settings
    assert settings.props[PREFER_DARK] is True
    source.lookup = lambda name, recursive: None                        # not GNOME: "system" leaves GTK's own choice
    for own in (True, False):
        settings.props[PREFER_DARK] = own
        gui.Frame(gtk, "system")
        assert settings.props[PREFER_DARK] is own


def test_the_theme_setting_reaches_the_frame():
    followed = []
    api = types.SimpleNamespace(settings=types.SimpleNamespace(theme="dark"))

    def save(patch):
        api.settings.theme = patch.get("theme", api.settings.theme)
        return {"saved": True}
    page = types.SimpleNamespace(save_settings=save)
    gui._frame_follows(page, api, types.SimpleNamespace(follow=followed.append))
    assert page.save_settings({"theme": "light"}) == {"saved": True} and followed == ["light"]
    page.save_settings({"lang": "uk"})
    assert followed == ["light"]                                        # other settings: the frame stays
    import inspect
    assert inspect.getfullargspec(page.save_settings).args[1:] == ["patch"]   # what pywebview hands the page


# ---------------------------------------------------------------- Update now keeps the window
def test_update_now_keeps_the_window(monkeypatch, tmp_path):
    calls = []

    def pinned(args):                                                   # a test version: installed from its tag
        calls.append(args)
        return (0, "lanterna is already at latest version 1.1.8b7") if args[0] == "upgrade" else (0, "installed")
    updates.pipx_update("1.1.8", pinned, keep=(["--system-site-packages"], True))
    assert calls[1] == ["install", "--force", "--system-site-packages", f"git+{updates.HOMEPAGE}@v1.1.8"]
    assert calls[2] == ["inject", "lanterna", "pywebview"]
    calls.clear()
    updates.pipx_update("1.1.8", pinned, keep=([], False))              # the terminal app only: as before
    assert calls[1:] == [["install", "--force", f"git+{updates.HOMEPAGE}@v1.1.8"]]
    cfg = tmp_path / "pyvenv.cfg"                                       # what this install has, from its own venv
    cfg.write_text("home = /usr/bin\ninclude-system-site-packages = true\nversion = 3.14.3\n", encoding="utf-8")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object() if name == "webview" else None)
    assert updates.window_parts() == (["--system-site-packages"], True)
    cfg.write_text("include-system-site-packages = false\n", encoding="utf-8")
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    assert updates.window_parts() == ([], False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert updates.window_parts() == ([], False)


def test_new_words_are_translated():
    for s in ["Lanterna is in your app menu now, in its own window. Press Super and type Lanterna.",
              "Lanterna opens in the terminal. For its own window:",
              "Install PyGObject and WebKitGTK 4.1 with your system's package manager, then:",
              "Lanterna's own window needs a few parts of the system. Until then, type lanterna in a terminal; "
              "lanterna desktop says what to install."]:
        for lang in set(i18n.LANGS) - {"en"}:
            assert i18n.t(s, lang) != s, (lang, s)
