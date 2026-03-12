"""
Production Go-Live Deployment Module API Tests
Tests new deployment orchestration endpoints: risk assessment, strategy, infrastructure topology,
secrets manager, backup trigger/cleanup, and horizontal scaling validation.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test user credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestDeploymentOrchestratorEndpoints:
    """Tests for deployment orchestration endpoints (NEW)."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}
    
    # ── Deployment Risk Assessment ───────────────────────────────────────
    
    def test_deployment_risk_assessment_returns_safety_score(self, auth_headers):
        """GET /api/production-golive/deployment/risk-assessment - returns safety/risk scores"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/risk-assessment",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate core risk assessment structure
        assert "safety_score" in data, "Missing 'safety_score'"
        assert "risk_score" in data, "Missing 'risk_score'"
        assert "verdict" in data, "Missing 'verdict'"
        assert "risks" in data, "Missing 'risks' array"
        assert "mitigations" in data, "Missing 'mitigations' array"
        assert "assessed_at" in data, "Missing 'assessed_at'"
        
        # Validate types
        assert isinstance(data["safety_score"], int), "safety_score should be int"
        assert isinstance(data["risk_score"], int), "risk_score should be int"
        assert data["verdict"] in ["LOW_RISK", "MEDIUM_RISK", "HIGH_RISK"], f"Invalid verdict: {data['verdict']}"
        assert 0 <= data["safety_score"] <= 100, "safety_score should be 0-100"
        
        # Validate risks array structure
        if len(data["risks"]) > 0:
            risk = data["risks"][0]
            assert "factor" in risk, "Risk missing 'factor'"
            assert "weight" in risk, "Risk missing 'weight'"
            assert "description" in risk, "Risk missing 'description'"
        
        print(f"Risk Assessment: safety={data['safety_score']}%, risk={data['risk_score']}, verdict={data['verdict']}, risks={len(data['risks'])}")
    
    def test_deployment_risk_assessment_has_mitigations_for_risks(self, auth_headers):
        """Risk assessment mitigations match risk factors."""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/risk-assessment",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Mitigations should provide actionable items
        if len(data["risks"]) > 0:
            assert len(data["mitigations"]) > 0, "Should have mitigations for identified risks"
            # Mitigations are strings with actions
            for mitigation in data["mitigations"]:
                assert isinstance(mitigation, str), "Mitigation should be string"
                assert len(mitigation) > 10, "Mitigation should be actionable text"
        
        print(f"Mitigations: {len(data['mitigations'])} recommendations")
    
    # ── Deployment Strategy ────────────────────────────────────────────
    
    def test_deployment_strategy_returns_batches_and_plan(self, auth_headers):
        """GET /api/production-golive/deployment/strategy - returns strategy and deployment batches"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/strategy",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate strategy structure
        assert "strategy" in data, "Missing 'strategy'"
        assert data["strategy"] in ["rolling_update", "blue_green", "canary"], f"Invalid strategy: {data['strategy']}"
        assert "description" in data, "Missing 'description'"
        assert "deployment_batches" in data, "Missing 'deployment_batches'"
        assert "rollback_plan" in data, "Missing 'rollback_plan'"
        assert "pre_deployment_checks" in data, "Missing 'pre_deployment_checks'"
        assert "post_deployment_checks" in data, "Missing 'post_deployment_checks'"
        assert "estimated_duration_minutes" in data, "Missing 'estimated_duration_minutes'"
        
        # Validate batches
        batches = data["deployment_batches"]
        assert isinstance(batches, list), "deployment_batches should be list"
        assert len(batches) > 0, "Should have at least one deployment batch"
        
        # Validate batch structure
        batch = batches[0]
        assert "order" in batch, "Batch missing 'order'"
        assert "component" in batch, "Batch missing 'component'"
        assert "type" in batch, "Batch missing 'type'"
        assert "replicas" in batch, "Batch missing 'replicas'"
        assert "critical" in batch, "Batch missing 'critical'"
        
        # Validate rollback plan
        rollback = data["rollback_plan"]
        assert "auto_rollback" in rollback, "Rollback missing 'auto_rollback'"
        assert "health_check_interval_sec" in rollback, "Rollback missing 'health_check_interval_sec'"
        assert "failure_threshold" in rollback, "Rollback missing 'failure_threshold'"
        
        print(f"Strategy: {data['strategy']}, {len(batches)} batches, est. {data['estimated_duration_minutes']}min")
    
    def test_deployment_strategy_includes_required_components(self, auth_headers):
        """Strategy includes all critical production components."""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/strategy",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required components for full-stack deployment
        required_components = {"backend", "frontend", "worker", "redis", "nginx"}
        batch_components = {b["component"] for b in data["deployment_batches"]}
        
        for req in required_components:
            assert req in batch_components, f"Missing required component: {req}"
        
        print(f"Components: {batch_components}")
    
    # ── Deployment Infrastructure ──────────────────────────────────────
    
    def test_deployment_infrastructure_returns_topology(self, auth_headers):
        """GET /api/production-golive/deployment/infrastructure - returns infra topology"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/infrastructure",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate infrastructure structure
        assert "components" in data, "Missing 'components'"
        assert "config_files" in data, "Missing 'config_files'"
        assert "monitoring_stack" in data, "Missing 'monitoring_stack'"
        assert "security" in data, "Missing 'security'"
        assert "grafana_dashboards" in data, "Missing 'grafana_dashboards'"
        assert "total_components" in data, "Missing 'total_components'"
        assert "critical_components" in data, "Missing 'critical_components'"
        
        # Validate components
        components = data["components"]
        assert isinstance(components, dict), "components should be dict"
        assert len(components) > 0, "Should have at least one component"
        
        # Validate component structure
        for comp_name, comp_data in components.items():
            assert "type" in comp_data, f"{comp_name} missing 'type'"
            assert "replicas_min" in comp_data, f"{comp_name} missing 'replicas_min'"
            assert "critical" in comp_data, f"{comp_name} missing 'critical'"
        
        # Validate config files
        config_files = data["config_files"]
        assert "docker_compose" in config_files, "Missing docker_compose config"
        assert "nginx" in config_files, "Missing nginx config"
        assert "prometheus" in config_files, "Missing prometheus config"
        
        # Validate monitoring stack
        monitoring = data["monitoring_stack"]
        assert "metrics" in monitoring, "Missing metrics in monitoring"
        assert "dashboards" in monitoring, "Missing dashboards in monitoring"
        
        print(f"Infrastructure: {data['total_components']} components, {data['critical_components']} critical")
    
    def test_deployment_infrastructure_has_grafana_dashboards(self, auth_headers):
        """Infrastructure includes Grafana dashboard definitions."""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/infrastructure",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        dashboards = data.get("grafana_dashboards", [])
        assert isinstance(dashboards, list), "grafana_dashboards should be list"
        assert len(dashboards) >= 3, f"Should have at least 3 dashboards, got {len(dashboards)}"
        
        # Validate dashboard structure
        for dash in dashboards:
            assert "name" in dash, "Dashboard missing 'name'"
            assert "uid" in dash, "Dashboard missing 'uid'"
            assert "path" in dash, "Dashboard missing 'path'"
        
        dashboard_names = [d["name"] for d in dashboards]
        print(f"Dashboards: {dashboard_names}")
    
    # ── Deployment First Batch ─────────────────────────────────────────
    
    def test_deployment_first_batch_returns_top_5(self, auth_headers):
        """GET /api/production-golive/deployment/first-batch - returns first 5 components"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/deployment/first-batch",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate first batch structure
        assert "strategy" in data, "Missing 'strategy'"
        assert "first_5_components" in data, "Missing 'first_5_components'"
        assert "pre_deployment_checks" in data, "Missing 'pre_deployment_checks'"
        assert "rollback_plan" in data, "Missing 'rollback_plan'"
        
        # Validate first 5 components
        first_5 = data["first_5_components"]
        assert isinstance(first_5, list), "first_5_components should be list"
        assert len(first_5) == 5, f"Should have exactly 5 components, got {len(first_5)}"
        
        print(f"First batch: {[c['component'] for c in first_5]}")


class TestSecretsManagerEndpoints:
    """Tests for secrets manager endpoints (NEW)."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}
    
    # ── Secrets Health ─────────────────────────────────────────────────
    
    def test_secrets_health_returns_provider_status(self, auth_headers):
        """GET /api/production-golive/secrets/health - returns provider health"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/secrets/health",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate secrets health structure
        assert "provider" in data, "Missing 'provider'"
        assert "status" in data, "Missing 'status'"
        assert "metrics" in data, "Missing 'metrics'"
        
        # Provider should be one of supported types
        assert data["provider"] in ["env", "aws", "vault"], f"Unknown provider: {data['provider']}"
        assert data["status"] in ["healthy", "unhealthy", "not_configured"], f"Invalid status: {data['status']}"
        
        print(f"Secrets: provider={data['provider']}, status={data['status']}")
    
    # ── Secrets Metrics ────────────────────────────────────────────────
    
    def test_secrets_metrics_returns_usage_stats(self, auth_headers):
        """GET /api/production-golive/secrets/metrics - returns usage metrics"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/secrets/metrics",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate metrics structure
        assert "provider" in data, "Missing 'provider'"
        assert "total_requests" in data, "Missing 'total_requests'"
        assert "access_log_size" in data, "Missing 'access_log_size'"
        
        # Validate types
        assert isinstance(data["total_requests"], int), "total_requests should be int"
        assert isinstance(data["access_log_size"], int), "access_log_size should be int"
        
        print(f"Secrets Metrics: requests={data['total_requests']}, log_size={data['access_log_size']}")
    
    # ── Secrets Access Log ─────────────────────────────────────────────
    
    def test_secrets_access_log_returns_masked_entries(self, auth_headers):
        """GET /api/production-golive/secrets/access-log - returns masked access log"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/secrets/access-log?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate access log structure
        assert "access_log" in data, "Missing 'access_log'"
        assert isinstance(data["access_log"], list), "access_log should be list"
        
        # If there are log entries, validate structure
        if len(data["access_log"]) > 0:
            entry = data["access_log"][0]
            assert "key" in entry, "Entry missing 'key'"
            assert "timestamp" in entry, "Entry missing 'timestamp'"
            # Key should be masked (first 3 chars + ***)
            assert "***" in entry["key"], "Key should be masked"
        
        print(f"Access log: {len(data['access_log'])} entries")


class TestBackupEndpoints:
    """Tests for backup trigger/cleanup endpoints (NEW)."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}
    
    # ── Backup Trigger ─────────────────────────────────────────────────
    
    def test_backup_trigger_creates_backup(self, auth_headers):
        """POST /api/production-golive/backup/trigger - triggers manual backup"""
        response = requests.post(
            f"{BASE_URL}/api/production-golive/backup/trigger",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate backup result structure
        assert "backup_id" in data, "Missing 'backup_id'"
        assert "status" in data, "Missing 'status'"
        assert "started_at" in data, "Missing 'started_at'"
        
        # Status should indicate outcome
        assert data["status"] in ["completed", "simulated", "running", "failed"], f"Invalid status: {data['status']}"
        
        # Backup ID should follow pattern
        assert data["backup_id"].startswith("bk_"), f"Invalid backup_id format: {data['backup_id']}"
        
        print(f"Backup: id={data['backup_id']}, status={data['status']}")
    
    # ── Backup History ─────────────────────────────────────────────────
    
    def test_backup_history_returns_list(self, auth_headers):
        """GET /api/production-golive/backup/history - returns backup history"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/backup/history?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate history structure
        assert "history" in data, "Missing 'history'"
        assert isinstance(data["history"], list), "history should be list"
        
        # If there are history entries, validate structure
        if len(data["history"]) > 0:
            entry = data["history"][0]
            assert "backup_id" in entry, "Entry missing 'backup_id'"
            assert "status" in entry, "Entry missing 'status'"
            assert "started_at" in entry, "Entry missing 'started_at'"
        
        print(f"Backup history: {len(data['history'])} entries")
    
    # ── Backup Cleanup ─────────────────────────────────────────────────
    
    def test_backup_cleanup_removes_old_backups(self, auth_headers):
        """POST /api/production-golive/backup/cleanup - cleans up old backups"""
        response = requests.post(
            f"{BASE_URL}/api/production-golive/backup/cleanup",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate cleanup result structure
        assert "removed" in data, "Missing 'removed'"
        assert "errors" in data, "Missing 'errors'"
        assert "remaining" in data, "Missing 'remaining'"
        
        # Validate types
        assert isinstance(data["removed"], int), "removed should be int"
        assert isinstance(data["errors"], int), "errors should be int"
        assert isinstance(data["remaining"], int), "remaining should be int"
        
        print(f"Cleanup: removed={data['removed']}, remaining={data['remaining']}")


class TestScalingEndpoints:
    """Tests for horizontal scaling endpoints (NEW)."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}
    
    # ── Scaling Summary ────────────────────────────────────────────────
    
    def test_scaling_summary_returns_instance_data(self, auth_headers):
        """GET /api/production-golive/scaling/summary - returns scaling status"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/scaling/summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate scaling summary structure
        assert "scaling_mode" in data, "Missing 'scaling_mode'"
        assert "current_instance" in data, "Missing 'current_instance'"
        assert "total_instances" in data, "Missing 'total_instances'"
        assert "active_instances" in data, "Missing 'active_instances'"
        assert "instances" in data, "Missing 'instances'"
        assert "stateless_check" in data, "Missing 'stateless_check'"
        
        # Validate scaling mode
        assert data["scaling_mode"] in ["single", "multi"], f"Invalid scaling_mode: {data['scaling_mode']}"
        
        # Validate types
        assert isinstance(data["total_instances"], int), "total_instances should be int"
        assert isinstance(data["active_instances"], int), "active_instances should be int"
        
        print(f"Scaling: mode={data['scaling_mode']}, instances={data['total_instances']}")
    
    # ── Stateless Check ────────────────────────────────────────────────
    
    def test_scaling_stateless_check_returns_validation(self, auth_headers):
        """GET /api/production-golive/scaling/stateless-check - returns statelessness validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/scaling/stateless-check",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate stateless check structure
        assert "ready_for_scaling" in data, "Missing 'ready_for_scaling'"
        assert "checks" in data, "Missing 'checks'"
        assert "scaling_mode" in data, "Missing 'scaling_mode'"
        assert "instance_id" in data, "Missing 'instance_id'"
        
        # Validate checks structure
        checks = data["checks"]
        assert isinstance(checks, dict), "checks should be dict"
        
        # Required statelessness checks
        required_checks = ["no_local_file_state", "env_based_config", "shared_db"]
        for check in required_checks:
            assert check in checks, f"Missing check: {check}"
        
        print(f"Stateless: ready={data['ready_for_scaling']}, checks={len(checks)}")


class TestAuthRequiredForNewEndpoints:
    """Tests to verify auth is required for all new deployment endpoints."""
    
    @pytest.mark.parametrize("endpoint,method", [
        ("/api/production-golive/deployment/risk-assessment", "GET"),
        ("/api/production-golive/deployment/strategy", "GET"),
        ("/api/production-golive/deployment/infrastructure", "GET"),
        ("/api/production-golive/deployment/first-batch", "GET"),
        ("/api/production-golive/secrets/health", "GET"),
        ("/api/production-golive/secrets/metrics", "GET"),
        ("/api/production-golive/secrets/access-log", "GET"),
        ("/api/production-golive/backup/trigger", "POST"),
        ("/api/production-golive/backup/history", "GET"),
        ("/api/production-golive/backup/cleanup", "POST"),
        ("/api/production-golive/scaling/summary", "GET"),
        ("/api/production-golive/scaling/stateless-check", "GET"),
    ])
    def test_new_endpoints_require_auth(self, endpoint, method):
        """All new deployment endpoints require authentication."""
        if method == "GET":
            response = requests.get(f"{BASE_URL}{endpoint}")
        else:
            response = requests.post(f"{BASE_URL}{endpoint}")
        
        assert response.status_code in [401, 403], \
            f"{endpoint} ({method}) should require auth, got {response.status_code}"
        print(f"Auth check passed: {endpoint} ({method}) -> {response.status_code}")


class TestSummaryEndpointIncludesNewFields:
    """Test that /summary endpoint includes new deployment-related data."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}
    
    def test_summary_includes_all_subsystems(self, auth_headers):
        """GET /api/production-golive/summary - includes all subsystems including backup"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Core required fields
        required_keys = [
            "readiness", "configuration", "config_activation", "redis", 
            "mongodb", "workers", "providers", "provider_tests", 
            "backup", "observability", "security", "prelaunch_latest", "alerts_summary"
        ]
        
        for key in required_keys:
            assert key in data, f"Summary missing: {key}"
        
        # Validate backup section structure
        backup = data.get("backup", {})
        assert "enabled" in backup, "backup missing 'enabled'"
        assert "retention_days" in backup, "backup missing 'retention_days'"
        
        print(f"Summary contains all {len(required_keys)} required subsystems")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
