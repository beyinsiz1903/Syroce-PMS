from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_system_db
from shared_kernel.migration_observability import MIGRATION_EVENT_TYPES

logger = logging.getLogger(__name__)

OUTBOX_WORKER_LOCK_ID = "outbox-lifecycle-worker"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class OutboxLifecycleWorker:
    """Temporary operational worker for validating the outbox lifecycle in-process.

    This is intentionally minimal and startup-managed so the migration program can
    prove `pending -> processing -> processed/failed/parked` before extracting a
    dedicated worker service.
    """

    def __init__(
        self,
        *,
        poll_interval_seconds: float = 2.0,
        batch_size: int = 10,
        max_retries: int = 3,
        backoff_base_seconds: float = 5.0,
        lease_duration_seconds: int = 15,
        processing_timeout_seconds: int = 60,
        drain_pause_seconds: float = 0.1,
    ) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.lease_duration_seconds = lease_duration_seconds
        self.processing_timeout_seconds = processing_timeout_seconds
        self.drain_pause_seconds = drain_pause_seconds
        self.owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def ensure_indexes(self) -> None:
        sysdb = get_system_db()
        await sysdb.outbox_events.create_index(
            [("tenant_id", 1), ("status", 1), ("next_attempt_at", 1), ("created_at", 1)],
            name="idx_outbox_lifecycle_claim",
        )
        await sysdb.outbox_events.create_index(
            [("status", 1), ("processing_started_at", 1)],
            name="idx_outbox_processing_timeout",
        )
        await sysdb.outbox_worker_locks.create_index(
            [("expires_at", 1)],
            name="idx_outbox_worker_lock_expires",
        )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        await self.ensure_indexes()
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run(), name="outbox-lifecycle-worker")
        logger.info("Outbox lifecycle worker started owner_id=%s", self.owner_id)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.release_lock()
        logger.info("Outbox lifecycle worker stopped owner_id=%s", self.owner_id)

    async def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    has_lock = await self.acquire_lock()
                    if not has_lock:
                        await asyncio.sleep(self.poll_interval_seconds)
                        continue

                    await self.recover_stuck_processing(limit=self.batch_size)
                    processed_count = await self.process_batch(limit=self.batch_size)
                    if processed_count == 0:
                        await asyncio.sleep(self.poll_interval_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Outbox lifecycle worker loop error")
                    await asyncio.sleep(self.poll_interval_seconds)
        finally:
            await self.release_lock()

    async def acquire_lock(self) -> bool:
        now = utc_now()
        now_iso = _iso(now)
        expires_at = _iso(now + timedelta(seconds=self.lease_duration_seconds))

        doc = await get_system_db().outbox_worker_locks.find_one_and_update(
            {
                "_id": OUTBOX_WORKER_LOCK_ID,
                "$or": [
                    {"owner_id": self.owner_id},
                    {"expires_at": {"$lte": now_iso}},
                    {"expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "owner_id": self.owner_id,
                    "heartbeat_at": now_iso,
                    "expires_at": expires_at,
                }
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "owner_id": 1},
        )
        if doc and doc.get("owner_id") == self.owner_id:
            return True

        try:
            await get_system_db().outbox_worker_locks.insert_one(
                {
                    "_id": OUTBOX_WORKER_LOCK_ID,
                    "owner_id": self.owner_id,
                    "heartbeat_at": now_iso,
                    "expires_at": expires_at,
                }
            )
            return True
        except DuplicateKeyError:
            return False

    async def release_lock(self) -> None:
        await get_system_db().outbox_worker_locks.delete_one(
            {
                "_id": OUTBOX_WORKER_LOCK_ID,
                "owner_id": self.owner_id,
            }
        )

    async def recover_stuck_processing(self, *, limit: int = 5) -> int:
        cutoff = _iso(utc_now() - timedelta(seconds=self.processing_timeout_seconds))
        stuck_events = await get_system_db().outbox_events.find(
            {
                "event_type": {"$in": MIGRATION_EVENT_TYPES},
                "status": "processing",
                "processing_started_at": {"$lte": cutoff},
            },
            {"_id": 0},
        ).sort("processing_started_at", 1).to_list(limit)

        recovered = 0
        for event in stuck_events:
            updated = await self.mark_failed_or_parked(
                event,
                RuntimeError("processing timeout exceeded"),
                previous_status="processing",
            )
            if updated:
                recovered += 1
        return recovered

    async def process_batch(self, *, limit: int | None = None) -> int:
        processed_count = 0
        target = limit or self.batch_size
        for _ in range(target):
            event = await self.claim_next_event()
            if not event:
                break
            await self.process_event(event)
            processed_count += 1
            if self.drain_pause_seconds > 0:
                await asyncio.sleep(self.drain_pause_seconds)
        return processed_count

    async def claim_next_event(self) -> dict[str, Any] | None:
        now_iso = iso_now()
        event = await get_system_db().outbox_events.find_one_and_update(
            {
                "event_type": {"$in": MIGRATION_EVENT_TYPES},
                "$or": [
                    {"status": "pending"},
                    {
                        "status": "failed",
                        "retry_count": {"$lt": self.max_retries},
                        "$or": [
                            {"next_attempt_at": {"$lte": now_iso}},
                            {"next_attempt_at": {"$exists": False}},
                        ],
                    },
                ],
            },
            {
                "$set": {
                    "status": "processing",
                    "processing_started_at": now_iso,
                    "updated_at": now_iso,
                    "worker_id": self.owner_id,
                    "worker_mode": "temporary_operational_worker",
                },
                "$inc": {"attempt_count": 1},
                "$unset": {
                    "next_attempt_at": "",
                },
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return event

    async def process_event(self, event: dict[str, Any]) -> None:
        try:
            await self.handle_event(event)
            await self.mark_processed(event)
        except Exception as exc:
            logger.warning(
                "Outbox event processing failed event_id=%s event_type=%s error=%s",
                event.get("event_id"),
                event.get("event_type"),
                exc,
            )
            await self.mark_failed_or_parked(event, exc)

    async def handle_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload") or {}
        delay_ms = min(max(int(payload.get("simulate_delay_ms") or 25), 0), 250)
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)

        if payload.get("force_fail"):
            raise RuntimeError(str(payload.get("force_fail_message") or "forced outbox delivery failure"))

    async def mark_processed(self, event: dict[str, Any]) -> bool:
        now_iso = iso_now()
        update_result = await get_system_db().outbox_events.update_one(
            {
                "event_id": event.get("event_id"),
                "status": "processing",
            },
            {
                "$set": {
                    "status": "processed",
                    "processed_at": now_iso,
                    "updated_at": now_iso,
                    "last_error": None,
                },
                "$unset": {
                    "failed_at": "",
                    "parked_at": "",
                    "parked_reason": "",
                    "processing_started_at": "",
                },
            },
        )
        return update_result.modified_count == 1

    async def mark_failed_or_parked(
        self,
        event: dict[str, Any],
        error: Exception,
        *,
        previous_status: str = "processing",
    ) -> bool:
        now = utc_now()
        now_iso = _iso(now)
        retry_count = int(event.get("retry_count") or 0) + 1
        error_message = str(error)

        if retry_count >= self.max_retries:
            update_doc = {
                "$set": {
                    "status": "parked",
                    "retry_count": retry_count,
                    "failed_at": now_iso,
                    "parked_at": now_iso,
                    "parked_reason": "retry_limit_exceeded",
                    "last_error": error_message,
                    "updated_at": now_iso,
                },
                "$unset": {
                    "next_attempt_at": "",
                    "processing_started_at": "",
                },
            }
        else:
            backoff_seconds = min(self.backoff_base_seconds * (2 ** (retry_count - 1)), 30)
            update_doc = {
                "$set": {
                    "status": "failed",
                    "retry_count": retry_count,
                    "failed_at": now_iso,
                    "next_attempt_at": _iso(now + timedelta(seconds=backoff_seconds)),
                    "last_error": error_message,
                    "updated_at": now_iso,
                },
                "$unset": {
                    "processing_started_at": "",
                },
            }

        update_result = await get_system_db().outbox_events.update_one(
            {
                "event_id": event.get("event_id"),
                "status": previous_status,
            },
            update_doc,
        )
        return update_result.modified_count == 1


outbox_lifecycle_worker = OutboxLifecycleWorker()
