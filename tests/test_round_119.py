"""Round 119: GitHub Models closed (30 July 2026): it's gone from Lanterna, and a service that answers with
something other than a model list gives a clear message instead of a JSONDecodeError."""
import json

import httpx

from lanterna import keys
from lanterna.config import Settings
from lanterna.providers import PROVIDERS, RETIRED, Client, ProviderError


def test_github_models_is_gone():
    assert "github" not in PROVIDERS and "github" in RETIRED
    assert all("models.github.ai" not in p.base_url for p in PROVIDERS.values())


def test_a_plain_ok_is_a_clear_error():
    c = Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="OK\r\n")))
    try:
        c.list_models()
        raise AssertionError("no error")
    except ProviderError as e:
        assert e.kind == "other" and e.status == 200 and "list of models" in str(e)


def test_check_key_says_the_service_answered_oddly(tmp_path, monkeypatch):
    from lanterna import app as appmod
    from lanterna.store import Store
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    saved = {}
    monkeypatch.setattr(keys, "set_key", lambda n, v: saved.__setitem__(n, v))
    real = Client

    def client(p, key, **kw):
        return real(p, key, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="OK")))
    monkeypatch.setattr(appmod, "Client", client)
    api = appmod.Api(store=Store(tmp_path / "t.db"), scheduler=False)
    r = api.check_key("mistral", "some-key")
    assert r["ok"] is False and r["error"] == "bad_reply" and not saved
    assert api.check_key("github", "some-key") == {"ok": False, "error": "empty"}


def test_old_settings_and_cache_that_name_it(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    from lanterna import config, discovery
    (config.config_dir() / "settings.json").write_text(json.dumps({"provider": "github", "lang": "uk"}), encoding="utf-8")
    s = Settings.load()
    assert s.provider == "" and s.lang == "uk"
    import datetime
    discovery._cache_file().write_text(json.dumps({"at": datetime.datetime.now().isoformat(), "providers": ["groq"], "candidates": [
        {"provider": "github", "model": "openai/gpt-4.1", "score": 90}, {"provider": "groq", "model": "llama-3.3-70b-versatile", "score": 80}]}),
        encoding="utf-8")
    assert [c.provider for c in discovery.load_cache(["groq"])] == ["groq"]


def test_window_message():
    from pathlib import Path

    from lanterna import gui
    js = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'r.error === "bad_reply"' in js
