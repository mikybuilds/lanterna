"""More ready-made connectors (each checked: the address answers, Lanterna can register itself, the sign-in page
opens), and the Browse page shows every category at once, like Claude's directory."""
import json
from pathlib import Path

from lanterna import connectors, i18n

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "lanterna" / "ui"
NEW = ["basecamp", "craft", "shortcut", "jotform", "fathom", "otter", "krisp", "whimsical", "picsart", "heygen",
       "renderai", "digitalocean", "railway", "heroku", "lovable", "postman", "buildkite", "planetscale", "workos",
       "sanity", "mux", "cf-browser", "cf-builds", "replicate", "fal", "ref", "deepwiki", "gitmcp", "kaggle", "ibkr",
       "paddle", "alphavantage", "coingecko", "cryptocom", "scite", "consensus", "parallel", "jina", "cf-radar",
       "mapbox", "beehiiv", "bitly", "porkbun", "godaddy"]


def test_more_ready_connectors():
    ready = [c for c in connectors.CATALOG if c["auth"] in ("oauth", "open")]
    assert len(ready) >= 115
    for cid in NEW:
        c = connectors.BY_ID[cid]
        assert c["url"].startswith("https://") and c["cat"] in connectors.CATEGORIES and c["about"], cid
    for cid in ("xero", "zendesk", "elevenlabs", "render", "indeed", "zoominfo"):
        assert connectors.BY_ID[cid]["auth"] == "closed" and connectors.BY_ID[cid]["why"]


def test_new_texts_are_translated():
    for lang in ("de", "es", "fr", "pl"):
        d = json.loads((ROOT / "src" / "lanterna" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
        for c in connectors.CATALOG:
            text = c["about"] or c["why"]
            assert text in d, (lang, c["id"])
    for c in connectors.CATALOG:
        text = c["about"] or c["why"]
        assert text in i18n._T and i18n._T[text]["uk"], c["id"]


def test_browse_shows_every_category():
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert "catSection(k, n)" in app and 'data-cat="${k}"' in app and "cn-more-hint" in app
    assert ".cn-more-hint" in (UI / "style.css").read_text(encoding="utf-8")
