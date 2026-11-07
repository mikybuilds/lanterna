"""Round 109: reading answers aloud (Windows voices or Piper as a separate download) and Settings tabs."""
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import httpx

from lanterna import gui, keys, speech
from lanterna.store import Store

UI = Path(gui.__file__).parent / "ui"


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


def test_only_the_words_are_read():
    text = "# План\n**Купи** хліб і [молоко](https://shop.example).\n```py\nprint(1)\n```\n- яйця\n| a | b |\n|---|---|"
    out = speech.speakable(text)
    assert "print" not in out and "https" not in out and "*" not in out and "#" not in out
    assert "План" in out and "Купи хліб і молоко" in out and "яйця" in out
    assert len(speech.speakable("слово " * 5000)) == speech.MAX_CHARS


def test_every_piper_file_is_pinned():
    for url, sha, size in speech.PIPER_FILES.values():
        assert url.startswith("https://github.com/rhasspy/piper/releases/download/2023.11.14-2/")
        assert len(sha) == 64 and size > 1_000_000
    assert speech._VOICES_AT.count("/resolve/") == 1 and "/resolve/main/" not in speech._VOICES_AT    # a fixed revision
    for lang in ("uk", "en", "it", "de", "es", "fr", "pl"):
        path, osha, osize, jsha, jsize = speech.VOICES[lang]
        assert len(osha) == 64 and len(jsha) == 64 and osize > 10_000_000 and jsize > 500


def test_piper_download_is_checked_and_unpacked(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("piper/piper.exe", b"MZ fake")
        z.writestr("../evil.txt", b"no")
    engine, voice, conf = buf.getvalue(), b"onnx" * 10, b"{}"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(speech.PIPER_FILES, "win32", ("https://x.test/piper_windows_amd64.zip",
                                                      hashlib.sha256(engine).hexdigest(), len(engine)))
    monkeypatch.setitem(speech.VOICES, "uk", ("uk/x/uk_UA-test-medium", hashlib.sha256(voice).hexdigest(), len(voice),
                                              hashlib.sha256(conf).hexdigest(), len(conf)))
    files = {"piper_windows_amd64.zip": engine, "uk_UA-test-medium.onnx": voice, "uk_UA-test-medium.onnx.json": conf}
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=files[r.url.path.rsplit("/", 1)[1]])))
    p = speech.Piper(tmp_path / "piper")
    p._download_all("uk", http)
    st = p.status("uk")
    assert st["phase"] == "ready" and st["engine"] and st["voice"], st
    assert not (tmp_path / "evil.txt").exists() and not list((tmp_path / "piper").glob("*.part"))


def test_a_changed_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(speech.PIPER_FILES, "win32", ("https://x.test/piper_windows_amd64.zip", "0" * 64, 10))
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"something else")))
    p = speech.Piper(tmp_path / "piper")
    p._download_all("uk", http)
    st = p.status("uk")
    assert st["phase"] == "error" and not st["engine"] and not list((tmp_path / "piper").glob("*"))


def test_not_ready_and_off(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api.save_settings({"tts": "piper"})
    assert api.tts_say("Привіт") == {"ok": False, "error": "not_ready"}
    api.save_settings({"tts": "loud"})                       # unknown: ignored
    assert api.settings.tts == "piper"
    api.save_settings({"tts": "off"})
    assert api.tts_play("Привіт")["error"] == "off"
    assert api.tts_status()["engine"] == "off" and "uk" in api.tts_status()["piper_langs"]


def test_the_window_has_read_aloud_and_its_methods():
    js = (UI / "app.js").read_text(encoding="utf-8")
    for m in ("tts_status", "tts_setup", "tts_setup_cancel", "tts_say"):
        assert m in gui.METHODS
    assert "tts_play" not in gui.METHODS                     # the page plays sound itself
    assert "function speak(" in js and "speechSynthesis" in js and "addSay(bot, text_)" in js
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'id="i-speak"' in html and 'id="i-stop"' in html


def test_settings_have_tabs_for_every_section():
    js = (UI / "app.js").read_text(encoding="utf-8")
    import re
    body = js[js.index("function openSettings()"):js.index("const paintPicks")]
    heads = set(re.findall(r'<h4[^>]*>\$\{t\("([^"]+)"\)\}', body))
    tabs = js[js.index("const SET_TABS"):js.index("let setTab")]
    missing = [h for h in heads if f'"{h}"' not in tabs]
    assert not missing, missing
    assert "settingsTabs(v, body)" in js


def test_windows_voices_make_a_wav(tmp_path, monkeypatch):
    if sys.platform != "win32" or not speech.windows_voices():
        import pytest
        pytest.skip("no Windows speech here")
    lang = speech.windows_voices()[0][1].split("-")[0]
    api = _api(tmp_path, monkeypatch)
    api.save_settings({"tts": "system", "lang": lang if lang in ("en", "it", "de", "es", "fr", "pl", "uk") else "en"})
    r = api.tts_say("Hello, this is a test.")
    assert r["ok"] and r["wav"].startswith("UklGR")             # "RIFF"


def test_no_windows_voice_for_the_language_is_said_clearly(monkeypatch):
    monkeypatch.setattr(speech, "windows_voices", lambda: [("Zira", "en-US")])
    monkeypatch.setattr(sys, "platform", "win32")
    import pytest
    with pytest.raises(speech.SpeechError) as e:
        speech.windows_say("Привіт", "uk")
    assert e.value.kind == "no_voice"
