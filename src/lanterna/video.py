"""Videos from a link: yt-dlp (github.com/yt-dlp/yt-dlp, over a thousand sites) saves them into Downloads.

Lanterna doesn't carry yt-dlp. It is a program from the system's own catalog, installed with the usual card the first
time: on Windows winget's yt-dlp.yt-dlp, which brings FFmpeg (it puts a video's picture and sound together) and Deno
(YouTube needs it); on Linux the distribution's package. Lanterna runs it with fixed options only:
- one video from a link; a whole playlist only when the user asks for it, at most 50 videos;
- never the user's own yt-dlp settings or plugins, never cookies or logins from the browser;
- files only into Downloads (a playlist into its own folder there), never over an older file, only video or sound;
- not a live stream (it would never end), not an address on this computer or the home network.
Stop closes yt-dlp and everything it started, and removes the unfinished parts.
"""
from __future__ import annotations

import ipaddress
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

WINGET_ID = "yt-dlp.yt-dlp"            # winget brings yt-dlp.FFmpeg and DenoLand.Deno with it
LINUX_PKG = "yt-dlp"
MAX_PLAYLIST = 50
MAX_HEIGHT = 1080                       # the user's choice: up to 1080p, MP4 (plays everywhere)
STALL = 300                             # seconds without a line from yt-dlp: it is stuck
PROBE_TIMEOUT = 120
SPARE = 512 * 1024 * 1024               # what stays free on the disk
OLD_DAYS = 120                          # an older yt-dlp often fails on sites that changed
MEDIA = frozenset(".mp4 .m4v .mkv .webm .mov .avi .flv .3gp .ts .mpg .mpeg .wmv .m4a .mp3 .opus .ogg .oga .aac "
                  ".flac .wav .wma".split())
PARTIAL = re.compile(r"\.(part|ytdl|temp)(\.\w+)?$|\.part-Frag\d+|\.f[\w-]+\.\w+(\.part)?$", re.I)
TAG = "[lnt]"                           # Lanterna's own lines in yt-dlp's output (--print, --progress-template)
_LINK = re.compile(r"^<?(https?://[^\s<>\"']+)>?$", re.I)
_VERSION = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})")

# yt-dlp's own words → what happened, for the plain-language line (the first match wins)
ERRORS = (
    ("live", re.compile(r"live event will begin|is_live|is a live|premieres in|upcoming live", re.I)),
    ("drm", re.compile(r"\bDRM\b", re.I)),
    ("js", re.compile(r"javascript runtime|js runtime|n challenge|nsig|signature solving|\bjsc\b", re.I)),
    # before "login": YouTube's "Private video. Sign in if you've been granted access", "…the account associated
    # with this video has been terminated"
    ("gone", re.compile(r"private video|has been removed|no longer available|been terminated|does not exist|"
                        r"HTTP Error 404|HTTP Error 410", re.I)),
    ("geo", re.compile(r"country|geo[- ]?restrict|not available in your|region", re.I)),
    ("login", re.compile(r"sign in|\blog ?in\b|cookies|members[- ]only|age[- ]restricted|confirm your age|"
                         r"authenticat|requires? (an )?account", re.I)),
    ("gone", re.compile(r"video unavailable|not available|deleted", re.I)),
    ("too_big", re.compile(r"larger than max-filesize|max-filesize", re.I)),
    ("no_video", re.compile(r"unsupported url|no video formats|no video could be found|no media found|"
                            r"unable to extract|requested format is not available|no suitable", re.I)),
    ("ffmpeg", re.compile(r"ffmpeg|ffprobe", re.I)),
    ("network", re.compile(r"unable to download webpage|getaddrinfo|name or service not known|timed out|"
                           r"connection (refused|reset|aborted)|network is unreachable|temporary failure|"
                           r"no route to host|ssl|certificate|HTTP Error 5\d\d|HTTP Error 429", re.I)),
)


# Sites that are about videos (or sound): a link to one is a video even before yt-dlp is installed. Another link
# alone in a message is tried only when yt-dlp is already there (a page may have a video in it); without yt-dlp it
# goes to the model as before, so a link to an article never brings an install card.
VIDEO_SITES = ("youtube.com", "youtu.be", "youtube-nocookie.com", "tiktok.com", "instagram.com", "facebook.com",
               "fb.watch", "x.com", "twitter.com", "vimeo.com", "dailymotion.com", "dai.ly", "twitch.tv", "reddit.com",
               "redd.it", "soundcloud.com", "bilibili.com", "b23.tv", "rumble.com", "ok.ru", "vk.com", "vkvideo.ru",
               "threads.net", "threads.com", "pinterest.com", "pin.it", "bsky.app", "streamable.com", "coub.com",
               "mixcloud.com", "bandcamp.com", "kick.com", "nicovideo.jp", "odysee.com", "peertube.tv")


class VideoError(Exception):
    pass


def bare_link(text: str) -> str:
    """The link when a message is only one web link (also in < >), else ""."""
    m = _LINK.match((text or "").strip())
    if not m:
        return ""
    url = m.group(1).rstrip(".,;!?…»”")
    host = urlsplit(url).hostname or ""
    return url if "." in host and len(url) <= 2000 else ""


def video_site(url: str) -> bool:
    """A link to a video site (VIDEO_SITES) or straight to a video or sound file."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if any(host == s or host.endswith("." + s) for s in VIDEO_SITES):
        return True
    return Path(parts.path).suffix.lower() in MEDIA


def where(host: str, resolve: Callable = socket.getaddrinfo) -> str:
    """Where a link's site is: "public"; "local" (this computer or the home network: never downloaded from);
    "unknown" (its name doesn't resolve: no internet, or a typo)."""
    host = (host or "").strip("[]")
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            ips = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in resolve(host, None)]
        except (OSError, UnicodeError, ValueError):
            return "unknown"
    if not ips:
        return "unknown"
    return "public" if all(ip.is_global and not ip.is_multicast for ip in ips) else "local"


def links_dirs(env: dict | None = None) -> list[Path]:
    """Where winget puts the programs it installs without an installer (yt-dlp, its FFmpeg and Deno): a program
    started before that install doesn't have these folders in its PATH yet."""
    if sys.platform != "win32":
        return []
    env = env if env is not None else os.environ
    out = []
    for base, sub in ((env.get("LOCALAPPDATA", ""), ("Microsoft", "WinGet", "Links")),
                      (env.get("ProgramFiles", ""), ("WinGet", "Links"))):
        if base:
            out.append(Path(base, *sub))
    return out


def child_path(env: dict | None = None) -> str:
    env = env if env is not None else os.environ
    extra = [str(d) for d in links_dirs(env)]
    return os.pathsep.join([*extra, env.get("PATH", "")])


def find(which: Callable[..., str | None] = shutil.which, env: dict | None = None) -> str:
    """yt-dlp's path, or "". winget's copy first (the card installs it and winget keeps it fresh), then any other."""
    exe = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    for d in links_dirs(env):
        if (d / exe).is_file():
            return str(d / exe)
    found = which("yt-dlp", path=child_path(env))
    if found:
        return found
    home = Path.home() / ".local" / "bin" / "yt-dlp"            # pipx / pip --user on Linux
    return str(home) if sys.platform != "win32" and home.is_file() else ""


def has_ffmpeg(which: Callable[..., str | None] = shutil.which, env: dict | None = None) -> bool:
    return bool(which("ffmpeg", path=child_path(env)))


def version(exe: str, run: Callable[..., tuple[int, str]] | None = None) -> str:
    """yt-dlp's version ("2026.10.26"), or ""."""
    run = run or _run_quiet
    code, out = run([exe, "--version"], 30)
    first = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
    return first if code == 0 and _VERSION.match(first) else ""


def is_old(ver: str, today: float | None = None) -> bool:
    m = _VERSION.match(ver or "")
    if not m:
        return False
    try:
        made = time.mktime((int(m[1]), int(m[2]), int(m[3]), 0, 0, 0, 0, 0, -1))
    except (OverflowError, ValueError):
        return False
    return ((today or time.time()) - made) / 86400 > OLD_DAYS


def kind_of(text: str) -> str:
    """yt-dlp's error → "login", "geo", "gone", … (ERRORS), or "other"."""
    for kind, rx in ERRORS:
        if rx.search(text or ""):
            return kind
    return "other"


def _run_quiet(args: list[str], timeout: float) -> tuple[int, str]:
    try:
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        r = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=_env(), **kw)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = child_path(env)
    env["PYTHONIOENCODING"] = "utf-8"                   # titles in any language come through the pipe whole
    env["PYTHONUTF8"] = "1"
    return env


COMMON = ["--ignore-config", "--no-plugin-dirs", "--encoding", "utf-8", "--no-color", "--socket-timeout", "30"]


def probe(exe: str, url: str, run: Callable[..., tuple[int, str]] | None = None) -> dict:
    """A playlist before it is downloaded: {"title", "count", "entries": [title, …]} (at most MAX_PLAYLIST titles).
    Raises VideoError with yt-dlp's words when it can't read it."""
    run = run or _run_quiet
    code, out = run([exe, *COMMON, "--flat-playlist", "-J", "--no-warnings", "-I", f"1:{MAX_PLAYLIST}", "--", url],
                    PROBE_TIMEOUT)
    start = out.find("{")
    try:
        data = json.loads(out[start:out.rfind("}") + 1]) if code == 0 and start >= 0 else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise VideoError(_first_error(out) or "yt-dlp couldn't read the link")
    entries = [e for e in data.get("entries") or [] if isinstance(e, dict)]
    count = data.get("playlist_count") or data.get("n_entries") or len(entries)
    return {"title": str(data.get("title") or data.get("id") or "playlist")[:120],
            "count": int(count) if isinstance(count, (int, float)) else len(entries),
            "entries": [str(e.get("title") or e.get("id") or "?")[:120] for e in entries[:MAX_PLAYLIST]],
            "playlist": data.get("_type") == "playlist"}


def _first_error(text: str) -> str:
    for line in (text or "").splitlines():
        if line.startswith("ERROR:"):
            # "ERROR: [youtube] dQw4w9WgXcQ: Private video…" → "Private video…" (the site and the video's id go)
            return re.sub(r"^ERROR:\s*(?:\[[^\]]+\]\s*(?:[^\s:]+:\s+)?)?", "", line).strip()[:300]
    return ""


@dataclass
class Progress:
    title: str = ""
    done: int = 0                  # bytes of the current part
    total: int = 0                 # its size (0: not known yet)
    part: str = "video"            # "video", "audio" (the sound of a video), "join" (putting them together)
    index: int = 0                 # in a playlist: which video (1, 2, …) of count
    count: int = 0


@dataclass
class Result:
    files: list[Path] = field(default_factory=list)
    title: str = ""
    height: int = 0
    error: str = ""                # "" or kind_of's word, "cancelled", "no_space"
    detail: str = ""               # yt-dlp's own words (the first ERROR line)
    playlist: int = 0              # the link was a playlist of this many videos, and only one was asked for
    folder: Path | None = None     # a whole playlist: its folder


def _kill_tree(proc) -> None:
    """yt-dlp.exe is a small starter with Python inside (two processes) and starts FFmpeg and Deno itself."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=20,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


class Job:
    """One download. run() blocks until it ends; stop (an Event) ends it early."""

    def __init__(self, exe: str, url: str, folder: Path, audio: bool = False, playlist: bool = False,
                 ffmpeg: bool = True, popen: Callable | None = None, kill: Callable = _kill_tree,
                 free: Callable[[Path], int] | None = None):
        self.exe, self.url, self.folder = exe, url, Path(folder)
        self.audio, self.playlist, self.ffmpeg = audio, playlist, ffmpeg
        self._popen = popen or subprocess.Popen
        self._kill = kill
        self._free = free or (lambda p: shutil.disk_usage(p).free)

    def args(self, room: int) -> list[str]:
        out = [self.exe, *COMMON, "--newline", "--progress", "--no-simulate", "--no-mtime", "--windows-filenames",
               "--retries", "5", "--fragment-retries", "5", "--match-filters", "!is_live",
               "--max-filesize", str(max(1, room)), "-P", str(self.folder),
               "--progress-template", "download:" + TAG + " dl %(progress.downloaded_bytes)s "
               "%(progress.total_bytes)s %(progress.total_bytes_estimate)s %(info.vcodec)s %(info.playlist_index)s "
               "%(info.n_entries)s",
               "--print", "pre_process:" + TAG + " seen %(live_status)s %(playlist_count)s",
               "--print", "before_dl:" + TAG + " title %(height)s %(title)s",
               "--print", "after_move:" + TAG + " file %(filepath)s"]
        if self.playlist:
            out += ["--yes-playlist", "-I", f"1:{MAX_PLAYLIST}",
                    "-o", "%(playlist_title).80B/%(playlist_index)02d. %(title).120B [%(id)s].%(ext)s"]
        else:
            out += ["--no-playlist", "-I", "1", "-o", "%(title).150B [%(id)s].%(ext)s"]
        if self.audio:
            out += (["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"] if self.ffmpeg
                    else ["-f", "ba[ext=m4a]/ba"])
        else:
            out += ["-S", f"res:{MAX_HEIGHT},vcodec:h264,acodec:aac,ext:mp4:m4a"]
            if self.ffmpeg:                       # without FFmpeg only a file with both picture and sound will do
                out += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
        return [*out, "--", self.url]

    def run(self, stop: threading.Event | None = None, on_progress: Callable[[Progress], None] | None = None) -> Result:
        stop = stop or threading.Event()
        res = Result()
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            room = self._free(self.folder) - SPARE
        except OSError as e:
            return Result(error="other", detail=str(e))
        if room <= 0:
            return Result(error="no_space")
        before = self._names()
        kw: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
        try:
            proc = self._popen(self.args(room), stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                               env=_env(), **kw)
        except OSError as e:
            return Result(error="other", detail=str(e))
        lines: queue.Queue = queue.Queue()
        errors: list[str] = []

        def pump(stream, sink, end: bool) -> None:
            try:
                for raw in iter(stream.readline, b""):
                    sink(raw.decode("utf-8", "replace").rstrip("\r\n"))
            except (OSError, ValueError):
                pass
            if end:
                sink(None)

        readers = [threading.Thread(target=pump, args=(proc.stdout, lines.put, True), daemon=True),
                   threading.Thread(target=pump, args=(proc.stderr, errors.append, False), daemon=True)]
        for r in readers:
            r.start()
        prog = Progress()
        quiet_since = time.monotonic()
        live = False
        while True:
            if stop.is_set():
                self._kill(proc)
                res.error = "cancelled"
                break
            try:
                line = lines.get(timeout=0.3)
            except queue.Empty:
                if time.monotonic() - quiet_since > STALL:
                    self._kill(proc)
                    res.error, res.detail = "network", "yt-dlp got nothing for 5 minutes"
                    break
                continue
            if line is None:
                break
            quiet_since = time.monotonic()
            if not line.startswith(TAG + " "):
                continue
            what, _, rest = line[len(TAG) + 1:].partition(" ")
            if what == "seen":
                status, _, count = rest.partition(" ")
                live = live or status in ("is_live", "is_upcoming")
                if not self.playlist and count.isdigit() and int(count) > 1:
                    res.playlist = int(count)
            elif what == "title":
                h, _, title = rest.partition(" ")
                prog = Progress(title=title.strip(), index=prog.index, count=prog.count)
                res.title = res.title or prog.title
                res.height = int(h) if h.isdigit() else res.height
            elif what == "dl":
                f = (rest.split(" ") + [""] * 6)[:6]
                total = _int(f[1]) or _int(f[2])
                # a video comes as its picture, then its sound (vcodec "none"), and FFmpeg puts them together;
                # a sound alone (audio) is turned into MP3 at the end
                part = "audio" if self.audio or f[3] == "none" else "video"
                prog.done, prog.total, prog.part = _int(f[0]), total, part
                prog.index, prog.count = _int(f[4]), _int(f[5])
                if total and prog.done >= total and self.ffmpeg and (self.audio or part == "audio"):
                    prog.part = "join"
            elif what == "file":
                p = Path(rest.strip())
                if p.suffix.lower() in MEDIA and _inside(p, self.folder):
                    res.files.append(p)
                elif p.exists() and _inside(p, self.folder):    # never left in Downloads: not a video or a sound
                    _remove(p)
                continue
            if on_progress and what in ("title", "dl"):
                on_progress(prog)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._kill(proc)
        for r in readers:
            r.join(timeout=5)
        if res.error == "cancelled" or (res.error and not res.files):
            self._clean(before, keep=res.files)
            return res
        detail = _first_error("\n".join(errors))
        if not res.files:
            res.error = "live" if live else (kind_of(detail) if detail else "no_video")
            res.detail = detail
            self._clean(before, keep=[])
        elif detail and self.playlist:
            res.detail = detail                          # some videos of the playlist didn't come
        self._clean(before, keep=res.files)
        if self.playlist and res.files:
            res.folder = res.files[0].parent
        return res

    def _names(self) -> set[str]:
        try:
            return {str(p) for p in self.folder.rglob("*")} if self.playlist else {str(p) for p in self.folder.iterdir()}
        except OSError:
            return set()

    def _clean(self, before: set[str], keep: list[Path]) -> None:
        """The unfinished parts this download left (.part, .ytdl, a format's own file before they were joined)."""
        kept = {str(p) for p in keep}
        new = [p for p in (self.folder.rglob("*") if self.playlist else self.folder.iterdir())
               if str(p) not in before and str(p) not in kept] if self.folder.is_dir() else []
        for p in new:
            if p.is_file() and PARTIAL.search(p.name):
                _remove(p)
        for p in sorted((p for p in new if p.is_dir()), key=lambda p: -len(p.parts)):
            try:
                p.rmdir()                                    # only when empty: a playlist folder that got nothing
            except OSError:
                pass


def _int(s: str) -> int:
    try:
        return max(0, int(float(s)))
    except (TypeError, ValueError):
        return 0


def _inside(p: Path, folder: Path) -> bool:
    try:
        p.resolve().relative_to(folder.resolve())
        return True
    except (OSError, ValueError):
        return False


def _remove(p: Path) -> None:
    try:
        p.unlink()
    except OSError:
        pass
