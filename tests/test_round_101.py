"""1.0: voice input. No real microphone, network or speech engine here."""
import hashlib
import io
import time
import wave
import zipfile

import httpx

from lanterna import keys, voice


def _wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(voice.RATE)
        w.writeframes(b"\0\0" * int(voice.RATE * seconds))
    return buf.getvalue()


def _api(tmp_path, monkeypatch, key=None):
    from lanterna.app import Api
    from lanterna.store import Store
    monkeypatch.setattr(keys, "get_key", lambda n: key if n == "groq" else None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


class FakeRecorder:
    def __init__(self, wav=b"", fail=""):
        self.wav, self.fail, self.recording, self.cancelled = wav, fail, False, False

    def start(self):
        if self.fail:
            raise voice.VoiceError(self.fail)
        self.recording = True

    def stop(self, cancel=False):
        self.recording, self.cancelled = False, cancel
        return b"" if cancel else self.wav


# ---------------------------------------------------------------- small pieces
def test_clean_text_and_length():
    assert voice.clean_text("  [BLANK_AUDIO] hello\n  there [Music] ") == "hello there"
    assert voice.speech_seconds(_wav(1.5)) == 1.5
    assert voice.speech_seconds(b"not a wav") == 0.0


def test_groq_sends_the_recording_and_reads_the_text():
    seen = {}

    def handler(req):
        seen["auth"], seen["url"], seen["body"] = req.headers["authorization"], str(req.url), req.read()
        return httpx.Response(200, json={"text": " Привіт, як справи? "})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert voice.transcribe_groq(_wav(1), "k-test", "uk", http) == "Привіт, як справи?"
    assert seen["url"] == voice.GROQ_URL and seen["auth"] == "Bearer k-test"
    assert b'name="language"' in seen["body"] and b"whisper-large-v3-turbo" in seen["body"]


def test_groq_errors_have_kinds():
    for status, kind in ((401, "no_key"), (500, "network")):
        http = httpx.Client(transport=httpx.MockTransport(lambda r, s=status: httpx.Response(s)))
        try:
            voice.transcribe_groq(_wav(1), "k", "", http)
        except voice.VoiceError as e:
            assert e.kind == kind
        else:
            raise AssertionError("no error")
    try:
        voice.transcribe_groq(_wav(1), "", "")
    except voice.VoiceError as e:
        assert e.kind == "no_key"


# ---------------------------------------------------------------- the local engine
def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_safe_extract_keeps_files_inside(tmp_path):
    arc = tmp_path / "a.zip"
    arc.write_bytes(_zip({"Release/whisper-cli.exe": b"x", "../evil.txt": b"bad", "Release/../ok.txt": b"ok"}))
    voice._safe_extract(arc, tmp_path / "out")
    assert (tmp_path / "out" / "Release" / "whisper-cli.exe").read_bytes() == b"x"
    assert (tmp_path / "out" / "ok.txt").is_file()
    assert not (tmp_path / "evil.txt").exists()


def _wait(w, model="small"):
    for _ in range(200):
        if w.status(model).get("phase") != "downloading":
            return w.status(model)
        time.sleep(0.02)
    raise AssertionError("still downloading")


def test_download_checks_every_file(tmp_path, monkeypatch):
    engine = _zip({"Release/whisper-cli.exe": b"exe", "Release/whisper-cli": b"exe", "../evil.txt": b"bad"})
    model = b"model-bytes" * 100
    monkeypatch.setattr(voice, "ENGINE_FILES", {voice.sys.platform: ("https://x/whisper-bin-x64.zip",
                                                                        hashlib.sha256(engine).hexdigest(), len(engine))})
    monkeypatch.setattr(voice, "MODELS", {"small": ("ggml-small.bin", hashlib.sha256(model).hexdigest(), len(model))})
    monkeypatch.setattr(voice.shutil, "which", lambda n: None)
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=engine if r.url.path.endswith(".zip") else model)))
    w = voice.LocalWhisper(tmp_path / "whisper")
    assert w.status("small")["engine"] is False
    w.setup("small", http)
    st = _wait(w)
    assert st["phase"] == "ready" and st["engine"] and st["model"] and st["done"] == st["total"]
    assert not (tmp_path / "evil.txt").exists()
    assert not list((tmp_path / "whisper").glob("*.part")) and not list((tmp_path / "whisper").glob("*.zip"))


def test_a_changed_file_is_thrown_away(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "MODELS", {"small": ("ggml-small.bin", "0" * 64, 10)})
    monkeypatch.setattr(voice.shutil, "which", lambda n: None)
    root = tmp_path / "whisper"
    for name in ("whisper-cli.exe", "whisper-cli"):                     # the engine is already there
        (root / "engine").mkdir(parents=True, exist_ok=True)
        (root / "engine" / name).write_bytes(b"x")
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"something else")))
    w = voice.LocalWhisper(root)
    w.setup("small", http)
    st = _wait(w)
    assert st["phase"] == "error" and st["error"] == "engine" and not st["model"]
    assert not list(root.glob("ggml-small.bin*"))


# ---------------------------------------------------------------- the app
def test_voice_settings_are_checked(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api.save_settings({"voice": "local", "voice_model": "turbo"})
    assert (api.settings.voice, api.settings.voice_model) == ("local", "turbo")
    api.save_settings({"voice": "loud", "voice_model": "huge"})
    assert (api.settings.voice, api.settings.voice_model) == ("local", "turbo")
    st = api.voice_status()
    assert st["engine"] == "local" and {m["id"] for m in st["models"]} == {"base", "small", "turbo"}


def test_mic_says_what_is_missing(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    api._recorder = FakeRecorder(_wav(1))
    assert api.voice_start() == {"ok": False, "error": "off"}
    api.save_settings({"voice": "groq"})
    assert api.voice_start()["error"] == "no_key"
    api.save_settings({"voice": "local"})
    monkeypatch.setattr(voice.shutil, "which", lambda n: None)
    assert api.voice_start()["error"] == "no_engine"
    assert api._recorder.recording is False


def test_mic_records_and_turns_speech_into_text(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch, key="k-test")
    api.save_settings({"voice": "groq", "lang": "uk"})
    sent = {}
    monkeypatch.setattr(voice, "transcribe_groq", lambda wav, key, lang: sent.update(key=key, lang=lang) or "привіт")
    api._recorder = FakeRecorder(_wav(1))
    assert api.voice_start() == {"ok": True} and api._recorder.recording
    assert api.voice_stop() == {"ok": True, "error": "", "text": "привіт"}
    assert sent == {"key": "k-test", "lang": "uk"}

    api._recorder = FakeRecorder(_wav(0.2))                              # a click, not speech: nothing is sent
    sent.clear()
    api.voice_start()
    assert api.voice_stop()["error"] == "empty" and sent == {}

    api._recorder = FakeRecorder(fail="no_mic")
    assert api.voice_start() == {"ok": False, "error": "no_mic"}

    api._recorder = FakeRecorder(_wav(1))
    api.voice_start()
    api.voice_cancel()
    assert api._recorder.cancelled and not api._recorder.recording


def test_engine_errors_reach_the_window(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch, key="k-test")
    api.save_settings({"voice": "groq"})

    def boom(*a):
        raise voice.VoiceError("network", "down")
    monkeypatch.setattr(voice, "transcribe_groq", boom)
    api._recorder = FakeRecorder(_wav(1))
    api.voice_start()
    assert api.voice_stop() == {"ok": False, "error": "network", "text": ""}


def test_voice_methods_are_exposed():
    from lanterna import gui
    for m in ("voice_status", "voice_start", "voice_stop", "voice_cancel", "voice_setup", "voice_setup_cancel"):
        assert m in gui.METHODS


# ---------------------------------------------------------------- the terminal
def test_terminal_settings_and_f2(tmp_path, monkeypatch):
    import asyncio

    from textual.widgets import Button, Input, Static

    from lanterna.tui import LanternaApp, SettingsScreen
    api = _api(tmp_path, monkeypatch, key="k-test")
    api.settings.onboarded, api.settings.update_check, api.settings.mode, api.settings.sync_asked = True, False, "local", True
    monkeypatch.setattr(voice.shutil, "which", lambda n: None)
    monkeypatch.setattr(voice, "transcribe_groq", lambda wav, key, lang: "погода в Києві")
    api._recorder = FakeRecorder(_wav(1))

    async def go():
        app = LanternaApp(api=api)
        async with app.run_test(size=(110, 60)) as pilot:
            await pilot.pause(0.3)
            app.screen.action_settings()
            for _ in range(100):
                await pilot.pause(0.05)
                if isinstance(app.screen, SettingsScreen) and app.screen.query("#voice-local"):
                    break
            await pilot.pause(0.5)                                 # let Settings finish filling in
            app.screen.query_one("#voice-local", Button).press()
            for _ in range(100):                                   # Settings opens again with the new choice
                await pilot.pause(0.05)
                if isinstance(app.screen, SettingsScreen) and app.screen.query("#voiceget") and "199" in str(app.screen.query_one("#voiceget", Button).label):
                    break
            assert api.settings.voice == "local"
            assert "199" in str(app.screen.query_one("#voiceget", Button).label)
            assert "Nothing leaves your PC" in str(app.screen.query_one("#voiceinfo", Static).render())
            app.screen.dismiss("")
            await pilot.pause(0.3)
            api.save_settings({"voice": "groq"})
            await pilot.press("f2")
            await pilot.pause(0.2)
            assert api._recorder.recording
            await pilot.press("f2")
            for _ in range(60):
                await pilot.pause(0.05)
                if app.screen.query_one("#composer", Input).value:
                    break
            assert app.screen.query_one("#composer", Input).value == "погода в Києві"
    asyncio.run(go())
