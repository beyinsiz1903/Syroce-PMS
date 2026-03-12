"""
Infrastructure Hardening API External Tests.
Tests all /api/infra/* endpoints via HTTP requests to the public URL.
These tests verify the actual deployed API functionality.
"""
import pytest
import requests
import os

# Use public URL for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://hardened-health-api.preview.emergentagent.com')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token once for all tests in module."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("access_token")
    assert token, "No access_token in response"
    return token


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ── Summary Endpoint (returns all 8 sections) ─────────────────────

class TestInfraSummary:
    """Tests for /api/infra/summary endpoint."""
    
    def test_summary_returns_all_sections(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify all 8 sections present
        expected_sections = ["redis_cluster", "distributed_locks", "worker_queues", 
                           "secrets", "backup", "observability", "scaling", "container"]
        for section in expected_sections:
            assert section in data, f"Missing section: {section}"
    
    def test_summary_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/infra/summary")
        assert resp.status_code == 403


# ── Redis Cluster Endpoints ────────────────────────────────────────

class TestRedisEndpoints:
    """Tests for Redis cluster endpoints."""
    
    def test_redis_health_returns_status_and_mode(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/redis/health", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "mode" in data
        # In fallback mode, status should be disconnected
        assert data["status"] in ("connected", "disconnected")
    
    def test_redis_metrics_returns_connection_metrics(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/redis/metrics", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "mode" in data
        assert "connections_created" in data
    
    def test_redis_locks_returns_metrics_and_active(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/redis/locks", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "active_locks" in data
        # Verify metrics structure
        assert "locks_acquired" in data["metrics"]


# ── Worker Queue Endpoints ─────────────────────────────────────────

class TestWorkerEndpoints:
    """Tests for worker queue endpoints."""
    
    def test_workers_summary_returns_queues_and_counts(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/workers/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "queues" in data
        assert "total_submitted" in data
        assert len(data["queues"]) >= 6  # 6 named queues
    
    def test_workers_queues_returns_six_named_queues(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/workers/queues", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Verify all 6 named queues
        expected_queues = ["default", "ml", "analytics", "messaging", "pipeline", "backup"]
        for queue in expected_queues:
            assert queue in data, f"Missing queue: {queue}"
    
    def test_workers_failures_returns_list(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/workers/failures", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_workers_stuck_returns_list(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/workers/stuck", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── Secrets Management Endpoints ───────────────────────────────────

class TestSecretsEndpoints:
    """Tests for secrets management endpoints."""
    
    def test_secrets_health_returns_env_provider(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/secrets/health", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "env"
        assert data["status"] == "healthy"
    
    def test_secrets_audit_returns_log_and_metrics(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/secrets/audit", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_log" in data
        assert "metrics" in data


# ── Backup & DR Endpoints ──────────────────────────────────────────

class TestBackupEndpoints:
    """Tests for backup and disaster recovery endpoints."""
    
    def test_backup_status_returns_enabled_rpo_collections(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/backup/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "rpo_target" in data
        assert "critical_collections" in data
        assert len(data["critical_collections"]) > 0
    
    def test_backup_history_returns_list(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/backup/history", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_backup_trigger_starts_backup(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/infra/backup/trigger", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "backup_triggered"
    
    def test_backup_cleanup_returns_removed_count(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/api/infra/backup/cleanup", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "removed" in data


# ── Cloud Observability Endpoints ──────────────────────────────────

class TestObservabilityEndpoints:
    """Tests for cloud observability endpoints."""
    
    def test_observability_status_returns_otel_sentry(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/observability/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "otel" in data
        assert "sentry" in data
    
    def test_observability_metrics_returns_latency_counters_gauges(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/observability/metrics", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "latency" in data
        assert "counters" in data
        assert "gauges" in data


# ── Horizontal Scaling Endpoints ───────────────────────────────────

class TestScalingEndpoints:
    """Tests for horizontal scaling endpoints."""
    
    def test_scaling_summary_returns_mode_instances(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/scaling/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "scaling_mode" in data
        assert "total_instances" in data
    
    def test_scaling_instances_returns_list(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/scaling/instances", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_stateless_check_returns_checks(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/scaling/stateless-check", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert "ready_for_scaling" in data
    
    def test_readiness_works_without_auth(self):
        """Load balancer readiness probe should work WITHOUT auth."""
        resp = requests.get(f"{BASE_URL}/api/infra/scaling/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True


# ── Container Info Endpoint ────────────────────────────────────────

class TestContainerEndpoints:
    """Tests for container info endpoints."""
    
    def test_container_info_returns_runtime_info(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/infra/container/info", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "is_containerized" in data
        assert "is_kubernetes" in data
        assert "python_version" in data
        assert "environment_vars_present" in data


# ── Authentication Tests ───────────────────────────────────────────

class TestAuthRequired:
    """Tests that endpoints require authentication."""
    
    @pytest.mark.parametrize("endpoint", [
        "/api/infra/summary",
        "/api/infra/redis/health",
        "/api/infra/redis/metrics",
        "/api/infra/redis/locks",
        "/api/infra/workers/summary",
        "/api/infra/workers/queues",
        "/api/infra/secrets/health",
        "/api/infra/backup/status",
        "/api/infra/observability/status",
        "/api/infra/scaling/summary",
        "/api/infra/container/info",
    ])
    def test_endpoints_return_403_without_token(self, endpoint):
        """All authenticated endpoints should return 403 without token."""
        resp = requests.get(f"{BASE_URL}{endpoint}")
        assert resp.status_code == 403, f"{endpoint} returned {resp.status_code}"
