"""
Test Suite P6 — Readiness Scorer, Safe Actions, Rollout Framework
===================================================================

Tests for:
  1. Readiness Scorer (scored "Why NOT READY?" with priorities)
  2. Safe Actions (1-click idempotent operator actions)
  3. Rollout Framework (phase gate state machine)
  4. API endpoints for all three
"""
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

BASE_URL = os.environ.get('VITE_BACKEND_URL', '')


# ══════════════════════════════════════════════════════════════
# 1. READINESS SCORER TESTS
# ══════════════════════════════════════════════════════════════

class TestReadinessScorer:
    """Test the readiness scoring logic."""

    @pytest.mark.asyncio
    async def test_compute_readiness_returns_structure(self):
        """Test that readiness score returns all expected fields."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value.to_list = AsyncMock(return_value=[])
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 0,
            "open_hard_fail_incidents": 0,
            "hard_fails_last_24h": 0,
            "by_failure_type": {},
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 0,
            "by_classification": {},
            "by_age_bucket": {},
            "by_provider": {},
        })

        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 1.0,
            "verify_success_count": 10,
            "verify_fail_count": 0,
            "queued_changes": 0,
            "emitted_payloads": 5,
            "hard_fail_blocked": 0,
        }

        with patch("domains.channel_manager.readiness_scorer.db", mock_db), \
             patch("domains.channel_manager.readiness_scorer.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.readiness_scorer.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.readiness_scorer.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.readiness_scorer import compute_readiness_score
            result = await compute_readiness_score("test-tenant")

        assert "score" in result
        assert "is_ready" in result
        assert "scores" in result
        assert "issues" in result
        assert "fix_order" in result
        assert "evaluated_at" in result
        assert isinstance(result["score"], int)

    @pytest.mark.asyncio
    async def test_perfect_score_when_no_issues(self):
        """Score should be 100 when all systems are green."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value.to_list = AsyncMock(return_value=[])
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 0, "open_hard_fail_incidents": 0,
            "hard_fails_last_24h": 0, "by_failure_type": {},
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 0, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 1.0, "verify_success_count": 10,
            "verify_fail_count": 0, "queued_changes": 0,
            "emitted_payloads": 5, "hard_fail_blocked": 0,
        }

        with patch("domains.channel_manager.readiness_scorer.db", mock_db), \
             patch("domains.channel_manager.readiness_scorer.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.readiness_scorer.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.readiness_scorer.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.readiness_scorer import compute_readiness_score
            result = await compute_readiness_score("test-tenant")

        assert result["score"] == 100
        assert result["is_ready"] is True
        assert len(result["issues"]) == 0

    @pytest.mark.asyncio
    async def test_hard_fail_reduces_score_to_critical(self):
        """Hard fail blocks should reduce score and generate critical issue."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value.to_list = AsyncMock(return_value=[])
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 5, "open_hard_fail_incidents": 2,
            "hard_fails_last_24h": 3, "by_failure_type": {},
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 0, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 1.0, "verify_success_count": 10,
            "verify_fail_count": 0, "queued_changes": 0,
            "emitted_payloads": 5, "hard_fail_blocked": 0,
        }

        with patch("domains.channel_manager.readiness_scorer.db", mock_db), \
             patch("domains.channel_manager.readiness_scorer.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.readiness_scorer.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.readiness_scorer.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.readiness_scorer import compute_readiness_score
            result = await compute_readiness_score("test-tenant")

        assert result["score"] < 100
        assert result["is_ready"] is False
        critical_issues = [i for i in result["issues"] if i["severity"] == "critical"]
        assert len(critical_issues) >= 1

    @pytest.mark.asyncio
    async def test_issues_sorted_by_severity(self):
        """Issues should be sorted: blocker > critical > warning > info."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        broken_rooms = [
            {"tenant_id": "t", "provider": "exely", "provider_room_code": "R1"},
        ]
        mock_collection.find.return_value.to_list = AsyncMock(return_value=broken_rooms)
        mock_collection.count_documents = AsyncMock(return_value=3)
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 2, "open_hard_fail_incidents": 1,
            "hard_fails_last_24h": 1, "by_failure_type": {},
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 1, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 0.85, "verify_success_count": 17,
            "verify_fail_count": 3, "queued_changes": 0,
            "emitted_payloads": 5, "hard_fail_blocked": 0,
        }

        with patch("domains.channel_manager.readiness_scorer.db", mock_db), \
             patch("domains.channel_manager.readiness_scorer.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.readiness_scorer.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.readiness_scorer.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.readiness_scorer import compute_readiness_score
            result = await compute_readiness_score("test-tenant")

        if len(result["issues"]) > 1:
            severity_order = {"blocker": 0, "critical": 1, "warning": 2, "info": 3}
            for i in range(len(result["issues"]) - 1):
                curr = severity_order.get(result["issues"][i]["severity"], 99)
                nxt = severity_order.get(result["issues"][i + 1]["severity"], 99)
                assert curr <= nxt, "Issues not sorted by severity"


# ══════════════════════════════════════════════════════════════
# 2. SAFE ACTIONS TESTS
# ══════════════════════════════════════════════════════════════

class TestSafeActions:
    """Test idempotent safe action service."""

    @pytest.mark.asyncio
    async def test_retry_safe_no_retryable(self):
        """Should return no_action when nothing to retry."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value.to_list = AsyncMock(return_value=[])
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.safe_actions_service.db", mock_db):
            from domains.channel_manager.safe_actions_service import retry_safe
            result = await retry_safe("test-tenant")

        assert result["status"] == "no_action"
        assert result["affected_count"] == 0

    @pytest.mark.asyncio
    async def test_retry_safe_processes_retryable(self):
        """Should retry failed change sets."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value.to_list = AsyncMock(return_value=[
            {"id": "cs-1", "status": "failed"},
            {"id": "cs-2", "status": "timeout"},
        ])
        mock_update_result = MagicMock()
        mock_update_result.modified_count = 2
        mock_collection.update_many = AsyncMock(return_value=mock_update_result)
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.safe_actions_service.db", mock_db):
            from domains.channel_manager.safe_actions_service import retry_safe
            result = await retry_safe("test-tenant", "admin@test.com")

        assert result["status"] == "completed"
        assert result["affected_count"] == 2
        assert result["post_verify"]["retried"] == 2
        assert result["post_verify"]["still_failed"] == 0

    @pytest.mark.asyncio
    async def test_suppress_noise_returns_completed(self):
        """Should suppress notifications and return completed."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.safe_actions_service.db", mock_db):
            from domains.channel_manager.safe_actions_service import suppress_noise
            result = await suppress_noise("test-tenant", duration_minutes=30)

        assert result["status"] == "completed"
        assert "30 dakika" in result["message"]

    @pytest.mark.asyncio
    async def test_suppress_noise_max_120_minutes(self):
        """Duration should be capped at 120 minutes."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.safe_actions_service.db", mock_db):
            from domains.channel_manager.safe_actions_service import suppress_noise
            result = await suppress_noise("test-tenant", duration_minutes=300)

        assert "120 dakika" in result["message"]


# ══════════════════════════════════════════════════════════════
# 3. ROLLOUT FRAMEWORK TESTS
# ══════════════════════════════════════════════════════════════

class TestRolloutFramework:
    """Test narrow rollout state machine."""

    @pytest.mark.asyncio
    async def test_default_state_not_active(self):
        """Default state should be INTERNAL and not active."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.rollout_framework.db", mock_db):
            from domains.channel_manager.rollout_framework import get_rollout_state
            state = await get_rollout_state("test-tenant")

        assert state["current_phase"] == "INTERNAL"
        assert state["is_active"] is False

    @pytest.mark.asyncio
    async def test_initialize_rollout(self):
        """Initialize should set phase to INTERNAL and active."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock()
        mock_collection.insert_one = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("domains.channel_manager.rollout_framework.db", mock_db):
            from domains.channel_manager.rollout_framework import initialize_rollout
            state = await initialize_rollout("test-tenant")

        assert state["current_phase"] == "INTERNAL"
        assert state["is_active"] is True
        assert state["phase_started_at"] is not None

    @pytest.mark.asyncio
    async def test_phase_order(self):
        """Phase order should be correct."""
        from domains.channel_manager.rollout_framework import RolloutPhase
        assert RolloutPhase.ORDERED == ["INTERNAL", "DUAL_PROVIDER", "REAL_PILOT", "7DAY_PROOF", "PRODUCTION"]

    @pytest.mark.asyncio
    async def test_gate_evaluation_returns_checks(self):
        """Gate evaluation should return structured checks."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={
            "tenant_id": "t", "current_phase": "INTERNAL",
            "phase_started_at": datetime.now(timezone.utc).isoformat(),
            "rollout_started_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True, "phase_history": [],
        })
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 0, "open_hard_fail_incidents": 0,
            "hard_fails_last_24h": 0, "by_failure_type": {},
        })
        mock_ah = AsyncMock(return_value={
            "total_healed": 10, "total_failed": 0,
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 0, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 0.98, "verify_success_count": 50,
            "verify_fail_count": 1, "queued_changes": 0,
            "emitted_payloads": 20, "hard_fail_blocked": 0,
        }
        mock_worker.status = "running"

        with patch("domains.channel_manager.rollout_framework.db", mock_db), \
             patch("domains.channel_manager.ari.hard_fail_gate.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.auto_heal_service.get_auto_heal_stats", mock_ah), \
             patch("domains.channel_manager.quarantine_service.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.ari.push_loop_worker.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.rollout_framework import evaluate_phase_gate
            result = await evaluate_phase_gate("test-tenant")

        assert "current_phase" in result
        assert "next_phase" in result
        assert "gate_passed" in result
        assert "checks" in result
        assert isinstance(result["checks"], list)

    @pytest.mark.asyncio
    async def test_transition_blocked_when_gates_fail(self):
        """Transition should be blocked when gate checks fail."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={
            "tenant_id": "t", "current_phase": "INTERNAL",
            "phase_started_at": "2026-01-01T00:00:00+00:00",
            "rollout_started_at": "2026-01-01T00:00:00+00:00",
            "is_active": True, "phase_history": [],
        })
        mock_collection.count_documents = AsyncMock(return_value=5)  # has incidents
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 3, "open_hard_fail_incidents": 2,
            "hard_fails_last_24h": 1, "by_failure_type": {},
        })
        mock_ah = AsyncMock(return_value={
            "total_healed": 5, "total_failed": 3,
        })
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 2, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 0.70, "verify_success_count": 7,
            "verify_fail_count": 3, "queued_changes": 5,
            "emitted_payloads": 5, "hard_fail_blocked": 3,
        }
        mock_worker.status = "running"

        with patch("domains.channel_manager.rollout_framework.db", mock_db), \
             patch("domains.channel_manager.ari.hard_fail_gate.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.auto_heal_service.get_auto_heal_stats", mock_ah), \
             patch("domains.channel_manager.quarantine_service.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.ari.push_loop_worker.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.rollout_framework import attempt_phase_transition
            result = await attempt_phase_transition("test-tenant")

        assert result["transitioned"] is False
        assert len(result.get("failed_checks", [])) > 0

    @pytest.mark.asyncio
    async def test_rollout_dashboard_returns_structure(self):
        """Dashboard should return all expected fields."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_hf = AsyncMock(return_value={
            "hard_fail_change_sets": 0, "open_hard_fail_incidents": 0,
            "hard_fails_last_24h": 0, "by_failure_type": {},
        })
        mock_ah = AsyncMock(return_value={"total_healed": 0, "total_failed": 0})
        mock_quarantine = AsyncMock(return_value={
            "total_quarantined": 0, "by_classification": {},
            "by_age_bucket": {}, "by_provider": {},
        })
        mock_worker = MagicMock()
        mock_worker.metrics.to_dict.return_value = {
            "verify_success_ratio": 1.0, "verify_success_count": 0,
            "verify_fail_count": 0, "queued_changes": 0,
            "emitted_payloads": 0, "hard_fail_blocked": 0,
        }
        mock_worker.status = "stopped"

        with patch("domains.channel_manager.rollout_framework.db", mock_db), \
             patch("domains.channel_manager.ari.hard_fail_gate.get_hard_fail_stats", mock_hf), \
             patch("domains.channel_manager.auto_heal_service.get_auto_heal_stats", mock_ah), \
             patch("domains.channel_manager.quarantine_service.get_quarantine_overview", mock_quarantine), \
             patch("domains.channel_manager.ari.push_loop_worker.get_push_worker", return_value=mock_worker):
            from domains.channel_manager.rollout_framework import get_rollout_dashboard
            result = await get_rollout_dashboard("test-tenant")

        assert "current_phase" in result
        assert "phase_progress" in result
        assert "gate_evaluation" in result
        assert isinstance(result["phase_progress"], list)
        assert len(result["phase_progress"]) == 5


# ══════════════════════════════════════════════════════════════
# 4. API ENDPOINT TESTS
# ══════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — skipping live API tests"
)
@pytest.mark.live_server
class TestAPIEndpoints:
    """Test the API endpoints via httpx."""

    @pytest.mark.asyncio
    async def test_all_p6_endpoints(self):
        """Test all P6 API endpoints in a single async context."""
        import httpx

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
            # Login
            login_resp = await client.post("/api/auth/login", json={
                "email": "demo@hotel.com", "password": "demo123",
            })
            assert login_resp.status_code == 200
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 1. Readiness Score
            r = await client.get("/api/lockdown/runtime/readiness-score", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "score" in data
            assert "issues" in data
            assert "fix_order" in data
            assert isinstance(data["score"], int)
            assert 0 <= data["score"] <= 100

            # 2. Safe Actions - Retry Safe
            r = await client.post("/api/lockdown/runtime/actions/retry-safe", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["action_type"] == "retry_safe"
            assert data["status"] in ("completed", "no_action")

            # 3. Safe Actions - Revalidate Mapping
            r = await client.post("/api/lockdown/runtime/actions/revalidate-mapping",
                                  headers=headers, json={})
            assert r.status_code == 200
            data = r.json()
            assert data["action_type"] == "revalidate_mapping"

            # 4. Safe Actions - Suppress Noise
            r = await client.post("/api/lockdown/runtime/actions/suppress-noise",
                                  headers=headers, json={"duration_minutes": 15})
            assert r.status_code == 200
            data = r.json()
            assert data["action_type"] == "suppress_noise"
            assert data["status"] == "completed"

            # 5. Rollout - State
            r = await client.get("/api/lockdown/runtime/rollout/state", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "current_phase" in data

            # 6. Rollout - Dashboard
            r = await client.get("/api/lockdown/runtime/rollout/dashboard", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "phase_progress" in data
            assert len(data["phase_progress"]) == 5

            # 7. Rollout - Initialize
            r = await client.post("/api/lockdown/runtime/rollout/initialize", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["current_phase"] == "INTERNAL"
            assert data["is_active"] is True

            # 8. Rollout - Gate Check
            r = await client.get("/api/lockdown/runtime/rollout/gate-check", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "gate_passed" in data
            assert "checks" in data

            # 9. Rollout - Advance (should fail since gates won't pass in test env)
            r = await client.post("/api/lockdown/runtime/rollout/advance", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "transitioned" in data
