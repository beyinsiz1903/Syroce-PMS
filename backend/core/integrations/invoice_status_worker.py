"""Worker for Nilvera Invoice Status Polling."""

import asyncio
import logging
from datetime import UTC, datetime

from core.database import _raw_db
from core.integrations.invoice_status_repository import InvoiceStatusRepository
from core.integrations.invoice_status_service import InvoiceStatusService
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState

logger = logging.getLogger(__name__)


class InvoiceStatusWorker:
    """Background worker for polling invoice statuses."""

    def __init__(self, batch_size: int = 50, poll_interval_sec: float = 5.0):
        self._batch_size = batch_size
        self._poll_interval_sec = poll_interval_sec
        self._worker_id = "status_worker_01"  # in real env, from env var or uuid
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="invoice-status-worker")
        logger.info(f"InvoiceStatusWorker started with ID {self._worker_id}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            try:
                self._task.cancel()
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("InvoiceStatusWorker stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(self._poll_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in InvoiceStatusWorker loop: {e}", exc_info=True)
                await asyncio.sleep(self._poll_interval_sec)

    async def _process_batch(self) -> int:
        now = datetime.now(UTC)

        # Only process SUBMITTED records that do NOT require reconciliation
        # and are due for a status check
        cursor = _raw_db.invoice_sync.find(
            {
                "state": InvoiceSyncState.SUBMITTED.value,
                "reconciliation_required": {"$ne": True},
                "next_status_check_at": {"$lte": now},
                "$or": [
                    {"status_lease_owner": None},
                    {"status_lease_expires_at": {"$lte": now}}
                ]
            }
        ).sort("next_status_check_at", 1).limit(self._batch_size)

        docs = await cursor.to_list(length=self._batch_size)
        if not docs:
            return 0

        processed = 0
        for doc in docs:
            record = InvoiceSync.model_validate(doc)
            # Try to claim the lease
            # In an optimized worker, we could use a bulk claim or rely on the find_and_modify in the service
            # For simplicity, we just pass to the service which claims it
            try:
                # Service claims it
                claimed = await InvoiceStatusRepository.claim_status_lease(
                    record.tenant_id, record.id, self._worker_id, lease_duration_sec=60
                )
                if claimed:
                    await InvoiceStatusService.process_polled_record(claimed, self._worker_id)
                    processed += 1
            except Exception as e:
                logger.error(f"Error processing status for dispatch {record.id}: {e}")

        return processed

invoice_status_worker = InvoiceStatusWorker()
