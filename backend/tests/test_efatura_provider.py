"""Task #571 — real e-Fatura/e-Arsiv provider integration.

Unit tests for ``core.efatura_provider``: fail-closed config gate, UBL-TR
document generation (incl. XML-injection escaping + e-Fatura vs e-Arsiv profile
selection), and the SSRF-safe submission helper. No network or DB required —
``safe_post_async`` is monkeypatched.
"""
from types import SimpleNamespace

import pytest

from core import efatura_provider as ep

_ENV_KEYS = (
    "EFATURA_PROVIDER",
    "EFATURA_PROVIDER_URL",
    "EFATURA_PROVIDER_API_KEY",
    "EFATURA_SUPPLIER_VKN",
    "EFATURA_SUPPLIER_NAME",
    "EFATURA_PROVIDER_TEST_MODE",
    "EFATURA_PROVIDER_TIMEOUT_SECONDS",
    "EFATURA_MAX_ATTEMPTS",
)


@pytest.fixture
def _clean_env(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _configure(monkeypatch):
    monkeypatch.setenv("EFATURA_PROVIDER", "uyumsoft")
    monkeypatch.setenv("EFATURA_PROVIDER_URL", "https://provider.example.com/cut")
    monkeypatch.setenv("EFATURA_PROVIDER_API_KEY", "k-123")
    monkeypatch.setenv("EFATURA_SUPPLIER_VKN", "1234567890")
    monkeypatch.setenv("EFATURA_SUPPLIER_NAME", "Test Otel AS")


# --------------------------------------------------------------------------- #
# Fail-closed config gate
# --------------------------------------------------------------------------- #

def test_not_configured_by_default(_clean_env):
    assert ep.is_configured() is False
    with pytest.raises(ep.EFaturaConfigError):
        ep.provider_config()


def test_partial_config_still_fail_closed(_clean_env):
    _clean_env.setenv("EFATURA_PROVIDER_URL", "https://x.example.com")
    # api key + vkn missing -> still not configured
    assert ep.is_configured() is False
    with pytest.raises(ep.EFaturaConfigError):
        ep.provider_config()


def test_full_config_resolves(_clean_env):
    _configure(_clean_env)
    assert ep.is_configured() is True
    cfg = ep.provider_config()
    assert cfg["provider"] == "uyumsoft"
    assert cfg["url"].startswith("https://")
    assert cfg["supplier_vkn"] == "1234567890"
    assert cfg["test_mode"] is False


def test_max_attempts_default_and_override(_clean_env):
    assert ep.max_attempts() == 5
    _clean_env.setenv("EFATURA_MAX_ATTEMPTS", "3")
    assert ep.max_attempts() == 3
    _clean_env.setenv("EFATURA_MAX_ATTEMPTS", "garbage")
    assert ep.max_attempts() == 5


# --------------------------------------------------------------------------- #
# Profile selection (e-Fatura vs e-Arsiv)
# --------------------------------------------------------------------------- #

def test_profile_vkn_is_efatura():
    assert ep.document_profile({"customer_tax_number": "1234567890"}) == "TICARIFATURA"


def test_profile_tckn_is_earsiv():
    assert ep.document_profile({"customer_tax_number": "12345678901"}) == "EARSIVFATURA"


def test_profile_no_tax_is_earsiv():
    assert ep.document_profile({}) == "EARSIVFATURA"


# --------------------------------------------------------------------------- #
# UBL-TR document generation
# --------------------------------------------------------------------------- #

def _invoice():
    return {
        "invoice_number": "INV-1",
        "customer_name": "Ali Veli",
        "customer_tax_number": "1234567890",
        "currency": "TRY",
        "subtotal": 100.0,
        "total_vat": 20.0,
        "total": 120.0,
        "items": [
            {"description": "Oda", "quantity": 1, "unit_price": 100.0,
             "vat_rate": 20, "vat_amount": 20.0, "total": 120.0},
        ],
    }


def test_ubl_contains_core_fields():
    xml = ep.build_ubl_tr_document(
        _invoice(), supplier_vkn="1234567890", supplier_name="Otel", ettn="ETTN-1",
    )
    assert "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in xml
    assert "<cbc:ProfileID>TICARIFATURA</cbc:ProfileID>" in xml
    assert "<cbc:UUID>ETTN-1</cbc:UUID>" in xml
    assert "<cbc:ID>INV-1</cbc:ID>" in xml
    assert ">120.00<" in xml  # payable/tax-inclusive amount
    assert "Ali Veli" in xml


def test_ubl_escapes_injection():
    inv = _invoice()
    inv["customer_name"] = "</Name></Party><EVIL>x</EVIL><Name>"
    inv["items"][0]["description"] = "<script>&bad"
    xml = ep.build_ubl_tr_document(
        inv, supplier_vkn="1234567890", supplier_name="Otel", ettn="E",
    )
    assert "<EVIL>" not in xml
    assert "&lt;EVIL&gt;" in xml
    assert "<script>" not in xml
    assert "&amp;bad" in xml


def test_ubl_earsiv_profile_for_individual():
    inv = _invoice()
    inv["customer_tax_number"] = ""
    xml = ep.build_ubl_tr_document(
        inv, supplier_vkn="1234567890", supplier_name="Otel", ettn="E",
    )
    assert "<cbc:ProfileID>EARSIVFATURA</cbc:ProfileID>" in xml


# --------------------------------------------------------------------------- #
# Submission helper
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_submit_success(monkeypatch, _clean_env):
    _configure(_clean_env)

    async def fake_post(url, **kw):
        assert url == "https://provider.example.com/cut"
        assert kw["headers"]["Authorization"] == "Bearer k-123"
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"ettn": "OFFICIAL-9", "status": "accepted"},
            text="ok",
        )

    monkeypatch.setattr("integrations.xchange.safety.safe_post_async", fake_post)
    out = await ep.submit_document(
        ubl_xml="<x/>", ettn="E", invoice_number="INV-1",
        document_profile="TICARIFATURA",
    )
    assert out["official_id"] == "OFFICIAL-9"
    assert out["status"] == "accepted"
    assert out["provider"] == "uyumsoft"


@pytest.mark.asyncio
async def test_submit_http_error_raises(monkeypatch, _clean_env):
    _configure(_clean_env)

    async def fake_post(url, **kw):
        return SimpleNamespace(status_code=500, json=lambda: {}, text="boom")

    monkeypatch.setattr("integrations.xchange.safety.safe_post_async", fake_post)
    with pytest.raises(ep.EFaturaSubmissionError):
        await ep.submit_document(
            ubl_xml="<x/>", ettn="E", invoice_number="INV-1",
            document_profile="EARSIVFATURA",
        )


@pytest.mark.asyncio
async def test_submit_transport_error_raises(monkeypatch, _clean_env):
    _configure(_clean_env)

    async def fake_post(url, **kw):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("integrations.xchange.safety.safe_post_async", fake_post)
    with pytest.raises(ep.EFaturaSubmissionError):
        await ep.submit_document(
            ubl_xml="<x/>", ettn="E", invoice_number="INV-1",
            document_profile="EARSIVFATURA",
        )


@pytest.mark.asyncio
async def test_submit_falls_back_to_local_ettn(monkeypatch, _clean_env):
    _configure(_clean_env)

    async def fake_post(url, **kw):
        return SimpleNamespace(status_code=200, json=lambda: {}, text="")

    monkeypatch.setattr("integrations.xchange.safety.safe_post_async", fake_post)
    out = await ep.submit_document(
        ubl_xml="<x/>", ettn="LOCAL-ETTN", invoice_number="INV-1",
        document_profile="TICARIFATURA",
    )
    assert out["official_id"] == "LOCAL-ETTN"
    assert out["status"] == "generated"
