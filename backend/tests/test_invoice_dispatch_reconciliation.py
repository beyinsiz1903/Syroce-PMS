import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_dispatch_service import InvoiceDispatchService
from core.integrations.invoice_dispatch_worker import invoice_dispatch_worker
from core.integrations.invoice_reconciliation_service import InvoiceReconciliationService
from core.integrations.invoice_reconciliation_worker import InvoiceReconciliationWorker
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.integrations.nilvera.errors import NilveraApiError, NilveraTimeoutError
from core.tenant_db import get_db_for_tenant, get_system_db
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState


@pytest.fixture
def mock_now():
    return datetime(2026, 7, 18, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
async def setup_sync_record(request: pytest.FixtureRequest, mock_now: datetime) -> InvoiceSync:
    tenant_id = "test_tenant"
    db = get_db_for_tenant(tenant_id)
    sysdb = get_system_db()

    # Clear existing
    await db.invoice_sync.delete_many({})
    await sysdb.invoice_sync.delete_many({})

    record = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        invoice_id="inv-123",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="test-idem",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.QUEUED,
        prepared_at=mock_now,
        created_at=mock_now,
        updated_at=mock_now,
        sending_at=mock_now,
        last_attempt_at=mock_now,
    )
    await sysdb.invoice_sync.insert_one(record.model_dump(mode="json"))
    await db.invoice_sync.insert_one(record.model_dump(mode="json"))
    return record


@pytest.fixture
def nilvera_client_mock():
    with patch("core.integrations.nilvera.client.NilveraHttpClient.post", new_callable=AsyncMock) as post_mock, \
         patch("core.integrations.nilvera.client.NilveraHttpClient.get", new_callable=AsyncMock) as get_mock:
        yield {"post": post_mock, "get": get_mock}


@pytest.fixture
def fake_reader(nilvera_client_mock):
    class FakeReader:
        async def get_sale_status(self, uuid_str: str) -> dict:
            return await nilvera_client_mock["get"](f"Status:{uuid_str}")
        async def get_sale_details(self, uuid_str: str) -> dict:
            return await nilvera_client_mock["get"](f"Details:{uuid_str}")
    return FakeReader()


@pytest.mark.asyncio
async def test_post_timeout_goes_to_reconciliation(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime):
    # Setup worker to process QUEUED
    nilvera_client_mock["post"].side_effect = NilveraTimeoutError(message="Timeout", correlation_id="x")

    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.SENDING, {
        "lease_owner": "worker-1", "lease_expires_at": mock_now + timedelta(minutes=5)
    })
    record.state = InvoiceSyncState.SENDING

    # Insert required documents into DB
    sysdb = get_system_db()
    await sysdb.invoices.insert_one({
        "id": record.invoice_id, "tenant_id": record.tenant_id, "invoice_type": "SATIS", "buyer_alias": "test", "invoice_number": "INV-123", "document_kind": "E_INVOICE", "items": [{"name": "Item", "description": "Item", "quantity": 1, "unit_price": 100, "total": 100}]
    })
    await sysdb.companies.insert_one({
        "vkn": "1234567890", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"
    })

    dummy_payload = MagicMock()
    dummy_payload.model_dump.return_value = {"dummy": "data"}
    with patch("core.integrations.invoice_dispatch_service.get_nilvera_tenant_config", return_value={"enabled": True, "api_key": "test", "seller": {"vkn": "123", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"}}):
        with patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper.map_to_nilvera", return_value=dummy_payload):
            await InvoiceDispatchService.execute_dispatch(record.tenant_id, record.id, "worker-1")

    # Check state
    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.RECONCILIATION_REQUIRED, updated.get("last_error_message")
    assert updated["reconciliation_required"] is True
    assert "TIMEOUT" in updated["reconciliation_reason"]


@pytest.mark.asyncio
async def test_reconciliation_404_provider_code_3003(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime, fake_reader):
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.RECONCILIATION_REQUIRED, {"status_lease_owner": "worker-2", "status_lease_expires_at": mock_now + timedelta(minutes=5), "current_reconciliation_cycle_id": "cycle-1"})
    record.version += 1 # Transition increments version

    nilvera_client_mock["get"].side_effect = NilveraApiError(message="Not found", http_status=404, provider_code="3003")

    with patch("core.integrations.invoice_reconciliation_service.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await InvoiceReconciliationService.execute_reconciliation(record.tenant_id, record.id, record.version, "worker-2", fake_reader)

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.RECONCILIATION_REQUIRED, updated
    assert updated["not_found_count"] == 1
    assert updated["reconciliation_attempt_count"] == 1


@pytest.mark.asyncio
async def test_reconciliation_404_provider_code_3009_invalid(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime, fake_reader):
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.RECONCILIATION_REQUIRED, {"status_lease_owner": "worker-2", "status_lease_expires_at": mock_now + timedelta(minutes=5)})
    record.version += 1 # Transition increments version

    nilvera_client_mock["get"].side_effect = NilveraApiError(message="Series not defined", http_status=404, provider_code="3009")

    with patch("core.integrations.invoice_reconciliation_service.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await InvoiceReconciliationService.execute_reconciliation(record.tenant_id, record.id, record.version, "worker-2", fake_reader)

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.RECONCILIATION_REQUIRED, updated
    assert updated["not_found_count"] == 0
    assert updated["reconciliation_attempt_count"] == 1


@pytest.mark.asyncio
async def test_reconciliation_status_200_details_404(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime, fake_reader):
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.RECONCILIATION_REQUIRED, {"status_lease_owner": "worker-2", "status_lease_expires_at": mock_now + timedelta(minutes=5)})
    record.version += 1 # Transition increments version

    async def get_side_effect(*args, **kwargs):
        if "Status" in args[0]:
            return {"UUID": record.request_uuid}
        elif "Details" in args[0]:
            raise NilveraApiError(message="Not found", http_status=404, provider_code="3003")
        return {}

    nilvera_client_mock["get"].side_effect = get_side_effect

    with patch("core.integrations.invoice_reconciliation_service.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await InvoiceReconciliationService.execute_reconciliation(record.tenant_id, record.id, record.version, "worker-2", fake_reader)

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.RECONCILIATION_REQUIRED, updated
    assert "Contradiction" in updated["reconciliation_note"]
    assert updated["not_found_count"] == 0
    assert updated["reconciliation_attempt_count"] == 1


@pytest.mark.asyncio
async def test_reconciliation_safe_to_retry_transition(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime, fake_reader):
    record = setup_sync_record

    # Simulate past attempts (2 not founds, 15+ mins ago)
    await InvoiceSyncRepository.transition_state(
        record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.RECONCILIATION_REQUIRED,
        {"not_found_count": 2, "reconciliation_attempt_count": 2, "first_not_found_at": mock_now - timedelta(minutes=16), "sending_at": mock_now - timedelta(minutes=16), "status_lease_owner": "worker-2", "status_lease_expires_at": mock_now + timedelta(minutes=5), "current_reconciliation_cycle_id": "cycle-3"}
    )
    record.version += 1 # Transition increments version

    nilvera_client_mock["get"].side_effect = NilveraApiError(message="Not found", http_status=404, provider_code="3003")

    with patch("core.integrations.invoice_reconciliation_service.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await InvoiceReconciliationService.execute_reconciliation(record.tenant_id, record.id, record.version, "worker-2", fake_reader)

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.SAFE_TO_RETRY
    assert updated["not_found_count"] == 3


@pytest.mark.asyncio
async def test_reconciliation_max_redispatch_reached(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime, fake_reader):
    record = setup_sync_record

    await InvoiceSyncRepository.transition_state(
        record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.RECONCILIATION_REQUIRED,
        {"not_found_count": 2, "redispatch_count": 1, "first_not_found_at": mock_now - timedelta(minutes=16), "sending_at": mock_now - timedelta(minutes=16), "status_lease_owner": "worker-2", "status_lease_expires_at": mock_now + timedelta(minutes=5), "current_reconciliation_cycle_id": "cycle-3"}
    )
    record.version += 1 # Transition increments version

    nilvera_client_mock["get"].side_effect = NilveraApiError(message="Not found", http_status=404, provider_code="3003")

    with patch("core.integrations.invoice_reconciliation_service.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await InvoiceReconciliationService.execute_reconciliation(record.tenant_id, record.id, record.version, "worker-2", fake_reader)

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    # Cannot go to SAFE_TO_RETRY because redispatch_count == 1
    assert updated["state"] == InvoiceSyncState.MANUAL_REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_reconciliation_worker_no_post_access():
    worker = InvoiceReconciliationWorker()
    assert not hasattr(worker, "post")
    # Worker is explicitly separated and doesn't load InvoiceDispatchService


@pytest.mark.asyncio
async def test_dispatch_409_known_duplicate_codes(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime):
    nilvera_client_mock["post"].side_effect = NilveraApiError(message="Conflict", http_status=409, provider_code="1004")
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.SENDING, {
        "lease_owner": "worker-1", "lease_expires_at": mock_now + timedelta(minutes=5)
    })
    record.state = InvoiceSyncState.SENDING

    # Insert required documents into DB
    sysdb = get_system_db()
    await sysdb.invoices.insert_one({
        "id": record.invoice_id, "tenant_id": record.tenant_id, "invoice_type": "SATIS", "buyer_alias": "test", "invoice_number": "INV-123", "document_kind": "E_INVOICE", "items": [{"name": "Item", "description": "Item", "quantity": 1, "unit_price": 100, "total": 100}]
    })
    await sysdb.companies.insert_one({
        "vkn": "1234567890", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"
    })
    dummy_payload = MagicMock()
    dummy_payload.model_dump.return_value = {"dummy": "data"}
    with patch("core.integrations.invoice_dispatch_service.get_nilvera_tenant_config", return_value={"enabled": True, "api_key": "test", "seller": {"vkn": "123", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"}}):
        with patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper.map_to_nilvera", return_value=dummy_payload):
            await InvoiceDispatchService.execute_dispatch(record.tenant_id, record.id, "worker-1")

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.RECONCILIATION_REQUIRED, updated
    assert updated["reconciliation_reason"] == "DUPLICATE_1004"


@pytest.mark.asyncio
async def test_dispatch_409_known_permanent_codes(setup_sync_record: InvoiceSync, nilvera_client_mock: dict[str, AsyncMock], mock_now: datetime):
    nilvera_client_mock["post"].side_effect = NilveraApiError(message="Conflict", http_status=409, provider_code="1000")
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.SENDING, {
        "lease_owner": "worker-1", "lease_expires_at": mock_now + timedelta(minutes=5)
    })
    record.state = InvoiceSyncState.SENDING

    # Insert required documents into DB
    sysdb = get_system_db()
    await sysdb.invoices.insert_one({
        "id": record.invoice_id, "tenant_id": record.tenant_id, "invoice_type": "SATIS", "buyer_alias": "test", "invoice_number": "INV-123", "document_kind": "E_INVOICE", "items": [{"name": "Item", "description": "Item", "quantity": 1, "unit_price": 100, "total": 100}]
    })
    await sysdb.companies.insert_one({
        "vkn": "1234567890", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"
    })

    dummy_payload = MagicMock()
    dummy_payload.model_dump.return_value = {"dummy": "data"}
    with patch("core.integrations.invoice_dispatch_service.get_nilvera_tenant_config", return_value={"enabled": True, "api_key": "test", "seller": {"vkn": "123", "name": "Test", "tax_office": "Test", "address": "Test", "city": "Test", "country": "Test"}}):
        with patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper.map_to_nilvera", return_value=dummy_payload):
            await InvoiceDispatchService.execute_dispatch(record.tenant_id, record.id, "worker-1")

    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.PERMANENT_ERROR


@pytest.mark.asyncio
async def test_dispatch_worker_safe_to_retry_claim(setup_sync_record: InvoiceSync, mock_now: datetime):
    record = setup_sync_record
    await InvoiceSyncRepository.transition_state(record.tenant_id, record.id, InvoiceSyncState.QUEUED, InvoiceSyncState.SAFE_TO_RETRY, {"redispatch_count": 0})

    with patch("core.integrations.invoice_dispatch_worker._utc_now", return_value=mock_now):
        processed = await invoice_dispatch_worker._claim_and_queue_safe_to_retry()

    assert processed == 1
    sysdb = get_system_db()
    updated = await sysdb.invoice_sync.find_one({"id": record.id})
    assert updated["state"] == InvoiceSyncState.QUEUED
    assert updated["redispatch_count"] == 1
