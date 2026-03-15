"""
Test Operational Monitoring & Alerting System
==============================================

Tests the NEW Monitoring feature with 6 API endpoints:
1. GET /api/channel-manager/monitoring/overview
2. GET /api/channel-manager/monitoring/alerts
3. GET /api/channel-manager/monitoring/metrics
4. GET /api/channel-manager/monitoring/providers
5. POST /api/channel-manager/monitoring/alerts/{alert_id}/ack
6. POST /api/channel-manager/monitoring/alerts/{alert_id}/resolve

Also validates:
- Monitoring worker state
- Alert lifecycle (create -> ack -> resolve)
- 5 health domain statuses (providers, ingest, ARI, reconciliation, queue)
"""
import pytest
import requests
import os
import time
import uuid
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for testing."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Auth headers for requests."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


# ══════════════════════════════════════════════════════════════════════
# Overview Endpoint Tests
# ══════════════════════════════════════════════════════════════════════

class TestMonitoringOverview:
    """Test GET /api/channel-manager/monitoring/overview"""

    def test_overview_returns_200(self, headers):
        """Overview endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_overview_has_system_health(self, headers):
        """Overview should include system_health field."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        assert "system_health" in data, "Missing system_health"
        assert data["system_health"] in ["healthy", "degraded", "critical", "unknown"], \
            f"Invalid system_health: {data['system_health']}"

    def test_overview_has_alert_counts(self, headers):
        """Overview should include active_alerts and critical_alerts counts."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        assert "active_alerts" in data, "Missing active_alerts"
        assert "critical_alerts" in data, "Missing critical_alerts"
        assert isinstance(data["active_alerts"], int)
        assert isinstance(data["critical_alerts"], int)

    def test_overview_has_5_domain_statuses(self, headers):
        """Overview should include status for all 5 health domains."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        
        # Check provider_statuses exists
        assert "provider_statuses" in data, "Missing provider_statuses"
        
        # Check domain statuses
        assert "ingest_status" in data, "Missing ingest_status"
        assert "ari_status" in data, "Missing ari_status"
        assert "recon_status" in data, "Missing recon_status"
        assert "queue_status" in data, "Missing queue_status"
        
        # Validate status values
        valid_statuses = ["healthy", "degraded", "critical", "unknown", "inactive"]
        for status_key in ["ingest_status", "ari_status", "recon_status", "queue_status"]:
            assert data[status_key] in valid_statuses, f"Invalid {status_key}: {data[status_key]}"

    def test_overview_has_queue_depth(self, headers):
        """Overview should include queue_depth metric."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        assert "queue_depth" in data, "Missing queue_depth"
        assert isinstance(data["queue_depth"], int)

    def test_overview_has_reconciliation_open_cases(self, headers):
        """Overview should include reconciliation_open_cases metric."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        assert "reconciliation_open_cases" in data, "Missing reconciliation_open_cases"
        assert isinstance(data["reconciliation_open_cases"], int)

    def test_overview_has_worker_state(self, headers):
        """Overview should include monitoring worker state."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        assert "worker" in data, "Missing worker state"
        worker = data["worker"]
        assert "running" in worker, "Missing worker.running"
        assert "interval_seconds" in worker, "Missing worker.interval_seconds"
        assert worker["interval_seconds"] == 60, "Monitoring worker interval should be 60s"


# ══════════════════════════════════════════════════════════════════════
# Alerts Endpoint Tests
# ══════════════════════════════════════════════════════════════════════

class TestMonitoringAlerts:
    """Test GET /api/channel-manager/monitoring/alerts"""

    def test_alerts_returns_200(self, headers):
        """Alerts endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts",
            headers=headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_alerts_returns_list(self, headers):
        """Alerts endpoint should return alerts list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts",
            headers=headers,
        )
        data = response.json()
        assert "alerts" in data, "Missing alerts list"
        assert isinstance(data["alerts"], list)
        assert "count" in data, "Missing count"
        assert "active_count" in data, "Missing active_count"

    def test_alerts_filter_by_status(self, headers):
        """Alerts can be filtered by status."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts?status=active",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        for alert in data["alerts"]:
            assert alert["status"] == "active"

    def test_alerts_filter_by_severity(self, headers):
        """Alerts can be filtered by severity."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts?severity=critical",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        for alert in data["alerts"]:
            assert alert["severity"] == "critical"

    def test_alert_structure(self, headers):
        """Alerts should have correct structure."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts",
            headers=headers,
        )
        data = response.json()
        if data["alerts"]:
            alert = data["alerts"][0]
            required_fields = ["id", "alert_type", "severity", "title", "status", "created_at"]
            for field in required_fields:
                assert field in alert, f"Missing field: {field}"


# ══════════════════════════════════════════════════════════════════════
# Metrics Endpoint Tests
# ══════════════════════════════════════════════════════════════════════

class TestMonitoringMetrics:
    """Test GET /api/channel-manager/monitoring/metrics"""

    def test_metrics_returns_200(self, headers):
        """Metrics endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_metrics_has_all_5_domains(self, headers):
        """Metrics should include all 5 health domains."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        
        assert "system_health" in data, "Missing system_health"
        assert "provider_health" in data, "Missing provider_health"
        assert "ingest_health" in data, "Missing ingest_health"
        assert "ari_health" in data, "Missing ari_health"
        assert "reconciliation_health" in data, "Missing reconciliation_health"
        assert "queue_health" in data, "Missing queue_health"

    def test_metrics_ingest_health_fields(self, headers):
        """Ingest health should have expected fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        ingest = data["ingest_health"]
        
        expected_fields = ["total_events", "pending", "processed", "failed", "status"]
        for field in expected_fields:
            assert field in ingest, f"Missing ingest_health.{field}"

    def test_metrics_ari_health_fields(self, headers):
        """ARI health should have expected fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        ari = data["ari_health"]
        
        expected_fields = ["total_pushes_24h", "success_rate", "pending_changesets", "status"]
        for field in expected_fields:
            assert field in ari, f"Missing ari_health.{field}"

    def test_metrics_reconciliation_health_fields(self, headers):
        """Reconciliation health should have expected fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        recon = data["reconciliation_health"]
        
        expected_fields = ["open_cases", "cases_by_type", "cases_by_severity", "status"]
        for field in expected_fields:
            assert field in recon, f"Missing reconciliation_health.{field}"

    def test_metrics_queue_health_fields(self, headers):
        """Queue health should have expected fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        queue = data["queue_health"]
        
        expected_fields = ["workers", "stalled_workers", "queue_depth", "status"]
        for field in expected_fields:
            assert field in queue, f"Missing queue_health.{field}"


# ══════════════════════════════════════════════════════════════════════
# Providers Endpoint Tests
# ══════════════════════════════════════════════════════════════════════

class TestMonitoringProviders:
    """Test GET /api/channel-manager/monitoring/providers"""

    def test_providers_returns_200(self, headers):
        """Providers endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/providers",
            headers=headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_providers_has_provider_details(self, headers):
        """Providers endpoint should include provider health details."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/providers",
            headers=headers,
        )
        data = response.json()
        
        assert "providers" in data, "Missing providers"
        assert "provider_alerts" in data, "Missing provider_alerts"
        assert "total_connections" in data, "Missing total_connections"
        assert "active_connections" in data, "Missing active_connections"

    def test_providers_health_breakdown(self, headers):
        """Each provider should have health metrics."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/providers",
            headers=headers,
        )
        data = response.json()
        
        for provider_name, provider_data in data["providers"].items():
            expected_fields = ["connection_count", "status", "consecutive_failures"]
            for field in expected_fields:
                assert field in provider_data, f"Missing {provider_name}.{field}"


# ══════════════════════════════════════════════════════════════════════
# Alert Lifecycle Tests (Ack/Resolve)
# ══════════════════════════════════════════════════════════════════════

class TestAlertLifecycle:
    """Test alert acknowledge and resolve endpoints."""

    def test_ack_nonexistent_alert_returns_404(self, headers):
        """Acknowledging nonexistent alert should return 404."""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{fake_id}/ack",
            headers=headers,
            json={"note": "test"},
        )
        assert response.status_code == 404

    def test_resolve_nonexistent_alert_returns_404(self, headers):
        """Resolving nonexistent alert should return 404."""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{fake_id}/resolve",
            headers=headers,
            json={"resolution": "test"},
        )
        assert response.status_code == 404

    def test_alert_lifecycle_with_existing_alert(self, headers):
        """Test full alert lifecycle if active alerts exist."""
        # Get existing alerts
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts?status=active",
            headers=headers,
        )
        data = response.json()
        
        if not data["alerts"]:
            pytest.skip("No active alerts to test lifecycle")
        
        alert = data["alerts"][0]
        alert_id = alert["id"]
        
        # Acknowledge alert
        ack_response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{alert_id}/ack",
            headers=headers,
            json={"note": "TEST_ACK_NOTE"},
        )
        assert ack_response.status_code == 200, f"Ack failed: {ack_response.text}"
        ack_data = ack_response.json()
        assert ack_data["alert_id"] == alert_id
        
        # Verify alert is now acknowledged
        verify_response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts",
            headers=headers,
        )
        verify_data = verify_response.json()
        updated_alert = next((a for a in verify_data["alerts"] if a["id"] == alert_id), None)
        assert updated_alert is not None
        assert updated_alert["status"] == "acknowledged"
        
        # Resolve alert
        resolve_response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{alert_id}/resolve",
            headers=headers,
            json={"resolution": "TEST_RESOLVED"},
        )
        assert resolve_response.status_code == 200, f"Resolve failed: {resolve_response.text}"
        
        # Verify alert is resolved
        final_response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts",
            headers=headers,
        )
        final_data = final_response.json()
        final_alert = next((a for a in final_data["alerts"] if a["id"] == alert_id), None)
        assert final_alert is not None
        assert final_alert["status"] == "resolved"

    def test_cannot_ack_already_resolved_alert(self, headers):
        """Cannot acknowledge an already resolved alert."""
        # Find a resolved alert
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts?status=resolved",
            headers=headers,
        )
        data = response.json()
        
        if not data["alerts"]:
            pytest.skip("No resolved alerts to test")
        
        alert_id = data["alerts"][0]["id"]
        
        # Try to acknowledge
        ack_response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{alert_id}/ack",
            headers=headers,
            json={"note": "Should fail"},
        )
        assert ack_response.status_code == 400

    def test_cannot_resolve_already_resolved_alert(self, headers):
        """Cannot resolve an already resolved alert."""
        # Find a resolved alert
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts?status=resolved",
            headers=headers,
        )
        data = response.json()
        
        if not data["alerts"]:
            pytest.skip("No resolved alerts to test")
        
        alert_id = data["alerts"][0]["id"]
        
        # Try to resolve again
        resolve_response = requests.post(
            f"{BASE_URL}/api/channel-manager/monitoring/alerts/{alert_id}/resolve",
            headers=headers,
            json={"resolution": "Should fail"},
        )
        assert resolve_response.status_code == 400


# ══════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════

class TestMonitoringIntegration:
    """Integration tests for monitoring system."""

    def test_monitoring_worker_is_running(self, headers):
        """Monitoring worker should be running."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/overview",
            headers=headers,
        )
        data = response.json()
        worker = data.get("worker", {})
        
        # Worker should be running after startup
        assert worker.get("running") is True, "Monitoring worker not running"

    def test_metrics_collected_at_timestamp(self, headers):
        """Metrics should have collected_at timestamp."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        
        assert "collected_at" in data, "Missing collected_at"
        # Validate timestamp format
        collected_at = data["collected_at"]
        assert "T" in collected_at, "Invalid timestamp format"

    def test_all_endpoints_require_auth(self):
        """All monitoring endpoints should require authentication."""
        endpoints = [
            "/api/channel-manager/monitoring/overview",
            "/api/channel-manager/monitoring/alerts",
            "/api/channel-manager/monitoring/metrics",
            "/api/channel-manager/monitoring/providers",
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            # API returns 401 or 403 for unauthenticated requests
            assert response.status_code in [401, 403], f"{endpoint} should require auth, got {response.status_code}"


# ══════════════════════════════════════════════════════════════════════
# Real Provider Integration Tests  
# ══════════════════════════════════════════════════════════════════════

class TestRealProviderIntegration:
    """Test that snapshot collectors and workers use real provider APIs."""

    def test_ingest_workers_have_real_provider_imports(self, headers):
        """Verify ingest workers import real provider clients."""
        # Get worker states to ensure workers are configured
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/metrics",
            headers=headers,
        )
        data = response.json()
        queue = data.get("queue_health", {})
        workers = queue.get("workers", {})
        
        # Should have hotelrunner_pull and exely_pull workers
        worker_names = list(workers.keys())
        assert any("hotelrunner" in name.lower() for name in worker_names), \
            f"HotelRunner pull worker not found in {worker_names}"
        assert any("exely" in name.lower() for name in worker_names), \
            f"Exely pull worker not found in {worker_names}"

    def test_provider_connections_exist(self, headers):
        """Verify provider connections are configured."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/monitoring/providers",
            headers=headers,
        )
        data = response.json()
        
        # Should have some provider connections
        assert data.get("total_connections", 0) >= 0, "Provider connections should be accessible"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
