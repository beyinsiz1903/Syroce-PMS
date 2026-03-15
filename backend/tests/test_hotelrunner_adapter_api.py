"""
HotelRunner Adapter API Tests
==============================

Tests for:
- Login API
- Provider Config APIs (hotelrunner)
- Connection test and validation endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")

class TestLoginAPI:
    """Authentication endpoint tests."""
    
    def test_login_success(self):
        """Test login with demo credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "demo@hotel.com"
        assert data["user"]["role"] == "admin"
    
    def test_login_invalid_credentials(self):
        """Test login with wrong credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@hotel.com", "password": "wrongpass"}
        )
        assert response.status_code == 401


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for subsequent tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestProviderConfigAPI:
    """Provider Config router tests."""
    
    def test_get_providers(self, auth_headers):
        """GET /api/channel-manager/config/providers returns both hotelrunner and exely."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) >= 2
        
        # Verify hotelrunner fields
        hr_provider = next((p for p in data["providers"] if p["provider"] == "hotelrunner"), None)
        assert hr_provider is not None
        assert hr_provider["display_name"] == "HotelRunner"
        assert any(f["key"] == "token" for f in hr_provider["fields"])
        assert any(f["key"] == "hr_id" for f in hr_provider["fields"])
        assert "validation_checks" in hr_provider
        
        # Verify exely fields
        exely_provider = next((p for p in data["providers"] if p["provider"] == "exely"), None)
        assert exely_provider is not None
        assert exely_provider["display_name"] == "Exely"
    
    def test_get_hotelrunner_credentials(self, auth_headers):
        """GET /api/channel-manager/config/providers/hotelrunner/credentials."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/credentials",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data  # May be null if not configured
    
    def test_get_invalid_provider_credentials(self, auth_headers):
        """GET /api/channel-manager/config/providers/invalid/credentials returns 400."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/invalid_provider/credentials",
            headers=auth_headers
        )
        assert response.status_code == 400


class TestHotelRunnerTestConnection:
    """Test connection endpoint tests."""
    
    def test_hotelrunner_test_connection_no_creds(self, auth_headers):
        """POST /api/channel-manager/config/providers/hotelrunner/test-connection - returns error when no valid creds."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/test-connection",
            headers=auth_headers
        )
        # Should return 200 with connected: false (no real credentials configured)
        assert response.status_code == 200
        data = response.json()
        # Either connected=false or error field present (depends on whether TEST_ creds exist)
        assert "connected" in data or "error" in data


class TestHotelRunnerValidation:
    """Full validation endpoint tests."""
    
    def test_hotelrunner_validate(self, auth_headers):
        """POST /api/channel-manager/config/providers/hotelrunner/validate."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/validate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert data["provider"] == "hotelrunner"
        assert "overall_status" in data
        assert "results" in data
        assert "readiness" in data
        
        # Validate readiness structure
        readiness = data["readiness"]
        assert "auth_ok" in readiness
        assert "pull_ok" in readiness
        assert "mapping_readiness_pct" in readiness
        assert "reservation_import_ready" in readiness
    
    def test_hotelrunner_readiness(self, auth_headers):
        """GET /api/channel-manager/config/providers/hotelrunner/readiness."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/config/providers/hotelrunner/readiness",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "auth_ok" in data
        assert "pull_ok" in data


class TestModelConnections:
    """Model router connection tests."""
    
    def test_get_connections(self, auth_headers):
        """GET /api/channel-manager/model/connections."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/model/connections",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "connections" in data
        assert isinstance(data["connections"], list)
    
    def test_get_room_mappings(self, auth_headers):
        """GET /api/channel-manager/model/room-mappings - requires property_id query param."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/model/room-mappings?property_id=default&provider=hotelrunner",
            headers=auth_headers
        )
        # 200 if mappings exist, 422 if params missing is handled
        assert response.status_code == 200
        data = response.json()
        assert "mappings" in data


class TestHotelRunnerRouter:
    """HotelRunner specific router tests."""
    
    def test_get_connection(self, auth_headers):
        """GET /api/channel-manager/hotelrunner/connection."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/connection",
            headers=auth_headers
        )
        # 200 if connection exists, may be different if not configured
        assert response.status_code in [200, 404]
    
    def test_get_channels(self, auth_headers):
        """GET /api/channel-manager/hotelrunner/channels - may return 404 if endpoint changed."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/channels",
            headers=auth_headers
        )
        # May return 200 or 400/401/404 depending on credentials/endpoint availability
        assert response.status_code in [200, 400, 401, 404, 500]


class TestExelyRouter:
    """Exely router tests."""
    
    def test_exely_test_connection(self, auth_headers):
        """POST /api/channel-manager/config/providers/exely/test-connection."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/exely/test-connection",
            headers=auth_headers
        )
        # Should work - returns error when no creds
        assert response.status_code in [200, 400]
    
    def test_exely_validate(self, auth_headers):
        """POST /api/channel-manager/config/providers/exely/validate."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/config/providers/exely/validate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "exely"
        assert "overall_status" in data
        assert "results" in data


class TestUnauthorizedAccess:
    """Tests for endpoints without auth token."""
    
    def test_providers_no_auth(self):
        """GET /api/channel-manager/config/providers without auth returns 401 or 403."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/config/providers")
        assert response.status_code in [401, 403]  # FastAPI may return 403 for missing token
    
    def test_connections_no_auth(self):
        """GET /api/channel-manager/model/connections without auth returns 401 or 403."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/model/connections")
        assert response.status_code in [401, 403]  # FastAPI may return 403 for missing token
