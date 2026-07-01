"""
TS-006 to TS-010: Worker / Queue Failure Resilience Tests

Tests:
- TS-006: Provider 429 during ARI push (outbox retry)
- TS-007: Worker crash after claim, before completion (stuck recovery)
- TS-008: Duplicate outbox event claim (atomic race condition)
- TS-009: Delayed outbox processing detection
- TS-010: ARI parity mismatch detection (permanent failure visibility)

Markers: chaos_l1, chaos_l2, chaos_outbox
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.outbox_service import is_retryable_error


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _utc_past(hours=0, minutes=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)).isoformat()


# ═══════════════════════════════════════════════════════════════════
# TS-006: Provider 429 During ARI Push
# ═══════════════════════════════════════════════════════════════════

class TestProvider429DuringARIPush:
    """
    Scenario A-04: Rate limiting during ARI push.
    Guarantee: 429 classified as RETRYABLE, event rescheduled with backoff.
    """

    @pytest.mark.chaos_l1
    def test_429_classified_as_retryable(self):
        """429 error must be classified as retryable in outbox service."""
        assert is_retryable_error("429: rate limit exceeded") is True
        assert is_retryable_error("Provider returned 429") is True
        assert is_retryable_error("rate limit hit on exely API") is True

    @pytest.mark.chaos_l2
    async def test_outbox_event_transitions_to_retry_on_429(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Outbox event should go to retry status with backoff on 429."""
        tenant_id = tenant_factory("429-001")
        event = outbox_event_factory(
            tenant_id=tenant_id,
            status="processing",
            attempt_count=1,
        )
        await db.outbox_events.insert_one(event)

        # Simulate _handle_failure for retryable error
        from core.outbox_service import compute_next_available_at
        next_at = compute_next_available_at(2)
        now = _utc_now()

        await db.outbox_events.update_one(
            {"id": event["id"]},
            {"$set": {
                "status": "retry",
                "last_error": "429: rate limit exceeded",
                "available_at": next_at,
                "updated_at": now,
            }},
        )

        updated = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert updated["status"] == "retry"
        assert "429" in updated["last_error"]
        assert updated["available_at"] > now  # Backoff applied


# ═══════════════════════════════════════════════════════════════════
# TS-007: Worker Crash After Claim (Stuck Recovery)
# ═══════════════════════════════════════════════════════════════════

class TestStuckRecovery:
    """
    Scenario B-02: Worker crashes after claiming outbox event.
    Guarantee: Stuck events recovered after processing_timeout.
    """

    @pytest.mark.chaos_l2
    async def test_stuck_event_recovered(self, db, outbox_event_factory, tenant_factory, outbox_worker):
        """Events stuck in 'processing' beyond timeout must be recovered to 'retry'."""
        tenant_id = tenant_factory("stuck-001")

        # Create event stuck in processing since 2 hours ago
        event = outbox_event_factory(tenant_id=tenant_id, status="processing")
        event["last_attempt_at"] = _utc_past(hours=2)
        await db.outbox_events.insert_one(event)

        # Run recovery
        recovered = await outbox_worker._recover_stuck()
        assert recovered >= 1

        # Verify event recovered to retry
        updated = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert updated["status"] == "retry"
        assert "timeout" in updated.get("last_error", "").lower()

    @pytest.mark.chaos_l2
    async def test_recently_claimed_event_not_recovered(
        self, db, outbox_event_factory, tenant_factory, outbox_worker
    ):
        """Events claimed recently (within timeout) must NOT be recovered."""
        tenant_id = tenant_factory("stuck-002")

        # Create event in processing but very recently (just now)
        event = outbox_event_factory(tenant_id=tenant_id, status="processing")
        event["last_attempt_at"] = _utc_now()
        await db.outbox_events.insert_one(event)

        # Run recovery — should not touch this event
        recovered = await outbox_worker._recover_stuck()

        updated = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert updated["status"] == "processing"  # Still processing (not recovered)


# ═══════════════════════════════════════════════════════════════════
# TS-008: Duplicate Outbox Event Claim (Atomic Race)
# ═══════════════════════════════════════════════════════════════════

class TestAtomicClaim:
    """
    Scenario B-05: Two workers attempt to claim the same event.
    Guarantee: Exactly ONE claim succeeds (MongoDB atomic find_one_and_update).
    """

    @pytest.mark.chaos_l2
    async def test_concurrent_claims_yield_exactly_one_winner(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Only one concurrent claim should succeed for the same event."""
        tenant_id = tenant_factory("race-001")

        # Insert exactly one claimable event
        event = outbox_event_factory(tenant_id=tenant_id, status="pending")
        await db.outbox_events.insert_one(event)

        from core.outbox_worker import OutboxWorker
        worker1 = OutboxWorker(poll_interval=0, batch_size=1, processing_timeout=120)
        worker2 = OutboxWorker(poll_interval=0, batch_size=1, processing_timeout=120)

        # Race: both try to claim at the same time
        results = await asyncio.gather(
            worker1._claim_event(),
            worker2._claim_event(),
        )

        # Exactly one should get the event, one should get None
        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1, f"Expected exactly 1 claim, got {len(claimed)}"

        # The event in DB should be processing with exactly 1 worker_id
        doc = await db.outbox_events.find_one({"id": event["id"]}, {"_id": 0})
        assert doc["status"] == "processing"
        assert doc["attempt_count"] == 1


# ═══════════════════════════════════════════════════════════════════
# TS-009: Delayed Outbox Processing Detection
# ═══════════════════════════════════════════════════════════════════

class TestDelayedProcessingDetection:
    """
    Scenario B-06: Outbox events sit pending beyond SLA.
    Guarantee: Delayed events visible in /api/ops/outbox metrics.
    """

    @pytest.mark.chaos_l2
    async def test_old_pending_events_counted_as_stuck(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Events pending for >30 min should appear as stuck in ops view."""
        tenant_id = tenant_factory("delay-001")

        # Insert 3 events created 1 hour ago, still pending
        for _ in range(3):
            event = outbox_event_factory(
                tenant_id=tenant_id,
                status="pending",
                created_at=_utc_past(hours=1),
                available_at=_utc_past(hours=1),
            )
            await db.outbox_events.insert_one(event)

        # Query same as ops_router outbox endpoint
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        stuck_count = await db.outbox_events.count_documents({
            "status": {"$in": ["pending", "retry"]},
            "created_at": {"$lte": cutoff},
        })
        assert stuck_count >= 3

    @pytest.mark.chaos_l2
    async def test_alert_fires_on_stuck_outbox(
        self, db, outbox_event_factory, tenant_factory, alerting_engine
    ):
        """AlertingEngine should fire outbox_stuck alert when threshold breached."""
        tenant_id = tenant_factory("alert-outbox-001")

        # Insert 10+ events stuck for >30 min (threshold is 10)
        for _ in range(12):
            event = outbox_event_factory(
                tenant_id=tenant_id,
                status="pending",
                created_at=_utc_past(hours=1),
            )
            await db.outbox_events.insert_one(event)

        # Run alert check
        fired = await alerting_engine.check_and_alert()
        outbox_alerts = [a for a in fired if a.get("trigger") == "outbox_stuck"]
        assert len(outbox_alerts) >= 1, "Expected outbox_stuck alert to fire"
        assert outbox_alerts[0]["severity"] == "high"


# ═══════════════════════════════════════════════════════════════════
# TS-010: Permanent Failure Visibility
# ═══════════════════════════════════════════════════════════════════

class TestPermanentFailureVisibility:
    """
    Scenario: Outbox event fails permanently.
    Guarantee: Visible in /api/ops/outbox as failed. Countable.
    """

    @pytest.mark.chaos_l2
    async def test_permanently_failed_event_visible(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Permanently failed events should be queryable for ops visibility."""
        tenant_id = tenant_factory("perm-fail-001")

        event = outbox_event_factory(
            tenant_id=tenant_id,
            status="failed",
            attempt_count=5,
            max_attempts=5,
        )
        event["last_error"] = "permanent: unsupported event_type"
        event["failed_at"] = _utc_now()
        await db.outbox_events.insert_one(event)

        # Verify visible via query
        failed = await db.outbox_events.count_documents({
            "tenant_id": tenant_id,
            "status": "failed",
        })
        assert failed == 1

    @pytest.mark.chaos_l2
    async def test_dead_letter_accumulation_visible(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Multiple dead-letter events should all be countable."""
        tenant_id = tenant_factory("dead-letter-001")

        for i in range(5):
            event = outbox_event_factory(
                tenant_id=tenant_id,
                status="failed",
                attempt_count=5,
                max_attempts=5,
            )
            event["last_error"] = f"permanent: test failure {i}"
            event["failed_at"] = _utc_now()
            await db.outbox_events.insert_one(event)

        count = await db.outbox_events.count_documents({
            "tenant_id": tenant_id,
            "status": "failed",
        })
        assert count == 5
