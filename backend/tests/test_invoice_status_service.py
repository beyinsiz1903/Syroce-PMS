from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.invoice_status_service import InvoiceStatusService
from core.integrations.nilvera.errors import NilveraApiError
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_repo():
    with patch("core.integrations.invoice_status_service.InvoiceStatusRepository.update_status_poll_result") as mock:
        mock.return_value = True
        yield mock

@pytest.fixture
def mock_config():
    with patch("core.integrations.invoice_status_service.get_nilvera_tenant_config") as mock:
        mock.side_effect = AsyncMock(return_value={"enabled": True, "api_key": "test_key"})
        yield mock

async def test_invalid_provider_uuid(mock_repo, mock_config):
    record = create_mock_sync(provider_doc_id="not-a-uuid")
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    mock_repo.assert_called_once()
    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is True
    assert updates.get("reconciliation_reason") == "INVALID_PROVIDER_UUID"

def create_mock_sync(provider_doc_id="12345678-1234-5678-1234-567812345678", tracking_started_at=None) -> InvoiceSync:
    now = datetime.now(UTC)
    return InvoiceSync(
        id="sync-1",
        tenant_id="tenant-1",
        invoice_id="inv-1",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash",
        request_uuid="req-123",
        state=InvoiceSyncState.SUBMITTED,
        provider_document_id=provider_doc_id,
        status_tracking_started_at=tracking_started_at or now,
        prepared_at=now,
        created_at=now,
        updated_at=now,
    )

async def test_24_hour_timeout(mock_repo, mock_config):
    old_time = datetime.now(UTC) - timedelta(hours=25)
    record = create_mock_sync(tracking_started_at=old_time)
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    mock_repo.assert_called_once()
    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is True
    assert updates.get("reconciliation_reason") == "STATUS_TIMEOUT_24H"
    assert updates.get("next_status_check_at") is None

async def test_missing_provider_document_id(mock_repo, mock_config):
    record = create_mock_sync(provider_doc_id=None)
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    mock_repo.assert_called_once()
    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is True
    assert updates.get("reconciliation_reason") == "MISSING_PROVIDER_DOCUMENT_ID"

@patch("core.integrations.invoice_status_service.NilveraHttpClient")
async def test_successful_pending(mock_client_cls, mock_repo, mock_config):
    mock_client = AsyncMock()
    mock_client.get.return_value = {"Status": "Kuyrukta", "StatusCode": "1000"}
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    record = create_mock_sync()
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    updates = mock_repo.call_args[0][3]
    assert "state" not in updates  # Remains SUBMITTED
    assert updates.get("provider_status") == "Kuyrukta"
    assert "next_status_check_at" in updates

@patch("core.integrations.invoice_status_service.NilveraHttpClient")
@patch("core.integrations.invoice_status_service.event_bus")
async def test_successful_accepted(mock_event_bus, mock_client_cls, mock_repo, mock_config):
    mock_client = AsyncMock()
    mock_client.get.return_value = {"Status": "Başarılı", "StatusCode": "1300"}
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    mock_event_bus.publish = AsyncMock()
    record = create_mock_sync()
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    updates = mock_repo.call_args[0][3]
    assert updates.get("state") == InvoiceSyncState.ACCEPTED.value
    assert updates.get("next_status_check_at") is None
    mock_event_bus.publish.assert_called_once_with("invoice.accepted", {"dispatch_id": "sync-1", "tenant_id": "tenant-1"})

@patch("core.integrations.invoice_status_service.NilveraHttpClient")
async def test_api_error_404(mock_client_cls, mock_repo, mock_config):
    mock_client = AsyncMock()
    mock_client.get.side_effect = NilveraApiError("Not Found", http_status=404)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    record = create_mock_sync()
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is True
    assert updates.get("reconciliation_reason") == "PROVIDER_NOT_FOUND_404"
    assert "state" not in updates

@patch("core.integrations.invoice_status_service.NilveraHttpClient")
async def test_api_error_401(mock_client_cls, mock_repo, mock_config):
    mock_client = AsyncMock()
    mock_client.get.side_effect = NilveraApiError("Auth Error", http_status=401)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    record = create_mock_sync()
    record.status_check_attempt_count = 1
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is not True
    assert updates.get("status_poll_retryable") is True
    assert updates.get("next_status_check_at") is not None
    # attempt count should NOT increase for auth errors ideally, but the code increases it then overrides or doesn't override.
    # Let's check what the code actually does.

@patch("core.integrations.invoice_status_service.NilveraHttpClient")
async def test_api_error_500(mock_client_cls, mock_repo, mock_config):
    mock_client = AsyncMock()
    mock_client.get.side_effect = NilveraApiError("Server Error", http_status=500)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    record = create_mock_sync()
    await InvoiceStatusService.process_polled_record(record, "worker-1")

    updates = mock_repo.call_args[0][3]
    assert updates.get("reconciliation_required") is not True
    assert updates.get("status_poll_retryable") is True
    assert updates.get("next_status_check_at") is not None
    assert updates.get("status_check_attempt_count") == 1
