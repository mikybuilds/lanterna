"""Round 135 (1.1.8b5): a light theme.

- Settings → General → Theme: Dark (as before), Light or Like the system. It is kept on this computer (not synced)
  and works at once; the window's own color before the page draws follows it, so there is no dark flash, and the
  page picks it before its first paint. Like the system follows Windows or GNOME, also when it switches while
  Lanterna is open.
- The light theme is warm paper with the same lantern. Amber is darker where it is text or a thin line (on white
  the bright one reads at 1.9:1); the buttons with dark words keep the bright amber. All text reads at least 4.5:1,
  as in the dark theme. The colors that were fixed for the dark theme (code, the user's message, dialogs' veil,
  shadows) are tokens now.
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
@pytest.mark.parametrize("fg", ["text", "muted", "faint", "amber", "amber-2", "red", "green", "err-text"])
def test_light_text_reads_on_every_background(fg):
    for bg in ("bg", "side", "surface", "surface-2"):
        assert _contrast(LIGHT[fg], LIGHT[bg]) >= 4.5, (fg, bg, round(_contrast(LIGHT[fg], LIGHT[bg]), 2))


def test_light_text_on_tinted_backgrounds():
    tint = _over(LIGHT["amber-soft"], LIGHT["bg"])                       # badges, tags, chosen options
    assert _contrast(LIGHT["amber-2"], tint) >= 4.5 and _contrast(LIGHT["amber"], tint) >= 4.5
    err = _over("rgba(240, 113, 103, .07)", LIGHT["bg"])                    # .err-box
    assert _contrast(LIGHT["err-text"], err) >= 4.5
    green = _over("rgba(91, 208, 138, .12)", LIGHT["bg"])                   # .badge.green
    assert _contrast(LIGHT["green"], green) >= 4.5
    assert _contrast("#1B1407", DARK["fill"]) >= 7 and _contrast("#1B1407", DARK["fill-2"]) >= 7   # dark words on amber
    focused = re.search(r':root\[data-theme="light"\] \.box:focus-within textarea::placeholder \{ color: (#[0-9A-F]{6}); \}',
                        CSS).group(1)
    assert _contrast(focused, LIGHT["surface"]) >= 4.5
    assert _contrast("#F5B544", LIGHT["surface"]) < 2                       # why amber text is darker there


def test_the_light_theme_only_changes_colors_that_exist():
    assert set(LIGHT) <= set(DARK), set(LIGHT) - set(DARK)
    for name in ("strong", "user-top", "code-bg", "glass", "float", "veil", "shine", "err-text", "zebra", "card", "well",
                 "rule", "shadow", "shadow-soft", "smoke", "bg", "text", "amber"):
        assert name in LIGHT, name                                          # each one the dark theme fixed has a light one
    assert "fill" not in LIGHT and "fill-2" not in LIGHT                   # the buttons keep the lantern's amber
    assert "color-scheme: light" in CSS[_at:CSS.index("}", _at)]


def test_no_dark_only_color_is_left_in_the_rules():
    rules = CSS[CSS.index("}") + 1:]
    rules = rules[:rules.index(':root[data-theme="light"]')] + rules[rules.index("}", rules.index(':root[data-theme="light"]')):]
    for fixed in ("#1E2539", "#0A0D15", "#FFC2BC", "#FFE9B8", "rgba(4, 6, 12", "rgba(20, 25, 41", "rgba(26, 32, 51",
                  "rgba(0, 0, 0, .8)", "rgba(0, 0, 0, .9)", "rgba(0, 0, 0, .45)", "rgba(214, 220, 232", "color: #fff; }"):
        assert fixed not in rules, fixed
    for rule in (".btn.primary {", ".send {"):                             # dark words: the bright amber in both themes
        body = CSS[CSS.index(rule):CSS.index("}", CSS.index(rule))]
        assert "linear-gradient(180deg, var(--fill-2), var(--fill))" in body and "color: #1B1407" in body


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
