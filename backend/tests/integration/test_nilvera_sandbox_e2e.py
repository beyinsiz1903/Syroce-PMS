import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncService
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import get_nilvera_config
from core.integrations.nilvera.document_service import NilveraDocumentService
from core.integrations.nilvera.errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraServerError,
)
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.incoming_answer import (
    NilveraIncomingAnswerDecision,
    NilveraIncomingAnswerService,
    NilveraIncomingAnswerState,
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

        if not pk_aliases:
            pytest.fail("No valid PK alias found for configured sandbox buyer")
        return pk_aliases[0]


@pytest.mark.external
async def test_taxpayer_query_contract(sandbox_client, buyer_vkn):
    """Test taxpayer query returns valid structure for the buyer VKN."""
    async with sandbox_client as client:
        service = NilveraTaxpayerService(client)
        result = await service.check_taxpayer(buyer_vkn)
        if result.tax_number != buyer_vkn:
            pytest.fail("Taxpayer query returned an unexpected tax identity")
        if not isinstance(result.is_e_invoice_user, bool):
            pytest.fail("Taxpayer query returned an invalid user-status type")


@pytest.mark.external
async def test_alias_query_contract(sandbox_client, buyer_vkn, sandbox_buyer_alias):
    """Test alias query and verify a valid alias is retrieved."""
    # Since sandbox_buyer_alias uses the API to fetch it, if it succeeds, the contract is working.
    if "urn:mail:" not in sandbox_buyer_alias or "@" not in sandbox_buyer_alias:
        pytest.fail("Sandbox buyer alias has an invalid format")


@pytest.mark.external
async def test_http_400_is_failure(sandbox_client):
    """Verify HTTP 400 (or 422) Validation Error is raised properly."""
    async with sandbox_client as client:
        with pytest.raises(NilveraApiError) as exc_info:
            # Send empty POST payload which should cause a validation error (400 or 422)
            await client.post("/einvoice/Send/Model", json={})

        assert exc_info.value.http_status in (400, 422)


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
        tax_office="GELİR İDARESİ",
        country="TÜRKİYE",
        city="ANKARA",
        district="ÇANKAYA",
        address="Çankaya Mah. Ankara Bulvarı No:1",
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
        exchange_rate=Decimal("1.0"),
        issue_date=datetime.now(UTC),
        buyer_tax_number=buyer_vkn,
        buyer_legal_name="TEST KURUM 2",
        buyer_country_name="TÜRKİYE",
        buyer_city="İSTANBUL",
        buyer_district="ŞİŞLİ",
        buyer_address="Şişli Merkez Cad.",
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
                total=Decimal("120.00"),
            )
        ],
    )

    payload = NilveraInvoiceMapper.map_to_nilvera(invoice, seller, sandbox_buyer_alias, request_uuid)

    async with sandbox_client as client:
        try:
            submit_res = await client.post("/einvoice/Send/Model", json=payload.model_dump(mode="json", by_alias=True))
        except NilveraApiError as e:
            pytest.fail(f"Invoice submission failed (error_type={type(e).__name__}, http_status={e.http_status}, retryable={e.retryable})")

        if not isinstance(submit_res, dict):
            pytest.fail(f"Invoice submission returned an invalid response type: {type(submit_res).__name__}")

        doc_uuid = submit_res.get("UUID")
        if not isinstance(doc_uuid, str) or not doc_uuid:
            pytest.fail("Invoice submission response is missing a document UUID")

        # 2. Polling config: 1, 2, 4, 5, 5... (max 30 attempts, ~140 seconds total)
        backoffs = [1, 2, 4] + [5] * 27

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
                pytest.fail(f"Provider status mapping returned UNKNOWN (response_type={type(status_res).__name__})")

        if not terminal_status_reached:
            pytest.fail("Timeout: Status remained PENDING after maximum polling attempts")

        assert final_outcome in (ProviderInvoiceOutcome.ACCEPTED, ProviderInvoiceOutcome.REJECTED)

        # ---------------------------------------------------------
        # Document Download Verification
        # ---------------------------------------------------------
        doc_service = NilveraDocumentService(client)

        pdf_content = await doc_service.download_sale_pdf(doc_uuid)
        if not pdf_content:
            pytest.fail("Downloaded PDF document is empty")
        if not pdf_content.startswith(b"%PDF-"):
            pytest.fail("Downloaded PDF document has an invalid signature")

        xml_content = await doc_service.download_sale_xml(doc_uuid)
        if not xml_content:
            pytest.fail("Downloaded XML document is empty")
        if b"Invoice" not in xml_content and b"invoice" not in xml_content:
            pytest.fail("Downloaded XML document does not contain an invoice root")


@pytest.mark.external
@pytest.mark.side_effect
async def test_sandbox_incoming_commercial_invoice_answer_contract(sandbox_client):
    """Approve only a test-generated commercial invoice after explicit authorization."""
    if os.environ.get("NILVERA_E2E_INCOMING_ANSWER_ALLOWED", "false").lower() != "true":
        pytest.skip("Incoming invoice answer write test requires explicit Sandbox authorization")

    def fail_safely(operation: str, exc: Exception) -> None:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        retryable = exc.retryable if isinstance(exc, NilveraApiError) else None
        pytest.fail(f"Incoming answer {operation} failed (error_type={type(exc).__name__}, http_status={http_status}, retryable={retryable})")

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=31)
    provider_uuid = None

    async with sandbox_client as client:
        incoming_service = NilveraIncomingService(client)
        for _ in range(12):
            try:
                page = await incoming_service.fetch_incoming_invoices(
                    start_date,
                    end_date,
                    page=1,
                    page_size=100,
                )
            except Exception as exc:
                fail_safely("candidate discovery", exc)
            for summary in page.items:
                normalized_answer = "".join(character for character in (summary.answer_code or "").lower() if character.isalnum())
                if not summary.invoice_number.startswith("TST2026"):
                    continue
                if normalized_answer not in {"", "unknown", "waitingforapproval"}:
                    continue
                try:
                    detail = await incoming_service.fetch_incoming_invoice_detail(summary.provider_uuid)
                except Exception as exc:
                    fail_safely("candidate detail query", exc)
                if detail.invoice_profile == "TICARIFATURA":
                    provider_uuid = summary.provider_uuid
                    break
            if provider_uuid is not None:
                break
            await asyncio.sleep(5)

        if provider_uuid is None:
            pytest.fail("No pending test-generated commercial invoice was available for the approved write test")

        answer_service = NilveraIncomingAnswerService(client)
        try:
            await answer_service.send_answer(
                provider_uuid,
                NilveraIncomingAnswerDecision.APPROVED,
            )
        except Exception as exc:
            fail_safely("write", exc)

        for delay in [1, 2, 4, 5, 5, 5, 5, 5, 5, 5]:
            await asyncio.sleep(delay)
            try:
                state = await answer_service.fetch_answer_state(provider_uuid)
            except Exception as exc:
                fail_safely("status query", exc)
            if state == NilveraIncomingAnswerState.APPROVED:
                return
            if state in {
                NilveraIncomingAnswerState.REJECTED,
                NilveraIncomingAnswerState.ANSWERED_AUTOMATICALLY,
            }:
                pytest.fail("Incoming invoice answer reached a conflicting terminal state")

    pytest.fail("Incoming invoice answer remained pending after the verification window")


@pytest.mark.external
async def test_sandbox_incoming_invoice_discovery(sandbox_client):
    """
    Verify incoming list, detail, status, PDF and XML read contracts without
    exposing provider payloads or invoice identifiers in failure output.
    """
    from datetime import timedelta

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=31)

    async with sandbox_client as client:
        incoming_service = NilveraIncomingService(client)
        page = await incoming_service.fetch_incoming_invoices(
            start_date,
            end_date,
            page=1,
            page_size=5,
        )
        if not page.items:
            pytest.fail("Incoming read contracts could not be verified because the configured Sandbox tenant has no invoice in the 31-day window")

        provider_uuid = page.items[0].provider_uuid
        detail = await incoming_service.fetch_incoming_invoice_detail(provider_uuid)
        status = await incoming_service.fetch_incoming_invoice_status(provider_uuid)

        if detail.provider_uuid != provider_uuid:
            pytest.fail("Incoming detail returned a different document identity")
        if detail.issue_date.tzinfo is None or status.issue_date.tzinfo is None:
            pytest.fail("Incoming detail or status returned a naive IssueDate")
        if not status.status_code:
            pytest.fail("Incoming status response is missing its status code")

        doc_service = NilveraDocumentService(client)
        purchase_pdf = await doc_service.download_purchase_pdf(provider_uuid)
        purchase_xml = await doc_service.download_purchase_xml(provider_uuid)
        if not purchase_pdf.startswith(b"%PDF-"):
            pytest.fail("Incoming PDF document has an invalid signature")
        if b"Invoice" not in purchase_xml and b"invoice" not in purchase_xml:
            pytest.fail("Incoming XML document does not contain an invoice root")


@pytest.mark.external
async def test_sandbox_incoming_invoice_sync_is_idempotent(sandbox_client):
    """Persist real Sandbox reads twice in an isolated local tenant."""
    from datetime import timedelta

    mongo_url = os.environ.get("MONGO_URL", "")
    if "localhost" not in mongo_url and "127.0.0.1" not in mongo_url:
        pytest.fail("Incoming persistence E2E requires the isolated local Mongo service")

    from bootstrap.migrations.versions.v005_incoming_invoice_lifecycle import MIGRATION as v005
    from bootstrap.migrations.versions.v007_f2_create_return_models import MIGRATION as v007
    from bootstrap.migrations.versions.v009_incoming_invoice_sync import MIGRATION as v009
    from core.database import _raw_db
    from core.tenant_db import get_db_for_tenant

    await v005.up(_raw_db)
    await v007.up(_raw_db)
    await v009.up(_raw_db)

    tenant_id = f"nilvera-sandbox-e2e-{uuid.uuid4().hex}"
    tenant_db = get_db_for_tenant(tenant_id)
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=31)
    try:
        async with sandbox_client as client:
            first = await IncomingInvoiceSyncService.sync_tenant(
                tenant_id,
                start_date,
                end_date,
                client=client,
            )
            second = await IncomingInvoiceSyncService.sync_tenant(
                tenant_id,
                start_date,
                end_date,
                client=client,
            )

        if first.invoices_seen == 0:
            pytest.fail("Incoming persistence could not be verified because no Sandbox invoice was available")
        if first.unknown_invoices or first.pending_invoices or first.provider_error_invoices:
            pytest.fail("Incoming persistence encountered a non-success provider status")
        if second.invoices_created or second.invoices_changed:
            pytest.fail("The second incoming synchronization changed an unchanged invoice")
        if second.lines_created or second.lines_changed or second.lines_deactivated:
            pytest.fail("The second incoming synchronization changed unchanged invoice lines")

        invoice_count = await tenant_db.incoming_invoices.count_documents({})
        line_count = await tenant_db.incoming_invoice_lines.count_documents({"active": {"$ne": False}})
        if invoice_count != first.invoices_seen:
            pytest.fail("Incoming synchronization did not persist exactly one record per provider invoice")
        if line_count == 0:
            pytest.fail("Incoming synchronization did not persist invoice lines")
    finally:
        await tenant_db.incoming_invoice_lines.delete_many({})
        await tenant_db.incoming_invoices.delete_many({})
        await tenant_db.incoming_invoice_sync_state.delete_many({})
