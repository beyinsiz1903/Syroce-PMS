"""Worker for Nilvera Invoice Status Polling."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pymongo.errors

from core.database import _raw_db
from core.integrations.invoice_status_service import InvoiceStatusService
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState
from models.schemas.nilvera_worker_health import NilveraWorkerErrorCode

logger = logging.getLogger(__name__)


from core.integrations.nilvera.worker_health import NilveraWorkerHealthMixin


class InvoiceStatusWorker(NilveraWorkerHealthMixin):
    """Background worker for polling invoice statuses."""

    def __init__(self, batch_size: int = 50, poll_interval_sec: float = 5.0):
        super().__init__(worker_name="invoice-status-worker")
        self._batch_size = batch_size
        self._poll_interval_sec = poll_interval_sec
        self._worker_id = f"status_worker_{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.health.enabled:
            logger.info(f"{self._worker_id} is disabled. Will not start.")
            return

        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._mark_starting()
        self._task = asyncio.create_task(self._run_loop(), name="invoice-status-worker")

        await asyncio.sleep(0)
        if self._task.done():
            self._record_loop_error(NilveraWorkerErrorCode.STARTUP_TASK_FAILED)
            self._mark_failed("STARTUP_TASK_FAILED")
            raise RuntimeError("NILVERA_WORKER_STARTUP_FAILED") from None

        self._mark_running()
        logger.info("InvoiceStatusWorker started with ID %s", self._worker_id)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._mark_stopping()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
            except TimeoutError:
                logger.warning("InvoiceStatusWorker drain timeout exceeded, cancelling task.")
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
        logger.info("InvoiceStatusWorker stopped")



    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._record_heartbeat()
                    processed = await self._process_batch()
                    if processed == 0:
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_sec)
                        except TimeoutError:
                            pass
                except asyncio.CancelledError:
                    raise
                except (TimeoutError, pymongo.errors.PyMongoError) as exc:
                    self._record_job_error(NilveraWorkerErrorCode.TRANSIENT_DEPENDENCY_ERROR)
                    logger.warning("InvoiceStatusWorker transient loop error: %s", type(exc).__name__)
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_sec)
                    except TimeoutError:
                        pass
                except Exception:
                    raise
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("NILVERA_WORKER_FATAL_ERROR worker=%s error_code=%s", self.worker_name, "FATAL_LOOP_ERROR")
            self._record_loop_error(NilveraWorkerErrorCode.FATAL_LOOP_ERROR)
            self._mark_failed("Worker loop crashed")

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
                    self._record_success(1)
            except Exception as e:
                self._record_job_error(NilveraWorkerErrorCode.STATUS_POLL_FAILED)
                logger.error(f"Error processing status for dispatch {record.id}: {type(e).__name__}")

        return processed

invoice_status_worker = InvoiceStatusWorker()
