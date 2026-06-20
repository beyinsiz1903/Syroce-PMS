"""Task #636 — Syroce Academy certificate QR-code rendering tests.

These cases lock down the certificate-HTML verification surface documented in
``backend/core/academy.py`` (``_certificate_html`` / ``_certificate_html_impl`` /
``_verification_base_url``) and ``backend/core/security.py``
(``generate_qr_code``) so the scan-to-verify behaviour cannot silently regress:

  1. With a public base URL configured the certificate HTML embeds a QR
     ``<img>`` data-URI PNG and renders the ``Dogrula: <url>`` line.
  2. The QR encodes the exact verification URL — proven deterministically by
     re-generating the QR for that URL and byte-matching the embedded data-URI
     (``qrcode`` output is deterministic for identical input).
  3. The verification URL ends with ``/sertifika-dogrula/{code}``.
  4. Without a base URL no QR is printed and the ``Dogrulama Kodu: <code>``
     text fallback is preserved.

This is a pure unit test against the HTML builder — it does not require a
running backend, a live DB, or WeasyPrint, matching the
``test_academy_security.py`` in-memory testing pattern.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from core import academy
from core.security import generate_qr_code

_BASE_ENV_VARS = ("FRONTEND_URL", "PUBLIC_APP_URL", "REPLIT_DEV_DOMAIN")

CERT = {
    "user_name": "Ayse Yilmaz",
    "course_title": "Resepsiyon Temelleri",
    "department_label": "On Buro",
    "score": 92,
    "verification_code": "ABC123XYZ",
    "issued_at": datetime(2026, 6, 20),
}
CODE = CERT["verification_code"]
ISSUED_STR = "20.06.2026"


def _clear_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _BASE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_certificate_html_embeds_qr_when_base_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://hotel.example.com/")

    html = academy._certificate_html(CERT, ISSUED_STR)

    expected_url = f"https://hotel.example.com/sertifika-dogrula/{CODE}"

    # QR <img> data-URI PNG is present.
    assert '<img class="qr"' in html
    assert 'src="data:image/png;base64,' in html

    # "Dogrula: <url>" line is rendered (not the code fallback).
    assert f"Dogrula: {expected_url}" in html
    assert "Dogrulama Kodu:" not in html


def test_certificate_qr_encodes_verification_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://hotel.example.com")

    html = academy._certificate_html(CERT, ISSUED_STR)

    expected_url = f"https://hotel.example.com/sertifika-dogrula/{CODE}"

    # The verification URL ends with /sertifika-dogrula/{code}.
    assert expected_url.endswith(f"/sertifika-dogrula/{CODE}")

    # The embedded QR encodes that exact URL: qrcode output is deterministic,
    # so regenerating the QR for expected_url must byte-match what is embedded.
    expected_qr = generate_qr_code(expected_url)
    assert f'<img class="qr" src="{expected_qr}" alt="QR" />' in html


def test_certificate_falls_back_to_code_text_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_base_env(monkeypatch)

    html = academy._certificate_html(CERT, ISSUED_STR)

    # No QR image is printed.
    assert "<img" not in html
    assert "data:image/png;base64," not in html

    # Text fallback is preserved.
    assert f"Dogrulama Kodu: {CODE}" in html
    assert "Dogrula:" not in html
