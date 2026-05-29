"""F8S § 64 — validate_document_bytes magic-byte verification unit tests.

Covers the HR staff-document upload hardening: real file-signature inspection
instead of attacker-controlled multipart Content-Type trust. Polyglot
HTML-as-PDF, SVG, executables and corrupt files must be rejected; genuine
PDF / DOC / DOCX / image content must be accepted with the *detected*
canonical content-type returned.
"""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from security.upload_validator import validate_document_bytes


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


# --- genuine documents accepted, detected content-type returned ----------

def test_genuine_pdf_accepted():
    content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    assert validate_document_bytes(content) == "application/pdf"


def test_genuine_docx_zip_accepted():
    # DOCX is a zip container — PK\x03\x04 local-file header.
    content = b"PK\x03\x04" + b"\x00" * 64
    ct = validate_document_bytes(content)
    assert ct == (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    )


def test_genuine_legacy_doc_ole_accepted():
    content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    assert validate_document_bytes(content) == "application/msword"


def test_genuine_png_accepted_via_image_path():
    assert validate_document_bytes(_png_bytes()) == "image/png"


def test_genuine_jpeg_accepted_via_image_path():
    assert validate_document_bytes(_jpeg_bytes()) == "image/jpeg"


# --- polyglot / spoof / malicious content rejected -----------------------

def test_html_as_pdf_polyglot_rejected():
    # The core fix: HTML body declared as application/pdf must NOT be accepted.
    content = b"<html><body><script>alert(1)</script></body></html>"
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(content, declared_mime="application/pdf")
    assert exc.value.status_code == 400


def test_svg_rejected():
    content = b"<svg><script>alert(1)</script></svg>"
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(content, declared_mime="application/pdf")
    assert exc.value.status_code == 400


def test_executable_rejected():
    content = b"MZ\x90\x00\x03\x00\x00\x00"
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(content, declared_mime="application/pdf")
    assert exc.value.status_code == 400


def test_plain_text_rejected():
    content = b"just some plain text masquerading as a document"
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(content, declared_mime="application/pdf")
    assert exc.value.status_code == 400


# --- size / empty guards --------------------------------------------------

def test_empty_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(b"")
    assert exc.value.status_code == 400


def test_oversized_rejected():
    big = b"%PDF-1.4\n" + b"\x00" * (6 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        validate_document_bytes(big)
    assert exc.value.status_code == 413
