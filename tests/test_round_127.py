"""Test versions (betas) before a release, and the Connectors window: logos and the header buttons."""
import json
import re
import subprocess
import sys
from pathlib import Path

from lanterna import connectors
from lanterna.updates import newer

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "lanterna" / "ui"


def test_a_beta_comes_before_its_release():
    assert newer("1.1.6", "1.1.6b1")                 # the release reaches people who tried the beta
    assert newer("1.1.6b2", "1.1.6b1") and newer("v1.1.6b1", "1.1.5")
    assert not newer("1.1.5", "1.1.6b1") and not newer("1.1.6b1", "1.1.6") and not newer("1.1.5", "1.1.5")
    assert newer("1.2.0", "1.1.9") and newer("1.1.10", "1.1.9")


def test_beta_notes_come_from_unreleased():
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "release_notes.py"), "9.9.9b1"], capture_output=True,
                         encoding="utf-8", check=True).stdout
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if "## Unreleased" in text:
        assert out.startswith("## 9.9.9b1 — test version") and "doesn't offer it as an update" in out
    assert "## 9.9.9 " not in out
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "--prerelease" in wf                      # GitHub's latest release (what the app checks) skips these


def test_connector_logos_are_bundled_and_match_the_catalog():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert html.index('src="logos.js"') < html.index('src="app.js"')
    js = (UI / "logos.js").read_text(encoding="utf-8")
    logos = json.loads(re.search(r"const LOGOS = (\{.*\});", js).group(1))
    ids = {c["id"] for c in connectors.CATALOG}
    assert len(logos) >= 45 and set(logos) <= ids
    for cid, (hexc, path) in logos.items():
        assert re.fullmatch(r"[0-9A-Fa-f]{6}", hexc), cid
        assert re.fullmatch(r"[MmZzLlHhVvCcSsQqTtAaEe0-9.,\- ]+", path), cid   # path data only, nothing to run
    assert "CC0" in js and "http" not in js                                    # nothing is loaded from the internet
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert "connLogo(c.name, c.id)" in app and 's.catalog' in app


def test_connectors_header_buttons_are_not_squares():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.dialog header \.cn-seg button \{[^}]*width: auto", css)
    assert re.search(r"\.dialog header \.cn-own \{[^}]*width: auto[^}]*white-space: nowrap", css)
