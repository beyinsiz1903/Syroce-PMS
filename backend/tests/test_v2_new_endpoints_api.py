"""
API Tests for new V2 endpoints:
- Mapping Completeness (GET /api/channel-manager/v2/mapping-completeness/{connector_id})
- Rate Push Metrics (GET /api/channel-manager/v2/rate-push-metrics/{connector_id})
- Health Trend Analytics (GET /api/channel-manager/v2/health-trend/{connector_id}/daily|weekly|summary)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def api_session():
    """Create a requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_session):
    """Get authentication token"""
    response = api_session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    # The API returns 'access_token' not 'token'
    token = data.get("access_token") or data.get("token")
    assert token, "No token in response"
    return token


@pytest.fixture(scope="module")
def authenticated_session(api_session, auth_token):
    """Session with auth header"""
    api_session.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_session


@pytest.fixture(scope="module")
def connector_id(authenticated_session):
    """Get a valid connector ID for testing"""
    response = authenticated_session.get(f"{BASE_URL}/api/channel-manager/v2/connectors")
    assert response.status_code == 200, f"Failed to get connectors: {response.text}"
    data = response.json()
    connectors = data.get("connectors", data) if isinstance(data, dict) else data
    assert len(connectors) > 0, "No connectors available for testing"
    return connectors[0]["id"]


# ─── Mapping Completeness Tests ─────────────────────────────────────────────

class TestMappingCompletenessAPI:
    """Tests for mapping completeness endpoints"""

    def test_get_mapping_completeness_report(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/mapping-completeness/{connector_id} returns validation report"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-completeness/{connector_id}"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Data assertions
        assert "readiness_score" in data, "Missing readiness_score"
        assert "sync_allowed" in data, "Missing sync_allowed"
        assert "import_allowed" in data, "Missing import_allowed"
        assert "checks" in data, "Missing checks"
        assert isinstance(data["readiness_score"], (int, float))
        assert isinstance(data["sync_allowed"], bool)
        assert isinstance(data["import_allowed"], bool)
        print(f"Mapping completeness - readiness_score: {data['readiness_score']}, sync_allowed: {data['sync_allowed']}")

    def test_get_sync_gate_status(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/mapping-completeness/{connector_id}/sync-gate returns gate status"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-completeness/{connector_id}/sync-gate"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "allowed" in data, "Missing allowed field"
        assert isinstance(data["allowed"], bool)
        print(f"Sync gate allowed: {data['allowed']}")

    def test_get_import_gate_status(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/mapping-completeness/{connector_id}/import-gate returns gate status"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-completeness/{connector_id}/import-gate"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "allowed" in data, "Missing allowed field"
        assert isinstance(data["allowed"], bool)
        print(f"Import gate allowed: {data['allowed']}")

    def test_mapping_completeness_invalid_connector(self, authenticated_session):
        """GET /api/channel-manager/v2/mapping-completeness/invalid-id handles not found"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-completeness/nonexistent-connector-xyz"
        )
        # Should still return 200 with default values or 404
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"

    def test_mapping_completeness_without_auth(self, api_session):
        """Mapping completeness endpoints require authentication"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-completeness/test-connector"
        )
        assert response.status_code in [401, 403], "Should require auth"


# ─── Rate Push Metrics Tests ─────────────────────────────────────────────────

class TestRatePushMetricsAPI:
    """Tests for rate push tracking endpoints"""

    def test_get_rate_push_metrics(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/rate-push-metrics/{connector_id} returns metrics"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/rate-push-metrics/{connector_id}"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Data assertions for expected fields
        expected_fields = [
            "rate_push_success_rate", "rate_push_failure_rate", 
            "rate_push_retry_count", "avg_latency_ms",
            "total_pushes", "success_count", "failure_count"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        # Type assertions
        assert isinstance(data["rate_push_success_rate"], (int, float))
        assert isinstance(data["rate_push_failure_rate"], (int, float))
        assert isinstance(data["total_pushes"], int)
        print(f"Rate push - success_rate: {data['rate_push_success_rate']}%, total_pushes: {data['total_pushes']}")

    def test_rate_push_metrics_with_days_param(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/rate-push-metrics/{connector_id}?days=30 works"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/rate-push-metrics/{connector_id}?days=30"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "rate_push_success_rate" in data

    def test_rate_push_metrics_without_auth(self, api_session):
        """Rate push metrics require authentication"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.get(
            f"{BASE_URL}/api/channel-manager/v2/rate-push-metrics/test-connector"
        )
        assert response.status_code in [401, 403], "Should require auth"


# ─── Health Trend Analytics Tests ─────────────────────────────────────────────

class TestHealthTrendAPI:
    """Tests for health trend analytics endpoints"""

    def test_get_daily_health_trend(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/health-trend/{connector_id}/daily returns daily trend"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/{connector_id}/daily"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should be a list (can be empty if no historical data)
        assert isinstance(data, list), "Daily trend should be a list"
        print(f"Daily trend records: {len(data)}")

    def test_get_daily_health_trend_with_days(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/health-trend/{connector_id}/daily?days=7 works"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/{connector_id}/daily?days=7"
        )
        assert response.status_code == 200, f"Failed: {response.text}"

    def test_get_weekly_health_trend(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/health-trend/{connector_id}/weekly returns weekly trend"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/{connector_id}/weekly"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Weekly trend should be a list"
        print(f"Weekly trend records: {len(data)}")

    def test_get_weekly_health_trend_with_weeks(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/health-trend/{connector_id}/weekly?weeks=4 works"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/{connector_id}/weekly?weeks=4"
        )
        assert response.status_code == 200, f"Failed: {response.text}"

    def test_get_health_trend_summary(self, authenticated_session, connector_id):
        """GET /api/channel-manager/v2/health-trend/{connector_id}/summary returns trend summary"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/{connector_id}/summary"
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Data assertions
        assert "health_score" in data, "Missing health_score"
        assert isinstance(data["health_score"], dict), "health_score should be dict"
        
        # Health score should have current, previous, delta, trend
        hs = data["health_score"]
        for field in ["current", "previous", "delta", "trend"]:
            assert field in hs, f"Missing {field} in health_score"
        
        print(f"Trend summary - health_score: {hs['current']}, delta: {hs['delta']}, trend: {hs['trend']}")

    def test_health_trend_without_auth(self, api_session):
        """Health trend endpoints require authentication"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        response = session.get(
            f"{BASE_URL}/api/channel-manager/v2/health-trend/test-connector/summary"
        )
        assert response.status_code in [401, 403], "Should require auth"


# ─── Connector Endpoint Test ─────────────────────────────────────────────────

class TestConnectorEndpoint:
    """Tests to verify connectors exist for testing"""

    def test_list_connectors(self, authenticated_session):
        """GET /api/channel-manager/v2/connectors returns list"""
        response = authenticated_session.get(f"{BASE_URL}/api/channel-manager/v2/connectors")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        connectors = data.get("connectors", data) if isinstance(data, dict) else data
        assert isinstance(connectors, list)
        print(f"Available connectors: {len(connectors)}")
        for c in connectors[:3]:
            print(f"  - {c.get('id', 'N/A')}: {c.get('display_name', c.get('name', 'N/A'))}")
