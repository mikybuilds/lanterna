"""Round 136 (1.1.8b6): real Word and LibreOffice documents, and CSV files Excel reads.

- Asked for a .docx or .odt file (in the working folder, or on the desktop and in the user's folders), Lanterna makes
  a real document: the Markdown it writes becomes headings, lists, bold, italic, code, quotes; a table's rows become
  lines with tabs. Word, LibreOffice and Google Docs open it; Word doesn't show "Compatibility Mode". The card says
  it becomes a document, so the # and ** in its preview don't worry anyone.
- An existing document is still never changed (its formatting would be lost): Lanterna offers a new name.
- A new .csv starts with the mark Excel needs to read Cyrillic and other letters; rewriting one keeps what the old
  file had; adding to the end never puts the mark in the middle, and no longer leaves an empty row. Reading one
  back leaves the mark out.
- On Windows the model is told which column and decimal separators Excel on this computer expects (";" and "," in
  Ukraine, Germany, France…), so a table opens in columns, not all in the first one.
- Reading a Word file keeps "&", "<", tabs and line breaks; a LibreOffice file keeps tabs and a code line's indent.
"""
import io
import sys
import types
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from lanterna import docmake, gui, i18n, pcfiles
from lanterna.app import card_text
from lanterna.files import prepare_one
from lanterna.workspace import Actions, Workspace, WorkError, folder_tools

UI = Path(gui.__file__).parent / "ui"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
BOM = b"\xef\xbb\xbf"

SAMPLE = """# Звіт за жовтень
Вступ з **жирним**, *курсивом*, `кодом` і [посиланням](https://example.org/a).

## Список справ
- перший пункт
- R&D <важливо>
1. раз
2) два
> цитата

| Ім'я | Вік |
|---|---|
| Анна | 30 |

```
def f():
    return 1
```
---
### Кінець
"""


def _parts(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def _paragraphs(document: bytes) -> list:
    """(style, text) of each paragraph of word/document.xml; a tab is "\t"."""
    out = []
    for p in ET.fromstring(document).iter(W + "p"):
        st = p.find(f"{W}pPr/{W}pStyle")
        words = "".join((e.text or "") if e.tag == W + "t" else "\t" for e in p.iter() if e.tag in (W + "t", W + "tab"))
        out.append((st.get(W + "val") if st is not None else "", words))
    return out


def _look(document: bytes, words: str) -> set:
    """How the run with these words looks: b (bold), i (italic), mono (code)."""
    for r in ET.fromstring(document).iter(W + "r"):
        if "".join(t.text or "" for t in r.iter(W + "t")) == words:
            pr = r.find(W + "rPr")
            got = {c.tag[len(W):] for c in pr} if pr is not None else set()
            return {x for x, tag in (("b", "b"), ("i", "i"), ("mono", "rFonts")) if tag in got}
    raise AssertionError(words)


# ---------------------------------------------------------------- the documents
def test_a_word_document_is_real():
    parts = _parts(docmake.docx(SAMPLE))
    assert set(parts) == {"[Content_Types].xml", "_rels/.rels", "word/_rels/document.xml.rels", "word/document.xml",
                          "word/styles.xml", "word/settings.xml"}
    for x in parts.values():
        ET.fromstring(x)                                                 # every part is well-formed XML
    assert "wordprocessingml.document.main+xml" in parts["[Content_Types].xml"].decode()
    assert b'w:name="compatibilityMode"' in parts["word/settings.xml"] and b'w:val="15"' in parts["word/settings.xml"]
    paras = _paragraphs(parts["word/document.xml"])
    assert paras[0] == ("Heading1", "Звіт за жовтень")
    assert ("Heading2", "Список справ") in paras and ("Heading3", "Кінець") in paras
    assert ("", "Вступ з жирним, курсивом, кодом і посиланням (https://example.org/a).") in paras
    assert ("", "•\tперший пункт") in paras and ("", "•\tR&D <важливо>") in paras
    assert ("", "1.\tраз") in paras and ("", "2)\tдва") in paras
    assert ("Quote", "цитата") in paras and ("", "Ім'я\tВік") in paras and ("", "Анна\t30") in paras
    assert ("Code", "def f():") in paras and ("Code", "    return 1") in paras
    assert not any(m in w for _, w in paras for m in ("|", "---", "**", "```", "# "))    # no Markdown marks are left
    doc = parts["word/document.xml"]
    assert _look(doc, "жирним") == {"b"} and _look(doc, "курсивом") == {"i"} and _look(doc, "кодом") == {"mono"}
    styles = parts["word/styles.xml"].decode()
    assert '<w:name w:val="heading 1"/>' in styles and '<w:outlineLvl w:val="0"/>' in styles     # Word's own headings
    assert 'w:hanging="360"' in doc.decode()                            # a list item's words line up after its mark


def test_a_libreoffice_document_is_real():
    data = docmake.odt(SAMPLE)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED     # what ODF asks for
        assert z.read("mimetype") == b"application/vnd.oasis.opendocument.text"
        assert b'manifest:full-path="content.xml"' in z.read("META-INF/manifest.xml")
        ET.fromstring(z.read("styles.xml"))
        raw = z.read("content.xml")
    content = ET.fromstring(raw)
    heads = [(h.get(TEXT + "outline-level"), "".join(h.itertext())) for h in content.iter(TEXT + "h")]
    assert heads == [("1", "Звіт за жовтень"), ("2", "Список справ"), ("3", "Кінець")]
    styles = {p.get(TEXT + "style-name") for p in content.iter(TEXT + "p")}
    assert {"Standard", "List_20_Item", "Quotations", "Preformatted_20_Text", "Table_20_Row"} <= styles
    raw = raw.decode()
    assert '<text:span text:style-name="Bold">жирним</text:span>' in raw
    assert '<text:span text:style-name="Italic">курсивом</text:span>' in raw
    assert '<text:s text:c="4"/>return 1' in raw and "•<text:tab/>перший пункт" in raw and "R&amp;D &lt;важливо&gt;" in raw


@pytest.mark.parametrize("ext", [".docx", ".odt"])
def test_lanterna_reads_back_what_it_made(ext):
    text = prepare_one("report" + ext, docmake.build(ext, SAMPLE))[0]
    for line in ("Звіт за жовтень", "•\tперший пункт", "•\tR&D <важливо>", "Ім'я\tВік", "def f():\n    return 1",
                 "Кінець"):
        assert line in text, (ext, line)


def test_odd_text_still_makes_a_document_that_opens():
    odd = "a\x00b\x07c\x1b[31m\U0000FFFE d \U0000DC80 e <tag> & \"q\""      # control bytes, a non-character, half a letter
    for ext in (".docx", ".odt"):
        data = docmake.build(ext, odd)
        for name, x in _parts(data).items():
            if name.endswith(".xml"):
                ET.fromstring(x)
        assert 'abc[31m d  e <tag> & "q"' in prepare_one("x" + ext, data)[0], ext
        empty = docmake.build(ext, "")
        assert zipfile.ZipFile(io.BytesIO(empty)).testzip() is None
    assert docmake.blocks("") == [] and docmake.blocks(None) == []


def test_markdown_marks_become_formatting_not_symbols():
    assert docmake.runs("a **b** *c* `d`") == [("", "a "), ("b", "b"), ("", " "), ("i", "c"), ("", " "), ("c", "d")]
    for plain in ("2*3*4 = 24", "file_name_here", "__init__.py", "a * b * c", "5 * 3"):
        assert docmake.runs(plain) == [("", plain)], plain
    assert docmake.runs("see [the docs](https://example.org/x)") == [("", "see the docs (https://example.org/x)")]
    assert docmake.blocks("***\n- - -\n___") == []                         # lines that only draw a rule
    assert docmake.blocks("* one\n+ two\n• three") == [("bullet", "one"), ("bullet", "two"), ("bullet", "three")]
    assert docmake.blocks("#hashtag") == [("p", "#hashtag")] and docmake.blocks("#### Small") == [("h3", "Small")]
    assert docmake.blocks("```\n\n  x\n") == [("code", ""), ("code", "  x"), ("code", "")]   # code keeps its lines


# ---------------------------------------------------------------- the working folder and the user's folders
@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    acts, cards = Actions(), []
    acts.bind(cards, 7)
    w = Workspace(lambda: str(root), acts)
    w.cards = cards
    return w


def test_the_working_folder_makes_real_documents(ws):
    for name, kind in (("Звіт.docx", "docx"), ("notes.ODT", "odt")):
        ws.propose_write(name, SAMPLE, "replace")                            # not there yet: made new
        card = ws.cards[-1]
        assert card["kind"] == "write_new" and card["details"]["doc"] == kind
        assert card["details"]["preview"].startswith("# Звіт за жовтень")
        a = ws.actions.confirm(card["id"])
        assert a.state == "done" and a.undo["type"] == "trash"                 # Undo moves it to the Recycle Bin
        data = (ws.root() / name).read_bytes()
        assert data.startswith(b"PK") and "Звіт за жовтень" in prepare_one(name, data)[0]
    assert "•\tперший пункт" in ws.read("Звіт.docx")                         # folder_read reads it back


def test_an_existing_document_is_never_changed(ws):
    old = ws.root() / "report.docx"
    old.write_bytes(docmake.docx("# Old"))
    before = old.read_bytes()
    for mode in ("replace", "append"):
        with pytest.raises(WorkError) as e:
            ws.propose_write("report.docx", "# New", mode)
        assert "Nothing was changed" in str(e.value) and "report (2).docx" in str(e.value)
    with pytest.raises(WorkError) as e:
        ws.propose_write("report.docx", "# New", "create")
    assert "report (2).docx" in str(e.value) and "replace" not in str(e.value)
    assert not ws.cards and old.read_bytes() == before
    ws.propose_write("later.odt", "# Mine")                                   # it appeared between the card and Confirm
    (ws.root() / "later.odt").write_bytes(b"someone else's")
    assert ws.actions.confirm(ws.cards[-1]["id"]).state == "failed"
    assert (ws.root() / "later.odt").read_bytes() == b"someone else's"


def test_what_it_offers_instead_of_excel_or_pdf(ws):
    with pytest.raises(WorkError) as e:
        ws.propose_write("budget.xlsx", "Food,100")
    assert "'budget.csv'" in str(e.value) and "'budget.md'" in str(e.value)
    with pytest.raises(WorkError) as e:
        ws.propose_write("letter.pdf", "Dear Anna")
    assert "'letter.docx'" in str(e.value) and "'letter.md'" in str(e.value)
    assert not ws.cards


def _places(tmp_path):
    home = {p: tmp_path / p.title() for p in pcfiles.PLACES}
    for f in home.values():
        f.mkdir()
    acts, cards = Actions(), []
    acts.bind(cards, 3)
    return home, acts, cards, pcfiles.Places(acts, folders=lambda: home, opener=lambda p: None)


def test_the_desktop_gets_real_documents_too(tmp_path):
    home, acts, cards, pl = _places(tmp_path)
    pl.propose_write("desktop", "Лист.docx", "Шановна Анно,\n\n**дякую** за допомогу.")
    assert cards[-1]["kind"] == "pc_write" and cards[-1]["details"]["doc"] == "docx"
    assert acts.confirm(cards[-1]["id"]).state == "done"
    data = (home["desktop"] / "Лист.docx").read_bytes()
    assert "Шановна Анно," in prepare_one("Лист.docx", data)[0]
    assert b"<w:b/>" in _parts(data)["word/document.xml"]
    with pytest.raises(WorkError):
        pl.propose_write("desktop", "Лист.docx", "again")                     # never over a file
    pl.propose_write("documents", "Таблиця.csv", "Ім'я;Вік\nАнна;30\n")
    assert "doc" not in cards[-1]["details"]
    acts.confirm(cards[-1]["id"])
    raw = (home["documents"] / "Таблиця.csv").read_bytes()
    assert raw == BOM + "Ім'я;Вік\nАнна;30\n".encode("utf-8")
    assert pl.read("documents", "Таблиця.csv").count("Ім'я;Вік") == 1 and docmake.BOM not in pl.read("documents", "Таблиця.csv")


# ---------------------------------------------------------------- CSV files for Excel
def test_csv_files_excel_reads_with_their_letters(ws):
    f = ws.root() / "people.csv"
    ws.propose_write("people.csv", docmake.BOM + "Ім'я;Місто\nАнна;Київ")      # the model's own mark isn't doubled
    ws.actions.confirm(ws.cards[-1]["id"])
    assert f.read_bytes() == BOM + "Ім'я;Місто\nАнна;Київ".encode()
    ws.propose_write("people.csv", docmake.BOM + "Богдан;Львів\n", "append")    # not in the middle
    ws.actions.confirm(ws.cards[-1]["id"])
    assert f.read_bytes() == BOM + "Ім'я;Місто\nАнна;Київ\nБогдан;Львів\n".encode()
    ws.propose_write("people.csv", "Олена;Одеса", "append")                    # it ends with a new line: no empty row
    ws.actions.confirm(ws.cards[-1]["id"])
    assert f.read_text(encoding="utf-8") == docmake.BOM + "Ім'я;Місто\nАнна;Київ\nБогдан;Львів\nОлена;Одеса"
    assert docmake.BOM not in ws.read("people.csv")                             # reading it back leaves the mark out
    ws.propose_write("people.csv", "a;b", "replace")
    ws.actions.confirm(ws.cards[-1]["id"])
    assert f.read_bytes() == BOM + b"a;b"
    plain = ws.root() / "for_a_program.csv"
    plain.write_bytes(b"id,name\n1,x\n")                                       # made without the mark: stays so
    ws.propose_write("for_a_program.csv", docmake.BOM + "id,name\n2,y\n", "replace")
    ws.actions.confirm(ws.cards[-1]["id"])
    assert plain.read_bytes() == b"id,name\n2,y\n"
    ws.propose_write("notes.txt", "Привіт")                                     # other text files: no mark
    ws.actions.confirm(ws.cards[-1]["id"])
    assert (ws.root() / "notes.txt").read_bytes() == "Привіт".encode()
    assert prepare_one("people.csv", f.read_bytes())[0] == "[File: people.csv]\n```\na;b\n```"   # an attached one too


class _Key:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _registry(values: dict):
    return types.SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=lambda *a: _Key(),
                                 QueryValueEx=lambda k, name: (values[name], 1))


def test_the_model_learns_what_excel_on_this_computer_expects(monkeypatch, ws, tmp_path):
    monkeypatch.setattr(docmake.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _registry({"sList": ";", "sDecimal": ","}))     # Ukraine, Germany…
    assert docmake.excel_marks() == (";", ",")
    hint = docmake.excel_hint()
    assert "';' between columns" in hint and "(3,5)" in hint
    write = next(t for t in folder_tools(ws) if t.name == "folder_write")
    pc = next(t for t in pcfiles.place_tools(_places(tmp_path)[3]) if t.name == "pc_write")
    for tool in (write, pc):
        assert hint in tool.description and ".docx / .odt" in tool.description and "Markdown" in tool.description
    monkeypatch.setitem(sys.modules, "winreg", _registry({"sList": ",", "sDecimal": "."}))     # the USA, the UK…
    assert docmake.excel_hint() == ""
    monkeypatch.setitem(sys.modules, "winreg", _registry({"sList": "|||", "sDecimal": "?"}))   # something odd
    assert docmake.excel_marks() == (",", ".")

    def broken(*a):
        raise OSError("no key")
    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=broken))
    assert docmake.excel_marks() == (",", ".")
    monkeypatch.setattr(docmake.sys, "platform", "linux")                      # LibreOffice asks when it opens one
    assert docmake.excel_hint() == ""


# ---------------------------------------------------------------- reading other people's documents
def test_reading_a_word_file_keeps_ampersands_tabs_and_breaks():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>R&amp;D &lt;2025&gt;</w:t>'
                   '<w:tab/><w:t>Q4</w:t><w:br/><w:t>next</w:t></w:r></w:p><w:p><w:pPr><w:tabs><w:tab w:val="left" '
                   'w:pos="720"/></w:tabs></w:pPr><w:r><w:t>Done</w:t></w:r></w:p></w:body></w:document>')
    assert "R&D <2025>\tQ4\nnext\nDone" in prepare_one("old.docx", buf.getvalue())[0]


def test_reading_a_libreoffice_file_keeps_tabs_and_indents():
    content = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
               '<text:p>\n   Name<text:tab/>Age\n</text:p>'
               '<text:p><text:s text:c="4"/>return 1</text:p>'
               '<text:p>one<text:line-break/>two <text:span>three</text:span></text:p>'
               '<text:p><text:s text:c="lots"/>x</text:p>'
               '</office:text></office:body></office:document-content>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", content)
    assert "Name\tAge\n    return 1\none\ntwo three\n x" in prepare_one("old.odt", buf.getvalue())[0]


# ---------------------------------------------------------------- the card
def test_the_card_says_it_becomes_a_document():
    assert card_text("write_new", {"path": "a.docx", "doc": "docx"}, "uk").startswith("документ Word (заголовки")
    assert card_text("pc_write", {"path": "a.odt", "doc": "odt"}, "en").startswith("a LibreOffice document")
    assert card_text("write_new", {"path": "a.txt"}, "en") == ""
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'if (d.doc) meta.push(d.doc === "odt" ? t("a LibreOffice document (headings, lists and bold become real formatting)")' in js
    for s in ("a Word document (headings, lists and bold become real formatting)",
              "a LibreOffice document (headings, lists and bold become real formatting)"):
        assert set(i18n._T[s]) == {"uk", "it"}, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s), (lang, s)
