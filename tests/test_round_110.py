"""Round 110: long files send the parts that fit the question (or the whole file on request); scanned PDFs go as
pictures; spreadsheets, slides, OpenDocument files and e-books are read."""
import base64
import io
import zipfile

import pytest

from lanterna import files, sent


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _zip(parts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in parts.items():
            z.writestr(k, v)
    return buf.getvalue()


NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def test_xlsx_rows_with_shared_strings():
    data = _zip({
        "xl/workbook.xml": f'<workbook {NS}><sheets><sheet name="Бюджет" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst {NS}><si><t>Хліб</t></si><si><r><t>Мо</t></r><r><t>локо</t></r></si></sst>',
        "xl/worksheets/sheet1.xml": f'<worksheet {NS}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>32.5</v></c></row>'
                                    '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>48</v></c><c r="C2" t="b"><v>1</v></c></row>'
                                    '<row r="3"><c r="A3" t="inlineStr"><is><t>Разом</t></is></c></row></sheetData></worksheet>'})
    text = files.doc_text("бюджет.xlsx", data)
    assert text.splitlines() == ["## Бюджет", "A1=Хліб\tB1=32.5", "A2=Молоко\tB2=48\tC2=TRUE", "A3=Разом"]


def test_pptx_slides_in_order():
    def slide(t):
        return ('<p:sld xmlns:p="p" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>'
                + t + '</a:t></a:r></a:p></p:sld>')
    data = _zip({"ppt/slides/slide10.xml": slide("Десятий"), "ppt/slides/slide2.xml": slide("Другий"),
                 "ppt/slides/slide1.xml": slide("Перший")})
    assert files.doc_text("a.pptx", data).splitlines() == ["## Slide 1", "Перший", "## Slide 2", "Другий", "## Slide 3", "Десятий"]


def test_odt_and_ods():
    office = 'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"'
    odt = _zip({"content.xml": f'<office:document-content {office}><office:body><office:text><text:h>Розділ</text:h>'
                               '<text:p>Перший <text:span>абзац</text:span>.</text:p></office:text></office:body></office:document-content>'})
    assert files.doc_text("a.odt", odt).splitlines() == ["Розділ", "Перший абзац."]
    ods = _zip({"content.xml": f'<office:document-content {office}><office:body><office:spreadsheet><table:table>'
                               '<table:table-row><table:table-cell><text:p>a</text:p></table:table-cell><table:table-cell><text:p>1</text:p></table:table-cell></table:table-row>'
                               '</table:table></office:spreadsheet></office:body></office:document-content>'})
    assert files.doc_text("a.ods", ods) == "a\t1"


def test_epub_follows_the_reading_order():
    data = _zip({
        "META-INF/container.xml": '<container><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>',
        "OEBPS/book.opf": '<package><manifest><item id="c2" href="ch2.xhtml"/><item id="c1" href="ch1.xhtml"/></manifest>'
                          '<spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>',
        "OEBPS/ch1.xhtml": "<html><head><style>p{}</style></head><body><h1>Глава 1</h1><p>Жили&nbsp;були дід і баба.</p></body></html>",
        "OEBPS/ch2.xhtml": "<html><body><p>Глава 2</p><p>Кінець.</p></body></html>"})
    assert files.doc_text("казка.epub", data).split() == "Глава 1 Жили були дід і баба. Глава 2 Кінець.".split()


def test_broken_office_file_is_a_clear_error():
    with pytest.raises(files.FileError, match="can't be read"):
        files.doc_text("a.xlsx", b"not a zip")


def test_scanned_pdf_goes_as_pictures():
    pytest.importorskip("pypdfium2")
    from PIL import Image
    pages = [Image.new("RGB", (600, 800), c) for c in ("white", "gray", "white", "gray", "white")]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:])           # pictures only, no text layer
    block, images, parts = files.prepare_full("скан.pdf", buf.getvalue())
    assert "Scanned PDF: скан.pdf" in block and "pages 1-4 of 5" in block
    assert len(images) == files.SCAN_PAGES and all(i.startswith("data:image/jpeg;base64,") for i in images)
    p = files.prepare([{"name": "скан.pdf", "data": _b64(buf.getvalue())}])
    assert len(p.images) == 4
    # reading a folder never sends pictures of a scan
    with pytest.raises(files.FileError, match="no text layer"):
        files.prepare_one("скан.pdf", buf.getvalue())


def test_a_long_file_sends_the_parts_that_fit():
    filler = "\n".join(f"Рядок {i}: звичайний текст про погоду і новини." for i in range(900))
    text = filler[:20000] + "\nГарантія на пральну машину триває 24 місяці з дня покупки.\n" + filler[20000:]
    data = text.encode()
    p = files.prepare([{"name": "інструкція.txt", "data": _b64(data)}], focus="Скільки триває гарантія на пральну машину?")
    assert p.parts == ["інструкція.txt"] and "24 місяці" in p.text and "only the parts that fit the question" in p.text
    assert len(p.text) < files.TEXT_LIMIT + 400
    whole = files.prepare([{"name": "інструкція.txt", "data": _b64(data), "whole": True}], focus="гарантія")
    assert whole.parts == [] and "24 місяці" in whole.text and len(whole.text) > len(text)
    plain = files.prepare([{"name": "інструкція.txt", "data": _b64(data)}])        # no question: the start, as before
    assert "file cut" in plain.text and plain.parts == []


def test_the_note_says_only_parts_went():
    rows = sent.build("M", False, 0, False, 0, ["a.txt"], 0, [("currency", "{}")], parts=["a.txt"])
    assert {"t": "Only the parts of {names} that fit your question", "v": {"names": "a.txt"}} in rows
    assert {"t": "Exchange rates from the National Bank of Ukraine (nothing about you)", "v": {}} in rows


def test_folders_read_office_files_too(tmp_path):
    from lanterna.files import DOC_EXT
    assert {".xlsx", ".pptx", ".odt", ".epub"} <= DOC_EXT
    odt = _zip({"content.xml": '<d xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><text:p>Привіт з ODT</text:p></d>'})
    assert "Привіт з ODT" in files.prepare_one("a.odt", odt)[0]
