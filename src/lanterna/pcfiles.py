"""The user's own folders: Downloads, Desktop, Documents, Pictures, Videos, Music.

Rules
- Only these folders (where the system says they are) and what is inside them. Hidden files and folders
  (names starting with a dot) and links out of them are never used.
- Looking (overview, lists, reading a file) happens right away: the text goes to the model in use.
- Every change is only proposed: the user sees a card (what moves where, what goes to the Recycle Bin) and
  presses Confirm. Deleting means the Recycle Bin / Trash, never for good. A sort can be undone.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from . import quiet
from .files import IMAGE_EXT, FileError, prepare_one
from .workspace import NEVER_WRITE, WAITING, WorkError

PLACES = ("downloads", "desktop", "documents", "pictures", "videos", "music")
LIST_LIMIT = 200
BATCH_LIMIT = 2000                 # files in one card
READ_LIMIT = 12000
FRESH = 120                        # files changed in the last 2 minutes may still be downloading: left alone
PARTIAL = {".crdownload", ".part", ".partial", ".download", ".tmp", ".opdownload"}

# Windows: HKCU\...\User Shell Folders value names (Downloads has only a GUID)
_WIN_NAMES = {"downloads": "{374DE290-123F-4565-9164-39C4925E467B}", "desktop": "Desktop", "documents": "Personal",
              "pictures": "My Pictures", "videos": "My Video", "music": "My Music"}
_XDG = {"downloads": "DOWNLOAD", "desktop": "DESKTOP", "documents": "DOCUMENTS", "pictures": "PICTURES",
        "videos": "VIDEOS", "music": "MUSIC"}
_FALLBACK = {"downloads": "Downloads", "desktop": "Desktop", "documents": "Documents", "pictures": "Pictures",
             "videos": "Videos", "music": "Music"}

CATEGORIES = {        # category → extensions (lower case, with the dot)
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls", ".xlsx", ".ods", ".csv", ".ppt",
                  ".pptx", ".odp", ".epub", ".pages", ".numbers", ".key", ".tex"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".svg", ".ico",
               ".raw", ".cr2", ".nef", ".psd", ".avif"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v", ".flv", ".3gp"},
    "Music": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus", ".mid", ".midi"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".iso", ".img"},
    "Installers": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle", ".dmg", ".pkg", ".deb", ".rpm",
                   ".appimage", ".flatpakref", ".apk"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".c", ".cpp", ".h", ".hpp",
             ".cs", ".java", ".kt", ".go", ".rs", ".sh", ".ps1", ".bat", ".ipynb", ".sql", ".php", ".rb", ".lua"},
    "Torrents": {".torrent"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2"},
}
CATEGORY_ORDER = list(CATEGORIES) + ["Other"]


def category(p: Path | str) -> str:
    ext = Path(p).suffix.lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return "Other"


def size_text(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


# ---------------------------------------------------------------- where the folders are
def _windows_folder(place: str) -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            raw, _ = winreg.QueryValueEx(k, _WIN_NAMES[place])
        return Path(os.path.expandvars(str(raw)))
    except OSError:
        return None


def _xdg_folder(place: str) -> Path | None:
    f = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
    try:
        text = f.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(rf'^XDG_{_XDG[place]}_DIR="([^"]*)"', text, re.M)
    if not m:
        return None
    return Path(m.group(1).replace("$HOME", str(Path.home())))


def known_folders() -> dict[str, Path]:
    """place → folder, only those that exist and are not the home folder itself."""
    out = {}
    home = Path.home().resolve()
    for place in PLACES:
        p = (_windows_folder(place) if sys.platform == "win32" else _xdg_folder(place)) or Path.home() / _FALLBACK[place]
        try:
            p = p.resolve()
        except OSError:
            continue
        if p.is_dir() and p != home and p.parent != p:
            out[place] = p
    return out


# ---------------------------------------------------------------- Recycle Bin / Trash
def _trash_windows(paths: list[Path]) -> None:
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    for p in paths:
        op = SHFILEOPSTRUCTW(None, FO_DELETE, str(p) + "\0", None,
                             FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc or op.fAnyOperationsAborted or p.exists():
            raise WorkError(f"Windows couldn't move '{p.name}' to the Recycle Bin (code {rc}).")


def _trash_linux(paths: list[Path]) -> None:
    gio = shutil.which("gio")
    for p in paths:
        if gio:
            r = subprocess.run([gio, "trash", "--", str(p)], capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and not p.exists():
                continue
        _trash_freedesktop(p)


def _trash_freedesktop(p: Path) -> None:
    """The Trash of the freedesktop.org spec, in the home folder's own disk only."""
    base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash"
    files, info = base / "files", base / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    if os.stat(p).st_dev != os.stat(files).st_dev:
        raise WorkError(f"'{p.name}' is on another disk; the Trash can't take it.")
    name, i = p.name, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        i += 1
        name = f"{p.stem}.{i}{p.suffix}"
    from urllib.parse import quote
    (info / f"{name}.trashinfo").write_text(
        f"[Trash Info]\nPath={quote(str(p))}\nDeletionDate={dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n",
        encoding="utf-8")
    os.rename(p, files / name)


def to_trash(paths: list[Path]) -> None:
    (_trash_windows if sys.platform == "win32" else _trash_linux)(paths)


MB, GB = 1024 ** 2, 1024 ** 3
INSTALLERS = {".exe", ".msi", ".msix", ".dmg", ".pkg", ".deb", ".rpm", ".appimage", ".iso", ".flatpakref"}


def _age(seconds: float) -> str:
    days = int(seconds // 86400)
    return "today" if days < 1 else f"{days} days ago" if days < 60 else f"{days // 30} months ago" if days < 730 \
        else f"{days // 365} years ago"


def _tree_size(root: Path, limit: int = 100_000, seconds: float = 6.0) -> int:
    """Size of a folder tree; stops early (a lower bound) after `limit` files or `seconds`."""
    total = n = 0
    t0 = time.time()
    for dirpath, _dirs, names in os.walk(root):
        if time.time() - t0 > seconds:
            return total
        for name in names:
            n += 1
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
            if n > limit:
                return total
    return total


def trash_size() -> int:
    """How big the user's Recycle Bin / Trash is (only what this user can see)."""
    if sys.platform == "win32":
        total = 0
        for drive in {Path.home().drive or "C:", "C:"}:
            base = Path(drive + "\\") / "$Recycle.Bin"
            try:
                for d in base.iterdir():
                    try:
                        total += _tree_size(d)
                    except OSError:
                        continue
            except OSError:
                continue
        return total
    base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash" / "files"
    return _tree_size(base) if base.is_dir() else 0


def temp_size() -> int:
    import tempfile
    try:
        return _tree_size(Path(tempfile.gettempdir()))
    except OSError:
        return 0


# ---------------------------------------------------------------- back from the Recycle Bin / Trash
def restore_from_trash(paths: list[str]) -> tuple[int, int]:
    """Puts files Lanterna moved to the Recycle Bin back where they were. Returns (restored, not found).
    A file is skipped when something with that name is there again, or it was emptied from the bin."""
    back = gone = 0
    for p in map(Path, paths):
        if p.exists():
            gone += 1
            continue
        try:
            ok = (_restore_windows if sys.platform == "win32" else _restore_freedesktop)(p)
        except OSError:
            ok = False
        back, gone = (back + 1, gone) if ok else (back, gone + 1)
    return back, gone


def _restore_freedesktop(p: Path) -> bool:
    from urllib.parse import unquote
    base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash"
    best, best_date = None, ""
    for info in (base / "info").glob("*.trashinfo"):
        try:
            text = info.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        path = next((unquote(ln[5:].strip()) for ln in text.splitlines() if ln.startswith("Path=")), "")
        date = next((ln[13:].strip() for ln in text.splitlines() if ln.startswith("DeletionDate=")), "")
        if path == str(p) and date >= best_date:
            best, best_date = info, date
    if best is None:
        return False
    item = base / "files" / best.name[: -len(".trashinfo")]
    if not item.exists():
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item), str(p))
    best.unlink(missing_ok=True)
    return True


def _recycle_info(data: bytes) -> tuple[int, str] | None:
    """A Windows Recycle Bin $I file: (deletion time as FILETIME, original path)."""
    import struct
    if len(data) < 24:
        return None
    version, _size, when = struct.unpack_from("<qqq", data, 0)
    if version == 2 and len(data) >= 28:
        n = struct.unpack_from("<i", data, 24)[0]
        raw = data[28:28 + n * 2]
    elif version == 1:
        raw = data[24:24 + 520]
    else:
        return None
    return when, raw.decode("utf-16-le", errors="replace").split("\0", 1)[0]


def _restore_windows(p: Path) -> bool:
    drive = p.drive or "C:"
    base = Path(drive + "\\") / "$Recycle.Bin"
    best, best_when = None, -1
    try:
        folders = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        return False
    try:
        p = p.parent.resolve() / p.name                       # the bin keeps long names, not 8.3 short ones
    except OSError:
        pass
    want = str(p).lower()
    for d in folders:
        try:
            infos = list(d.glob("$I*"))                      # other users' folders can't be listed: skipped
        except OSError:
            continue
        for i in infos:
            try:
                parsed = _recycle_info(i.read_bytes())
            except OSError:
                continue
            if parsed and parsed[1].lower() == want and parsed[0] > best_when:
                best, best_when = i, parsed[0]
    if best is None:
        return False
    item = best.with_name("$R" + best.name[2:])
    if not item.exists():
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item), str(p))
    best.unlink(missing_ok=True)
    return True


def free_name(p: Path, taken: set | None = None) -> Path:
    """p, or 'name (2).ext' etc. if that exists already."""
    taken = taken or set()
    if not p.exists() and p not in taken:
        return p
    for i in range(2, 10000):
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists() and q not in taken:
            return q
    raise WorkError(f"Too many files called '{p.name}'.")


# ---------------------------------------------------------------- the tools' logic
class Places:
    def __init__(self, actions, lang: Callable[[], str] = lambda: "en", folders: Callable[[], dict] = known_folders,
                 trash: Callable[[list], None] = to_trash, opener: Callable[[Path], None] | None = None):
        self.actions, self.lang, self._folders, self._trash = actions, lang, folders, trash
        self._opener = opener or _open_in_file_manager
        self.undo: dict[str, list[tuple[str, str]]] = {}      # sort id → [(from, to)] for "Undo"
        self.last_undo = (0, 0)
        self._lock = threading.Lock()

    # -- paths
    def folders(self) -> dict[str, Path]:
        return self._folders()

    def roots(self) -> set[str]:
        out = set()
        for p in self.folders().values():
            out.add(str(p))
            try:
                out.add(str(p.resolve()))
            except OSError:
                pass
        return out

    def root(self, place: str) -> Path:
        place = str(place or "").strip().lower()
        f = self.folders()
        if place not in f:
            have = ", ".join(f) or "none"
            raise WorkError(f"Unknown folder '{place}'. Available: {have}.")
        return f[place].resolve()

    def path(self, place: str, rel: str = "") -> Path:
        root = self.root(place)
        rel = str(rel or "").strip().replace("\\", "/").strip("/")
        if rel in ("", "."):
            return root
        if any(part.startswith(".") for part in rel.split("/")):
            raise WorkError("Hidden files and folders (names starting with a dot) are not used.")
        p = (root / rel).resolve()
        if p != root and not p.is_relative_to(root):
            raise WorkError(f"'{rel}' is outside the {place} folder.")
        return p

    def rel(self, place: str, p: Path) -> str:
        return p.relative_to(self.root(place)).as_posix() or "."

    def _visible(self, d: Path):
        try:
            for x in d.iterdir():
                if x.name.startswith(".") or x.name.lower() in ("desktop.ini", "thumbs.db"):
                    continue
                yield x
        except OSError as e:
            raise WorkError(f"Can't open '{d.name}': {e.strerror or e}") from e

    # -- looking
    def places(self) -> str:
        lines = []
        for place, p in self.folders().items():
            try:
                n = sum(1 for _ in self._visible(p))
            except WorkError:
                n = "?"
            lines.append(f"- {place}: {p} ({n} items)")
        return "The user's folders:\n" + "\n".join(lines) if lines else "No user folders were found."

    def overview(self, place: str, path: str = "") -> str:
        d = self.path(place, path)
        if not d.is_dir():
            raise WorkError(f"'{path}' is not a folder.")
        now = time.time()
        by_cat: dict[str, list] = {}
        dirs, files = [], []
        for x in self._visible(d):
            try:
                st = x.stat()
            except OSError:
                continue
            if x.is_dir():
                dirs.append(x.name)
            else:
                files.append((x, st))
                by_cat.setdefault(category(x), []).append(st.st_size)
        total = sum(st.st_size for _, st in files)
        lines = [f"Folder {place}/{self.rel(place, d)}: {len(files)} files ({size_text(total)}), {len(dirs)} subfolders."]
        for c in CATEGORY_ORDER:
            if c in by_cat:
                lines.append(f"- {c}: {len(by_cat[c])} files, {size_text(sum(by_cat[c]))}")
        if files:
            old = [f for f, st in files if now - st.st_mtime > 180 * 86400]
            lines.append(f"Older than 6 months: {len(old)} files.")
            big = sorted(files, key=lambda f: -f[1].st_size)[:8]
            lines.append("Biggest: " + "; ".join(f"{f.name} ({size_text(st.st_size)})" for f, st in big))
            newest = sorted(files, key=lambda f: -f[1].st_mtime)[:5]
            lines.append("Newest: " + "; ".join(f"{f.name} ({dt.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d})" for f, st in newest))
        if dirs:
            lines.append("Subfolders: " + ", ".join(sorted(dirs)[:40]) + (" …" if len(dirs) > 40 else ""))
        return "\n".join(lines)

    def list(self, place: str, path: str = "", sort: str = "name", kind: str = "") -> str:
        d = self.path(place, path)
        if not d.is_dir():
            raise WorkError(f"'{path}' is not a folder.")
        items = []
        for x in self._visible(d):
            try:
                st = x.stat()
            except OSError:
                continue
            if kind and (x.is_dir() or category(x).lower() != kind.lower()):
                continue
            items.append((x, st))
        key = {"size": lambda i: -i[1].st_size, "date": lambda i: -i[1].st_mtime}.get(
            sort, lambda i: (not i[0].is_dir(), i[0].name.lower()))
        items.sort(key=key)
        lines = []
        for x, st in items[:LIST_LIMIT]:
            when = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            lines.append(f"📁 {x.name}/" if x.is_dir() else f"📄 {x.name}  ({size_text(st.st_size)}, {when})")
        more = f"\n… and {len(items) - LIST_LIMIT} more" if len(items) > LIST_LIMIT else ""
        return f"{place}/{self.rel(place, d)} ({len(items)} items):\n" + ("\n".join(lines) or "(empty)") + more

    def find(self, text: str, place: str = "") -> str:
        q = str(text or "").strip().lower()
        if not q:
            raise WorkError("Say what to look for.")
        hits, seen = [], 0
        for pl in ([place] if place else list(self.folders())):
            root = self.root(pl)
            for dirpath, dirs, names in os.walk(root):
                dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "__pycache__")]
                for n in names:
                    seen += 1
                    if q in n.lower() and not n.startswith("."):
                        hits.append(f"{pl}/{Path(dirpath, n).relative_to(root).as_posix()}")
                if seen > 20000 or len(hits) >= 40:
                    break
        return ("Found:\n" + "\n".join(hits)) if hits else f"No file names with '{text}'."

    def read(self, place: str, path: str, start: int = 0) -> str:
        p = self.path(place, path)
        if not p.is_file():
            raise WorkError(f"There is no file '{path}' in {place}.")
        if p.suffix.lower() in IMAGE_EXT:
            return f"'{p.name}' is a picture. Ask the user to attach it to the chat to look at it."
        if p.stat().st_size > 20 * 1024 * 1024:
            return f"'{p.name}' is too big to read ({size_text(p.stat().st_size)})."
        from .github import looks_secret
        data = p.read_bytes()
        if looks_secret(p.name, data):
            return (f"'{p.name}' looks like it holds a password, key or token, so Lanterna doesn't read it "
                    "(it would go to the model). The user can open it themselves.")
        try:
            body = prepare_one(p.name, data)[0] if p.suffix.lower() in (".pdf", ".docx") else \
                data[:800_000].decode("utf-8", "replace")
        except FileError as e:
            raise WorkError(str(e)) from e
        start = max(0, int(start or 0))
        part = body[start:start + READ_LIMIT]
        more = f"\n[… more: call pc_read again with start={start + READ_LIMIT}]" if len(body) > start + READ_LIMIT else ""
        return f"File {place}/{self.rel(place, p)}:\n{part}{more}"

    def duplicates(self, place: str, path: str = "") -> str:
        d = self.path(place, path)
        by_size: dict[int, list[Path]] = {}
        for dirpath, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for n in names:
                if n.startswith("."):
                    continue
                p = Path(dirpath, n)
                try:
                    s = p.stat().st_size
                except OSError:
                    continue
                if s > 0:
                    by_size.setdefault(s, []).append(p)
        groups = []
        for s, ps in by_size.items():
            if len(ps) < 2:
                continue
            by_hash: dict[str, list[Path]] = {}
            for p in ps[:20]:
                try:
                    h = hashlib.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                    by_hash.setdefault(h.hexdigest(), []).append(p)
                except OSError:
                    continue
            groups += [(s, g) for g in by_hash.values() if len(g) > 1]
        if not groups:
            return f"No duplicate files in {place}/{self.rel(place, d)}."
        groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
        waste = sum(s * (len(g) - 1) for s, g in groups)
        lines = [f"{len(groups)} groups of identical files; removing the extra copies frees {size_text(waste)}:"]
        for s, g in groups[:30]:
            newest = sorted(g, key=lambda p: p.stat().st_mtime)
            lines.append(f"- {size_text(s)}: " + " = ".join(self.rel(place, p) for p in newest))
        return "\n".join(lines)

    def show(self, place: str, path: str = "") -> str:
        p = self.path(place, path)
        if not p.exists():
            raise WorkError(f"There is no '{path}' in {place}.")
        self._opener(p)
        return f"Opened {place}/{self.rel(place, p)} in the file manager."

    # -- changes (cards)
    def _files(self, place: str, paths: list[str]) -> list[Path]:
        if not paths:
            raise WorkError("Name at least one file.")
        out = []
        for rel in paths[:BATCH_LIMIT]:
            p = self.path(place, rel)
            if p == self.root(place):
                raise WorkError(f"The {place} folder itself can't be used here.")
            if not p.exists():
                raise WorkError(f"There is no '{rel}' in {place}.")
            out.append(p)
        return out

    # -- where the space goes (Settings → Computer → Help free up space)
    def space_report(self, place: str = "") -> str:
        """Read-only: free space, the biggest and oldest big files, old installers, the Recycle Bin and temp files."""
        places = [place] if place else list(self.folders())
        now, files, walked, t0 = time.time(), [], 0, time.time()
        for pl in places:
            root = self.path(pl)
            for dirpath, dirs, names in os.walk(root):
                dirs[:] = [x for x in dirs if not x.startswith(".") and not os.path.islink(os.path.join(dirpath, x))]
                for n in names:
                    if n.startswith("."):
                        continue
                    walked += 1
                    fp = Path(dirpath) / n
                    try:
                        st = fp.lstat()
                    except OSError:
                        continue
                    if st.st_size >= 20 * MB:
                        files.append((st.st_size, st.st_mtime, pl, self.rel(pl, fp)))
                if walked > 200_000 or time.time() - t0 > 20:
                    break
            if walked > 200_000 or time.time() - t0 > 20:
                break
        lines = []
        seen_dev = set()
        for pl in places:
            try:
                du = shutil.disk_usage(self.root(pl))
            except OSError:
                continue
            key = (du.total, du.free)
            if key in seen_dev:
                continue
            seen_dev.add(key)
            low = " — almost full" if du.free < du.total * 0.1 or du.free < 10 * GB else ""
            lines.append(f"Disk with {pl}: {size_text(du.free)} free of {size_text(du.total)}{low}")
        big = sorted(files, reverse=True)[:15]
        if big:
            lines.append("\nBiggest files:")
            lines += [f"- {pl}/{rel} — {size_text(sz)}, changed {_age(now - mt)}" for sz, mt, pl, rel in big if sz >= 100 * MB] \
                or ["- none over 100 MB"]
        old = sorted((f for f in files if now - f[1] > 365 * 86400), reverse=True)[:10]
        if old:
            lines.append(f"\nBig files not changed for over a year ({size_text(sum(f[0] for f in old))}):")
            lines += [f"- {pl}/{rel} — {size_text(sz)}, {_age(now - mt)}" for sz, mt, pl, rel in old]
        inst = []
        if "downloads" in self.folders() and (not place or place == "downloads"):
            for x in self._visible(self.path("downloads")):
                try:
                    st = x.stat()
                except OSError:
                    continue
                if x.is_file() and x.suffix.lower() in INSTALLERS and now - st.st_mtime > 30 * 86400:
                    inst.append((st.st_size, x.name))
        if inst:
            lines.append(f"\nOld installers in Downloads (already used, usually safe to remove; {size_text(sum(s for s, _ in inst))}):")
            lines += [f"- downloads/{n} — {size_text(s)}" for s, n in sorted(inst, reverse=True)[:15]]
        rb, tmp = trash_size(), temp_size()
        if rb:
            lines.append(f"\nRecycle Bin: {size_text(rb)}. Only the user can empty it (Lanterna never deletes for good).")
        if tmp > 500 * MB:
            lines.append(f"Temporary files of programs: {size_text(tmp)}. The system's own cleanup removes them safely "
                         "(Windows: Settings → Storage → Temporary files; open it with pc_settings_page 'storage').")
        lines.append("\nTo free space: suggest what can go to the Recycle Bin (pc_trash, the user confirms on a card) — "
                     "old installers and duplicates first. Never suggest deleting documents or photos the user may need "
                     "without asking which ones.")
        return "\n".join(lines)

    def loose_count(self, place: str = "downloads") -> int:
        """Files lying loose in a folder (not in subfolders, not still downloading): for the weekly tidy-up."""
        now, n = time.time(), 0
        try:
            for x in self._visible(self.path(place)):
                try:
                    if x.is_file() and x.suffix.lower() not in PARTIAL and now - x.stat().st_mtime >= FRESH:
                        n += 1
                except OSError:
                    continue
        except (OSError, WorkError):
            return 0
        return n

    def propose_sort(self, place: str, path: str = "", by: str = "type", older_than_days: int = 0) -> str:
        from .i18n import t
        d = self.path(place, path)
        if not d.is_dir():
            raise WorkError(f"'{path}' is not a folder.")
        lang, now = self.lang(), time.time()
        moves, skipped = [], 0
        for x in sorted(self._visible(d), key=lambda x: x.name.lower()):
            if x.is_dir():
                continue
            try:
                st = x.stat()
            except OSError:
                continue
            if x.suffix.lower() in PARTIAL or now - st.st_mtime < FRESH:
                skipped += 1                         # maybe still downloading
                continue
            if older_than_days and now - st.st_mtime < older_than_days * 86400:
                continue
            when = dt.datetime.fromtimestamp(st.st_mtime)
            cat = t(category(x), lang)
            sub = {"date": f"{when:%Y-%m}", "type_date": f"{cat}/{when:%Y}"}.get(by, cat)
            moves.append((x, sub, st.st_size))
        if not moves:
            return "Nothing to sort here: no loose files" + (" (some are still downloading)" if skipped else "") + "."
        if len(moves) > BATCH_LIMIT:
            moves = moves[:BATCH_LIMIT]
        groups: dict[str, list[str]] = {}
        for x, sub, _ in moves:
            groups.setdefault(sub, []).append(x.name)
        base = self.rel(place, d)
        plan = [(self.rel(place, x), (f"{base}/{sub}" if base != "." else sub)) for x, sub, _ in moves]
        details = {"place": place, "path": base, "dir": str(d), "count": len(plan), "by": by,
                   "size": sum(s for *_, s in moves), "skipped": skipped,
                   "groups": [{"to": k, "count": len(v), "files": v[:12]} for k, v in sorted(groups.items())]}
        sid = uuid.uuid4().hex[:10]
        details["undo"] = sid

        def run() -> str:
            done = self._move_many(place, [(a, f"{b}/{Path(a).name}") for a, b in plan])
            self.undo[sid] = done
            self.actions.note_undo({"type": "moves", "moves": done})
            return f"{len(done)} files sorted into {len(groups)} folders|undo:{sid}"
        self.actions.propose("pc_sort", details, run)
        return WAITING + f" Plan: {len(plan)} files into {len(groups)} folders: " + ", ".join(
            f"{k} ({len(v)})" for k, v in sorted(groups.items())) + "."

    def propose_move(self, place: str, paths: list[str], to: str, to_place: str = "") -> str:
        files = self._files(place, paths)
        to_place = to_place or place
        dest = self.path(to_place, to)
        if dest.exists() and not dest.is_dir():
            raise WorkError(f"'{to}' is a file, not a folder.")
        for p in files:
            if p.is_dir() and (dest == p or dest.is_relative_to(p)):
                raise WorkError(f"'{p.name}' can't go inside itself.")
        dest_rel = self.rel(to_place, dest)
        plan = [(self.rel(place, p), p.name if dest_rel == "." else f"{dest_rel}/{p.name}") for p in files]
        details = {"place": place, "to_place": to_place, "to": self.rel(to_place, dest), "count": len(plan),
                   "files": [a for a, _ in plan][:40], "size": sum(_size_of(p) for p in files)}

        def run() -> str:
            done = self._move_many(place, plan, to_place)
            self.actions.note_undo({"type": "moves", "moves": done})
            return f"{len(done)} moved to {to_place}/{details['to']}"
        self.actions.propose("pc_move", details, run)
        return WAITING

    def propose_rename(self, place: str, path: str, new_name: str) -> str:
        p = self._files(place, [path])[0]
        new_name = str(new_name or "").strip()
        if not new_name or "/" in new_name or "\\" in new_name or new_name.startswith("."):
            raise WorkError("Give a plain new name (no folders, not starting with a dot).")
        if Path(new_name).suffix.lower() in NEVER_WRITE and Path(new_name).suffix.lower() != p.suffix.lower():
            raise WorkError(f"Lanterna doesn't make {Path(new_name).suffix} files.")
        q = p.with_name(new_name)
        if q.exists():
            raise WorkError(f"'{new_name}' already exists there.")
        a, b = self.rel(place, p), self.rel(place, q)

        def run() -> str:
            self.actions.note_undo({"type": "moves", "moves": self._move_many(place, [(a, b)])})
            return f"{a} → {b}"
        self.actions.propose("pc_rename", {"place": place, "path": a, "to": b, "dir": str(p.parent)}, run)
        return WAITING

    def propose_mkdir(self, place: str, path: str) -> str:
        p = self.path(place, path)
        if p.exists():
            raise WorkError(f"'{path}' already exists.")
        rel = self.rel(place, p)

        def run() -> str:
            q = self.path(place, rel)
            q.mkdir(parents=True, exist_ok=False)
            self.actions.note_undo({"type": "rmdir", "path": str(q)})
            return f"{place}/{rel}"
        self.actions.propose("pc_mkdir", {"place": place, "path": rel}, run)
        return WAITING

    def propose_trash(self, place: str, paths: list[str], reason: str = "") -> str:
        files = self._files(place, paths)
        rels = [self.rel(place, p) for p in files]
        details = {"place": place, "count": len(rels), "files": rels[:60], "size": sum(_size_of(p) for p in files),
                   "reason": str(reason or "")[:200]}

        def run() -> str:
            ps = [self.path(place, r) for r in rels]
            missing = [r for r, p in zip(rels, ps) if not p.exists()]
            there = [p for p in ps if p.exists()]
            self._trash(there)
            self.actions.note_undo({"type": "trash", "paths": [str(p) for p in there]})
            return f"{len(ps) - len(missing)} moved to the Recycle Bin" + (f"; already gone: {', '.join(missing[:5])}" if missing else "")
        self.actions.propose("pc_trash", details, run)
        return WAITING + " (They go to the Recycle Bin / Trash and can be restored from there.)"

    def _move_many(self, place: str, plan: list[tuple[str, str]], to_place: str = "") -> list[tuple[str, str]]:
        """Moves files (paths re-checked now); a name that is taken gets ' (2)'. Returns [(from, to)] absolute."""
        to_place = to_place or place
        done, taken = [], set()
        with self._lock:
            for a, b in plan:
                src, dst = self.path(place, a), self.path(to_place, b)
                if not src.exists():
                    continue
                dst = free_name(dst, taken)
                taken.add(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                done.append((str(src), str(dst)))
        return done

    def undo_sort(self, sid: str, moves: list | None = None) -> str:
        moves = self.undo.pop(str(sid), None) if moves is None else moves
        if moves is None:
            raise WorkError("This sort can't be undone any more (Lanterna was restarted or it was undone already).")
        from .history import undo_moves
        back, left = undo_moves(moves, self.roots())
        self.last_undo = (back, left)
        return f"{back} files are back where they were" + (f"; {left} had been moved or replaced since" if left else "")


def _size_of(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _open_in_file_manager(p: Path) -> None:
    if sys.platform == "win32":
        args = ["explorer", "/select,", str(p)] if p.is_file() else ["explorer", str(p)]
        quiet.spawn(args)
    else:
        target = p.parent if p.is_file() else p
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener:
            quiet.spawn([opener, str(target)] if opener.endswith("xdg-open") else [opener, "open", str(target)])


# ---------------------------------------------------------------- tools
def space_tools(pl: Places) -> list:
    """Settings → Computer → Help free up space (off by default)."""
    from .tools import Tool, _obj
    places = list(pl.folders())
    if not places:
        return []
    return [Tool("pc_space", "Where the disk space goes: free space, the biggest files in the user's folders, big files "
                 "not touched for a year, old installers in Downloads, the Recycle Bin and temporary files. Read-only. "
                 "Call it when the user asks to free up space, why the disk is full, or what takes the most space.",
                 _obj({"place": {"type": "string", "enum": places, "description": "one folder, or leave empty for all"}}),
                 lambda place="": pl.space_report(place), "📊")]


def place_tools(pl: Places) -> list:
    from .tools import Tool, _obj
    s = {"type": "string"}
    arr = {"type": "array", "items": s}
    places = list(pl.folders())
    if not places:
        return []
    place = {"type": "string", "enum": places}
    names = ", ".join(places)
    card = "The user confirms it on a card, so don't ask for permission in text first."
    return [
        Tool("pc_folders", f"The user's own folders on this computer ({names}) and where they are. Use these tools when "
             "the user talks about their Downloads, Desktop, Documents, Pictures, Videos or Music.",
             _obj({}), lambda: pl.places(), "🗂"),
        Tool("pc_overview", "Summary of one of the user's folders: how many files of each kind (documents, images, "
             "installers…), sizes, the biggest and newest files, old files, subfolders. For 'what is in my downloads' "
             "or before a cleanup; to sort, call pc_sort directly.",
             _obj({"place": place, "path": s}, ["place"]), lambda place, path="": pl.overview(place, path), "🗂"),
        Tool("pc_list", "List files in one of the user's folders. sort: name | size | date. kind filters by type "
             "(Documents, Images, Videos, Music, Archives, Installers, Code, Torrents, Fonts, Other).",
             _obj({"place": place, "path": s, "sort": {"type": "string", "enum": ["name", "size", "date"]}, "kind": s},
                  ["place"]),
             lambda place, path="", sort="name", kind="": pl.list(place, path, sort, kind), "📁"),
        Tool("pc_find", "Find files by name in the user's folders (all of them, or one place).",
             _obj({"text": s, "place": place}, ["text"]), lambda text, place="": pl.find(text, place), "🔍"),
        Tool("pc_read", "Read a text, PDF or Word file from the user's folders. Long files come in parts (start).",
             _obj({"place": place, "path": s, "start": {"type": "integer"}}, ["place", "path"]),
             lambda place, path, start=0: pl.read(place, path, start), "📖"),
        Tool("pc_duplicates", "Find identical files (same content) in one of the user's folders and how much space the "
             "extra copies take.",
             _obj({"place": place, "path": s}, ["place"]), lambda place, path="": pl.duplicates(place, path), "🧮"),
        Tool("pc_sort", "Sort / tidy up the loose files of one of the user's folders into subfolders — call it directly "
             "when the user asks to sort or tidy a folder. by: type (Documents, "
             "Images, Installers…), date (one folder per month) or type_date. older_than_days: only older files. "
             "Files still downloading are left alone. " + card + " It can be undone.",
             _obj({"place": place, "path": s, "by": {"type": "string", "enum": ["type", "date", "type_date"]},
                   "older_than_days": {"type": "integer"}}, ["place"]),
             lambda place, path="", by="type", older_than_days=0: pl.propose_sort(place, path, by, older_than_days), "🗂"),
        Tool("pc_move", "Move files or folders (paths inside `place`) into folder `to` (inside `to_place`, default "
             "the same place; created if missing). " + card,
             _obj({"place": place, "paths": arr, "to": s, "to_place": place}, ["place", "paths", "to"]),
             lambda place, paths, to, to_place="": pl.propose_move(place, list(paths or []), to, to_place), "📦"),
        Tool("pc_rename", "Rename a file or folder in the user's folders. " + card,
             _obj({"place": place, "path": s, "new_name": s}, ["place", "path", "new_name"]),
             lambda place, path, new_name: pl.propose_rename(place, path, new_name), "✏️"),
        Tool("pc_make_folder", "Create a folder in the user's folders. " + card,
             _obj({"place": place, "path": s}, ["place", "path"]), lambda place, path: pl.propose_mkdir(place, path), "📁"),
        Tool("pc_trash", "Move files or folders to the Recycle Bin / Trash (they can be restored from there; nothing "
             "is deleted for good). Use for duplicates, old installers etc. the user wants gone. Give a short reason. "
             + card,
             _obj({"place": place, "paths": arr, "reason": s}, ["place", "paths"]),
             lambda place, paths, reason="": pl.propose_trash(place, list(paths or []), reason), "🗑"),
        Tool("pc_show", "Open one of the user's folders (or show a file in it) in the file manager.",
             _obj({"place": place, "path": s}, ["place"]), lambda place, path="": pl.show(place, path), "🗂"),
    ]
