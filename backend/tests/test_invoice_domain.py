from decimal import Decimal

import pytest

from models.schemas.invoicing import Invoice, InvoiceCreate, InvoiceItem, TaxDetail, validate_invoice_tax_snapshot


def get_valid_item() -> InvoiceItem:
    return InvoiceItem(
        description="Test Item",
        quantity=2.0,
        unit_price=10.0,
        total=20.0,
        # Snapshot fields
        unit_code="C62",
        tax_quantity=Decimal("2"),
        tax_unit_price=Decimal("10.00"),
        discount_amount=Decimal("0.00"),
        line_extension_amount=Decimal("20.00"),
        kdv_rate=Decimal("20.00"),
        kdv_amount=Decimal("4.00"),
        other_taxes=[
            TaxDetail(
                tax_code="0059",
                tax_name="Konaklama Vergisi",
                rate=Decimal("2.00"),
                taxable_amount=Decimal("20.00"),
                amount=Decimal("0.40")
            )
        ]
    )

def get_valid_invoice_create() -> InvoiceCreate:
    item = get_valid_item()
    return InvoiceCreate(
        customer_name="Test Customer",
        customer_email="test@example.com",
        due_date="2026-07-30T00:00:00Z",
        items=[item],
        subtotal=20.0,
        tax=4.4,
        total=24.4,
        # Snapshot fields
        line_extension_total=Decimal("20.00"),
        kdv_total=Decimal("4.00"),
        other_tax_total=Decimal("0.40"),
        payable_total=Decimal("24.40"),
        discount_total=Decimal("0.00")
    )


# Scenario 1: geçerli tam snapshot
def test_valid_tax_snapshot():
    invoice = get_valid_invoice_create()
    assert validate_invoice_tax_snapshot(invoice) is True


# Scenario 2: eksik zorunlu snapshot alanı
def test_missing_snapshot_field():
    invoice = get_valid_invoice_create()
    invoice.kdv_total = None
    with pytest.raises(ValueError, match="Missing required snapshot field: kdv_total"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 3: quantity sıfır/negatif
def test_quantity_zero_or_negative():
    invoice = get_valid_invoice_create()
    invoice.items[0].tax_quantity = Decimal("0")
    with pytest.raises(ValueError, match="Item 0 tax_quantity must be > 0"):
        validate_invoice_tax_snapshot(invoice)

    invoice.items[0].tax_quantity = Decimal("-1")
    with pytest.raises(ValueError, match="Item 0 tax_quantity must be > 0"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 4: fazla quantity ondalığı
def test_excessive_quantity_decimals():
    invoice = get_valid_invoice_create()
    invoice.items[0].tax_quantity = Decimal("2.12345")
    with pytest.raises(ValueError, match="Item 0 tax_quantity exceeds maximum allowed decimals of 4"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 5: fazla unit_price ondalığı
def test_excessive_unit_price_decimals():
    invoice = get_valid_invoice_create()
    invoice.items[0].tax_unit_price = Decimal("10.1234567")
    with pytest.raises(ValueError, match="Item 0 tax_unit_price exceeds maximum allowed decimals of 6"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 6: fazla para ondalığı
def test_excessive_money_decimals():
    invoice = get_valid_invoice_create()
    invoice.payable_total = Decimal("24.401")
    with pytest.raises(ValueError, match="payable_total exceeds maximum allowed decimals of 2"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 7: discount gross tutardan büyük
def test_discount_exceeds_gross():
    invoice = get_valid_invoice_create()
    invoice.items[0].discount_amount = Decimal("25.00")  # gross is 20.00
    with pytest.raises(ValueError, match="Item 0 discount_amount cannot exceed gross_line_amount"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 8: line extension uyuşmazlığı
def test_line_extension_mismatch():
    invoice = get_valid_invoice_create()
    # Gross is 20, discount is 0. Expected line ext is 20. Provide 19.
    invoice.items[0].line_extension_amount = Decimal("19.00")
    with pytest.raises(ValueError, match="Item 0 line_extension_amount mismatch. Expected 20.00, got 19.00"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 9: KDV toplam uyuşmazlığı
def test_kdv_total_mismatch():
    invoice = get_valid_invoice_create()
    invoice.kdv_total = Decimal("5.00")
    with pytest.raises(ValueError, match="kdv_total mismatch. Expected 4.00, got 5.00"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 10: diğer vergi toplam uyuşmazlığı
def test_other_tax_total_mismatch():
    invoice = get_valid_invoice_create()
    invoice.other_tax_total = Decimal("0.50")
    with pytest.raises(ValueError, match="other_tax_total mismatch. Expected 0.40, got 0.50"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 11: payable toplam uyuşmazlığı
def test_payable_total_mismatch():
    invoice = get_valid_invoice_create()
    invoice.payable_total = Decimal("24.00")
    with pytest.raises(ValueError, match="payable_total mismatch. Expected 24.40, got 24.00"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 12: exemption alanlarının tek taraflı verilmesi
def test_exemption_fields_pair_validation():
    # Only reason
    with pytest.raises(ValueError, match="exemption_code and exemption_reason must both be provided"):
        TaxDetail(
            tax_code="0015",
            tax_name="KDV",
            rate=Decimal("0.00"),
            taxable_amount=Decimal("100"),
            amount=Decimal("0"),
            exemption_reason="İhracat"
        )
    # Only code
    with pytest.raises(ValueError, match="exemption_code and exemption_reason must both be provided"):
        TaxDetail(
            tax_code="0015",
            tax_name="KDV",
            rate=Decimal("0.00"),
            taxable_amount=Decimal("100"),
            amount=Decimal("0"),
            exemption_code="301"
        )
    # Both provided
    t = TaxDetail(
        tax_code="0015",
        tax_name="KDV",
        rate=Decimal("0.00"),
        taxable_amount=Decimal("100"),
        amount=Decimal("0"),
        exemption_code="301",
        exemption_reason="İhracat İstisnası"
    )
    assert t.exemption_code == "301"


# Scenario 13: legacy Invoice kaydının hâlâ parse edilebilmesi
def test_legacy_invoice_parsing():
    # A legacy JSON dictionary without any of the new Decimal snapshot fields
    # Should be parsed cleanly by Pydantic as backward-compatible
    legacy_data = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "tenant_id": "tenant1",
        "invoice_number": "INV-1001",
        "customer_name": "Legacy Customer",
        "customer_email": "legacy@example.com",
        "subtotal": 100.0,
        "tax": 18.0,
        "total": 118.0,
        "items": [
            {
                "description": "Legacy Item",
                "quantity": 1.0,
                "unit_price": 100.0,
                "total": 100.0
            }
        ]
    }
    invoice = Invoice(**legacy_data)
    assert invoice.customer_name == "Legacy Customer"
    assert invoice.total == 118.0
    # New fields should be None / default
    assert invoice.payable_total is None
    assert invoice.tax_data_complete is False
    assert invoice.items[0].tax_quantity is None


# Scenario 14: boş items listesi
def test_empty_items_list():
    invoice = get_valid_invoice_create()
    invoice.items = []
    with pytest.raises(ValueError, match="Invoice must have at least one item"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 15: unit_code None veya whitespace
def test_unit_code_none_or_whitespace():
    invoice = get_valid_invoice_create()
    invoice.items[0].unit_code = None
    with pytest.raises(ValueError, match="Item 0 missing unit_code"):
        validate_invoice_tax_snapshot(invoice)

    invoice.items[0].unit_code = "   "
    with pytest.raises(ValueError, match="Item 0 missing unit_code"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 16: kdv_rate eksik veya negatif
def test_kdv_rate_missing_or_negative():
    invoice = get_valid_invoice_create()
    invoice.items[0].kdv_rate = None
    with pytest.raises(ValueError, match="Item 0 missing kdv_rate"):
        validate_invoice_tax_snapshot(invoice)

    invoice.items[0].kdv_rate = Decimal("-10.00")
    with pytest.raises(ValueError, match="Item 0 kdv_rate cannot be negative"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 17: fazla kdv_rate ondalığı
def test_excessive_kdv_rate_decimals():
    invoice = get_valid_invoice_create()
    invoice.items[0].kdv_rate = Decimal("20.123")
    with pytest.raises(ValueError, match="Item 0 kdv_rate exceeds maximum allowed decimals of 2"):
        validate_invoice_tax_snapshot(invoice)


# Scenario 18: fazla TaxDetail taxable_amount ondalığı
def test_tax_detail_excessive_decimals():
    with pytest.raises(ValueError, match="taxable_amount exceeds maximum allowed decimals of 2"):
        TaxDetail(
            tax_code="0015",
            tax_name="KDV",
            rate=Decimal("20.00"),
            taxable_amount=Decimal("100.123"),
            amount=Decimal("20.02")
        )


# Scenario 19: iki exemption alanının whitespace olması
def test_exemption_fields_whitespace():
    t = TaxDetail(
        tax_code="0015",
        tax_name="KDV",
        rate=Decimal("20.00"),
        taxable_amount=Decimal("100"),
        amount=Decimal("20"),
        exemption_code="   ",
        exemption_reason=" \t "
    )
    assert t.exemption_code is None
    assert t.exemption_reason is None


# Scenario 20: NaN / Infinity reddi
def test_nan_infinity_rejection():
    invoice = get_valid_invoice_create()
    invoice.items[0].tax_quantity = Decimal("Infinity")
    with pytest.raises(ValueError, match="Item 0 tax_quantity must be a finite number"):
        validate_invoice_tax_snapshot(invoice)

    invoice.items[0].tax_quantity = Decimal("NaN")
    with pytest.raises(ValueError, match="Item 0 tax_quantity must be a finite number"):
        validate_invoice_tax_snapshot(invoice)
