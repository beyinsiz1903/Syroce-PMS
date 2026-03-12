"""
API Tests for Reservation Import Engine endpoints.
Tests the new /api/channel-manager/v2/reservations/* endpoints.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://go-live-ready-6.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code}")


@pytest.fixture
def auth_headers(auth_token):
    """Headers with authentication token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestReservationStatsEndpoint:
    """Test GET /api/channel-manager/v2/reservations/stats"""

    def test_stats_endpoint_returns_200(self, auth_headers):
        """Stats endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/stats",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_stats_has_required_fields(self, auth_headers):
        """Stats should have all required fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/stats",
            headers=auth_headers
        )
        data = response.json()
        
        # Verify structure
        assert "total_reservations" in data
        assert "by_status" in data
        assert "by_ack_status" in data
        assert "review_queue_count" in data
        assert "ack_failed_count" in data
        assert "recent_batches" in data
        assert "success_rate" in data
        
        # by_status and by_ack_status should be dicts
        assert isinstance(data["by_status"], dict)
        assert isinstance(data["by_ack_status"], dict)
        # recent_batches should be a list
        assert isinstance(data["recent_batches"], list)


class TestImportedReservationsEndpoint:
    """Test GET /api/channel-manager/v2/reservations/imported"""

    def test_imported_endpoint_returns_200(self, auth_headers):
        """Imported reservations endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/imported",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_imported_returns_list_structure(self, auth_headers):
        """Should return reservations list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/imported",
            headers=auth_headers
        )
        data = response.json()
        assert "reservations" in data
        assert "count" in data
        assert isinstance(data["reservations"], list)


class TestReviewQueueEndpoint:
    """Test GET /api/channel-manager/v2/reservations/review-queue"""

    def test_review_queue_returns_200(self, auth_headers):
        """Review queue endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/review-queue",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_review_queue_returns_list_structure(self, auth_headers):
        """Should return queue list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/review-queue",
            headers=auth_headers
        )
        data = response.json()
        assert "queue" in data
        assert "count" in data
        assert isinstance(data["queue"], list)


class TestBatchesEndpoint:
    """Test GET /api/channel-manager/v2/reservations/batches"""

    def test_batches_returns_200(self, auth_headers):
        """Batches endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/batches",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_batches_returns_list_structure(self, auth_headers):
        """Should return batches list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/batches",
            headers=auth_headers
        )
        data = response.json()
        assert "batches" in data
        assert "count" in data
        assert isinstance(data["batches"], list)


class TestAuditTrailEndpoint:
    """Test GET /api/channel-manager/v2/reservations/audit-trail"""

    def test_audit_trail_returns_200(self, auth_headers):
        """Audit trail endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/audit-trail",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_audit_trail_returns_list_structure(self, auth_headers):
        """Should return audit logs list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reservations/audit-trail",
            headers=auth_headers
        )
        data = response.json()
        assert "audit_logs" in data
        assert "count" in data
        assert isinstance(data["audit_logs"], list)


class TestRetryAcksEndpoint:
    """Test POST /api/channel-manager/v2/reservations/retry-acks"""

    def test_retry_acks_returns_error_without_connector(self, auth_headers):
        """Should return error when no connector_id provided."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reservations/retry-acks",
            headers=auth_headers,
            json={}
        )
        # Expect validation error (422) or bad request (400) when connector_id missing
        assert response.status_code in [400, 422]

    def test_retry_acks_returns_error_for_missing_connector(self, auth_headers):
        """Should return 400 error for non-existent connector."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reservations/retry-acks",
            headers=auth_headers,
            json={"connector_id": "non-existent-connector-12345"}
        )
        # Should return 400 for connector not found
        assert response.status_code == 400


class TestEndpointAuthentication:
    """Test that endpoints require authentication."""

    def test_stats_requires_auth(self):
        """Stats endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/v2/reservations/stats")
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403]

    def test_imported_requires_auth(self):
        """Imported endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/v2/reservations/imported")
        assert response.status_code in [401, 403]

    def test_review_queue_requires_auth(self):
        """Review queue endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/v2/reservations/review-queue")
        assert response.status_code in [401, 403]
