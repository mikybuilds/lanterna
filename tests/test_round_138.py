"""Round 138 (1.1.8b8): Lanterna's own window on Linux (Fedora and the others).

- `lanterna desktop` puts Lanterna's own window in the app menu (lanterna-gui, no terminal) when it can open
  here: pywebview with the system's GTK WebKit, or Qt's WebEngine. Otherwise the menu opens the full-screen app in
  the terminal as before, and the command says exactly what gives it the window on this distribution (Fedora,
  Ubuntu/Debian/Mint, Arch), or what to look for elsewhere. `--terminal` keeps the terminal app.
- The window is "lanterna" to the desktop, so the dock and Alt+Tab show it with the launcher's name and icon.
- Started from the menu without what it needs, the window says so in a notification (no terminal to read it in)
  instead of failing silently; the terminal app works meanwhile.
"""
import io
import sys
import types
from pathlib import Path

import pytest
from rich.console import Console

from lanterna import cli, desktop, gui, i18n, keys

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
    assert desktop.window_ready() == {"pywebview", "gi", "webkit"}      # a fresh pipx install
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
    assert desktop.window_steps({"pywebview"}, ["fedora"]) == ["pipx inject lanterna pywebview", "lanterna desktop"]
    assert desktop.window_steps({"webkit"}, ["fedora"]) == [FEDORA[0], "lanterna desktop"]
    assert desktop.window_steps(set(), ["fedora"]) == []


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


def test_new_words_are_translated():
    for s in ["Lanterna is in your app menu now, in its own window. Press Super and type Lanterna.",
              "Lanterna opens in the terminal. For its own window:",
              "Install PyGObject and WebKitGTK 4.1 with your system's package manager, then:",
              "Lanterna's own window needs a few parts of the system. Until then, type lanterna in a terminal; "
              "lanterna desktop says what to install."]:
        for lang in set(i18n.LANGS) - {"en"}:
            assert i18n.t(s, lang) != s, (lang, s)
