"""
Deploy Tracker API Tests — CI/CD → Control Plane Integration
Tests for:
  - POST /api/ops/deploys (record deploy event)
  - GET /api/ops/dashboard/deploys (deploy history)
  - GET /api/ops/dashboard/deploy-stats (aggregated statistics)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


class TestDeployTrackerAPI:
    """Deploy Tracker API endpoint tests"""

    # ─── POST /api/ops/deploys ───────────────────────────────────────
    def test_record_deploy_event_success(self):
        """POST /api/ops/deploys - Record a successful deploy event"""
        unique_sha = f"pytest-{uuid.uuid4().hex[:16]}"
        payload = {
            "sha": unique_sha,
            "environment": "pytest-env",
            "status": "success",
            "actor": "pytest-runner",
            "branch": "test-branch",
            "smoke_test": {
                "endpoints": [
                    {"name": "Health", "path": "/api/health", "status": 200, "latency_ms": 50, "result": "OK"}
                ]
            },
            "rollback": False
        }
        response = requests.post(f"{BASE_URL}/api/ops/deploys", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("recorded") is True
        assert data.get("sha") == unique_sha[:8]  # short_sha
        assert data.get("environment") == "pytest-env"
        assert data.get("status") == "success"

    def test_record_deploy_event_failure_with_rollback(self):
        """POST /api/ops/deploys - Record a failed deploy with rollback"""
        unique_sha = f"pytest-fail-{uuid.uuid4().hex[:16]}"
        payload = {
            "sha": unique_sha,
            "environment": "pytest-staging",
            "status": "failure",
            "actor": "pytest-runner",
            "branch": "feature/broken",
            "smoke_test": {
                "endpoints": [
                    {"name": "Health", "path": "/api/health", "status": 500, "latency_ms": 3000, "result": "FAIL"}
                ]
            },
            "rollback": True,
            "rollback_reason": "Health check failed — HTTP 500"
        }
        response = requests.post(f"{BASE_URL}/api/ops/deploys", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("recorded") is True
        assert data.get("status") == "failure"

    def test_record_deploy_event_minimal_fields(self):
        """POST /api/ops/deploys - Record with minimal required fields"""
        unique_sha = f"pytest-min-{uuid.uuid4().hex[:16]}"
        payload = {
            "sha": unique_sha,
            "environment": "pytest-minimal",
            "status": "success"
        }
        response = requests.post(f"{BASE_URL}/api/ops/deploys", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("recorded") is True

    # ─── GET /api/ops/dashboard/deploys ──────────────────────────────
    def test_get_deploy_history(self):
        """GET /api/ops/dashboard/deploys - Returns deploy history list"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "deploys" in data
        assert "count" in data
        assert isinstance(data["deploys"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["deploys"])

    def test_get_deploy_history_with_limit(self):
        """GET /api/ops/dashboard/deploys?limit=5 - Respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys", params={"limit": 5})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["deploys"]) <= 5

    def test_get_deploy_history_with_environment_filter(self):
        """GET /api/ops/dashboard/deploys?environment=production - Filters by environment"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys", params={"environment": "production"})
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned deploys should be for production environment
        for deploy in data["deploys"]:
            assert deploy.get("environment") == "production"

    def test_deploy_history_sorted_newest_first(self):
        """GET /api/ops/dashboard/deploys - Returns newest first"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys", params={"limit": 10})
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data["deploys"]) >= 2:
            # Verify descending order by recorded_at
            for i in range(len(data["deploys"]) - 1):
                current = data["deploys"][i].get("recorded_at", "")
                next_one = data["deploys"][i + 1].get("recorded_at", "")
                assert current >= next_one, "Deploys should be sorted newest first"

    def test_deploy_history_contains_expected_fields(self):
        """GET /api/ops/dashboard/deploys - Each deploy has required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys", params={"limit": 1})
        
        assert response.status_code == 200
        data = response.json()
        
        if data["deploys"]:
            deploy = data["deploys"][0]
            # Required fields
            assert "sha" in deploy
            assert "short_sha" in deploy
            assert "environment" in deploy
            assert "status" in deploy
            assert "recorded_at" in deploy
            # Optional but expected fields
            assert "actor" in deploy
            assert "branch" in deploy
            assert "smoke_test" in deploy
            assert "rollback" in deploy

    # ─── GET /api/ops/dashboard/deploy-stats ─────────────────────────
    def test_get_deploy_stats(self):
        """GET /api/ops/dashboard/deploy-stats - Returns aggregated statistics"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "by_environment" in data
        assert "overall" in data
        assert isinstance(data["by_environment"], list)
        assert isinstance(data["overall"], dict)

    def test_deploy_stats_overall_structure(self):
        """GET /api/ops/dashboard/deploy-stats - Overall stats have required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        
        assert response.status_code == 200
        data = response.json()
        overall = data["overall"]
        
        # Required overall fields
        assert "total_deploys" in overall
        assert "total_success" in overall
        assert "total_failure" in overall
        assert "total_rollbacks" in overall
        assert "overall_success_rate" in overall
        
        # Type checks
        assert isinstance(overall["total_deploys"], int)
        assert isinstance(overall["overall_success_rate"], (int, float))

    def test_deploy_stats_environment_breakdown(self):
        """GET /api/ops/dashboard/deploy-stats - Environment breakdown has required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        
        assert response.status_code == 200
        data = response.json()
        
        for env_stat in data["by_environment"]:
            assert "environment" in env_stat
            assert "total" in env_stat
            assert "success" in env_stat
            assert "failure" in env_stat
            assert "rollback_count" in env_stat
            assert "success_rate" in env_stat
            assert "last_deploy" in env_stat

    def test_deploy_stats_success_rate_calculation(self):
        """GET /api/ops/dashboard/deploy-stats - Success rate is correctly calculated"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        
        assert response.status_code == 200
        data = response.json()
        overall = data["overall"]
        
        if overall["total_deploys"] > 0:
            expected_rate = round((overall["total_success"] / overall["total_deploys"]) * 100, 1)
            assert abs(overall["overall_success_rate"] - expected_rate) < 0.2, \
                f"Success rate mismatch: expected {expected_rate}, got {overall['overall_success_rate']}"


# ─── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def check_base_url():
    """Ensure BASE_URL is set"""
    if not BASE_URL:
        pytest.skip("VITE_BACKEND_URL not set")
