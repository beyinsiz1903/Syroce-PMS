"""
Phase 6 — Runtime Validation & Go-Live API Integration Tests
"""
import pytest
import httpx
import uuid

API_BASE = "http://localhost:8001"


@pytest.fixture(scope="session")
def auth_headers():
    resp = httpx.post(
        f"{API_BASE}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Validation Scenarios ─────────────────────────────────────

class TestValidationScenarios:
    def test_get_scenarios(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/scenarios", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]["scenarios"]
        assert "load" in data
        assert "stress" in data
        assert "chaos" in data
        assert "soak" in data
        assert len(data["load"]) == 5
        assert len(data["stress"]) == 4
        assert len(data["chaos"]) == 5

    def test_run_load_scenario(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/run",
            json={"scenario_type": "load", "scenario_id": "ota_reservation_burst"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "passed"
        assert data["metrics"]["total_requests"] > 0
        assert data["metrics"]["error_rate"] <= 0.02

    def test_run_stress_scenario(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/run",
            json={"scenario_type": "stress", "scenario_id": "concurrent_frontdesk"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "passed"
        assert data["metrics"]["total_requests"] == 30

    def test_run_chaos_scenario(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/run",
            json={"scenario_type": "chaos", "scenario_id": "redis_connection_flap"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "passed"
        assert "recovery_seconds" in data["metrics"]

    def test_unknown_scenario_fails(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/run",
            json={"scenario_type": "load", "scenario_id": "nonexistent"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_validation_report(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/report?hours=72", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_runs" in data
        assert "pass_rate" in data
        assert data["pass_rate"] >= 0


# ── Incident Drills ──────────────────────────────────────────

class TestIncidentDrills:
    def test_list_drills(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/drills", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 5

    def test_execute_drill(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/drills/execute",
            json={"drill_id": "database_latency"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "completed"
        assert data["detection_within_threshold"] is True
        assert "baseline_avg_ms" in data["metrics"]

    def test_drill_history(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/drills/history", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "drills" in data

    def test_unknown_drill_fails(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/validation/drills/execute",
            json={"drill_id": "nonexistent"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_drill_cleanup(self, auth_headers):
        r = httpx.post(f"{API_BASE}/api/validation/drills/cleanup", headers=auth_headers)
        assert r.status_code == 200
        assert "cleaned_documents" in r.json()["data"]


# ── Observability Validation ─────────────────────────────────

class TestObservabilityValidation:
    def test_full_validation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/observability", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "overall_score" in data
        assert data["overall_score"] >= 50
        assert len(data["categories"]) == 4

    def test_metrics_validation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/observability/metrics", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["category"] == "metrics"

    def test_logs_validation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/observability/logs", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["category"] == "logs"

    def test_alerts_validation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/observability/alerts", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["category"] == "alerts"

    def test_audit_timeline_validation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/observability/audit-timeline", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["category"] == "audit_timeline"


# ── Go-Live Score ────────────────────────────────────────────

class TestGoLiveScore:
    def test_compute_score(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/golive-score", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "overall_score" in data
        assert "maturity_level" in data
        assert "maturity_name" in data
        assert "go_live_ready" in data
        assert "categories" in data
        assert len(data["categories"]) == 7
        # Score should be positive
        assert data["overall_score"] > 0

    def test_score_categories(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/golive-score", headers=auth_headers)
        data = r.json()["data"]
        expected_categories = [
            "runtime_validation", "provider_validation", "incident_response",
            "tenant_isolation", "observability", "audit_timeline", "pilot_checklist"
        ]
        for cat in expected_categories:
            assert cat in data["categories"]
            assert "score" in data["categories"][cat]
            assert "weight" in data["categories"][cat]

    def test_score_history(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/validation/golive-score/history", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "scores" in data
