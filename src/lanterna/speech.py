"""Reading answers aloud (Settings → Reading aloud). Three choices:

off     — nothing.
system  — the voices already on the computer, nothing to download: on Windows through Windows' own speech
          (System.Speech, the same voices as Narrator's "Desktop" ones); the terminal app on Linux uses spd-say.
piper   — Piper, a separate free program with natural voices (it is GPL-licensed, so it is not part of Lanterna:
          it is downloaded on request from its own release page into Lanterna's folder, as pinned files checked by
          SHA-256, and runs as its own program). Works offline after the download.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import tarfile
from pathlib import Path

import httpx

ENGINES = ("off", "system", "piper")
MAX_CHARS = 6000

_PIPER = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"
PIPER_FILES = {   # platform: (url, sha256, size)
    "win32": (_PIPER + "piper_windows_amd64.zip", "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea", 22477236),
    "linux": (_PIPER + "piper_linux_x86_64.tar.gz", "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992", 26460462),
}
_VOICES_AT = "https://huggingface.co/rhasspy/piper-voices/resolve/e7229f7d33a10e145e109b886d661984201ac3c4/"
VOICES = {        # lang: (path without .onnx, onnx sha256, onnx size, json sha256, json size)
    "uk": ("uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium",
           "7920419ac5f6fd8b6450520f24b52ed5a319cb53dd018fbcd71c9e079cbac84f", 76735663,
           "4e96e72917ca9b94edc77d6ccfee03a73f450ba2fc1ca93c2e562bc014e5aa55", 2002),
    "en": ("en/en_US/lessac/medium/en_US-lessac-medium",
           "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f", 63201294,
           "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0", 4885),
    "it": ("it/it_IT/paola/medium/it_IT-paola-medium",
           "6fc918b5a0ea6137382833dddfa567bffbe6a5060c02043c87192ee59c04210c", 63511038,
           "aea19c0a7fce29fbc359b93f10e7902854401e4c95ae2ea328ae516b15d296cf", 7099),
    "de": ("de/de_DE/thorsten/medium/de_DE-thorsten-medium",
           "7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819", 63201294,
           "974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85", 4819),
    "es": ("es/es_ES/davefx/medium/es_ES-davefx-medium",
           "6658b03b1a6c316ee4c265a9896abc1393353c2d9e1bca7d66c2c442e222a917", 63201294,
           "0e0dda87c732f6f38771ff274a6380d9252f327dca77aa2963d5fbdf9ec54842", 4817),
    "fr": ("fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
           "641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99", 63201294,
           "39479916c2db192b5ac9764daddd0c744d83e023ad890c6976c0633ae4df8959", 4875),
    "pl": ("pl/pl_PL/gosia/medium/pl_PL-gosia-medium",
           "38f66464240ed74f186e6b7dc13c6e3b22e023426299f25c2b3cc9dfa9373fbc", 63201294,
           "1aefb31a9d53ffe44a8163ff73ec833acb7a6253848f6bb0403d8a66f9c7510d", 4814),
}


class SpeechError(Exception):
    """kind: platform | not_ready | engine | network | cancelled | no_player"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


def speakable(text: str) -> str:
    """The answer as plain sentences to read: no code blocks, links, tables or markdown signs."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s*\|?[-:| ]{3,}\|?\s*$", " ", t, flags=re.M)        # table rules
    t = t.replace("|", ", ")
    t = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+•]|\d+[.)])\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~#$]+", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    return t[:MAX_CHARS]


# ---------------------------------------------------------------- Piper, a separate program in Lanterna's folder
class Piper:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._job: dict = {}
        self._cancel = threading.Event()

    def binary(self) -> Path | None:
        name = "piper.exe" if sys.platform == "win32" else "piper"
        eng = self.root / "engine"
        for p in sorted(eng.rglob(name)) if eng.is_dir() else []:
            if p.is_file():
                return p
        return None

    def voice_path(self, lang: str) -> Path:
        return self.root / (VOICES.get(lang, VOICES["en"])[0].rsplit("/", 1)[1] + ".onnx")

    def status(self, lang: str) -> dict:
        with self._lock:
            job = dict(self._job)
        v = VOICES.get(lang, VOICES["en"])
        engine_mb = round(PIPER_FILES.get(sys.platform, ("", "", 0))[2] / 1e6)
        return {"engine": self.binary() is not None, "voice": self.voice_path(lang).is_file()
                and self.voice_path(lang).with_suffix(".onnx.json").is_file(),
                "platform_ok": sys.platform in PIPER_FILES, "engine_mb": engine_mb, "voice_mb": round(v[2] / 1e6),
                "phase": job.get("phase", "idle"), "done": job.get("done", 0), "total": job.get("total", 0),
                "error": job.get("error", "")}

    def setup(self, lang: str, http: httpx.Client | None = None) -> dict:
        with self._lock:
            if self._job.get("phase") == "downloading":
                return self.status(lang)
            self._job = {"phase": "downloading", "done": 0, "total": 0, "error": ""}
        self._cancel.clear()
        threading.Thread(target=self._download_all, args=(lang, http), daemon=True).start()
        return self.status(lang)

    def cancel(self) -> None:
        self._cancel.set()

    def _set(self, **kw) -> None:
        with self._lock:
            self._job.update(kw)

    def _download_all(self, lang: str, http: httpx.Client | None) -> None:
        from .voice import _safe_extract
        lang = lang if lang in VOICES else "en"
        path, osha, osize, jsha, jsize = VOICES[lang]
        todo = []
        if self.binary() is None:
            if sys.platform not in PIPER_FILES:
                self._set(phase="error", error="platform")
                return
            todo.append(("engine", *PIPER_FILES[sys.platform]))
        if not self.voice_path(lang).is_file():
            todo.append(("voice", _VOICES_AT + path + ".onnx", osha, osize))
        if not self.voice_path(lang).with_suffix(".onnx.json").is_file():
            todo.append(("config", _VOICES_AT + path + ".onnx.json", jsha, jsize))
        self._set(total=sum(x[3] for x in todo))
        client = http or httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                                      headers={"User-Agent": "Lanterna"})
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for kind, url, sha, _size in todo:
                part = self.root / (url.rsplit("/", 1)[1] + ".part")
                self._fetch(client, url, sha, part)
                done = part.with_name(part.name[:-5])
                part.replace(done)
                if kind == "engine":
                    shutil.rmtree(self.root / "engine", ignore_errors=True)
                    _safe_extract(done, self.root / "engine")
                    done.unlink(missing_ok=True)
            self._set(phase="ready")
        except SpeechError as e:
            self._set(phase="error" if e.kind != "cancelled" else "idle", error=e.kind)
        except (OSError, httpx.HTTPError, zipfile.BadZipFile, tarfile.TarError) as e:
            self._set(phase="error", error=str(e)[:200])
        finally:
            if http is None:
                client.close()

    def _fetch(self, client: httpx.Client, url: str, sha: str, part: Path) -> None:
        h = hashlib.sha256()
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                raise SpeechError("network", f"{r.status_code} for {url}")
            with open(part, "wb") as out:
                for chunk in r.iter_bytes(1 << 16):
                    if self._cancel.is_set():
                        out.close()
                        part.unlink(missing_ok=True)
                        raise SpeechError("cancelled")
                    out.write(chunk)
                    h.update(chunk)
                    with self._lock:
                        self._job["done"] = self._job.get("done", 0) + len(chunk)
        if h.hexdigest() != sha:
            part.unlink(missing_ok=True)
            raise SpeechError("network", "the downloaded file is not the expected one")

    def say(self, text: str, lang: str) -> bytes:
        """The text as WAV bytes."""
        exe, model = self.binary(), self.voice_path(lang)
        if exe is None or not model.is_file():
            raise SpeechError("not_ready", "Piper or its voice is not downloaded yet")
        fd, out = tempfile.mkstemp(suffix=".wav", prefix="lanterna-say-")
        import os
        os.close(fd)
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run([str(exe), "--model", str(model), "--output_file", out], input=text.encode("utf-8"),
                               capture_output=True, timeout=300, creationflags=flags, cwd=str(exe.parent))
            if r.returncode != 0:
                raise SpeechError("engine", r.stderr.decode("utf-8", "replace")[-300:])
            return Path(out).read_bytes()
        except subprocess.TimeoutExpired as e:
            raise SpeechError("engine", "Piper took too long") from e
        finally:
            Path(out).unlink(missing_ok=True)


# ---------------------------------------------------------------- Windows' own voices
_SAPI = "System.Speech, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35"
_sapi_lock = threading.Lock()


def windows_voices() -> list[tuple[str, str]]:
    """[(voice name, culture like "en-US")] of the voices Windows has, [] when there is no Windows speech."""
    if sys.platform != "win32":
        return []
    try:
        import clr                                         # pythonnet: it is already there for the window
        clr.AddReference(_SAPI)
        from System.Speech.Synthesis import SpeechSynthesizer
    except Exception:                                      # noqa: BLE001  no .NET speech on this PC
        return []
    with _sapi_lock:
        s = SpeechSynthesizer()
        try:
            return [(v.VoiceInfo.Name, v.VoiceInfo.Culture.Name) for v in s.GetInstalledVoices() if v.Enabled]
        finally:
            s.Dispose()


def windows_say(text: str, lang: str) -> bytes:
    """The text as WAV bytes in a Windows voice for this language."""
    voice = next((n for n, c in windows_voices() if c.lower().startswith(lang.lower())), None)
    if voice is None:
        raise SpeechError("no_voice" if sys.platform == "win32" else "platform")
    import clr
    clr.AddReference(_SAPI)
    from System.IO import MemoryStream
    from System.Speech.Synthesis import SpeechSynthesizer
    with _sapi_lock:
        s, buf = SpeechSynthesizer(), MemoryStream()
        try:
            s.SelectVoice(voice)
            s.SetOutputToWaveStream(buf)
            s.Speak(text)
            s.SetOutputToNull()
            return bytes(buf.ToArray())
        except Exception as e:                             # noqa: BLE001
            raise SpeechError("engine", str(e)[:200]) from e
        finally:
            s.Dispose()
            buf.Dispose()


# ---------------------------------------------------------------- the terminal app plays sound itself
_playing: subprocess.Popen | None = None


def play(wav: bytes) -> None:
    """Plays WAV bytes and returns at once (Windows: winsound; Linux: pw-play, paplay or aplay)."""
    global _playing
    stop()
    if sys.platform == "win32":
        import winsound
        threading.Thread(target=winsound.PlaySound, args=(wav, winsound.SND_MEMORY), daemon=True).start()
        return
    player = next((p for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)
    if not player:
        raise SpeechError("no_player", "no sound player found (pw-play, paplay or aplay)")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix="lanterna-say-")
    import os
    with os.fdopen(fd, "wb") as f:
        f.write(wav)
    _playing = subprocess.Popen([player, name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=lambda p=_playing, n=name: (p.wait(), Path(n).unlink(missing_ok=True)), daemon=True).start()


def system_say(text: str, lang: str) -> None:
    """Linux: the system's own speech (speech-dispatcher's spd-say)."""
    global _playing
    stop()
    exe = shutil.which("spd-say")
    if not exe:
        raise SpeechError("no_player", "spd-say is not installed")
    _playing = subprocess.Popen([exe, "-w", "-l", lang, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop() -> None:
    global _playing
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except (ImportError, RuntimeError):
            pass
    if _playing and _playing.poll() is None:
        _playing.terminate()
    _playing = None
    if shutil.which("spd-say") and sys.platform != "win32":
        subprocess.run(["spd-say", "-C"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
