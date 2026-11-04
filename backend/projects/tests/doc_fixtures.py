"""Builders for small valid documents used by the project tests."""

from __future__ import annotations

import io
import zipfile
import zlib

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_docx(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buf.getvalue()


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf_pages(pages: list[list[str]], *, compress: bool = True, image_only: bool = False) -> bytes:
    """A structurally valid PDF (xref table, Helvetica font) with one content stream per page.

    ``image_only`` draws a 2x2 grey image on every page and no text, like a scanned document.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # patched below
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    image = add(
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 4 >>\n"
        b"stream\n\x00\x80\xc0\xff\nendstream"
    )
    kids: list[int] = []
    for lines in pages:
        if image_only:
            ops = b"q 200 0 0 200 50 500 cm /Im0 Do Q"
        else:
            text = "BT /F1 12 Tf 72 720 Td 16 TL\n" + "".join(f"({_esc(line)}) Tj T*\n" for line in lines) + "ET"
            ops = text.encode("latin-1")
        stream = zlib.compress(ops) if compress else ops
        flt = b"/Filter /FlateDecode " if compress else b""
        content = add(b"<< " + flt + b"/Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        xobjects = f" /XObject << /Im0 {image} 0 R >>" if image_only else ""
        page = add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font} 0 R >>{xobjects} >> /Contents {content} 0 R >>".encode()
        )
        kids.append(page)
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_pdf(*lines: str, compress: bool = True) -> bytes:
    """Single-page text PDF."""
    return make_pdf_pages([list(lines)], compress=compress)


def make_encrypted_pdf(password: str = "secret") -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("Confidential requirement."))))
    writer.encrypt(password, algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
