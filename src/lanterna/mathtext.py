r"""Formulas in answers. Models write them in LaTeX: $…$ or \(…\) inside a sentence, $$…$$ or \[…\] on a line of
their own. The window draws them (KaTeX, ui/katex.js); the terminal and reading aloud get them as plain text:
\frac{Q}{\Delta t} → Q/Δt, x^2 → x², 10^{-19} → 10⁻¹⁹, \Omega → Ω, \sqrt{2} → √2, \ce{H2SO4} → H₂SO₄.

They are found as in the window (cutMath in ui/app.js): "$5 and $10" stay money, `code` stays as it is."""
from __future__ import annotations

import re

_BLANK = re.compile(r"\n[ \t]*\n")


def _money(body: str) -> bool:
    """$10, oppure 5$: starts with a digit, has a space and a word (not a TeX command or \\text{…}): money."""
    return bool(re.match(r"[0-9]", body) and re.search(r"\s", body)
                and re.search(r"[^\W\d_]{3}", re.sub(r"\\[A-Za-z]+\s*(\{[^{}]*\})?", " ", body)))


def parts(text: str) -> list[tuple[str, str]]:
    """The text as ("text", …), ("inline", tex) and ("display", tex) pieces, in order."""
    out: list[tuple[str, str]] = []
    buf: list[str] = []

    def found(kind: str, tex: str) -> None:
        if buf:
            out.append(("text", "".join(buf)))
            buf.clear()
        out.append((kind, tex))

    for n, b in enumerate(str(text or "").split("```")):
        if n:
            buf.append("```")
        if n % 2:                                          # a code block
            buf.append(b)
            continue
        i = 0
        while i < len(b):
            c, d = b[i], b[i + 1:i + 2]
            if c == "`":                                   # `code`, up to as many ` on the same line
                run = re.match(r"`+", b[i:]).group(0)
                end, nl = b.find(run, i + len(run)), b.find("\n", i)
                stop = end + len(run) if end > -1 and (nl < 0 or end < nl) else i + len(run)
                buf.append(b[i:stop])
                i = stop
                continue
            if c == "\\" and d == "$":
                buf.append("$")
                i += 2
                continue
            if c == "\\" and d in ("[", "("):
                end = b.find("\\]" if d == "[" else "\\)", i + 2)
                body = b[i + 2:end] if end > -1 else ""
                if body.strip() and not _BLANK.search(body) and (
                        not re.fullmatch(r"[\d\s,;–-]+", body) if d == "[" else "\n" not in body):   # \[1\]: a note
                    found("display" if d == "[" else "inline", body)
                    i = end + 2
                    continue
            if c == "$" and d == "$":
                end = b.find("$$", i + 2)
                body = b[i + 2:end] if end > -1 else ""
                if body.strip() and not _BLANK.search(body):
                    found("display", body)
                    i = end + 2
                    continue
                buf.append("$$")
                i += 2
                continue
            if c == "$" and d and not d.isspace() and d != "$" and not (i and re.match(r"[A-Za-z0-9_$\\]", b[i - 1])):
                j = i + 1
                while j < len(b) and b[j] not in "$\n":
                    j += 2 if b[j] == "\\" else 1
                body = b[i + 1:j]
                if (j < len(b) and b[j] == "$" and not b[j - 1].isspace() and not re.match(r"[0-9]", b[j + 1:j + 2])
                        and not _money(body)):
                    found("inline", body)
                    i = j + 1
                    continue
            buf.append(c)
            i += 1
    if buf:
        out.append(("text", "".join(buf)))
    return out


# ---------------------------------------------------------------- LaTeX as plain text
GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
         "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
         "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ",
         "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
         "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
         "Omega": "Ω", "hbar": "ℏ", "ell": "ℓ", "infty": "∞", "partial": "∂", "nabla": "∇", "emptyset": "∅",
         "varnothing": "∅", "forall": "∀", "exists": "∃", "nexists": "∄", "neg": "¬", "lnot": "¬", "angle": "∠",
         "measuredangle": "∡", "triangle": "△", "square": "□", "prime": "′", "degree": "°", "aleph": "ℵ", "Re": "ℜ",
         "Im": "ℑ", "ldots": "…", "dots": "…", "dotsc": "…", "dotsb": "⋯", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
         "therefore": "∴", "because": "∵", "bullet": "•", "star": "⋆", "dagger": "†", "checkmark": "✓",
         "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉", "vert": "|",
         "lvert": "|", "rvert": "|", "Vert": "‖", "lVert": "‖", "rVert": "‖", "backslash": "\\", "lbrace": "{",
         "rbrace": "}", "lbrack": "[", "rbrack": "]", "colon": ":", "surd": "√", "top": "⊤", "bot": "⊥"}
REL = {"=": "=", "<": "<", ">": ">", "le": "≤", "leq": "≤", "leqslant": "≤", "ge": "≥", "geq": "≥", "geqslant": "≥",
       "ne": "≠", "neq": "≠", "approx": "≈", "simeq": "≃", "sim": "∼", "cong": "≅", "equiv": "≡", "propto": "∝",
       "ll": "≪", "gg": "≫", "to": "→", "rightarrow": "→", "longrightarrow": "⟶", "leftarrow": "←", "gets": "←",
       "longleftarrow": "⟵", "leftrightarrow": "↔", "Rightarrow": "⇒", "Longrightarrow": "⟹", "implies": "⟹",
       "Leftarrow": "⇐", "Longleftarrow": "⟸", "impliedby": "⟸", "Leftrightarrow": "⇔", "iff": "⟺",
       "Longleftrightarrow": "⟺", "mapsto": "↦", "uparrow": "↑", "downarrow": "↓", "rightleftharpoons": "⇌",
       "leftrightarrows": "⇄", "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃",
       "supseteq": "⊇", "perp": "⊥", "parallel": "∥", "mid": "|", "nmid": "∤", "models": "⊨", "vdash": "⊢",
       "doteq": "≐", "asymp": "≍"}
BIN = {"+": "+", "-": "-", "−": "-", "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "·", "ast": "*",
       "circ": "∘", "cup": "∪", "cap": "∩", "setminus": "∖", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨",
       "oplus": "⊕", "ominus": "⊖", "otimes": "⊗", "odot": "⊙", "bmod": "mod", "mod": "mod"}
BIGOP = {"sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮",
         "bigcup": "⋃", "bigcap": "⋂", "bigoplus": "⨁", "bigotimes": "⨂"}
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "arccot", "sinh", "cosh", "tanh", "coth",
         "sh", "ch", "th", "tg", "ctg", "arctg", "arcctg", "log", "ln", "lg", "exp", "lim", "liminf", "limsup", "max",
         "min", "sup", "inf", "det", "dim", "ker", "gcd", "deg", "arg", "Pr", "hom", "argmax", "argmin"}
BB = {"N": "ℕ", "Z": "ℤ", "Q": "ℚ", "R": "ℝ", "C": "ℂ", "P": "ℙ", "H": "ℍ"}
ACCENT = {"vec": "\u20d7", "overrightarrow": "\u20d7", "hat": "\u0302", "widehat": "\u0302", "bar": "\u0304",
          "overline": "\u0305", "dot": "\u0307", "ddot": "\u0308", "tilde": "\u0303", "widetilde": "\u0303",
          "check": "\u030c", "acute": "\u0301", "grave": "\u0300", "breve": "\u0306", "underline": "\u0332"}
SAME = {"text", "textrm", "textbf", "textit", "textsf", "texttt", "textnormal", "textup", "mbox", "hbox", "emph"}
STYLE = {"mathrm", "mathbf", "mathit", "mathsf", "mathtt", "mathnormal", "boldsymbol", "bm", "mathcal", "mathscr",
         "mathfrak", "pmb", "boxed", "fbox", "cancel", "bcancel", "xcancel", "sout", "underbrace", "overbrace",
         "mathring", "smash", "mathop", "mathbin", "mathrel", "mathord", "mathopen", "mathclose", "mathpunct",
         "mathinner", "operatorname"}
DROP = {"left", "right", "middle", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr",
        "Biggl", "Biggr", "limits", "nolimits", "nonumber", "notag", "hline", "strut", "mathstrut", "allowbreak",
        "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle", "relax", "centering"}
SKIP_ARG = {"color", "label", "phantom", "hphantom", "vphantom", "cline", "hspace", "vspace", "kern", "mkern"}
SPACE = {",": " ", ":": " ", ";": " ", ">": " ", " ": " ", "!": "", "quad": " ", "qquad": " ", "enspace": " ",
         "thinspace": " ", "medspace": " ", "thickspace": " ", "space": " ", "nobreakspace": " ", "negthinspace": ""}
_SUP = dict(zip("0123456789+-−=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ"))
_SUB = dict(zip("0123456789+-−=()", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎"))
_ROWS = {"pmatrix": "()", "bmatrix": "[]", "Bmatrix": "{}", "vmatrix": "||", "Vmatrix": "‖‖"}


def sup(s: str) -> str:
    s = s.strip()
    if s in ("∘", "°", "\\circ"):
        return "°"
    if s and set(s) <= {"′"}:
        return s
    if s and all(ch in _SUP for ch in s):
        return "".join(_SUP[ch] for ch in s)
    return "" if not s else "^" + s if len(s) == 1 else f"^({s})"


def sub(s: str) -> str:
    s = s.strip()
    if s and all(ch in _SUB for ch in s):
        return "".join(_SUB[ch] for ch in s)
    return "" if not s else "_" + s if len(s) == 1 or s.isalnum() else f"_({s})"


# one thing: a number, or a letter with its marks and scripts (Δt, dx, r², R₁, x_max)
_ONE = re.compile(r"(?:\d+(?:[.,]\d+)?|[Δδd∂]?[^\W\d_][\u0300-\u036f\u20d0-\u20ff]*)"
                  r"(?:[⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ⁺⁻⁼⁽⁾₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎′°]|[_^](?:\([^()]*\)|[^\W_]+))*")


def _over(s: str) -> str:
    """The top of a fraction: in brackets when it is more than one term (a + b, a/b)."""
    s = s.strip()
    return f"({s})" if re.search(r"[\s+\-=<>±∓×÷·,;/]", s) else s


def _under(s: str) -> str:
    """The bottom of a fraction or what is under a root: in brackets unless it is one thing (Δt, r², 2)."""
    s = s.strip()
    return s if not s or _ONE.fullmatch(s) else f"({s})"


def chem(src: str) -> str:
    r"""\ce{…} (chemistry) as text: 2H2 + O2 -> 2H2O → 2H₂ + O₂ → 2H₂O, Fe^{3+} → Fe³⁺, SO4^2- → SO₄²⁻."""
    s = " ".join(src.split())
    s = re.sub(r"<=>|<->|<-->|->|<-|=>", lambda m: {"<=>": " ⇌ ", "<->": " ↔ ", "<-->": " ⇄ ", "->": " → ",
                                                       "<-": " ← ", "=>": " ⇒ "}[m.group(0)], s)
    s = re.sub(r"(→|←|⇌|↔|⇄)\s*(\[[^\]]*\]){1,2}", r"\1", s)            # conditions over an arrow
    s = re.sub(r"\^\{?([0-9]*[+-]|[0-9]+)\}?", lambda m: sup(m.group(1)), s)
    s = re.sub(r"(?<=[A-Za-z)\]])([0-9]?[+-])(?=\s|$|[),])", lambda m: sup(m.group(1)), s)   # Na+, Cl-, Mg2+
    s = re.sub(r"(?<=[A-Za-z)\]])([0-9]+)", lambda m: sub(m.group(1)), s)
    s = s.replace("*", "·").replace("_", "")
    return " ".join(s.replace("{", "").replace("}", "").split())


class _TeX:
    """A small reader of LaTeX math: enough of it for plain text that reads like the formula."""

    def __init__(self, src: str, display: bool = False):
        self.s, self.i, self.display = src, 0, display

    # -- the pieces of the source
    def _skip_spaces(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def raw_group(self) -> str:
        """{…} as written (or the next single sign), for \\text, \\ce and names."""
        self._skip_spaces()
        s = self.s
        if self.i >= len(s):
            return ""
        if s[self.i] != "{":
            m = re.compile(r"\\[A-Za-z]+|\\.|.", re.S).match(s, self.i)
            self.i = m.end()
            return m.group(0)
        depth, j = 0, self.i
        while j < len(s):
            if s[j] == "\\":
                j += 2
                continue
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            if depth == 0:
                break
            j += 1
        body, self.i = s[self.i + 1:j], min(j + 1, len(s))
        return body

    def optional(self) -> str:
        """[…] right after a command (\\sqrt[3]{x}), or ""."""
        self._skip_spaces()
        if self.i < len(self.s) and self.s[self.i] == "[":
            end = self.s.find("]", self.i)
            if end > -1:
                body, self.i = self.s[self.i + 1:end], end + 1
                return body
        return ""

    def arg(self, script: bool = False) -> str:
        """The next argument as text: a {group}, a command, or one sign."""
        self._skip_spaces()
        if self.i >= len(self.s):
            return ""
        c = self.s[self.i]
        if c == "{":
            self.i += 1
            return self.math(script=script, until="}")
        if c == "\\":
            text, _kind = self.command()
            return text or ""
        self.i += 1
        return c

    # -- reading
    def math(self, script: bool = False, until: str = "") -> str:
        """Atoms with their sub- and superscripts, spaced like TeX does it (none inside a script). A fraction next to
        other things goes in brackets: (1/2)mv², ρ(L/S)."""
        out: list[str] = []
        prev, gap = None, False
        while self.i < len(self.s):
            c = self.s[self.i]
            if c.isspace():
                self.i += 1
                gap = True
                continue
            if until and c == until:
                self.i += 1
                break
            if c in "^_":
                text, kind = "", "ord"
            elif c == "{":
                self.i += 1
                text, kind = self.math(script=script, until="}"), "ord"
            elif c == "\\":
                text, kind = self.command()
                if text is None:
                    continue
            else:
                self.i += 1
                text, kind = self.char(c)
            scripts = self.scripts()
            if kind == "space":
                out.append(text + scripts)
                prev = "ord" if prev == "frac" else prev
                continue
            if kind == "frac" and (scripts or prev in ("ord", "close", "frac", "op")):
                text, kind = f"({text})", "ord"
            if prev == "frac" and kind in ("ord", "open", "frac", "op"):
                out[-1] = f"({out[-1]})"                             # the fraction before this one: (1/2)m
                prev = "ord"
            text += scripts
            if not script:
                if kind == "bin" and prev in (None, "bin", "rel", "open", "punct", "op"):
                    kind = "ord"                                     # a sign: -5, (−x)
                if kind in ("rel", "bin"):
                    text = f" {text} "
                elif kind == "op" and prev not in (None, "open", "op", "rel", "bin", "punct"):
                    text = " " + text
                elif kind in ("ord", "frac") and prev == "op" and text[:1] not in "([":
                    text = " " + text
                elif prev == "punct" and gap:
                    text = " " + text                                # "1, 2" keeps its space, "3,14" stays one number
            out.append(text)
            prev, gap = kind, False
        return "".join(out)

    @staticmethod
    def char(c: str) -> tuple[str, str]:
        if c in REL:
            return REL[c], "rel"
        if c in "+-−*×÷±·":
            return {"−": "-"}.get(c, c), "bin"
        if c in "([":
            return c, "open"
        if c in ")]":
            return c, "close"
        if c in ",;":
            return c, "punct"
        if c == "~":
            return " ", "space"
        if c == "&":
            return " ", "space"
        if c == "}":                                         # a stray closing brace
            return "", "space"
        return c, "ord"

    def scripts(self) -> str:
        out = ""
        while True:
            j = self.i
            while j < len(self.s) and self.s[j].isspace():
                j += 1
            if j < len(self.s) and self.s[j] in "^_":
                which, self.i = self.s[j], j + 1
                body = self.arg(script=True)
                out += sup(body) if which == "^" else sub(body)
            elif j < len(self.s) and self.s[j] == "'":
                self.i = j + 1
                out += "′"
            else:
                return out

    def command(self) -> tuple[str | None, str]:
        """\\name or \\x at self.i: its text and kind (ord, op, bin, rel, open, close, punct, space); None: nothing."""
        s = self.s
        m = re.compile(r"\\([A-Za-z]+\*?|.?)", re.S).match(s, self.i)
        name, self.i = m.group(1), m.end()
        if name[:1].isalpha():
            name = name.rstrip("*")
            while self.i < len(s) and s[self.i] in " \t\n":                 # a space after \name belongs to it
                self.i += 1
        if name in SPACE:
            return SPACE[name], "space"
        if name in ("{", "}"):
            return name, "open" if name == "{" else "close"
        if name == "|":
            return "‖", "ord"
        if name == "\\" or name in ("newline", "cr"):
            self.optional()
            return "\n" if self.display else "; ", "space"
        if len(name) == 1 and not name.isalpha():                          # \% \$ \& \# \_
            return name, "ord"
        if name in GREEK:
            return GREEK[name], "ord"
        if name in REL:
            return REL[name], "rel"
        if name in BIN:
            return BIN[name], "bin"
        if name in BIGOP:
            return BIGOP[name], "op"
        if name in FUNCS:
            return name, "op"
        if name in DROP:
            if name in ("left", "right", "middle", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr", "big",
                        "Big", "bigg", "Bigg"):
                self._skip_spaces()
                if s[self.i:self.i + 1] == ".":                              # \left. : no bracket
                    self.i += 1
            return None, "space"
        if name in SKIP_ARG:
            self.raw_group()
            return None, "space"
        if name in ("frac", "dfrac", "tfrac", "cfrac", "flatfrac"):
            a, b = self.arg(), self.arg()
            return f"{_over(a)}/{_under(b)}", "frac"
        if name in ("binom", "dbinom", "tbinom"):
            a, b = self.arg(), self.arg()
            return f"C({a.strip()}, {b.strip()})", "ord"
        if name == "sqrt":
            n, x = self.optional().strip(), self.arg()
            return ({"": "√", "2": "√", "3": "∛", "4": "∜"}.get(n) or sup(n) + "√") + _under(x), "ord"
        if name in SAME:
            return self.text(self.raw_group()), "ord"
        if name in ("mathbb", "Bbb", "mathbbm"):
            body = self.arg()
            return "".join(BB.get(ch, ch) for ch in body), "ord"
        if name in STYLE:
            return self.arg(), "op" if name == "operatorname" else "ord"
        if name in ACCENT:
            body = self.arg().strip()
            mark = ACCENT[name]
            if len(body) > 1 and name in ("overline", "underline"):
                return "".join(ch + mark for ch in body), "ord"
            return body + mark, "ord"
        if name in ("textcolor", "colorbox", "href"):
            self.raw_group()
            return self.arg(), "ord"
        if name in ("overset", "stackrel", "underset"):
            self.arg(script=True)
            base = self.arg()
            return base.strip(), "rel" if base.strip() in REL.values() else "ord"
        if name in ("xrightarrow", "xleftarrow", "xRightarrow", "xLeftarrow", "xleftrightarrow"):
            self.optional()
            self.raw_group()
            return {"xrightarrow": "→", "xleftarrow": "←", "xRightarrow": "⇒", "xLeftarrow": "⇐"}.get(name, "↔"), "rel"
        if name == "pmod":
            return f" (mod {self.arg().strip()})", "ord"
        if name in ("ce", "pu"):
            return chem(self.raw_group()), "ord"
        if name == "tag":
            return f"   ({self.text(self.raw_group())})", "space"
        if name == "not":
            nxt = self.arg()
            return {"=": "≠", "∈": "∉", "<": "≮", ">": "≯", "≡": "≢", "⊂": "⊄", "|": "∤"}.get(nxt.strip(), nxt + "\u0338"), "rel"
        if name == "begin":
            return self.environment(self.raw_group().strip()), "ord"
        if name == "end":
            self.raw_group()
            return None, "space"
        if s[self.i:self.i + 1] == "{":                                     # an unknown command with a group: the group
            return None, "space"
        return name, "ord"

    def text(self, body: str) -> str:
        """\\text{…}: the words as written, $…$ inside as math."""
        out = re.sub(r"\$([^$]*)\$", lambda m: to_text(m.group(1)), body)
        out = re.sub(r"\\([%$&#_{}])", r"\1", out)
        out = re.sub(r"\\(?:[,;: !]|quad|qquad|enspace|space)\s*", " ", out)
        out = re.sub(r"\\([A-Za-z]+)\s*", lambda m: GREEK.get(m.group(1), REL.get(m.group(1), "")), out)
        return out.replace("{", "").replace("}", "").replace("~", " ")

    def environment(self, name: str) -> str:
        """\\begin{name}…\\end{name}: rows on lines of their own (or after "; " inside a sentence)."""
        name = name.rstrip("*")
        if name in ("array", "tabular", "alignat", "alignedat"):
            self.raw_group()
        s, depth, j = self.s, 0, self.i
        begin, end = re.compile(r"\\begin\s*\{"), re.compile(r"\\end\s*\{")
        while j < len(s):
            if begin.match(s, j):
                depth += 1
            elif end.match(s, j):
                if depth == 0:
                    break
                depth -= 1
            j += 1
        body = s[self.i:j]
        close = s.find("}", j)
        self.i = close + 1 if j < len(s) and close > -1 else len(s)
        rows = [[_TeX(cell).math().strip() for cell in _split(row, "&")] for row in _split(body, "\\\\")]
        lines = [" ".join(" ".join(r).split()) for r in rows if any(r)]
        if name in _ROWS:
            a, b = _ROWS[name]
            lines = [f"{a}{line}{b}" for line in lines] if self.display else [f"{a}{'; '.join(lines)}{b}"]
        return ("\n" if self.display else "; ").join(lines)


def _split(body: str, sep: str) -> list[str]:
    """body cut at sep where it isn't inside {…} or an inner \\begin…\\end."""
    out, depth, env, j, last = [], 0, 0, 0, 0
    while j < len(body):
        if body.startswith("\\begin", j):
            env += 1
        elif body.startswith("\\end", j):
            env -= 1
        if body.startswith(sep, j) and depth == 0 and env == 0:
            out.append(body[last:j])
            j += len(sep)
            last = j
            continue
        if body[j] == "\\":
            j += 2
            continue
        depth += {"{": 1, "}": -1}.get(body[j], 0)
        j += 1
    out.append(body[last:])
    return out


def to_text(tex: str, display: bool = False) -> str:
    r"""One formula as plain text: \frac{Q}{\Delta t} → Q/Δt. A display formula may have several lines."""
    try:
        text = _TeX(str(tex), display).math()
    except (RecursionError, AttributeError, IndexError):                  # very deep or odd TeX: as written
        return " ".join(str(tex).split())
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# ---------------------------------------------------------------- for the terminal and for reading aloud
_MD_SIGNS = re.compile(r"([\\`*_\[\]<>#|~])")


def _md(s: str) -> str:
    """Plain text that the terminal's Markdown shows as it is."""
    s = re.sub(r"^(\s*)([-+])(?=\s)", r"\1\\\2", _MD_SIGNS.sub(r"\\\1", s))      # not a list: "- x", "1. x"
    return re.sub(r"^(\s*\d+)([.)])(?=\s)", r"\1\\\2", s)


def for_terminal(text: str) -> str:
    """The answer for the terminal's Markdown, formulas as text. One on a line of its own stays on its own line(s):
    the line before it and its own lines end with two spaces, Markdown's line break."""
    ps = parts(text)
    if len(ps) == 1 and ps[0][0] == "text":
        return ps[0][1]
    out = ""
    for n, (kind, src) in enumerate(ps):
        if kind == "text":
            out += src
            continue
        line_start = out[out.rfind("\n") + 1:]
        after = ps[n + 1][1] if n + 1 < len(ps) and ps[n + 1][0] == "text" else ""
        if kind == "display" and not line_start.strip() and not after.split("\n", 1)[0].strip(" \t.,;:!?"):
            head = out[:len(out) - len(line_start)]
            if head.endswith("\n") and head[:-1].rsplit("\n", 1)[-1].strip() and not head[:-1].endswith("  "):
                head = head[:-1] + "  \n"
            rows = [_md(r) for r in to_text(src, display=True).split("\n")]
            out = head + line_start + ("  \n" + line_start).join(rows)
            if "\n" in after:                                                # the next line starts on a line of its own
                k = after.index("\n")
                ps[n + 1] = ("text", after[:k].rstrip() + "  " + after[k:])
        else:
            out += _md(to_text(src).replace("\n", "; "))
    return out


def plain(text: str) -> str:
    """A short line (a chat's name, a suggested next message) with its formulas as plain text: $R_{eq}$ → R_eq."""
    return "".join(src if kind == "text" else to_text(src).replace("\n", "; ") for kind, src in parts(text))


def for_speech(text: str) -> str:
    """The answer with its formulas as words and signs to read: I = Q/Δt."""
    return "".join(src if kind == "text" else f" {to_text(src).replace(chr(10), '; ')} " for kind, src in parts(text))
