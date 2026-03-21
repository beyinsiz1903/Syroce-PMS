"""
OTA-002: Outbox Worker — Production Async Background Worker
=============================================================
Polls the outbox_events collection for pending/retry events,
atomically claims them, dispatches via outbox_dispatcher,
and handles retry/failure lifecycle.

Features:
  - Atomic claim pattern (no duplicate processing)
  - Exponential backoff retry
  - Stuck processing recovery
  - Graceful shutdown
  - Health metrics
"""
import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pymongo import ReturnDocument

from core.database import db
from core.outbox_service import (
    OTA_OUTBOX_EVENT_TYPES,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSED,
    STATUS_PROCESSING,
    STATUS_RETRY,
    compute_next_available_at,
    is_retryable_error,
)

logger = logging.getLogger("core.outbox_worker")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class OutboxWorker:
    """
    Production outbox worker for PMS → OTA guaranteed delivery.

    Replaces the temporary OutboxLifecycleWorker with real provider dispatch.
    """

    def __init__(
        self,
        *,
        poll_interval: float = 2.0,
        batch_size: int = 10,
        processing_timeout: int = 120,
        drain_pause: float = 0.1,
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.processing_timeout = processing_timeout
        self.drain_pause = drain_pause
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        # Metrics
        self._processed_count = 0
        self._failed_count = 0
        self._retry_count = 0
        self._last_processed_at: Optional[str] = None

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "processed_total": self._processed_count,
            "failed_total": self._failed_count,
            "retry_total": self._retry_count,
            "last_processed_at": self._last_processed_at,
            "running": self._task is not None and not self._task.done(),
        }

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-ota-worker")
        logger.info("OTA Outbox Worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("OTA Outbox Worker stopped: %s", self.worker_id)

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
                except Exception:
                    logger.exception("Outbox worker loop error")
                    await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass

    async def _recover_stuck(self) -> int:
        """Recover events stuck in 'processing' state beyond timeout."""
        cutoff = _iso(_utc_now() - timedelta(seconds=self.processing_timeout))
        now = _iso(_utc_now())

        result = await db.outbox_events.update_many(
            {
                "status": STATUS_PROCESSING,
                "last_attempt_at": {"$lte": cutoff},
                "max_attempts": {"$exists": True},
            },
            {
                "$set": {
                    "status": STATUS_RETRY,
                    "available_at": now,
                    "updated_at": now,
                    "last_error": "processing timeout — recovered by worker",
                },
            },
        )
        if result.modified_count > 0:
            logger.warning("Recovered %d stuck outbox events", result.modified_count)
        return result.modified_count

    async def _process_batch(self) -> int:
        """Process up to batch_size events."""
        processed = 0
        for _ in range(self.batch_size):
            event = await self._claim_event()
            if not event:
                break
            await self._process_event(event)
            processed += 1
            if self.drain_pause > 0:
                await asyncio.sleep(self.drain_pause)
        return processed

    async def _claim_event(self) -> Optional[Dict[str, Any]]:
        """Atomically claim the next pending/retry event.
        
        Only claims OTA outbox events (those with max_attempts field set by
        enqueue_outbox_event). Legacy migration events are left for the
        OutboxLifecycleWorker.
        """
        now = _iso(_utc_now())

        event = await db.outbox_events.find_one_and_update(
            {
                "status": {"$in": [STATUS_PENDING, STATUS_RETRY]},
                "available_at": {"$lte": now},
                "max_attempts": {"$exists": True},
            },
            {
                "$set": {
                    "status": STATUS_PROCESSING,
                    "last_attempt_at": now,
                    "updated_at": now,
                    "worker_id": self.worker_id,
                },
                "$inc": {"attempt_count": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return event

    async def _process_event(self, event: Dict[str, Any]) -> None:
        """Dispatch event and handle result."""
        event_id = event.get("id", "unknown")

        try:
            from core.outbox_dispatcher import dispatch_outbox_event

            success, message = await dispatch_outbox_event(event)

            if success:
                await self._mark_processed(event, message)
            else:
                await self._handle_failure(event, message)

        except Exception as e:
            logger.exception("Outbox dispatch error for event %s", event_id)
            error_msg = str(e)
            if is_retryable_error(error_msg):
                await self._handle_failure(event, f"retryable: {error_msg[:500]}")
            else:
                await self._handle_failure(event, f"permanent: {error_msg[:500]}")

    async def _mark_processed(self, event: Dict[str, Any], message: str) -> None:
        """Mark event as successfully processed."""
        now = _iso(_utc_now())
        await db.outbox_events.update_one(
            {"id": event["id"], "status": STATUS_PROCESSING},
            {
                "$set": {
                    "status": STATUS_PROCESSED,
                    "processed_at": now,
                    "updated_at": now,
                    "last_error": None,
                    "delivery_message": message[:500],
                },
            },
        )
        self._processed_count += 1
        self._last_processed_at = now
        logger.info(
            "Outbox event processed: %s type=%s msg=%s",
            event.get("id"), event.get("event_type"), message[:100],
        )

    async def _handle_failure(self, event: Dict[str, Any], message: str) -> None:
        """Handle failed dispatch — retry or mark as permanently failed."""
        now = _iso(_utc_now())
        attempt_count = event.get("attempt_count", 1)
        max_attempts = event.get("max_attempts", 5)
        is_permanent = message.startswith("permanent:")

        if is_permanent or attempt_count >= max_attempts:
            # Permanently failed
            await db.outbox_events.update_one(
                {"id": event["id"], "status": STATUS_PROCESSING},
                {
                    "$set": {
                        "status": STATUS_FAILED,
                        "last_error": message[:1000],
                        "updated_at": now,
                        "failed_at": now,
                    },
                },
            )
            self._failed_count += 1
            logger.error(
                "Outbox event FAILED (permanent): %s type=%s attempts=%d error=%s",
                event.get("id"), event.get("event_type"), attempt_count, message[:200],
            )
        else:
            # Schedule retry
            next_at = compute_next_available_at(attempt_count + 1)
            await db.outbox_events.update_one(
                {"id": event["id"], "status": STATUS_PROCESSING},
                {
                    "$set": {
                        "status": STATUS_RETRY,
                        "last_error": message[:1000],
                        "available_at": next_at,
                        "updated_at": now,
                    },
                },
            )
            self._retry_count += 1
            logger.warning(
                "Outbox event scheduled for retry: %s type=%s attempt=%d/%d next_at=%s",
                event.get("id"), event.get("event_type"),
                attempt_count, max_attempts, next_at,
            )


# Singleton worker instance
outbox_ota_worker = OutboxWorker()
