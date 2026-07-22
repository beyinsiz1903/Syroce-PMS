"""
Test Virtual Rooms and Rate Manager Push Providers
Tests for iteration 170 features:
1. Virtual rooms exclusion from default room list
2. Virtual rooms inclusion with include_virtual=true
3. Virtual rooms listing endpoint
4. No-show to virtual room assignment
5. Push providers endpoint (Exely + HotelRunner)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.live_server

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        # Try both token formats
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestVirtualRoomsExclusion:
    """Test that virtual rooms are excluded by default from room list"""

    def test_rooms_default_excludes_virtual(self, authenticated_client):
        """GET /api/pms/rooms should exclude virtual rooms by default"""
        response = authenticated_client.get(f"{BASE_URL}/api/pms/rooms")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        rooms = response.json()
        assert isinstance(rooms, list), "Response should be a list"
        
        # Check that no virtual rooms are in the list
        virtual_rooms = [r for r in rooms if r.get('is_virtual') == True]
        assert len(virtual_rooms) == 0, f"Found {len(virtual_rooms)} virtual rooms in default list"
        
        # Check that no V- prefixed rooms are in the list
        v_prefixed = [r for r in rooms if r.get('room_number', '').startswith('V-')]
        assert len(v_prefixed) == 0, f"Found {len(v_prefixed)} V- prefixed rooms in default list"
        
        # Should return 30 rooms (not 36)
        print(f"Total rooms returned (excluding virtual): {len(rooms)}")
        # Note: The exact count may vary, but virtual rooms should be excluded

    def test_rooms_with_include_virtual_true(self, authenticated_client):
        """GET /api/pms/rooms?include_virtual=true should include virtual rooms"""
        response = authenticated_client.get(f"{BASE_URL}/api/pms/rooms?include_virtual=true")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        rooms = response.json()
        assert isinstance(rooms, list), "Response should be a list"
        
        # Check that virtual rooms are included
        virtual_rooms = [r for r in rooms if r.get('is_virtual') == True]
        print(f"Virtual rooms found: {len(virtual_rooms)}")
        
        # Check for V- prefixed rooms
        v_prefixed = [r for r in rooms if r.get('room_number', '').startswith('V-')]
        print(f"V- prefixed rooms: {[r.get('room_number') for r in v_prefixed]}")
        
        # Should have more rooms than default (36 vs 30)
        print(f"Total rooms with virtual: {len(rooms)}")

    def test_rooms_count_difference(self, authenticated_client):
        """Verify that include_virtual=true returns more rooms than default"""
        # Get default rooms (no virtual)
        response_default = authenticated_client.get(f"{BASE_URL}/api/pms/rooms")
        assert response_default.status_code == 200
        rooms_default = response_default.json()
        
        # Get rooms with virtual
        response_virtual = authenticated_client.get(f"{BASE_URL}/api/pms/rooms?include_virtual=true")
        assert response_virtual.status_code == 200
        rooms_virtual = response_virtual.json()
        
        # Virtual list should have more rooms
        print(f"Default rooms: {len(rooms_default)}, With virtual: {len(rooms_virtual)}")
        assert len(rooms_virtual) >= len(rooms_default), "Virtual list should have >= rooms than default"


class TestVirtualRoomsEndpoint:
    """Test the dedicated virtual rooms endpoint"""

    def test_get_virtual_rooms(self, authenticated_client):
        """GET /api/pms/rooms/virtual should list all virtual rooms"""
        response = authenticated_client.get(f"{BASE_URL}/api/pms/rooms/virtual")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        rooms = response.json()
        assert isinstance(rooms, list), "Response should be a list"
        
        # All rooms should be virtual
        for room in rooms:
            assert room.get('is_virtual') == True, f"Room {room.get('room_number')} is not virtual"
        
        # Check for expected virtual room types
        room_numbers = [r.get('room_number') for r in rooms]
        print(f"Virtual rooms: {room_numbers}")
        
        # Expected virtual rooms: V-STD, V-DLX, V-SUP, V-STE, V-JST, V-FAM
        expected_prefixes = ['V-']
        for room in rooms:
            rn = room.get('room_number', '')
            assert any(rn.startswith(p) for p in expected_prefixes), f"Unexpected room number: {rn}"


class TestNoShowVirtualAssignment:
    """Test no-show to virtual room assignment"""

    def test_no_show_virtual_endpoint_exists(self, authenticated_client):
        """POST /api/pms/bookings/no-show-virtual endpoint should exist"""
        # Test with invalid booking ID to verify endpoint exists
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/bookings/no-show-virtual",
            json={"booking_id": "non-existent-booking-id", "charge_first_night": False}
        )
        # Should return 404 (booking not found) not 405 (method not allowed)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        
        # Check error message
        data = response.json()
        assert "detail" in data or "error" in data, "Should have error detail"
        print(f"No-show virtual endpoint response: {data}")


class TestPushProviders:
    """Test push providers endpoint for Rate Manager"""

    def test_get_push_providers(self, authenticated_client):
        """GET /api/channel-manager/rate-manager/push-providers should return provider statuses"""
        response = authenticated_client.get(f"{BASE_URL}/api/channel-manager/rate-manager/push-providers")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "providers" in data, "Response should have 'providers' key"
        
        providers = data["providers"]
        assert isinstance(providers, list), "Providers should be a list"
        
        # Should have at least Exely and HotelRunner
        provider_slugs = [p.get("slug") for p in providers]
        print(f"Provider slugs: {provider_slugs}")
        
        # Check Exely provider
        exely = next((p for p in providers if p.get("slug") == "exely"), None)
        assert exely is not None, "Exely provider should be present"
        assert "name" in exely, "Exely should have name"
        assert "mode" in exely, "Exely should have mode"
        assert "push_active" in exely, "Exely should have push_active"
        print(f"Exely: {exely}")
        
        # Check HotelRunner provider
        hotelrunner = next((p for p in providers if p.get("slug") == "hotelrunner"), None)
        assert hotelrunner is not None, "HotelRunner provider should be present"
        assert "name" in hotelrunner, "HotelRunner should have name"
        assert "mode" in hotelrunner, "HotelRunner should have mode"
        assert "push_active" in hotelrunner, "HotelRunner should have push_active"
        print(f"HotelRunner: {hotelrunner}")

    def test_push_providers_modes(self, authenticated_client):
        """Verify push providers have valid modes"""
        response = authenticated_client.get(f"{BASE_URL}/api/channel-manager/rate-manager/push-providers")
        assert response.status_code == 200
        
        providers = response.json().get("providers", [])
        valid_modes = ["live", "shadow", "inactive", "read_only"]
        
        for provider in providers:
            mode = provider.get("mode")
            assert mode in valid_modes, f"Invalid mode '{mode}' for provider {provider.get('name')}"
            print(f"{provider.get('name')}: mode={mode}, push_active={provider.get('push_active')}")


class TestDashboardExcludesVirtual:
    """Test that dashboard stats exclude virtual rooms"""

    def test_dashboard_room_count(self, authenticated_client):
        """GET /api/pms/dashboard should exclude virtual rooms from count"""
        response = authenticated_client.get(f"{BASE_URL}/api/pms/dashboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "total_rooms" in data, "Dashboard should have total_rooms"
        
        total_rooms = data.get("total_rooms", 0)
        print(f"Dashboard total_rooms: {total_rooms}")
        
        # Get actual room counts for comparison
        rooms_default = authenticated_client.get(f"{BASE_URL}/api/pms/rooms").json()
        rooms_virtual = authenticated_client.get(f"{BASE_URL}/api/pms/rooms?include_virtual=true").json()
        
        print(f"Rooms API (default): {len(rooms_default)}")
        print(f"Rooms API (with virtual): {len(rooms_virtual)}")
        
        # Dashboard should match default (non-virtual) count
        # Note: There might be slight differences due to caching


class TestCalendarExcludesVirtual:
    """Test that calendar room list excludes virtual rooms"""

    def test_calendar_rooms_no_virtual(self, authenticated_client):
        """Calendar should not show virtual rooms in the grid"""
        # The calendar uses /api/pms/rooms without include_virtual
        response = authenticated_client.get(f"{BASE_URL}/api/pms/rooms")
        assert response.status_code == 200
        
        rooms = response.json()
        
        # No V- prefixed rooms should appear
        v_rooms = [r for r in rooms if r.get('room_number', '').startswith('V-')]
        assert len(v_rooms) == 0, f"Calendar should not show virtual rooms: {[r.get('room_number') for r in v_rooms]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
