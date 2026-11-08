"""Round 122: Cerebras is gone (its free plan ended in July 2026), and three free services came in: NVIDIA,
Z.ai (only the free GLM Flash models) and Cohere (a small monthly limit, so few test requests). Every service
says what to know before signing up."""
import datetime
import json

import httpx

from lanterna import config, discovery, keys
from lanterna.config import Settings
from lanterna.providers import PROVIDERS, RETIRED, Client


def _client(pid, handler):
    return Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(handler))


def _models(*ids, key="data", field="id"):
    return lambda r: httpx.Response(200, json={key: [{field: i} for i in ids]})


def test_cerebras_is_gone_and_the_lists_agree():
    assert "cerebras" not in PROVIDERS and "cerebras" in RETIRED
    assert sorted(config.RETIRED_IDS) == sorted(RETIRED)
    assert all("cerebras" not in p.base_url for p in PROVIDERS.values())


def test_old_settings_and_cache_that_name_cerebras(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    (config.config_dir() / "settings.json").write_text(json.dumps({"provider": "cerebras", "lang": "uk"}), encoding="utf-8")
    s = Settings.load()
    assert s.provider == "" and s.lang == "uk"
    discovery._cache_file().write_text(json.dumps({"at": datetime.datetime.now().isoformat(), "providers": ["groq"], "candidates": [
        {"provider": "cerebras", "model": "llama-3.3-70b", "score": 80}, {"provider": "groq", "model": "llama-3.3-70b-versatile", "score": 80}]}),
        encoding="utf-8")
    assert [c.provider for c in discovery.load_cache(["groq"])] == ["groq"]


def test_every_cloud_service_says_what_to_know():
    from lanterna.i18n import catalog
    for p in PROVIDERS.values():
        if not p.local:
            assert p.note, p.id
            for lang in ("uk", "it", "de", "es", "fr", "pl"):
                assert p.note in catalog(lang), (p.id, lang)


def test_nvidia_leaves_out_what_isnt_chat():
    c = _client("nvidia", _models("moonshotai/kimi-k2.6", "deepseek-ai/deepseek-v4.1-flash", "nvidia/nemotron-4-340b-reward",
                                  "nvidia/nemotron-parse", "google/deplot", "adept/fuyu-8b", "nvidia/vila", "nvidia/nvclip",
                                  "mistralai/mixtral-8x22b-v0.1", "google/codegemma-7b", "google/gemma-2b",
                                  "writer/palmyra-med-70b", "google/gemma-4-31b-it", "nvidia/llama-3.2-nv-embedqa-1b-v2"))
    got = {x.model for x in discovery.candidates_for(c)}
    assert got == {"moonshotai/kimi-k2.6", "deepseek-ai/deepseek-v4.1-flash", "google/gemma-4-31b-it"}


def test_zai_uses_only_free_flash_models():
    c = _client("zai", _models("glm-5", "glm-4.7", "glm-4.7-flash", "glm-4.7-flashx", "GLM-4.6V-Flash", "glm-4.5-air"))
    assert c.list_models() == ["glm-4.7-flash", "GLM-4.6V-Flash"]
    assert {x.model for x in discovery.candidates_for(c)} == {"glm-4.7-flash", "GLM-4.6V-Flash"}


def test_zai_without_a_model_list_uses_the_known_free_ones():
    for resp in (httpx.Response(404, json={"error": {"message": "not found"}}), httpx.Response(200, json={"data": [{"id": "glm-5"}]})):
        c = _client("zai", lambda r, resp=resp: resp)
        assert c.list_models() == list(PROVIDERS["zai"].known)
        assert all(m.endswith("-flash") for m in c.list_models())


def test_key_check_without_a_list_asks_once(tmp_path, monkeypatch):
    from lanterna import app as appmod
    from lanterna.store import Store
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    saved = {}
    monkeypatch.setattr(keys, "set_key", lambda n, v: saved.__setitem__(n, v))
    seen = []
    status = {"chat": 401}

    def handler(r):
        seen.append(r.url.path)
        if r.url.path.endswith("/models"):
            return httpx.Response(404, json={})
        if status["chat"] != 200:
            return httpx.Response(status["chat"], json={"error": {"message": "bad key"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi"}}]})
    real = Client
    monkeypatch.setattr(appmod, "Client", lambda p, key, **kw: real(p, key, transport=httpx.MockTransport(handler)))
    api = appmod.Api(store=Store(tmp_path / "t.db"), scheduler=False)
    r = api.check_key("zai", "wrong")
    assert r["ok"] is False and r["error"] == "auth" and not saved
    assert seen[-1].endswith("/chat/completions")
    status["chat"] = 200
    assert api.check_key("zai", "right")["ok"] is True and saved == {"zai": "right"}


def test_cohere_list_comes_from_its_own_address_and_is_pinged_once(monkeypatch):
    monkeypatch.setattr(keys, "get_key", lambda n: None)                 # no real keys
    urls = []

    def handler(r):
        urls.append(str(r.url))
        if r.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [{"name": "command-a-03-2025"}, {"name": "command-r-plus-08-2024"},
                                                        {"name": "command-r7b-12-2024"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi"}}]})
    c = _client("cohere", handler)
    found = discovery.discover(ping=True, providers=["cohere"], clients={"cohere": c})
    assert urls[0] == "https://api.cohere.ai/v1/models?endpoint=chat"
    assert [u for u in urls if u.endswith("/chat/completions")] == ["https://api.cohere.ai/compatibility/v1/chat/completions"]
    assert found[0].model == "command-a-03-2025" and found[0].status == "ok"


def test_settings_rows_and_terminal_show_the_note():
    from pathlib import Path

    from lanterna import gui
    js = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert "t(p.note)" in js
    import inspect

    from lanterna import cli, tui
    assert "p.note" in inspect.getsource(cli.ask_key)
    assert 't(p["note"], lang)' in inspect.getsource(tui) and "t(p.note, lang)" in inspect.getsource(tui)
