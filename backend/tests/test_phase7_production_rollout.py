"""
Phase 7 — Production Rollout & Pilot Readiness Tests
======================================================
Tests for all Phase 7 services and API endpoints.
"""
import pytest
import httpx
import os

API = os.environ.get("REACT_APP_BACKEND_URL", "https://hotelrunner-sandbox.preview.emergentagent.com")
TEST_EMAIL = "demo@hotel.com"
TEST_PASS = "demo123"


@pytest.fixture(scope="module")
def token():
    resp = httpx.post(f"{API}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS}, timeout=15)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── 1. Production Environment Validation ──────────────────────────

class TestProductionEnvironment:
    def test_env_validation(self, headers):
        r = httpx.get(f"{API}/api/production/env/validate", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "overall_score" in data
        assert "categories" in data
        assert "infrastructure" in data["categories"]
        assert "security" in data["categories"]
        assert "data_safety" in data["categories"]
        assert "observability" in data["categories"]
        assert data["total_checks"] > 0

    def test_env_categories_have_checks(self, headers):
        r = httpx.get(f"{API}/api/production/env/validate", headers=headers, timeout=15)
        data = r.json()["data"]
        for cat_name, cat_data in data["categories"].items():
            assert "checks" in cat_data
            assert "total" in cat_data
            assert "passed" in cat_data


# ── 2. Canary Deployment ─────────────────────────────────────────

class TestCanaryDeployment:
    def test_get_deployment_plan(self, headers):
        r = httpx.get(f"{API}/api/production/canary/plan", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "stages" in data
        assert len(data["stages"]) == 4
        assert "rollback_triggers" in data
        assert "canary_metrics" in data

    def test_get_canary_status(self, headers):
        r = httpx.get(f"{API}/api/production/canary/status", headers=headers, timeout=15)
        assert r.status_code == 200

    def test_advance_canary_stage(self, headers):
        r = httpx.post(f"{API}/api/production/canary/advance",
            json={"target_stage_id": "stage_1"}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["current_stage_id"] == "stage_1"
        assert data["status"] == "active"

    def test_advance_to_stage_2(self, headers):
        r = httpx.post(f"{API}/api/production/canary/advance",
            json={"target_stage_id": "stage_2"}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["current_stage_id"] == "stage_2"

    def test_check_rollback_triggers(self, headers):
        r = httpx.get(f"{API}/api/production/canary/triggers", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "triggers" in data
        assert "any_triggered" in data
        assert "recommendation" in data

    def test_rollback(self, headers):
        r = httpx.post(f"{API}/api/production/canary/rollback",
            json={"reason": "Test rollback"}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "rolled_back"
        assert data["rollback_reason"] == "Test rollback"


# ── 3. Pilot Onboarding ──────────────────────────────────────────

class TestPilotOnboarding:
    def test_create_onboarding(self, headers):
        r = httpx.post(f"{API}/api/production/pilot/onboarding",
            json={"hotel_name": "Test Pilot Hotel"}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["hotel_name"] == "Test Pilot Hotel"
        assert data["status"] == "in_progress"

    def test_get_onboarding(self, headers):
        r = httpx.get(f"{API}/api/production/pilot/onboarding", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "steps_definition" in data
        assert "progress" in data or "status" in data

    def test_run_auto_validations(self, headers):
        r = httpx.post(f"{API}/api/production/pilot/onboarding/run-auto", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "results" in data
        assert "passed" in data
        assert "total" in data

    def test_complete_manual_step(self, headers):
        r = httpx.post(f"{API}/api/production/pilot/onboarding/complete-step",
            json={"step_id": "room_types_mapping", "notes": "Test completion"},
            headers=headers, timeout=15)
        assert r.status_code == 200

    def test_get_success_criteria(self, headers):
        r = httpx.get(f"{API}/api/production/pilot/success-criteria", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "criteria" in data
        assert "met_count" in data
        assert "pilot_success" in data


# ── 4. Pilot Monitoring ──────────────────────────────────────────

class TestPilotMonitoring:
    def test_monitoring_dashboard(self, headers):
        r = httpx.get(f"{API}/api/production/monitoring/dashboard", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "reservation_metrics" in data
        assert "sync_metrics" in data
        assert "queue_health" in data
        assert "incident_summary" in data

    def test_alerts_config(self, headers):
        r = httpx.get(f"{API}/api/production/monitoring/alerts-config", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "alerts" in data
        assert len(data["alerts"]) >= 5

    def test_generate_daily_report(self, headers):
        r = httpx.post(f"{API}/api/production/monitoring/daily-report", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "report_type" in data
        assert data["report_type"] == "daily_operations"

    def test_report_history(self, headers):
        r = httpx.get(f"{API}/api/production/monitoring/reports", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "reports" in data


# ── 5. Production Load Validation ────────────────────────────────

class TestProductionLoadValidation:
    def test_get_load_scenarios(self, headers):
        r = httpx.get(f"{API}/api/production/load/scenarios", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "scenarios" in data
        assert len(data["scenarios"]) == 5

    def test_run_load_scenario(self, headers):
        r = httpx.post(f"{API}/api/production/load/run",
            json={"scenario_id": "ota_reservation_burst"}, headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["scenario_id"] == "ota_reservation_burst"
        assert "metrics" in data
        assert "status" in data

    def test_get_load_report(self, headers):
        r = httpx.get(f"{API}/api/production/load/report?hours=24", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "runs" in data
        assert "pass_rate" in data


# ── 6. Tenant Isolation Confirmation ─────────────────────────────

class TestTenantIsolation:
    def test_isolation_validation(self, headers):
        r = httpx.get(f"{API}/api/production/isolation/validate", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "tests" in data
        assert "score" in data
        assert "critical_all_pass" in data
        assert "no_data_leakage" in data
        assert data["total"] == 8


# ── 7. Post-Launch Monitoring ────────────────────────────────────

class TestPostLaunchMonitoring:
    def test_post_launch_status(self, headers):
        r = httpx.get(f"{API}/api/production/post-launch/status", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "monitors" in data
        assert "scheduled_drills" in data
        assert "monitoring_active" in data

    def test_record_drill(self, headers):
        r = httpx.post(f"{API}/api/production/post-launch/record-drill",
            json={"schedule_id": "weekly_incident_drill", "result": "pass", "details": {"notes": "Test drill"}},
            headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["schedule_id"] == "weekly_incident_drill"
        assert data["result"] == "pass"

    def test_maturity_report(self, headers):
        r = httpx.get(f"{API}/api/production/post-launch/maturity-report", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "current_score" in data
        assert "uptime_percent" in data


# ── 8. Final Maturity Score ──────────────────────────────────────

class TestFinalMaturityScore:
    def test_compute_score(self, headers):
        r = httpx.get(f"{API}/api/production/maturity/score", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "overall_score" in data
        assert "maturity_level" in data
        assert "maturity_name" in data
        assert "categories" in data
        assert "go_live_ready" in data

    def test_score_history(self, headers):
        r = httpx.get(f"{API}/api/production/maturity/history?limit=5", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "scores" in data
