import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncService
from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
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
    NilveraIncomingAnswerService,
    NilveraIncomingAnswerState,
)
from core.integrations.nilvera.mapper import NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome, map_nilvera_status
from core.integrations.nilvera.taxpayer import NilveraTaxpayerService
from models.schemas.incoming_invoice import (
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)
from models.schemas.invoicing import Invoice, InvoiceItem
from tests.nilvera_sandbox_fixture import (
    BLOCKED_NOT_FOUND_AFTER_EXHAUSTIVE_READ,
    FOUND,
    MATCH_COUNT_ZERO,
    NOT_FOUND_OR_NOT_VISIBLE,
    ReadOnlySandboxClient,
    SandboxFixtureError,
    build_fixture_identity,
    build_fixture_request_uuid,
    company_identity_matches,
    ensure_distinct_sandbox_keys,
    pilot_invoice_datetime,
    prepare_incoming_commercial_fixture,
    reconcile_incoming_commercial_fixture,
)

# Mark all tests in this file as nilvera_sandbox
pytestmark = [pytest.mark.asyncio, pytest.mark.nilvera_sandbox]


@pytest.mark.external
async def test_sandbox_incoming_fixture_accounts_preflight(record_property):
    """Verify both Sandbox accounts using GET only and emit safe booleans."""
    sender_key = os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY", "")
    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")

    try:
        ensure_distinct_sandbox_keys(sender_key, receiver_key)
    except SandboxFixtureError as exc:
        pytest.fail(exc.safe_code, pytrace=False)

    sender_client = new_sandbox_client(sender_key)
    receiver_client = new_sandbox_client(receiver_key)
    try:
        async with sender_client as sender, receiver_client as receiver:
            sender_match = await company_identity_matches(sender, seller_tax_number)
            receiver_match = await company_identity_matches(receiver, buyer_tax_number)
    except SandboxFixtureError as exc:
        record_property("provider_write_count", "0")
        pytest.fail(exc.safe_code, pytrace=False)

    record_property("sender_match", str(sender_match).lower())
    record_property("receiver_match", str(receiver_match).lower())
    record_property("provider_write_count", "0")
    if not sender_match or not receiver_match:
        pytest.fail("BLOCKED_COMPANY_IDENTITY_MISMATCH", pytrace=False)


def check_missing_secrets() -> bool:
    """Return True if any required secret is missing."""
    buyer = os.environ.get("NILVERA_E2E_BUYER_VKN")
    seller = os.environ.get("NILVERA_E2E_SELLER_VKN")
    sender_key = os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY")
    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY")
    fixture_mode = os.environ.get("NILVERA_E2E_INCOMING_FIXTURE_ALLOWED", "false").lower() == "true"
    answer_mode = os.environ.get("NILVERA_E2E_INCOMING_ANSWER_ALLOWED", "false").lower() == "true"
    reconciliation_mode = os.environ.get("NILVERA_E2E_RECONCILIATION_ALLOWED", "false").lower() == "true"

    if fixture_mode or reconciliation_mode or answer_mode:
        hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY")
        run_id_name = "NILVERA_E2E_RUN_ID" if fixture_mode else "NILVERA_E2E_SOURCE_RUN_ID"
        run_id = os.environ.get(run_id_name)
        source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP") if not fixture_mode else "not-required"
        selected_keys_present = bool(sender_key and receiver_key) if not answer_mode else bool(receiver_key)
        return not (selected_keys_present and hmac_key and run_id and source_timestamp and buyer and seller)
    selected_key = receiver_key if answer_mode else sender_key
    return not (selected_key and buyer and seller)


@pytest.fixture(autouse=True)
def skip_if_missing_secrets():
    """Skip E2E test if required secrets are missing."""
    if check_missing_secrets():
        pytest.skip("Missing required Nilvera Sandbox configuration. Skipping real sandbox E2E tests.")


@pytest.fixture
def api_key():
    if os.environ.get("NILVERA_E2E_INCOMING_ANSWER_ALLOWED", "false").lower() == "true":
        return os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY")
    return os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY")


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


def new_sandbox_client(api_key: str) -> NilveraHttpClient:
    """Create a separate client while retaining the sandbox-only host guard."""
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
        series="SYR",
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
async def test_sandbox_prepare_incoming_commercial_invoice_fixture(record_property):
    """Create at most one commercial Sandbox fixture and verify receiver visibility."""
    if os.environ.get("NILVERA_E2E_INCOMING_FIXTURE_ALLOWED", "false").lower() != "true":
        pytest.skip("Incoming fixture write test requires explicit Sandbox authorization")

    sender_key = os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY", "")
    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    run_id = os.environ.get("NILVERA_E2E_RUN_ID", "")
    pilot_invoice_date = os.environ.get("NILVERA_PILOT_INVOICE_DATE")
    try:
        workflow_run_attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError:
        pytest.fail("BLOCKED_INVALID_FIXTURE_RUN_ATTEMPT", pytrace=False)
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")

    try:
        ensure_distinct_sandbox_keys(sender_key, receiver_key)
    except SandboxFixtureError as exc:
        pytest.fail(exc.safe_code, pytrace=False)

    sender_client = new_sandbox_client(sender_key)
    receiver_client = new_sandbox_client(receiver_key)
    async with sender_client as sender, receiver_client as receiver:
        try:
            aliases = await NilveraTaxpayerService(sender).get_taxpayer_aliases(buyer_tax_number)
        except Exception as exc:
            pytest.fail(f"BLOCKED_FIXTURE_ALIAS_QUERY (error_type={type(exc).__name__})", pytrace=False)
        buyer_aliases = [alias for alias in aliases.aliases if "pk" in alias.lower()]
        if not buyer_aliases:
            pytest.fail("BLOCKED_FIXTURE_BUYER_ALIAS")

        try:
            result = await prepare_incoming_commercial_fixture(
                sender_client=sender,
                receiver_client=receiver,
                sender_key=sender_key,
                receiver_key=receiver_key,
                hmac_key=hmac_key,
                run_id=run_id,
                seller_tax_number=seller_tax_number,
                buyer_tax_number=buyer_tax_number,
                buyer_alias=buyer_aliases[0],
                pilot_invoice_date=pilot_invoice_date,
                workflow_run_attempt=workflow_run_attempt,
            )
        except SandboxFixtureError as exc:
            record_property("provider_write_count", str(exc.provider_write_count))
            safe_metadata = {
                "failure_stage": exc.failure_stage,
                "http_status": str(exc.http_status) if exc.http_status is not None else None,
                "http_status_class": exc.http_status_class,
                "provider_code": exc.provider_code,
                "validation_issue": exc.validation_issue,
                "validation_detail": exc.validation_detail,
                "exception_type": exc.exception_type,
                "write_disposition": exc.write_disposition,
                "classification": exc.classification,
            }
            for name, value in safe_metadata.items():
                if value is not None:
                    record_property(name, value)
            pytest.fail(exc.safe_code, pytrace=False)

    record_property("correlation_label", result.correlation_label)
    record_property("provider_write_count", str(result.provider_write_count))
    record_property("sender_match", str(result.sender_match).lower())
    record_property("receiver_match", str(result.receiver_match).lower())
    record_property("provider_outcome", result.provider_outcome.value)
    record_property("receiver_visible", str(result.receiver_visible).lower())


@pytest.mark.external
async def test_sandbox_reconcile_incoming_commercial_invoice_fixture(record_property):
    """Reconcile one prior fixture using company-verified, non-retrying GET requests."""
    if os.environ.get("NILVERA_E2E_RECONCILIATION_ALLOWED", "false").lower() != "true":
        pytest.skip("Incoming fixture reconciliation requires explicit Sandbox authorization")

    sender_key = os.environ.get("NILVERA_E2E_SENDER_SANDBOX_KEY", "")
    receiver_key = os.environ.get("NILVERA_E2E_RECEIVER_SANDBOX_KEY", "")
    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP", "")
    buyer_tax_number = os.environ.get("NILVERA_E2E_BUYER_VKN", "")
    seller_tax_number = os.environ.get("NILVERA_E2E_SELLER_VKN", "")

    try:
        reference_time = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise ValueError
        ensure_distinct_sandbox_keys(sender_key, receiver_key)
    except (SandboxFixtureError, ValueError) as exc:
        safe_code = exc.safe_code if isinstance(exc, SandboxFixtureError) else "BLOCKED_INVALID_RECONCILIATION_SOURCE_YEAR"
        pytest.fail(safe_code, pytrace=False)

    sender_client = new_sandbox_client(sender_key)
    receiver_client = new_sandbox_client(receiver_key)
    async with sender_client as sender, receiver_client as receiver:
        try:
            result = await reconcile_incoming_commercial_fixture(
                sender_client=ReadOnlySandboxClient(sender),
                receiver_client=ReadOnlySandboxClient(receiver),
                sender_key=sender_key,
                receiver_key=receiver_key,
                hmac_key=hmac_key,
                run_id=source_run_id,
                seller_tax_number=seller_tax_number,
                buyer_tax_number=buyer_tax_number,
                reference_time=reference_time,
            )
        except SandboxFixtureError as exc:
            record_property("provider_write_count", "0")
            if exc.sender_match is not None:
                record_property("sender_match", str(exc.sender_match).lower())
            if exc.receiver_match is not None:
                record_property("receiver_match", str(exc.receiver_match).lower())
            if exc.match_count_class is not None:
                record_property("match_count_class", exc.match_count_class)
            if exc.sender_page_count_class is not None:
                record_property("sender_page_count_class", exc.sender_page_count_class)
            if exc.receiver_page_count_class is not None:
                record_property("receiver_page_count_class", exc.receiver_page_count_class)
            safe_metadata = {
                "failure_stage": exc.failure_stage,
                "http_status": str(exc.http_status) if exc.http_status is not None else None,
                "http_status_class": exc.http_status_class,
                "provider_code": exc.provider_code,
                "exception_type": exc.exception_type,
            }
            for name, value in safe_metadata.items():
                if value is not None:
                    record_property(name, value)
            pytest.fail(exc.safe_code, pytrace=False)

    provider_status_class = result.outgoing_outcome.name if result.outgoing_outcome is not None else "NOT_AVAILABLE"
    outgoing_found = result.outgoing_result == FOUND
    receiver_visible = result.receiver_visibility == FOUND
    record_property("provider_write_count", str(result.provider_write_count))
    record_property("sender_match", str(result.sender_match).lower())
    record_property("receiver_match", str(result.receiver_match).lower())
    record_property("outgoing_found", str(outgoing_found).lower())
    record_property("receiver_visible", str(receiver_visible).lower())
    record_property("match_count_class", result.match_count_class)
    record_property("provider_status_class", provider_status_class)
    record_property("sender_page_count_class", result.sender_page_count_class)
    record_property("receiver_page_count_class", result.receiver_page_count_class)
    record_property("http_status", str(result.http_status) if result.http_status is not None else "NOT_APPLICABLE")
    record_property("provider_code", "NOT_APPLICABLE")

    if result.match_count_class == MATCH_COUNT_ZERO:
        pytest.fail(BLOCKED_NOT_FOUND_AFTER_EXHAUSTIVE_READ, pytrace=False)
    if result.outgoing_outcome == ProviderInvoiceOutcome.REJECTED:
        pytest.fail("FIXTURE_RECONCILIATION_PROVIDER_REJECTED", pytrace=False)
    if result.outgoing_outcome in {ProviderInvoiceOutcome.PENDING, ProviderInvoiceOutcome.UNKNOWN}:
        pytest.fail("BLOCKED_FIXTURE_RECONCILIATION_PROVIDER_NOT_TERMINAL", pytrace=False)
    if not receiver_visible or result.receiver_status_ready is not True:
        pytest.fail(NOT_FOUND_OR_NOT_VISIBLE, pytrace=False)


@pytest.mark.external
@pytest.mark.side_effect
async def test_sandbox_incoming_commercial_invoice_answer_contract(sandbox_client, record_property):
    """Approve one test invoice through the persisted lifecycle after authorization."""
    if os.environ.get("NILVERA_E2E_INCOMING_ANSWER_ALLOWED", "false").lower() != "true":
        pytest.skip("Incoming invoice answer write test requires explicit Sandbox authorization")

    def fail_safely(operation: str, exc: Exception) -> None:
        http_status = exc.http_status if isinstance(exc, NilveraApiError) else None
        retryable = exc.retryable if isinstance(exc, NilveraApiError) else None
        pytest.fail(f"Incoming answer {operation} failed (error_type={type(exc).__name__}, http_status={http_status}, retryable={retryable})")

    mongo_url = os.environ.get("MONGO_URL", "")
    if "localhost" not in mongo_url and "127.0.0.1" not in mongo_url:
        pytest.fail("Incoming answer lifecycle E2E requires the isolated local Mongo service")

    hmac_key = os.environ.get("NILVERA_E2E_CORRELATION_HMAC_KEY", "")
    source_run_id = os.environ.get("NILVERA_E2E_SOURCE_RUN_ID", "")
    source_timestamp = os.environ.get("NILVERA_E2E_SOURCE_RUN_TIMESTAMP", "")
    try:
        reference_time = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise ValueError
        fixture_time = pilot_invoice_datetime(os.environ.get("NILVERA_PILOT_INVOICE_DATE"))
        identity = build_fixture_identity(
            year=fixture_time.year,
            run_id=source_run_id,
            hmac_key=hmac_key,
        )
        target_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))
    except (SandboxFixtureError, ValueError):
        pytest.fail("BLOCKED_INVALID_ANSWER_FIXTURE_SOURCE", pytrace=False)

    from bootstrap.migrations.versions.v005_incoming_invoice_lifecycle import MIGRATION as v005
    from bootstrap.migrations.versions.v006_incoming_invoice_answer_atomicity import MIGRATION as v006
    from bootstrap.migrations.versions.v007_f2_create_return_models import MIGRATION as v007
    from bootstrap.migrations.versions.v009_incoming_invoice_sync import MIGRATION as v009
    from core.database import _raw_db
    from core.tenant_db import get_db_for_tenant

    await v005.up(_raw_db)
    await v006.up(_raw_db)
    await v007.up(_raw_db)
    await v009.up(_raw_db)

    tenant_id = f"nilvera-answer-e2e-{uuid.uuid4().hex}"
    tenant_db = get_db_for_tenant(tenant_id)
    end_date = fixture_time + timedelta(days=1)
    start_date = fixture_time - timedelta(days=31)
    provider_uuid = None
    provider_write_count = 0
    provider_state = NilveraIncomingAnswerState.UNKNOWN
    lifecycle_state: InvoiceLifecycleActionState | None = None

    class BorrowedClientContext:
        def __init__(self, client):
            self.client = client

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

    try:
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
                    normalized_status = "".join(character for character in (summary.status_code or "").upper() if character.isalnum())
                    if summary.provider_uuid != target_provider_uuid:
                        continue
                    if normalized_answer not in {"", "waitingforapproval"}:
                        continue
                    if normalized_status not in {"SUCCEED", "SUCCESS"}:
                        continue
                    try:
                        detail = await incoming_service.fetch_incoming_invoice_detail(summary.provider_uuid)
                        status = await incoming_service.fetch_incoming_invoice_status(summary.provider_uuid)
                    except Exception as exc:
                        fail_safely("candidate verification", exc)
                    if detail.provider_uuid != target_provider_uuid or detail.invoice_profile != "TICARIFATURA":
                        continue
                    verified_answer = "".join(character for character in (status.answer_code or "").lower() if character.isalnum())
                    verified_status = "".join(character for character in status.status_code.upper() if character.isalnum())
                    if verified_answer in {"", "waitingforapproval"} and verified_status in {"SUCCEED", "SUCCESS"}:
                        provider_uuid = summary.provider_uuid
                        break
                if provider_uuid is not None:
                    break
                await asyncio.sleep(5)

            if provider_uuid is None:
                pytest.fail("BLOCKED_NO_ELIGIBLE_TEST_INVOICE")

            try:
                await IncomingInvoiceSyncService.sync_tenant(
                    tenant_id,
                    start_date,
                    end_date,
                    client=client,
                )
            except Exception as exc:
                fail_safely("local synchronization", exc)

            invoice = await IncomingInvoiceRepository.get_by_provider_uuid(tenant_id, provider_uuid)
            if invoice is None:
                pytest.fail("Eligible Sandbox invoice was not persisted locally")
            if invoice.profile != IncomingInvoiceProfile.COMMERCIAL:
                pytest.fail("Eligible Sandbox invoice has an invalid local profile")
            if invoice.answer_status != IncomingInvoiceAnswerStatus.PENDING:
                pytest.fail("Eligible Sandbox invoice is not locally pending")
            if invoice.provider_status != IncomingInvoiceProviderStatus.SUCCEED:
                pytest.fail("Eligible Sandbox invoice is not locally provider-ready")

            action = InvoiceLifecycleAction(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                direction=InvoiceLifecycleDirection.INCOMING,
                source_invoice_id=invoice.id,
                source_provider_uuid=provider_uuid,
                action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
                state=InvoiceLifecycleActionState.REQUESTED,
                request_uuid=str(uuid.uuid4()),
                idempotency_key=f"{tenant_id}:sandbox-answer:{invoice.id}",
                request_fingerprint="sandbox-incoming-approve-v1",
                answer_guard_key=invoice.id,
                requested_by="sandbox-e2e",
                requested_at=datetime.now(UTC),
            )
            if await InvoiceLifecycleRepository.create_action(action) != ActionCreationResult.SUCCESS:
                pytest.fail("Sandbox lifecycle action could not be created")

            borrowed_context = BorrowedClientContext(client)
            with (
                patch.object(client, "post", wraps=client.post) as provider_post,
                patch(
                    "core.integrations.invoice_lifecycle_service.get_nilvera_tenant_config",
                    new=AsyncMock(return_value={"enabled": True, "api_key": "sandbox-e2e-present"}),
                ),
                patch(
                    "core.integrations.invoice_lifecycle_service.NilveraHttpClient",
                    return_value=borrowed_context,
                ),
                patch(
                    "core.integrations.invoice_lifecycle_service.event_bus.publish",
                    new=AsyncMock(return_value={}),
                ),
                patch(
                    "core.integrations.invoice_lifecycle_service.STATUS_POLL_DELAYS",
                    (1, 2, 4, 5, 5),
                ),
            ):
                for delay in (0, 1.5, 2.5, 4.5, 5.5, 5.5):
                    if delay:
                        await asyncio.sleep(delay)
                    try:
                        await InvoiceLifecycleService.process_lifecycle_action(
                            tenant_id,
                            action.id,
                            "sandbox-e2e-worker",
                        )
                        persisted_action = await InvoiceLifecycleRepository.get_by_id(tenant_id, action.id)
                    except Exception as exc:
                        provider_write_count = provider_post.await_count
                        pytest.fail(f"Incoming answer lifecycle processing failed (error_type={type(exc).__name__}, write_count={provider_write_count})")
                    if persisted_action is None:
                        pytest.fail("Sandbox lifecycle action disappeared during processing")
                    lifecycle_state = persisted_action.state
                    if lifecycle_state in {
                        InvoiceLifecycleActionState.SUCCEEDED,
                        InvoiceLifecycleActionState.FAILED,
                        InvoiceLifecycleActionState.RECONCILIATION_REQUIRED,
                    }:
                        break
                provider_write_count = provider_post.await_count

            try:
                provider_state = await NilveraIncomingAnswerService(client).fetch_answer_state(provider_uuid)
            except Exception as exc:
                fail_safely("final provider status query", exc)

            persisted_invoice = await IncomingInvoiceRepository.get_by_id(tenant_id, invoice.id)
            if provider_write_count != 1:
                pytest.fail(f"Incoming answer provider write count is invalid (write_count={provider_write_count})")
            if provider_state != NilveraIncomingAnswerState.APPROVED:
                pytest.fail(f"Incoming answer provider state is not approved (state={provider_state.value})")
            if lifecycle_state != InvoiceLifecycleActionState.SUCCEEDED:
                safe_state = lifecycle_state.value if lifecycle_state is not None else "MISSING"
                pytest.fail(f"Incoming answer lifecycle state is not successful (state={safe_state})")
            if persisted_invoice is None or persisted_invoice.answer_status != IncomingInvoiceAnswerStatus.APPROVED:
                pytest.fail("Incoming answer local invoice state is not approved")

            record_property("provider_write_count", str(provider_write_count))
            record_property("provider_answer_state", provider_state.value)
            record_property("lifecycle_state", lifecycle_state.value)
    finally:
        await tenant_db.invoice_lifecycle_actions.delete_many({})
        await tenant_db.incoming_invoice_lines.delete_many({})
        await tenant_db.incoming_invoices.delete_many({})
        await tenant_db.incoming_invoice_sync_state.delete_many({})


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
