"""Worker for processing background invoice lifecycle actions."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
from core.tenant_db import get_system_db
from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState

logger = logging.getLogger(__name__)

# Used strictly for the raw Mongo operations
_raw_db: AsyncIOMotorDatabase | None = None


from core.integrations.nilvera.worker_health import NilveraWorkerHealthMixin


class InvoiceLifecycleWorker(NilveraWorkerHealthMixin):
    """Background worker that polls and executes deferred lifecycle actions."""

    def __init__(self, poll_interval_sec: int = 15, batch_size: int = 20):
        super().__init__(worker_name="invoice-lifecycle-worker")
        self._poll_interval = poll_interval_sec
        self._batch_size = batch_size
        self._worker_id = f"lifecycle_worker_{uuid.uuid4()}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Starts the worker in the background."""
        if not self.health.enabled:
            logger.info(f"{self._worker_id} is disabled. Will not start.")
            return

        global _raw_db
        if _raw_db is None:
            _raw_db = get_system_db()

        if self._task and not self._task.done():
            logger.warning("InvoiceLifecycleWorker is already running.")
            return

        self._stop_event.clear()
        self._mark_starting()
        self._task = asyncio.create_task(self._run_loop())

        await asyncio.sleep(0)
        if self._task.done():
            self._record_loop_error("STARTUP_TASK_FAILED")
            self._mark_failed("STARTUP_TASK_FAILED")
            raise RuntimeError("NILVERA_WORKER_STARTUP_FAILED") from None

        self._mark_running()
        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) started.")

    async def stop(self) -> None:
        """Gracefully stops the worker."""
        if not self._task:
            return

        self._mark_stopping()
        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) stopping...")
        self._stop_event.set()

        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except TimeoutError:
            logger.warning(f"InvoiceLifecycleWorker ({self._worker_id}) did not shut down gracefully in time. Forcing.")
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

        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) stopped.")

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._record_heartbeat()
                    processed = await self._process_batch()
                    if processed == 0:
                        await asyncio.sleep(self._poll_interval)
                    else:
                        await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    raise
                except (TimeoutError, pymongo.errors.PyMongoError) as exc:
                    self._record_job_error("TRANSIENT_DEPENDENCY_ERROR", fatal=False)
                    logger.warning(f"InvoiceLifecycleWorker transient loop error: {type(exc).__name__}")
                    await asyncio.sleep(self._poll_interval)
                except Exception:
                    raise
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("NILVERA_WORKER_FATAL_ERROR worker=%s error_code=%s", self.worker_name, "FATAL_LOOP_ERROR")
            self._record_loop_error("FATAL_LOOP_ERROR")
            self._mark_failed("Worker loop crashed")

    async def _process_batch(self) -> int:
        now = datetime.now(UTC)

        # Only process REQUESTED or RETRY_SCHEDULED records that are due
        cursor = (
            _raw_db.invoice_lifecycle_actions.find(
                {
                    "state": {"$in": [InvoiceLifecycleActionState.REQUESTED.value, InvoiceLifecycleActionState.RETRY_SCHEDULED.value]},
                    "$or": [{"next_attempt_at": None}, {"next_attempt_at": {"$lte": now}}],
                    "$and": [{"$or": [{"lifecycle_lease_owner": None}, {"lifecycle_lease_expires_at": {"$lte": now}}]}],
                }
            )
            .sort("next_attempt_at", 1)
            .limit(self._batch_size)
        )

        docs = await cursor.to_list(length=self._batch_size)
        if not docs:
            return 0

        processed = 0
        for doc in docs:
            action = InvoiceLifecycleAction.model_validate(doc)
            try:
                claimed_and_processed = await InvoiceLifecycleService.process_lifecycle_action(action.tenant_id, action.id, self._worker_id)
                if claimed_and_processed:
                    processed += 1
                    self._record_success(1)
            except Exception as e:
                self._record_job_error("LIFECYCLE_PROCESS_FAILED", fatal=False)
                logger.error(f"Error processing lifecycle action {action.id}: {type(e).__name__}")

        return processed

invoice_lifecycle_worker = InvoiceLifecycleWorker()
