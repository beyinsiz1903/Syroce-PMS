"""
OTA-002: Outbox Pattern Test Suite
====================================
Tests for the guaranteed delivery outbox pattern.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from core.outbox_service import (
    BOOKING_CANCELLED,
    BOOKING_CREATED,
    DEFAULT_MAX_ATTEMPTS,
    INVENTORY_BLOCKED,
    INVENTORY_RELEASED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSED,
    STATUS_PROCESSING,
    STATUS_RETRY,
    _build_idempotency_key,
    compute_next_available_at,
    enqueue_outbox_event,
    is_retryable_error,
)
from core.outbox_worker import OutboxWorker


TEST_TENANT = f"test_outbox_{uuid.uuid4().hex[:8]}"
TEST_PROPERTY = f"prop_{uuid.uuid4().hex[:8]}"


async def _get_db():
    """Create a fresh Motor client for testing."""
    import os
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def _cleanup_events(db):
    await db.outbox_events.delete_many({"tenant_id": TEST_TENANT})


# ─── A. Enqueue Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_creates_pending_event():
    """Enqueue should create an event with status=pending and all required fields."""
    client, db = await _get_db()
    try:
        await _cleanup_events(db)

        result = await enqueue_outbox_event(
            db,
            tenant_id=TEST_TENANT,
            event_type=BOOKING_CREATED,
            entity_type="booking",
            entity_id="booking_001",
            property_id=TEST_PROPERTY,
            payload={"check_in": "2026-04-01", "check_out": "2026-04-03", "property_id": TEST_PROPERTY},
        )

        assert result["status"] == STATUS_PENDING
        assert result["tenant_id"] == TEST_TENANT
        assert result["event_type"] == BOOKING_CREATED
        assert result["entity_type"] == "booking"
        assert result["entity_id"] == "booking_001"
        assert result["attempt_count"] == 0
        assert result["max_attempts"] == DEFAULT_MAX_ATTEMPTS
        assert result["idempotency_key"] is not None
        assert result["correlation_id"] is not None
        assert result["available_at"] is not None
        assert result["created_at"] is not None

        stored = await db.outbox_events.find_one({"id": result["id"]}, {"_id": 0})
        assert stored is not None
        assert stored["status"] == STATUS_PENDING
    finally:
        await _cleanup_events(db)
        client.close()


@pytest.mark.asyncio
async def test_enqueue_with_session_inside_transaction():
    """Outbox event should be inserted within a MongoDB transaction."""
    client, db = await _get_db()
    booking_id = f"txn_booking_{uuid.uuid4().hex[:8]}"
    try:
        async with await client.start_session() as session:
            try:
                async with session.start_transaction():
                    await db.bookings.insert_one(
                        {
                            "id": booking_id,
                            "tenant_id": TEST_TENANT,
                            "status": "confirmed",
                            "check_in": "2026-05-01",
                            "check_out": "2026-05-03",
                        },
                        session=session,
                    )
                    result = await enqueue_outbox_event(
                        db,
                        session=session,
                        tenant_id=TEST_TENANT,
                        event_type=BOOKING_CREATED,
                        entity_type="booking",
                        entity_id=booking_id,
                        payload={"check_in": "2026-05-01", "check_out": "2026-05-03", "property_id": TEST_TENANT},
                    )
            except OperationFailure as e:
                if e.code == 20:
                    pytest.skip("MongoDB transactions require replica set (standalone mode detected)")
                raise

        booking = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
        event = await db.outbox_events.find_one({"id": result["id"]}, {"_id": 0})
        assert booking is not None
        assert event is not None
        assert event["status"] == STATUS_PENDING
    finally:
        await db.bookings.delete_one({"id": booking_id})
        await _cleanup_events(db)
        client.close()


@pytest.mark.asyncio
async def test_enqueue_idempotent_duplicate():
    """Enqueuing the same event twice should not create duplicates."""
    client, db = await _get_db()
    try:
        payload = {"check_in": "2026-06-01", "check_out": "2026-06-03", "property_id": TEST_TENANT}
        entity_id = f"idempotent_{uuid.uuid4().hex[:8]}"

        await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
            entity_type="booking", entity_id=entity_id, payload=payload,
        )
        await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
            entity_type="booking", entity_id=entity_id, payload=payload,
        )

        count = await db.outbox_events.count_documents({
            "tenant_id": TEST_TENANT, "entity_id": entity_id, "event_type": BOOKING_CREATED,
        })
        assert count == 1
    finally:
        await _cleanup_events(db)
        client.close()


# ─── B. Worker Success Flow ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_processes_pending_event():
    """Worker should claim and process a pending event."""
    client, db = await _get_db()
    try:
        entity_id = f"worker_test_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
            entity_type="booking", entity_id=entity_id,
            payload={"check_in": "2026-07-01", "check_out": "2026-07-03", "property_id": TEST_TENANT},
        )

        worker = OutboxWorker(poll_interval=0.1, batch_size=1)

        with patch("core.outbox_dispatcher.dispatch_outbox_event", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = (True, "Test success")

            # Override worker's db reference
            with patch("core.outbox_worker.db", db):
                from pymongo import ReturnDocument
                claimed = await db.outbox_events.find_one_and_update(
                    {
                        "id": event["id"],
                        "status": STATUS_PENDING,
                        "max_attempts": {"$exists": True},
                    },
                    {
                        "$set": {"status": STATUS_PROCESSING, "last_attempt_at": datetime.now(timezone.utc).isoformat()},
                        "$inc": {"attempt_count": 1},
                    },
                    projection={"_id": 0},
                    return_document=ReturnDocument.AFTER,
                )
                assert claimed is not None
                assert claimed["status"] == STATUS_PROCESSING

                await worker._process_event(claimed)

        stored = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert stored["status"] == STATUS_PROCESSED
        assert stored["processed_at"] is not None
    finally:
        await _cleanup_events(db)
        client.close()


# ─── C. Retry Flow ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_retries_on_transient_failure():
    """Worker should schedule retry on transient failure."""
    client, db = await _get_db()
    try:
        entity_id = f"retry_test_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CANCELLED,
            entity_type="booking", entity_id=entity_id,
            payload={"check_in": "2026-08-01", "check_out": "2026-08-03", "property_id": TEST_TENANT},
        )

        worker = OutboxWorker(poll_interval=0.1, batch_size=1)

        with patch("core.outbox_dispatcher.dispatch_outbox_event", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = (False, "retryable: connection timeout")

            with patch("core.outbox_worker.db", db):
                claimed = await db.outbox_events.find_one_and_update(
                    {"id": event["id"], "status": STATUS_PENDING},
                    {
                        "$set": {"status": STATUS_PROCESSING, "last_attempt_at": datetime.now(timezone.utc).isoformat()},
                        "$inc": {"attempt_count": 1},
                    },
                    projection={"_id": 0},
                )
                await worker._process_event(claimed)

        stored = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert stored["status"] == STATUS_RETRY
        assert stored["last_error"] is not None
        assert "timeout" in stored["last_error"]
    finally:
        await _cleanup_events(db)
        client.close()


# ─── D. Max Retry → Failed ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_fails_after_max_attempts():
    """Event should be marked as failed after reaching max_attempts."""
    client, db = await _get_db()
    try:
        entity_id = f"maxretry_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=INVENTORY_BLOCKED,
            entity_type="room_block", entity_id=entity_id, max_attempts=2,
            payload={"property_id": TEST_TENANT, "room_id": "r1", "date_start": "2026-01-01", "date_end": "2026-01-05"},
        )

        await db.outbox_events.update_one(
            {"id": event["id"]},
            {"$set": {"attempt_count": 2, "status": STATUS_PROCESSING}},
        )

        worker = OutboxWorker()
        updated = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})

        with patch("core.outbox_worker.db", db):
            await worker._handle_failure(updated, "retryable: server error 503")

        stored = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert stored["status"] == STATUS_FAILED
        assert stored["failed_at"] is not None
    finally:
        await _cleanup_events(db)
        client.close()


@pytest.mark.asyncio
async def test_permanent_error_fails_immediately():
    """Permanent errors should mark event as failed without retry."""
    client, db = await _get_db()
    try:
        entity_id = f"perm_fail_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=INVENTORY_RELEASED,
            entity_type="room_block", entity_id=entity_id,
            payload={"property_id": TEST_TENANT, "room_id": "r2", "date_start": "2026-02-01", "date_end": "2026-02-05"},
        )

        worker = OutboxWorker()

        with patch("core.outbox_dispatcher.dispatch_outbox_event", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = (False, "permanent: invalid payload schema_mismatch")

            with patch("core.outbox_worker.db", db):
                claimed = await db.outbox_events.find_one_and_update(
                    {"id": event["id"], "status": STATUS_PENDING},
                    {
                        "$set": {"status": STATUS_PROCESSING, "last_attempt_at": datetime.now(timezone.utc).isoformat()},
                        "$inc": {"attempt_count": 1},
                    },
                    projection={"_id": 0},
                )
                await worker._process_event(claimed)

        stored = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert stored["status"] == STATUS_FAILED
    finally:
        await _cleanup_events(db)
        client.close()


# ─── E. Duplicate Claim Protection ──────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_claim_protection():
    """Two sequential claims should not claim the same event."""
    client, db = await _get_db()
    try:
        entity_id = f"claim_race_{uuid.uuid4().hex[:8]}"
        await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
            entity_type="booking", entity_id=entity_id,
            payload={"check_in": "2026-09-01", "check_out": "2026-09-03", "property_id": TEST_TENANT},
        )

        now = datetime.now(timezone.utc).isoformat()

        # First claim
        claimed1 = await db.outbox_events.find_one_and_update(
            {
                "tenant_id": TEST_TENANT,
                "entity_id": entity_id,
                "status": STATUS_PENDING,
                "max_attempts": {"$exists": True},
            },
            {"$set": {"status": STATUS_PROCESSING, "last_attempt_at": now, "worker_id": "w1"}, "$inc": {"attempt_count": 1}},
            projection={"_id": 0},
        )

        # Second claim on the same entity — should return None
        claimed2 = await db.outbox_events.find_one_and_update(
            {
                "tenant_id": TEST_TENANT,
                "entity_id": entity_id,
                "status": STATUS_PENDING,
                "max_attempts": {"$exists": True},
            },
            {"$set": {"status": STATUS_PROCESSING, "last_attempt_at": now, "worker_id": "w2"}, "$inc": {"attempt_count": 1}},
            projection={"_id": 0},
        )

        assert claimed1 is not None
        assert claimed2 is None, "Second claim should return None — event already claimed"
    finally:
        await _cleanup_events(db)
        client.close()


# ─── F. Transaction Rollback Test ────────────────────────────────────


@pytest.mark.asyncio
async def test_transaction_rollback_removes_outbox_event():
    """If the parent transaction rolls back, the outbox event should not exist."""
    client, db = await _get_db()
    booking_id = f"rollback_{uuid.uuid4().hex[:8]}"
    event_id = None

    try:
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    await db.bookings.insert_one(
                        {"id": booking_id, "tenant_id": TEST_TENANT, "status": "confirmed"},
                        session=session,
                    )
                    result = await enqueue_outbox_event(
                        db, session=session,
                        tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
                        entity_type="booking", entity_id=booking_id,
                        payload={"check_in": "2026-10-01", "check_out": "2026-10-03", "property_id": TEST_TENANT},
                    )
                    event_id = result["id"]
                    raise Exception("Simulated business logic failure")
        except Exception:
            pass

        booking = await db.bookings.find_one({"id": booking_id})
        assert booking is None, "Booking should not exist after rollback"

        if event_id:
            event = await db.outbox_events.find_one({"id": event_id})
            assert event is None, "Outbox event should not exist after rollback"
    finally:
        await db.bookings.delete_many({"id": booking_id})
        await _cleanup_events(db)
        client.close()


# ─── G. Error Classification ────────────────────────────────────────


def test_retryable_error_classification():
    """Timeout, 5xx, and network errors should be retryable."""
    assert is_retryable_error("Connection timeout") is True
    assert is_retryable_error("HTTP 503 Service Unavailable") is True
    assert is_retryable_error("Connection refused") is True
    assert is_retryable_error("Rate limit exceeded (429)") is True
    assert is_retryable_error("Network unreachable") is True


def test_permanent_error_classification():
    """Mapping, auth, and payload errors should be permanent."""
    assert is_retryable_error("mapping error: room type not found") is False
    assert is_retryable_error("invalid payload format") is False
    assert is_retryable_error("Authentication failed permanently") is False
    assert is_retryable_error("schema_mismatch in response") is False
    assert is_retryable_error("unsupported rate plan") is False


# ─── H. Requeue / Replay ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requeue_failed_event():
    """Requeue should reset a failed event to pending."""
    client, db = await _get_db()
    try:
        entity_id = f"requeue_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CANCELLED,
            entity_type="booking", entity_id=entity_id,
            payload={"property_id": TEST_TENANT, "check_in": "2026-11-01", "check_out": "2026-11-03"},
        )
        await db.outbox_events.update_one(
            {"id": event["id"]},
            {"$set": {"status": STATUS_FAILED, "attempt_count": 5, "last_error": "some error"}},
        )

        now = datetime.now(timezone.utc).isoformat()
        result = await db.outbox_events.find_one_and_update(
            {"id": event["id"], "status": STATUS_FAILED},
            {"$set": {"status": STATUS_PENDING, "available_at": now, "attempt_count": 0, "last_error": None}},
        )
        assert result is not None

        stored = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert stored["status"] == STATUS_PENDING
        assert stored["attempt_count"] == 0
    finally:
        await _cleanup_events(db)
        client.close()


@pytest.mark.asyncio
async def test_replay_failed_events_by_provider():
    """Replay should requeue all failed events for a specific provider."""
    client, db = await _get_db()
    try:
        for i in range(3):
            event = await enqueue_outbox_event(
                db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
                entity_type="booking", entity_id=f"replay_{i}_{uuid.uuid4().hex[:8]}",
                provider="exely",
                payload={"property_id": TEST_TENANT, "check_in": "2026-12-01", "check_out": "2026-12-03"},
            )
            await db.outbox_events.update_one({"id": event["id"]}, {"$set": {"status": STATUS_FAILED}})

        now = datetime.now(timezone.utc).isoformat()
        result = await db.outbox_events.update_many(
            {"status": STATUS_FAILED, "provider": "exely", "tenant_id": TEST_TENANT},
            {"$set": {"status": STATUS_PENDING, "available_at": now, "attempt_count": 0, "last_error": None}},
        )
        assert result.modified_count == 3
    finally:
        await _cleanup_events(db)
        client.close()


# ─── I. Backoff Computation ─────────────────────────────────────────


def test_retry_backoff_schedule():
    """Backoff schedule should follow the defined policy."""
    dt1 = datetime.fromisoformat(compute_next_available_at(1))
    dt2 = datetime.fromisoformat(compute_next_available_at(2))
    dt3 = datetime.fromisoformat(compute_next_available_at(3))
    assert dt2 > dt1
    assert dt3 > dt2


# ─── J. Idempotency Key Generation ──────────────────────────────────


def test_idempotency_key_deterministic():
    """Same inputs should produce the same idempotency key."""
    payload = {"room_id": "r1", "check_in": "2026-01-01"}
    key1 = _build_idempotency_key("tenant1", "booking.created.v1", "b1", payload)
    key2 = _build_idempotency_key("tenant1", "booking.created.v1", "b1", payload)
    assert key1 == key2


def test_idempotency_key_different_for_different_payloads():
    """Different payloads should produce different idempotency keys."""
    payload1 = {"room_id": "r1", "check_in": "2026-01-01"}
    payload2 = {"room_id": "r1", "check_in": "2026-01-02"}
    key1 = _build_idempotency_key("tenant1", "booking.created.v1", "b1", payload1)
    key2 = _build_idempotency_key("tenant1", "booking.created.v1", "b1", payload2)
    assert key1 != key2


# ─── K. Worker Metrics ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_metrics():
    """Worker should track processing metrics."""
    client, db = await _get_db()
    try:
        worker = OutboxWorker()
        assert worker.metrics["processed_total"] == 0
        assert worker.metrics["running"] is False

        entity_id = f"metrics_{uuid.uuid4().hex[:8]}"
        event = await enqueue_outbox_event(
            db, tenant_id=TEST_TENANT, event_type=BOOKING_CREATED,
            entity_type="booking", entity_id=entity_id,
            payload={"property_id": TEST_TENANT, "check_in": "2026-07-15", "check_out": "2026-07-17"},
        )

        with patch("core.outbox_dispatcher.dispatch_outbox_event", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = (True, "OK")

            with patch("core.outbox_worker.db", db):
                claimed = await db.outbox_events.find_one_and_update(
                    {"id": event["id"], "status": STATUS_PENDING},
                    {"$set": {"status": STATUS_PROCESSING}, "$inc": {"attempt_count": 1}},
                    projection={"_id": 0},
                )
                await worker._process_event(claimed)

        assert worker.metrics["processed_total"] == 1
        assert worker.metrics["last_processed_at"] is not None
    finally:
        await _cleanup_events(db)
        client.close()
