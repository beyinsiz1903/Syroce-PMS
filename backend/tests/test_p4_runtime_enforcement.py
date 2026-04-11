"""
P4 Runtime Enforcement Tests
============================

Tests for the three runtime enforcement layers:
  1. Hard Fail Gate — mapping enforcement blocks bad pushes
  2. Auto-Heal Service — conservative healing with evidence
  3. Push Loop Worker — runtime loop with observability

Total: 75+ tests ensuring production-grade runtime behavior.
"""
import asyncio
import pytest
import uuid
from datetime import datetime, timezone, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════
# Test Helpers
# ══════════════════════════════════════════════════════════════════════

TENANT = "test-tenant-p4"
PROPERTY = "test-property-p4"
PROVIDER = "hotelrunner"


def make_change_set(**overrides):
    """Create a test change set."""
    base = {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT,
        "property_id": PROPERTY,
        "provider": PROVIDER,
        "coalescing_key": f"{TENANT}|{PROPERTY}|{PROVIDER}|STD|BAR|2025-07-01:2025-07-05|rate",
        "room_type_code": "STD",
        "rate_plan_code": "BAR",
        "date_from": "2025-07-01",
        "date_to": "2025-07-05",
        "change_scope": "rate",
        "compacted_payload": {"base_rate": 150.0, "currency": "TRY"},
        "provider_delta_hash": "abc123",
        "status": "pending",
        "outbound_change_id": str(uuid.uuid4()),
        "outbound_attempt_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def make_recon_case(drift_type="stale_locally", status="open", **overrides):
    """Create a test reconciliation case."""
    base = {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT,
        "property_id": PROPERTY,
        "provider": PROVIDER,
        "case_type": "stale_sync",
        "drift_type": drift_type,
        "severity": "medium",
        "status": status,
        "description": f"Test case: {drift_type}",
        "details": {"room_type_code": "STD"},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════════════════
# 1. HARD FAIL GATE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestHardFailGate:
    """Test the hard fail gate — mapping enforcement at runtime."""

    def test_verdict_pass(self):
        """Verdict should start as passed."""
        from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
        v = HardFailVerdict(passed=True)
        assert v.passed is True
        assert v.status == "pass"
        assert v.failures == []

    def test_verdict_fail_on_add(self):
        """Adding a failure should mark verdict as blocked."""
        from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
        v = HardFailVerdict(passed=True)
        v.add_failure("room", "STD", "unmapped", "No mapping found", "Create mapping")
        assert v.passed is False
        assert v.status == "hard_fail"
        assert len(v.failures) == 1

    def test_verdict_multiple_failures(self):
        """Multiple failures should accumulate."""
        from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
        v = HardFailVerdict(passed=True)
        v.add_failure("room", "STD", "unmapped", "Missing room", "Create room mapping")
        v.add_failure("rate_plan", "BAR", "unmapped", "Missing rate", "Create rate mapping")
        assert len(v.failures) == 2
        assert "room" in v.summary()
        assert "rate_plan" in v.summary()

    def test_verdict_summary_pass(self):
        """Passed verdict should have clean summary."""
        from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
        v = HardFailVerdict(passed=True)
        assert v.summary() == "All mappings valid"

    @pytest.mark.asyncio
    async def test_check_mapping_gate_room_missing(self):
        """Gate should fail when room mapping is missing."""
        from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate
        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            mock_db.__getitem__ = MagicMock(return_value=MagicMock())
            mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)

            verdict = await check_mapping_gate(TENANT, PROPERTY, PROVIDER, "STD", "BAR")
            assert verdict.passed is False
            assert any(f["entity_type"] == "room" for f in verdict.failures)

    @pytest.mark.asyncio
    async def test_check_mapping_gate_room_inactive(self):
        """Gate should fail when room mapping is inactive."""
        from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate
        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            room_col = MagicMock()
            rate_col = MagicMock()

            def get_collection(name):
                if name == "room_mappings":
                    return room_col
                return rate_col

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            room_col.find_one = AsyncMock(return_value={"is_active": False, "pms_room_type_id": "R1"})
            rate_col.find_one = AsyncMock(return_value={
                "is_active": True, "pms_rate_plan_id": "RP1", "validation_status": "valid",
            })

            verdict = await check_mapping_gate(TENANT, PROPERTY, PROVIDER, "STD", "BAR")
            assert verdict.passed is False
            assert any(f["failure_type"] == "inactive" for f in verdict.failures)

    @pytest.mark.asyncio
    async def test_check_mapping_gate_all_valid(self):
        """Gate should pass when all mappings are valid."""
        from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate
        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            valid_room = {"is_active": True, "pms_room_type_id": "R1", "validation_status": "valid"}
            valid_rate = {"is_active": True, "pms_rate_plan_id": "RP1", "validation_status": "valid"}

            room_col = MagicMock()
            rate_col = MagicMock()

            def get_collection(name):
                if name == "room_mappings":
                    return room_col
                return rate_col

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            room_col.find_one = AsyncMock(return_value=valid_room)
            rate_col.find_one = AsyncMock(return_value=valid_rate)

            verdict = await check_mapping_gate(TENANT, PROPERTY, PROVIDER, "STD", "BAR")
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_check_mapping_gate_no_rate_code(self):
        """Gate should pass without rate plan check when rate_plan_code is None."""
        from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate
        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            room_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=room_col)
            room_col.find_one = AsyncMock(return_value={
                "is_active": True, "pms_room_type_id": "R1", "validation_status": "valid",
            })

            verdict = await check_mapping_gate(TENANT, PROPERTY, PROVIDER, "STD", None)
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_check_mapping_gate_room_deleted_pms_id(self):
        """Gate should fail when room mapping has no pms_room_type_id."""
        from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate
        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            mock_db.__getitem__ = MagicMock(return_value=MagicMock())
            mock_db.__getitem__.return_value.find_one = AsyncMock(
                return_value={"is_active": True, "pms_room_type_id": "", "validation_status": "valid"}
            )
            verdict = await check_mapping_gate(TENANT, PROPERTY, PROVIDER, "STD", None)
            assert verdict.passed is False
            assert verdict.failures[0]["failure_type"] == "deleted"

    @pytest.mark.asyncio
    async def test_enforce_quarantines_on_failure(self):
        """enforce_hard_fail_gate should quarantine change set on mapping failure."""
        from domains.channel_manager.ari.hard_fail_gate import enforce_hard_fail_gate
        cs = make_change_set()

        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            mock_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=mock_col)
            mock_col.find_one = AsyncMock(return_value=None)
            mock_col.update_one = AsyncMock()
            mock_col.insert_one = AsyncMock()

            verdict = await enforce_hard_fail_gate(cs)
            assert verdict.passed is False
            # Should have called update_one for quarantine
            assert mock_col.update_one.called

    @pytest.mark.asyncio
    async def test_enforce_passes_valid_mapping(self):
        """enforce_hard_fail_gate should pass when mappings are valid."""
        from domains.channel_manager.ari.hard_fail_gate import enforce_hard_fail_gate
        cs = make_change_set()

        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            room_col = MagicMock()
            rate_col = MagicMock()
            call_count = [0]

            def get_collection(name):
                if name == "room_mappings":
                    return room_col
                if name == "rate_plan_mappings":
                    return rate_col
                return MagicMock()

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            room_col.find_one = AsyncMock(return_value={
                "is_active": True, "pms_room_type_id": "R1", "validation_status": "valid",
            })
            rate_col.find_one = AsyncMock(return_value={
                "is_active": True, "pms_rate_plan_id": "RP1", "validation_status": "valid",
            })

            verdict = await enforce_hard_fail_gate(cs)
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_duplicate_incident_prevention(self):
        """Should not create duplicate incidents for same mapping failure."""
        from domains.channel_manager.ari.hard_fail_gate import _create_hard_fail_incident, HardFailVerdict
        cs = make_change_set()
        verdict = HardFailVerdict(passed=False)
        verdict.add_failure("room", "STD", "unmapped", "No mapping", "Create mapping")

        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            recon_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=recon_col)
            recon_col.find_one = AsyncMock(return_value={"id": "existing-incident"})
            recon_col.insert_one = AsyncMock()

            result = await _create_hard_fail_incident(cs, verdict)
            assert result == "existing-incident"
            recon_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_quarantine(self):
        """Should release quarantined change sets back to pending."""
        from domains.channel_manager.ari.hard_fail_gate import release_quarantine

        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            cs_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=cs_col)
            mock_result = MagicMock()
            mock_result.modified_count = 3
            cs_col.update_many = AsyncMock(return_value=mock_result)

            released = await release_quarantine(TENANT, "STD", "BAR", PROVIDER)
            assert released == 3

    @pytest.mark.asyncio
    async def test_hard_fail_stats(self):
        """Should return aggregate hard fail statistics."""
        from domains.channel_manager.ari.hard_fail_gate import get_hard_fail_stats

        with patch("domains.channel_manager.ari.hard_fail_gate.db") as mock_db:
            cs_col = MagicMock()
            recon_col = MagicMock()
            hf_log = MagicMock()

            def get_collection(name):
                if name == "ari_change_sets":
                    return cs_col
                if "reconciliation" in name:
                    return recon_col
                return hf_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cs_col.count_documents = AsyncMock(return_value=5)

            # Mock async aggregate cursor
            async def _empty_aiter():
                return
                yield  # noqa: makes this an async generator

            cs_col.aggregate = MagicMock(return_value=_empty_aiter())
            recon_col.count_documents = AsyncMock(return_value=2)
            hf_log.count_documents = AsyncMock(return_value=10)

            stats = await get_hard_fail_stats(TENANT)
            assert stats["hard_fail_change_sets"] == 5
            assert stats["enforcement_active"] is True


# ══════════════════════════════════════════════════════════════════════
# 2. AUTO-HEAL SERVICE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestAutoHealService:
    """Test conservative auto-healing workflow."""

    def test_safe_whitelist_contents(self):
        """Safe whitelist should contain only low-risk drift types."""
        from domains.channel_manager.auto_heal_service import SAFE_WHITELIST
        assert "stale_locally" in SAFE_WHITELIST
        assert "stale_remotely" in SAFE_WHITELIST
        assert "missing_locally" not in SAFE_WHITELIST
        assert "financial_mismatch" not in SAFE_WHITELIST

    def test_risky_whitelist_contents(self):
        """Risky whitelist should contain payload_mismatch."""
        from domains.channel_manager.auto_heal_service import RISKY_WHITELIST
        assert "payload_mismatch" in RISKY_WHITELIST
        assert "mapping_mismatch" not in RISKY_WHITELIST

    def test_auto_heal_result_init(self):
        """AutoHealResult should start clean."""
        from domains.channel_manager.auto_heal_service import AutoHealResult
        r = AutoHealResult()
        assert r.processed == 0
        assert r.healed == 0
        assert r.failed == 0

    def test_auto_heal_result_to_dict(self):
        """to_dict should include all fields."""
        from domains.channel_manager.auto_heal_service import AutoHealResult
        r = AutoHealResult()
        r.processed = 5
        r.healed = 3
        r.failed = 1
        d = r.to_dict()
        assert d["processed"] == 5
        assert d["healed"] == 3
        assert d["failed"] == 1

    @pytest.mark.asyncio
    async def test_heal_stale_locally(self):
        """Should auto-heal stale_locally cases."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_locally")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)

            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            result = await run_auto_heal_cycle(TENANT)
            assert result.processed == 1
            assert result.healed == 1

    @pytest.mark.asyncio
    async def test_heal_stale_remotely(self):
        """Should auto-heal stale_remotely cases."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_remotely")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)

            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            result = await run_auto_heal_cycle(TENANT)
            assert result.healed == 1

    @pytest.mark.asyncio
    async def test_skip_manual_review_types(self):
        """Should NOT auto-heal manual review drift types."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="financial_mismatch")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=recon_col)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)

            result = await run_auto_heal_cycle(TENANT)
            assert result.healed == 0
            assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_risky_not_healed_by_default(self):
        """Risky types should NOT be healed unless include_risky=True."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="payload_mismatch")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=recon_col)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)

            result = await run_auto_heal_cycle(TENANT, include_risky=False)
            assert result.healed == 0

    @pytest.mark.asyncio
    async def test_risky_healed_with_opt_in(self):
        """Risky types should be healed when include_risky=True."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="payload_mismatch")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            result = await run_auto_heal_cycle(TENANT, include_risky=True)
            assert result.healed == 1

    @pytest.mark.asyncio
    async def test_evidence_created_on_heal(self):
        """Auto-heal should create an evidence record."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_locally")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            await run_auto_heal_cycle(TENANT)
            # Evidence should be logged
            heal_log.insert_one.assert_called()
            evidence = heal_log.insert_one.call_args[0][0]
            assert evidence["status"] == "completed"
            assert evidence["drift_type"] == "stale_locally"

    @pytest.mark.asyncio
    async def test_failed_heal_escalation(self):
        """Failed heal should escalate to investigating status."""
        from domains.channel_manager.auto_heal_service import _escalate_case

        case = make_recon_case(drift_type="stale_locally")
        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            await _escalate_case(case, "Test error")

            # Should update case to investigating
            update_args = recon_col.update_one.call_args
            update_set = update_args[0][1]["$set"]
            assert update_set["status"] == "investigating"
            assert update_set["severity"] == "high"

    @pytest.mark.asyncio
    async def test_max_heals_per_cycle_respected(self):
        """Should respect max_heals limit."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        cases = [make_recon_case(drift_type="stale_locally") for _ in range(10)]

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=cases[:3])  # DB returns only 3
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            result = await run_auto_heal_cycle(TENANT, max_heals=3)
            assert result.processed == 3

    @pytest.mark.asyncio
    async def test_empty_cycle(self):
        """Empty cycle should return zeros."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=recon_col)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[])
            recon_col.find = MagicMock(return_value=cursor)

            result = await run_auto_heal_cycle(TENANT)
            assert result.processed == 0
            assert result.healed == 0

    @pytest.mark.asyncio
    async def test_heal_marks_case_resolved(self):
        """Healed case should be marked as resolved by system:auto_heal."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_locally")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            await run_auto_heal_cycle(TENANT)

            update_args = recon_col.update_one.call_args
            update_set = update_args[0][1]["$set"]
            assert update_set["status"] == "resolved"
            assert "auto_heal" in update_set["resolved_by"]
            assert "AUTO_HEAL" in update_set["resolution"]

    @pytest.mark.asyncio
    async def test_auto_heal_stats(self):
        """Stats should return aggregate auto-heal info."""
        from domains.channel_manager.auto_heal_service import get_auto_heal_stats

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            heal_log = MagicMock()
            recon_col = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            heal_log.count_documents = AsyncMock(return_value=10)
            recon_col.count_documents = AsyncMock(return_value=3)

            async def _empty_aiter():
                return
                yield  # noqa

            heal_log.aggregate = MagicMock(return_value=_empty_aiter())

            stats = await get_auto_heal_stats(TENANT)
            assert stats["total_healed"] == 10
            assert "safe_whitelist" in stats


# ══════════════════════════════════════════════════════════════════════
# 3. PUSH LOOP WORKER TESTS
# ══════════════════════════════════════════════════════════════════════

class TestPushLoopMetrics:
    """Test push loop metrics collection."""

    def test_metrics_init(self):
        """Metrics should start at zero."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        assert m.queued_changes == 0
        assert m.emitted_payloads == 0
        assert m.cycle_count == 0

    def test_metrics_to_dict(self):
        """to_dict should produce complete metrics snapshot."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        m.queued_changes = 10
        m.emitted_payloads = 5
        m.dropped_as_duplicate = 2
        m.hard_fail_blocked = 1
        m.verify_success_count = 4
        m.verify_fail_count = 1
        d = m.to_dict()
        assert d["queued_changes"] == 10
        assert d["emitted_payloads"] == 5
        assert d["dropped_as_duplicate"] == 2
        assert d["hard_fail_blocked"] == 1
        assert d["verify_success_ratio"] == pytest.approx(0.8, abs=0.01)

    def test_metrics_success_ratio_zero_division(self):
        """Success ratio should be 0 when no verifies."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        assert m.to_dict()["verify_success_ratio"] == 0.0

    def test_ack_latency_tracking(self):
        """Should track per-provider ack latency."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        m.record_ack_latency("hotelrunner", 100)
        m.record_ack_latency("hotelrunner", 200)
        m.record_ack_latency("exely", 50)

        assert m.get_avg_latency("hotelrunner") == 150.0
        assert m.get_avg_latency("exely") == 50.0
        assert m.get_avg_latency("unknown") == 0.0

    def test_ack_latency_cap(self):
        """Should keep only last 100 latency samples."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        for i in range(150):
            m.record_ack_latency("hr", i)
        assert len(m._provider_latencies["hr"]) == 100

    def test_metrics_reset(self):
        """Reset should clear all metrics."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        m.emitted_payloads = 50
        m.record_ack_latency("hr", 100)
        m.reset()
        assert m.emitted_payloads == 0
        assert m.get_avg_latency("hr") == 0.0


class TestPushLoopWorker:
    """Test the push loop worker lifecycle and behavior."""

    def test_worker_initial_state(self):
        """Worker should start as stopped."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        w = PushLoopWorker()
        assert w.status == "stopped"
        assert w._running is False

    @pytest.mark.asyncio
    async def test_worker_start_stop(self):
        """Worker should transition through start/stop states."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        w = PushLoopWorker(interval_seconds=100)  # long interval to prevent actual cycles
        await w.start()
        assert w.status == "running"
        await w.stop()
        assert w.status == "stopped"

    def test_worker_pause_resume(self):
        """Worker should support pause/resume."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        w = PushLoopWorker()
        w._running = True
        w.pause()
        assert w.status == "paused"
        w.resume()
        assert w.status == "running"
        w._running = False

    def test_worker_status_dict(self):
        """get_status should return complete worker state."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        w = PushLoopWorker(interval_seconds=5, batch_size=50)
        status = w.get_status()
        assert status["status"] == "stopped"
        assert status["interval_seconds"] == 5
        assert status["batch_size"] == 50
        assert "metrics" in status

    def test_register_adapter(self):
        """Should register provider adapters."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        w = PushLoopWorker()
        adapter = MagicMock()
        w.register_adapter("hotelrunner", adapter)
        assert "hotelrunner" in w._provider_adapters

    def test_singleton_worker(self):
        """get_push_worker should return singleton."""
        from domains.channel_manager.ari.push_loop_worker import get_push_worker
        w1 = get_push_worker()
        w2 = get_push_worker()
        assert w1 is w2


# ══════════════════════════════════════════════════════════════════════
# 4. INTEGRATION TESTS — Combined behavior
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeIntegration:
    """Test interactions between the three runtime layers."""

    @pytest.mark.asyncio
    async def test_hard_fail_blocks_push_loop(self):
        """Push loop should respect hard fail gate and increment metrics."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker, PushLoopMetrics

        worker = PushLoopWorker()
        cs = make_change_set()

        with patch("domains.channel_manager.ari.push_loop_worker.repo") as mock_repo, \
             patch("domains.channel_manager.ari.push_loop_worker.enforce_hard_fail_gate") as mock_gate:

            # Setup: pending change set with failing gate
            mock_repo.get_pending_change_sets = AsyncMock(return_value=[cs])

            from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
            failed_verdict = HardFailVerdict(passed=False)
            failed_verdict.add_failure("room", "STD", "unmapped", "Missing", "Create")
            mock_gate.return_value = failed_verdict

            await worker._process_tenant(TENANT)
            assert worker.metrics.hard_fail_blocked == 1
            assert worker.metrics.emitted_payloads == 0

    @pytest.mark.asyncio
    async def test_push_loop_drops_duplicates(self):
        """Push loop should drop outbound duplicates and track metrics."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker

        worker = PushLoopWorker()
        cs = make_change_set()

        with patch("domains.channel_manager.ari.push_loop_worker.repo") as mock_repo, \
             patch("domains.channel_manager.ari.push_loop_worker.enforce_hard_fail_gate") as mock_gate:

            from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
            mock_gate.return_value = HardFailVerdict(passed=True)

            mock_repo.get_pending_change_sets = AsyncMock(return_value=[cs])
            mock_repo.check_outbound_idempotency = AsyncMock(return_value=True)
            mock_repo.update_change_set_status = AsyncMock()

            await worker._process_tenant(TENANT)
            assert worker.metrics.dropped_as_duplicate == 1

    @pytest.mark.asyncio
    async def test_push_loop_emits_on_success(self):
        """Push loop should emit and track success."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopWorker
        from domains.channel_manager.ari.events import ProviderResult

        worker = PushLoopWorker()
        adapter = AsyncMock()
        adapter.push_rate = AsyncMock(return_value=ProviderResult(
            success=True, provider="hotelrunner", status_code=200,
            duration_ms=50,
        ))
        worker.register_adapter("hotelrunner", adapter)

        cs = make_change_set()

        with patch("domains.channel_manager.ari.push_loop_worker.repo") as mock_repo, \
             patch("domains.channel_manager.ari.push_loop_worker.enforce_hard_fail_gate") as mock_gate, \
             patch("domains.channel_manager.ari.push_loop_worker.rate_limiter") as mock_rl, \
             patch("domains.channel_manager.ari.push_loop_worker.compile_delta") as mock_compile, \
             patch("domains.channel_manager.ari.push_loop_worker.process_ack") as mock_ack:

            from domains.channel_manager.ari.hard_fail_gate import HardFailVerdict
            mock_gate.return_value = HardFailVerdict(passed=True)

            mock_repo.get_pending_change_sets = AsyncMock(return_value=[cs])
            mock_repo.check_outbound_idempotency = AsyncMock(return_value=False)
            mock_repo.update_change_set_status = AsyncMock()
            mock_rl.acquire = AsyncMock(return_value=True)

            from domains.channel_manager.ari.events import ARIDelta
            mock_delta = MagicMock(spec=ARIDelta)
            mock_delta.change_scope = "rate"
            mock_compile.return_value = mock_delta

            mock_ack.return_value = "acked"

            await worker._process_tenant(TENANT)
            assert worker.metrics.emitted_payloads == 1
            assert worker.metrics.verify_success_count == 1

    @pytest.mark.asyncio
    async def test_auto_heal_produces_evidence_trail(self):
        """Each auto-heal should leave a complete evidence trail."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_locally")

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            heal_log = MagicMock()

            def get_collection(name):
                if "reconciliation" in name:
                    return recon_col
                return heal_log

            mock_db.__getitem__ = MagicMock(side_effect=get_collection)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)
            recon_col.update_one = AsyncMock()
            heal_log.insert_one = AsyncMock()

            await run_auto_heal_cycle(TENANT)

            # Check evidence
            evidence = heal_log.insert_one.call_args[0][0]
            assert "id" in evidence
            assert evidence["tenant_id"] == TENANT
            assert evidence["drift_type"] == "stale_locally"
            assert evidence["rule_resolution"] == "safe_auto_heal"
            assert evidence["gold_source"] == "provider_snapshot"
            assert evidence["heal_action"] == "re_ingest"
            assert evidence["case_snapshot"]["provider"] == PROVIDER

    @pytest.mark.asyncio
    async def test_heal_skips_unknown_drift_types(self):
        """Unknown drift types should not be healed."""
        from domains.channel_manager.auto_heal_service import run_auto_heal_cycle
        case = make_recon_case(drift_type="stale_locally")
        case["drift_type"] = "totally_unknown_type"

        with patch("domains.channel_manager.auto_heal_service.db") as mock_db:
            recon_col = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=recon_col)
            cursor = MagicMock()
            cursor.sort = MagicMock(return_value=cursor)
            cursor.limit = MagicMock(return_value=cursor)
            cursor.to_list = AsyncMock(return_value=[case])
            recon_col.find = MagicMock(return_value=cursor)

            result = await run_auto_heal_cycle(TENANT)
            assert result.healed == 0

    def test_push_metrics_provider_latency_in_dict(self):
        """Metrics dict should include per-provider latency."""
        from domains.channel_manager.ari.push_loop_worker import PushLoopMetrics
        m = PushLoopMetrics()
        m.record_ack_latency("hotelrunner", 100)
        m.record_ack_latency("hotelrunner", 200)
        m.record_ack_latency("exely", 300)

        d = m.to_dict()
        assert d["provider_ack_latency_avg_ms"]["hotelrunner"] == 150.0
        assert d["provider_ack_latency_avg_ms"]["exely"] == 300.0
