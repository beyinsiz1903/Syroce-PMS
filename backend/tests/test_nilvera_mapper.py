"""Tests for Nilvera Invoice Mapper."""

from datetime import UTC, datetime

import pytest

from core.integrations.nilvera.errors import NilveraBusinessRuleError
from core.integrations.nilvera.mapper import NilveraInvoiceMapper
from models.schemas.invoicing import Invoice, InvoiceItem


def _create_test_invoice(tax_id: str | None = "1234567890", name: str = "Test Customer", items: list[InvoiceItem] | None = None) -> Invoice:
    if items is None:
        items = [InvoiceItem(description="Oda Konaklama", quantity=2.0, unit_price=500.0, total=1000.0)]
    return Invoice(
        tenant_id="tenant-123",
        invoice_number="INV-001",
        customer_name=name,
        billing_tax_id=tax_id,
        items=items,
        subtotal=1000.0,
        tax=200.0,
        total=1200.0,
        issue_date=datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC),
    )


def test_mapper_successful_e_invoice():
    invoice = _create_test_invoice(tax_id="1234567890")
    payload = NilveraInvoiceMapper.map_to_nilvera(invoice=invoice, supplier_vkn="0987654321", supplier_name="Test Hotel", document_type="E_INVOICE")

    assert payload.company_info.tax_number == "0987654321"
    assert payload.customer_info.tax_number == "1234567890"
    assert payload.invoice_info.invoice_type == "SATIS"
    assert payload.invoice_info.payable_amount == 1200.0
    assert payload.invoice_info.line_extension_amount == 1000.0
    assert payload.invoice_info.general_kdv_total == 200.0
    assert len(payload.invoice_lines) == 1
    assert payload.invoice_lines[0].name == "Oda Konaklama"
    assert payload.invoice_lines[0].quantity == 2.0
    assert payload.invoice_lines[0].price == 500.0
    # KDV Percent default is 20
    assert payload.invoice_lines[0].kdv_percent == 20.0
    assert payload.invoice_lines[0].kdv_total == 200.0


def test_mapper_successful_e_archive_fallback():
    # customer_tax_id None -> expects fallback to 11111111111 for E_ARCHIVE
    invoice = _create_test_invoice(tax_id=None)
    payload = NilveraInvoiceMapper.map_to_nilvera(
        invoice=invoice,
        supplier_vkn="0987654321",
        supplier_name="Test Hotel",
        document_type="E_ARCHIVE"
    )

    assert payload.customer_info.tax_number == "11111111111"


def test_mapper_fails_e_invoice_missing_vkn():
    # customer_tax_id None -> expects error for E_INVOICE
    invoice = _create_test_invoice(tax_id=None)
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice=invoice, supplier_vkn="0987654321", supplier_name="Test Hotel", document_type="E_INVOICE")
    assert "E-Fatura gönderimi için geçerli bir VKN" in str(exc.value)


def test_mapper_fails_invalid_vkn_length():
    invoice = _create_test_invoice(tax_id="12345")  # 5 digits, invalid
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice=invoice, supplier_vkn="0987654321", supplier_name="Test Hotel", document_type="E_INVOICE")
    assert "E-Fatura gönderimi için geçerli bir VKN" in str(exc.value)


def test_mapper_fails_missing_customer_name():
    invoice = _create_test_invoice(name="")
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice=invoice, supplier_vkn="0987654321", supplier_name="Test Hotel")
    assert "Fatura alıcı adı (Customer Name) boş olamaz" in str(exc.value)


def test_mapper_fails_no_items():
    invoice = _create_test_invoice(items=[])
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice=invoice, supplier_vkn="0987654321", supplier_name="Test Hotel")
    assert "en az bir kalem (satır) bulunmalıdır" in str(exc.value)
