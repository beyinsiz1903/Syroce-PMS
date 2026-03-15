"""
ARI Push Engine V2 API Tests.

Tests for new features added:
1. Delta Hash enrichment with 7 fields (provider, property_id, room_type, rate_plan, date_from, date_to, payload)
2. Provider Test Harness/Checklist (HotelRunner 9 steps, Exely 6 steps)
3. Drift Worker dual-mode (normal/recovery)
4. Dashboard metrics enhancement (provider_health, performance, queue stats)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")

TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"
PROPERTY_ID = "prop-001"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════════════════
# TEST HARNESS CHECKLIST TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProviderTestHarnessChecklist:
    """Provider test harness checklist endpoints."""
    
    def test_hotelrunner_checklist_returns_9_steps(self, api_client):
        """GET /api/channel-manager/ari/test-harness/checklist/hotelrunner returns 9 steps."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/test-harness/checklist/hotelrunner")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "hotelrunner"
        assert data["total"] == 9
        assert len(data["steps"]) == 9
        # Verify expected steps exist
        step_ids = [s["step"] for s in data["steps"]]
        expected_steps = ["connect", "room_list", "rate_plan_list", "mapping", "reservation_pull",
                         "ari_push_avail", "ari_push_rate", "ari_push_restriction", "webhook_roundtrip"]
        for step in expected_steps:
            assert step in step_ids, f"Missing step: {step}"
    
    def test_exely_checklist_returns_6_steps(self, api_client):
        """GET /api/channel-manager/ari/test-harness/checklist/exely returns 6 steps."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/test-harness/checklist/exely")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "exely"
        assert data["total"] == 6
        assert len(data["steps"]) == 6
        # Verify expected steps exist
        step_ids = [s["step"] for s in data["steps"]]
        expected_steps = ["wsse_auth", "hotel_avail_rq", "read_rq", "hotel_avail_notif", 
                         "rate_amount_notif", "reservation_confirm"]
        for step in expected_steps:
            assert step in step_ids, f"Missing step: {step}"
    
    def test_unknown_provider_returns_404(self, api_client):
        """GET /api/channel-manager/ari/test-harness/checklist/unknown returns 404."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/test-harness/checklist/unknown_provider")
        assert response.status_code == 404
        data = response.json()
        assert "Unknown provider" in data["detail"]


# ═══════════════════════════════════════════════════════════════════
# TEST HARNESS RUN TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProviderTestHarnessRun:
    """Provider test harness run endpoints."""
    
    def test_run_hotelrunner_all_tests(self, api_client):
        """POST /api/channel-manager/ari/test-harness/run/hotelrunner runs all 9 tests."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/test-harness/run/hotelrunner")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "hotelrunner"
        assert "results" in data
        assert "summary" in data
        assert data["summary"]["total"] == 9
        # In DRY-RUN mode, all should pass
        assert data["summary"]["passed"] == 9
        assert data["summary"]["failed"] == 0
    
    def test_run_exely_all_tests(self, api_client):
        """POST /api/channel-manager/ari/test-harness/run/exely runs all 6 tests."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/test-harness/run/exely")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "exely"
        assert "results" in data
        assert "summary" in data
        assert data["summary"]["total"] == 6
        # In DRY-RUN mode, all should pass
        assert data["summary"]["passed"] == 6
        assert data["summary"]["failed"] == 0
    
    def test_run_unknown_provider_returns_404(self, api_client):
        """POST /api/channel-manager/ari/test-harness/run/unknown returns 404."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/test-harness/run/unknown_provider")
        assert response.status_code == 404
    
    def test_test_result_structure(self, api_client):
        """Test results should have step, success, duration_ms, detail, tested_at."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/test-harness/run/hotelrunner")
        data = response.json()
        for result in data["results"]:
            assert "step" in result
            assert "success" in result
            assert "duration_ms" in result
            assert "detail" in result
            assert "tested_at" in result


# ═══════════════════════════════════════════════════════════════════
# DRIFT WORKER DUAL-MODE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDriftWorkerMode:
    """Drift worker dual-mode (normal/recovery) endpoints."""
    
    def test_get_drift_mode_returns_current_mode(self, api_client):
        """GET /api/channel-manager/ari/drift/mode returns current mode."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/drift/mode")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "interval" in data
        assert "scope" in data
        assert data["mode"] in ["normal", "recovery"]
    
    def test_switch_to_recovery_mode(self, api_client):
        """POST /api/channel-manager/ari/drift/mode/recovery switches to recovery mode."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/drift/mode/recovery")
        assert response.status_code == 200
        data = response.json()
        assert data["current_mode"] == "recovery"
        assert data["interval"] == 30  # Recovery mode = 30s interval
        assert data["scope"] == "full"  # Recovery mode = full scope
    
    def test_switch_to_normal_mode(self, api_client):
        """POST /api/channel-manager/ari/drift/mode/normal switches back to normal mode."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/drift/mode/normal")
        assert response.status_code == 200
        data = response.json()
        assert data["current_mode"] == "normal"
        assert data["interval"] == 120  # Normal mode = 120s (2 min) interval
        assert data["scope"] == "changed"  # Normal mode = changed rooms only
    
    def test_invalid_mode_returns_400(self, api_client):
        """POST /api/channel-manager/ari/drift/mode/invalid returns 400."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/drift/mode/invalid_mode")
        assert response.status_code == 400
        data = response.json()
        assert "Invalid mode" in data["detail"]


# ═══════════════════════════════════════════════════════════════════
# OPERATIONAL METRICS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOperationalMetrics:
    """Dashboard operational metrics endpoint."""
    
    def test_metrics_endpoint_accessible(self, api_client):
        """GET /api/channel-manager/ari/test-harness/metrics returns metrics."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/test-harness/metrics",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "provider_health" in data
        assert "performance" in data
        assert "queue" in data
    
    def test_queue_stats_structure(self, api_client):
        """Queue stats should have queue_depth, retry_backlog, dead_letter_count."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/test-harness/metrics",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        data = response.json()
        queue = data["queue"]
        assert "queue_depth" in queue
        assert "retry_backlog" in queue
        assert "dead_letter_count" in queue
        # All should be non-negative integers
        assert isinstance(queue["queue_depth"], int)
        assert queue["queue_depth"] >= 0
    
    def test_provider_health_has_rates(self, api_client):
        """Provider health should have ack_rate, error_rate, retry_rate."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/test-harness/metrics",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        data = response.json()
        provider_health = data["provider_health"]
        if provider_health:  # If there's any provider data
            for provider, health in provider_health.items():
                assert "total_pushes" in health
                assert "ack_rate" in health
                assert "error_rate" in health
                assert "retry_rate" in health


# ═══════════════════════════════════════════════════════════════════
# ENRICHED DELTA HASH TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEnrichedDeltaHash:
    """Verify change sets include enriched provider_delta_hash."""
    
    def test_change_sets_have_provider_delta_hash(self, api_client):
        """GET /api/channel-manager/ari/change-sets should include provider_delta_hash."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        if data["change_sets"]:
            for cs in data["change_sets"]:
                assert "provider_delta_hash" in cs, "Change set missing provider_delta_hash"
                # Hash should be 16 hex chars
                hash_value = cs["provider_delta_hash"]
                assert len(hash_value) == 16, f"Hash should be 16 chars, got {len(hash_value)}"
                assert all(c in "0123456789abcdef" for c in hash_value), "Hash should be hex"


# ═══════════════════════════════════════════════════════════════════
# ENGINE STATS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEngineStatsV2:
    """Engine stats endpoint with buffer, rate_limiter, adapters."""
    
    def test_engine_stats_has_all_fields(self, api_client):
        """GET /api/channel-manager/ari/engine-stats returns buffer, rate_limiter, adapters."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/engine-stats")
        assert response.status_code == 200
        data = response.json()
        assert "buffer" in data
        assert "rate_limiter" in data
        assert "registered_adapters" in data
        # Both adapters should be registered
        assert "hotelrunner" in data["registered_adapters"]
        assert "exely" in data["registered_adapters"]


# ═══════════════════════════════════════════════════════════════════
# AGGREGATE STATS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAggregateStats:
    """Aggregate ARI stats endpoint."""
    
    def test_stats_returns_all_metrics(self, api_client):
        """GET /api/channel-manager/ari/stats returns all aggregate metrics."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/stats",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        expected_fields = ["total_events", "pending_changes", "acked_changes", 
                         "failed_changes", "drift_count", "total_outbound_pushes"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"{field} should be integer"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
