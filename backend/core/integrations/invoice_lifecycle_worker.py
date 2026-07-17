"""Worker for processing background invoice lifecycle actions."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.integrations.invoice_lifecycle_service import InvoiceLifecycleService
from core.tenant_db import get_system_db
from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState

logger = logging.getLogger(__name__)

# Used strictly for the raw Mongo operations
_raw_db: AsyncIOMotorDatabase | None = None


class InvoiceLifecycleWorker:
    """Background worker that polls and executes deferred lifecycle actions."""

    def __init__(self, poll_interval_sec: int = 15, batch_size: int = 20):
        self._poll_interval = poll_interval_sec
        self._batch_size = batch_size
        self._worker_id = f"lifecycle_worker_{uuid.uuid4()}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Starts the worker in the background."""
        global _raw_db
        if _raw_db is None:
            _raw_db = get_system_db()

        if self._task and not self._task.done():
            logger.warning("InvoiceLifecycleWorker is already running.")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) started.")

    async def stop(self) -> None:
        """Gracefully stops the worker."""
        if not self._task:
            return

        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) stopping...")
        self._stop_event.set()

        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except TimeoutError:
            logger.warning(f"InvoiceLifecycleWorker ({self._worker_id}) did not shut down gracefully in time. Forcing.")
            self._task.cancel()
        except asyncio.CancelledError:
            pass

        self._task = None
        logger.info(f"InvoiceLifecycleWorker ({self._worker_id}) stopped.")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(self._poll_interval)
                else:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"InvoiceLifecycleWorker unhandled error: {e}")
                await asyncio.sleep(self._poll_interval)

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
            except Exception as e:
                logger.error(f"Error processing lifecycle action {action.id}: {e}")

        return processed
