"""Round 151 (1.1.11b3): videos from a link.

A message that is only a link to a video: Lanterna downloads it into Downloads with yt-dlp (no model needed), shows
the progress in the "what I'm doing" line and puts the file's link under the reply. yt-dlp comes from the system's
catalog, on a card, the first time. The model has video_download for the rest: only the sound as MP3, a whole
playlist (after a card with its list), a link with words around it.
Nothing here runs yt-dlp, winget or the network: yt-dlp is a pretend process with the lines the test gives it.
"""
import dataclasses
import json
import os
import threading
import time
from pathlib import Path

import pytest

from lanterna import app, gui, i18n, sources, thinking, tools, tui, video
from lanterna.discovery import Candidate
from lanterna.router import Router
from lanterna.video import TAG, Job, Progress, Result
from test_round_144 import _api  # noqa: E402  (an Api of its own)
from test_round_147 import _Fake, _until_done  # noqa: E402  (a pretend model, waiting for a reply)

ROOT = Path(__file__).parents[1] / "src" / "lanterna"
JS = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "ui" / "style.css").read_text(encoding="utf-8")
URL = "https://youtu.be/dQw4w9WgXcQ"
SCAM = "https://privatbank-ua.secure-login.top/verify"         # a fake bank page (see test_round_133)


# ---------------------------------------------------------------- which messages are a video
@pytest.mark.parametrize("text, url", [
    (URL, URL),
    ("  " + URL + "\n", URL),
    ("<" + URL + ">", URL),
    (URL + ".", URL),
    ("https://www.tiktok.com/@a/video/1?lang=uk", "https://www.tiktok.com/@a/video/1?lang=uk"),
    ("подивись " + URL, ""),
    (URL + " " + URL, ""),
    ("ftp://example.com/a.mp4", ""),
    ("https://localhost/a.mp4", ""),
    ("https://" + "a" * 2000 + ".com/", ""),
    ("", ""),
])
def test_only_a_message_that_is_one_link_is_a_download(text, url):
    assert video.bare_link(text) == url


@pytest.mark.parametrize("url, site", [
    ("https://www.youtube.com/watch?v=1", True), ("https://m.youtube.com/watch?v=1", True),
    ("https://music.youtube.com/watch?v=1", True), ("https://vm.tiktok.com/ZM1/", True),
    ("https://x.com/a/status/1", True), ("https://example.com/files/clip.MP4", True),
    ("https://example.com/song.mp3?x=1", True), ("https://example.com/news/article", False),
    ("https://notyoutube.com/watch?v=1", False), ("https://youtube.com.example.net/watch", False),
])
def test_video_sites_and_links_to_media_files(url, site):
    assert video.video_site(url) is site


def test_a_link_to_this_computer_or_the_home_network_is_never_downloaded():
    def dns(*ips):
        return lambda host, port: [(2, 1, 6, "", (ip, 0)) for ip in ips]

    def offline(host, port):
        raise OSError("getaddrinfo failed")

    assert video.where("youtu.be", dns("142.250.180.14")) == "public"
    assert video.where("nas.lan", dns("192.168.1.20")) == "local"
    assert video.where("mixed.example", dns("142.250.180.14", "10.0.0.5")) == "local"
    assert video.where("127.0.0.1") == video.where("::1") == video.where("169.254.1.1") == "local"
    assert video.where("youtu.be", offline) == "unknown"                # no internet: not "your computer"


# ---------------------------------------------------------------- how yt-dlp is run
def test_yt_dlp_runs_with_fixed_options_only(tmp_path):
    args = Job("yt-dlp", URL, tmp_path).args(10 ** 9)
    assert args[0] == "yt-dlp" and args[-2:] == ["--", URL]             # a link can't become an option
    for flag in ("--ignore-config", "--no-plugin-dirs", "--no-playlist", "--no-mtime", "--windows-filenames"):
        assert flag in args, flag
    assert args[args.index("-P") + 1] == str(tmp_path) and args[args.index("--max-filesize") + 1] == "1000000000"
    assert args[args.index("-I") + 1] == "1" and args[args.index("--match-filters") + 1] == "!is_live"
    assert args[args.index("-S") + 1].startswith("res:1080,") and args[args.index("--merge-output-format") + 1] == "mp4"
    out = args[args.index("-o") + 1]
    assert out == "%(title).150B [%(id)s].%(ext)s" and ".." not in out and not os.path.isabs(out)
    joined = " ".join(args)
    for never in ("--cookies", "--cookies-from-browser", "--exec", "--config-location", "--username", "--password",
                  "--netrc", "--batch-file", "--load-info-json", "--plugin-dirs ", "--update"):
        assert never not in joined, never


def test_the_sound_a_playlist_and_no_ffmpeg(tmp_path):
    mp3 = Job("yt-dlp", URL, tmp_path, audio=True).args(1)
    assert mp3[mp3.index("--audio-format") + 1] == "mp3" and "-x" in mp3 and "-S" not in mp3
    m4a = Job("yt-dlp", URL, tmp_path, audio=True, ffmpeg=False).args(1)
    assert m4a[m4a.index("-f") + 1] == "ba[ext=m4a]/ba" and "-x" not in m4a           # nothing to turn it into MP3
    plain = Job("yt-dlp", URL, tmp_path, ffmpeg=False).args(1)
    assert "--merge-output-format" not in plain and "--remux-video" not in plain
    many = Job("yt-dlp", URL, tmp_path, playlist=True).args(1)
    assert "--yes-playlist" in many and many[many.index("-I") + 1] == "1:50" and "--no-playlist" not in many
    assert many[many.index("-o") + 1].startswith("%(playlist_title).80B/%(playlist_index)02d. ")


class _Pipe:
    """A pretend pipe of yt-dlp: its lines, then (hold) nothing more until the process is killed."""

    def __init__(self, lines, hold=None):
        self.lines = [x if isinstance(x, bytes) else (x + "\n").encode("utf-8") for x in lines]
        self.hold = hold

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        if self.hold is not None:
            self.hold.wait(10)
        return b""


class _Proc:
    def __init__(self, out=(), err=(), hold=False):
        self.pid, self.killed = 4242, threading.Event()
        self.stdout = _Pipe(out, self.killed if hold else None)
        self.stderr = _Pipe(err)

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed.set()


def _job(tmp_path, proc, made=(), seen=None, **kw):
    """A Job whose yt-dlp is `proc`; `made`: the files yt-dlp writes (name → bytes) when it starts."""
    def popen(args, **opts):
        if seen is not None:
            seen.append((args, opts))
        for name, data in made:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return proc
    kills = []
    job = Job("yt-dlp", URL, tmp_path, popen=popen, kill=lambda p: kills.append(p) or p.kill(),
              free=lambda p: 10 ** 12, **kw)
    return job, kills


def test_a_download_shows_its_progress_and_keeps_only_the_video(tmp_path):
    (tmp_path / "older.mp4.part").write_bytes(b"x")             # not this download's: never touched
    final = tmp_path / "Song name [dQw4w9WgXcQ].mp4"
    out = ["[youtube] dQw4w9WgXcQ: Downloading webpage", f"{TAG} seen not_live NA",
           f"{TAG} title 1080 Song name", f"{TAG} dl 1000 4000 NA avc1.640028 NA NA",
           f"{TAG} dl 4000 4000 NA avc1.640028 NA NA", f"{TAG} dl 500 NA 1000 none NA NA",
           f"{TAG} dl 1000 NA 1000 none NA NA", '[Merger] Merging formats into "Song name [dQw4w9WgXcQ].mp4"',
           f"{TAG} file {final}", f"{TAG} file {tmp_path / 'setup.exe'}", f"{TAG} file {tmp_path.parent / 'x.mp4'}"]
    made = [(final.name, b"v" * 10), ("Song name [dQw4w9WgXcQ].f137.mp4.part", b"p"),
            ("Song name [dQw4w9WgXcQ].f140.m4a", b"a"), ("Song name [dQw4w9WgXcQ].mp4.ytdl", b"y"),
            ("setup.exe", b"MZ")]
    (tmp_path.parent / "x.mp4").write_bytes(b"outside")
    seen, calls = [], []
    job, kills = _job(tmp_path, _Proc(out), made, calls)
    res = job.run(on_progress=lambda p: seen.append(dataclasses.replace(p)))
    assert res.error == "" and res.files == [final] and res.title == "Song name" and res.height == 1080
    assert sorted(p.name for p in tmp_path.iterdir()) == [final.name, "older.mp4.part"]   # parts and setup.exe gone
    assert (tmp_path.parent / "x.mp4").exists() and not kills                            # outside: not touched
    assert [(p.part, p.done, p.total) for p in seen] == [("video", 0, 0), ("video", 1000, 4000), ("video", 4000, 4000),
                                                         ("audio", 500, 1000), ("join", 1000, 1000)]
    assert all(p.title == "Song name" for p in seen) and res.playlist == 0 and res.folder is None
    opts = calls[0][1]
    assert opts["stdin"] is not None and opts["env"]["PYTHONIOENCODING"] == "utf-8"
    assert opts.get("creationflags") or opts.get("start_new_session")                     # no console, own group


@pytest.mark.parametrize("err, kind, detail", [
    ("ERROR: [youtube] dQw4w9WgXcQ: Private video. Sign in if you've been granted access to this video", "gone",
     "Private video. Sign in if you've been granted access to this video"),
    ("ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm your age. This video may be inappropriate", "login",
     "Sign in to confirm your age. This video may be inappropriate"),
    ("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable. The uploader has not made this video available in your "
     "country", "geo", "Video unavailable. The uploader has not made this video available in your country"),
    ("ERROR: [generic] Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network",
     "Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>"),
    ("ERROR: Unsupported URL: https://example.com/news", "no_video", "Unsupported URL: https://example.com/news"),
    ("ERROR: [Bandcamp] 1: This video is DRM protected", "drm", "This video is DRM protected"),
    ("ERROR: [youtube] dQw4w9WgXcQ: HTTP Error 403: Forbidden", "other", "HTTP Error 403: Forbidden"),
])
def test_a_failed_download_says_what_happened_and_leaves_nothing(tmp_path, err, kind, detail):
    job, _ = _job(tmp_path, _Proc([f"{TAG} seen not_live NA"], ["WARNING: slow", err]), [("a [x].mp4.part", b"p")])
    res = job.run()
    assert res.error == kind and res.files == [] and not list(tmp_path.iterdir()) and res.detail == detail


def test_a_live_stream_and_a_page_without_a_video(tmp_path):
    job, _ = _job(tmp_path, _Proc([f"{TAG} seen is_live NA", "[download] does not pass filter (!is_live), skipping"]))
    assert job.run().error == "live"
    job, _ = _job(tmp_path, _Proc([]))
    assert job.run().error == "no_video"


def test_a_link_to_a_playlist_downloads_one_video_and_says_so(tmp_path):
    f = tmp_path / "A [a].mp4"
    job, _ = _job(tmp_path, _Proc([f"{TAG} seen not_live 12", f"{TAG} title 720 A", f"{TAG} file {f}"]),
                  [(f.name, b"v")])
    res = job.run()
    assert res.files == [f] and res.playlist == 12 and res.height == 720


def test_a_whole_playlist_goes_into_its_own_folder(tmp_path):
    a, b = tmp_path / "Mix" / "01. A [a].mp4", tmp_path / "Mix" / "02. B [b].mp4"
    out = [f"{TAG} seen not_live 3", f"{TAG} title 1080 A", f"{TAG} dl 5 10 NA avc1 1 3", f"{TAG} file {a}",
           f"{TAG} title 1080 B", f"{TAG} dl 5 10 NA avc1 2 3", f"{TAG} file {b}"]
    seen = []
    job, _ = _job(tmp_path, _Proc(out, ["ERROR: [youtube] c: Video unavailable"]),
                  [("Mix/01. A [a].mp4", b"1"), ("Mix/02. B [b].mp4", b"2"), ("Mix/03. C [c].mp4.part", b"3")],
                  playlist=True)
    res = job.run(on_progress=lambda p: seen.append((p.title, p.index, p.count)))
    assert res.files == [a, b] and res.folder == tmp_path / "Mix" and res.error == "" and res.playlist == 0
    assert res.detail == "Video unavailable" and not (tmp_path / "Mix" / "03. C [c].mp4.part").exists()
    assert ("A", 1, 3) in seen and ("B", 2, 3) in seen


def test_stop_kills_yt_dlp_and_removes_the_unfinished_parts(tmp_path):
    (tmp_path / "older.mp4.part").write_bytes(b"x")
    stop = threading.Event()
    proc = _Proc([f"{TAG} title 1080 Long one", f"{TAG} dl 10 1000 NA avc1 NA NA"], hold=True)
    job, kills = _job(tmp_path, proc, [("Long one [z].f137.mp4.part", b"p"), ("Long one [z].f137.mp4", b"q")])
    res = job.run(stop, on_progress=lambda p: p.done and stop.set())
    assert res.error == "cancelled" and kills == [proc] and res.files == []
    assert [p.name for p in tmp_path.iterdir()] == ["older.mp4.part"]


def test_yt_dlp_that_hangs_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "STALL", 0.3)
    proc = _Proc([], hold=True)
    job, kills = _job(tmp_path, proc)
    res = job.run()
    assert res.error == "network" and kills == [proc]


def test_no_room_on_the_disk(tmp_path):
    started = []
    job = Job("yt-dlp", URL, tmp_path, popen=lambda *a, **k: started.append(a), free=lambda p: video.SPARE)
    assert job.run().error == "no_space" and not started


def test_a_playlist_is_read_before_its_card(monkeypatch):
    data = {"_type": "playlist", "title": "Mix", "playlist_count": 70,
            "entries": [{"title": f"Song {i}", "id": str(i)} for i in range(1, 51)]}
    asked = []
    run = lambda args, timeout: asked.append(args) or (0, "WARNING: x\n" + json.dumps(data))   # noqa: E731
    info = video.probe("yt-dlp", URL, run)
    assert info == {"title": "Mix", "count": 70, "entries": [f"Song {i}" for i in range(1, 51)], "playlist": True}
    assert asked[0][-2:] == ["--", URL] and "--flat-playlist" in asked[0] and "--ignore-config" in asked[0]
    with pytest.raises(video.VideoError, match="^The playlist does not exist$"):
        video.probe("yt-dlp", URL, lambda a, t: (1, "ERROR: [youtube:tab] PLx: The playlist does not exist"))


def test_finding_yt_dlp_and_its_age(tmp_path, monkeypatch):
    links = tmp_path / "Microsoft" / "WinGet" / "Links"
    links.mkdir(parents=True)
    (links / "yt-dlp.exe").write_bytes(b"MZ")
    monkeypatch.setattr(video, "sys", type("S", (), {"platform": "win32"}))
    env = {"LOCALAPPDATA": str(tmp_path), "PATH": "P"}
    assert video.find(lambda *a, **k: None, env) == str(links / "yt-dlp.exe")          # winget's own copy first
    assert video.child_path(env) == os.pathsep.join([str(links), "P"])        # a running Lanterna's PATH is old
    assert video.find(lambda name, path=None: "/usr/bin/yt-dlp", {"PATH": "P"}) == "/usr/bin/yt-dlp"
    assert video.version("yt-dlp", lambda a, t: (0, "2026.10.26\n")) == "2026.10.26"
    assert video.version("yt-dlp", lambda a, t: (0, "Traceback…")) == video.version("x", lambda a, t: (127, "")) == ""
    now = time.mktime((2026, 11, 22, 12, 0, 0, 0, 0, -1))
    assert video.is_old("2025.06.01", now) and not video.is_old("2026.10.26", now) and not video.is_old("", now)


# ---------------------------------------------------------------- in a chat
def _job_class(result, progress=(), seen=None):
    class FakeJob:
        def __init__(self, exe, url, folder, audio=False, playlist=False, ffmpeg=True, **kw):
            self.folder = folder
            if seen is not None:
                seen.append({"exe": exe, "url": url, "audio": audio, "playlist": playlist, "ffmpeg": ffmpeg})

        def run(self, stop=None, on_progress=None):
            for p in progress:
                on_progress(p)
                time.sleep(0.05)                      # the test's polls see the line
            return result(self.folder) if callable(result) else result
    return FakeJob


def _video_api(tmp_path, monkeypatch, exe="yt-dlp"):
    api = _api(tmp_path, monkeypatch)
    down = tmp_path / "Downloads"
    down.mkdir()
    monkeypatch.setattr(api, "_save_folder", lambda: down)
    monkeypatch.setattr(video, "where", lambda host, resolve=None: "public")
    monkeypatch.setattr(video, "find", lambda *a, **k: exe)
    monkeypatch.setattr(video, "has_ffmpeg", lambda *a, **k: True)
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: (_ for _ in ()).throw(AssertionError("no model")))
    return api, down


def _saved_video(folder, name="Song [dQw4w9WgXcQ].mp4"):
    f = folder / name
    f.write_bytes(b"v")
    return Result(files=[f], title="Song", height=1080)


def test_a_link_alone_is_downloaded_without_a_model(tmp_path, monkeypatch):
    api, down = _video_api(tmp_path, monkeypatch)
    jobs = []
    monkeypatch.setattr(video, "Job", _job_class(_saved_video, [Progress("Song", 50, 100)], jobs))
    monkeypatch.setattr(app, "_size_of", lambda p: 245 * 1024 ** 2)
    tid = api.new_thread()["id"]
    p, seen = _until_done(api, api.send(tid, URL)["stream"])
    assert p["error"] is None and not p["stopped"]
    assert p["final"] == "Збережено «Song» у Завантаженнях (1080p, 245,0 МБ)."
    assert jobs == [{"exe": "yt-dlp", "url": URL, "audio": False, "playlist": False, "ffmpeg": True}]
    assert any(x.get("live") == "Завантажую «Song»: 50%" for x in seen)
    assert {"kind": "tool", "text": "Шукаю відео: youtu.be"} in p["steps"]
    f = str(down / "Song [dQw4w9WgXcQ].mp4")
    assert p["sources"]["saved"] == [{"path": f, "label": "Song [dQw4w9WgXcQ].mp4", "folder": False, "size": 1}]
    last = api.messages(tid)[-1]                                       # kept with the reply: an opened chat shows it
    assert last["role"] == "assistant" and last["content"] == p["final"] and last["sources"]["saved"][0]["path"] == f


def test_a_link_alone_to_a_playlist_saves_one_and_tells_how_to_get_all(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    one = lambda folder: dataclasses.replace(_saved_video(folder), playlist=12)   # noqa: E731
    monkeypatch.setattr(video, "Job", _job_class(one))
    p, _ = _until_done(api, api.send(api.new_thread()["id"], URL)["stream"])
    assert p["final"].startswith("Збережено «Song» у Завантаженнях (1080p, 1 Б).\n\nЦе посилання на плейлист із 12 "
                                 "відео: збережено лише це. Щоб отримати всі, напиши «завантаж увесь плейлист»")


def test_a_page_without_a_video_goes_to_the_model_as_before(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "Job", _job_class(Result(error="no_video", detail="Unsupported URL")))
    fake = _Fake([["Це стаття про погоду в Кракові."]])
    router = Router([Candidate("groq", "fake-model", 50)], client_for=lambda pid: fake)
    router.current = router.candidates[0]
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    tid = api.new_thread()["id"]
    p, _ = _until_done(api, api.send(tid, "https://example.com/news/weather")["stream"])
    assert p["error"] is None and p["final"] == "Це стаття про погоду в Кракові."
    assert [m["role"] for m in api.messages(tid)] == ["user", "assistant"]


def test_without_yt_dlp_an_article_link_never_brings_an_install_card(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch, exe="")
    asked = []
    monkeypatch.setattr(api, "_run_video", lambda *a: asked.append(a))
    monkeypatch.setattr(api, "_run", lambda sid, tid, text, history, *rest: asked.append(("model", text)) or
                        api._streams[sid].__setattr__("done", True))
    tid = api.new_thread()["id"]
    api.send(tid, "https://example.com/news/weather")
    time.sleep(0.2)
    assert asked == [("model", "https://example.com/news/weather")]


def test_with_settings_computer_off_a_link_goes_to_the_model(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    api.settings.pc_access = False                    # Settings → Computer: nothing in the user's folders
    asked = []
    monkeypatch.setattr(api, "_run_video", lambda *a: asked.append("video"))
    monkeypatch.setattr(api, "_run", lambda sid, tid, text, history, *rest: asked.append("model") or
                        api._streams[sid].__setattr__("done", True))
    api.send(api.new_thread()["id"], URL)
    time.sleep(0.2)
    assert asked == ["model"] and "video_download" not in api.toolbox.tools
    api.settings.pc_access = True                     # on again: no restart needed
    assert api.toolbox.tools["video_download"].group == "video"


def test_a_link_that_looks_like_a_scam_is_never_opened(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setattr(api, "_run_video", lambda *a: asked.append("video"))
    monkeypatch.setattr(api, "_run", lambda sid, tid, text, history, *rest: asked.append("model") or
                        api._streams[sid].__setattr__("done", True))
    api.send(api.new_thread()["id"], SCAM)
    time.sleep(0.2)
    assert asked == ["model"]                   # the model explains the signs; yt-dlp never sees the link
    monkeypatch.setattr(video, "Job", lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    _, out, th = _tool_run(api, api.new_thread()["id"], url=SCAM)
    th.join(5)
    assert out[0].startswith("Not opened: this link looks like a scam")


def _installer(api, monkeypatch, found_after="C:/WinGet/Links/yt-dlp.exe"):
    """No yt-dlp yet: the card installs it (the test confirms it); after that it is found."""
    have = {"exe": ""}
    monkeypatch.setattr(video, "find", lambda *a, **k: have["exe"])
    monkeypatch.setattr(api.apps, "managers", lambda: ["winget"])
    monkeypatch.setattr(api.apps, "_busy", lambda pid: ("", ""))
    proposed = []

    def propose(op, pid, source="", parts=None):
        proposed.append((op, pid, source))
        api.actions.propose("app_install", {"id": pid, "name": "yt-dlp", "source": source},
                            lambda: have.__setitem__("exe", found_after) or "installed")
        return "Prepared."
    monkeypatch.setattr(api.apps, "propose", propose)
    return proposed


def _card(api, sid, kind):
    for _ in range(200):
        p = api.poll(sid)
        cards = [c for c in p.get("cards", []) if c["kind"] == kind]
        if cards:
            return p, cards[-1]
        time.sleep(0.02)
    raise AssertionError("no card")


def test_the_first_time_a_card_installs_yt_dlp_and_the_download_goes_on(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    proposed = _installer(api, monkeypatch)
    jobs = []
    monkeypatch.setattr(video, "Job", _job_class(_saved_video, seen=jobs))
    tid = api.new_thread()["id"]
    sid = api.send(tid, URL)["stream"]
    p, card = _card(api, sid, "app_install")
    assert proposed == [("install", "yt-dlp.yt-dlp", "winget")] and not p["done"] and not jobs
    assert p["steps"][-1]["text"] == "Для відео потрібна безкоштовна програма yt-dlp: картка, щоб її встановити"
    api.action_confirm(card["id"])
    p, _ = _until_done(api, sid)
    assert p["final"].startswith("Збережено «Song» у Завантаженнях") and jobs[0]["exe"] == "C:/WinGet/Links/yt-dlp.exe"
    assert "yt-dlp встановлено" in [s["text"] for s in p["steps"]]


def test_stop_while_the_install_card_waits(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    _installer(api, monkeypatch)
    sid = api.send(api.new_thread()["id"], URL)["stream"]
    _, card = _card(api, sid, "app_install")
    api.stop_answer(sid)
    p, _ = _until_done(api, sid)
    assert p["final"] == "Зупинено. Нічого не завантажено." and p["stopped"]
    assert api.actions.get(card["id"]).state == "cancelled"


def test_a_card_from_an_earlier_link_isnt_made_twice(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch, exe="")
    monkeypatch.setattr(api.apps, "managers", lambda: ["winget"])
    monkeypatch.setattr(api.apps, "_busy", lambda pid: ("pending", "yt-dlp"))
    p, _ = _until_done(api, api.send(api.new_thread()["id"], URL)["stream"])
    assert p["final"].startswith("Картка для встановлення yt-dlp уже є, під однією з попередніх відповідей")


def test_without_a_package_manager_it_says_where_yt_dlp_is(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch, exe="")
    monkeypatch.setattr(api.apps, "managers", lambda: [])
    p, _ = _until_done(api, api.send(api.new_thread()["id"], URL)["stream"])
    assert "https://github.com/yt-dlp/yt-dlp" in p["final"] and not p.get("cards")


def test_youtube_without_deno_offers_deno(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "Job", _job_class(Result(error="js", detail="No supported JavaScript runtime")))
    monkeypatch.setattr(app.shutil, "which", lambda name, path=None: None)
    monkeypatch.setattr(api.apps, "managers", lambda: ["winget"])
    cards = []
    monkeypatch.setattr(api.apps, "propose", lambda op, pid, source="", parts=None: cards.append((op, pid, source)))
    p, _ = _until_done(api, api.send(api.new_thread()["id"], URL)["stream"])
    assert cards == [("install", "DenoLand.Deno", "winget")]
    assert p["final"] == ("YouTube тепер потребує ще однієї безкоштовної програми, Deno (https://deno.com), а її на "
                          "цьому комп'ютері немає. Картка, щоб її встановити, нижче: підтверди її, а тоді надішли "
                          "посилання ще раз.")


def test_an_old_yt_dlp_is_offered_an_update(tmp_path, monkeypatch):
    links = tmp_path / "Links"
    api, _ = _video_api(tmp_path, monkeypatch, exe=str(links / "yt-dlp.exe"))
    monkeypatch.setattr(video, "Job", _job_class(Result(error="no_video", detail="Unable to extract")))
    monkeypatch.setattr(video, "version", lambda exe, run=None: "2025.01.15")
    monkeypatch.setattr(video, "links_dirs", lambda env=None: [links])
    monkeypatch.setattr(app.shutil, "which", lambda name, path=None: "deno")
    cards = []
    monkeypatch.setattr(api.apps, "propose", lambda op, pid, source="", parts=None: cards.append((op, pid)))
    p, _ = _until_done(api, api.send(api.new_thread()["id"], URL)["stream"])
    assert cards == [("upgrade", "yt-dlp.yt-dlp")]
    assert p["final"] == ("За цим посиланням немає відео, яке yt-dlp міг би взяти. yt-dlp тут старий (2025.01.15), а "
                          "сайти часто змінюються: оновлення може допомогти. Картка для оновлення нижче.")


@pytest.mark.parametrize("kind, text", [
    ("login", "Цей сайт віддає відео лише тим, хто увійшов в акаунт."),
    ("no_space", "На диску замало вільного місця для цього відео."),
    ("too_big", "На диску замало вільного місця для цього відео."),
    ("cancelled", "Зупинено. Незавершені частини видалено."),
    ("other", "yt-dlp не зміг це завантажити: HTTP Error 403: Forbidden"),
])
def test_what_a_failed_download_says(tmp_path, monkeypatch, kind, text):
    api, _ = _video_api(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "Job", _job_class(Result(error=kind, detail="HTTP Error 403: Forbidden")))
    monkeypatch.setattr(app.shutil, "which", lambda name, path=None: "deno")
    monkeypatch.setattr(video, "version", lambda exe, run=None: "2026.10.26")
    p, _ = _until_done(api, api.send(api.new_thread()["id"], "https://vimeo.com/76979871")["stream"])
    assert p["final"].startswith(text) and p["stopped"] == (kind == "cancelled")


def test_a_link_to_the_home_network_and_no_internet(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    for place, text in (("local", "Це посилання веде на цей комп'ютер"), ("unknown", "Не вдалося зв'язатися")):
        monkeypatch.setattr(video, "where", lambda host, resolve=None, place=place: place)
        p, _ = _until_done(api, api.send(api.new_thread()["id"], "https://nas.lan/films/a.mp4")["stream"])
        assert p["final"].startswith(text)


# ---------------------------------------------------------------- the model's tool: MP3, a whole playlist
def _tool_run(api, tid, **args):
    """video_download as the model calls it, inside a reply (its own thread, like a real answer)."""
    st = app._Stream("uk")
    out = []

    def call():
        api._here.st = st
        api.actions.bind(st.cards, tid)
        tool = api._video_tools()[0]
        out.append(tool.run(**args))
    th = threading.Thread(target=call, daemon=True)
    th.start()
    return st, out, th


def test_the_sound_of_a_whole_playlist_after_its_card(tmp_path, monkeypatch):
    api, down = _video_api(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "probe", lambda exe, url, run=None: {
        "title": "Mix", "count": 3, "entries": ["A", "B", "C"], "playlist": True})
    jobs = []

    def three(folder):
        (folder / "Mix").mkdir()
        files = [folder / "Mix" / f"0{i}. {n} [{n}].mp3" for i, n in enumerate("ABC", 1)]
        for f in files:
            f.write_bytes(b"m")
        return Result(files=files, title="A", folder=folder / "Mix")
    monkeypatch.setattr(video, "Job", _job_class(three, seen=jobs))
    tid = api.new_thread()["id"]
    st, out, th = _tool_run(api, tid, url="https://www.youtube.com/playlist?list=PL1", audio=True, playlist=True)
    for _ in range(200):
        if st.cards:
            break
        time.sleep(0.02)
    card = st.cards[-1]
    assert card["kind"] == "video_playlist" and not jobs                        # nothing before the user's yes
    d = api.actions.get(card["id"]).details
    assert app.action_title("video_playlist", d, "", "uk") == "Завантажити 3 відео з «Mix»"
    assert app.card_text("video_playlist", d, "uk").splitlines()[-4:] == [
        "1. A", "2. B", "3. C", "В окрему папку в Завантаженнях, лише звук (MP3)."]
    api.action_confirm(card["id"])
    th.join(10)
    assert jobs[0]["audio"] and jobs[0]["playlist"]
    assert out == ["Saved 3 files from the playlist «Mix» into a folder of their own in Downloads. The file's link is "
                   "under your reply by itself: don't write its path or a link."]
    assert st.saved == [{"path": str(down / "Mix"), "folder": True, "count": 3}]
    assert i18n.t("Saved {n} files from the playlist «{title}» into a folder of their own in Downloads.", "uk", n=3,
                  title="Mix") == "Збережено 3 файли з плейлиста «Mix» в окрему папку в Завантаженнях."


def test_the_playlist_card_says_so_when_it_is_cut(tmp_path, monkeypatch):
    d = {"name": "Long", "count": 50, "total": 120, "files": [f"S{i}" for i in range(50)], "url": URL}
    lines = app.card_text("video_playlist", d, "uk").splitlines()
    assert "… +38" in lines and "Лише перші 50 із 120." in lines and lines[-1].endswith("до 1080p (MP4).")
    assert app.action_title("video_playlist", d, "", "pl") == "Pobierz 50 filmów z „Long”"


def test_the_tool_only_takes_one_link_and_only_inside_a_reply(tmp_path, monkeypatch):
    api, _ = _video_api(tmp_path, monkeypatch)
    tool = api._video_tools()[0]
    assert tool.name == "video_download" and tool.group == "video" and tool.label == "⬇️"
    assert tool.run(url="дивись тут " + URL).startswith("Error: url must be one web link")
    assert tool.run(url=URL).startswith("Error: video_download works only while answering")
    assert tools.GROUPS["video"].search("скачай мені це відео з ютуба") and tools.GROUPS["video"].search(
        "save this song as mp3") and not tools.GROUPS["video"].search("яка погода завтра у Львові?")


# ---------------------------------------------------------------- the link under the reply
def test_the_window_opens_only_what_was_downloaded(tmp_path, monkeypatch):
    api, down = _video_api(tmp_path, monkeypatch)
    film, setup, folder = down / "a [x].mp4", down / "setup.exe", down / "Mix"
    folder.mkdir()
    for f in (film, setup, tmp_path / "b.mp4"):
        f.write_bytes(b"x")
    opened, shown = [], []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)
    monkeypatch.setattr(app.quiet, "open_url", lambda p: opened.append(p) or True)
    from lanterna import pcfiles
    monkeypatch.setattr(pcfiles, "_open_in_file_manager", lambda p: shown.append(p))
    assert api.open_download(str(film)) and opened == [str(film.resolve())]
    for bad in (str(setup), str(tmp_path / "b.mp4"), str(down), str(down / ".." / "b.mp4"), "", "C:\\Windows\\x.mp4"):
        assert not api.open_download(bad) and not api.show_download(bad), bad
    assert api.open_download(str(folder)) and shown == [folder.resolve()]        # a playlist's folder
    assert api.show_download(str(film)) and shown[-1] == film.resolve() and len(opened) == 1
    assert {"open_download", "show_download"} <= gui.METHODS                     # the window may call them


def test_the_saved_file_is_drawn_under_the_reply():
    raw = sources.dumps({"saved": sources.saved([Path("D:/Media/Downloads/Song [a].mp4")])})
    assert sources.view(raw)["saved"] == [{"path": str(Path("D:/Media/Downloads/Song [a].mp4")),
                                           "label": "Song [a].mp4", "folder": False}]
    many = sources.view(sources.dumps({"saved": sources.saved([1, 2], folder="D:/Downloads/Mix")}))
    assert many["saved"] == [{"path": "D:/Downloads/Mix", "label": "Mix", "folder": True, "count": 2}]
    assert sources.view(json.dumps({"saved": [{"path": "a\nb"}, {"path": 5}, "x"]})) == {}
    assert "function savedBox(src)" in JS and 'api.open_download(f.dataset.file)' in JS
    assert 'api.show_download(s.dataset.show)' in JS and 't("Files: {n}", { n: f.count })' in JS
    assert 'video_playlist: "Download {count} videos from «{name}»"' in JS and ".saved-f" in CSS
    assert "function fileSize(n)" in JS and "esc(fileSize(f.size))" in JS       # 263,2 МБ, as the reply writes it
    box = tui.sources_box({"saved": [{"path": str(Path("D:/Media/Downloads/Song [a].mp4").absolute()),
                                      "label": "Song [a].mp4"}]}, "uk")
    text = box[0].content
    assert text.plain.startswith("Збережено:\n• Song [a].mp4\n") and any(
        "link file:" in str(s.style) for s in text.spans)


# ---------------------------------------------------------------- words
def test_the_thinking_line_says_the_area_in_the_users_language():
    assert thinking.tool_step("fix_check", '{"what": "updates"}', "uk") == "Шукаю, що не так: оновлення"
    assert thinking.tool_step("fix_check", '{"what": "Sound"}', "pl") == "Szukam, co jest nie tak: dźwięk"
    assert thinking.tool_step("fix_check", '{"what": "Hollow Knight"}', "uk") == "Шукаю, що не так: Hollow Knight"
    assert thinking.tool_step("video_download", json.dumps({"url": URL}), "uk") == "Завантажую з youtu.be"


def test_what_went_to_the_model_names_the_video_site():
    from lanterna import sent
    calls = [("video_download", json.dumps({"url": URL, "audio": True})), ("video_download", json.dumps({"url": SCAM}))]
    items = sent.build("M", False, 0, False, 0, [], 0, calls)
    assert {"t": "A web page was opened: {site}", "v": {"site": "youtu.be"}} in items
    assert "secure-login" not in json.dumps(items)                  # refused, so it was never opened


def test_every_video_string_is_translated():
    new = [*app.VIDEO_SAY.values(), *app.PLAYLIST_WHERE.values(), *thinking.AREA_WORDS.values(),
           thinking.TOOL_TEXT["video_download"][0], "Looking for the video: {site}", "yt-dlp is installed",
           "Videos need the free program yt-dlp: a card to install it", "Saved «{title}» in Downloads ({what}).",
           "Saved «{title}» in Downloads.", "Not all of them came: {error}", "A card to update it is below.",
           "Saved {n} files from the playlist «{title}» into a folder of their own in Downloads.",
           "The link is a playlist of {n} videos: I saved only this one. To get them all, write “download the whole "
           "playlist” and the link.", "A card to install it is below: confirm it, then send the link again.",
           "yt-dlp here is old ({version}), and sites change often: updating it may help.",
           "Turning «{title}» into MP3", "Putting the picture and the sound of «{title}» together",
           "Downloading the sound of «{title}»: {x}", "Downloading «{title}»: {x}", "{i} of {n}",
           "Download {count} videos from «{name}»", "Downloading {count} videos from «{name}»",
           "Only the first {count} of {total}.", "Files: {n}", "Saved:"]
    for s in new:
        assert s in i18n._T and i18n._T[s]["uk"] != s and i18n._T[s]["it"] != s, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s, s) != s, (lang, s)
    assert i18n.t("Saved {n} files from the playlist «{title}» into a folder of their own in Downloads.", "en", n=1,
                  title="X") == "Saved 1 file from the playlist «X» into a folder of its own in Downloads."
