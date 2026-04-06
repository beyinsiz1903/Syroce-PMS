"""
Channel Connections API Tests
=============================
Tests for the new Channel Connections Overview endpoint that provides
unified view of all channel providers (HotelRunner, Exely).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestChannelConnectionsOverview:
    """Tests for GET /api/channel-manager/connections/overview endpoint."""
    
    def test_overview_endpoint_returns_200(self, auth_headers):
        """Test that overview endpoint returns 200 OK."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_overview_returns_tenant_id(self, auth_headers):
        """Test that response includes tenant_id."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert isinstance(data["tenant_id"], str)
        assert len(data["tenant_id"]) > 0
    
    def test_overview_returns_providers_array(self, auth_headers):
        """Test that response includes providers array."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) == 2  # HotelRunner and Exely
    
    def test_overview_hotelrunner_provider_structure(self, auth_headers):
        """Test HotelRunner provider data structure."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find HotelRunner provider
        hr_provider = next((p for p in data["providers"] if p["provider"] == "hotelrunner"), None)
        assert hr_provider is not None, "HotelRunner provider not found"
        
        # Check required fields
        assert hr_provider["display_name"] == "HotelRunner"
        assert "connected" in hr_provider
        assert isinstance(hr_provider["connected"], bool)
        assert "property_name" in hr_provider
        assert "hr_id" in hr_provider
        assert "environment" in hr_provider
        assert "channels" in hr_provider
        assert isinstance(hr_provider["channels"], list)
        assert "room_mappings_count" in hr_provider
        assert isinstance(hr_provider["room_mappings_count"], int)
        assert "auto_sync_reservations" in hr_provider
    
    def test_overview_exely_provider_structure(self, auth_headers):
        """Test Exely provider data structure."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find Exely provider
        exely_provider = next((p for p in data["providers"] if p["provider"] == "exely"), None)
        assert exely_provider is not None, "Exely provider not found"
        
        # Check required fields
        assert exely_provider["display_name"] == "Exely"
        assert "connected" in exely_provider
        assert isinstance(exely_provider["connected"], bool)
        assert "property_name" in exely_provider
        assert "hotel_code" in exely_provider
        assert "currency" in exely_provider
        assert "room_types" in exely_provider
        assert isinstance(exely_provider["room_types"], list)
        assert "rate_plans" in exely_provider
        assert isinstance(exely_provider["rate_plans"], list)
        assert "room_mappings_count" in exely_provider
        assert isinstance(exely_provider["room_mappings_count"], int)
        assert "auto_sync_reservations" in exely_provider
    
    def test_overview_returns_pms_room_types(self, auth_headers):
        """Test that response includes PMS room types."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "pms_room_types" in data
        assert isinstance(data["pms_room_types"], list)
    
    def test_overview_returns_checked_at_timestamp(self, auth_headers):
        """Test that response includes checked_at timestamp."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "checked_at" in data
        assert isinstance(data["checked_at"], str)
        # Should be ISO format
        assert "T" in data["checked_at"]
    
    def test_overview_requires_authentication(self):
        """Test that endpoint requires authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_overview_hotelrunner_connected_status(self, auth_headers):
        """Test that HotelRunner shows connected status for demo tenant."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        hr_provider = next((p for p in data["providers"] if p["provider"] == "hotelrunner"), None)
        assert hr_provider is not None
        
        # Demo tenant should have HotelRunner connected
        assert hr_provider["connected"] == True, "HotelRunner should be connected for demo tenant"
        assert hr_provider["property_name"] != "", "Property name should not be empty"
        assert hr_provider["hr_id"] != "", "HR ID should not be empty"
        assert hr_provider["room_mappings_count"] >= 0
    
    def test_overview_exely_connected_status(self, auth_headers):
        """Test that Exely shows connected status for demo tenant."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connections/overview",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        exely_provider = next((p for p in data["providers"] if p["provider"] == "exely"), None)
        assert exely_provider is not None
        
        # Demo tenant should have Exely connected
        assert exely_provider["connected"] == True, "Exely should be connected for demo tenant"
        assert exely_provider["property_name"] != "", "Property name should not be empty"
        assert exely_provider["hotel_code"] != "", "Hotel code should not be empty"
        assert exely_provider["room_mappings_count"] >= 0


class TestHotelRunnerTestConnection:
    """Tests for HotelRunner test connection endpoint."""
    
    def test_hotelrunner_test_endpoint(self, auth_headers):
        """Test HotelRunner test connection endpoint."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/test",
            headers=auth_headers,
            json={}
        )
        # Should return 200 with success/connected status
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Check for success or connected field
        assert "success" in data or "connected" in data


class TestExelyTestConnection:
    """Tests for Exely test connection endpoint."""
    
    def test_exely_test_endpoint(self, auth_headers):
        """Test Exely test connection endpoint."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/test",
            headers=auth_headers,
            json={}
        )
        # Should return 200 with success/connected status
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Check for success or connected field
        assert "success" in data or "connected" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
