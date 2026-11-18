"""Round 135 (1.1.8b5): a light theme.

- Settings → General → Theme: Dark (as before), Light or Like the system. It is kept on this computer (not synced)
  and works at once; the window's own color before the page draws follows it, so there is no dark flash, and the
  page picks it before its first paint. Like the system follows Windows or GNOME, also when it switches while
  Lanterna is open.
- The light theme has the same lantern. Amber is darker where it is text or a thin line (on white the bright one
  reads at 1.9:1). All text reads at least 4.5:1, as in the dark theme. Every color is a token (1.1.10b9: the
  site's charcoal or light gray and one amber; the main buttons are the text's color with the page's on them).
- The terminal follows it (Ctrl+P → Light theme / Dark theme).
"""
import asyncio
import re
import sys
import types
from pathlib import Path

import pytest

from lanterna import gui, i18n
from lanterna.config import Settings
from lanterna.sync import PREFS

pytest.importorskip("textual")
from lanterna.tui import LIGHT as TUI_LIGHT  # noqa: E402
from lanterna.tui import LanternaApp  # noqa: E402
from test_tui import api, chat_ready, wait_for  # noqa: E402,F401  (the fake model and vault)

UI = Path(gui.__file__).parent / "ui"
CSS = (UI / "style.css").read_text(encoding="utf-8")


def _tokens(block: str) -> dict:
    return dict(re.findall(r"^\s*--([a-z0-9-]+):\s*([^;]+);", block, re.M))


DARK = _tokens(CSS[:CSS.index("}")])
_at = CSS.index(':root[data-theme="light"] {')
LIGHT = _tokens(CSS[_at:CSS.index("}", _at)])


def _luminance(color: str) -> float:
    def part(h):
        c = int(h, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (part(color[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _over(rgba: str, bg: str) -> str:
    """A see-through color as it looks over `bg`."""
    *rgb, a = (float(x) for x in re.findall(r"[\d.]+", rgba))
    base = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(c * a + b * (1 - a)):02X}" for c, b in zip(rgb, base))


# ---------------------------------------------------------------- the colors
# 1.1.10b9: the window took the look of the author's site: charcoal (or light gray) and one amber, no gradients.
TEXTS = ("text", "muted", "faint", "amber", "red", "green")
BACKS = ("bg", "bg-2", "side", "surface", "surface-2")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_text_reads_on_every_background(theme):
    T = DARK if theme == "dark" else LIGHT
    for fg in TEXTS:
        for bg in BACKS:
            assert _contrast(T[fg], T[bg]) >= 4.5, (theme, fg, bg, round(_contrast(T[fg], T[bg]), 2))
    for bg in ("bg", "side", "surface"):                                   # the edge of a box you type in: 3:1 at least
        assert _contrast(T["edge"], T[bg]) >= 3, (theme, bg, round(_contrast(T["edge"], T[bg]), 2))
    assert _contrast(T["bg"], T["text"]) >= 7                               # the main button: the page's color on the text's


def test_the_light_theme_only_changes_colors_that_exist():
    assert set(LIGHT) <= set(DARK), set(LIGHT) - set(DARK)
    colors = {k for k, v in DARK.items() if "#" in v or "rgba(" in v}
    assert len(colors) >= 20 and colors <= set(LIGHT), colors - set(LIGHT)   # each color of the dark theme has a light one
    assert "color-scheme: light" in CSS[_at:CSS.index("}", _at)]
    assert _contrast("#F5B544", LIGHT["surface"]) < 2                       # why amber text is darker there


def test_colors_come_only_from_the_tokens():
    rules = CSS[CSS.index("}") + 1:]
    rules = rules[:rules.index(':root[data-theme="light"]')] + rules[rules.index("}", rules.index(':root[data-theme="light"]')):]
    rules = re.sub(r"/\*.*?\*/", "", rules, flags=re.S)
    assert not re.findall(r"#[0-9A-Fa-f]{3,8}\b", rules) and "rgba(" not in rules and "rgb(" not in rules
    grads = [rules.rfind("}", 0, m.start()) for m in re.finditer("gradient", rules)]
    assert len(grads) == 1 and rules[grads[0]:].lstrip("} \n").startswith(".lim.unknown .lim-track")   # stripes: "no data"
    assert set(re.findall(r"box-shadow: ([^;]+);", rules)) == {"var(--pop)"}                          # only what floats
    assert "blur(" not in rules
    for rule in (".btn.primary {", ".send {"):                             # the main buttons: the text's color, the page's words
        body = CSS[CSS.index(rule):CSS.index("}", CSS.index(rule))]
        assert "background: var(--text)" in body and "color: var(--bg)" in body


# ---------------------------------------------------------------- the setting
def test_the_page_picks_the_theme_before_its_first_paint():
    html = (UI / "index.html").read_text(encoding="utf-8")
    head = html[:html.index("</head>")]
    assert head.index('localStorage.getItem("theme")') < head.index('<link rel="stylesheet" href="style.css">')
    assert 'prefers-color-scheme: light' in head and "dataset.theme" in head


def test_the_window_has_the_setting():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'const THEMES = ["dark", "light", "system"];' in js
    i = js.index("function setTheme(v)")
    fn = js[i:js.index("\n}\n", i)]
    assert 'lightSystem.matches ? "light" : "dark"' in fn and 'localStorage.setItem("theme", theme)' in fn
    assert 'lightSystem.addEventListener("change"' in js and 'window.addEventListener("focus", () => { if (theme === "system")' in js
    assert "if (S.settings.theme && S.settings.theme !== theme) setTheme(S.settings.theme);" in js     # the settings file decides
    assert 't({ dark: "Dark", light: "Light", system: "Like the system" }[v])' in js and 'id="seg-theme"' in js
    assert "S = await api.save_settings({ theme });" in js


def test_the_setting_is_kept_on_this_computer(api):  # noqa: F811
    assert Settings().theme == "dark" and "theme" not in PREFS            # each computer its own
    for v in ("light", "system", "dark"):
        assert api.save_settings({"theme": v})["settings"]["theme"] == v
    assert api.save_settings({"theme": "neon"})["settings"]["theme"] == "dark"


def test_the_window_color_before_the_page_draws(monkeypatch):
    assert gui.DARK_BG == DARK["bg"] and gui.LIGHT_BG == LIGHT["bg"]
    assert gui.window_color("light") == gui.LIGHT_BG and gui.window_color("dark") == gui.DARK_BG
    assert gui.window_color("anything") == gui.DARK_BG
    monkeypatch.setattr(gui.sys, "platform", "linux")
    assert gui.window_color("system") == gui.DARK_BG                       # the page sets it right a moment later
    monkeypatch.setattr(gui.sys, "platform", "win32")
    for light, want in ((1, gui.LIGHT_BG), (0, gui.DARK_BG)):
        class Key:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        fake = types.SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=lambda *a: Key(),
                                     QueryValueEx=lambda k, name, light=light: (light, 4))
        monkeypatch.setitem(sys.modules, "winreg", fake)
        assert gui.window_color("system") == want
    def broken(*a):
        raise OSError("no key")
    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=broken))
    assert gui.window_color("system") == gui.DARK_BG


def test_new_strings_are_translated_everywhere():
    for s in ("Theme", "Dark", "Light", "Like the system", "Light theme", "Dark theme"):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)


# ---------------------------------------------------------------- the terminal
def test_the_terminal_follows_and_switches(api):  # noqa: F811
    api.save_settings({"onboarded": True, "name": "Bo", "lang": "uk", "provider": "groq", "theme": "light"})
    assert not TUI_LIGHT.dark and TUI_LIGHT.background == LIGHT["bg"] and TUI_LIGHT.foreground == LIGHT["text"]

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(120, 40)) as pilot:
            assert await wait_for(pilot, lambda: chat_ready(app))
            assert app.theme == "lanterna-light"
            scr = app.screen
            names = [c.title for c in app.get_system_commands(scr)]
            assert "Темна тема" in names and "Світла тема" not in names
            scr.action_toggle_theme()
            await pilot.pause()
            assert app.theme == "lanterna" and api.settings.theme == "dark"
            assert "Світла тема" in [c.title for c in app.get_system_commands(scr)]
            scr.action_toggle_theme()
            assert app.theme == "lanterna-light" and api.settings.theme == "light"
    asyncio.run(go())
