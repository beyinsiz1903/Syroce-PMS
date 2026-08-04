import uuid
from datetime import UTC, datetime
from decimal import Decimal

from core.integrations.nilvera.config import get_nilvera_config
from core.integrations.nilvera.mapper import NilveraInvoiceMapper, SellerSnapshot
from models.schemas.invoicing import Invoice, InvoiceItem


def test_sandbox_host_is_forced(monkeypatch):
    """Ensure we never hit production or localhost when env is test."""
    monkeypatch.setenv("NILVERA_ENV", "test")
    monkeypatch.setenv("NILVERA_ENABLED", "true")

    import core.integrations.nilvera.config
    core.integrations.nilvera.config._config = None
    config = get_nilvera_config()

    assert config.env == "test", "Environment must be test"
    assert config.base_url == "https://apitest.nilvera.com"

    forbidden_hosts = ["api.nilvera.com", "localhost", "127.0.0.1", "http://"]
    for host in forbidden_hosts:
        assert host not in config.base_url

def test_invoice_mapper_contract():
    """Verify that the payload mapper works cleanly without API call."""
    request_uuid = uuid.uuid4()
    seller = SellerSnapshot(
        tax_number="1234567801",
        name="TEST KURUM 1",
        tax_office="TEST VD",
        country="Türkiye",
        city="İstanbul",
        address="Test Mah. Test Sok. No:1"
    )

    invoice = Invoice(
        id=str(uuid.uuid4()),
        tenant_id="test-tenant",
        document_kind="E_INVOICE",
        invoice_number=f"TST2026{str(uuid.uuid4().int)[:9]}",
        invoice_type="SATIS",
        profile="TICARIFATURA",
        series="TST",
        currency="TRY",
        issue_date=datetime.now(UTC),
        buyer_tax_number="1234567802",
        buyer_legal_name="TEST KURUM 2",
        buyer_country_name="Türkiye",
        buyer_city="Ankara",
        buyer_address="Test Alıcı Adres",
        payable_total=Decimal("120.00"),
        line_extension_total=Decimal("100.00"),
        kdv_total=Decimal("20.00"),
        other_tax_total=Decimal("0.00"),
        discount_total=Decimal("0.00"),
        items=[
            InvoiceItem(
                description="Test Hizmeti",
                quantity=Decimal("1.0"),
                tax_quantity=Decimal("1.0"),
                unit_code="C62",
                unit_price=Decimal("100.00"),
                tax_unit_price=Decimal("100.00"),
                discount_amount=Decimal("0.0"),
                line_extension_amount=Decimal("100.00"),
                kdv_rate=Decimal("20.0"),
                kdv_amount=Decimal("20.00"),
                total=Decimal("120.00")
            )
        ]
    )

    alias = "urn:mail:defaultpk@nilvera.com"
    payload = NilveraInvoiceMapper.map_to_nilvera(invoice, seller, alias, request_uuid)

    assert payload.EInvoice.InvoiceInfo.UUID == str(request_uuid)
    assert payload.EInvoice.CompanyInfo.TaxNumber == "1234567801"
    assert payload.EInvoice.CustomerInfo.TaxNumber == "1234567802"

def test_sandbox_key_missing_skips_logic(monkeypatch):
    """
    Unit test to verify that the missing secrets logic works.
    We temporarily clear the env vars and ensure the check returns True.
    """
    from tests.integration.test_nilvera_sandbox_e2e import check_missing_secrets
    monkeypatch.delenv("NILVERA_E2E_SANDBOX_KEY", raising=False)
    monkeypatch.delenv("NILVERA_E2E_BUYER_VKN", raising=False)
    monkeypatch.delenv("NILVERA_E2E_SELLER_VKN", raising=False)
    
    assert check_missing_secrets() is True

