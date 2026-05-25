"""
DATA-001: Import Retry Worker — Background Worker for OTA Import Retries
=========================================================================
Polls imported_reservations for retry-eligible records and attempts
to import them via the import bridge service.

Mirrors the OTA-002 outbox worker architecture:
  - Atomic claim pattern
  - Exponential backoff
  - Stuck processing recovery
  - Graceful shutdown
  - Health metrics
"""
import asyncio
import logging
import os
import socket
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from core.import_bridge_service import (
    COLL_IMPORTED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_RETRY,
    auto_import_reservation_to_pms,
)
from core.tenant_db import get_system_db, tenant_context
from core.transient_db_guard import TransientFailureTracker

logger = logging.getLogger("core.import_retry_worker")

# Demotes Atlas transient hiccups (AutoReconnect / NoPrimary / SSL timeout)
# to WARNING for the first few consecutive misses, then escalates to ERROR
# so a sustained outage is still visible in Sentry. See
# `core.transient_db_guard` for the rationale.
_transient_tracker = TransientFailureTracker("import-retry-worker")


@contextmanager
def _nullcontext():
    yield


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class ImportRetryWorker:
    """
    Background worker for processing pending and retry import records.
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
        self.worker_id = f"import-{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        # Metrics
        self._processed_count = 0
        self._failed_count = 0
        self._retry_count = 0
        self._last_processed_at: str | None = None

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "imported_total": self._processed_count,
            "failed_total": self._failed_count,
            "retry_total": self._retry_count,
            "last_processed_at": self._last_processed_at,
            "running": self._task is not None and not self._task.done(),
        }

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="import-retry-worker")
        logger.info("Import Retry Worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Import Retry Worker stopped: %s", self.worker_id)

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
        """Recover records stuck in 'processing' state beyond timeout."""
        cutoff = _iso(_utc_now() - timedelta(seconds=self.processing_timeout))
        now = _iso(_utc_now())
        sysdb = get_system_db()

        result = await sysdb[COLL_IMPORTED].update_many(
            {
                "import_status": STATUS_PROCESSING,
                "updated_at": {"$lte": cutoff},
            },
            {
                "$set": {
                    "import_status": STATUS_RETRY,
                    "next_retry_at": now,
                    "updated_at": now,
                    "last_error": "processing timeout — recovered by import worker",
                },
            },
        )
        if result.modified_count > 0:
            logger.warning("Recovered %d stuck import records", result.modified_count)
        return result.modified_count

    async def _process_batch(self) -> int:
        """Claim and process up to batch_size import records."""
        processed = 0
        for _ in range(self.batch_size):
            record = await self._claim_record()
            if not record:
                break
            await self._process_record(record)
            processed += 1
            if self.drain_pause > 0:
                await asyncio.sleep(self.drain_pause)
        return processed

    async def _claim_record(self) -> dict[str, Any] | None:
        """Atomically claim the next eligible import record."""
        now = _iso(_utc_now())
        sysdb = get_system_db()

        record = await sysdb[COLL_IMPORTED].find_one_and_update(
            {
                "import_status": {"$in": [STATUS_PENDING, STATUS_RETRY]},
                "$or": [
                    {"next_retry_at": None},
                    {"next_retry_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "import_status": STATUS_PROCESSING,
                    "updated_at": now,
                },
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return record

    async def _process_record(self, record: dict[str, Any]) -> None:
        """Process a single import record within tenant context."""
        record_id = record.get("id", "unknown")
        tenant_id = record.get("tenant_id", "")

        with tenant_context(tenant_id) if tenant_id else _nullcontext():
            success, message = await auto_import_reservation_to_pms(
                record_id, pre_claimed_record=record
            )

            if success:
                self._processed_count += 1
                self._last_processed_at = _iso(_utc_now())
                logger.info("Import worker processed: %s → %s", record_id, message[:100])
            else:
                if "retry" in message.lower() or "error" in message.lower():
                    self._retry_count += 1
                else:
                    self._failed_count += 1
                logger.warning("Import worker result: %s → %s", record_id, message[:200])


# Singleton worker instance
import_retry_worker = ImportRetryWorker()
