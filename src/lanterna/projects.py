"""Lanterna's own folder for the things it makes: Documents/Lanterna projects/<project>/…

A game, a little program, a game mod, a website: the model writes its files here at once, without a card for each
one (the user chose that: this folder is Lanterna's, and nothing outside it is touched or replaced). Lanterna only
writes the files and checks them for mistakes (project_check reads them, it never runs them); starting a program it
made is the user's choice. Files that Windows or Linux could run by a double click aren't written at all.
Godot 4 games are checked by godot.py; a new game or site can start from files that already work (starters.py,
project_start); and project_check also notes what isn't a mistake but matters (notes_for).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from .workspace import NEVER_WRITE, NOT_TEXT, READ_LIMIT, WRITE_LIMIT, WorkError

FOLDER = "Lanterna projects"
MAX_FILES = 300                     # files in one project
MAX_DEPTH = 8                       # folders inside a project
# besides what's never written anywhere: launchers and programs of Linux and macOS
NEVER = NEVER_WRITE | {".desktop", ".sh", ".bash", ".zsh", ".command", ".appimage", ".run", ".deb", ".rpm", ".so",
                       ".dylib", ".bin", ".elf", ".apk", ".app", ".service", ".msc", ".inf", ".chm", ".application",
                       ".appref-ms", ".gadget", ".scf", ".xll", ".settingcontent-ms", ".diagcab", ".library-ms",
                       ".wsc", ".sct", ".psc1", ".ps1xml", ".ps2", ".msh", ".mshxml", ".ins", ".isp", ".job"}
OPENABLE = {".html", ".htm", ".md", ".txt", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".csv"}
_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.I)


def default_root() -> Path:
    """Documents/Lanterna projects (the Documents folder the system names, so a OneDrive Documents works too).
    LANTERNA_PROJECTS puts it elsewhere (the tests use that)."""
    if os.environ.get("LANTERNA_PROJECTS"):
        return Path(os.environ["LANTERNA_PROJECTS"])
    from .pcfiles import known_folders
    docs = known_folders().get("documents") or Path.home() / "Documents"
    return docs / FOLDER


def clean_name(name: str) -> str:
    """A project's folder name from what the model gave: no slashes or other signs Windows forbids."""
    n = " ".join(_BAD_NAME.sub(" ", str(name or "")).split()).strip(" .")[:60].strip(" .")
    if not n or _RESERVED.match(n):
        raise WorkError("Give the project a short name, e.g. 'Snake game' or 'Minecraft datapack'.")
    return n


def _size(n: int) -> str:
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


class Projects:
    def __init__(self, root: Callable[[], Path] = default_root, opener: Callable[[Path], None] | None = None):
        self._root, self._opener = root, opener

    def root(self) -> Path:
        return Path(self._root())

    def folder(self, project: str, make: bool = False) -> Path:
        p = self.root() / clean_name(project)
        if make:
            p.mkdir(parents=True, exist_ok=True)
        return p

    def path(self, project: str, rel: str, make: bool = False) -> Path:
        """A file inside the project, or WorkError (nothing outside the project folder is ever used)."""
        base = self.folder(project, make)
        rel = str(rel or "").strip().replace("\\", "/").lstrip("/")
        parts = [x for x in rel.split("/") if x not in ("", ".")]
        if not parts:
            raise WorkError("Give a file name inside the project, e.g. 'index.html'.")
        if ".." in parts or re.match(r"^[a-z]:", rel, re.I) or any(_BAD_NAME.search(x) or _RESERVED.match(x)
                                                                   for x in parts):
            raise WorkError(f"'{rel}' isn't a file name inside the project.")
        if len(parts) > MAX_DEPTH + 1:
            raise WorkError("Too many folders inside each other.")
        p = base.joinpath(*parts)
        try:
            if not p.resolve().is_relative_to(base.resolve()):
                raise WorkError(f"'{rel}' is outside the project folder.")
        except OSError as e:
            raise WorkError(f"'{rel}' can't be used: {e}") from None
        return p

    def rel(self, project: str, p: Path) -> str:
        return p.relative_to(self.folder(project)).as_posix()

    def _files(self, project: str) -> list[Path]:
        base = self.folder(project)
        if not base.is_dir():
            return []
        out = []
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules"))
            out += [Path(dirpath) / f for f in sorted(files)]
            if len(out) > MAX_FILES * 2:
                break
        return out

    # ------------------------------------------------------------------ writing (at once: the folder is Lanterna's)
    def write(self, project: str, path: str, text: str, mode: str = "replace") -> str:
        p = self.path(project, path, make=True)
        rel = self.rel(project, p)
        ext = p.suffix.lower()
        if p.name.lower().endswith(".js") or ext in NEVER:
            hint = (" For a web game or page put the script inside the HTML file, in <script>…</script>. If the "
                    "project really needs a separate .js file (a game's script API), write it as "
                    f"'{p.name}.txt' and tell the user to remove '.txt' from its name.") if ext == ".js" else (
                " Write the program in Python (.py) or as a web page (.html) instead.")
            raise WorkError(f"Lanterna doesn't write {ext} files: they could run a program on a double click.{hint}")
        if ext in NOT_TEXT:
            raise WorkError(f"'{p.name}': Lanterna writes only text files here (code, HTML, JSON, Markdown…), "
                            f"not {ext} files. Draw pictures in code (canvas, CSS, inline SVG) or use emoji.")
        if p.is_dir():
            raise WorkError(f"'{rel}' is a folder.")
        text = str(text if text is not None else "")
        if re.match(r"\s*\[saved: \d+ characters", text):     # chat.SHRUNK: the note about an earlier file
            raise WorkError("That is Lanterna's note about a file written earlier, not a file's text. Nothing was "
                            "written: send the real, complete text of the file.")
        mode = "append" if str(mode).lower() == "append" else "replace"
        old = p.stat().st_size if p.is_file() else -1
        if mode == "append" and old >= 0:
            if old + len(text.encode("utf-8")) > WRITE_LIMIT * 4:
                raise WorkError("The file would be too long; split it into a few files.")
        elif len(text) > WRITE_LIMIT:
            raise WorkError("That is too long for one file; split it into a few files.")
        if old < 0 and len(self._files(project)) >= MAX_FILES:
            raise WorkError(f"The project already has {MAX_FILES} files.")
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append" and old > 0:
            with open(p, "a", encoding="utf-8", newline="") as f:
                f.write(text)
        else:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        body = p.read_text(encoding="utf-8", errors="replace")
        what = ("Added to" if mode == "append" and old > 0 else "Rewrote" if old >= 0 else "Wrote")
        out = (f"{what} {clean_name(project)}/{rel} ({_size(p.stat().st_size)}, {body.count(chr(10)) + 1} lines) in "
               f"{self.folder(project)}.")
        problems = check_text(p.name, body)                # a quick look (a cut-off answer shows at once)
        if problems:
            out += (" A quick look found: " + "; ".join(problems[:3]) + ". (If you are going to add the rest with "
                    "mode 'append', that is expected; otherwise fix it.)")
        return out + " When all the files are written, look them over with project_check."

    def edit(self, project: str, path: str, find: str, replace: str) -> str:
        """One exact piece of a file changed (a fix doesn't need the whole file written again)."""
        p = self.path(project, path)
        if not p.is_file():
            raise WorkError(f"There is no '{path}' in the project '{clean_name(project)}'.")
        body = p.read_text(encoding="utf-8", errors="replace")
        find = str(find or "")
        if not find:
            raise WorkError("Say which exact text to change (find).")
        n = body.count(find)
        if n == 0:
            near = body.find(find.strip().splitlines()[0].strip()) if find.strip() else -1
            tip = " (its first line is there: copy the text exactly, with the same spaces)" if near >= 0 else ""
            raise WorkError(f"That text isn't in {path}{tip}. Read the file with project_read and copy the part "
                            "exactly, or write the whole file again.")
        if n > 1:
            raise WorkError(f"That text is in {path} {n} times: give a longer piece, so it is there only once.")
        new = body.replace(find, str(replace if replace is not None else ""), 1)
        if len(new) > WRITE_LIMIT * 4:
            raise WorkError("The file would be too long.")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        line = body[:body.find(find)].count("\n") + 1
        return f"Changed {clean_name(project)}/{self.rel(project, p)} at line {line}."

    # ------------------------------------------------------------------ a starter: files that already work
    def start(self, project: str, kind: str, language: str = "") -> str:
        """A new project from a starter (starters.py), written through write(): only into an empty project."""
        from . import starters
        kind = str(kind or "").strip().lower()
        if kind not in starters.KITS:
            raise WorkError(f"There is no starter '{kind}'. Starters: {', '.join(starters.KITS)}. For anything else "
                            "write the files with project_write.")
        name = clean_name(project)
        if self._files(project):
            raise WorkError(f"'{name}' already has files: a starter goes only into a new project. Build on what is "
                            "there (project_list, project_read), or start under a new project name.")
        made = starters.files(kind, name, language)
        for path, text in made.items():
            self.write(project, path, text)
        folder = self.folder(project)
        rows = "\n".join(f"• {p}" for p in made)
        return (f"Started '{name}' in {folder} with {len(made)} file(s) that already work:\n{rows}\n"
                f"It is {starters.KITS[kind].replace('{folder}', str(folder))}")

    # ------------------------------------------------------------------ reading
    def list(self, project: str = "") -> str:
        root = self.root()
        if not str(project or "").strip():
            if not root.is_dir():
                return f"There are no projects yet. They are kept in {root}."
            rows = []
            for d in sorted((x for x in root.iterdir() if x.is_dir() and not x.name.startswith(".")),
                            key=lambda x: -x.stat().st_mtime)[:60]:
                try:
                    files = self._files(d.name)
                except WorkError:                          # a folder the user named in a way projects can't be
                    continue
                when = dt.datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                rows.append(f"📁 {d.name} ({len(files)} files, changed {when})")
            return f"Projects in {root}:\n" + ("\n".join(rows) or "(none yet)")
        base = self.folder(project)
        if not base.is_dir():
            return f"There is no project '{clean_name(project)}' yet (it is made by the first project_write)."
        files = self._files(project)
        rows = [f"📄 {self.rel(project, f)} ({_size(f.stat().st_size)})" for f in files[:200]]
        more = f"\n… and {len(files) - 200} more" if len(files) > 200 else ""
        return f"Project '{base.name}' in {base} ({len(files)} files):\n" + ("\n".join(rows) or "(empty)") + more

    def read(self, project: str, path: str, start: int = 0, size: int = READ_LIMIT) -> str:
        """Up to `size` characters from `start` (the chat passes what fits the model's tool result)."""
        p = self.path(project, path)
        if not p.is_file():
            raise WorkError(f"There is no '{path}' in the project '{clean_name(project)}'.")
        if p.suffix.lower() in NOT_TEXT:
            return f"'{self.rel(project, p)}' isn't a text file."
        body = p.read_bytes()[:WRITE_LIMIT * 4].decode("utf-8", "replace")
        start, size = max(0, int(start or 0)), max(500, min(READ_LIMIT, int(size) - 300))
        part = body[start:start + size]
        more = (f"\n[… {len(body) - start - size} more characters: call project_read again with start="
                f"{start + size}]") if len(body) > start + size else ""
        return f"File '{self.rel(project, p)}' (characters {start}-{start + len(part)} of {len(body)}):\n{part}{more}"

    def check(self, project: str, path: str = "") -> str:
        """Looks the files over for mistakes in how they are written. Nothing is run."""
        base = self.folder(project)
        if not base.is_dir():
            raise WorkError(f"There is no project '{clean_name(project)}' yet.")
        files = [self.path(project, path)] if str(path or "").strip() else self._files(project)
        if not files or not files[0].is_file():
            raise WorkError(f"There is no '{path}' in the project." if path else "The project has no files yet.")
        rows, bad, notes = [], 0, []
        for f in files[:MAX_FILES]:
            rel = self.rel(project, f)
            try:
                body = f.read_bytes()[:WRITE_LIMIT * 4].decode("utf-8")
            except UnicodeDecodeError:
                rows.append(f"• {rel}: not UTF-8 text")
                bad += 1
                continue
            except OSError as e:
                rows.append(f"• {rel}: can't be read ({e})")
                bad += 1
                continue
            problems = check_text(f.name, body, base, f.parent)
            if problems:
                bad += 1
                rows.append(f"• {rel}: " + "; ".join(problems[:4]))
            elif f.suffix.lower() in CHECKED or f.name.lower().endswith(".js.txt"):
                rows.append(f"• {rel}: OK")
            notes += [f"• {rel}: {n}" for n in notes_for(f.name, body, base, f.parent)[:3]]
        head = (f"Checked {len(files)} file(s) of '{base.name}': " +
                (f"{bad} with mistakes." if bad else "no mistakes found."))
        tail = ("\nFix them (project_edit for a small change, project_write for a whole file), then check again."
                if bad else "\nThis checks how the files are written, not whether the program works: nothing was run.")
        if notes:
            tail = ("\nNot mistakes, but worth a look (fix those that matter for what the user wants):\n"
                    + "\n".join(notes[:20]) + tail)
        return head + "\n" + "\n".join(rows[:60]) + tail

    # ------------------------------------------------------------------ opening (when the user asks)
    def open(self, project: str, path: str = "") -> str:
        if not str(path or "").strip():
            p = self.folder(project)
            if not p.is_dir():
                raise WorkError(f"There is no project '{clean_name(project)}' yet.")
        else:
            p = self.path(project, path)
            if not p.is_file():
                raise WorkError(f"There is no '{path}' in the project.")
            if p.suffix.lower() not in OPENABLE:
                raise WorkError(f"Lanterna opens web pages, pictures and text files, not {p.suffix or 'program'} files: "
                                "starting a program is for the user. Open the folder instead (no path) and tell the "
                                "user how to start it.")
        (self._opener or _open)(p)
        return f"Opened {p} for the user."


def _open(p: Path) -> None:
    if p.is_dir():
        from .pcfiles import _open_in_file_manager
        _open_in_file_manager(p)
        return
    if sys.platform == "win32":
        os.startfile(str(p))                       # noqa: S606  (a web page or text file of the project)
        return
    import shutil

    from . import quiet
    opener = shutil.which("xdg-open")
    if not (opener and quiet.spawn([opener, str(p)])) and not quiet.open_url(p.as_uri()):
        raise WorkError("No program opened it.")


# ---------------------------------------------------------------------------------------------------- checks
STYLES = {".js": "js", ".mjs": "js", ".ts": "js", ".jsx": "js", ".tsx": "js", ".css": "css", ".scss": "c", ".less": "c",
          ".java": "c", ".cs": "c", ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c", ".cc": "c", ".kt": "c", ".kts": "c",
          ".go": "c", ".swift": "c", ".dart": "c", ".glsl": "c", ".hlsl": "c", ".shader": "c", ".php": "c",
          ".gd": "hash", ".rb": "hash", ".lua": "lua", ".luau": "lua", ".gdshader": "c", ".gdshaderinc": "c"}
CHECKED = {".py", ".pyw", ".json", ".mcmeta", ".xml", ".svg", ".html", ".htm", ".godot", ".tscn", ".tres", *STYLES}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_OPTIONAL_END = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot", "option", "optgroup", "colgroup",
                 "caption", "rb", "rt", "rp", "html", "head", "body"}
_JS_BEFORE_REGEX = set("(,=:[!&|?{};+-*%<>~^")
_JS_WORDS_BEFORE_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw",
                          "yield", "await", "instanceof"}


def check_text(name: str, body: str, folder: Path | None = None, here: Path | None = None) -> list[str]:
    """The mistakes found in one file's text (short sentences with line numbers); [] = none found."""
    low = name.lower()
    ext = Path(low).suffix
    if low.endswith(".js.txt"):
        ext = ".js"
    try:
        if ext in (".py", ".pyw"):
            return _python(body, name)
        if ext in (".json", ".mcmeta"):
            return _json(body)
        if ext in (".xml", ".svg"):
            return _xml(body)
        if ext in (".html", ".htm"):
            return _html(body, folder, here)
        if ext in (".gd", ".godot", ".tscn", ".tres"):             # Godot 4 (godot.py): its words, ids and paths
            return _godot(ext, body, folder, here)
        if ext in STYLES:
            problem = brackets(body, STYLES[ext])
            return [problem] if problem else []
    except RecursionError:
        return ["it is nested too deeply to check"]
    return []


def _godot(ext: str, body: str, folder: Path | None, here: Path | None) -> list[str]:
    from . import godot
    if ext == ".gd":
        problem = brackets(body, "hash")
        return ([problem] if problem else []) + godot.gdscript(body, folder, here)
    if ext == ".godot":
        return godot.project_file(body, folder, here)
    return godot.scene(body, "gd_scene" if ext == ".tscn" else "gd_resource", folder, here)


def _quote(body: str, line: int) -> str:
    lines = body.splitlines()
    if 1 <= line <= len(lines):
        s = lines[line - 1].strip()
        return f" ({s[:80]}{'…' if len(s) > 80 else ''})" if s else ""
    return ""


def _python(body: str, name: str) -> list[str]:
    import warnings
    try:
        with warnings.catch_warnings():                    # a warning printed now would land on the terminal app
            warnings.simplefilter("ignore")
            compile(body, name, "exec", dont_inherit=True) # only turned into bytecode: nothing runs
    except SyntaxError as e:
        line = e.lineno or 0
        return [f"line {line}: {e.msg}{_quote(body, line)}"]
    except (ValueError, MemoryError) as e:
        return [str(e)[:120]]
    return []


def _json(body: str) -> list[str]:
    try:
        json.loads(body)
    except json.JSONDecodeError as e:
        return [f"line {e.lineno}: {e.msg}{_quote(body, e.lineno)}"]
    return []


def _xml(body: str) -> list[str]:
    try:
        ElementTree.fromstring(body.encode("utf-8"))
    except ElementTree.ParseError as e:
        line = e.position[0] if e.position else 0
        return [f"line {line}: {str(e).split(':')[0]}{_quote(body, line)}"]
    return []


class _HtmlCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.problems: list[str] = []
        self.parts: list[tuple[str, int, dict, list[str]]] = []      # (script|style, line, attributes, text)
        self.refs: list[tuple[str, int]] = []
        self._in: tuple[str, int, dict, list[str]] | None = None

    def _refs(self, tag, a: dict) -> None:
        for key in ("src", "href"):
            if a.get(key) and (tag in ("script", "img", "audio", "video", "source", "iframe")
                               or tag == "link" and "stylesheet" in a.get("rel", "").lower()):
                self.refs.append((a[key], self.getpos()[0]))

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self._refs(tag, a)
        if tag in _VOID:
            return
        line = self.getpos()[0]
        if tag in ("script", "style"):
            self._in = (tag, line, a, [])
        self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self._refs(tag, {k: (v or "") for k, v in attrs})   # <br/>, <path … />: nothing stays open

    def handle_data(self, data):
        if self._in:
            self._in[3].append(data)

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag in _VOID:
            return
        if self._in and tag == self._in[0]:
            self.parts.append(self._in)
            self._in = None
        if not any(t == tag for t, _ in self.stack):
            if tag not in _OPTIONAL_END:
                self.problems.append(f"line {line}: </{tag}> closes nothing")
            return
        while self.stack:
            t, ln = self.stack.pop()
            if t == tag:
                break
            if t not in _OPTIONAL_END:
                self.problems.append(f"line {ln}: <{t}> isn't closed before </{tag}> on line {line}")


def _html(body: str, folder: Path | None, here: Path | None) -> list[str]:
    h = _HtmlCheck()
    h.feed(body)
    h.close()
    out = list(h.problems)
    if h._in:
        out.append(f"line {h._in[1]}: this <{h._in[0]}> is never closed: the file looks cut off")
    for t, ln in h.stack:
        if t not in _OPTIONAL_END and not (h._in and ln == h._in[1]):
            out.append(f"line {ln}: <{t}> is never closed")
    low = body.lower()
    if "<html" in low and "</html>" not in low and not h._in:
        out.append("there is no </html> at the end: the file may be cut off")
    for kind, line, attrs, text in h.parts:
        code = "".join(text)
        typ = attrs.get("type", "").lower()
        problem = ""
        if kind == "style":
            problem = brackets(code, "css")
        elif typ in ("", "text/javascript", "module", "application/javascript"):
            problem = brackets(code, "js")
        elif "json" in typ or typ == "importmap":
            problem = "; ".join(_json(code))
        if problem:
            m = re.match(r"line (\d+): (.*)", problem, re.S)
            out.append(f"line {line + int(m.group(1)) - 1}: {m.group(2)}" if m else f"<{kind}> on line {line}: {problem}")
    if folder is not None and here is not None:
        for ref, line in h.refs:
            r = ref.split("#")[0].split("?")[0]
            if not r or re.match(r"^[a-z][a-z0-9+.-]*:|^//", r, re.I):
                continue                                   # a web address, data: or another page's part
            target = (folder / r.lstrip("/")) if r.startswith("/") else (here / r)
            if not target.exists():
                out.append(f"line {line}: '{r}' isn't in the project (write it, or put its code inside this file)")
    return out


def brackets(text: str, style: str) -> str:
    """The first unclosed or stray bracket, string or comment ("" = none), with its line. style: js, css, c (also //
    and /* */ comments), hash (# comments) or lua (-- comments, [[long strings]]). Strings and comments are skipped,
    so a bracket inside them doesn't count."""
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    i, n, line = 0, len(text), 1
    prev = ""                                              # the last code character (or word), for JS regex literals
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        two = text[i:i + 2]
        if style in ("js", "css", "c") and two == "/*":
            j = text.find("*/", i + 2)
            if j < 0:
                return f"line {line}: a /* comment is never closed"
            line += text.count("\n", i, j)
            i = j + 2
            continue
        if (style in ("js", "c") and two == "//") or (style == "hash" and c == "#"):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if style == "lua" and two == "--":
            m = re.match(r"--\[(=*)\[", text[i:i + 40])
            if m:
                end = "]" + m.group(1) + "]"
                j = text.find(end, i)
                if j < 0:
                    return f"line {line}: a --[[ comment is never closed"
                line += text.count("\n", i, j)
                i = j + len(end)
            else:
                j = text.find("\n", i)
                i = n if j < 0 else j
            continue
        if style == "lua" and c == "[":
            m = re.match(r"\[(=*)\[", text[i:i + 40])
            if m:
                end = "]" + m.group(1) + "]"
                j = text.find(end, i + 2)
                if j < 0:
                    return f"line {line}: a [[ text is never closed"
                line += text.count("\n", i, j)
                i = j + len(end)
                prev = "a"
                continue
        if c == "`" and style == "js":
            j, line, err = _template(text, i + 1, line)
            if err:
                return err
            if j < 0:                                      # a ${ … } inside: its code is checked like the rest
                stack.append(("${", line))
                i = -j
                prev = "{"
                continue
            i, prev = j, "a"
            continue
        if c in "\"'":
            if style in ("c", "hash") and text.startswith(('"""', "'''"), i):   # Java / Kotlin / GDScript blocks
                q = text[i:i + 3]
                j = text.find(q, i + 3)
                if j < 0:
                    return f"line {line}: a {q} text is never closed"
                line += text.count("\n", i, j)
                i, prev = j + 3, "a"
                continue
            if style == "c":
                if c == "'":                               # a char ('x', '\n'), or a Rust lifetime / apostrophe
                    m = re.match(r"'(\\.[^'\n]{0,8}|[^'\\\n])'", text[i:i + 12])
                    if not m:
                        i += 1
                        continue
                    i, prev = i + m.end(), "a"
                    continue
                if text[i - 1:i] == "@":                   # C# verbatim string: "" is a quote, \ is a letter
                    j = i + 1
                    while True:
                        j = text.find('"', j)
                        if j < 0:
                            return f"line {line}: a @\"…\" text is never closed"
                        if text[j + 1:j + 2] == '"':
                            j += 2
                            continue
                        break
                    line += text.count("\n", i, j)
                    i, prev = j + 1, "a"
                    continue
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                elif text[j] == "\n" and style != "lua":
                    if style == "hash" or style == "css":
                        break
                    return f"line {line}: a text in {c} quotes isn't closed on its line{_quote(text, line)}"
                elif text[j] == "\n":
                    break
                j += 1
            if j >= n:
                return f"line {line}: a text in {c} quotes is never closed{_quote(text, line)}"
            line += text.count("\n", i, j)                 # a \ at a line's end goes on to the next line
            if text[j] == "\n":
                i = j
                continue
            i, prev = j + 1, "a"
            continue
        if c == "/" and style == "js" and (prev == "" or prev in _JS_BEFORE_REGEX or prev in _JS_WORDS_BEFORE_REGEX):
            j = _regex_end(text, i)
            if j > 0:
                i, prev = j, "a"
                continue
        if c in "([{":
            stack.append((c, line))
        elif c in ")]}":
            if stack and stack[-1][0] == "${" and c == "}":
                stack.pop()
                j, line, err = _template(text, i + 1, line)
                if err:
                    return err
                if j < 0:
                    stack.append(("${", line))
                    i = -j
                    prev = "{"
                    continue
                i, prev = j, "a"
                continue
            if not stack:
                return f"line {line}: '{c}' closes nothing{_quote(text, line)}"
            top, at = stack[-1]
            if top != pairs[c]:
                want = {"(": ")", "[": "]", "{": "}", "${": "}"}[top]
                return (f"line {line}: '{c}' where '{want}' was expected (for the '{top}' on line {at})"
                        f"{_quote(text, line)}")
            stack.pop()
        if c.isalnum() or c in "_$":
            m = re.match(r"[\w$]+", text[i:i + 40])
            word = m.group(0) if m else c
            prev = word if word in _JS_WORDS_BEFORE_REGEX else "a"
            i += len(word)
            continue
        prev = c
        i += 1
    if stack:
        top, at = stack[-1]
        close = {"(": ")", "[": "]"}.get(top, "}")
        return f"line {at}: '{top}' is never closed (a missing '{close}', or the file is cut off){_quote(text, at)}"
    return ""


def _template(text: str, i: int, line: int) -> tuple[int, int, str]:
    """A JS `template` from i (after ` or after the } of a ${ }): (the index after its closing `, line, "") or
    (-(the index after a ${), line, "") or (0, line, the problem)."""
    start_line = line
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            line += 1
        elif c == "`":
            return i + 1, line, ""
        elif c == "$" and text[i + 1:i + 2] == "{":
            return -(i + 2), line, ""
        i += 1
    return 0, line, f"line {start_line}: a text in ` quotes is never closed"


def _regex_end(text: str, i: int) -> int:
    """The end of a JS /regex/flags starting at i, or 0 when it isn't one (then / is division)."""
    j, n, cls = i + 1, len(text), False
    if text[j:j + 1] in ("/", "*", ""):
        return 0
    while j < n:
        c = text[j]
        if c == "\n":
            return 0
        if c == "\\":
            j += 2
            continue
        if c == "[":
            cls = True
        elif c == "]":
            cls = False
        elif c == "/" and not cls:
            j += 1
            while j < n and text[j].isalpha():
                j += 1
            return j
        j += 1
    return 0


# ---------------------------------------------------------------------------------------------------- notes
# Not mistakes, but what a person notices: a page tiny on a phone, text hard to read, a program that needs something
# Python doesn't have. project_check shows them after its findings; the model fixes what matters for the user's wish.
_PIP = {"PIL": "pillow", "cv2": "opencv-python", "yaml": "pyyaml", "bs4": "beautifulsoup4", "sklearn": "scikit-learn",
        "skimage": "scikit-image", "dateutil": "python-dateutil", "serial": "pyserial", "dotenv": "python-dotenv",
        "Crypto": "pycryptodome", "docx": "python-docx", "pptx": "python-pptx", "fitz": "pymupdf",
        "OpenGL": "PyOpenGL", "usb": "pyusb", "gi": "PyGObject", "jwt": "PyJWT", "win32api": "pywin32",
        "win32con": "pywin32", "win32gui": "pywin32", "win32com": "pywin32", "pythoncom": "pywin32",
        "telegram": "python-telegram-bot", "discord": "discord.py", "attr": "attrs", "magic": "python-magic"}


def notes_for(name: str, body: str, folder: Path | None = None, here: Path | None = None) -> list[str]:
    """What project_check notes besides mistakes (short sentences, [] = nothing)."""
    ext = Path(name.lower()).suffix
    try:
        if ext in (".html", ".htm"):
            return _page_notes(body)
        if ext == ".css":
            return _style_notes(body)
        if ext in (".py", ".pyw") and folder is not None and here is not None:
            return _python_notes(body, folder, here)
    except (RecursionError, ValueError):
        return []
    return []


def _page_notes(body: str) -> list[str]:
    low = body.lower()
    out = []
    if "<html" in low or "<body" in low or "<!doctype" in low:          # a whole page, not a piece of one
        if not re.search(r"<meta\b[^>]*\bname\s*=\s*[\"']?viewport", low):
            out.append('no <meta name="viewport" content="width=device-width, initial-scale=1">: on a phone the '
                       "page shows tiny")
        if not re.search(r"<html\b[^>]*\blang\s*=", low):
            out.append('no lang on <html> (e.g. <html lang="uk">): screen readers and translators guess the language')
        if not re.search(r"<title>\s*[^<\s]", low):
            out.append("no <title>: the browser tab has no name")
    bare = [x for x in re.findall(r"<img\b[^>]*>", low) if not re.search(r"\balt\s*=", x)]
    if bare:
        out.append(f"{len(bare)} picture(s) without alt text (alt=\"what it shows\", alt=\"\" for decoration)")
    if "lorem ipsum" in low:
        out.append("placeholder text (lorem ipsum) is still there: write the real text")
    h = _HtmlCheck()
    h.feed(body)
    h.close()
    for kind, line, _attrs, text in h.parts:
        if kind == "style":
            out += _style_notes("".join(text), line)
    return out


def _rgb(value: str) -> tuple[int, int, int] | None:
    v = value.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1) if len(m.group(1)) == 6 else "".join(c * 2 for c in m.group(1))
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(?:1|1\.0+)\s*)?\)", v)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return {"white": (255, 255, 255), "black": (0, 0, 0)}.get(v)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """WCAG contrast of two colors: 1 (the same) to 21 (black on white); text needs 4.5 at least."""
    def lum(rgb):
        ch = [(c / 255) / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _rules(css: str) -> list[tuple[str, str, int]]:
    """The rules outside @media and other @ blocks: (selector, body, the index where the selector starts)."""
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        sel = css[i:j].split(";")[-1]
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        if sel.strip() and not sel.strip().startswith("@"):
            out.append((sel.strip(), css[j + 1:k - 1], j - len(sel) + (len(sel) - len(sel.lstrip()))))
        i = k
    return out


def _style_notes(css: str, first: int = 1) -> list[str]:
    import bisect
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S)
    breaks = [m.start() for m in re.finditer("\n", text)]

    def line(at: int) -> int:
        return first + bisect.bisect_left(breaks, at)
    out = []
    rules = _rules(text)
    names = {}
    for _sel, body, _at in rules:
        for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            names[k] = v.strip()

    def color(v: str):
        for _ in range(4):
            m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)", v.strip())
            if not m:
                break
            v = names.get(m.group(1), m.group(2) or "")
        return _rgb(v) if v else None
    hard = 0
    for sel, body, at in rules:
        decl = {k.lower(): v.strip() for k, v in re.findall(r"(?<![\w-])([a-zA-Z-]+)\s*:\s*([^;]+)", body)}
        fg, bg = decl.get("color"), decl.get("background-color") or decl.get("background")
        a, b = (color(fg), color(bg)) if fg and bg else (None, None)
        if a and b and contrast(a, b) < 4.5:
            out.append(f"line {line(at)}: the text on its background is hard to read in {sel[:40]} (contrast "
                       f"{contrast(a, b):.1f}:1, text needs 4.5:1)")
            hard += 1
            if hard >= 2:
                break
    for m in re.finditer(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", text):
        if float(m.group(1)) < 12:
            out.append(f"line {line(m.start())}: text of {m.group(1)}px is hard to read (12px at least, 16px for "
                       "body text)")
            break
    if "@media" not in text and "max-width" not in text:
        for m in re.finditer(r"(?<![\w-])width\s*:\s*(\d{3,4})px", text):
            if int(m.group(1)) >= 700:
                out.append(f"line {line(m.start())}: a fixed width of {m.group(1)}px doesn't fit a phone (use "
                           f"max-width: {m.group(1)}px with width: 100%)")
                break
    return out


def _python_notes(body: str, folder: Path, here: Path) -> list[str]:
    import ast
    try:
        tree = ast.parse(body)                              # only read: nothing runs
    except SyntaxError:
        return []
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            mods.add(node.module.split(".")[0])

    def own(m: str) -> bool:
        return any((d / f"{m}.py").is_file() or (d / m).is_dir() for d in {here, folder})
    outside = sorted(m for m in mods if m not in sys.stdlib_module_names and not own(m))
    if not outside:
        return []
    listed = set()
    for d in {here, folder}:
        req = d / "requirements.txt"
        if req.is_file():
            for row in req.read_text(encoding="utf-8", errors="replace").splitlines():
                row = row.split("#")[0].strip()
                if row and not row.startswith("-"):
                    listed.add(re.split(r"[<>=!~;\[\s@]", row, 1)[0].lower().replace("_", "-"))
    need = [p for p in dict.fromkeys(_PIP.get(m, m) for m in outside) if p.lower().replace("_", "-") not in listed]
    if not need:
        return []
    return [f"it needs {', '.join(need)}, which isn't part of Python: put {'it' if len(need) == 1 else 'them'} in "
            f"requirements.txt and tell the user to run: pip install {' '.join(need)}"]


# ---------------------------------------------------------------------------------------------------- tools
def project_tools(pr: Projects, limit: Callable[[], int] = lambda: READ_LIMIT,
                  after: Callable[[str], str] = lambda out: out, lang: Callable[[], str] = lambda: "") -> list:
    """limit: characters of a tool result for the current model; after: adds the plan's next step to an answer;
    lang: the app's language (a starter's words when the model names none)."""
    from . import starters
    from .tools import Tool, _obj
    s = {"type": "string"}
    proj = {"type": "string", "description": "the project's short name (its folder in Lanterna projects), "
                                             "e.g. 'Snake game'"}
    path = {"type": "string", "description": "the file inside the project, e.g. 'index.html' or 'data/pack.mcmeta'"}
    g = "make"
    return [
        Tool("project_start", "Start a NEW project from Lanterna's starter files, which already work and pass "
             "project_check, then build the user's wish on them: 'godot-2d' or 'godot-3d' (a Godot 4 game: "
             "project.godot, a level, a player scene with its script), 'website' (index.html with style.css: a calm "
             "design with colors, a dark theme, type sizes, spacing, cards, buttons, forms), 'web-game' (a canvas "
             "game in one index.html). Only into a new, empty project; for anything else write the files with "
             "project_write.",
             _obj({"project": proj, "kind": {"type": "string", "enum": list(starters.KITS)},
                   "language": {"type": "string", "description": "the language of the words in the files, e.g. 'uk' "
                                                                  "or 'en' (the user's language)"}}, ["project", "kind"]),
             lambda project, kind, language="": after(pr.start(project, kind, language or lang())), "🧩", g),
        Tool("project_write", "Write a file of a project the user asked you to make (a game, a little program, a mod, a "
             "website) into Lanterna's own folder Documents/Lanterna projects/<project>. It is written at once, no "
             "confirmation; nothing outside that folder is touched. mode 'replace' (default) writes the whole file "
             "(a new one or again); 'append' adds text to its end, so a long file can be written in a few parts. Text "
             "files only; no .exe, .bat, .js and the like: a web game is one .html file with its script and styles "
             "inside. Write complete, working code, never 'the rest goes here'.",
             _obj({"project": proj, "path": path, "text": {"type": "string", "description": "the file's text"},
                   "mode": {"type": "string", "enum": ["replace", "append"]}}, ["project", "path", "text"]),
             lambda project, path, text, mode="replace": after(pr.write(project, path, text, mode)), "💾", g),
        Tool("project_edit", "Change one exact piece of a project file (to fix a mistake without writing the whole "
             "file again): find must be copied exactly from the file and be there only once.",
             _obj({"project": proj, "path": path, "find": s, "replace": s}, ["project", "path", "find", "replace"]),
             lambda project, path, find, replace: after(pr.edit(project, path, find, replace)), "✏️", g),
        Tool("project_read", "Read a file of a project in Lanterna projects (a long file in parts: start = where to "
             "go on).", _obj({"project": proj, "path": path, "start": {"type": "integer"}}, ["project", "path"]),
             lambda project, path, start=0: pr.read(project, path, start, limit()), "📖", g),
        Tool("project_list", "List the projects in Lanterna projects (no project given), or the files of one project.",
             _obj({"project": proj}), lambda project="": pr.list(project), "📁", g),
        Tool("project_check", "Look a project's files over for mistakes without running them: Python syntax, JSON, XML, "
             "HTML tags and the script inside it, brackets and quotes in JavaScript, CSS, Java, C#, Lua and others, "
             "Godot 4 (GDScript, project.godot, scenes: Godot 3 words, tabs and spaces, ids, missing files), and files "
             "the page uses but that are missing. It also lists notes that aren't mistakes (a page tiny on a phone, "
             "text hard to read, a library Python lacks). Call it after writing the files, fix what it finds, and "
             "check again.", _obj({"project": proj, "path": {"type": "string", "description": "one file (optional)"}},
                            ["project"]),
             lambda project, path="": after(pr.check(project, path)), "🧪", g),
        Tool("project_open", "Open a project's folder for the user (no path), or one of its web pages, pictures or text "
             "files (an HTML game opens in the browser). Only when the user asks to see, open or play it. Programs "
             "aren't started: tell the user how to start them.", _obj({"project": proj, "path": path}, ["project"]),
             lambda project, path="": pr.open(project, path), "📂", g),
    ]
