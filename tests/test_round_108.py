"""Round 108: currency (official NBU rates) and units; audio files turned into text."""
import base64
import time

import httpx

from lanterna import convert, keys, tools, voice
from lanterna.store import Store

NBU = [{"cc": "USD", "rate": 41.5, "exchangedate": "09.11.2026"}, {"cc": "EUR", "rate": 45.0, "exchangedate": "09.11.2026"},
       {"cc": "PLN", "rate": 10.5, "exchangedate": "09.11.2026"}, {"cc": "GBP", "rate": 53.2, "exchangedate": "09.11.2026"},
       {"cc": "JPY", "rate": 0.27, "exchangedate": "09.11.2026"}]


def _nbu(rows=NBU, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=rows)))


# ---------------------------------------------------------------- currency
def test_currency_through_the_hryvnia():
    out = convert.currency(100, "USD", "UAH", http=_nbu())
    assert out.startswith("100 USD = 4 150.00 UAH") and "09.11.2026" in out
    assert convert.currency(90, "євро", "$", http=_nbu()).startswith("90 EUR = 97.59 USD")
    assert convert.currency("1,5", "pln", "грн", http=_nbu()).startswith("1.5 PLN = 15.75 UAH")


def test_currency_errors_are_clear():
    assert "no official rate for XYZ" in convert.currency(1, "XYZ", "UAH", http=_nbu())
    assert convert.currency(1, "USD", "UAH", http=_nbu(status=500)).startswith("Error: the National Bank")
    assert convert.currency("abc", "USD", "UAH", http=_nbu()).startswith("Error: amount")


def test_rates_are_cached_for_an_hour(monkeypatch):
    calls = []
    monkeypatch.setattr(convert, "_cache", {"at": 0.0, "rates": {}, "date": ""})
    from lanterna import tools as tl
    monkeypatch.setattr(tl, "_http", lambda **k: calls.append(1) or _nbu())
    convert.currency(1, "USD", "UAH")
    convert.currency(2, "EUR", "UAH")
    assert len(calls) == 1
    convert._cache["at"] = time.time() - convert.CACHE_FOR - 1
    convert.currency(1, "USD", "UAH")
    assert len(calls) == 2


# ---------------------------------------------------------------- units
def test_units():
    cu = convert.convert_units
    assert cu(5, "km", "mi") == "5 km = 3.1069 mi"
    assert cu(100, "F", "C") == "100 °F = 37.7778 °C"
    assert cu(0, "c", "k") == "0 °C = 273.15 K"
    assert cu(6, "соток", "ha") == "6 a = 0.06 ha"
    assert cu(100, "Mbit", "mb") == "100 mbit = 12.5 mb"
    assert cu(2, "cups", "ml") == "2 cup = 473.18 ml"
    assert cu(1, "kwh", "kcal") == "1 kwh = 860.42 kcal"
    assert "different things" in cu(3, "kg", "m")
    assert "unknown unit xx" in cu(1, "xx", "m")


def test_the_model_gets_both_tools():
    names = {t.name for t in tools.Toolbox(None)._make()}
    assert {"currency", "convert_units"} <= names


# ---------------------------------------------------------------- audio files
def _api(tmp_path, monkeypatch, groq=None):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: groq if n == "groq" else None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


def _wait(api, sid):
    for _ in range(100):
        p = api.poll(sid)
        if p["done"]:
            return p
        time.sleep(0.05)
    raise AssertionError("never finished")


def test_audio_needs_voice_input_set_up(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    tid = api.store.new_thread()
    r = api.send(tid, "що тут?", [{"name": "нотатка.mp3", "data": base64.b64encode(b"ID3...").decode()}])
    assert r["ok"] is False and r["error"] == "file" and "Voice input" in r["message"]
    assert api.store.messages(tid) == []


def test_audio_goes_to_the_model_as_text(tmp_path, monkeypatch):
    from lanterna import app as appmod
    api = _api(tmp_path, monkeypatch, groq="k")
    api.save_settings({"voice": "groq"})
    sent = []

    def fake_groq(data, key, lang="", http=None, name="voice.wav"):
        sent.append((name, data, key))
        return "Купи хліб і молоко"
    monkeypatch.setattr(voice, "transcribe_groq", fake_groq)
    got = {}

    class Conv:
        def __init__(self, *a, **k):
            self.router, self.last_reply = None, "Ось список: хліб, молоко."

        def ask(self, text, images=None):
            got["text"] = text
            yield "Ось список: хліб, молоко."
    monkeypatch.setattr(appmod, "Conversation", Conv)
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: None)
    monkeypatch.setattr(api, "_start_side_jobs", lambda *a: None)
    tid = api.store.new_thread()
    r = api.send(tid, "зроби список", [{"name": "voice.ogg", "data": base64.b64encode(b"OggS").decode()}])
    p = _wait(api, r["stream"])
    assert not p["error"], p
    assert sent == [("voice.ogg", b"OggS", "k")]
    assert "[Audio: voice.ogg, turned into text]" in got["text"] and "Купи хліб" in got["text"]
    first = api.store.messages(tid)[0]
    assert first["role"] == "user" and "Купи хліб" in first["content"] and "🎧 transcribe_audio" in p["tools"]


def test_a_failed_transcription_says_why_and_keeps_the_question(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch, groq="k")
    api.save_settings({"voice": "groq"})
    monkeypatch.setattr(voice, "transcribe_groq", lambda *a, **k: (_ for _ in ()).throw(voice.VoiceError("network", "Groq answered 500")))
    tid = api.store.new_thread()
    r = api.send(tid, "що тут?", [{"name": "a.m4a", "data": base64.b64encode(b"x").decode()}])
    p = _wait(api, r["stream"])
    assert p["error"]["kind"] == "file" and "a.m4a" in p["error"]["message"]
    assert api.store.messages(tid)[0]["content"] == "що тут?\n\n[Audio: a.m4a]"


def test_local_engine_takes_only_what_whisper_reads(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api.save_settings({"voice": "local"})
    monkeypatch.setattr(api._whisper, "status", lambda m: {"engine": True, "model": True})
    assert api._audio_problem(["a.mp3", "b.wav"]) == ""
    assert "a.m4a" in api._audio_problem(["a.m4a"])


def test_groq_gets_the_right_file_type():
    seen = {}

    def answer(req):
        seen["body"] = req.read()
        return httpx.Response(200, json={"text": "привіт"})
    http = httpx.Client(transport=httpx.MockTransport(answer))
    assert voice.transcribe_groq(b"x", "k", http=http, name="Запис.opus") == "привіт"
    assert b'filename="audio.ogg"' in seen["body"] and b"audio/ogg" in seen["body"]
