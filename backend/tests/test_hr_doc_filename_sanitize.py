"""Wave 4 § file_upload_security — HR document filename sanitization.

Complements `test_upload_validator_document.py` (magic-byte content guard) by
locking the filename hardening that protects both the GridFS write path and the
download `Content-Disposition` header against path traversal and CRLF/quote
header injection.

The same `_sanitize_doc_filename` is applied at upload AND at download, so the
canonical stored content-type plus a sanitized filename are the only values
that ever reach the response headers.
"""

from domains.hr.router import _sanitize_doc_filename


def test_path_traversal_stripped_to_basename():
    assert _sanitize_doc_filename("../../../../etc/passwd") == "passwd"
    assert _sanitize_doc_filename("..\\..\\windows\\system32\\sam") == "sam"


def test_leading_dots_dropped():
    # `..` / `.hidden` must not survive as a dotfile or traversal token.
    assert not _sanitize_doc_filename("...").startswith(".")
    assert _sanitize_doc_filename(".bashrc") == "bashrc"


def test_crlf_and_quote_header_injection_neutralized():
    raw = 'evil.pdf"\r\nContent-Type: text/html\r\nX-Injected: 1'
    out = _sanitize_doc_filename(raw)
    assert "\r" not in out and "\n" not in out
    assert '"' not in out


def test_empty_or_none_falls_back_to_document():
    assert _sanitize_doc_filename(None) == "document"
    assert _sanitize_doc_filename("") == "document"
    assert _sanitize_doc_filename("///") == "document"


def test_length_capped():
    out = _sanitize_doc_filename("a" * 500 + ".pdf")
    assert len(out) <= 200


def test_safe_characters_preserved():
    assert _sanitize_doc_filename("Sozlesme_2026-01 v2.pdf") == "Sozlesme_2026-01 v2.pdf"


# --- download behavior: served content-type = stored detected type ---------

import pytest


@pytest.mark.asyncio
async def test_download_uses_stored_content_type_and_sanitized_filename(monkeypatch):
    """Route-level: download serves the magic-byte-detected content_type that
    was persisted at upload (never a spoofed value), and the
    Content-Disposition filename is sanitized at download time too."""
    import base64
    from types import SimpleNamespace

    import domains.hr.router as hr

    stored = {
        "id": "doc-1",
        "tenant_id": "t1",
        "staff_id": None,  # no per-record authz needed
        "content_type": "application/pdf",  # detected canonical type
        # legacy raw filename with traversal + CRLF injection attempt
        "filename": "../../etc/passwd\r\nX-Evil: 1",
        "data_b64": base64.b64encode(b"%PDF-1.4 fake").decode(),
    }

    class _Docs:
        async def find_one(self, *_a, **_k):
            return stored

    monkeypatch.setattr(hr, "db", SimpleNamespace(staff_documents=_Docs()))
    user = SimpleNamespace(tenant_id="t1", id="u1", role="admin")

    resp = await hr.download_staff_document(doc_id="doc-1", current_user=user)
    assert resp.media_type == "application/pdf"
    cd = resp.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd
    assert "passwd" in cd and ".." not in cd
