"""New Word (.docx) and LibreOffice (.odt) documents from the text Lanterna writes, and CSV files Excel reads.

Word and LibreOffice files are zip archives of XML: plain text put into one makes a file that doesn't open. Here
Markdown-like text becomes a real document: headings (#, ##, ###), paragraphs, bullet and numbered lists, quotes,
code blocks, and **bold**, *italic* and `code` inside a line; the rows of a table become lines with tabs. An
existing document is never changed (its formatting would be lost). Standard library only.

A new CSV file starts with a byte order mark, so Excel shows Cyrillic and other letters right (LibreOffice and
Google Sheets read it either way); a rewritten one keeps what the old file had. Excel also splits the columns by
the list separator of the computer's region (";" in Ukraine, Germany, France…): the model is told which one.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from xml.sax.saxutils import escape

DOCS = {".docx", ".odt"}
BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"

# not allowed in XML (control characters, the two non-characters, halves of a broken character)
_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\U0000FFFE\U0000FFFF\U0000D800-\U0000DFFF]")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_INLINE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|(?<![\w*])([*_])(?=\S)([^*_\n]+?)(?<=\S)\2(?![\w*])|`([^`\n]+)`")
_RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?")


def blocks(text: str) -> list[tuple[str, str]]:
    """The text as (kind, line); kind: h1, h2, h3, p, bullet, number, quote, row or code. Blank lines are left out
    outside code: paragraphs have their own spacing."""
    out: list[tuple[str, str]] = []
    code = False
    for raw in _BAD.sub("", str(text or "")).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            code = not code
            continue
        if code:
            out.append(("code", line))
            continue
        s = line.strip()
        if not s or re.fullmatch(r"([-*_])( ?\1){2,}", s):           # nothing, or a --- line
            continue
        head = re.match(r"(#{1,6})\s+(.*)", s)
        if head:
            out.append((f"h{min(len(head.group(1)), 3)}", head.group(2).rstrip("#").strip()))
        elif re.match(r"[-*+•]\s+", s):
            out.append(("bullet", re.sub(r"^[-*+•]\s+", "", s)))
        elif re.match(r"\d{1,3}[.)]\s+", s):
            out.append(("number", s))
        elif s.startswith(">"):
            out.append(("quote", s.lstrip(">").strip()))
        elif "|" in s and _RULE.fullmatch(s):                         # a table's |---|---| line
            continue
        elif s.startswith("|") and s.endswith("|") and len(s) > 1:
            out.append(("row", "\t".join(c.strip() for c in s[1:-1].split("|"))))
        else:
            out.append(("p", s))
    return out


def runs(line: str) -> list[tuple[str, str]]:
    """A line as (style, text): "" plain, "b" bold, "i" italic, "c" code. A link keeps its address: "text (url)"."""
    line = _LINK.sub(r"\1 (\2)", line)
    out, at = [], 0
    for m in _INLINE.finditer(line):
        if m.start() > at:
            out.append(("", line[at:m.start()]))
        out.append(("b", m.group(1)) if m.group(1) is not None else ("i", m.group(3)) if m.group(3) is not None
                   else ("c", m.group(4)))
        at = m.end()
    if at < len(line):
        out.append(("", line[at:]))
    return [r for r in out if r[1]]


def _lead(kind: str, line: str) -> str:
    """A list item: its mark, a tab, its words (the hanging indent lines the words up)."""
    if kind == "bullet":
        return "•\t" + line
    if kind == "number":
        m = re.match(r"(\d{1,3}[.)])\s+(.*)", line)
        return f"{m.group(1)}\t{m.group(2)}" if m else line
    return line


# ---------------------------------------------------------------- Word
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PKG = "http://schemas.openxmlformats.org/package/2006"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MONO = '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'


def _w_text(t: str) -> str:
    return "<w:tab/>".join(f'<w:t xml:space="preserve">{escape(x)}</w:t>' if x else "" for x in t.split("\t"))


def _w_par(kind: str, line: str) -> str:
    style = {"h1": "Heading1", "h2": "Heading2", "h3": "Heading3", "quote": "Quote", "code": "Code"}.get(kind)
    ppr = f'<w:pStyle w:val="{style}"/>' if style else ""
    if kind in ("bullet", "number"):
        ppr += '<w:spacing w:after="60"/><w:ind w:left="720" w:hanging="360"/>'
    elif kind == "row":
        ppr += '<w:spacing w:after="60"/>'
    body = ""
    for st, t in [("", line)] if kind == "code" else runs(_lead(kind, line)):
        rpr = {"b": "<w:b/>", "i": "<w:i/>", "c": _MONO}.get(st, "")
        body += f'<w:r>{f"<w:rPr>{rpr}</w:rPr>" if rpr else ""}{_w_text(t)}</w:r>'
    return f'<w:p>{f"<w:pPr>{ppr}</w:pPr>" if ppr else ""}{body}</w:p>'


def _w_style(sid: str, name: str, ppr: str, rpr: str) -> str:
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
            f'<w:next w:val="Normal"/><w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


def docx(text: str) -> bytes:
    """A Word document (A4, Calibri 11) that Word, LibreOffice and Google Docs open; Word opens it in its own
    current mode, not "Compatibility Mode"."""
    body = "".join(_w_par(k, ln) for k, ln in blocks(text)) or "<w:p/>"
    document = (f'{_XML}<w:document xmlns:w="{_W}"><w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1418" w:header="708" w:footer="708" '
                'w:gutter="0"/></w:sectPr></w:body></w:document>')
    head = '<w:keepNext/><w:spacing w:before="{b}" w:after="120"/><w:outlineLvl w:val="{lvl}"/>'
    styles = (f'{_XML}<w:styles xmlns:w="{_W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" '
              'w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
              '</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr>'
              '</w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              + _w_style("Heading1", "heading 1", head.format(b=360, lvl=0), '<w:b/><w:sz w:val="36"/><w:szCs w:val="36"/>')
              + _w_style("Heading2", "heading 2", head.format(b=280, lvl=1), '<w:b/><w:sz w:val="30"/><w:szCs w:val="30"/>')
              + _w_style("Heading3", "heading 3", head.format(b=220, lvl=2), '<w:b/><w:sz w:val="26"/><w:szCs w:val="26"/>')
              + _w_style("Quote", "Quote", '<w:ind w:left="567"/>', '<w:i/><w:color w:val="555555"/>')
              + _w_style("Code", "Code", '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>',
                         _MONO + '<w:sz w:val="20"/><w:szCs w:val="20"/>')
              + "</w:styles>")
    settings = (f'{_XML}<w:settings xmlns:w="{_W}"><w:defaultTabStop w:val="720"/><w:compat><w:compatSetting '
                'w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
                '</w:settings>')
    part = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    types = (f'{_XML}<Types xmlns="{_PKG}/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             f'<Override PartName="/word/document.xml" ContentType="{part}.document.main+xml"/>'
             f'<Override PartName="/word/styles.xml" ContentType="{part}.styles+xml"/>'
             f'<Override PartName="/word/settings.xml" ContentType="{part}.settings+xml"/></Types>')
    rels = (f'{_XML}<Relationships xmlns="{_PKG}/relationships">'
            f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = (f'{_XML}<Relationships xmlns="{_PKG}/relationships">'
                f'<Relationship Id="rId1" Type="{_REL}/styles" Target="styles.xml"/>'
                f'<Relationship Id="rId2" Type="{_REL}/settings" Target="settings.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/settings.xml", settings)
    return buf.getvalue()


# ---------------------------------------------------------------- LibreOffice (OpenDocument)
_NS = {p: f"urn:oasis:names:tc:opendocument:xmlns:{n}" for p, n in (
    ("office", "office:1.0"), ("style", "style:1.0"), ("text", "text:1.0"), ("fo", "xsl-fo-compatible:1.0"))}
_XMLNS = " ".join(f'xmlns:{p}="{u}"' for p, u in _NS.items())


def _o_text(t: str) -> str:
    """Spaces and tabs as OpenDocument keeps them (it joins a run of spaces into one otherwise)."""
    out = []
    for piece in re.split(r"(\t| {2,})", t):
        if piece == "\t":
            out.append("<text:tab/>")
        elif piece.startswith("  "):
            out.append(f'<text:s text:c="{len(piece)}"/>')
        else:
            out.append(escape(piece))
    return "".join(out)


def _o_span(st: str, t: str) -> str:
    name = {"b": "Bold", "i": "Italic", "c": "Code"}.get(st)
    return f'<text:span text:style-name="{name}">{_o_text(t)}</text:span>' if name else _o_text(t)


def _o_par(kind: str, line: str) -> str:
    if kind in ("h1", "h2", "h3"):
        n = kind[1]
        inner = "".join(_o_span(st, t) for st, t in runs(line))
        return f'<text:h text:style-name="Heading_20_{n}" text:outline-level="{n}">{inner}</text:h>'
    style = {"quote": "Quotations", "code": "Preformatted_20_Text", "bullet": "List_20_Item", "number": "List_20_Item",
             "row": "Table_20_Row"}.get(kind, "Standard")
    pieces = [("", line)] if kind == "code" else runs(_lead(kind, line))
    return f'<text:p text:style-name="{style}">{"".join(_o_span(st, t) for st, t in pieces)}</text:p>'


def _o_style(name: str, shown: str, par: str = "", txt: str = "", cls: str = "text", tab: str = "") -> str:
    props = ""
    if par or tab:
        stops = f'<style:tab-stops><style:tab-stop style:position="{tab}"/></style:tab-stops>' if tab else ""
        props = f"<style:paragraph-properties {par}>{stops}</style:paragraph-properties>"
    return (f'<style:style style:name="{name}" style:display-name="{shown}" style:family="paragraph" '
            f'style:parent-style-name="Standard" style:class="{cls}">{props}'
            + (f"<style:text-properties {txt}/>" if txt else "") + "</style:style>")


def odt(text: str) -> bytes:
    """A LibreOffice Writer document (A4) that LibreOffice, Word and Google Docs open."""
    body = "".join(_o_par(k, ln) for k, ln in blocks(text)) or '<text:p text:style-name="Standard"/>'
    mono = 'fo:font-family="\'Liberation Mono\'"'
    content = (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-content {_XMLNS} office:version="1.2">'
               '<office:automatic-styles>'
               '<style:style style:name="Bold" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>'
               '<style:style style:name="Italic" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>'
               f'<style:style style:name="Code" style:family="text"><style:text-properties {mono}/></style:style>'
               f'</office:automatic-styles><office:body><office:text>{body}</office:text></office:body>'
               '</office:document-content>')
    head = 'fo:margin-top="{t}cm" fo:margin-bottom="0.2cm" fo:keep-with-next="always"'
    styles = (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-styles {_XMLNS} office:version="1.2">'
              '<office:styles><style:default-style style:family="paragraph"><style:paragraph-properties '
              'fo:margin-bottom="0.28cm" fo:line-height="115%"/><style:text-properties fo:font-family="Calibri" '
              'fo:font-size="11pt"/></style:default-style>'
              '<style:style style:name="Standard" style:family="paragraph" style:class="text"/>'
              + _o_style("Heading_20_1", "Heading 1", head.format(t="0.6"), 'fo:font-size="18pt" fo:font-weight="bold"', "chapter")
              + _o_style("Heading_20_2", "Heading 2", head.format(t="0.5"), 'fo:font-size="15pt" fo:font-weight="bold"', "chapter")
              + _o_style("Heading_20_3", "Heading 3", head.format(t="0.4"), 'fo:font-size="13pt" fo:font-weight="bold"', "chapter")
              + _o_style("Quotations", "Quotations", 'fo:margin-left="1cm"', 'fo:font-style="italic" fo:color="#555555"')
              + _o_style("Preformatted_20_Text", "Preformatted Text", 'fo:margin-bottom="0cm" fo:line-height="100%"',
                         mono + ' fo:font-size="10pt"', "html")
              + _o_style("List_20_Item", "List Item", 'fo:margin-left="1.27cm" fo:text-indent="-0.635cm" '
                         'fo:margin-bottom="0.1cm"', cls="list", tab="0cm")
              + _o_style("Table_20_Row", "Table Row", 'fo:margin-bottom="0.1cm"')
              + '</office:styles><office:automatic-styles><style:page-layout style:name="A4">'
              '<style:page-layout-properties fo:page-width="21cm" fo:page-height="29.7cm" fo:margin-top="2cm" '
              'fo:margin-bottom="2cm" fo:margin-left="2.5cm" fo:margin-right="2cm"/></style:page-layout>'
              '</office:automatic-styles><office:master-styles><style:master-page style:name="Standard" '
              'style:page-layout-name="A4"/></office:master-styles></office:document-styles>')
    manifest = ('<?xml version="1.0" encoding="UTF-8"?>\n<manifest:manifest xmlns:manifest="urn:oasis:names:tc:'
                'opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                '<manifest:file-entry manifest:full-path="/" manifest:version="1.2" '
                'manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
                '</manifest:manifest>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")   # first and not packed
        z.writestr("META-INF/manifest.xml", manifest, zipfile.ZIP_DEFLATED)
        z.writestr("content.xml", content, zipfile.ZIP_DEFLATED)
        z.writestr("styles.xml", styles, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def build(suffix: str, text: str) -> bytes:
    """The document's bytes for a new .docx or .odt file."""
    return odt(text) if suffix.lower() == ".odt" else docx(text)


# ---------------------------------------------------------------- CSV
def csv_text(text: str, old: bytes | None = None) -> str:
    """A CSV file's text: a new one starts with a byte order mark (Excel then reads it as UTF-8, not as the old
    Windows letters); a rewritten one keeps what the old file had, so a program that reads it isn't surprised."""
    text = str(text or "").lstrip(BOM)
    return BOM + text if old is None or old.startswith(BOM.encode("utf-8")) else text


def excel_marks() -> tuple[str, str]:
    """The column and decimal separators Excel on this computer uses for CSV files: Windows' region settings
    (";" and "," in Ukraine, Germany, France…). Elsewhere LibreOffice asks when it opens one: "," and "."."""
    if sys.platform != "win32":
        return ",", "."
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as k:
            sep, dec = winreg.QueryValueEx(k, "sList")[0], winreg.QueryValueEx(k, "sDecimal")[0]
    except (OSError, ImportError):
        return ",", "."
    return (sep if sep in (",", ";") else ","), (dec if dec in (",", ".") else ".")


def excel_hint() -> str:
    """For the file tools' descriptions: how a .csv must look for Excel on this computer ("" = the usual commas)."""
    sep, dec = excel_marks()
    if sep == ",":
        return ""
    return (f" In a .csv for Excel put '{sep}' between columns" + (" and write decimals with a comma (3,5)"
            if dec == "," else "") + ": Excel on this computer expects that (a program may want commas).")
