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
    """Returns (text block, image data URL or None)."""
    if len(data) > MAX_BYTES:
        raise FileError(f"{name} is bigger than 20 MB")
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT or data[:4] in (b"\x89PNG", b"GIF8") or data[:3] == b"\xff\xd8\xff":
        return f"[Photo: {name}]", _image_url(data)
    if ext == ".pdf" or data[:5] == b"%PDF-":
        text = _pdf_text(data)
        if not text.strip():
            raise FileError(f"{name} has no text layer (it is a scan). Send a photo of the page instead")
    elif ext == ".docx":
        text = _docx_text(data)
    elif ext in TEXT_EXT or not ext:
        text = data.decode("utf-8", "replace")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise FileError(f"{name}: this file type is not supported yet") from e
    text = text.replace("\r\n", "\n").strip()
    cut = len(text) > TEXT_LIMIT
    return f"[File: {name}]\n```\n{text[:TEXT_LIMIT]}\n```" + ("\n[…file cut, too long]" if cut else ""), None


def prepare(files: list[dict]) -> Prepared:
    """files: [{"name": ..., "data": base64}] from the window app, or [{"path": ...}] from the terminal."""
    out = Prepared()
    blocks = []
    for f in files or []:
        name, data = read_upload(f)
        if len(data) > MAX_BYTES:
            raise FileError(f"{name} is bigger than 20 MB")
        block, image = prepare_one(name, data)
        blocks.append(block)
        out.names.append(name)
        if image:
            out.images.append(image)
    out.text = "\n\n".join(blocks)
    return out
