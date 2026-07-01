"""
CI/CD Pipeline API Tests — 3-tier deploy validation (PR Gate, Staging Gate, Nightly)

Tests:
- GET /api/ops/cicd/tiers - Returns 3 tier configurations
- POST /api/ops/cicd/run - Trigger pipeline run for each tier
- GET /api/ops/cicd/runs - List recent pipeline runs
- GET /api/ops/cicd/runs/{run_id} - Get specific run details
- GET /api/ops/cicd/deploy-gate/{run_id} - Get deploy gate verdict
- GET /api/ops/cicd/baseline - Get last passing baselines per tier
- GET /api/ops/cicd/health-badges - Get 3 separate badges (sandbox_validation, staging_deploy_validation, prod_health)
- GET /api/ops/cicd/trends - Get trend data with overall and provider level
- Auth guard: All endpoints require Bearer token
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestCICDAuthGuard:
    """Verify all /api/ops/cicd/* endpoints require authentication."""

    def test_tiers_without_auth_returns_401(self):
        """GET /api/ops/cicd/tiers without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/ops/cicd/tiers")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_runs_without_auth_returns_401(self):
        """GET /api/ops/cicd/runs without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/ops/cicd/runs")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_health_badges_without_auth_returns_401(self):
        """GET /api/ops/cicd/health-badges without auth should return 401."""
        response = requests.get(f"{BASE_URL}/api/ops/cicd/health-badges")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_run_without_auth_returns_401(self):
        """POST /api/ops/cicd/run without auth should return 401."""
        response = requests.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "pr_gate"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestCICDTiers:
    """Test GET /api/ops/cicd/tiers endpoint."""

    def test_get_tiers_returns_3_tiers(self, api_client):
        """GET /api/ops/cicd/tiers should return 3 tier configurations."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/tiers")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "tiers" in data, "Response should contain 'tiers' key"
        
        tiers = data["tiers"]
        assert len(tiers) == 3, f"Expected 3 tiers, got {len(tiers)}"
        
        # Verify all 3 tiers exist
        assert "pr_gate" in tiers, "Missing pr_gate tier"
        assert "staging_gate" in tiers, "Missing staging_gate tier"
        assert "nightly" in tiers, "Missing nightly tier"

    def test_pr_gate_tier_config(self, api_client):
        """PR Gate tier should have correct configuration."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/tiers")
        assert response.status_code == 200
        
        pr_gate = response.json()["tiers"]["pr_gate"]
        assert pr_gate["display_name"] == "PR Gate"
        assert pr_gate["blocks_deploy"] is True
        assert pr_gate["duplicate_count"] == 3
        assert pr_gate["storm_size"] == 6
        assert "hotelrunner" in pr_gate["providers"]
        assert "exely" in pr_gate["providers"]

    def test_staging_gate_tier_config(self, api_client):
        """Staging Gate tier should have correct configuration."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/tiers")
        assert response.status_code == 200
        
        staging = response.json()["tiers"]["staging_gate"]
        assert staging["display_name"] == "Staging Gate"
        assert staging["blocks_deploy"] is True
        assert staging["duplicate_count"] == 5
        assert staging["storm_size"] == 10

    def test_nightly_tier_config(self, api_client):
        """Nightly tier should have correct configuration (blocks_deploy=False)."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/tiers")
        assert response.status_code == 200
        
        nightly = response.json()["tiers"]["nightly"]
        assert nightly["display_name"] == "Nightly Resilience"
        assert nightly["blocks_deploy"] is False  # Nightly doesn't block deploy
        assert nightly["duplicate_count"] == 10
        assert nightly["storm_size"] == 25


class TestCICDRunPipeline:
    """Test POST /api/ops/cicd/run endpoint."""

    def test_run_pr_gate_returns_result(self, api_client):
        """POST /api/ops/cicd/run with tier=pr_gate should return run result."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "pr_gate", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify run structure
        assert "run_id" in data, "Response should contain run_id"
        assert data["tier"] == "pr_gate"
        assert "acceptance_criteria" in data
        assert "deploy_gate" in data
        
        # Verify acceptance criteria structure
        acceptance = data["acceptance_criteria"]
        assert "criteria" in acceptance
        assert "all_passed" in acceptance
        assert "critical_failure_count" in acceptance
        
        # Verify deploy gate structure
        gate = data["deploy_gate"]
        assert "verdict" in gate
        assert gate["verdict"] in ["PASS", "BLOCK", "WARN"]
        assert "deploy_allowed" in gate
        assert "message" in gate

    def test_run_staging_gate_returns_full_scenarios(self, api_client):
        """POST /api/ops/cicd/run with tier=staging_gate should return full scenario pack."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "staging_gate", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["tier"] == "staging_gate"
        assert "simulation_summary" in data
        assert "provider_results" in data
        
        # Verify simulation ran
        summary = data["simulation_summary"]
        assert "total_scenarios" in summary
        assert "passed" in summary
        assert "failed" in summary

    def test_run_nightly_blocks_deploy_false(self, api_client):
        """POST /api/ops/cicd/run with tier=nightly should have blocks_deploy=false."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "nightly", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["tier"] == "nightly"
        
        # Nightly tier doesn't block deploy even on failure
        tier_config = data.get("tier_config", {})
        assert tier_config.get("blocks_deploy") is False

    def test_run_invalid_tier_returns_400(self, api_client):
        """POST /api/ops/cicd/run with invalid tier should return 400."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "invalid_tier", "triggered_by": "test_agent"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_acceptance_criteria_includes_required_checks(self, api_client):
        """Acceptance criteria should include all required checks."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "pr_gate", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200
        
        criteria = response.json()["acceptance_criteria"]["criteria"]
        criteria_ids = [c["id"] for c in criteria]
        
        # Required acceptance criteria
        required = [
            "zero_oversell",
            "zero_duplicate_consumption",
            "zero_inconsistent_state",
            "stale_provider_recovery",
            "reconciliation_recovery",
            "deterministic_modify_cancel",
            "zero_regression_vs_baseline"
        ]
        
        for req in required:
            assert req in criteria_ids, f"Missing required criteria: {req}"


class TestCICDRuns:
    """Test GET /api/ops/cicd/runs and GET /api/ops/cicd/runs/{run_id} endpoints."""

    def test_list_runs_returns_recent_runs(self, api_client):
        """GET /api/ops/cicd/runs should return list of recent runs."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "runs" in data
        assert "total" in data
        assert isinstance(data["runs"], list)

    def test_list_runs_with_tier_filter(self, api_client):
        """GET /api/ops/cicd/runs?tier=pr_gate should filter by tier."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs?tier=pr_gate")
        assert response.status_code == 200
        
        data = response.json()
        for run in data["runs"]:
            assert run["tier"] == "pr_gate", f"Expected pr_gate tier, got {run['tier']}"

    def test_get_specific_run_returns_details(self, api_client):
        """GET /api/ops/cicd/runs/{run_id} should return specific run details."""
        # First get a run_id from the list
        list_response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs?limit=1")
        assert list_response.status_code == 200
        
        runs = list_response.json()["runs"]
        if not runs:
            pytest.skip("No runs available to test")
        
        run_id = runs[0]["run_id"]
        
        # Get specific run
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs/{run_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["run_id"] == run_id
        assert "tier" in data
        assert "acceptance_criteria" in data
        assert "deploy_gate" in data
        assert "provider_results" in data

    def test_get_nonexistent_run_returns_404(self, api_client):
        """GET /api/ops/cicd/runs/{run_id} with invalid ID should return 404."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs/nonexistent-run-id")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestCICDDeployGate:
    """Test GET /api/ops/cicd/deploy-gate/{run_id} endpoint."""

    def test_get_deploy_gate_returns_verdict(self, api_client):
        """GET /api/ops/cicd/deploy-gate/{run_id} should return gate verdict."""
        # First get a run_id
        list_response = api_client.get(f"{BASE_URL}/api/ops/cicd/runs?limit=1")
        assert list_response.status_code == 200
        
        runs = list_response.json()["runs"]
        if not runs:
            pytest.skip("No runs available to test")
        
        run_id = runs[0]["run_id"]
        
        # Get deploy gate
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/deploy-gate/{run_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["run_id"] == run_id
        assert "tier" in data
        assert "deploy_gate" in data
        assert "acceptance_criteria" in data
        
        gate = data["deploy_gate"]
        assert "verdict" in gate
        assert gate["verdict"] in ["PASS", "BLOCK", "WARN"]

    def test_deploy_gate_nonexistent_run_returns_404(self, api_client):
        """GET /api/ops/cicd/deploy-gate/{run_id} with invalid ID should return 404."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/deploy-gate/nonexistent-run-id")
        assert response.status_code == 404


class TestCICDBaseline:
    """Test GET /api/ops/cicd/baseline endpoint."""

    def test_get_baseline_returns_per_tier(self, api_client):
        """GET /api/ops/cicd/baseline should return last passing baseline per tier."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/baseline")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Should have keys for all 3 tiers
        assert "pr_gate" in data
        assert "staging_gate" in data
        assert "nightly" in data


class TestCICDHealthBadges:
    """Test GET /api/ops/cicd/health-badges endpoint."""

    def test_get_health_badges_returns_3_badges(self, api_client):
        """GET /api/ops/cicd/health-badges should return 3 separate badges."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/health-badges")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "badges" in data
        
        badges = data["badges"]
        
        # Must have 3 separate badges
        assert "sandbox_validation" in badges, "Missing sandbox_validation badge"
        assert "staging_deploy_validation" in badges, "Missing staging_deploy_validation badge"
        assert "prod_health" in badges, "Missing prod_health badge"

    def test_health_badge_structure(self, api_client):
        """Each health badge should have correct structure."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/health-badges")
        assert response.status_code == 200
        
        badges = response.json()["badges"]
        
        for label, badge in badges.items():
            assert "status" in badge, f"Badge {label} missing status"
            assert "verdict" in badge, f"Badge {label} missing verdict"
            assert "tier" in badge, f"Badge {label} missing tier"
            assert "display_name" in badge, f"Badge {label} missing display_name"

    def test_health_badges_tier_mapping(self, api_client):
        """Health badges should map to correct tiers."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/health-badges")
        assert response.status_code == 200
        
        badges = response.json()["badges"]
        
        # Verify tier mapping
        assert badges["sandbox_validation"]["tier"] == "pr_gate"
        assert badges["staging_deploy_validation"]["tier"] == "staging_gate"
        assert badges["prod_health"]["tier"] == "nightly"


class TestCICDTrends:
    """Test GET /api/ops/cicd/trends endpoint."""

    def test_get_trends_returns_data(self, api_client):
        """GET /api/ops/cicd/trends should return trend data."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/trends")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify structure
        assert "overall_trend" in data
        assert "provider_trends" in data
        assert "total_runs" in data
        assert "timestamp" in data

    def test_trends_overall_structure(self, api_client):
        """Overall trend data should have correct structure."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/trends")
        assert response.status_code == 200
        
        overall = response.json()["overall_trend"]
        
        if overall:  # If there are runs
            for item in overall:
                assert "run_id" in item
                assert "tier" in item
                assert "date" in item
                assert "pass_rate" in item
                assert "verdict" in item

    def test_trends_with_tier_filter(self, api_client):
        """GET /api/ops/cicd/trends?tier=pr_gate should filter by tier."""
        response = api_client.get(f"{BASE_URL}/api/ops/cicd/trends?tier=pr_gate")
        assert response.status_code == 200
        
        overall = response.json()["overall_trend"]
        for item in overall:
            assert item["tier"] == "pr_gate"


class TestCICDAcceptanceCriteriaValues:
    """Test that acceptance criteria values are correctly evaluated."""

    def test_passing_run_has_all_criteria_passed(self, api_client):
        """A passing run should have all acceptance criteria passed."""
        # Run a pipeline
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "pr_gate", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200
        
        data = response.json()
        acceptance = data["acceptance_criteria"]
        gate = data["deploy_gate"]
        
        # If all passed, verdict should be PASS
        if acceptance["all_passed"]:
            assert gate["verdict"] == "PASS"
            assert gate["deploy_allowed"] is True
            assert acceptance["critical_failure_count"] == 0

    def test_criteria_have_severity_and_value(self, api_client):
        """Each criterion should have severity and value fields."""
        response = api_client.post(
            f"{BASE_URL}/api/ops/cicd/run",
            json={"tier": "pr_gate", "triggered_by": "test_agent"}
        )
        assert response.status_code == 200
        
        criteria = response.json()["acceptance_criteria"]["criteria"]
        
        for c in criteria:
            assert "id" in c
            assert "name" in c
            assert "passed" in c
            assert "severity" in c
            assert "value" in c


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
