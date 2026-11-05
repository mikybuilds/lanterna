"""Is there a newer Lanterna? Asks the project's public release list when the app starts (can be turned off) and in About.

Sends nothing about the user: a plain GET of the latest release, no IDs, no stats.

Installed with Setup.exe, Lanterna updates itself: it downloads the new installer to a temporary folder, checks
it against the SHA-256 that the release page lists, runs it silently over the old version (same folder, same
shortcuts, chats and keys untouched) and opens again. The temporary file is removed on the next start.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from . import HOMEPAGE, __version__

# The project page is <host>/<owner>/<repo>; its release list lives on api.<host>.
_REPO = "/".join(HOMEPAGE.rstrip("/").split("/")[-2:])
_API = HOMEPAGE.rstrip("/").replace("//", "//api.", 1).rsplit("/", 2)[0]


def _parts(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def newer(latest: str, current: str = __version__) -> bool:
    return _parts(latest) > _parts(current)


def check(transport: httpx.BaseTransport | None = None) -> dict:
    """{"current", "latest", "newer", "url", "notes", "assets"}; latest is "" when the check failed (offline, not published yet)."""
    out = {"current": __version__, "latest": "", "newer": False, "url": HOMEPAGE + "/releases/latest", "notes": [], "assets": {}}
    try:
        with httpx.Client(base_url=_API, timeout=6, transport=transport,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "Lanterna"}) as c:
            r = c.get(f"repos/{_REPO}/releases/latest")
        if r.status_code == 200:
            data = r.json()
            out["latest"] = str(data.get("tag_name", "")).lstrip("v")
            out["newer"] = bool(out["latest"]) and newer(out["latest"])
            out["notes"] = release_notes(str(data.get("body") or ""), out["latest"])
            assets = [a for a in data.get("assets") or [] if isinstance(a, dict) and a.get("name") and a.get("browser_download_url")]
            out["assets"] = {str(a["name"]): str(a["browser_download_url"]) for a in assets}
            out["digests"] = {str(a["name"]): str(a["digest"]) for a in assets
                              if str(a.get("digest") or "").startswith("sha256:")}
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return out


def release_notes(body: str, version: str, limit: int = 6) -> list[str]:
    """The first few "- " lines of this version's section in the release text (the changelog)."""
    out, inside = [], False
    for line in body.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(version) and line[3:].strip().split(" ")[0] == version
        elif inside and line.lstrip().startswith("- "):
            out.append(line.strip()[2:].strip())
    return out[:limit]


def install_kind() -> str:
    """How this copy was installed, so the update steps fit: installer | portable | pipx | source | pip."""
    if getattr(sys, "frozen", False):
        return "installer" if (Path(sys.executable).parent / "unins000.exe").exists() else "portable"
    if "pipx" in Path(sys.prefix).as_posix().lower():
        return "pipx"
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists() and (root / "pyproject.toml").exists():
        return "source"
    return "pip"


SAME_DATA = "Your chats, settings and keys stay as they are."


def how_to(kind: str, latest: str, assets: dict | None = None) -> dict:
    """What to do for this kind of install: steps (English; the caller translates), a command to copy, a download link."""
    assets = assets or {}
    page = HOMEPAGE + "/releases/latest"
    if kind == "installer":
        name = f"Lanterna-Setup-{latest}.exe"
        return {"steps": ["Press Download and save {file}.", "Close Lanterna, then run the file you downloaded.",
                          "If Windows says “Windows protected your PC”, choose More info → Run anyway.", SAME_DATA],
                "file": name, "command": "", "download": assets.get(name, page)}
    if kind == "portable":
        name = f"Lanterna-{latest}-portable-windows.zip"
        return {"steps": ["Press Download and save {file}.", "Close Lanterna, unzip the new folder and use it instead of the old one.",
                          SAME_DATA],
                "file": name, "command": "", "download": assets.get(name, page)}
    if kind == "source":
        return {"steps": ["Close Lanterna.", "In the project folder run:", "Start Lanterna again."],
                "file": "", "command": "git pull && pip install -e .", "download": ""}
    command = "pipx upgrade lanterna" if kind == "pipx" else "pip install --upgrade git+" + HOMEPAGE
    return {"steps": ["Close Lanterna.", "Open a terminal and run:", "Start Lanterna again. " + SAME_DATA],
            "file": "", "command": command, "download": ""}


# ---------------------------------------------------------------- self-update (Windows installer)
UPDATE_DIR = Path(tempfile.gettempdir()) / "lanterna-update"
MAX_SETUP = 300 * 1024 * 1024


def setup_asset(info: dict) -> dict | None:
    """The installer of the latest release with its checksum, or None when it can't be updated automatically."""
    latest = str(info.get("latest") or "")
    name = f"Lanterna-Setup-{latest}.exe"
    url = (info.get("assets") or {}).get(name, "")
    digest = (info.get("digests") or {}).get(name, "")
    if not (latest and info.get("newer") and digest and url.startswith(f"{HOMEPAGE}/releases/download/")):
        return None
    return {"version": latest, "name": name, "url": url, "sha256": digest.split(":", 1)[1].lower()}


def cleanup(older_than: float = 60.0) -> None:
    """Removes installers left from an earlier update (only Lanterna's own temporary folder)."""
    try:
        for f in UPDATE_DIR.glob("Lanterna-Setup-*"):
            if time.time() - f.stat().st_mtime > older_than:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def launch_setup(path: Path, lang: str = "en") -> None:
    """Runs the installer silently over this copy; it closes Lanterna if needed and opens it again when done."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(path), *setup_args(lang)], creationflags=flags, close_fds=True)


def setup_args(lang: str = "en") -> list[str]:
    """Inno Setup switches: no windows, close the running app, open it again afterwards (RELAUNCH is ours)."""
    names = ["VERYSILENT", "SUPPRESSMSGBOXES", "NORESTART", "CLOSEAPPLICATIONS", "RELAUNCH=1",
             "LANG=" + (lang if lang in ("en", "uk", "it") else "en")]
    return [chr(47) + n for n in names]


# ---------------------------------------------------------------- self-update (Linux, installed with pipx)
PIPX_TIMEOUT = 900


def pipx_asset(info: dict, kind: str | None = None, which: Callable[[str], str | None] = shutil.which) -> dict | None:
    """Update now for a pipx install: Lanterna runs pipx itself. None when pipx is not there."""
    kind = kind or install_kind()
    if kind != "pipx" or not info.get("newer") or not info.get("latest") or not which("pipx"):
        return None
    return {"version": str(info["latest"]), "pipx": True}


def run_pipx(args: list[str], timeout: float = PIPX_TIMEOUT) -> tuple[int, str]:
    exe = shutil.which("pipx")
    if not exe:
        return 127, "pipx was not found"
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=timeout, start_new_session=True)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "pipx took too long"
    except OSError as e:
        return 126, str(e)


def pipx_update(version: str, runner: Callable[[list[str]], tuple[int, str]] = run_pipx) -> str:
    """pipx upgrade; if pipx thinks it is up to date (an install pinned to an old tag), reinstall that release."""
    code, out = runner(["upgrade", "lanterna"])
    if code == 0 and "already at latest" not in out.lower():
        return out
    if code not in (0, 1):
        raise RuntimeError(_tail(out) or f"pipx stopped with code {code}")
    code, out = runner(["install", "--force", f"git+{HOMEPAGE}@v{version}"])
    if code != 0:
        raise RuntimeError(_tail(out) or f"pipx stopped with code {code}")
    return out


def _tail(out: str) -> str:
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return " ".join(lines[-3:])[-300:]


def restart_args() -> list[str]:
    """How to start this Lanterna again after an update: the same command it was started with."""
    exe = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if exe and os.path.isfile(exe) and os.access(exe, os.X_OK) and not exe.endswith(".py"):
        return [exe, *sys.argv[1:]]
    return [sys.executable, "-m", "lanterna.cli", *sys.argv[1:]]


class Updater:
    """phase: idle · downloading · installing · restart (pipx: installed, start again) · error. The UI polls status()."""

    def __init__(self, transport: httpx.BaseTransport | None = None,
                 launch: Callable[[Path, str], None] = launch_setup, quit_app: Callable[[], None] | None = None,
                 folder: Path | None = None, pipx_runner: Callable[[list[str]], tuple[int, str]] = run_pipx):
        self.transport, self.launch, self.pipx_runner = transport, launch, pipx_runner
        self.quit_app = quit_app or (lambda: os._exit(0))
        self.folder = folder or UPDATE_DIR
        self.phase, self.error, self.done, self.total, self.version = "idle", "", 0, 0, ""
        self._lock = threading.Lock()

    def status(self) -> dict:
        return {"phase": self.phase, "error": self.error, "done": self.done, "total": self.total, "version": self.version}

    def start(self, asset: dict, lang: str = "en", wait: bool = False) -> dict:
        with self._lock:
            if self.phase in ("downloading", "installing"):
                return self.status()
            self.phase, self.error, self.done, self.total, self.version = "downloading", "", 0, 0, asset["version"]
        th = threading.Thread(target=self._run, args=(asset, lang), daemon=True)
        th.start()
        if wait:
            th.join()
        return self.status()

    def _run(self, asset: dict, lang: str) -> None:
        if asset.get("pipx"):
            try:
                self.phase = "installing"
                pipx_update(asset["version"], self.pipx_runner)
                self.phase = "restart"
            except Exception as e:                # noqa: BLE001  the old version keeps working
                self.phase, self.error = "error", str(e)[:200] or e.__class__.__name__
            return
        try:
            path = self.download(asset)
            self.phase = "installing"
            self.launch(path, lang)
            time.sleep(1.5)                       # let the UI say "Lanterna will open again"
            self.quit_app()
        except Exception as e:                    # noqa: BLE001  shown in the dialog, the old version keeps working
            self.phase, self.error = "error", str(e)[:200] or e.__class__.__name__

    def download(self, asset: dict) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        dest = self.folder / asset["name"]
        part = dest.with_suffix(".part")
        sha = hashlib.sha256()
        with httpx.Client(timeout=60, follow_redirects=True, transport=self.transport,
                          headers={"User-Agent": "Lanterna"}) as c, c.stream("GET", asset["url"]) as r:
            if r.status_code != 200:
                raise RuntimeError(f"download failed: HTTP {r.status_code}")
            self.total = int(r.headers.get("content-length") or 0)
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(256 * 1024):
                    self.done += len(chunk)
                    if self.done > MAX_SETUP:
                        raise RuntimeError("the file is too big")
                    sha.update(chunk)
                    f.write(chunk)
        if sha.hexdigest() != asset["sha256"]:
            part.unlink(missing_ok=True)
            raise RuntimeError("the downloaded file is damaged (checksum mismatch)")
        part.replace(dest)
        return dest
