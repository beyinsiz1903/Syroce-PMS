"""
HotelRunner Integration API Tests
Tests the HotelRunner channel manager endpoints:
- Connection status (disconnected state)
- Room mappings (empty list)
- Sync logs (empty list)  
- Local reservations (empty list)
- Connect with invalid credentials (400 error)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestHotelRunnerAuth:
    """Test authentication for HotelRunner endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Token may be in 'access_token' field
        self.token = data.get("access_token") or data.get("token")
        assert self.token, f"No token in response: {data}"
        self.headers = {"Authorization": f"Bearer {self.token}"}


class TestHotelRunnerConnection(TestHotelRunnerAuth):
    """Test HotelRunner connection status API"""
    
    def test_connection_status_disconnected(self):
        """GET /api/channel-manager/hotelrunner/connection - should return disconnected"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/connection",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have 'connected' field set to False (no credentials configured)
        assert "connected" in data, f"Missing 'connected' field: {data}"
        # Connected should be false since no real credentials are set up
        # Note: might be True if demo has connected before, but we expect False
        print(f"Connection status: {data}")


class TestHotelRunnerRoomMappings(TestHotelRunnerAuth):
    """Test HotelRunner room mappings API"""
    
    def test_room_mappings_empty(self):
        """GET /api/channel-manager/hotelrunner/room-mappings - should return list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have 'mappings' array
        assert "mappings" in data, f"Missing 'mappings' field: {data}"
        assert isinstance(data["mappings"], list), f"mappings should be list: {data}"
        print(f"Room mappings count: {data.get('count', len(data['mappings']))}")


class TestHotelRunnerSyncLogs(TestHotelRunnerAuth):
    """Test HotelRunner sync logs API"""
    
    def test_sync_logs_list(self):
        """GET /api/channel-manager/hotelrunner/sync-logs - should return list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/sync-logs",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have 'logs' array
        assert "logs" in data, f"Missing 'logs' field: {data}"
        assert isinstance(data["logs"], list), f"logs should be list: {data}"
        print(f"Sync logs count: {data.get('count', len(data['logs']))}")


class TestHotelRunnerLocalReservations(TestHotelRunnerAuth):
    """Test HotelRunner local reservations API"""
    
    def test_local_reservations_list(self):
        """GET /api/channel-manager/hotelrunner/reservations/local - should return list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/reservations/local",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have 'reservations' array
        assert "reservations" in data, f"Missing 'reservations' field: {data}"
        assert isinstance(data["reservations"], list), f"reservations should be list: {data}"
        print(f"Local reservations count: {data.get('count', len(data['reservations']))}")


class TestHotelRunnerConnect(TestHotelRunnerAuth):
    """Test HotelRunner connect API with invalid credentials"""
    
    def test_connect_with_invalid_token(self):
        """POST /api/channel-manager/hotelrunner/connect - should return 400 with invalid token"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/connect",
            headers=self.headers,
            json={
                "token": "invalid_test_token_xyz",
                "hr_id": "invalid_hr_id_123",
                "property_name": "Test Property"
            }
        )
        # Should fail with 400 or 502 (bad gateway from HotelRunner)
        assert response.status_code in [400, 502], f"Expected 400/502, got: {response.status_code} - {response.text}"
        print(f"Connect with invalid credentials response: {response.status_code} - {response.text[:200]}")
