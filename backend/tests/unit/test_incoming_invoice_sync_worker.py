from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncResult
from core.integrations.incoming_invoice_sync_worker import IncomingInvoiceSyncWorker
from core.integrations.nilvera.errors import NilveraServerError
from models.schemas.nilvera_worker_health import NilveraWorkerErrorCode, NilveraWorkerStatus


def _result() -> IncomingInvoiceSyncResult:
    return IncomingInvoiceSyncResult(
        invoices_seen=1,
        invoices_created=1,
        invoices_changed=0,
        lines_created=1,
        lines_changed=0,
        lines_deactivated=0,
        unknown_invoices=0,
        pending_invoices=0,
        provider_error_invoices=0,
    )


@pytest.mark.asyncio
async def test_process_tenant_uses_bounded_overlap_and_completes_success():
    worker = IncomingInvoiceSyncWorker(overlap_hours=48)
    worker.health.status = NilveraWorkerStatus.RUNNING
    last_end = datetime.now(UTC) - timedelta(hours=1)
    with (
        patch(
            "core.integrations.incoming_invoice_sync_worker.IncomingInvoiceSyncService.sync_tenant",
            new=AsyncMock(return_value=_result()),
        ) as sync_mock,
        patch.object(
            worker,
            "_complete_success",
            new=AsyncMock(return_value=True),
        ) as complete_mock,
    ):
        await worker._process_tenant(
            "tenant-a",
            {"last_successful_end_at": last_end},
        )

    start_date = sync_mock.await_args.args[1]
    end_date = sync_mock.await_args.args[2]
    assert end_date - start_date <= timedelta(days=31)
    assert start_date == last_end - timedelta(hours=48)
    complete_mock.assert_awaited_once()
    assert worker.health.processed_total == 1


@pytest.mark.asyncio
async def test_provider_failure_records_safe_metadata_only(caplog):
    worker = IncomingInvoiceSyncWorker()
    worker.health.status = NilveraWorkerStatus.RUNNING
    sensitive_payload = "private-provider-payload"
    error = NilveraServerError("Provider failed", raw_response=sensitive_payload)
    with (
        patch(
            "core.integrations.incoming_invoice_sync_worker.IncomingInvoiceSyncService.sync_tenant",
            new=AsyncMock(side_effect=error),
        ),
        patch.object(worker, "_complete_failure", new=AsyncMock()) as complete_mock,
    ):
        await worker._process_tenant("tenant-a", {})

    complete_mock.assert_awaited_once_with("tenant-a", "NILVERA_SERVER_ERROR")
    assert worker.health.last_error_code == NilveraWorkerErrorCode.INCOMING_SYNC_FAILED
    assert worker.health.status == NilveraWorkerStatus.DEGRADED
    assert sensitive_payload not in caplog.text


@pytest.mark.asyncio
async def test_lost_lease_is_not_recorded_as_success():
    worker = IncomingInvoiceSyncWorker()
    worker.health.status = NilveraWorkerStatus.RUNNING
    with (
        patch(
            "core.integrations.incoming_invoice_sync_worker.IncomingInvoiceSyncService.sync_tenant",
            new=AsyncMock(return_value=_result()),
        ),
        patch.object(
            worker,
            "_complete_success",
            new=AsyncMock(return_value=False),
        ),
    ):
        await worker._process_tenant("tenant-a", {})

    assert worker.health.processed_total == 0
    assert worker.health.last_error_code == NilveraWorkerErrorCode.INCOMING_SYNC_FAILED
