"""Stage 6: update check, secrets scan, packaging files."""
import importlib.util
import json
import re
from pathlib import Path

import httpx

from lanterna import HOMEPAGE, __version__, updates

ROOT = Path(__file__).parents[1]


def _scanner():
    spec = importlib.util.spec_from_file_location("scan_secrets", ROOT / "tools" / "scan_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_update_check_reads_latest_release_only():
    seen = []

    def h(req):
        seen.append((req.method, req.url.path, req.content))
        return httpx.Response(200, json={"tag_name": "v9.0.0"})

    r = updates.check(transport=httpx.MockTransport(h))
    assert r["newer"] and r["latest"] == "9.0.0" and r["url"].startswith(HOMEPAGE)
    assert seen == [("GET", "/repos/" + "/".join(HOMEPAGE.split("/")[-2:]) + "/releases/latest", b"")]


def test_update_check_is_quiet_when_offline_or_unpublished():
    def missing(req):
        return httpx.Response(404, json={"message": "Not Found"})

    def offline(req):
        raise httpx.ConnectError("offline")

    for h in (missing, offline):
        r = updates.check(transport=httpx.MockTransport(h))
        assert r["latest"] == "" and r["newer"] is False


CHANGELOG_BODY = "# Changelog\n\n## 0.2.0 — better\n\n**New**\n- Update notice\n- Faster start\n\n## 0.1.0 — first\n- Old thing\n"


def test_update_check_reads_notes_and_downloads():
    def h(req):
        return httpx.Response(200, json={"tag_name": "v0.2.0", "body": CHANGELOG_BODY, "assets": [
            {"name": "Lanterna-Setup-0.2.0.exe", "browser_download_url": HOMEPAGE + "/releases/download/v0.2.0/Lanterna-Setup-0.2.0.exe"}]})

    r = updates.check(transport=httpx.MockTransport(h))
    assert r["notes"] == ["Update notice", "Faster start"]
    assert updates.release_notes(CHANGELOG_BODY, "0.1.0") == ["Old thing"]
    assert updates.release_notes(CHANGELOG_BODY, "0.1") == []          # whole version only, no prefix match
    how = updates.how_to("installer", "0.2.0", r["assets"])
    assert how["download"].endswith("/Lanterna-Setup-0.2.0.exe") and how["file"] == "Lanterna-Setup-0.2.0.exe"
    assert updates.how_to("portable", "0.2.0", {})["download"].endswith("/releases/latest")   # no asset list: release page
    assert updates.how_to("pipx", "0.2.0")["command"] == "pipx upgrade lanterna"
    assert updates.how_to("pip", "0.2.0")["command"] == "pip install --upgrade git+" + HOMEPAGE
    assert updates.install_kind() in ("source", "pip", "pipx")             # tests never run frozen


def test_api_update_steps_are_translated_and_can_be_turned_off(tmp_path, monkeypatch):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    calls = []
    monkeypatch.setattr(updates, "check", lambda: calls.append(1) or {
        "current": "0.1.0", "latest": "0.2.0", "newer": True, "url": "u", "notes": [], "assets": {}})
    monkeypatch.setattr(updates, "install_kind", lambda: "installer")
    a = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    a.save_settings({"lang": "uk"})
    r = a.update_notice()
    assert r["newer"] and "assets" not in r and r["download"].endswith("/releases/latest")
    assert r["steps"][0] == "Натисни «Завантажити» і збережи Lanterna-Setup-0.2.0.exe."
    a.save_settings({"update_check": False})
    assert a.settings.update_check is False
    assert a.update_notice()["newer"] is False and len(calls) == 1      # off: no request at all


def test_version_compare():
    assert updates.newer("0.1.1", "0.1.0") and updates.newer("1.0", "0.9.9")
    assert not updates.newer("0.1.0", "0.1.0") and not updates.newer("0.0.9", "0.1.0")


def test_repository_has_no_secrets_or_personal_data():
    found = _scanner().scan_files()
    assert not found, found


def test_scanner_catches_keys_mails_and_paths():
    s = _scanner()
    sample = " ".join(["gs" + "k_" + "a1" * 15, "AI" + "za" + "B" * 35, "sk-or-v1-" + "ab" * 16,
                       "gh" + "p_" + "x" * 36, "someone" + "@" + "mail.it", "C:" + "\\Users\\" + "anna\\x",
                       "-----BEGIN " + "PRIVATE KEY-----"])
    kinds = {f.split(": ")[1] for f in s.scan_text(sample, "x")}
    assert {"Groq key", "Google API key", "OpenRouter key", "GitHub token", "e-mail address", "personal path",
            "private key"} <= kinds
    assert not s.scan_text("Co-Authored-By: Claude <noreply" + "@" + "anthropic.com>", "x")


def test_installer_and_release_files_agree():
    iss = (ROOT / "packaging" / "lanterna.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss and "Lanterna-Setup-{#AppVersion}" in iss
    rel = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "Lanterna-Setup-$env:VERSION.exe" in rel and "--selfcheck" in rel and "scan_secrets.py --history" in rel
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(r"[a-z]", __version__):           # a test version takes the notes from "Unreleased"
        assert log.count("## Unreleased") == 1
    else:
        assert log.count(f"## {__version__}") == 1
    assert 'throw "tests failed"' in rel            # a failed test must stop the release


def test_vault_errors_are_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna import keys
    from lanterna.app import Api
    from lanterna.providers import Client
    from lanterna.store import Store

    monkeypatch.setattr(Client, "list_models", lambda self: ["m"])

    def no_vault(p, k):
        raise RuntimeError("No recommended backend was available")

    monkeypatch.setattr(keys, "set_key", no_vault)
    r = Api(store=Store(tmp_path / "t.db"), scheduler=False).check_key("groq", "gsk_test")
    assert r == {"ok": False, "error": "vault", "message": "No recommended backend was available"}


def test_selfcheck_report(tmp_path):
    from lanterna.gui import selfcheck
    out = tmp_path / "r.json"
    selfcheck(str(out))
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["ui"] is True and rep["version"] == __version__ and rep["pypdf"] == "ok" and rep["crypto"] == "ok"
    assert re.match(r"\d+\.\d+\.\d+", rep["version"])


def test_desktop_launcher_for_gnome(tmp_path, monkeypatch):
    from lanterna import desktop
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    desk, icon = desktop.install()
    text = desk.read_text(encoding="utf-8")
    assert desk == tmp_path / "applications" / "lanterna.desktop" and icon.is_file()
    assert "Name=Lanterna" in text and "Terminal=true" in text and "Icon=lanterna" in text
    exec_line = next(l for l in text.splitlines() if l.startswith("Exec="))
    assert "lanterna" in exec_line
    assert desktop.remove() and not desk.exists() and not icon.exists()
