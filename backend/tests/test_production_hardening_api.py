"""
Production Hardening API Tests.

Tests HTTP endpoints for:
  - Health Dashboard API
  - Alert Delivery API
  - Background Worker API
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

# Test session with auth
@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ══════════════════════════════════════════════════════════════════
# Health Dashboard API Tests
# ══════════════════════════════════════════════════════════════════

class TestHealthDashboardAPI:
    """Tests for GET /api/channel-manager/v2/health-dashboard/connectors."""

    def test_get_all_connector_health(self, auth_headers):
        """GET connectors health returns data with expected structure."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/health-dashboard/connectors",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Validate structure
        assert "connectors" in data
        assert "total" in data
        assert "average_health_score" in data
        assert isinstance(data["connectors"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["average_health_score"], (int, float))
        
        # Should have healthy/degraded/critical counts
        assert "healthy" in data
        assert "degraded" in data
        assert "critical" in data

    def test_get_connector_health_not_found(self, auth_headers):
        """GET non-existent connector returns 404."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/health-dashboard/connectors/nonexistent-connector-id",
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_health_dashboard_requires_auth(self):
        """Health dashboard endpoints require authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/health-dashboard/connectors"
        )
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden


# ══════════════════════════════════════════════════════════════════
# Alert Delivery API Tests
# ══════════════════════════════════════════════════════════════════

class TestAlertDeliveryAPI:
    """Tests for Alert Delivery channel CRUD endpoints."""

    def test_list_delivery_channels(self, auth_headers):
        """GET /delivery/channels returns channel list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "channels" in data
        assert "count" in data
        assert isinstance(data["channels"], list)

    def test_create_delivery_channel(self, auth_headers):
        """POST /delivery/channels creates a new channel."""
        payload = {
            "channel_type": "webhook",
            "name": "TEST_webhook_channel",
            "enabled": True,
            "min_severity": "warning",
            "config": {"url": "https://example.com/webhook"},
            "throttle_seconds": 300
        }
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers,
            json=payload
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "channel" in data
        assert data["channel"]["name"] == "TEST_webhook_channel"
        assert data["channel"]["channel_type"] == "webhook"
        assert "id" in data["channel"]

    def test_delete_delivery_channel(self, auth_headers):
        """DELETE /delivery/channels/{id} removes channel."""
        # First create a channel
        payload = {
            "channel_type": "slack",
            "name": "TEST_to_delete",
            "enabled": True,
            "min_severity": "critical",
            "config": {},
            "throttle_seconds": 60
        }
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers,
            json=payload
        )
        assert create_response.status_code == 200
        channel_id = create_response.json()["channel"]["id"]
        
        # Delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels/{channel_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        
        # Verify it's gone from list
        list_response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers
        )
        channels = list_response.json()["channels"]
        channel_ids = [c["id"] for c in channels]
        assert channel_id not in channel_ids

    def test_delete_nonexistent_channel(self, auth_headers):
        """DELETE non-existent channel returns 404."""
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels/nonexistent-id",
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_test_delivery_channel(self, auth_headers):
        """POST /delivery/test/{id} sends test notification."""
        # First create a channel
        payload = {
            "channel_type": "webhook",
            "name": "TEST_for_testing",
            "enabled": True,
            "min_severity": "info",
            "config": {"url": ""},  # Empty URL so it won't actually send
            "throttle_seconds": 0
        }
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers,
            json=payload
        )
        channel_id = create_response.json()["channel"]["id"]
        
        # Test it
        test_response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/delivery/test/{channel_id}",
            headers=auth_headers
        )
        assert test_response.status_code == 200
        
        data = test_response.json()
        assert "message" in data
        assert "result" in data

    def test_test_nonexistent_channel(self, auth_headers):
        """POST /delivery/test/{id} with invalid id returns 404."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/delivery/test/nonexistent-id",
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_get_delivery_log(self, auth_headers):
        """GET /delivery/log returns delivery logs."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/delivery/log",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "logs" in data
        assert "count" in data
        assert isinstance(data["logs"], list)

    def test_delivery_requires_auth(self):
        """Delivery endpoints require authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels"
        )
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden


# ══════════════════════════════════════════════════════════════════
# Background Worker API Tests
# ══════════════════════════════════════════════════════════════════

class TestBackgroundWorkerAPI:
    """Tests for Background Worker job endpoints."""

    def test_run_job(self, auth_headers):
        """POST /worker/jobs/run triggers a specific job."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs/run?job_type=connector_health_check",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)  # Should return job info

    def test_run_job_all_types(self, auth_headers):
        """Each job type can be triggered."""
        # Note: reservation_import may fail with 502 if external HotelRunner is unavailable
        job_types = [
            # "reservation_import",  # Skip - requires external HotelRunner connection
            "inventory_safety_sync", 
            "connector_health_check",
            "metrics_aggregation"
        ]
        for jt in job_types:
            response = requests.post(
                f"{BASE_URL}/api/channel-manager/v2/worker/jobs/run?job_type={jt}",
                headers=auth_headers
            )
            assert response.status_code == 200, f"Job type {jt} failed"

    def test_run_all_jobs(self, auth_headers):
        """POST /worker/jobs/run-all triggers all scheduled jobs."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs/run-all",
            headers=auth_headers
        )
        # May return 502 if reservation_import fails (external dependency)
        assert response.status_code in [200, 502]
        
        if response.status_code == 200:
            data = response.json()
            # Should return results for each job type
            assert isinstance(data, dict)

    def test_list_worker_jobs(self, auth_headers):
        """GET /worker/jobs lists job history."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "jobs" in data
        assert "count" in data
        assert isinstance(data["jobs"], list)

    def test_list_jobs_with_filters(self, auth_headers):
        """GET /worker/jobs supports filtering."""
        # Filter by job_type
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs?job_type=reservation_import&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Filter by status
        response2 = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs?status=completed&limit=10",
            headers=auth_headers
        )
        assert response2.status_code == 200

    def test_get_worker_stats(self, auth_headers):
        """GET /worker/stats returns job statistics."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/worker/stats",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Should contain stats per job type
        assert isinstance(data, dict)
        assert "stats" in data or "intervals" in data

    def test_worker_requires_auth(self):
        """Worker endpoints require authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/worker/jobs"
        )
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden


# ══════════════════════════════════════════════════════════════════
# Cleanup
# ══════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_channels(auth_headers):
    """Clean up TEST_ prefixed channels after all tests."""
    yield
    # Cleanup: delete channels starting with TEST_
    try:
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/delivery/channels",
            headers=auth_headers
        )
        if response.status_code == 200:
            channels = response.json().get("channels", [])
            for ch in channels:
                if ch.get("name", "").startswith("TEST_"):
                    requests.delete(
                        f"{BASE_URL}/api/channel-manager/v2/delivery/channels/{ch['id']}",
                        headers=auth_headers
                    )
    except Exception:
        pass
