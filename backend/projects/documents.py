"""Validated text extraction for intent documents (txt / md / pdf / docx).

Nothing here trusts a file extension or the client's content type: the file *signature* decides the
format and must agree with the extension. Nothing is executed or rendered; DOCX is read as a bounded zip of
XML parts with the standard library, and PDF text is read from the page content streams with a small
bounded parser (no new dependency). Anything that cannot be read becomes an explicit
``ExtractionError`` - an empty or unreadable document is never turned into text.

Limitation (reported, not hidden): the PDF reader only decodes text drawn with simple fonts. PDFs that use
embedded CID fonts, are scanned images, or are encrypted yield an extraction failure; use DOCX/Markdown/TXT
for those.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_EXTRACTED_CHARS = 200_000
MAX_ZIP_MEMBER_BYTES = 8 * 1024 * 1024  # decompressed size cap (zip-bomb guard)
MAX_PDF_PAGES = 200

#: extension -> (canonical format, accepted client content types)
SUPPORTED: dict[str, tuple[str, frozenset[str]]] = {
    ".txt": ("text", frozenset({"text/plain", "application/octet-stream"})),
    ".md": ("markdown", frozenset({"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"})),
    ".markdown": ("markdown", frozenset({"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"})),
    ".pdf": ("pdf", frozenset({"application/pdf", "application/octet-stream"})),
    ".docx": (
        "docx",
        frozenset({
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        }),
    ),
}
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(Exception):
    """A document cannot be accepted (type, size, signature)."""

    code = "invalid_document"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ExtractionError(DocumentError):
    code = "extraction_failed"


@dataclass(frozen=True)
class ExtractedDocument:
    format: str
    text: str
    content_type: str


def _extension(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def safe_filename(filename: str) -> str:
    """Display name only (never used as a path): basename, control characters removed, bounded."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:200] or "document"


def validate_upload(filename: str, content_type: str | None, data: bytes) -> str:
    """Return the canonical format after validating size, extension, content type and file signature."""
    ext = _extension(filename)
    if ext not in SUPPORTED:
        raise DocumentError("Unsupported file type", {"supported": sorted(SUPPORTED), "extension": ext or None})
    fmt, accepted = SUPPORTED[ext]
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentError("The file is too large", {"max_bytes": MAX_DOCUMENT_BYTES})
    if len(data) == 0:
        raise DocumentError("The file is empty")
    declared = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if declared not in accepted:
        raise DocumentError("The content type does not match the file type", {"content_type": declared, "accepted": sorted(accepted)})
    if fmt == "pdf" and not data.lstrip()[:5].startswith(b"%PDF-"):
        raise DocumentError("The file is not a PDF (signature mismatch)")
    if fmt == "docx" and not data.startswith(b"PK\x03\x04"):
        raise DocumentError("The file is not a DOCX (signature mismatch)")
    is_binary = b"\x00" in data[:8192] or data.startswith((b"%PDF-", b"PK\x03\x04", b"\x7fELF", b"MZ"))
    if fmt in ("text", "markdown") and is_binary:
        raise DocumentError("The file is not plain text (binary content detected)")
    return fmt


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("The text file is not valid UTF-8")


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise ExtractionError("The file is not a Word document (no word/document.xml)") from exc
            if info.file_size > MAX_ZIP_MEMBER_BYTES:
                raise ExtractionError("The document content is too large")
            xml = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise ExtractionError("The DOCX archive is corrupt") from exc
    if b"<!DOCTYPE" in xml[:2048].upper() or b"<!ENTITY" in xml[:8192].upper():
        raise ExtractionError("The document uses XML entity declarations, which are not accepted")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ExtractionError("The document XML is malformed") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_W_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_W_NS}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W_NS}tab":
                parts.append("\t")
            elif node.tag in (f"{_W_NS}br", f"{_W_NS}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _pdf_text(data: bytes) -> str:
    """Multi-page text extraction with pypdf. Every failure mode is an explicit ``ExtractionError``.

    OCR is NOT supported: a scanned / image-only PDF is reported as such and never turned into text.
    """
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        encrypted = reader.is_encrypted
        page_count = len(reader.pages) if not encrypted else 0
    except (PyPdfError, ValueError, KeyError, TypeError, OSError, RecursionError, AssertionError, NotImplementedError) as exc:
        raise ExtractionError("The PDF is malformed or unreadable") from exc
    if encrypted:
        raise ExtractionError("The PDF is encrypted; remove the password protection and upload it again")
    if page_count == 0:
        raise ExtractionError("The PDF has no pages")
    if page_count > MAX_PDF_PAGES:
        raise ExtractionError("The PDF has too many pages", {"pages": page_count, "max_pages": MAX_PDF_PAGES})

    parts: list[str] = []
    unreadable = 0
    total = 0
    for page in reader.pages:
        try:
            text = (page.extract_text() or "").strip()
        except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, AssertionError, NotImplementedError):
            unreadable += 1
            continue
        if text:
            total += len(text)
            if total > MAX_EXTRACTED_CHARS:
                raise ExtractionError("The extracted text is too long", {"max_chars": MAX_EXTRACTED_CHARS})
            parts.append(text)
    if parts:
        return "\n\n".join(parts)
    if unreadable == page_count:
        raise ExtractionError("The PDF pages could not be read (malformed content)")
    if _has_images(reader):
        raise ExtractionError(
            "The PDF has no extractable text: it appears to be a scanned or image-only document. "
            "OCR is not available, so its content cannot be read. Upload a text-based PDF, DOCX, Markdown or TXT."
        )
    return ""


def _has_images(reader: PdfReader) -> bool:
    try:
        return any(len(page.images) > 0 for page in reader.pages)
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, AssertionError, NotImplementedError, OSError):
        return False

def extract_text(filename: str, content_type: str | None, data: bytes) -> ExtractedDocument:
    """Validate and extract. Raises ``DocumentError`` / ``ExtractionError`` with an explicit reason."""
    fmt = validate_upload(filename, content_type, data)
    if fmt in ("text", "markdown"):
        raw = _decode_text(data)
    elif fmt == "docx":
        raw = _docx_text(data)
    else:
        raw = _pdf_text(data)
    text = _clean(raw)
    if not text:
        raise ExtractionError("No text could be extracted from the document (it is empty or has no readable text)")
    if len(text) > MAX_EXTRACTED_CHARS:
        raise ExtractionError("The extracted text is too long", {"max_chars": MAX_EXTRACTED_CHARS, "chars": len(text)})
    return ExtractedDocument(fmt, text, (content_type or "application/octet-stream").split(";")[0].strip().lower())


__all__ = [
    "DocumentError", "ExtractedDocument", "ExtractionError", "MAX_DOCUMENT_BYTES", "MAX_EXTRACTED_CHARS",
    "SUPPORTED", "extract_text", "safe_filename", "validate_upload",
]
