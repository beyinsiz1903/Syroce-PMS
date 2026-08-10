import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker
from models.schemas.invoice_lifecycle import InvoiceLifecycleActionState


def _action_doc(**updates):
    values = {
        "id": "sensitive-action-identity",
        "tenant_id": "sensitive-tenant-identity",
        "direction": "INCOMING",
        "source_invoice_id": "sensitive-invoice-identity",
        "source_provider_uuid": "11112222-3333-4444-5555-666677778888",
        "action_type": "ACCEPT_INCOMING",
        "state": "REQUESTED",
        "request_uuid": "request-id",
        "idempotency_key": "idempotency-key",
        "request_fingerprint": "fingerprint",
        "requested_by": "admin",
        "requested_at": datetime.now(UTC),
    }
    values.update(updates)
    return values


def _mock_db(docs):
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=docs)
    collection = MagicMock()
    collection.find.return_value = cursor
    return MagicMock(invoice_lifecycle_actions=collection), collection


@pytest.mark.asyncio
async def test_worker_start_and_stop():
    worker = InvoiceLifecycleWorker(poll_interval_sec=0.01, batch_size=5)
    with (
        patch("core.integrations.invoice_lifecycle_worker.get_system_db", return_value=MagicMock()),
        patch.object(worker, "_process_batch", new=AsyncMock(return_value=0)),
    ):
        await worker.start()
        assert worker._task is not None
        assert not worker._task.done()
        await worker.stop()

    assert worker._task is None


@pytest.mark.asyncio
async def test_worker_query_includes_verification_and_stale_processing_states():
    worker = InvoiceLifecycleWorker(batch_size=5)
    db, collection = _mock_db([])
    with patch("core.integrations.invoice_lifecycle_worker._raw_db", db):
        assert await worker._process_batch() == 0

    query = collection.find.call_args.args[0]
    states = set(query["state"]["$in"])
    assert states == {
        InvoiceLifecycleActionState.REQUESTED.value,
        InvoiceLifecycleActionState.PROCESSING.value,
        InvoiceLifecycleActionState.RETRY_SCHEDULED.value,
        InvoiceLifecycleActionState.PROVIDER_PENDING.value,
    }


@pytest.mark.asyncio
async def test_worker_counts_only_claimed_actions():
    worker = InvoiceLifecycleWorker(batch_size=5)
    db, _ = _mock_db([_action_doc()])
    with (
        patch("core.integrations.invoice_lifecycle_worker._raw_db", db),
        patch(
            "core.integrations.invoice_lifecycle_worker.InvoiceLifecycleService.process_lifecycle_action",
            new=AsyncMock(return_value=False),
        ) as process,
    ):
        processed = await worker._process_batch()

    assert processed == 0
    process.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_does_not_log_action_tenant_or_invoice_identity(caplog):
    worker = InvoiceLifecycleWorker(batch_size=5)
    doc = _action_doc()
    db, _ = _mock_db([doc])
    with (
        patch("core.integrations.invoice_lifecycle_worker._raw_db", db),
        patch(
            "core.integrations.invoice_lifecycle_worker.InvoiceLifecycleService.process_lifecycle_action",
            new=AsyncMock(side_effect=RuntimeError("provider payload must not leak")),
        ),
        caplog.at_level(logging.ERROR, logger="core.integrations.invoice_lifecycle_worker"),
    ):
        assert await worker._process_batch() == 0

    for sensitive in {
        doc["id"],
        doc["tenant_id"],
        doc["source_invoice_id"],
        doc["source_provider_uuid"],
        "provider payload must not leak",
    }:
        assert sensitive not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
