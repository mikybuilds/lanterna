r"""Round 139 (1.1.9b1): formulas.

Models write formulas in LaTeX ($I$, $$I = \frac{Q}{\Delta t}$$, \(…\), \[…\]) and the window showed them as typed.
- The window draws them with KaTeX, which is part of the app (no internet): a formula on a line of its own sits in
  the middle, one in a sentence stays in the line; chemistry (\ce{H2O}) too. Money stays money ("$5 and $10"),
  `code` stays code, and TeX that KaTeX can't read stays as written.
- Answers also show tables, "---" lines and > quotes, which came as typed too.
- The terminal and reading aloud get formulas as plain text: Q/Δt, x², 10⁻¹⁹, Ω, √2, H₂O.
"""
import asyncio
import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path

import httpx
import pytest

from lanterna import gui, keys, speech, tui
from lanterna.mathtext import for_terminal, parts, to_text

UI = Path(gui.__file__).parent / "ui"
JS = (UI / "app.js").read_text(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]

# the answer from the report: Gemini's study notes in Italian
NOTES = ("Ecco la base:\n\n"
         "*   **Corrente elettrica ($I$)**: È il flusso ordinato di cariche elettriche.\n"
         "    $$\\text{Formula: } I = \\frac{Q}{\\Delta t} \\quad \\text{[Ampere, A]}$$\n"
         "*   **Resistenza elettrica ($R$)**: È la proprietà di opporsi alla corrente.\n"
         "    $$\\text{Unità di misura: Ohm } [\\Omega]$$\n\n---\n")


def _grab(name: str) -> str:
    i = JS.index(name)
    depth = 0
    for k in range(JS.index("{", i), len(JS)):
        depth += {"{": 1, "}": -1}.get(JS[k], 0)
        if depth == 0:
            return JS[i:k + 1]
    raise AssertionError(name)


def _line(start: str, until_semicolon: bool = False) -> str:
    """A top-level const of app.js: its line, or up to the line that ends with ";"."""
    return re.search(r"^" + re.escape(start) + (r"[\s\S]*?;$" if until_semicolon else r".*$"), JS, re.M).group(0)


def _node(code: str, katex: bool = True, fake_tex: bool = False):
    """Runs app.js's md() (and what it uses) in node; with the real KaTeX of the window, or none, or a stand-in
    tex() that only says what it was given."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    load = ""
    if katex:
        load = ("const self = {}, window = self, document = { compatMode: 'CSS1Compat', addEventListener() {} };\n"
                "new Function('self', 'window', 'document', 'module', 'exports', 'define', require('fs').readFileSync("
                + json.dumps(str(UI / "katex.js")) + ", 'utf8'))(self, window, document);\nconst katex = self.katex;")
    tex = 'function tex(src, display) { return (display ? "D:" : "I:") + src; }' if fake_tex else _grab("function tex(")
    src = "\n".join([load, _line("const esc = "), _line("const TEX = "), tex, _line("const moneyLike = "), _grab("function cutMath("),
                     _line("const cellsOf = ", until_semicolon=True), _grab("function tableAlign("), _grab("function md("), code])
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _md(text: str, plain: bool = False, katex: bool = True) -> str:
    return _node(f"process.stdout.write(JSON.stringify(md({json.dumps(text)}, {str(plain).lower()})))", katex=katex)


def _formulas(html: str) -> list[tuple[str, str]]:
    """The formulas KaTeX drew: ("D" on a line of its own or "I" in a line, the TeX it was given)."""
    out = []
    for m in re.finditer(r'(<span class="katex-display">)?<span class="katex">', html):
        tex = re.search(r'<annotation encoding="application/x-tex">(.*?)</annotation>', html[m.end():], re.S).group(1)
        out.append(("D" if m.group(1) else "I", unescape(tex)))
    return out


# ---------------------------------------------------------------- finding formulas: the window and the terminal agree
FIND = [
    ("**Corrente elettrica ($I$)**", ["I:I"]),
    ("$$x^2$$ and \\(a\\) and \\[b\\]", ["D:x^2", "I:a", "D:b"]),
    ("$$\n\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}\n$$", ["D:\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}"]),
    ("Costa $5 e $10, oppure 5$ e 10$.", []),
    ("between $5 and $10", []),
    ("$5-$10 or $20,000 and $30,000", []),
    ("=SUM($A$1:$B$2) or US$5", []),
    ("`echo $HOME$PATH` and ```\n$x$\n``` and $y$", ["I:y"]),
    ("``a $b$ c`` $d$", ["I:d"]),
    ("see \\[1\\] and \\[2, 3\\]", []),
    ("\\$5 and $x$", ["I:x"]),
    ("$x $ and $ x$ and $x$5", []),
    ("$2x + 1$ and $1, 2$ and $3 \\cdot 4$", ["I:2x + 1", "I:1, 2", "I:3 \\cdot 4"]),
    ("$3x + 2 = 11$, $10 metri$, $10\\text{ metri}$, $10 \\, \\mathrm{cm}$, $10. Excel: =SUM($A$1)",
     ["I:3x + 2 = 11", "I:10\\text{ metri}", "I:10 \\, \\mathrm{cm}"]),
    ("$a\\$b$ and $$a\n\nb$$", ["I:a\\$b"]),
    ("$x\ny$ and $$$", []),
    ("$\\ce{H2O}$ is water", ["I:\\ce{H2O}"]),
]


@pytest.mark.parametrize("text, found", FIND)
def test_the_window_and_the_terminal_find_the_same_formulas(text, found):
    js = _node(f"const f = []; {json.dumps(text)}.split('```').forEach((b, i) => i % 2 || cutMath(b, f)); "   # as md()
               "process.stdout.write(JSON.stringify(f.map(x => x.html)))", katex=False, fake_tex=True)
    py = [("D:" if kind == "display" else "I:") + src.strip() for kind, src in parts(text) if kind != "text"]
    assert js == found and py == found


def test_money_code_and_escaped_dollars_stay_as_written():
    text = "Costa $5 e $10. Excel: =SUM($A$1:$B$2). `echo $HOME` and \\$7"
    assert "".join(s for _k, s in parts(text)) == text.replace("\\$7", "$7")
    assert for_terminal("No formulas **here**, $5.") == "No formulas **here**, $5."


# ---------------------------------------------------------------- the window
def test_the_window_draws_the_formulas_of_the_report():
    html = _md(NOTES)
    assert _formulas(html) == [("I", "I"), ("D", "\\text{Formula: } I = \\frac{Q}{\\Delta t} \\quad \\text{[Ampere, A]}"),
                               ("I", "R"), ("D", "\\text{Unità di misura: Ohm } [\\Omega]")]
    assert "$" not in re.sub(r"<annotation.*?</annotation>", "", html) and "katex-error" not in html
    assert "<br><span class=\"katex-display\">" not in html                      # its own line, no empty line above
    assert html.count("<li>") == 2 and html.endswith("<hr>")                    # still a list; "---" is a line
    assert "<math" in html                                                      # MathML for screen readers


def test_chemistry_greek_and_matrices_are_drawn():
    html = _md("Acqua: $\\ce{H2O}$, $\\alpha + \\beta$\n\n$$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$$")
    assert [k for k, _ in _formulas(html)] == ["I", "I", "D"] and "katex-error" not in html
    assert "<msub>" in html and "α" in html and "<mtable" in html


def test_tex_katex_cannot_read_and_no_katex_stay_as_written():
    html = _md("Broken: $\\frac{a$ and fine: $x$")
    assert "Broken: $\\frac{a$ and fine: " in html and _formulas(html) == [("I", "x")]
    html = _md("**Bold** $I = \\frac{Q}{t}$", katex=False)                     # no katex.js: the page still works
    assert html == "<p><strong>Bold</strong> $I = \\frac{Q}{t}$</p>"


def test_your_own_message_keeps_its_dollars_and_lines():
    html = _md("Quanto fa $x^2$?\n---\n| a | b |\n|---|---|", plain=True)
    assert "katex" not in html and "<hr>" not in html and "<table>" not in html


def test_tables_lines_and_quotes():
    html = _md("| Grandezza | Simbolo | Unità |\n|---|:-:|--:|\n| Corrente | $I$ | **A** |\n| Modulo | $|x|$ \\| y |\n\n"
               "Testo\n\n***\n\n> **Nota:** due\n> righe\n\na | b\nc | d\n\nx | y\n---", katex=False)
    assert ('<div class="tbl"><table><thead><tr><th>Grandezza</th><th style="text-align:center">Simbolo</th>'
            '<th style="text-align:right">Unità</th></tr></thead><tbody>') in html
    assert '<td style="text-align:center">$I$</td><td style="text-align:right"><strong>A</strong></td>' in html
    assert '<td style="text-align:center">$|x|$ | y</td><td style="text-align:right"></td>' in html   # | in a formula
    assert "<p>Testo</p><hr><blockquote><strong>Nota:</strong> due<br>righe</blockquote>" in html
    assert "<p>a | b<br>c | d</p>" in html                                      # no rule line: not a table
    assert html.endswith("<p>x | y</p><hr>")                                    # a rule needs a |


def test_the_page_loads_katex_from_the_app():
    page = (UI / "index.html").read_text(encoding="utf-8")
    assert page.index('href="katex.css"') < page.index('href="style.css"')
    assert page.index('src="katex.js"') < page.index('src="app.js"')
    css = (UI / "katex.css").read_text(encoding="utf-8")
    fonts = re.findall(r"@font-face\{[^}]*\}", css)
    assert len(fonts) == 20 and all("url(data:font/woff2;base64," in f for f in fonts)   # nothing to fetch
    assert "url(fonts/" not in css
    js = (UI / "katex.js").read_text(encoding="utf-8")
    assert "mhchem.min.js" in js and "copy-tex.min.js" in js
    assert "MIT" in (UI / "katex-license.txt").read_text(encoding="utf-8")
    assert "ui/*" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")          # the files go into the package


# ---------------------------------------------------------------- formulas as text
@pytest.mark.parametrize("tex, text", [
    (r"\text{Formula: } I = \frac{Q}{\Delta t} \quad \text{[Ampere, A]}", "Formula: I = Q/Δt [Ampere, A]"),
    (r"\text{Unità di misura: Ohm } [\Omega]", "Unità di misura: Ohm [Ω]"),
    (r"\frac{1}{2}mv^2", "(1/2)mv²"),
    (r"\rho \frac{L}{S}", "ρ(L/S)"),
    (r"\frac{q_1 q_2}{4\pi\varepsilon_0 r^2}", "q₁q₂/(4πε₀r²)"),
    (r"\frac{a+b}{c} + \frac{dV}{dt}", "(a + b)/c + dV/dt"),
    (r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", "x = (-b ± √(b² - 4ac))/(2a)"),
    (r"1.6 \times 10^{-19}\,\text{C}", "1.6 × 10⁻¹⁹ C"),
    (r"30^\circ + 45^{\circ}", "30° + 45°"),
    (r"\sqrt{2} \cdot \sqrt[3]{8}", "√2 · ∛8"),
    (r"e^{i\pi} + 1 = 0", "e^(iπ) + 1 = 0"),
    (r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}", "∑_(i=1)ⁿ i = (n(n + 1))/2"),
    (r"\int_0^1 x^2 \, dx", "∫₀¹ x² dx"),
    (r"\lim_{x \to \infty} f(x)", "lim_(x→∞) f(x)"),
    (r"\vec{F} = m\vec{a}", "F\u20d7 = ma\u20d7"),
    (r"\Delta V = V_A - V_B,\; x_{\text{max}}", "ΔV = V_A - V_B, x_max"),
    (r"\sin^2 x + \cos^2 x = 1", "sin² x + cos² x = 1"),
    (r"\log_2 8 \neq \ln e", "log₂ 8 ≠ ln e"),
    (r"x \in \mathbb{R},\ x \geq 0", "x ∈ ℝ, x ≥ 0"),
    (r"\left( \frac{a}{b} \right)^2", "(a/b)²"),
    (r"\{1, 2\} \cup \{3,14\}", "{1, 2} ∪ {3,14}"),
    (r"50\% \text{ di } 20", "50% di 20"),
    (r"\ce{2H2 + O2 -> 2H2O}", "2H₂ + O₂ → 2H₂O"),
    (r"\ce{Na+ + Cl- -> NaCl},\ \ce{SO4^2-},\ \ce{Fe^{3+}}", "Na⁺ + Cl⁻ → NaCl, SO₄²⁻, Fe³⁺"),
    (r"\pu{9.81 m/s^2}", "9.81 m/s²"),
    (r"f(x) = \begin{cases} x, & x \geq 0 \\ -x, & x < 0 \end{cases}", "f(x) = x, x ≥ 0; -x, x < 0"),
    (r"A = \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}", "A = (1 2; 3 4)"),
    (r"\frac{", "/"), (r"\begin{", ""), ("\\", ""), ("{" * 400 + "x" + "}" * 400, "x"),       # broken: no crash
])
def test_formulas_as_plain_text(tex, text):
    assert to_text(tex) == text


def test_a_formula_of_several_lines():
    assert to_text(r"\begin{aligned} a &= b + c \\ &= d \end{aligned}", display=True) == "a = b + c\n= d"
    assert to_text(r"\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}", display=True) == "(1 2)\n(3 4)"


def test_the_terminal_shows_formulas_as_text_on_their_own_lines():
    from markdown_it import MarkdownIt                      # the parser of the terminal's Markdown (Textual)
    out = tui.shown(NOTES)
    assert ("*   **Corrente elettrica (I)**: È il flusso ordinato di cariche elettriche.  \n"
            "    Formula: I = Q/Δt \\[Ampere, A\\]  \n*   **Resistenza") in out
    html = MarkdownIt("gfm-like").render(out)
    assert "elettriche.<br />\nFormula: I = Q/Δt [Ampere, A]</li>" in html          # a line of its own, in the item
    assert html.count("<li>") == 2 and "<hr />" in html and "$" not in html and "\\" not in html
    html = MarkdownIt("gfm-like").render(for_terminal("| a | $|x|$ |\n|---|---|\n| $x_1 * y_2$ | $-1$ |"))
    assert "<th>|x|</th>" in html and "<td>x₁ * y₂</td>" in html and "<td>-1</td>" in html   # signs stay signs
    out = for_terminal("Risolvi:\n$$\\begin{aligned} x &= 1 \\\\ y &= 2 \\end{aligned}$$\nFine.")
    assert MarkdownIt("gfm-like").render(out) == "<p>Risolvi:<br />\nx = 1<br />\ny = 2<br />\nFine.</p>\n"


def test_a_chat_name_and_suggested_messages_have_no_tex():
    from lanterna import chat
    assert chat.clean_title("Legge di Ohm: $V = R \\cdot I$") == "Legge di Ohm: V = R · I"
    assert chat.clean_follow_ups("- Come si calcola $R_{eq}$?\n- E se \\(\\frac{1}{R}\\) cresce?\n- Costa $5?") == [
        "Come si calcola R_eq?", "E se 1/R cresce?", "Costa $5?"]


def test_reading_aloud_says_the_formula():
    words = speech.speakable(NOTES)
    assert "Formula: I = Q/Δt [Ampere, A]" in words and "\\frac" not in words and "$" not in words


def test_the_chat_in_the_terminal_shows_the_formula(tmp_path, monkeypatch):
    pytest.importorskip("textual")
    from textual.widgets import Input, Markdown
    from lanterna.app import Api
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router
    from lanterna.store import Store

    monkeypatch.setattr(keys, "get_key", lambda p: "k")
    monkeypatch.setattr(keys, "stored_key", lambda p: "k")
    api = Api(store=Store(tmp_path / "t.db"))
    api.settings.onboarded, api.settings.sync_asked, api.settings.update_check, api.settings.provider = True, True, False, "groq"
    body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in ("La legge:\n", "$$V = R \\cdot I$$"))
    router = Router([Candidate("groq", "fake-model", 50)], client_for=lambda pid: Client(
        PROVIDERS["groq"], "k", transport=httpx.MockTransport(lambda req: httpx.Response(200, content=(body + "data: [DONE]\n\n").encode()))))
    router.current = router.candidates[0]
    monkeypatch.setattr(api, "_get_router", lambda refresh=False: router)

    async def go():
        app = tui.LanternaApp(api=api)
        async with app.run_test(size=(110, 36)) as pilot:
            for _ in range(200):
                await pilot.pause(0.05)
                if type(app.screen).__name__ == "ChatScreen" and app.screen.query("#composer"):
                    break
            app.screen.query_one("#composer", Input).value = "Ohm?"
            await pilot.press("enter")
            for _ in range(200):
                await pilot.pause(0.05)
                if app.screen._stream is None and app.screen._text:
                    break
            await pilot.pause(0.3)
            shown = [m.source for m in app.screen.query(".msg-bot").results(Markdown)]
            assert shown[-1] == "La legge:  \nV = R · I"
    asyncio.run(go())

