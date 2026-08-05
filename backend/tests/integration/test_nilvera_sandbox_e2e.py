import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import get_nilvera_config
from core.integrations.nilvera.errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraServerError,
    NilveraValidationError,
)
from core.integrations.nilvera.mapper import NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome, map_nilvera_status
from core.integrations.nilvera.taxpayer import NilveraTaxpayerService
from models.schemas.invoicing import Invoice, InvoiceItem

# Mark all tests in this file as nilvera_sandbox
pytestmark = [pytest.mark.asyncio, pytest.mark.nilvera_sandbox]


def check_missing_secrets() -> bool:
    """Return True if any required secret is missing."""
    key = os.environ.get("NILVERA_E2E_SANDBOX_KEY")
    buyer = os.environ.get("NILVERA_E2E_BUYER_VKN")
    seller = os.environ.get("NILVERA_E2E_SELLER_VKN")
    return not (key and buyer and seller)


@pytest.fixture(autouse=True)
def skip_if_missing_secrets():
    """Skip E2E test if required secrets are missing."""
    if check_missing_secrets():
        pytest.skip("Missing NILVERA_E2E_SANDBOX_KEY, BUYER_VKN or SELLER_VKN. Skipping real sandbox E2E tests.")


@pytest.fixture
def api_key():
    return os.environ.get("NILVERA_E2E_SANDBOX_KEY")


@pytest.fixture
def buyer_vkn():
    return os.environ.get("NILVERA_E2E_BUYER_VKN")


@pytest.fixture
def seller_vkn():
    return os.environ.get("NILVERA_E2E_SELLER_VKN")


@pytest.fixture
def sandbox_client(api_key):
    """Provides an authenticated HTTP client locked to the test environment."""
    os.environ["NILVERA_ENV"] = "test"
    os.environ["NILVERA_ENABLED"] = "true"
    import core.integrations.nilvera.config
    core.integrations.nilvera.config._config = None
    
    config = get_nilvera_config()
    assert config.base_url == "https://apitest.nilvera.com", "Sandbox test MUST use apitest.nilvera.com"
    
    return NilveraHttpClient(api_key=api_key)


@pytest_asyncio.fixture
async def sandbox_buyer_alias(sandbox_client, buyer_vkn):
    """Dynamically queries the alias for the test buyer VKN."""
    async with sandbox_client as client:
        service = NilveraTaxpayerService(client)
        result = await service.get_taxpayer_aliases(buyer_vkn)
        
        # We need an active PK alias
        pk_aliases = [a for a in result.aliases if a.startswith("urn:mail:defaultpk")]
        if not pk_aliases:
            # Fallback to any PK alias if defaultpk isn't there
            pk_aliases = [a for a in result.aliases if "pk" in a.lower()]
            
        assert len(pk_aliases) > 0, f"No valid PK alias found for {buyer_vkn}. Aliases: {result.aliases}"
        return pk_aliases[0]


@pytest.mark.external
async def test_taxpayer_query_contract(sandbox_client, buyer_vkn):
    """Test taxpayer query returns valid structure for the buyer VKN."""
    async with sandbox_client as client:
        service = NilveraTaxpayerService(client)
        result = await service.check_taxpayer(buyer_vkn)
        assert result.tax_number == buyer_vkn
        assert isinstance(result.is_e_invoice_user, bool)


@pytest.mark.external
async def test_alias_query_contract(sandbox_client, buyer_vkn, sandbox_buyer_alias):
    """Test alias query and verify a valid alias is retrieved."""
    # Since sandbox_buyer_alias uses the API to fetch it, if it succeeds, the contract is working.
    assert "urn:mail:" in sandbox_buyer_alias
    assert "@" in sandbox_buyer_alias


@pytest.mark.external
async def test_http_400_is_failure(sandbox_client):
    """Verify HTTP 400 (or 422) Validation Error is raised properly."""
    async with sandbox_client as client:
        with pytest.raises(NilveraApiError) as exc_info:
            # Send empty POST payload which could cause a 400 or 500
            await client.post("/einvoice/Send/Model", json={})
        
        assert exc_info.value.http_status in (400, 422, 500)


@pytest.mark.external
async def test_http_401_is_failure(monkeypatch, buyer_vkn):
    """Verify HTTP 401 Auth Error behaves safely."""
    monkeypatch.setenv("NILVERA_ENV", "test")
    monkeypatch.setenv("NILVERA_ENABLED", "true")
    import core.integrations.nilvera.config
    core.integrations.nilvera.config._config = None
    
    client = NilveraHttpClient(api_key="invalid_token")
    assert client._config.base_url == "https://apitest.nilvera.com"
    
    async with client as c:
        with pytest.raises(NilveraAuthError) as exc_info:
            await c.get(f"/general/GlobalCompany/Check/TaxNumber/{buyer_vkn}?globalUserType=Invoice")
        
        assert exc_info.value.http_status in (401, 403)


@pytest.mark.external
async def test_http_500_is_failure(sandbox_client):
    """Verify that HTTP 500 isn't swallowed and comes up as a Server Error."""
    # Since we can't easily force Nilvera to 500, we mock the internal httpx client
    async with sandbox_client as client:
        active = client._get_active_client()
        
        async def mock_send(*args, **kwargs):
            return httpx.Response(500, json={"Errors": [{"Code": "500", "Description": "Internal Server Error"}]}, request=args[0])
            
        active.send = mock_send
        
        with pytest.raises(NilveraServerError) as exc_info:
            await client.get("/some/endpoint")
            
        assert exc_info.value.http_status == 500


@pytest.mark.external
async def test_secret_redaction(monkeypatch, caplog, buyer_vkn, seller_vkn, api_key):
    """Verify that API keys and VKNs do not leak into logs, exceptions or representations."""
    monkeypatch.setenv("NILVERA_ENV", "test")
    monkeypatch.setenv("NILVERA_ENABLED", "true")
    import core.integrations.nilvera.config
    core.integrations.nilvera.config._config = None
    
    # We will force a 401 to ensure the request is logged and the exception is raised
    client = NilveraHttpClient(api_key=api_key)
    
    with caplog.at_level(logging.DEBUG, logger="core.integrations.nilvera"):
        # We manually overwrite the token for this request so it fails but uses the real token format
        invalidated_key = f"{api_key}_invalidated"
        client._api_key = invalidated_key
        
        async with client as c:
            with pytest.raises(NilveraAuthError) as exc_info:
                # We inject VKNs into the payload to see if they leak on error
                await c.get(f"/general/GlobalCompany/Check/TaxNumber/{buyer_vkn}?dummy_seller={seller_vkn}")
                
            exc_str = str(exc_info.value)
            exc_repr = repr(exc_info.value)
            
            # Check Exception messages
            for sensitive in (api_key, invalidated_key, buyer_vkn, seller_vkn):
                if sensitive in exc_str or sensitive in exc_repr:
                    pytest.fail(f"Sensitive data leaked in exception string/repr")
                    
        # Check HTTP Client representation
        client_repr = repr(client)
        if api_key in client_repr or invalidated_key in client_repr:
            pytest.fail("API Key leaked in client repr")
            
        # Check caplog (HTTP debug logs, etc)
        text = caplog.text
        for sensitive in (api_key, invalidated_key, buyer_vkn, seller_vkn):
            if sensitive in text:
                pytest.fail(f"Sensitive data leaked into logs (should be masked)")


@pytest.mark.external
@pytest.mark.side_effect
async def test_sandbox_invoice_submission_and_polling_flow(sandbox_client, buyer_vkn, seller_vkn, sandbox_buyer_alias):
    """
    Side effect test: Submits a single valid invoice to the sandbox 
    and polls its status until terminal.
    """
    request_uuid = uuid.uuid4()
    seller = SellerSnapshot(
        tax_number=seller_vkn,
        name="TEST KURUM 1",
        tax_office="TEST VD",
        country="Türkiye",
        city="İstanbul",
        address="Test Mah. Test Sok. No:1"
    )
    
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
        buyer_tax_number=buyer_vkn,
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
                description="Test Hizmeti Flow Sandbox",
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
    
    payload = NilveraInvoiceMapper.map_to_nilvera(invoice, seller, sandbox_buyer_alias, request_uuid)
    
    async with sandbox_client as client:
        try:
            submit_res = await client.post("/einvoice/Send/Model", json=payload.model_dump(mode='json', by_alias=True))
        except NilveraValidationError as e:
            raw = getattr(e, 'sanitized_preview', str(e))
            detail = getattr(e, 'sanitized_detail', "")
            desc = getattr(e, 'sanitized_description', "")
            pytest.fail(f"Invoice submission failed with 400 Validation Error. API Response: {raw} | Desc: {desc} | Detail: {detail}")
        
        assert "UUID" in submit_res
        assert submit_res["UUID"] != ""
        doc_uuid = submit_res["UUID"]
        
        # 2. Polling config: 1, 2, 4, 5, 5... (max 20 attempts, ~90 seconds total)
        backoffs = [1, 2, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
        
        terminal_status_reached = False
        final_outcome = None
        
        for attempt, delay in enumerate(backoffs, 1):
            await asyncio.sleep(delay)
            
            try:
                status_res = await client.get(f"/einvoice/Sale/{doc_uuid}/Status", timeout=10.0)
            except httpx.TimeoutException:
                pytest.fail("Status polling timed out")
            
            if isinstance(status_res, list) and len(status_res) > 0:
                item = status_res[0]
            elif isinstance(status_res, dict):
                item = status_res
            else:
                pytest.fail("Unexpected response schema from Status endpoint")
                
            if "InvoiceStatus" in item:
                raw_status = item["InvoiceStatus"].get("Code")
                raw_code = str(item.get("EnvelopeInfo", {}).get("GIBCode", item["InvoiceStatus"].get("Description", "")))
            else:
                raw_status = item.get("Status")
                raw_code = str(item.get("StatusCode", ""))
                
            outcome = map_nilvera_status(raw_status, raw_code)
            
            if outcome in (ProviderInvoiceOutcome.ACCEPTED, ProviderInvoiceOutcome.REJECTED):
                terminal_status_reached = True
                final_outcome = outcome
                break
            
            if outcome == ProviderInvoiceOutcome.UNKNOWN:
                pytest.fail(f"Received UNKNOWN status from provider: {raw_status} (Code: {raw_code}). Full response: {status_res}")
        
        if not terminal_status_reached:
            pytest.fail("Timeout: Status remained PENDING after maximum polling attempts")
            
        assert final_outcome in (ProviderInvoiceOutcome.ACCEPTED, ProviderInvoiceOutcome.REJECTED)
