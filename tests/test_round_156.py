"""Round 156 (1.1.11b10): Lanterna's side panel in Chrome shows the chat or the note, never both.

A screenshot from the user: scrolling down in the side panel went past the chat into a dark empty screen with the
lantern and an empty button. The note for when Lanterna isn't running (main#off) was always on the page, under the
chat: sidepanel.css gives the iframe and main a display of their own, and that wins over the hidden attribute
sidepanel.js sets. The same made the panel look empty when Lanterna wasn't running: the note was under a whole
screen of the hidden (empty) iframe. Lanterna's own window has had the rule since long ago (style.css).
"""
import json
import re
from pathlib import Path

from lanterna import browser

EXT = Path(browser.__file__).parent / "chrome"
UI = Path(browser.__file__).parent / "ui"


def rules(css: str) -> list[tuple[str, str]]:
    """(selector, declarations) of each rule, the ones inside @media too."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def hides_always(css: str) -> bool:
    return any(s == "[hidden]" and re.search(r"display:\s*none\s*!important", b) for s, b in rules(css))


def test_hidden_hides_in_the_side_panel_whatever_display_its_parts_have():
    css = (EXT / "sidepanel.css").read_text(encoding="utf-8")
    js = (EXT / "sidepanel.js").read_text(encoding="utf-8")
    page = (EXT / "sidepanel.html").read_text(encoding="utf-8")
    assert '<iframe id="ui"' in page and '<main id="off" hidden>' in page
    assert 'frame.hidden = true' in js and '$("off").hidden = true' in js      # one of the two at a time
    shown = {s for s, b in rules(css) if re.search(r"(^|;)\s*display:", b)}
    assert {"iframe", "main"} <= shown                      # a display of their own: without the rule both show
    assert hides_always(css)
    assert hides_always((UI / "style.css").read_text(encoding="utf-8"))         # the window: the same rule


def test_the_fixed_panel_reaches_chrome():
    """Chrome keeps an unpacked extension as it was until Lanterna sees an older version connect: then it copies
    the new files and reloads it (app._browser_connected). b9's extension was 1.1.11.7."""
    m = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert tuple(int(x) for x in m["version"].split(".")) > (1, 1, 11, 7)
    assert browser.manifest_version() == m["version"]
