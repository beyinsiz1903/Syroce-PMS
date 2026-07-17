from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_status_worker import InvoiceStatusWorker
from models.schemas.invoice_sync import InvoiceSyncState

pytestmark = pytest.mark.asyncio

@pytest.fixture
def worker():
    return InvoiceStatusWorker(batch_size=5, poll_interval_sec=0.1)

@patch("core.integrations.invoice_status_worker._raw_db")
@patch("core.integrations.invoice_status_worker.InvoiceStatusRepository")
@patch("core.integrations.invoice_status_worker.InvoiceStatusService")
async def test_worker_process_batch(mock_service, mock_repo, mock_raw_db, worker):
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    mock_dict = {
        "id": "test_id_1",
        "tenant_id": "t1",
        "invoice_id": "inv-1",
        "provider": "NILVERA",
        "document_kind": "E_INVOICE",
        "idempotency_key": "v1:hash",
        "request_uuid": "req-123",
        "state": InvoiceSyncState.SUBMITTED.value,
        "provider_document_id": "doc-123",
        "reconciliation_required": False,
        "prepared_at": now,
        "created_at": now,
        "updated_at": now,
    }
    mock_cursor.to_list = AsyncMock(return_value=[mock_dict])
    mock_raw_db.invoice_sync.find.return_value = mock_cursor

    mock_repo.claim_status_lease = AsyncMock(return_value=True)
    mock_service.process_polled_record = AsyncMock()

    processed = await worker._process_batch()

    assert processed == 1
    mock_raw_db.invoice_sync.find.assert_called_once()

    # Verify query constraints
    query = mock_raw_db.invoice_sync.find.call_args[0][0]
    assert query["state"] == InvoiceSyncState.SUBMITTED.value
    assert query["reconciliation_required"] == {"$ne": True}
    assert "$or" in query

    mock_repo.claim_status_lease.assert_called_once()
    mock_service.process_polled_record.assert_called_once()

@patch("core.integrations.invoice_status_worker._raw_db")
async def test_worker_process_batch_empty(mock_raw_db, worker):
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_raw_db.invoice_sync.find.return_value = mock_cursor

    processed = await worker._process_batch()

    assert processed == 0

async def test_worker_start_stop(worker):
    await worker.start()
    assert worker._running is True
    assert worker._task is not None
    assert not worker._task.done()

    await worker.stop()
    assert worker._running is False
    assert worker._task.done()
