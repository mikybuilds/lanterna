"""Round 147 (1.1.10b9): the window redone in the style of the site, with more visuals (the rules are local).

The look itself is checked in the browser on tools/ui_demo.py. What these tests hold:
- pc_disk's count of the whole disk becomes a figure the window draws above the reply: how full the disk is and
  its biggest folders right on the disk (the rest together). It is kept with the reply on this computer only, so
  an opened chat draws it again; it holds only the names of the folders on the disk, and none of it goes to the
  model or to sync.
- The window's bars stay quiet: every number is printed beside its bar, grey for facts, amber only for a limit
  that runs out, red only for little left (with the number). Cards show their groups and files as rows with an
  icon of the kind, no emoji. The limit under the message box stands right after the buttons, the hint gives way.
- After the design critic: the figure starts with what is used, on the same scale as the rest; the hello calls a
  person as Ukrainian does (the regular endings only, any other name as typed); an answer coming in shows no
  half-written table, ** or `; the marks of the services stand on a plain tile.
"""
import json
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from lanterna import diskmap, diskuse, sources
from lanterna.diskmap import GB
from lanterna.discovery import Candidate
from lanterna.providers import ToolCall, ToolCalls
from lanterna.router import Router
from test_round_144 import _api  # noqa: E402  (an Api of its own)
from test_round_146 import GAMES, R, SIZES, _Walk, _p  # noqa: E402  (the pretend disk)


@pytest.fixture(autouse=True)
def _no_figures(monkeypatch):
    """No figure of another test is waiting, and no real other disk is looked at."""
    diskmap._figures.clear()
    monkeypatch.setattr(diskmap, "other_disks", lambda root, win=False: [])
    yield
    diskmap._figures.clear()


DISK = diskmap.Disk(476 * GB, 456 * GB, 20 * GB)


# ---------------------------------------------------------------- the figure of the disk
def test_a_count_of_the_whole_disk_leaves_its_figure_once():
    diskmap.drive_parts(_Walk(), win=True, disk=DISK, games=GAMES)
    fig = diskmap.take()
    assert fig == {"disk": R, "counted": SIZES[_p()], "whole": True,
                   "parts": [{"name": "Program Files (x86)", "size": SIZES[_p("Program Files (x86)")]},
                             {"name": "Users", "size": SIZES[_p("Users")]},
                             {"name": "Windows", "size": SIZES[_p("Windows")]},
                             {"kind": "files", "size": 7 * GB},             # pagefile.sys and the like
                             {"name": "Program Files", "size": SIZES[_p("Program Files")]}],
                   "total": DISK.total, "used": DISK.used, "free": DISK.free, "low": True,
                   "uncounted": DISK.used - SIZES[_p()]}                    # restore points and closed folders
    assert diskmap.take() is None                                       # taken once
    assert "olena" not in json.dumps(fig)                               # no path below the disk's own folders


def test_the_rest_is_one_part_and_nothing_is_guessed():
    tops = [(n * GB, _p(f"F{n}")) for n in (9, 8, 7, 6, 5, 4, 3)] + [(0, _p("Empty"))]
    fig = diskmap.figure(R, None, tops, 2 * GB, 44 * GB, False)
    assert [p.get("name") for p in fig["parts"]] == ["F9", "F8", "F7", "F6", "F5", None]
    assert fig["parts"][-1] == {"kind": "other", "size": 9 * GB}         # 4 + 3 + the files right on the disk
    assert fig == {"disk": R, "parts": fig["parts"], "counted": 44 * GB, "whole": False}   # no disk: no sizes of it
    half = diskmap.figure(R, DISK, [(5 * GB, _p("A"))], 0, 5 * GB, False)
    assert half["uncounted"] == 0 and half["low"]                       # still counting: nothing is "not counted"


class _Box:
    """A toolbox whose pc_disk keeps a figure like the real one (only for the whole disk)."""

    def __init__(self, fig):
        self.fig, self.focus, self.page_limit = fig, "", 0

    def run(self, name, arguments):
        if name == "pc_disk" and not json.loads(arguments or "{}").get("folder"):
            diskmap.keep(self.fig)
        return "Disk C:\\ — 20.0 GB free of 476.0 GB"


FIG = diskmap.figure(R, DISK, [(80 * GB, _p("Program Files (x86)")), (60 * GB, _p("Users"))], 7 * GB, 300 * GB, True)


def test_the_answer_notes_the_figure_with_its_sources():
    noted = sources.Noted(_Box(FIG))
    assert noted.run("pc_disk", "{}") == "Disk C:\\ — 20.0 GB free of 476.0 GB"   # the model gets the same text
    assert noted.disk == FIG and noted.data() == {"read": [], "found": [], "disk": FIG}
    assert sources.view(sources.dumps(noted.data())) == {}               # «Sources» stay pages only
    diskmap.keep({"disk": "left by a regular task", "parts": []})       # in this thread, outside an answer
    other = sources.Noted(_Box(FIG))
    other.run("pc_disk", json.dumps({"folder": "D:"}))                   # one folder: no figure
    assert other.disk is None and other.data() == {} and diskmap.take() is None


@pytest.mark.parametrize("raw", ["", "{", "[]", '{"disk": 5}', '{"disk": {"parts": "x"}}', '{"read": []}',
                                 '{"disk": {"parts": [{"size": true, "name": "x"}, {"size": 5, "kind": "evil"}]}}'])
def test_a_figure_that_does_not_look_right_is_not_drawn(raw):
    assert sources.disk(raw) == {}


def test_the_kept_figure_is_read_back_as_it_was():
    assert sources.disk(sources.dumps({"disk": FIG})) == FIG
    odd = sources.disk(json.dumps({"disk": {"disk": "C:\\", "total": 10, "used": -1, "free": "x", "whole": 1,
                                            "parts": [{"name": "N" * 300, "size": 4, "kind": "other"},
                                                      {"name": 5, "size": 3}, {"kind": "files", "size": 2.5}]}}))
    assert odd == {"disk": "C:\\", "total": 10, "whole": False, "low": False,
                   "parts": [{"size": 4, "name": "N" * sources.LABEL}, {"size": 2.5, "kind": "files"}]}


# ---------------------------------------------------------------- in a real answer
class _Fake:
    def __init__(self, replies):
        self.replies = replies

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        yield from (self.replies.pop(0) if self.replies else ["Гаразд."])

    def close(self):
        pass


def _until_done(api, sid):
    seen = []
    for _ in range(300):
        p = api.poll(sid)
        seen.append(p)
        if p.get("done"):
            return p, seen
        time.sleep(0.02)
    raise AssertionError("the answer never ended")


@pytest.mark.parametrize("private", [False, True])
def test_an_answer_that_counted_the_disk_draws_it_and_keeps_it(tmp_path, monkeypatch, private):
    api = _api(tmp_path, monkeypatch)
    calls = ToolCalls([ToolCall("c1", "pc_disk", "{}")])
    fake = _Fake([[calls], ["Найбільше займає Program Files (x86)."]])
    router = Router([Candidate("groq", "fake-model", 50)], client_for=lambda pid: fake)
    router.current = router.candidates[0]
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)
    told = []
    monkeypatch.setattr(diskuse, "report", lambda part="", **kw: diskmap.keep(FIG) or told.append(part)
                        or "Disk C:\\ — 20.0 GB free of 476.0 GB")
    tid = api.new_thread(private=private)["id"]
    p, seen = _until_done(api, api.send(tid, "Що займає місце на диску?")["stream"])
    assert p["error"] is None and told == [""] and p["disk"] == FIG
    assert p["sources"] == {}                                           # not a source: pages only
    msgs = api.messages(tid)
    assert msgs[-1]["disk"] == FIG and msgs[0]["disk"] == {} and msgs[-1]["sources"] == {}
    p, _ = _until_done(api, api.send(tid, "Дякую")["stream"])            # no count: no figure
    assert "disk" not in p and api.messages(tid)[-1]["disk"] == {}
    if not private:
        row = sqlite3.connect(api.store.path).execute(
            "SELECT sources FROM messages WHERE role='assistant' ORDER BY id").fetchone()
        assert json.loads(row[0])["disk"] == FIG                        # kept with the reply on this computer
        synced = api.store.export_sync()["messages"].values()
        assert synced and all(set(m) == {"thread", "role", "content", "model", "at"} for m in synced)   # not synced


# ---------------------------------------------------------------- the window
UI = Path(__file__).parents[1] / "src" / "lanterna" / "ui"
NEW_WORDS = ["KB", "MB", "Disk {d}", "{free} free of {total}", "almost full", "Files right on the disk", "Not counted",
             "Still counting: the sizes are at least these.", "{p}% of the disk", "of {total}",
             "full again in {t}", "Files still downloading are left alone ({n}).",
             # after the critic: a calm hello, the start rows, the disk's "Used" row, the steps, the limit's words
             "Hi, {n}.", "Hi.", "Explanations", "Safety", "Explain simply why the sky is blue", "Used", "Steps ({n})",
             "{left} of {limit} left",
             # a count as "(N)" in every language: no "Sort 1 files", "Move 1 items"
             "Sort the files in {place} ({count})", "Sorted the files in {place} ({count})", "Move to {to} ({count})",
             "Moved to {to} ({count})", "Move to the Recycle Bin ({count})", "Moved to the Recycle Bin ({count})"]
COUNTED = ["Sort {count} files in {place}", "Sorted {count} files in {place}", "Move {count} items to {to}",
           "Moved {count} items to {to}", "Move {count} items to the Recycle Bin", "Moved {count} items to the Recycle Bin",
           "Sort {count} emails into folders", "Sorted {count} emails into folders"]
GONE_FROM_THE_WINDOW = ["Hi, {n}!", "Hi!", "{left} of {limit}", "Remind", "Thinking · steps: {n}",
                        "Explain something simply"]   # the last two stay for the terminal look only


def _ui(name):
    return (UI / name).read_text(encoding="utf-8")


def test_the_window_draws_the_figure_live_and_in_an_opened_chat():
    js = _ui("app.js")
    assert "function addBot(text, model, sent, second = false, sources = null, disk = null)" in js
    assert "${diskFig(disk)}" in js                                        # above the words of the reply
    assert 'if (p.disk && !bot.querySelector(".dfig"))' in js              # live: once, as soon as it is counted
    assert "m.sources, m.disk)" in js                                      # an opened chat draws it again


def test_the_new_words_are_in_every_language():
    js, i18n_py = _ui("app.js"), (UI.parent / "i18n.py").read_text(encoding="utf-8")
    table = js[js.index("const STR = {"):js.index("let LANG")]
    for w in NEW_WORDS:
        assert re.search(r'^\s*' + re.escape(json.dumps(w, ensure_ascii=False)) + r'\s*:\s*\{\s*uk: "[^"]+", it: "[^"]+"',
                         table, re.M), w
    for gone in ("reset in {t}", "{n} files still downloading are left alone.", *COUNTED):   # "1 files … are": read wrong
        assert gone not in js and gone not in i18n_py
        for lang in ("de", "es", "fr", "pl"):
            assert gone not in json.loads((UI.parent / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
    for gone in GONE_FROM_THE_WINDOW:
        assert not re.search(r'^\s*' + re.escape(json.dumps(gone, ensure_ascii=False)) + r'\s*:', table, re.M), gone
        if gone in ("Hi, {n}!", "Hi!", "{left} of {limit}", "Remind"):            # nothing else uses these
            for lang in ("de", "es", "fr", "pl"):
                assert gone not in json.loads((UI.parent / "locale" / f"{lang}.json").read_text(encoding="utf-8"))


def _between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def test_the_bars_stay_quiet_and_every_number_is_printed():
    js, css = _ui("app.js"), _ui("style.css")
    draw = _between(js, "function bytes(n)", "// ---------------------------------------------------------------- ")
    assert 'aria-hidden="true"' in _between(draw, "function meter(", "\n}")          # the number is the text
    fig = _between(draw, "function diskFig(", "\n}")
    assert '${meter(n / whole, cls === "used" ? "used" : "thin")}<span class="num">${bytes(n)}</span>' in fig   # a bar, its number
    assert not re.search("[\U0001F000-\U0001FFFF☀-➿]", draw)                # icons, no emoji
    rules = {m.group(1).strip(): m.group(2) for m in re.finditer(r"^([^{}@/\n][^{}\n]*)\{([^}]*)\}", css, re.M)}
    assert "var(--faint)" in rules[".mtr > i"] and "var(--muted)" in rules[".mtr.used > i"]   # facts: grey
    assert "var(--flame)" in rules[".mtr.lmtr > i"] and "var(--red)" in rules[".mtr.low > i"]  # a limit; little left
    assert "border-radius" not in rules[".mtr"]                                       # square, like the site
    assert "var(--flame)" in rules[".plan-bar i.now"] and "var(--muted)" in rules[".plan-bar i.done"]


def test_the_cards_show_rows_with_icons_of_the_kind():
    js, html = _ui("app.js"), _ui("index.html")
    for kind in ("film", "photo", "music", "package", "file", "folder", "disk"):
        assert f'<symbol id="i-{kind}"' in html, kind
    assert 'groupRows(d.groups || [], d.count, "mail")' in js and "groupRows(d.groups || [], d.count)" in js
    assert "fileList(d.files || [], d.count)" in js


def test_the_limit_stands_after_the_buttons_and_the_hint_gives_way():
    js, css = _ui("app.js"), _ui("style.css")
    under = _between(js, '<div class="under">', '<span class="hint"')
    assert under.index('class="fold-wrap"') < under.index('id="lim"')
    assert "grid-template-columns: auto auto minmax(0, 1fr)" in _between(css, ".under {", "}")
    assert re.search(r"@media \(max-width: 900px\) \{[^\n]*\.hint \{ display: none; \}", css)
    assert 'frac < 0.25 ? " · " + t("full again in {t}"' in js                       # the time only when little is left


# ---------------------------------------------------------------- after the design critic
def _fn(js, start):
    """One top-level function of app.js: from its first line to the "}" that closes it at the line start."""
    i = js.index(start)
    return js[i:js.index("\n}\n", i) + 2]


def _node(code, tmp_path):
    """Runs a piece of the window's code in node; what it printed, read as JSON."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    run = tmp_path / "run.js"
    run.write_text(code, encoding="utf-8")
    r = subprocess.run([node, str(run)], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


PLAIN = r"""const LANG = "en", t = (s, o = {}) => s.replace(/\{(\w+)\}/g, (_, k) => o[k]);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const icon = n => `<svg data-i="${n}"></svg>`;
"""


def test_the_disk_figure_starts_with_what_is_used_and_keeps_one_scale(tmp_path):
    js = _ui("app.js")
    code = PLAIN + "".join(_fn(js, f"function {n}(") for n in ("bytes", "meter", "diskFig"))
    html = _node(code + f"process.stdout.write(JSON.stringify(diskFig({json.dumps(FIG)})));", tmp_path)
    rows = re.findall(r'<li(?: class="(\w+)")? title="[^"]*"><span class="nm">([^<]*)</span>'
                      r'<span class="mtr (\w+)" aria-hidden="true"><i style="width:([\d.]+)%"></i></span>'
                      r'<span class="num">([^<]+)</span></li>', html)
    label = {"files": "Files right on the disk", "other": "Other"}
    want = ([("used", "Used", FIG["used"])] + [("", p.get("name") or label[p["kind"]], p["size"]) for p in FIG["parts"]]
            + [("unc", "Not counted", FIG["uncounted"])])
    assert [(c, nm) for c, nm, *_ in rows] == [(c, nm) for c, nm, _ in want]       # "Used" first, then what takes it
    for (c, _, n), (_, _, bar, width, num) in zip(want, rows):
        assert bar == ("used" if c == "used" else "thin")                          # one bar stands out, the rest quiet
        assert abs(float(width) - n / FIG["total"] * 100) < 0.06                   # one scale: the whole disk
        assert num == f"{n / GB:.1f} GB"                                           # and its number beside it
    assert "20.0 GB free of 476.0 GB · almost full" in html and '<svg data-i="warn">' in html


CALLED = [("uk", "Олена", "Олено"), ("uk", "Ганна", "Ганно"), ("uk", "Марія", "Маріє"), ("uk", "Зоя", "Зоє"),
          ("uk", "Таня", "Таню"), ("uk", "Ілля", "Ілле"), ("uk", " Олена ", "Олено"), ("uk", "Андрій", "Андрій"),
          ("uk", "Олена Петрівна", "Олена Петрівна"), ("uk", "Anna", "Anna"), ("uk", "олена", "олена"),
          ("uk", "", ""), ("en", "Олена", "Олена"), ("it", "Anna", "Anna")]


def test_the_hello_calls_a_person_as_ukrainian_does(tmp_path):
    js = _ui("app.js")
    cases = json.dumps([[lang, name] for lang, name, _ in CALLED])
    code = "let LANG;\n" + _fn(js, "function calling(") + (
        f"process.stdout.write(JSON.stringify({cases}.map(([l, n]) => {{ LANG = l; return calling(n); }})));")
    assert _node(code, tmp_path) == [said for *_, said in CALLED]       # the regular endings only; the rest as typed
    assert '${name ? t("Hi, {n}.", { n: esc(calling(name)) }) : t("Hi.")}' in js   # a calm hello, escaped


STREAMED = [("Ось:\n\n| Що | Де |", "Ось:\n"),                                    # a head alone: no table yet
            ("| Що | Де |\n|---|-", ""),                                           # its |---| line still coming
            ("| Що | Де |\n|---|---|", "| Що | Де |\n|---|---|"),                 # whole: the table shows
            ("| Що | Де |\n|---|---|\n| Фото | D:", "| Що | Де |\n|---|---|"),      # a row being written waits
            ("| Що | Де |\n|---|---|\n| Фото | D: |", "| Що | Де |\n|---|---|\n| Фото | D: |"),
            ("Це **важливо", "Це важливо"), ("Готово **так** і **ні", "Готово **так** і ні"),
            ("Набери `npm", "Набери npm"), ("Це **важливо**.", "Це **важливо**."),
            ("```\n| a |\n**b", "```\n| a |\n**b")]                               # inside code: as it comes


def test_an_answer_coming_in_shows_no_half_written_marks(tmp_path):
    js = _ui("app.js")
    code = (js[js.index("const cellsOf = "):js.index("function tableAlign(")] + _fn(js, "function tableAlign(")
            + _fn(js, "function streamTail(") + "process.stdout.write(JSON.stringify("
            + json.dumps([s for s, _ in STREAMED]) + ".map(s => streamTail(s))));")
    assert _node(code, tmp_path) == [shown for _, shown in STREAMED]
    assert js.count("box.innerHTML = md(streamTail(text_));") == 2                 # while it comes in
    assert "box.innerHTML = md(text_);" in js                                      # the whole answer: as written


def test_closing_the_settings_keeps_the_open_chat():
    js = _ui("app.js")
    main = _fn(js, "function renderMain(")          # the settings redraw the window when they close
    assert 'dialog(t("Settings"), `<section id="set-body"></section>`, () => { LANG = S.settings.lang; renderMain(); })' in js
    assert "const was = drawn ? thread : undefined;" in main and "drawn = true;" in main
    assert ("openThread(was === null ? null : was && list.some(x => x.id === was) ? was"
            " : !QUICK && list.length ? list[0].id : null)") in main   # the same chat (or a new one); the newest at first


def test_the_step_going_on_is_shown_once():
    js, css = _ui("app.js"), _ui("style.css")
    assert 'last.classList.toggle("now", !writing && !!p.live && p.live.startsWith(last.textContent.trim()))' in js
    assert ".tool.now { display: none; }" in css                                   # the live line says it already
    assert 'chips.querySelectorAll(".now").forEach(x => x.classList.remove("now"));' in js   # at the end it shows again


def test_a_card_with_one_thing_reads_right_in_english():
    from lanterna import i18n
    said = [i18n.t(k, "en", place="Downloads", to="Documents", count=1) for k in NEW_WORDS[-6:]]
    assert said == ["Sort the files in Downloads (1)", "Sorted the files in Downloads (1)", "Move to Documents (1)",
                    "Moved to Documents (1)", "Move to the Recycle Bin (1)", "Moved to the Recycle Bin (1)"]
    js = _ui("app.js")
    assert 'pc_sort: "Sort the files in {place} ({count})", pc_move: "Move to {to} ({count})"' in js
    assert 'mail_sort: "Sort the emails into folders ({count})"' in js


@pytest.mark.parametrize("lang", ["en", "uk", "it", "de", "es", "fr", "pl"])
def test_the_done_lines_of_moves_still_count_as_moves(lang):
    from lanterna import chat, i18n
    for key in ("Moved to {to} ({count})", "Sorted the files in {place} ({count})"):   # "I moved them" is true after these
        assert chat._MOVED_NOTE.search(i18n.t(key, lang, to="Documents", place="Downloads", count=2)), (lang, key)


def test_the_last_words_of_the_critic():
    js = _ui("app.js")
    assert '<span class="hint" title="${esc(care)}">${esc(careShort)}</span>' in js           # the first sentence fits
    assert 'careShort = care.slice(0, care.indexOf(". ") + 1 || care.length)' in js
    for btn in ('id="lim-refresh"', 'id="fact-add"'):                                           # an icon alone: a name
        assert 'aria-label="${esc(t(' in js[js.index(btn):js.index(">", js.index(btn))], btn
    for btn in ("gh-on", "gd-on", "wd-pick", "bk-set"):                                         # one primary a tab
        assert f'<button class="btn ghost small" id="{btn}">' in js, btn
    assert 'esc(capital(t("switched to {m}", { m }))' in js
    assert '"switched to {m}": { uk: "Тепер відповідає {m}", it: "ora risponde {m}" }' in js    # Lanterna is "she"


def test_the_marks_of_the_services_stand_on_a_plain_tile():
    logo = _fn(_ui("app.js"), "function connLogo(")
    assert "rgba(" not in logo and '<span class="cn-logo img" aria-hidden="true">' in logo   # no tint of the brand
