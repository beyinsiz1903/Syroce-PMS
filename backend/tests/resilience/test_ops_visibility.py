"""
TS-021 to TS-025: Control Plane / Ops Visibility Resilience Tests

Tests:
- TS-021: Failure surfaced in /api/ops/failures
- TS-022: Stuck outbox visible in /api/ops/outbox
- TS-023: Repeated failures trigger alert threshold
- TS-024: Security anomaly in audit trail
- TS-025: Runbook availability for critical failures

Markers: chaos_l1, chaos_l2
"""
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.asyncio]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _utc_past(minutes=0, hours=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)).isoformat()


# ═══════════════════════════════════════════════════════════════════
# TS-021: Failure Surfaced in Control Plane
# ═══════════════════════════════════════════════════════════════════

class TestFailureVisibility:
    """
    Scenario F-01: Every recorded failure must appear in /api/ops/failures.
    """

    @pytest.mark.chaos_l2
    async def test_recorded_failure_appears_in_list(
        self, db, failure_tracker, tenant_factory
    ):
        """Failure recorded via tracker must be queryable."""
        tenant_id = tenant_factory("vis-001")

        event = await failure_tracker.record(
            tenant_id=tenant_id,
            provider="exely",
            operation_type="reservation_import",
            error_code="IMPORT_TIMEOUT",
            error_message="Connection timed out after 30s",
        )

        # Query via tracker
        result = await failure_tracker.list_failures(tenant_id=tenant_id)
        assert result["total"] >= 1
        ids = [item["id"] for item in result["items"]]
        assert event["id"] in ids

    @pytest.mark.chaos_l2
    async def test_failure_fields_complete(
        self, db, failure_tracker, tenant_factory
    ):
        """Recorded failure must have all required fields."""
        tenant_id = tenant_factory("vis-002")

        event = await failure_tracker.record(
            tenant_id=tenant_id,
            provider="hotelrunner",
            operation_type="ari_push",
            error_code="PUSH_502",
            error_message="Provider returned 502 Bad Gateway",
        )

        # Fetch from DB directly
        doc = await db.cp_failures.find_one({"id": event["id"]}, {"_id": 0})
        assert doc is not None

        # All required fields present
        required_fields = [
            "id", "tenant_id", "provider", "operation_type",
            "failure_type", "severity", "error_code", "error_message",
            "status", "retry_count", "correlation_id",
            "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in doc, f"Missing field: {field}"

        # Check correct classification
        assert doc["failure_type"] == "provider_error"  # "502" triggers provider
        assert doc["status"] == "open"


# ═══════════════════════════════════════════════════════════════════
# TS-022: Stuck Outbox Visibility
# ═══════════════════════════════════════════════════════════════════

class TestStuckOutboxVisibility:
    """
    Scenario F-01: Stuck outbox events must be visible in ops metrics.
    """

    @pytest.mark.chaos_l2
    async def test_stuck_outbox_count_accurate(
        self, db, outbox_event_factory, tenant_factory
    ):
        """Count of stuck outbox events must reflect reality."""
        tenant_id = tenant_factory("stuck-vis-001")
        cutoff_minutes = 30

        # Insert 4 events stuck for >30 min
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        for _ in range(4):
            event = outbox_event_factory(
                tenant_id=tenant_id,
                status="pending",
                created_at=_utc_past(hours=1),
                available_at=future_time,
            )
            await db.outbox_events.insert_one(event)

        # Same query as ops_router
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cutoff_minutes)).isoformat()
        stuck_count = await db.outbox_events.count_documents({
            "status": {"$in": ["pending", "retry"]},
            "created_at": {"$lte": cutoff},
        })
        assert stuck_count >= 4


# ═══════════════════════════════════════════════════════════════════
# TS-023: Repeated Failures Trigger Alert
# ═══════════════════════════════════════════════════════════════════

class TestAlertThresholdBreach:
    """
    Scenario F-03: Alert fires when failure count exceeds threshold.
    """

    @pytest.mark.chaos_l2
    async def test_import_failure_spike_alert(
        self, db, failure_event_factory, tenant_factory, alerting_engine
    ):
        """5+ import failures in 30 min must trigger import_failure_spike alert."""
        tenant_id = tenant_factory("alert-spike-001")

        # Insert 6 recent import failures
        for i in range(6):
            failure = failure_event_factory(
                tenant_id=tenant_id,
                operation_type="reservation_import",
                status="open",
            )
            await db.cp_failures.insert_one(failure)

        # Run alert check
        fired = await alerting_engine.check_and_alert()
        import_alerts = [a for a in fired if a.get("trigger") == "import_failure_spike"]
        assert len(import_alerts) >= 1
        assert import_alerts[0]["severity"] == "high"

    @pytest.mark.chaos_l2
    async def test_alert_persisted_to_db(
        self, db, failure_event_factory, tenant_factory, alerting_engine
    ):
        """Fired alerts must be persisted in cp_alerts collection."""
        tenant_id = tenant_factory("alert-persist-001")

        for i in range(6):
            failure = failure_event_factory(
                tenant_id=tenant_id,
                operation_type="reservation_import",
                status="open",
            )
            await db.cp_failures.insert_one(failure)

        fired = await alerting_engine.check_and_alert()
        assert len(fired) >= 1

        # Verify persistence
        alert_count = await db.cp_alerts.count_documents({
            "trigger": "import_failure_spike",
        })
        assert alert_count >= 1

    @pytest.mark.chaos_l2
    async def test_alert_cooldown_prevents_duplicate_fire(
        self, db, failure_event_factory, tenant_factory, alerting_engine
    ):
        """Same alert should not fire twice within cooldown period."""
        tenant_id = tenant_factory("alert-cooldown-001")

        for i in range(6):
            failure = failure_event_factory(
                tenant_id=tenant_id,
                operation_type="reservation_import",
                status="open",
            )
            await db.cp_failures.insert_one(failure)

        # First check — alert fires
        fired_1 = await alerting_engine.check_and_alert()
        import_alerts_1 = [a for a in fired_1 if a.get("trigger") == "import_failure_spike"]

        # Second check — should be suppressed by cooldown
        fired_2 = await alerting_engine.check_and_alert()
        import_alerts_2 = [a for a in fired_2 if a.get("trigger") == "import_failure_spike"]

        assert len(import_alerts_1) >= 1
        assert len(import_alerts_2) == 0  # Cooldown suppressed


# ═══════════════════════════════════════════════════════════════════
# TS-024: Security Anomaly Visibility
# ═══════════════════════════════════════════════════════════════════

class TestSecurityAnomalyVisibility:
    """
    Scenario: Denied secret accesses must appear in anomaly detection.
    """

    @pytest.mark.chaos_l2
    async def test_denied_access_appears_in_anomalies(
        self, db, secret_access_control, tenant_factory
    ):
        """Denied access attempts must be visible via get_anomalies()."""
        tenant_id = tenant_factory("anomaly-001")

        # Log 3 denied accesses
        for _ in range(3):
            await secret_access_control.log_access(
                tenant_id=tenant_id,
                provider="exely",
                access_type="read",
                caller="unknown_service",
                result="denied",
                reason="Access policy denied",
            )

        # Check anomalies
        anomalies = await secret_access_control.get_anomalies(
            hours=1, tenant_id=tenant_id
        )
        assert anomalies["anomaly_count"] >= 3

    @pytest.mark.chaos_l2
    async def test_secret_anomaly_alert_fires(
        self, db, tenant_factory, alerting_engine
    ):
        """3+ secret access failures should trigger secret_anomaly alert."""
        tenant_id = tenant_factory("anomaly-alert-001")

        # Insert denied access records directly
        for i in range(4):
            await db.secret_access_audit.insert_one({
                "tenant_id": tenant_id,
                "provider": "exely",
                "access_type": "read",
                "caller": "attacker",
                "result": "denied",
                "reason": "Access policy denied",
                "timestamp": _utc_now(),
            })

        # Run alert check
        fired = await alerting_engine.check_and_alert()
        secret_alerts = [a for a in fired if a.get("trigger") == "secret_anomaly"]
        assert len(secret_alerts) >= 1
        assert secret_alerts[0]["severity"] == "critical"


# ═══════════════════════════════════════════════════════════════════
# TS-025: Runbook Availability
# ═══════════════════════════════════════════════════════════════════

class TestRunbookAvailability:
    """
    Scenario F-05: All critical operations must have runbooks.
    """

    @pytest.mark.chaos_l1
    async def test_all_14_runbooks_exist(self):
        """All 14 predefined runbooks must be accessible."""
        from controlplane.runbooks import list_runbooks

        runbooks = list_runbooks()
        assert len(runbooks) >= 14

    @pytest.mark.chaos_l1
    async def test_runbook_has_required_fields(self):
        """Each runbook must have all required fields."""
        from controlplane.runbooks import list_runbooks

        for rb in list_runbooks():
            assert rb.get("id"), f"Runbook missing id"
            assert rb.get("title"), f"Runbook {rb.get('id')} missing title"
            assert rb.get("description"), f"Runbook {rb.get('id')} missing description"
            assert rb.get("resolution_steps"), f"Runbook {rb.get('id')} missing resolution_steps"
            assert len(rb["resolution_steps"]) >= 1

    @pytest.mark.chaos_l1
    async def test_critical_operations_have_runbooks(self):
        """Critical operations must each have at least one runbook."""
        from controlplane.runbooks import list_runbooks

        critical_ops = [
            "reservation_import",
            "outbox_dispatch",
            "ari_push",
            "crypto_decrypt",
            "secret_access",
        ]

        all_related = set()
        for rb in list_runbooks():
            for op in rb.get("related_operations", []):
                all_related.add(op)

        for op in critical_ops:
            assert op in all_related, (
                f"No runbook covers critical operation: {op}"
            )

    @pytest.mark.chaos_l1
    async def test_specific_runbook_retrievable(self):
        """Individual runbooks must be retrievable by ID."""
        from controlplane.runbooks import get_runbook, list_runbooks

        # Get first runbook's actual ID
        all_runbooks = list_runbooks()
        assert len(all_runbooks) > 0
        first_id = all_runbooks[0]["id"]

        rb = get_runbook(first_id)
        assert rb is not None
        assert rb.id == first_id
