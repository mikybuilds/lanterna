"""Voice input: record the microphone and turn the speech into text.

Two engines, chosen in Settings (off by default):
  groq   online: Groq's Whisper (fast and accurate; the audio goes to Groq, the Groq key is needed)
  local  on this computer: whisper.cpp (nothing leaves the PC; a one-time download of the engine and a model)

Recording needs nothing extra: Windows records through its own MCI (winmm), Linux through pw-record,
parecord or arecord. The whisper.cpp build and the models are pinned to exact files with their SHA-256,
so Lanterna only ever runs the files it was made with.
"""
from __future__ import annotations

import hashlib
import io
import os
import queue
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import httpx

ENGINES = ("off", "groq", "local")
MAX_SECONDS = 120
RATE = 16000
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"

_WCPP = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/"
ENGINE_FILES = {   # platform: (url, sha256, size)
    "win32": (_WCPP + "whisper-bin-x64.zip", "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb", 8928640),
    "linux": (_WCPP + "whisper-bin-ubuntu-x64.tar.gz", "a72becf15d7917f990f6313867a52638b82b7f9ef237fb0c980dac56a135781c", 10364195),
}
_HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
MODELS = {         # id: (file, sha256, size) — base is quick, small is better for most languages, turbo is the best
    "base": ("ggml-base-q5_1.bin", "422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898", 59707625),
    "small": ("ggml-small-q5_1.bin", "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb", 190085487),
    "turbo": ("ggml-large-v3-turbo-q5_0.bin", "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2", 574041195),
}


class VoiceError(Exception):
    """kind: no_mic | no_key | network | engine | empty"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


# ---------------------------------------------------------------- recording
class _MciRecorder:
    """Windows: MCI waveaudio. MCI devices belong to the thread that opened them, so one thread does it all."""

    def __init__(self):
        self._cmds: queue.Queue = queue.Queue()
        self._done: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _mci(cmd: str) -> int:
        import ctypes
        f = ctypes.windll.winmm.mciSendStringW
        f.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        return f(cmd, None, 0, None)

    def start(self) -> bool:
        ready: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        return ready.get(timeout=5)

    def _run(self, ready: queue.Queue) -> None:
        alias = "lanternavoice"
        ok = (self._mci(f"open new type waveaudio alias {alias}") == 0
              and self._mci(f"set {alias} bitspersample 16 samplespersec {RATE} channels 1 "
                            f"bytespersec {RATE * 2} alignment 2") == 0
              and self._mci(f"record {alias}") == 0)
        ready.put(ok)
        if not ok:
            self._mci(f"close {alias}")
            return
        try:
            what = self._cmds.get(timeout=MAX_SECONDS)
        except queue.Empty:
            what = "stop"                                   # too long: stop by itself, keep what was said
        self._mci(f"stop {alias}")
        data = b""
        name = Path(tempfile.gettempdir()) / f"lanterna-voice-{os.getpid()}-{int(time.time() * 1000)}.wav"
        saved = what == "stop" and self._mci(f'save {alias} "{name}"') == 0
        self._mci(f"close {alias}")                         # MCI keeps the file open until the device closes
        try:
            if saved and name.is_file():
                data = name.read_bytes()
        finally:
            name.unlink(missing_ok=True)
        self._done.put(data)

    def stop(self, cancel: bool = False) -> bytes:
        self._cmds.put("cancel" if cancel else "stop")
        try:
            return self._done.get(timeout=10)
        except queue.Empty:
            return b""


class _ProcRecorder:
    """Linux: the first recorder that is installed (PipeWire, PulseAudio or ALSA)."""

    COMMANDS = (("pw-record", ["--rate", str(RATE), "--channels", "1", "--format", "s16"]),
                ("parecord", [f"--rate={RATE}", "--channels=1", "--format=s16le", "--file-format=wav"]),
                ("arecord", ["-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "wav"]))

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._file = ""

    @classmethod
    def available(cls) -> str:
        return next((name for name, _ in cls.COMMANDS if shutil.which(name)), "")

    def start(self) -> bool:
        name = self.available()
        if not name:
            return False
        args = dict(self.COMMANDS)[name]
        fd, self._file = tempfile.mkstemp(suffix=".wav", prefix="lanterna-voice-")
        os.close(fd)
        self._proc = subprocess.Popen([name, *args, self._file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        if self._proc.poll() is not None:
            Path(self._file).unlink(missing_ok=True)
            return False
        self._limit = threading.Timer(MAX_SECONDS, self._too_long, args=(self._proc,))
        self._limit.daemon = True
        self._limit.start()
        return True

    @staticmethod
    def _too_long(proc: subprocess.Popen) -> None:
        """A forgotten recording stops by itself, like on Windows (what was said is kept)."""
        import signal
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)

    def stop(self, cancel: bool = False) -> bytes:
        import signal
        if getattr(self, "_limit", None):
            self._limit.cancel()
        if self._proc and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)           # lets the recorder finish the WAV header
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        p = Path(self._file)
        data = b"" if cancel or not p.is_file() else p.read_bytes()
        p.unlink(missing_ok=True)
        return data


class Recorder:
    """One recording at a time: start(), then stop() gives the WAV bytes (b"" if nothing came)."""

    def __init__(self):
        self._rec = None
        self._started = 0.0

    @property
    def recording(self) -> bool:
        return self._rec is not None

    def start(self) -> None:
        if self._rec:
            return
        rec = _MciRecorder() if sys.platform == "win32" else _ProcRecorder()
        if not rec.start():
            raise VoiceError("no_mic", "no microphone or recorder")
        self._rec, self._started = rec, time.time()

    def stop(self, cancel: bool = False) -> bytes:
        rec, self._rec = self._rec, None
        return rec.stop(cancel) if rec else b""


def speech_seconds(wav: bytes) -> float:
    """How long the recording is (0 if it isn't a WAV)."""
    import wave
    try:
        with wave.open(io.BytesIO(wav)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return 0.0


# ---------------------------------------------------------------- online: Groq Whisper
GROQ_TYPES = {".mp3": "audio/mpeg", ".mpga": "audio/mpeg", ".mpeg": "audio/mpeg", ".wav": "audio/wav",
              ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac",
              ".webm": "audio/webm"}
LOCAL_TYPES = {".wav", ".mp3", ".flac", ".ogg", ".oga"}      # what whisper.cpp reads by itself


def transcribe_groq(wav: bytes, key: str, lang: str = "", http: httpx.Client | None = None,
                    name: str = "voice.wav") -> str:
    if not key:
        raise VoiceError("no_key")
    data = {"model": GROQ_MODEL, "response_format": "json", "temperature": "0"}
    if lang and lang != "auto":
        data["language"] = lang
    ext = Path(name).suffix.lower()
    upload = ("audio.ogg" if ext in (".oga", ".opus") else "audio" + ext) if ext in GROQ_TYPES else "voice.wav"
    client = http or httpx.Client(timeout=180)
    try:
        r = client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, data=data,
                        files={"file": (upload, wav, GROQ_TYPES.get(ext, "audio/wav"))})
    except httpx.HTTPError as e:
        raise VoiceError("network", str(e)) from e
    finally:
        if http is None:
            client.close()
    if r.status_code in (401, 403):
        raise VoiceError("no_key", "the Groq key was not accepted")
    if r.status_code >= 400:
        raise VoiceError("network", f"Groq answered {r.status_code}")
    return clean_text(str(r.json().get("text", "")))


# ---------------------------------------------------------------- on this computer: whisper.cpp
def _safe_extract(archive: Path, dest: Path) -> None:
    """Unpacks only regular files and folders that stay inside dest."""
    dest = dest.resolve()

    def inside(name: str) -> Path | None:
        p = (dest / name).resolve()
        return p if p == dest or dest in p.parents else None

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            for m in z.infolist():
                target = inside(m.filename)
                if target is None:
                    continue
                if m.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(m) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
    else:
        with tarfile.open(archive) as tf:
            for m in tf.getmembers():
                target = inside(m.name)
                if target is None or not (m.isfile() or m.isdir()):
                    continue                                 # no links, devices or paths outside dest
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src:
                    with src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if m.mode & 0o111:
                        target.chmod(0o755)


class LocalWhisper:
    """whisper.cpp in Lanterna's own folder: downloaded once (when the user presses Download), then offline."""

    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._job: dict = {}
        self._cancel = threading.Event()

    # where things are
    def binary(self) -> Path | None:
        names = ("whisper-cli.exe", "main.exe") if sys.platform == "win32" else ("whisper-cli",)
        found = shutil.which("whisper-cli") if sys.platform != "win32" else None   # Linux: a packaged one is fine
        if found:
            return Path(found)
        eng = self.root / "engine"
        for name in names:
            for p in sorted(eng.rglob(name)) if eng.is_dir() else []:
                return p
        return None

    def model_path(self, model: str) -> Path:
        return self.root / MODELS.get(model, MODELS["small"])[0]

    def status(self, model: str) -> dict:
        with self._lock:
            job = dict(self._job)
        return {"engine": self.binary() is not None, "model": self.model_path(model).is_file(),
                "platform_ok": sys.platform in ENGINE_FILES, **job}

    # downloading
    def setup(self, model: str, http: httpx.Client | None = None) -> dict:
        """Starts downloading what is missing (engine and/or model) in the background."""
        with self._lock:
            if self._job.get("phase") == "downloading":
                return dict(self._job)
            self._job = {"phase": "downloading", "done": 0, "total": 0, "error": ""}
        self._cancel.clear()
        threading.Thread(target=self._download_all, args=(model, http), daemon=True).start()
        return self.status(model)

    def cancel(self) -> None:
        self._cancel.set()

    def _download_all(self, model: str, http: httpx.Client | None) -> None:
        todo = []
        if self.binary() is None:
            if sys.platform not in ENGINE_FILES:
                self._set(phase="error", error="platform")
                return
            todo.append(("engine", *ENGINE_FILES[sys.platform]))
        if not self.model_path(model).is_file():
            todo.append(("model", _HF + MODELS[model][0], MODELS[model][1], MODELS[model][2]))
        self._set(total=sum(x[3] for x in todo))
        client = http or httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                                      headers={"User-Agent": "Lanterna"})
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for kind, url, sha, size in todo:
                part = self.root / (url.rsplit("/", 1)[1] + ".part")
                self._fetch(client, url, sha, part)
                if kind == "engine":
                    shutil.rmtree(self.root / "engine", ignore_errors=True)
                    _safe_extract(part.with_suffix(""), self.root / "engine")
                    part.with_suffix("").unlink(missing_ok=True)
                else:
                    part.with_suffix("").replace(self.model_path(model))
            self._set(phase="ready")
        except VoiceError as e:
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
                raise VoiceError("network", f"{r.status_code} for {url}")
            with open(part, "wb") as out:
                for chunk in r.iter_bytes(1 << 16):
                    if self._cancel.is_set():
                        out.close()
                        part.unlink(missing_ok=True)
                        raise VoiceError("cancelled")
                    out.write(chunk)
                    h.update(chunk)
                    with self._lock:
                        self._job["done"] = self._job.get("done", 0) + len(chunk)
        if h.hexdigest() != sha:
            part.unlink(missing_ok=True)
            raise VoiceError("engine", "the downloaded file is not the expected one")
        part.replace(part.with_suffix(""))                   # "x.zip.part" -> "x.zip"

    def _set(self, **kw) -> None:
        with self._lock:
            self._job.update(kw)

    # using it
    def transcribe(self, wav: bytes, model: str, lang: str = "", suffix: str = ".wav") -> str:
        exe, mp = self.binary(), self.model_path(model)
        if exe is None or not mp.is_file():
            raise VoiceError("engine", "the speech engine is not downloaded yet")
        suffix = suffix if suffix in LOCAL_TYPES else ".wav"
        fd, name = tempfile.mkstemp(suffix=suffix, prefix="lanterna-voice-")
        os.close(fd)
        try:
            Path(name).write_bytes(wav)
            args = [str(exe), "-m", str(mp), "-f", name, "-nt", "-np", "-t", str(max(1, min(8, (os.cpu_count() or 4) - 1))),
                    "-l", lang if lang and lang != "auto" else "auto"]
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(args, capture_output=True, timeout=1800, creationflags=flags, cwd=str(exe.parent))
        except subprocess.TimeoutExpired as e:
            raise VoiceError("engine", "the speech engine took too long") from e
        finally:
            Path(name).unlink(missing_ok=True)
        if r.returncode != 0:
            raise VoiceError("engine", r.stderr.decode("utf-8", "replace")[-300:])
        return clean_text(r.stdout.decode("utf-8", "replace"))


def clean_text(text: str) -> str:
    """Drops whisper's sound notes ("[BLANK_AUDIO]", "[Music]") and extra spaces."""
    import re
    return " ".join(re.sub(r"\[[^\]]{0,40}\]", " ", text or "").split())
