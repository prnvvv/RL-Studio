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


def make_pdf(*lines: str, compress: bool = True) -> bytes:
    ops = "BT /F1 12 Tf 72 720 Td 14 TL\n" + "".join(
        f"({line.replace(chr(92), chr(92) * 2).replace('(', chr(92) + '(').replace(')', chr(92) + ')')}) Tj T*\n"
        for line in lines
    ) + "ET"
    stream = zlib.compress(ops.encode("latin-1")) if compress else ops.encode("latin-1")
    flt = b"/Filter /FlateDecode " if compress else b""
    return (
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
        b"4 0 obj << " + flt + b"/Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )
