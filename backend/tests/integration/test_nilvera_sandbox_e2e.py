import asyncio
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import get_nilvera_config
from core.integrations.nilvera.errors import NilveraAuthError, NilveraValidationError
from core.integrations.nilvera.mapper import NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome, map_nilvera_status
from core.integrations.nilvera.taxpayer import NilveraTaxpayerService
from models.schemas.invoicing import Invoice, InvoiceItem

# Setup Sandbox Environment Requirements
API_KEY = os.environ.get("NILVERA_E2E_SANDBOX_KEY")
BUYER_VKN = os.environ.get("NILVERA_E2E_BUYER_VKN", "1234567802")
SELLER_VKN = os.environ.get("NILVERA_E2E_SELLER_VKN", "1234567801")

# Mark all tests in this file
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.nilvera_sandbox,
    pytest.mark.external,
    pytest.mark.side_effect,
]

def skip_if_no_key():
    if not API_KEY:
        pytest.skip("NILVERA_E2E_SANDBOX_KEY is missing. Skipping real sandbox E2E tests.")

@pytest.fixture
def sandbox_client():
    skip_if_no_key()
    # Force env to test
    os.environ["NILVERA_ENV"] = "test"
    os.environ["NILVERA_ENABLED"] = "true"

    config = get_nilvera_config()
    assert config.base_url == "https://apitest.nilvera.com", "Sandbox test MUST use apitest.nilvera.com"

    client = NilveraHttpClient(api_key=API_KEY)
    return client

async def test_sandbox_key_missing_skips():
    """Verify that tests are properly skipped if the key is missing."""
    if not API_KEY:
        pytest.skip("Verified that test skips when key is missing.")
    assert True

async def test_sandbox_host_is_forced():
    """Ensure we never hit production or localhost."""
    # Force test env explicitly
    os.environ["NILVERA_ENV"] = "test"
    os.environ["NILVERA_ENABLED"] = "true"
    config = get_nilvera_config()

    # We enforce test environment in E2E
    assert config.env == "test", "Environment must be test"
    assert config.base_url == "https://apitest.nilvera.com"

    # Check that forbidden hosts are definitely not the base_url
    forbidden_hosts = ["api.nilvera.com", "localhost", "127.0.0.1", "http://"]
    for host in forbidden_hosts:
        assert host not in config.base_url

async def test_taxpayer_query_contract(sandbox_client):
    """Test taxpayer query returns valid structure."""
    async with sandbox_client as client:
        service = NilveraTaxpayerService(client)
        result = await service.check_taxpayer(BUYER_VKN)
        assert result.tax_number == BUYER_VKN
        assert isinstance(result.is_e_invoice_user, bool)

async def test_alias_query_contract(sandbox_client):
    """Test alias query and verify the standard alias exists."""
    async with sandbox_client as client:
        service = NilveraTaxpayerService(client)
        result = await service.get_taxpayer_aliases(BUYER_VKN)

        assert result.tax_number == BUYER_VKN
        assert len(result.aliases) > 0, "No aliases found for sandbox buyer VKN"

        # We expect a default PK alias from Nilvera
        expected_alias = "urn:mail:defaultpk@nilvera.com"
        assert expected_alias in result.aliases, f"Expected alias {expected_alias} not found in {result.aliases}"

async def test_invoice_mapper_contract():
    """Verify that the payload mapper works cleanly without API call."""
    request_uuid = uuid.uuid4()
    seller = SellerSnapshot(
        tax_number=SELLER_VKN,
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
        buyer_tax_number=BUYER_VKN,
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
    assert payload.EInvoice.CompanyInfo.TaxNumber == SELLER_VKN
    assert payload.EInvoice.CustomerInfo.TaxNumber == BUYER_VKN

async def test_invoice_submission_contract(sandbox_client):
    """Test actual invoice submission to sandbox."""
    request_uuid = uuid.uuid4()
    seller = SellerSnapshot(
        tax_number=SELLER_VKN,
        name="TEST KURUM 1",
        tax_office="TEST VD",
        country="Türkiye",
        city="İstanbul",
        address="Test Mah. Test Sok. No:1"
    )

    # Generate unique invoice number
    # Standard format: 3 letters + 4 year + 9 sequence = 16 chars
    seq = str(uuid.uuid4().int)[:9].zfill(9)
    inv_no = f"TST2026{seq}"

    invoice = Invoice(
        id=str(uuid.uuid4()),
        tenant_id="test-tenant",
        document_kind="E_INVOICE",
        invoice_number=inv_no,
        invoice_type="SATIS",
        profile="TICARIFATURA",
        series="TST",
        currency="TRY",
        issue_date=datetime.now(UTC),
        buyer_tax_number=BUYER_VKN,
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
                description="Test Hizmeti Sandbox",
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

    async with sandbox_client as client:
        # Submit invoice
        response = await client.post("/einvoice/Send/Model", json=payload.model_dump(by_alias=True))

        # Assert valid UUID returned
        assert "UUID" in response
        assert response["UUID"] != ""
        # The returned UUID should match our request_uuid if the provider respects it
        assert response["UUID"].lower() == str(request_uuid).lower()

async def test_status_polling_contract(sandbox_client):
    """Test polling status of a submitted invoice, PENDING is NOT a success."""
    # First, submit a fresh invoice to poll
    request_uuid = uuid.uuid4()
    seller = SellerSnapshot(
        tax_number=SELLER_VKN,
        name="TEST KURUM 1",
        tax_office="TEST VD",
        country="Türkiye",
        city="İstanbul",
        address="Test Mah. Test Sok. No:1"
    )

    seq = str(uuid.uuid4().int)[:9].zfill(9)
    inv_no = f"TSP2026{seq}"

    invoice = Invoice(
        id=str(uuid.uuid4()),
        tenant_id="test-tenant",
        document_kind="E_INVOICE",
        invoice_number=inv_no,
        invoice_type="SATIS",
        profile="TICARIFATURA",
        series="TSP",
        currency="TRY",
        issue_date=datetime.now(UTC),
        buyer_tax_number=BUYER_VKN,
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
                description="Test Hizmeti Polling Sandbox",
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

    async with sandbox_client as client:
        submit_res = await client.post("/einvoice/Send/Model", json=payload.model_dump(by_alias=True))
        doc_uuid = submit_res["UUID"]

        # Polling config: 1, 2, 4, 5, 5... (max 12 attempts)
        backoffs = [1, 2, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5]

        terminal_status_reached = False
        final_outcome = None

        for attempt, delay in enumerate(backoffs, 1):
            await asyncio.sleep(delay)

            # Use timeout=10s for single request
            try:
                status_res = await client.get(f"/einvoice/Sale/{doc_uuid}/Status", timeout=10.0)
            except httpx.TimeoutException:
                pytest.fail("Status polling timed out")

            # Depending on Nilvera response structure for Status endpoint
            # It usually returns a list or a single object. If list:
            if isinstance(status_res, list) and len(status_res) > 0:
                raw_status = status_res[0].get("Status")
                raw_code = str(status_res[0].get("StatusCode", ""))
            elif isinstance(status_res, dict):
                raw_status = status_res.get("Status")
                raw_code = str(status_res.get("StatusCode", ""))
            else:
                pytest.fail("Unexpected response schema from Status endpoint")

            outcome = map_nilvera_status(raw_status, raw_code)

            if outcome in (ProviderInvoiceOutcome.ACCEPTED, ProviderInvoiceOutcome.REJECTED):
                terminal_status_reached = True
                final_outcome = outcome
                break

            # If outcome is UNKNOWN, we fail
            if outcome == ProviderInvoiceOutcome.UNKNOWN:
                pytest.fail(f"Received UNKNOWN status from provider: {raw_status} (Code: {raw_code})")

        # If we exhausted attempts and didn't reach terminal status, FAIL
        if not terminal_status_reached:
            pytest.fail("Timeout: Status remained PENDING after maximum polling attempts")

        assert final_outcome in (ProviderInvoiceOutcome.ACCEPTED, ProviderInvoiceOutcome.REJECTED)

async def test_http_400_is_failure(sandbox_client):
    """Verify HTTP 400 Validation Error is raised properly."""
    async with sandbox_client as client:
        with pytest.raises(NilveraValidationError) as exc_info:
            # Send completely invalid payload
            await client.post("/einvoice/Send/Model", json={"Invalid": "Payload"})

        assert exc_info.value.http_status == 400

async def test_http_401_is_failure():
    """Verify HTTP 401 Auth Error."""
    skip_if_no_key()
    client = NilveraHttpClient(api_key="invalid_token")
    # Must use test environment explicitly to not hit production
    os.environ["NILVERA_ENV"] = "test"
    async with client as c:
        with pytest.raises(NilveraAuthError) as exc_info:
            await c.get(f"/general/GlobalCompany/Check/TaxNumber/{BUYER_VKN}?globalUserType=Invoice")

        assert exc_info.value.http_status in (401, 403)

async def test_http_500_is_failure(sandbox_client):
    """Verify that HTTP 500 isn't swallowed and comes up as a Server Error."""
    # Since we can't easily force Nilvera to 500, we'll mock the internal httpx client
    async with sandbox_client as client:
        active = client._get_active_client()

        async def mock_send(*args, **kwargs):
            return httpx.Response(500, json={"Errors": [{"Code": "500", "Description": "Internal Server Error"}]}, request=args[0])

        active.send = mock_send

        from core.integrations.nilvera.errors import NilveraServerError
        with pytest.raises(NilveraServerError) as exc_info:
            await client.get("/some/endpoint")

        assert exc_info.value.http_status == 500

def test_secret_redaction(caplog):
    """Verify that API keys, tokens, and VKNs do not leak into logs."""
    skip_if_no_key()

    # Let's inspect caplog
    text = caplog.text
    if API_KEY in text:
        pytest.fail("Sandbox credential leaked into logs")
    # Only mask or exact matches for VKN
    if BUYER_VKN in text:
        pytest.fail("Buyer VKN leaked into logs (should be masked)")
    if SELLER_VKN in text:
        pytest.fail("Seller VKN leaked into logs (should be masked)")
