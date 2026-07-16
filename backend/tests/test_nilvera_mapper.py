import uuid
from datetime import UTC, datetime, tzinfo
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.integrations.nilvera.errors import NilveraBusinessRuleError
from core.integrations.nilvera.mapper import (
    NilveraInvoiceMapper,
    SellerSnapshot,
)
from models.schemas.invoicing import Invoice, InvoiceItem, TaxDetail


def create_valid_invoice(currency="TRY", exchange_rate=None) -> Invoice:
    return Invoice(
        tenant_id="tenant_123",
        invoice_number="INV-001",
        customer_name="Test Buyer",
        customer_email="test@example.com",
        subtotal=100.0,
        tax=20.0,
        total=120.0,
        due_date=datetime(2026, 8, 17, tzinfo=UTC),
        document_kind="E_INVOICE",
        invoice_type="SATIS",
        profile="TICARIFATURA",
        series="SYR",
        issue_date=datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC),
        buyer_tax_number="1111111111",
        buyer_legal_name="Test Buyer",
        buyer_country_name="Türkiye",
        buyer_city="İstanbul",
        buyer_address="Test Mah.",
        buyer_tax_office="Beyoğlu",
        currency=currency,
        exchange_rate=exchange_rate,
        discount_total=None,
        line_extension_total=Decimal("100.00"),
        kdv_total=Decimal("20.00"),
        other_tax_total=Decimal("0.00"),
        payable_total=Decimal("120.00"),
        tax_data_complete=True,
        items=[
            InvoiceItem(
                description="Test Item",
                quantity=1.000,
                unit_price=100.00,
                total=100.00,
                discount_amount=Decimal("0.00"),
                line_extension_amount=Decimal("100.00"),
                kdv_rate=Decimal("20.00"),
                kdv_amount=Decimal("20.00"),
                tax_quantity=Decimal("1.0000"),
                tax_unit_price=Decimal("100.000000"),
                unit_code="C62",
                other_taxes=[],
            )
        ],
    )


def create_valid_seller() -> SellerSnapshot:
    return SellerSnapshot(
        tax_number="2222222222",
        name="Test Seller",
        tax_office="Kadıköy",
        country="Türkiye",
        city="İstanbul",
        address="Seller Mah.",
    )


def test_successful_mapping_and_decimal_types():
    invoice = create_valid_invoice()
    seller = create_valid_seller()
    request_uuid = uuid.uuid4()

    payload = NilveraInvoiceMapper.map_to_nilvera(
        invoice=invoice,
        seller=seller,
        customer_alias="urn:mail:receiver@example.com",
        request_uuid=request_uuid,
    )

    # Typed payload checks
    assert payload.EInvoice.CustomerInfo.TaxNumber == "1111111111"
    assert payload.EInvoice.CompanyInfo.TaxNumber == "2222222222"
    assert payload.EInvoice.InvoiceInfo.UUID == str(request_uuid)
    assert payload.CustomerAlias == "urn:mail:receiver@example.com"

    # Financial fields should be Decimal in typed model
    assert isinstance(payload.EInvoice.InvoiceInfo.PayableAmount, Decimal)
    assert isinstance(payload.EInvoice.InvoiceLines[0].KDVTotal, Decimal)
    assert isinstance(payload.EInvoice.InvoiceLines[0].Quantity, Decimal)
    assert isinstance(payload.EInvoice.InvoiceInfo.IssueDate, datetime)
    assert payload.EInvoice.InvoiceInfo.IssueDate.tzinfo is not None

    # Verify mode="python" serialization
    dump = payload.model_dump(mode="python", by_alias=True, exclude_none=True)

    # Ensure nested elements are Decimal in dict
    info = dump["EInvoice"]["InvoiceInfo"]
    lines = dump["EInvoice"]["InvoiceLines"]
    assert isinstance(info["PayableAmount"], Decimal)
    assert isinstance(lines[0]["KDVTotal"], Decimal)
    assert isinstance(lines[0]["Price"], Decimal)
    assert isinstance(info["IssueDate"], datetime)

    # No ExchangeRate for TRY
    assert "ExchangeRate" not in info


def test_empty_items_special_code():
    invoice = create_valid_invoice()
    invoice.items = []

    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_ITEMS_EMPTY"


def test_seller_snapshot_frozen():
    seller = create_valid_seller()
    with pytest.raises(ValidationError):
        seller.tax_number = "123"

def test_seller_snapshot_missing_fields_no_pydantic_error():
    # Should not raise Pydantic ValidationError on creation
    seller = SellerSnapshot(tax_number="2222222222")  # Missing name
    invoice = create_valid_invoice()

    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, seller, "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_SELLER_NAME_REQUIRED"


@pytest.mark.parametrize("field, invalid_val, expected_code", [
    ("tax_number", None, "E_INVOICE_SELLER_TAX_NUMBER_REQUIRED"),
    ("tax_number", "", "E_INVOICE_SELLER_TAX_NUMBER_REQUIRED"),
    ("tax_number", "   ", "E_INVOICE_SELLER_TAX_NUMBER_REQUIRED"),
    ("name", None, "E_INVOICE_SELLER_NAME_REQUIRED"),
    ("name", "", "E_INVOICE_SELLER_NAME_REQUIRED"),
    ("name", "   ", "E_INVOICE_SELLER_NAME_REQUIRED"),
    ("tax_office", None, "E_INVOICE_SELLER_TAX_OFFICE_REQUIRED"),
    ("tax_office", "", "E_INVOICE_SELLER_TAX_OFFICE_REQUIRED"),
    ("tax_office", "   ", "E_INVOICE_SELLER_TAX_OFFICE_REQUIRED"),
    ("country", None, "E_INVOICE_SELLER_COUNTRY_REQUIRED"),
    ("country", "", "E_INVOICE_SELLER_COUNTRY_REQUIRED"),
    ("country", "   ", "E_INVOICE_SELLER_COUNTRY_REQUIRED"),
    ("city", None, "E_INVOICE_SELLER_CITY_REQUIRED"),
    ("city", "", "E_INVOICE_SELLER_CITY_REQUIRED"),
    ("city", "   ", "E_INVOICE_SELLER_CITY_REQUIRED"),
    ("address", None, "E_INVOICE_SELLER_ADDRESS_REQUIRED"),
    ("address", "", "E_INVOICE_SELLER_ADDRESS_REQUIRED"),
    ("address", "   ", "E_INVOICE_SELLER_ADDRESS_REQUIRED"),
])
def test_seller_missing_and_whitespace_fields(field, invalid_val, expected_code):
    invoice = create_valid_invoice()
    seller = create_valid_seller().model_copy(update={field: invalid_val})

    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, seller, "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == expected_code


@pytest.mark.parametrize("field, invalid_val, expected_code", [
    ("buyer_tax_number", None, "E_INVOICE_BUYER_TAX_NUMBER_REQUIRED"),
    ("buyer_tax_number", "", "E_INVOICE_BUYER_TAX_NUMBER_REQUIRED"),
    ("buyer_tax_number", "   ", "E_INVOICE_BUYER_TAX_NUMBER_REQUIRED"),
    ("buyer_legal_name", None, "E_INVOICE_BUYER_NAME_REQUIRED"),
    ("buyer_legal_name", "", "E_INVOICE_BUYER_NAME_REQUIRED"),
    ("buyer_legal_name", "   ", "E_INVOICE_BUYER_NAME_REQUIRED"),
    ("buyer_country_name", None, "E_INVOICE_BUYER_COUNTRY_REQUIRED"),
    ("buyer_country_name", "", "E_INVOICE_BUYER_COUNTRY_REQUIRED"),
    ("buyer_country_name", "   ", "E_INVOICE_BUYER_COUNTRY_REQUIRED"),
    ("buyer_city", None, "E_INVOICE_BUYER_CITY_REQUIRED"),
    ("buyer_city", "", "E_INVOICE_BUYER_CITY_REQUIRED"),
    ("buyer_city", "   ", "E_INVOICE_BUYER_CITY_REQUIRED"),
    ("buyer_address", None, "E_INVOICE_BUYER_ADDRESS_REQUIRED"),
    ("buyer_address", "", "E_INVOICE_BUYER_ADDRESS_REQUIRED"),
    ("buyer_address", "   ", "E_INVOICE_BUYER_ADDRESS_REQUIRED"),
])
def test_buyer_missing_and_whitespace_fields(field, invalid_val, expected_code):
    invoice = create_valid_invoice()
    setattr(invoice, field, invalid_val)

    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == expected_code


def test_naive_datetime():
    invoice = create_valid_invoice()
    # No tzinfo
    invoice.issue_date = datetime(2026, 7, 17, 10, 0, 0)
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_NAIVE_DATETIME"

    # With tzinfo but utcoffset() is None (Python doesn't easily create these natively without custom tzinfo,
    # but we can simulate a timezone whose utcoffset is None)
    class NullTZ(tzinfo):
        def utcoffset(self, dt): return None
    invoice.issue_date = datetime(2026, 7, 17, 10, 0, 0, tzinfo=NullTZ())
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_NAIVE_DATETIME"


@pytest.mark.parametrize("rate", [None, Decimal("0.0"), Decimal("-1.5"), Decimal("NaN"), Decimal("Infinity")])
def test_foreign_currency_invalid_exchange_rates(rate):
    invoice = create_valid_invoice(currency="USD")
    # Bypass Pydantic validation for non-finite values to test mapper's defensive checks
    object.__setattr__(invoice, "exchange_rate", rate)
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_EXCHANGE_RATE_REQUIRED"

def test_foreign_currency_exchange_rate():
    invoice = create_valid_invoice(currency="USD", exchange_rate=Decimal("30.5"))
    payload = NilveraInvoiceMapper.map_to_nilvera(
        invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
    )
    assert payload.EInvoice.InvoiceInfo.ExchangeRate == Decimal("30.5")


def test_tax_number_validation():
    invoice = create_valid_invoice()
    seller = create_valid_seller().model_copy(update={"tax_number": "123456789"})  # 9 digits
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice, seller, "urn:mail:receiver@example.com", uuid.uuid4())
    assert exc.value.provider_code == "E_INVOICE_SELLER_TAX_NUMBER_INVALID"
    assert "123456789" not in str(exc.value)

    seller = create_valid_seller().model_copy(update={"tax_number": "2222222222"})
    invoice.buyer_tax_number = "abc1234567"
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice, seller, "urn:mail:receiver@example.com", uuid.uuid4())
    assert exc.value.provider_code == "E_INVOICE_BUYER_TAX_NUMBER_INVALID"


@pytest.mark.parametrize("alias", [None, "", "   "])
def test_customer_alias_required(alias):
    invoice = create_valid_invoice()
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(invoice, create_valid_seller(), alias, uuid.uuid4())
    assert exc.value.provider_code == "E_INVOICE_CUSTOMER_ALIAS_REQUIRED"


def test_customer_alias_strip():
    invoice = create_valid_invoice()
    payload = NilveraInvoiceMapper.map_to_nilvera(
        invoice, create_valid_seller(), "   urn:mail:receiver@example.com  ", uuid.uuid4()
    )
    assert payload.CustomerAlias == "urn:mail:receiver@example.com"


def test_domain_validation_failure_wrapping():
    invoice = create_valid_invoice()
    invoice.payable_total = Decimal("-10.00")
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_DOMAIN_VALIDATION_FAILED"
    assert exc.value.__suppress_context__ is True


def test_no_float_in_mapper_source():
    with open("core/integrations/nilvera/mapper.py") as f:
        content = f.read()
    # Ensure float usage is completely removed
    assert "float(" not in content


def test_document_kind():
    invoice = create_valid_invoice()
    invoice.document_kind = "E_ARCHIVE"
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_DOCUMENT_KIND_INVALID"


@pytest.mark.parametrize("series, expected_code", [
    (None, "E_INVOICE_SERIES_REQUIRED"),
    ("", "E_INVOICE_SERIES_REQUIRED"),
    ("   ", "E_INVOICE_SERIES_REQUIRED"),
    (" AB", "E_INVOICE_SERIES_FORMAT_INVALID"),
    ("AB ", "E_INVOICE_SERIES_FORMAT_INVALID"),
    ("A\nC", "E_INVOICE_SERIES_FORMAT_INVALID"),
    ("AB", "E_INVOICE_SERIES_FORMAT_INVALID"),  # length 2
    ("ABCD", "E_INVOICE_SERIES_FORMAT_INVALID"), # length 4
])
def test_series_validation(series, expected_code):
    invoice = create_valid_invoice()
    invoice.series = series
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == expected_code


@pytest.mark.parametrize("currency, expected_code", [
    (None, "E_INVOICE_CURRENCY_REQUIRED"),
    ("", "E_INVOICE_CURRENCY_REQUIRED"),
    ("   ", "E_INVOICE_CURRENCY_REQUIRED"),
    ("try", "E_INVOICE_CURRENCY_INVALID"),
    ("TR", "E_INVOICE_CURRENCY_INVALID"),
    ("TRYY", "E_INVOICE_CURRENCY_INVALID"),
    ("TR1", "E_INVOICE_CURRENCY_INVALID"),
])
def test_currency_validation(currency, expected_code):
    invoice = create_valid_invoice()
    invoice.currency = currency
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == expected_code


@pytest.mark.parametrize("profile, expected_code", [
    (None, "E_INVOICE_PROFILE_REQUIRED"),
    ("", "E_INVOICE_PROFILE_REQUIRED"),
    ("   ", "E_INVOICE_PROFILE_REQUIRED"),
])
def test_profile_validation(profile, expected_code):
    invoice = create_valid_invoice()
    invoice.profile = profile
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == expected_code


def test_invoice_type():
    invoice = create_valid_invoice()
    invoice.invoice_type = "IADE"
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_TYPE_UNSUPPORTED"


def test_kdv_exemption_unsupported():
    invoice = create_valid_invoice()
    invoice.items[0].kdv_rate = Decimal("0")
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_KDV_EXEMPTION_UNSUPPORTED"


def test_kdv_rate_18_success():
    invoice = create_valid_invoice()
    invoice.items[0].kdv_rate = Decimal("18")
    invoice.items[0].kdv_amount = Decimal("18.00")
    invoice.kdv_total = Decimal("18.00")
    invoice.payable_total = Decimal("118.00")

    payload = NilveraInvoiceMapper.map_to_nilvera(
        invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
    )
    assert payload.EInvoice.InvoiceLines[0].KDVPercent == Decimal("18")
    assert payload.EInvoice.InvoiceLines[0].KDVTotal == Decimal("18.00")


def test_other_taxes_unsupported():
    invoice = create_valid_invoice()
    invoice.items[0].other_taxes = [
        TaxDetail(
            tax_code="0059",
            tax_name="Konaklama",
            rate=Decimal("2"),
            taxable_amount=Decimal("100"),
            amount=Decimal("2"),
        )
    ]
    invoice.other_tax_total = Decimal("2.00")
    invoice.payable_total = Decimal("122.00")
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", uuid.uuid4()
        )
    assert exc.value.provider_code == "E_INVOICE_OTHER_TAX_UNSUPPORTED"


def test_request_uuid_invalid_type():
    invoice = create_valid_invoice()
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, create_valid_seller(), "urn:mail:receiver@example.com", "not-a-uuid" # type: ignore
        )
    assert exc.value.provider_code == "E_INVOICE_UUID_INVALID"


def test_pii_not_in_error_message():
    invoice = create_valid_invoice()
    seller = create_valid_seller().model_copy(update={"tax_number": "123"})
    with pytest.raises(NilveraBusinessRuleError) as exc:
        NilveraInvoiceMapper.map_to_nilvera(
            invoice, seller, "urn:mail:receiver@example.com", uuid.uuid4()
        )

    msg = str(exc.value)
    assert "123" not in msg
    assert "urn:mail:receiver@example.com" not in msg
    assert "Test Buyer" not in msg
    assert "Test Mah." not in msg
