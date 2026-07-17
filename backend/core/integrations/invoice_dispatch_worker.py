"""
NILVERA-001: Invoice Dispatch Worker — Background Worker for Nilvera Dispatch
=========================================================================
Polls invoice_sync for PREPARED/RETRYING records and attempts
to send them to Nilvera via InvoiceDispatchService.

Features:
  - Cross-tenant polling via sysdb
  - Atomic claim pattern
  - Exponential backoff
  - Stuck processing recovery
  - Graceful shutdown
"""

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from core.integrations.invoice_dispatch_service import InvoiceDispatchService
from core.tenant_db import get_system_db, tenant_context
from core.transient_db_guard import TransientFailureTracker
from models.schemas.invoice_sync import InvoiceSyncState

logger = logging.getLogger("core.integrations.invoice_dispatch_worker")

_transient_tracker = TransientFailureTracker("invoice-dispatch-worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InvoiceDispatchWorker:
    """
    Background worker for processing pending invoice sync records to Nilvera.
    """

    def __init__(
        self,
        *,
        poll_interval: float = 5.0,
        batch_size: int = 10,
        processing_timeout: int = 120,
        drain_pause: float = 0.2,
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.processing_timeout = processing_timeout
        self.drain_pause = drain_pause
        self.worker_id = f"inv-dispatch-{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        # Metrics
        self._processed_count = 0
        self._failed_count = 0
        self._last_processed_at: str | None = None

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "processed_total": self._processed_count,
            "failed_total": self._failed_count,
            "last_processed_at": self._last_processed_at,
            "running": self._task is not None and not self._task.done(),
        }

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="invoice-dispatch-worker")
        logger.info("Invoice Dispatch Worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except TimeoutError:
                logger.warning("Worker drain timeout exceeded, cancelling task.")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
        logger.info("Invoice Dispatch Worker stopped: %s", self.worker_id)

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._recover_stuck()
                    count = await self._process_batch()
                    if count == 0:
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _transient_tracker.log_exception(
                        logger,
                        exc,
                        TransientFailureTracker.OUTER_LOOP_KEY,
                        context="loop tick",
                        non_transient_msg="%s loop error: %s",
                    )
                    await asyncio.sleep(self.poll_interval)
                else:
                    _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except asyncio.CancelledError:
            pass

    async def _recover_stuck(self) -> int:
        """Recover records stuck in 'SENDING' state beyond their lease."""
        now = _utc_now()
        sysdb = get_system_db()

        result = await sysdb.invoice_sync.update_many(
            {
                "state": InvoiceSyncState.SENDING,
                "lease_expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "state": InvoiceSyncState.RETRYABLE_ERROR,
                    "next_retry_at": now,
                    "updated_at": now,
                    "last_error_message": "lease expired — recovered by worker",
                    "last_error_retryable": True,
                    "lease_owner": None,
                    "lease_expires_at": None,
                },
            },
        )
        if result.modified_count > 0:
            logger.warning("Recovered %d stuck invoice sync records", result.modified_count)
        return result.modified_count

    async def _process_batch(self) -> int:
        """Claim and process up to batch_size invoice sync records."""
        processed = 0
        for _ in range(self.batch_size):
            if self._stop.is_set():
                break
            record = await self._claim_record()
            if not record:
                break
            await self._process_record(record)
            processed += 1
            if self.drain_pause > 0:
                await asyncio.sleep(self.drain_pause)
        return processed

    async def _claim_record(self) -> dict[str, Any] | None:
        """Atomically claim the next eligible invoice sync record using lease mechanics."""
        now = _utc_now()
        sysdb = get_system_db()

        record = await sysdb.invoice_sync.find_one_and_update(
            {
                "state": {"$in": [InvoiceSyncState.PREPARED, InvoiceSyncState.QUEUED, InvoiceSyncState.RETRYABLE_ERROR]},
                "$and": [
                    {
                        "$or": [
                            {"next_retry_at": None},
                            {"next_retry_at": {"$exists": False}},
                            {"next_retry_at": {"$lte": now}},
                        ]
                    },
                    {
                        "$or": [
                            {"lease_expires_at": None},
                            {"lease_expires_at": {"$exists": False}},
                            {"lease_expires_at": {"$lte": now}},
                        ]
                    }
                ]
            },
            {
                "$set": {
                    "state": InvoiceSyncState.SENDING,
                    "lease_owner": self.worker_id,
                    "lease_expires_at": now + timedelta(seconds=self.processing_timeout),
                    "sending_at": now,
                    "updated_at": now,
                    "last_attempt_at": now,
                },
                "$inc": {"version": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "id": 1, "tenant_id": 1},
        )
        return record

    async def _process_record(self, record: dict[str, Any]) -> None:
        """Process a single invoice sync record within tenant context."""
        record_id = record.get("id")
        tenant_id = record.get("tenant_id")

        if not record_id or not tenant_id:
            logger.error("Invalid record claimed: %s", record)
            return

        # Use tenant context so all nested repository calls map correctly to the tenant
        with tenant_context(tenant_id):
            success = await InvoiceDispatchService.execute_dispatch(tenant_id, record_id, worker_id=self.worker_id)

            if success:
                self._processed_count += 1
                self._last_processed_at = _utc_now().isoformat()
                logger.info("Invoice dispatch worker success: %s for tenant %s", record_id, tenant_id)
            else:
                self._failed_count += 1
                logger.warning("Invoice dispatch worker failed/retry: %s for tenant %s", record_id, tenant_id)


# Singleton worker instance
invoice_dispatch_worker = InvoiceDispatchWorker()
