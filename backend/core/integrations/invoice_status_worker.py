"""Worker for Nilvera Invoice Status Polling."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from core.database import _raw_db
from core.integrations.invoice_status_service import InvoiceStatusService
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState

logger = logging.getLogger(__name__)


class InvoiceStatusWorker:
    """Background worker for polling invoice statuses."""

    def __init__(self, batch_size: int = 50, poll_interval_sec: float = 5.0):
        self._batch_size = batch_size
        self._poll_interval_sec = poll_interval_sec
        self._worker_id = f"status_worker_{uuid.uuid4().hex[:8]}"
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
                await asyncio.wait_for(self._task, timeout=10.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
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
            try:
                claimed_and_processed = await InvoiceStatusService.poll_invoice_status(record.tenant_id, record.id, self._worker_id)
                if claimed_and_processed:
                    processed += 1
            except Exception as e:
                logger.error(f"Error processing status for dispatch {record.id}: {e}")

        return processed

invoice_status_worker = InvoiceStatusWorker()
