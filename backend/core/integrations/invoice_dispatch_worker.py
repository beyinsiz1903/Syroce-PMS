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

import pymongo.errors
from pymongo import ReturnDocument

from core.integrations.invoice_dispatch_service import InvoiceDispatchService
from core.tenant_db import get_system_db, tenant_context
from core.transient_db_guard import TransientFailureTracker
from models.schemas.invoice_sync import InvoiceSyncState
from models.schemas.nilvera_worker_health import NilveraWorkerErrorCode

logger = logging.getLogger("core.integrations.invoice_dispatch_worker")

_transient_tracker = TransientFailureTracker("invoice-dispatch-worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


from core.integrations.nilvera.worker_health import NilveraWorkerHealthMixin


class InvoiceDispatchWorker(NilveraWorkerHealthMixin):
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
        super().__init__(worker_name="invoice-dispatch-worker")
        self.worker_id = f"inv-dispatch-{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.processing_timeout = processing_timeout
        self.drain_pause = drain_pause

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.health.enabled:
            logger.info(f"{self.worker_id} is disabled. Will not start.")
            return

        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._mark_starting()
        self._task = asyncio.create_task(self._run(), name="invoice-dispatch-worker")

        await asyncio.sleep(0)
        if self._task.done():
            self._record_loop_error(NilveraWorkerErrorCode.STARTUP_TASK_FAILED)
            self._mark_failed("STARTUP_TASK_FAILED")
            raise RuntimeError("NILVERA_WORKER_STARTUP_FAILED") from None

        self._mark_running()
        logger.info("Invoice Dispatch Worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._mark_stopping()
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
                self._mark_stopped()
        logger.info("Invoice Dispatch Worker stopped: %s", self.worker_id)

    @property
    def metrics(self) -> dict[str, Any]:
        """Compatibility adapter for existing metric consumers."""
        health = self.health
        return {
            "worker_id": self.worker_id,
            "processed_total": health.processed_total,
            "failed_total": health.job_failed_total,
            "last_processed_at": (
                health.last_success_at.isoformat()
                if health.last_success_at
                else None
            ),
            "running": health.task_alive,
        }

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._record_heartbeat()
                    await self._recover_stuck()
                    await self._claim_and_queue_safe_to_retry()
                    count = await self._process_batch()
                    if count == 0:
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    raise
                except (TimeoutError, pymongo.errors.PyMongoError) as exc:
                    self._record_job_error(NilveraWorkerErrorCode.TRANSIENT_DEPENDENCY_ERROR)
                    _transient_tracker.log_exception(
                        logger,
                        exc,
                        TransientFailureTracker.OUTER_LOOP_KEY,
                        context="loop tick",
                        non_transient_msg="%s loop error: %s",
                    )
                    await asyncio.sleep(self.poll_interval)
                except Exception:
                    raise
                else:
                    _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("NILVERA_WORKER_FATAL_ERROR worker=%s error_code=%s", self.worker_name, "FATAL_LOOP_ERROR")
            self._record_loop_error(NilveraWorkerErrorCode.FATAL_LOOP_ERROR)
            self._mark_failed("Worker loop crashed")

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

    async def _claim_and_queue_safe_to_retry(self) -> int:
        """Atomically transition SAFE_TO_RETRY records back to QUEUED."""
        now = _utc_now()
        sysdb = get_system_db()
        processed = 0

        for _ in range(self.batch_size):
            if self._stop_event.is_set():
                break

            record = await sysdb.invoice_sync.find_one_and_update(
                {
                    "state": InvoiceSyncState.SAFE_TO_RETRY,
                    "redispatch_count": {"$lt": 1}
                },
                {
                    "$set": {
                        "state": InvoiceSyncState.QUEUED,
                        "queued_at": now,
                        "updated_at": now,
                        "next_retry_at": now,
                    },
                    "$inc": {"version": 1, "redispatch_count": 1}
                },
                sort=[("updated_at", 1)],
                return_document=ReturnDocument.AFTER,
                projection={"_id": 0, "id": 1, "tenant_id": 1},
            )

            if not record:
                break
            processed += 1

        return processed

    async def _process_batch(self) -> int:
        """Claim and process up to batch_size invoice sync records."""
        processed = 0
        for _ in range(self.batch_size):
            if self._stop_event.is_set():
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
                "state": {"$in": [InvoiceSyncState.PREPARED, InvoiceSyncState.QUEUED]},
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
                self._record_success(1)
                logger.info("Invoice dispatch worker success: %s for tenant %s", record_id, tenant_id)
            else:
                self._record_job_error(NilveraWorkerErrorCode.DISPATCH_FAILED)
                logger.warning("Invoice dispatch worker failed/retry: %s for tenant %s", record_id, tenant_id)


# Singleton worker instance
invoice_dispatch_worker = InvoiceDispatchWorker()
