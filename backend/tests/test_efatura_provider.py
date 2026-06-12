"""Task #584 — e-Fatura/e-Arsiv UBL-TR document generation (no transmission).

Unit tests for ``core.efatura_provider``: fail-closed config gate (supplier VKN
only), UBL-TR document generation (incl. XML-injection escaping + e-Fatura vs
e-Arsiv profile selection), and the HTTP-header-safe download filename helper.
No network or DB required — the module no longer transmits to any provider.
"""
import pytest

from core import efatura_provider as ep

_ENV_KEYS = (
    "EFATURA_PROVIDER",
    "EFATURA_SUPPLIER_VKN",
    "EFATURA_SUPPLIER_NAME",
    "EFATURA_MAX_ATTEMPTS",
)


@pytest.fixture
def _clean_env(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _configure(monkeypatch):
    monkeypatch.setenv("EFATURA_PROVIDER", "uyumsoft")
    monkeypatch.setenv("EFATURA_SUPPLIER_VKN", "1234567890")
    monkeypatch.setenv("EFATURA_SUPPLIER_NAME", "Test Otel AS")


# --------------------------------------------------------------------------- #
# Fail-closed config gate (supplier VKN only)
# --------------------------------------------------------------------------- #

def test_not_configured_by_default(_clean_env):
    assert ep.is_configured() is False
    with pytest.raises(ep.EFaturaConfigError):
        ep.provider_config()


def test_provider_set_but_no_vkn_still_fail_closed(_clean_env):
    _clean_env.setenv("EFATURA_PROVIDER", "uyumsoft")
    # supplier VKN missing -> still not configured
    assert ep.is_configured() is False
    with pytest.raises(ep.EFaturaConfigError):
        ep.provider_config()


def test_vkn_only_resolves(_clean_env):
    _configure(_clean_env)
    assert ep.is_configured() is True
    cfg = ep.provider_config()
    assert cfg["provider"] == "uyumsoft"
    assert cfg["supplier_vkn"] == "1234567890"
    assert cfg["supplier_name"] == "Test Otel AS"
    # provider POST credentials are gone
    assert "url" not in cfg
    assert "api_key" not in cfg
    assert "test_mode" not in cfg
    assert "timeout" not in cfg


def test_provider_defaults_to_generic(_clean_env):
    _clean_env.setenv("EFATURA_SUPPLIER_VKN", "1234567890")
    cfg = ep.provider_config()
    assert cfg["provider"] == "generic"
    assert cfg["supplier_name"] == ""


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
# HTTP-header-safe download filename
# --------------------------------------------------------------------------- #

def test_safe_xml_filename_basic():
    fn = ep.safe_xml_filename("INV-1", "Ali Veli")
    assert fn == "efatura-INV-1-Ali-Veli.xml"
    assert fn.endswith(".xml")


def test_safe_xml_filename_strips_header_injection():
    fn = ep.safe_xml_filename('INV-1"\r\nSet-Cookie: x=1', "Guest")
    assert "\r" not in fn and "\n" not in fn
    assert '"' not in fn
    assert fn.endswith(".xml")
    assert fn.startswith("efatura-")


def test_safe_xml_filename_non_ascii_collapses():
    fn = ep.safe_xml_filename("FT-2026", "Çağrı Şükrü")
    # non-ASCII guest name characters collapse to '-'
    assert all(c.isascii() for c in fn)
    assert fn.endswith(".xml")


def test_safe_xml_filename_empty_fallback():
    fn = ep.safe_xml_filename("", None)
    assert fn == "efatura-efatura.xml"
