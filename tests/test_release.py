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
    assert (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").count(f"## {__version__}") == 1


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
    assert rep["ui"] is True and rep["version"] == __version__ and rep["pypdf"] == "ok"
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
