import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from core.database import db
from shared_kernel.migration_observability import MigrationObservabilityService
from shared_kernel.outbox_lifecycle import OutboxLifecycleWorker


TEST_LOOP = asyncio.new_event_loop()


def run_async(coro):
    return TEST_LOOP.run_until_complete(coro)


def _build_event(*, tenant_id: str, event_type: str, status: str = "pending", payload=None, created_at=None, retry_count: int = 0):
    now = datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())
    return {
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
        "property_id": tenant_id,
        "correlation_id": f"corr-{uuid.uuid4()}",
        "payload": payload or {},
        "status": status,
        "created_at": (created_at or now).isoformat(),
        "reservation_id": str(uuid.uuid4()),
        "retry_count": retry_count,
    }


def test_outbox_worker_processes_pending_event_to_processed():
    async def _run():
        tenant_id = f"tenant-{uuid.uuid4()}"
        event = _build_event(tenant_id=tenant_id, event_type="reservation.created.v1")
        await db.outbox_events.insert_one(event)

        worker = OutboxLifecycleWorker(batch_size=1, poll_interval_seconds=0.01, backoff_base_seconds=0.01, drain_pause_seconds=0)
        try:
            await worker.process_batch(limit=1)
            stored = await db.outbox_events.find_one({"event_id": event["event_id"]}, {"_id": 0})
            assert stored["status"] == "processed"
            assert stored["processed_at"]
            assert stored["attempt_count"] == 1
            assert stored.get("last_error") is None
        finally:
            await db.outbox_events.delete_many({"tenant_id": tenant_id})

    run_async(_run())


def test_outbox_worker_retries_then_parks_forced_failure():
    async def _run():
        tenant_id = f"tenant-{uuid.uuid4()}"
        event = _build_event(
            tenant_id=tenant_id,
            event_type="folio.opened.v1",
            payload={"force_fail": True, "force_fail_message": "boom"},
        )
        await db.outbox_events.insert_one(event)

        worker = OutboxLifecycleWorker(batch_size=1, poll_interval_seconds=0.01, backoff_base_seconds=0, drain_pause_seconds=0, max_retries=3)
        try:
            await worker.process_batch(limit=1)
            await worker.process_batch(limit=1)
            await worker.process_batch(limit=1)
            stored = await db.outbox_events.find_one({"event_id": event["event_id"]}, {"_id": 0})
            assert stored["status"] == "parked"
            assert stored["retry_count"] == 3
            assert stored["parked_at"]
            assert stored["parked_reason"] == "retry_limit_exceeded"
            assert stored["last_error"] == "boom"
        finally:
            await db.outbox_events.delete_many({"tenant_id": tenant_id})

    run_async(_run())


def test_migration_observability_exposes_lifecycle_counts_and_ages():
    async def _run():
        tenant_id = f"tenant-{uuid.uuid4()}"
        now = datetime.now(timezone.utc)
        docs = [
            _build_event(
                tenant_id=tenant_id,
                event_type="reservation.created.v1",
                status="pending",
                created_at=now - timedelta(minutes=30),
            ),
            _build_event(
                tenant_id=tenant_id,
                event_type="inventory.blocked.v1",
                status="processing",
                created_at=now - timedelta(minutes=10),
            ),
            _build_event(
                tenant_id=tenant_id,
                event_type="folio.opened.v1",
                status="processed",
                created_at=now - timedelta(minutes=5),
            ) | {"processed_at": now.isoformat()},
            _build_event(
                tenant_id=tenant_id,
                event_type="inventory.released.v1",
                status="failed",
                created_at=now - timedelta(minutes=40),
                retry_count=2,
            ) | {"failed_at": now.isoformat(), "last_error": "retry me", "next_attempt_at": now.isoformat()},
            _build_event(
                tenant_id=tenant_id,
                event_type="folio.opened.v1",
                status="parked",
                created_at=now - timedelta(minutes=50),
                retry_count=3,
            ) | {"parked_at": now.isoformat(), "parked_reason": "retry_limit_exceeded", "last_error": "boom"},
        ]

        await db.outbox_events.insert_many(docs)

        service = MigrationObservabilityService()
        try:
            payload = await service.get_dashboard(tenant_id)
            lifecycle = payload["outbox"]["lifecycle"]
            queue_depth = payload["outbox"]["queue_depth"]
            assert lifecycle["pending_count"] == 1
            assert lifecycle["processing_count"] == 1
            assert lifecycle["processed_count"] == 1
            assert lifecycle["failed_count"] == 1
            assert lifecycle["parked_count"] == 1
            assert lifecycle["oldest_pending_age_minutes"] is not None
            assert lifecycle["oldest_failed_age_minutes"] is not None
            assert queue_depth["stale_pending"] == 1
        finally:
            await db.outbox_events.delete_many({"tenant_id": tenant_id})

    run_async(_run())