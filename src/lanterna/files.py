"""Turns attached files into something a model can read: text for documents, small JPEGs for photos."""
from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024        # bigger files are refused
TEXT_LIMIT = 15000                  # characters of a document sent to the model
IMAGE_SIDE = 1024                   # photos are scaled down to this many pixels on the long side

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".flac", ".webm", ".mpga", ".mpeg", ".aac"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".py", ".js", ".ts", ".java", ".c",
            ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".yml", ".yaml", ".toml",
            ".ini", ".cfg", ".log", ".sql", ".css", ".tex", ".srt"}


class FileError(Exception):
    pass


@dataclass
class Prepared:
    text: str = ""                          # added to the user's message
    images: list[str] = field(default_factory=list)   # data URLs
    names: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)    # long files of which only the parts that fit went


def _image_url(data: bytes) -> str:
    try:
        from PIL import Image, ImageOps
    except ImportError:                       # without Pillow send the photo as it is
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except Exception as e:                    # noqa: BLE001
        raise FileError("this image can't be opened") from e
    im = im.convert("RGB")
    im.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise FileError("PDF support needs the pypdf package") from e
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:60])
    except Exception as e:                    # noqa: BLE001
        raise FileError("this PDF can't be read") from e


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError) as e:
        raise FileError("this Word file can't be read") from e
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


# ------------------------------------------------------------------ office files and books (no extra packages)
DOC_EXT = {".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods", ".odp", ".epub"}
WHOLE_LIMIT = 100_000               # "Whole file": this many characters at most
SCAN_PAGES = 4                      # a scanned PDF: its first pages go as pictures
_MEMBER_MAX = 60 * 1024 * 1024      # one part of an office file, unpacked (guards against zip bombs)


def _zip_read(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > _MEMBER_MAX:
        raise FileError("this file is too big inside")
    return z.read(info)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml(data: bytes):
    import xml.etree.ElementTree as ET
    return ET.fromstring(data)


def _xlsx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(_zip_read(z, "xl/sharedStrings.xml")):
                shared.append("".join(x.text or "" for x in si.iter() if _local(x.tag) == "t"))
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in _xml(_zip_read(z, "xl/_rels/workbook.xml.rels")):
                rels[r.get("Id")] = r.get("Target", "").lstrip("/").removeprefix("xl/")
        sheets = []
        for el in _xml(_zip_read(z, "xl/workbook.xml")).iter():
            if _local(el.tag) == "sheet":
                rid = next((v for k, v in el.attrib.items() if _local(k) == "id"), "")
                sheets.append((el.get("name", "?"), "xl/" + rels.get(rid, "")))
        out = []
        for title, path in sheets:
            if path not in names:
                continue
            out.append(f"## {title}")
            rows = 0
            for row in _xml(_zip_read(z, path)).iter():
                if _local(row.tag) != "row":
                    continue
                cells = []
                for c in row:
                    if _local(c.tag) != "c":
                        continue
                    kind, v = c.get("t", "n"), ""
                    for x in c.iter():
                        if _local(x.tag) == "v":
                            v = x.text or ""
                        elif _local(x.tag) == "t" and kind == "inlineStr":
                            v += x.text or ""
                    if kind == "s" and v.isdigit() and int(v) < len(shared):
                        v = shared[int(v)]
                    elif kind == "b":
                        v = "TRUE" if v == "1" else "FALSE"
                    cells.append(f"{c.get('r', '')}={v}" if v else "")
                line = "\t".join(x for x in cells if x)
                if line:
                    out.append(line)
                    rows += 1
                if rows >= 5000:
                    out.append("[…more rows]")
                    break
        return "\n".join(out)


def _pptx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        out = []
        for i, n in enumerate(slides, 1):
            out.append(f"## Slide {i}")
            for p in _xml(_zip_read(z, n)).iter():
                if _local(p.tag) == "p":
                    line = "".join(x.text or "" for x in p.iter() if _local(x.tag) == "t").strip()
                    if line:
                        out.append(line)
        return "\n".join(out)


def _odf_text(data: bytes) -> str:
    """OpenDocument text, spreadsheet or presentation (LibreOffice): paragraphs, headings and table rows."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = _xml(_zip_read(z, "content.xml"))
    out = []

    def walk(el) -> None:
        tag = _local(el.tag)
        if tag in ("p", "h"):
            line = "".join(el.itertext()).strip()
            if line:
                out.append(line)
            return
        if tag == "table-row":
            cells = ["".join(c.itertext()).strip() for c in el if _local(c.tag) == "table-cell"]
            line = "\t".join(x for x in cells if x)
            if line:
                out.append(line)
            return
        if tag == "page":
            out.append(f"## {el.get('{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}name', '')}".rstrip())
        for c in el:
            walk(c)
    walk(root)
    return "\n".join(out)


def _html_text(markup: str) -> str:
    import html as H
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr)>", "\n", markup)
    text = H.unescape(re.sub(r"<[^>]+>", "", markup))
    return "\n".join(" ".join(ln.split()) for ln in text.splitlines() if ln.strip())


def _epub_text(data: bytes) -> str:
    import posixpath
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        cont = _xml(_zip_read(z, "META-INF/container.xml"))
        opf = next((el.get("full-path") for el in cont.iter() if _local(el.tag) == "rootfile"), "")
        root, base = _xml(_zip_read(z, opf)), posixpath.dirname(opf)
        items = {el.get("id"): el.get("href", "") for el in root.iter() if _local(el.tag) == "item"}
        order = [items.get(el.get("idref"), "") for el in root.iter() if _local(el.tag) == "itemref"]
        out, size = [], 0
        names = set(z.namelist())
        for href in order:
            path = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
            if path not in names:
                continue
            part = _html_text(_zip_read(z, path).decode("utf-8", "replace"))
            out.append(part)
            size += len(part)
            if size > WHOLE_LIMIT * 2:
                break
        return "\n\n".join(x for x in out if x)


def scan_pages(data: bytes, pages: int = SCAN_PAGES) -> tuple[list[str], int]:
    """A PDF without text (a scan): its first pages as pictures, and how many pages it has.
    Needs pypdfium2 (BSD/Apache, part of Lanterna's install); ([], 0) without it."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return [], 0
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:                    # noqa: BLE001
        raise FileError("this PDF can't be read") from e
    try:
        total, urls = len(pdf), []
        for i in range(min(pages, total)):
            page = pdf[i]
            w, h = page.get_size()
            im = page.render(scale=min(2.0, IMAGE_SIDE * 1.6 / max(w, h, 1))).to_pil()
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "PNG")
            urls.append(_image_url(buf.getvalue()))
            page.close()
        return urls, total
    finally:
        pdf.close()


def doc_text(name: str, data: bytes) -> str:
    """The plain text of an office file, a PDF with text, or an e-book ("" for a scanned PDF)."""
    ext = Path(name).suffix.lower()
    try:
        if ext == ".pdf" or data[:5] == b"%PDF-":
            return _pdf_text(data)
        if ext == ".docx":
            return _docx_text(data)
        if ext in (".xlsx", ".xlsm"):
            return _xlsx_text(data)
        if ext == ".pptx":
            return _pptx_text(data)
        if ext in (".odt", ".ods", ".odp"):
            return _odf_text(data)
        if ext == ".epub":
            return _epub_text(data)
    except FileError:
        raise
    except Exception as e:                    # noqa: BLE001  broken zip, odd XML…
        raise FileError(f"{name} can't be read") from e
    raise FileError(f"{name}: this file type is not supported yet")


def is_audio(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXT


def audio_block(name: str, text: str) -> str:
    text = (text or "").strip()
    cut = len(text) > TEXT_LIMIT
    return (f"[Audio: {name}, turned into text]\n```\n{text[:TEXT_LIMIT]}\n```" +
            ("\n[…text cut, too long]" if cut else ""))


def read_upload(f: dict) -> tuple[str, bytes]:
    """(name, bytes) of one attached file: {"name", "data": base64} from the window or {"path"} from the terminal."""
    if f.get("path"):
        p = Path(str(f["path"])).expanduser()
        if not p.is_file():
            raise FileError(f"file not found: {p}")
        if p.stat().st_size > MAX_BYTES:
            raise FileError(f"{p.name} is bigger than 20 MB")
        return p.name, p.read_bytes()
    name = Path(str(f.get("name") or "file")).name
    try:
        return name, base64.b64decode(str(f.get("data") or ""), validate=False)
    except ValueError as e:
        raise FileError(f"{name}: broken upload") from e


def prepare_one(name: str, data: bytes) -> tuple[str, str | None]:
    """Returns (text block, image data URL or None). For reading files in folders: a scan is not looked at."""
    block, images, _parts = prepare_full(name, data, scans=False)
    return block, images[0] if images else None


def prepare_full(name: str, data: bytes, focus: str = "", whole: bool = False,
                 scans: bool = True) -> tuple[str, list[str], bool]:
    """(text block, image data URLs, only parts went). A long file sends only the parts that fit the question
    (`focus`) unless `whole`; a scanned PDF sends its first pages as pictures."""
    if len(data) > MAX_BYTES:
        raise FileError(f"{name} is bigger than 20 MB")
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT or data[:4] in (b"\x89PNG", b"GIF8") or data[:3] == b"\xff\xd8\xff":
        return f"[Photo: {name}]", [_image_url(data)], False
    if ext in DOC_EXT or data[:5] == b"%PDF-":
        text = doc_text(name, data)
        if not text.strip() and (ext == ".pdf" or data[:5] == b"%PDF-"):
            urls, total = scan_pages(data) if scans else ([], 0)
            if not urls:
                raise FileError(f"{name} has no text layer (it is a scan). Send a photo of the page instead")
            more = f" of {total}" if total > len(urls) else ""
            return (f"[Scanned PDF: {name} — no text layer, so pages 1-{len(urls)}{more} are attached as pictures]",
                    urls, False)
    elif ext in TEXT_EXT or not ext:
        text = data.decode("utf-8", "replace")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise FileError(f"{name}: this file type is not supported yet") from e
    text = text.replace("\r\n", "\n").strip()
    limit = WHOLE_LIMIT if whole else TEXT_LIMIT
    if len(text) > limit and focus.strip() and not whole:
        from .tools import focus_excerpt
        part, cut = focus_excerpt(text, focus, TEXT_LIMIT)
        if cut and "[…]" in part:
            return (f"[File: {name} — only the parts that fit the question ({len(part)} of {len(text)} characters); "
                    f"the user can send the whole file]\n```\n{part}\n```"), [], True
    cut = len(text) > limit
    return f"[File: {name}]\n```\n{text[:limit]}\n```" + ("\n[…file cut, too long]" if cut else ""), [], False


def prepare(files: list[dict], focus: str = "") -> Prepared:
    """files: [{"name": ..., "data": base64, "whole": bool}] from the window app, or [{"path": ...}] from the
    terminal. focus: the question, so a long file sends the parts that fit it."""
    out = Prepared()
    blocks = []
    for f in files or []:
        name, data = read_upload(f)
        if len(data) > MAX_BYTES:
            raise FileError(f"{name} is bigger than 20 MB")
        block, images, parts = prepare_full(name, data, focus, bool(f.get("whole")))
        blocks.append(block)
        out.names.append(name)
        out.images += images
        if parts:
            out.parts.append(name)
    out.text = "\n\n".join(blocks)
    return out
