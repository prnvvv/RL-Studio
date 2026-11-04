from __future__ import annotations

import io
import zipfile

import pytest

from backend.projects import documents as docs
from backend.projects.tests.doc_fixtures import (
    DOCX_TYPE,
    make_docx,
    make_encrypted_pdf,
    make_pdf,
    make_pdf_pages,
)


def test_plain_text_and_markdown_are_extracted() -> None:
    out = docs.extract_text("README.md", "text/markdown", b"# Goals\r\n\r\n\r\n\r\nThe agent should reach the goal in at least 80% of episodes.\n")
    assert out.format == "markdown"
    assert "at least 80%" in out.text
    assert "\r" not in out.text and "\n\n\n" not in out.text
    assert docs.extract_text("notes.txt", "text/plain", "cafÃ© reward >= 5".encode()).text == "cafÃ© reward >= 5"


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


def test_filename_is_display_only() -> None:
    assert docs.safe_filename("..\\..\\evil/../req\x00.md") == "req.md"
    assert docs.safe_filename("\x01\x02") == "document"
    assert len(docs.safe_filename("a" * 500 + ".md")) == 200


# ---- PDF (pypdf) ----------------------------------------------------------------------------------------------
def _pdf(data: bytes) -> docs.ExtractedDocument:
    return docs.extract_text("spec.pdf", "application/pdf", data)


def test_pdf_pages_are_extracted_in_order() -> None:
    out = _pdf(make_pdf_pages([["Page one: reach the goal."], ["Page two: avoid collisions.", "Reward >= 5"], ["Page three."]]))
    assert out.format == "pdf"
    assert out.text.split("\n\n") == [
        "Page one: reach the goal.",
        "Page two: avoid collisions.\nReward >= 5",
        "Page three.",
    ]


@pytest.mark.parametrize("compress", [True, False])
def test_pdf_compressed_and_uncompressed_streams(compress: bool) -> None:
    assert _pdf(make_pdf("Final reward (mean) must be >= 100.", compress=compress)).text == "Final reward (mean) must be >= 100."


def test_pdf_skips_blank_pages_but_keeps_the_rest() -> None:
    out = _pdf(make_pdf_pages([[""], ["Real content."], ["   "]]))
    assert out.text == "Real content."


def test_pdf_without_any_text_is_reported_as_empty() -> None:
    with pytest.raises(docs.ExtractionError, match="No text could be extracted"):
        _pdf(make_pdf_pages([["   "], [""]]))


def test_image_only_pdf_reports_that_ocr_is_unavailable() -> None:
    with pytest.raises(docs.ExtractionError) as info:
        _pdf(make_pdf_pages([[""], [""]], image_only=True))
    assert "scanned or image-only" in info.value.message and "OCR is not available" in info.value.message
    assert "ocr" not in docs.SUPPORTED  # no OCR path exists


def test_encrypted_pdf_is_refused_not_guessed() -> None:
    with pytest.raises(docs.ExtractionError, match="encrypted"):
        _pdf(make_encrypted_pdf())


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.4\ngarbage that is not a pdf object\n%%EOF",
        b"%PDF-1.7\n" + b"\x00\x01\x02" * 400,
        make_pdf("Truncated document.")[:60],
    ],
    ids=["garbage-body", "binary-body", "truncated"],
)
def test_malformed_pdf_is_an_explicit_error(data: bytes) -> None:
    with pytest.raises(docs.ExtractionError, match="malformed|no pages|could not be read"):
        _pdf(data)


def test_pdf_with_no_pages_is_an_explicit_error() -> None:
    with pytest.raises(docs.ExtractionError, match="no pages"):
        _pdf(make_pdf_pages([]))


def test_pdf_with_too_many_pages_is_refused() -> None:
    many = make_pdf_pages([["x"]] * (docs.MAX_PDF_PAGES + 1))
    with pytest.raises(docs.ExtractionError, match="too many pages") as info:
        _pdf(many)
    assert info.value.details["max_pages"] == docs.MAX_PDF_PAGES


def test_pdf_with_too_much_text_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docs, "MAX_EXTRACTED_CHARS", 50)
    with pytest.raises(docs.ExtractionError, match="too long"):
        _pdf(make_pdf_pages([["word " * 30], ["more " * 30]]))


def test_oversized_pdf_is_refused_before_parsing() -> None:
    padding = b"%" + b"x" * docs.MAX_DOCUMENT_BYTES + b"\n"
    with pytest.raises(docs.DocumentError, match="too large"):
        _pdf(make_pdf("small") + padding)


def test_pdf_signature_and_content_type_are_still_enforced() -> None:
    with pytest.raises(docs.DocumentError, match="signature"):
        docs.extract_text("fake.pdf", "application/pdf", b"PK\x03\x04 not a pdf")
    with pytest.raises(docs.DocumentError, match="content type"):
        docs.extract_text("spec.pdf", "text/plain", make_pdf("x"))
    with pytest.raises(docs.DocumentError, match="empty"):
        docs.extract_text("spec.pdf", "application/pdf", b"")


def test_the_upload_interface_is_unchanged_for_pdfs() -> None:
    """Same function, same result type and same supported-extension table as before."""
    assert docs.SUPPORTED[".pdf"][0] == "pdf"
    out = docs.extract_text("spec.pdf", "application/octet-stream", make_pdf("Stable interface."))
    assert (out.format, out.text, out.content_type) == ("pdf", "Stable interface.", "application/octet-stream")
