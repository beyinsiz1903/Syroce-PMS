import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker
from models.schemas.invoice_lifecycle import InvoiceLifecycleActionState


@pytest.fixture
def mock_db():
    with patch("core.integrations.invoice_lifecycle_worker._raw_db") as m:
        yield m


@pytest.mark.asyncio
async def test_worker_start_stop():
    worker = InvoiceLifecycleWorker(poll_interval_sec=1, batch_size=5)
    worker.start()
    assert worker._task is not None
    assert not worker._task.done()

    await worker.stop()
    assert worker._task is None


@pytest.mark.asyncio
async def test_worker_process_batch_empty(mock_db):
    worker = InvoiceLifecycleWorker(poll_interval_sec=1, batch_size=5)
    
    from unittest.mock import MagicMock
    # Mock empty db response
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    
    mock_db.invoice_lifecycle_actions.find.return_value = mock_cursor
    
    processed = await worker._process_batch()
    assert processed == 0

async def test_worker_unclaimed_action_not_counted(monkeypatch):
    from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker
    worker = InvoiceLifecycleWorker()
    
    async def mock_to_list(length):
        return [{"id": "act_1", "tenant_id": "t1", "direction": "INCOMING", "source_invoice_id": "inv_1", "source_provider_uuid": "u1", "action_type": "ACCEPT_INCOMING", "state": "REQUESTED", "request_uuid": "r1", "idempotency_key": "k1", "request_fingerprint": "f1", "requested_by": "admin", "requested_at": "2024-01-01T00:00:00Z"}]
    
    class MockCursor:
        def sort(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        async def to_list(self, length): return await mock_to_list(length)
    
    class MockCollection:
        def find(self, *args, **kwargs): return MockCursor()
        
    class MockDB:
        invoice_lifecycle_actions = MockCollection()
        
    import core.integrations.invoice_lifecycle_worker
    core.integrations.invoice_lifecycle_worker._raw_db = MockDB()
    
    # Mock service to return False (unclaimed)
    async def mock_process(*args, **kwargs): return False
    monkeypatch.setattr("core.integrations.invoice_lifecycle_worker.InvoiceLifecycleService.process_lifecycle_action", mock_process)
    
    processed = await worker._process_batch()
    assert processed == 0

async def test_worker_claimed_action_counted(monkeypatch):
    from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker
    worker = InvoiceLifecycleWorker()
    
    async def mock_to_list(length):
        return [{"id": "act_1", "tenant_id": "t1", "direction": "INCOMING", "source_invoice_id": "inv_1", "source_provider_uuid": "u1", "action_type": "ACCEPT_INCOMING", "state": "REQUESTED", "request_uuid": "r1", "idempotency_key": "k1", "request_fingerprint": "f1", "requested_by": "admin", "requested_at": "2024-01-01T00:00:00Z"}]
    
    class MockCursor:
        def sort(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        async def to_list(self, length): return await mock_to_list(length)
    
    class MockCollection:
        def find(self, *args, **kwargs): return MockCursor()
        
    class MockDB:
        invoice_lifecycle_actions = MockCollection()
        
    import core.integrations.invoice_lifecycle_worker
    core.integrations.invoice_lifecycle_worker._raw_db = MockDB()
    
    # Mock service to return True (claimed and processed)
    async def mock_process(*args, **kwargs): return True
    monkeypatch.setattr("core.integrations.invoice_lifecycle_worker.InvoiceLifecycleService.process_lifecycle_action", mock_process)
    
    processed = await worker._process_batch()
    assert processed == 1
