from __future__ import annotations

import io
import zipfile

import pytest

from backend.projects import documents as docs
from backend.projects.tests.doc_fixtures import DOCX_TYPE, make_docx, make_pdf


def test_plain_text_and_markdown_are_extracted() -> None:
    out = docs.extract_text("README.md", "text/markdown", b"# Goals\r\n\r\n\r\n\r\nThe agent should reach the goal in at least 80% of episodes.\n")
    assert out.format == "markdown"
    assert "at least 80%" in out.text
    assert "\r" not in out.text and "\n\n\n" not in out.text
    assert docs.extract_text("notes.txt", "text/plain", "café reward >= 5".encode()).text == "café reward >= 5"


def test_docx_text_is_extracted_without_executing_anything() -> None:
    out = docs.extract_text("req.docx", DOCX_TYPE, make_docx("Average reward must be at least 100.", "Avoid collisions."))
    assert out.format == "docx"
    assert out.text.splitlines() == ["Average reward must be at least 100.", "Avoid collisions."]


@pytest.mark.parametrize("compress", [True, False])
def test_pdf_text_is_extracted(compress: bool) -> None:
    out = docs.extract_text("spec.pdf", "application/pdf", make_pdf("Reach the goal in at most 200 steps.", "Reward (final) >= 1", compress=compress))
    assert out.format == "pdf"
    assert out.text.splitlines() == ["Reach the goal in at most 200 steps.", "Reward (final) >= 1"]


def test_extension_is_never_trusted() -> None:
    with pytest.raises(docs.DocumentError, match="signature"):
        docs.extract_text("fake.pdf", "application/pdf", b"just some text pretending to be a pdf")
    with pytest.raises(docs.DocumentError, match="signature"):
        docs.extract_text("fake.docx", DOCX_TYPE, b"not a zip")
    with pytest.raises(docs.DocumentError, match="not plain text"):
        docs.extract_text("sneaky.txt", "text/plain", make_pdf("x"))
    with pytest.raises(docs.DocumentError, match="not plain text"):
        docs.extract_text("sneaky.md", "text/markdown", b"abc\x00def")


def test_unsupported_type_content_type_mismatch_and_size() -> None:
    with pytest.raises(docs.DocumentError, match="Unsupported"):
        docs.extract_text("run.exe", "application/octet-stream", b"MZ....")
    with pytest.raises(docs.DocumentError, match="content type"):
        docs.extract_text("a.txt", "application/pdf", b"hello")
    with pytest.raises(docs.DocumentError, match="too large"):
        docs.extract_text("a.txt", "text/plain", b"x" * (docs.MAX_DOCUMENT_BYTES + 1))


def test_empty_and_whitespace_documents_are_rejected_not_invented() -> None:
    with pytest.raises(docs.DocumentError, match="empty"):
        docs.extract_text("a.txt", "text/plain", b"")
    with pytest.raises(docs.ExtractionError, match="No text"):
        docs.extract_text("a.md", "text/markdown", b"  \n\n \t ")
    with pytest.raises(docs.ExtractionError, match="No text"):
        docs.extract_text("a.docx", DOCX_TYPE, make_docx("   "))
    with pytest.raises(docs.ExtractionError, match="No text"):
        docs.extract_text("a.pdf", "application/pdf", make_pdf("   "))


def test_corrupt_and_hostile_containers_fail_explicitly() -> None:
    with pytest.raises(docs.ExtractionError, match="corrupt"):
        docs.extract_text("a.docx", DOCX_TYPE, b"PK\x03\x04" + b"garbage" * 20)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("other.xml", "<a/>")
    with pytest.raises(docs.ExtractionError, match="Word document"):
        docs.extract_text("a.docx", DOCX_TYPE, buf.getvalue())
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<w:document/>" + b" " * (docs.MAX_ZIP_MEMBER_BYTES + 1))
    with pytest.raises(docs.ExtractionError, match="too large"):
        docs.extract_text("a.docx", DOCX_TYPE, bomb.getvalue())
    entity = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
    ent = io.BytesIO()
    with zipfile.ZipFile(ent, "w") as z:
        z.writestr("word/document.xml", entity)
    with pytest.raises(docs.ExtractionError, match="entity"):
        docs.extract_text("a.docx", DOCX_TYPE, ent.getvalue())
    with pytest.raises(docs.ExtractionError, match="encrypted"):
        docs.extract_text("a.pdf", "application/pdf", b"%PDF-1.4\n/Encrypt 5 0 R\n%%EOF")


def test_filename_is_display_only() -> None:
    assert docs.safe_filename("..\\..\\evil/../req\x00.md") == "req.md"
    assert docs.safe_filename("\x01\x02") == "document"
    assert len(docs.safe_filename("a" * 500 + ".md")) == 200
