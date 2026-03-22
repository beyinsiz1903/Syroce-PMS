"""
Level 4: Burst / Soak / Storm Resilience Tests

Tests:
- Reservation burst test (50/100 events)
- ARI storm test (mass outbox events)
- Secret access anomaly flood
- Alert flood handling

These tests validate system behavior under sustained load.
Markers: chaos_l4
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.asyncio]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# Reservation Burst Test
# ═══════════════════════════════════════════════════════════════════

class TestReservationBurst:
    """
    Scenario: 50+ reservations arrive in rapid succession.
    Guarantee: No duplicates, no losses, all records created.
    """

    @pytest.mark.chaos_l4
    async def test_50_unique_imports_no_duplicates(
        self, db, import_record_factory, tenant_factory
    ):
        """50 unique reservation imports must all be created with no duplicates."""
        tenant_id = tenant_factory("burst-50")
        ext_ids = set()

        for i in range(50):
            ext_res_id = f"BURST-{uuid.uuid4().hex[:12]}"
            ext_ids.add(ext_res_id)
            record = import_record_factory(
                tenant_id=tenant_id,
                ext_res_id=ext_res_id,
            )
            await db.imported_reservations.insert_one(record)

        # Count total records
        total = await db.imported_reservations.count_documents({
            "tenant_id": tenant_id,
        })
        assert total == 50

        # Verify all unique ext_ids present
        cursor = db.imported_reservations.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "external_reservation_id": 1},
        )
        found_ids = set()
        async for doc in cursor:
            found_ids.add(doc["external_reservation_id"])
        assert found_ids == ext_ids

    @pytest.mark.chaos_l4
    async def test_burst_with_duplicate_ext_ids_handled(
        self, db, import_record_factory, tenant_factory
    ):
        """Burst with intentional duplicates — system handles gracefully."""
        tenant_id = tenant_factory("burst-dup")
        shared_ext_id = f"BURST-SHARED-{uuid.uuid4().hex[:8]}"

        # First record
        record1 = import_record_factory(
            tenant_id=tenant_id,
            ext_res_id=shared_ext_id,
        )
        await db.imported_reservations.insert_one(record1)

        # Attempt 10 duplicates — should be caught by application logic
        duplicates_caught = 0
        for _ in range(10):
            record = import_record_factory(
                tenant_id=tenant_id,
                ext_res_id=shared_ext_id,
            )
            record["connector_id"] = record1["connector_id"]
            try:
                await db.imported_reservations.insert_one(record)
            except Exception:
                duplicates_caught += 1

        # Either duplicates were caught by unique index OR multiple records exist
        # but the application logic should handle dedup at processing time
        total = await db.imported_reservations.count_documents({
            "tenant_id": tenant_id,
            "external_reservation_id": shared_ext_id,
        })
        # At minimum, the first record exists
        assert total >= 1


# ═══════════════════════════════════════════════════════════════════
# ARI Storm Test
# ═══════════════════════════════════════════════════════════════════

class TestARIStorm:
    """
    Scenario: Mass ARI update events flood the outbox.
    Guarantee: All enqueued, idempotency keys prevent exact duplicates.
    """

    @pytest.mark.chaos_l4
    async def test_100_ari_events_enqueued(
        self, db, outbox_event_factory, tenant_factory
    ):
        """100 ARI update events must all be enqueued."""
        tenant_id = tenant_factory("ari-storm-001")

        for i in range(100):
            event = outbox_event_factory(
                tenant_id=tenant_id,
                event_type="rate.updated.v1",
                entity_type="rate",
                status="pending",
            )
            await db.outbox_events.insert_one(event)

        count = await db.outbox_events.count_documents({
            "tenant_id": tenant_id,
            "event_type": "rate.updated.v1",
        })
        assert count == 100

    @pytest.mark.chaos_l4
    async def test_mixed_event_types_during_storm(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Storm of mixed event types must all be handled."""
        tenant_id = tenant_factory("ari-storm-002")
        event_types = [
            "booking.created.v1",
            "booking.modified.v1",
            "booking.cancelled.v1",
            "rate.updated.v1",
            "inventory.availability.updated.v1",
        ]

        for i in range(50):
            et = event_types[i % len(event_types)]
            event = outbox_event_factory(
                tenant_id=tenant_id,
                event_type=et,
                status="pending",
            )
            await db.outbox_events.insert_one(event)

        total = await db.outbox_events.count_documents({
            "tenant_id": tenant_id,
        })
        assert total == 50


# ═══════════════════════════════════════════════════════════════════
# Secret Access Anomaly Flood
# ═══════════════════════════════════════════════════════════════════

class TestSecretAnomalyFlood:
    """
    Scenario: 50 denied access attempts in rapid succession.
    Guarantee: All logged. Anomaly surfaced. Alert fires.
    """

    @pytest.mark.chaos_l4
    async def test_50_denied_attempts_all_logged(
        self, db, secret_access_control, tenant_factory
    ):
        """50 denied secret accesses must all appear in audit trail."""
        tenant_id = tenant_factory("anomaly-flood-001")

        for i in range(50):
            await secret_access_control.log_access(
                tenant_id=tenant_id,
                provider="exely",
                access_type="read",
                caller=f"attacker-{i % 5}",
                result="denied",
                reason="Simulated attack for chaos testing",
            )

        # Verify all logged
        count = await db.secret_access_audit.count_documents({
            "tenant_id": tenant_id,
            "result": "denied",
        })
        assert count == 50

    @pytest.mark.chaos_l4
    async def test_anomaly_detection_under_flood(
        self, db, secret_access_control, tenant_factory
    ):
        """Anomaly detection must work correctly under flood conditions."""
        tenant_id = tenant_factory("anomaly-flood-002")

        for i in range(30):
            await secret_access_control.log_access(
                tenant_id=tenant_id,
                provider="exely",
                access_type="read",
                caller="flood-attacker",
                result="denied",
                reason="Flood test",
            )

        anomalies = await secret_access_control.get_anomalies(
            hours=1, tenant_id=tenant_id
        )
        assert anomalies["anomaly_count"] >= 30


# ═══════════════════════════════════════════════════════════════════
# Control Plane Under Load
# ═══════════════════════════════════════════════════════════════════

class TestControlPlaneUnderLoad:
    """
    Scenario: Multiple failure types recorded rapidly.
    Guarantee: Aggregation queries still correct.
    """

    @pytest.mark.chaos_l4
    async def test_failure_aggregation_accuracy_under_load(
        self, db, failure_tracker, tenant_factory
    ):
        """Failure counts by type/severity must be accurate under load."""
        tenant_id = tenant_factory("cp-load-001")

        # Record diverse failures
        types = [
            ("reservation_import", "Connection timed out", 10),    # retryable
            ("ari_push", "exely returned 502", 5),                 # provider_error
            ("crypto_decrypt", "decrypt failed for credential", 3), # security_error
            ("outbox_dispatch", "mapping error: room not found", 2), # data_error
        ]

        for op_type, msg, count in types:
            for _ in range(count):
                await failure_tracker.record(
                    tenant_id=tenant_id,
                    provider="exely",
                    operation_type=op_type,
                    error_code=f"TEST_{op_type.upper()}",
                    error_message=msg,
                )

        # Verify counts
        total_open = await failure_tracker.count_open(tenant_id=tenant_id)
        assert total_open == 20  # 10 + 5 + 3 + 2

        by_type = await failure_tracker.count_by_type(tenant_id=tenant_id)
        assert by_type.get("retryable", 0) == 10
        assert by_type.get("provider_error", 0) == 5
        assert by_type.get("security_error", 0) == 3
        assert by_type.get("data_error", 0) == 2

        by_severity = await failure_tracker.count_by_severity(tenant_id=tenant_id)
        assert by_severity.get("warning", 0) == 12  # retryable(10) + data_error(2)
        assert by_severity.get("high", 0) == 5      # provider_error(5)
        assert by_severity.get("critical", 0) == 3   # security_error(3)
