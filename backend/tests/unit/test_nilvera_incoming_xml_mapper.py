from decimal import Decimal

import pytest

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_xml_mapper import NilveraIncomingXmlMapper


def _invoice_xml(*, uuid_value: str = "123e4567-e89b-12d3-a456-426614174000") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>TEST2026000000001</cbc:ID>
  <cbc:UUID>{uuid_value}</cbc:UUID>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification><cbc:ID>1234567890</cbc:ID></cac:PartyIdentification>
      <cac:PartyName><cbc:Name>Test Supplier</cbc:Name></cac:PartyName>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">2</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="TRY">100.00</cbc:LineExtensionAmount>
    <cac:AllowanceCharge>
      <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
      <cbc:Amount currencyID="TRY">10.00</cbc:Amount>
    </cac:AllowanceCharge>
    <cac:TaxTotal>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="TRY">100.00</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="TRY">20.00</cbc:TaxAmount>
        <cac:TaxCategory>
          <cbc:Percent>20</cbc:Percent>
          <cac:TaxScheme><cbc:Name>KDV</cbc:Name><cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="TRY">100.00</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="TRY">1.00</cbc:TaxAmount>
        <cac:TaxCategory>
          <cbc:Percent>1</cbc:Percent>
          <cac:TaxScheme><cbc:Name>Other Tax</cbc:Name><cbc:TaxTypeCode>9999</cbc:TaxTypeCode></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item><cbc:Name>Service</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="TRY">50.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>""".encode()


def test_maps_ubl_invoice_lines_without_parsing_other_dates():
    result = NilveraIncomingXmlMapper.map_document(_invoice_xml())

    assert result.provider_uuid == "123e4567-e89b-12d3-a456-426614174000"
    assert result.invoice_number == "TEST2026000000001"
    assert result.supplier_tax_number == "1234567890"
    assert result.supplier_name == "Test Supplier"
    assert len(result.lines) == 1

    line = result.lines[0]
    assert line.provider_line_id == "1"
    assert line.line_number == 1
    assert line.quantity == Decimal("2")
    assert line.unit_code == "C62"
    assert line.unit_price == Decimal("50.00")
    assert line.discount_amount == Decimal("10.00")
    assert line.line_extension_amount == Decimal("100.00")
    assert line.kdv_rate == Decimal("20")
    assert line.kdv_amount == Decimal("20.00")
    assert line.currency == "TRY"
    assert len(line.other_taxes) == 1
    assert line.other_taxes[0].tax_code == "9999"
    assert line.other_taxes[0].is_deduction is False


def test_rejects_invalid_uuid_without_exposing_value():
    sensitive_value = "sensitive-provider-identity"
    with pytest.raises(NilveraValidationError) as exc_info:
        NilveraIncomingXmlMapper.map_document(_invoice_xml(uuid_value=sensitive_value))

    assert sensitive_value not in str(exc_info.value)
    assert "invalid UUID" in str(exc_info.value)


def test_rejects_external_entity_xml():
    content = b"""<?xml version="1.0"?>
<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&xxe;</Invoice>"""
    with pytest.raises(NilveraValidationError, match="cannot be parsed"):
        NilveraIncomingXmlMapper.map_document(content)


def test_rejects_currency_mismatch():
    content = _invoice_xml().replace(
        b'<cbc:PriceAmount currencyID="TRY">',
        b'<cbc:PriceAmount currencyID="USD">',
    )
    with pytest.raises(NilveraValidationError, match="currencies do not match"):
        NilveraIncomingXmlMapper.map_document(content)


def test_derives_missing_tax_rate_from_explicit_tax_amounts():
    content = _invoice_xml().replace(b"<cbc:Percent>20</cbc:Percent>", b"", 1)
    result = NilveraIncomingXmlMapper.map_document(content)

    assert result.lines[0].kdv_rate == Decimal("20.00")


@pytest.mark.parametrize(
    ("raw_value", "lexical_form"),
    [
        ("20,00", "comma_separator"),
        ("1.000,00", "mixed_separators"),
        ("20 00", "embedded_whitespace"),
        ("not-a-number", "non_decimal"),
    ],
)
def test_invalid_decimal_reports_only_safe_lexical_form(raw_value, lexical_form):
    content = _invoice_xml().replace(b">20.00</cbc:TaxAmount>", f">{raw_value}</cbc:TaxAmount>".encode(), 1)

    with pytest.raises(NilveraValidationError) as exc_info:
        NilveraIncomingXmlMapper.map_document(content)

    message = str(exc_info.value)
    assert f"lexical_form={lexical_form}" in message
    assert raw_value not in message


@pytest.mark.parametrize(
    ("raw_value", "numeric_form"),
    [
        ("NaN", "non_finite"),
    ],
)
def test_invalid_decimal_reports_only_safe_numeric_form(raw_value, numeric_form):
    content = _invoice_xml().replace(b">20.00</cbc:TaxAmount>", f">{raw_value}</cbc:TaxAmount>".encode(), 1)

    with pytest.raises(NilveraValidationError) as exc_info:
        NilveraIncomingXmlMapper.map_document(content)

    message = str(exc_info.value)
    assert f"numeric_form={numeric_form}" in message
    assert raw_value not in message


def test_maps_negative_other_tax_amount_as_explicit_deduction():
    content = _invoice_xml().replace(b">1.00</cbc:TaxAmount>", b">-1.00</cbc:TaxAmount>", 1)
    result = NilveraIncomingXmlMapper.map_document(content)

    tax = result.lines[0].other_taxes[0]
    assert tax.amount == Decimal("1.00")
    assert tax.is_deduction is True


def test_maps_pricing_exchange_rate_for_foreign_currency_gl():
    exchange = b"""
    <cac:PricingExchangeRate>
      <cbc:SourceCurrencyCode>EUR</cbc:SourceCurrencyCode>
      <cbc:TargetCurrencyCode>TRY</cbc:TargetCurrencyCode>
      <cbc:CalculationRate>40.125000</cbc:CalculationRate>
    </cac:PricingExchangeRate>
    """
    content = _invoice_xml().replace(b"<cac:InvoiceLine>", exchange + b"<cac:InvoiceLine>", 1)
    result = NilveraIncomingXmlMapper.map_document(content)
    assert result.exchange_rate == Decimal("40.125000")
    assert result.exchange_rate_source_currency == "EUR"
    assert result.exchange_rate_target_currency == "TRY"


def test_rejects_negative_non_tax_amount_without_exposing_value():
    content = _invoice_xml().replace(
        b'<cbc:LineExtensionAmount currencyID="TRY">100.00',
        b'<cbc:LineExtensionAmount currencyID="TRY">-1.00',
        1,
    )

    with pytest.raises(NilveraValidationError) as exc_info:
        NilveraIncomingXmlMapper.map_document(content)

    message = str(exc_info.value)
    assert "numeric_form=negative" in message
    assert "-1.00" not in message
