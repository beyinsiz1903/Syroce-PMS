"""
Test Decision-Driven PMS Features API
Tests for:
- Dashboard Command Center: /api/pms/operational-alerts
- Room alternatives: /api/pms/room-alternatives/{room_number}
- Login flow with demo credentials
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://drift-detection-mock.preview.emergentagent.com')


class TestLogin:
    """Test login flow with demo credentials"""
    
    def test_login_with_demo_credentials(self):
        """Test login with demo@hotel.com / demo123"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert data.get("user", {}).get("email") == "demo@hotel.com"
        print(f"Login successful, user role: {data.get('user', {}).get('role')}")
        return data["access_token"]


class TestOperationalAlerts:
    """Test /api/pms/operational-alerts endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Login failed - skipping authenticated tests")
    
    def test_operational_alerts_endpoint_exists(self, auth_token):
        """Test that operational-alerts endpoint returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Operational alerts endpoint accessible")
    
    def test_operational_alerts_returns_alerts_array(self, auth_token):
        """Test that response contains alerts array"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data, "Response missing 'alerts' field"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        print(f"Alerts count: {len(data['alerts'])}")
    
    def test_operational_alerts_returns_summary(self, auth_token):
        """Test that response contains summary stats"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data, "Response missing 'summary' field"
        summary = data["summary"]
        # Check required summary fields
        assert "arrivals_today" in summary, "Summary missing arrivals_today"
        assert "departures_today" in summary, "Summary missing departures_today"
        assert "inhouse" in summary, "Summary missing inhouse"
        assert "dirty_rooms" in summary, "Summary missing dirty_rooms"
        print(f"Summary: arrivals={summary['arrivals_today']}, departures={summary['departures_today']}, inhouse={summary['inhouse']}, dirty={summary['dirty_rooms']}")
    
    def test_operational_alerts_returns_available_clean_rooms(self, auth_token):
        """Test that response contains available_clean_rooms"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "available_clean_rooms" in data, "Response missing 'available_clean_rooms' field"
        assert isinstance(data["available_clean_rooms"], list), "available_clean_rooms should be a list"
        print(f"Available clean rooms count: {len(data['available_clean_rooms'])}")
    
    def test_operational_alerts_alert_structure(self, auth_token):
        """Test alert structure if alerts exist"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=headers)
        assert response.status_code == 200
        data = response.json()
        alerts = data.get("alerts", [])
        if alerts:
            alert = alerts[0]
            # Check alert structure
            assert "type" in alert, "Alert missing 'type'"
            assert "severity" in alert, "Alert missing 'severity'"
            assert "title" in alert, "Alert missing 'title'"
            assert "description" in alert, "Alert missing 'description'"
            assert "action" in alert, "Alert missing 'action'"
            assert "action_label" in alert, "Alert missing 'action_label'"
            print(f"First alert: type={alert['type']}, severity={alert['severity']}, title={alert['title']}")
        else:
            print("No alerts present - all operations are running smoothly")


class TestRoomAlternatives:
    """Test /api/pms/room-alternatives/{room_number} endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Login failed - skipping authenticated tests")
    
    def test_room_alternatives_endpoint_exists(self, auth_token):
        """Test that room-alternatives endpoint returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # Use a common room number
        response = requests.get(f"{BASE_URL}/api/pms/room-alternatives/101", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Room alternatives endpoint accessible")
    
    def test_room_alternatives_returns_structure(self, auth_token):
        """Test that response contains expected structure"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/room-alternatives/101", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Check structure - may have alternatives or empty if room doesn't exist
        if "alternatives" in data:
            assert isinstance(data["alternatives"], list)
            print(f"Alternatives (simple): {len(data['alternatives'])}")
        else:
            # New structure with same_type and other_type
            assert "same_type" in data or "target_room_type" in data, "Response missing expected fields"
            if "same_type" in data:
                assert isinstance(data["same_type"], list)
                print(f"Same type alternatives: {len(data['same_type'])}")
            if "other_type" in data:
                assert isinstance(data["other_type"], list)
                print(f"Other type alternatives: {len(data['other_type'])}")


class TestPMSDashboard:
    """Test /api/pms/dashboard endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Login failed - skipping authenticated tests")
    
    def test_pms_dashboard_endpoint(self, auth_token):
        """Test PMS dashboard returns stats"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/dashboard", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_rooms" in data, "Missing total_rooms"
        assert "occupancy_rate" in data, "Missing occupancy_rate"
        print(f"Dashboard: total_rooms={data.get('total_rooms')}, occupancy={data.get('occupancy_rate')}%")


class TestFrontDeskData:
    """Test front desk related endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Login failed - skipping authenticated tests")
    
    def test_get_rooms(self, auth_token):
        """Test getting rooms list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Rooms should be a list"
        if data:
            room = data[0]
            assert "room_number" in room, "Room missing room_number"
            assert "status" in room, "Room missing status"
            # Check for dirty rooms
            dirty_count = sum(1 for r in data if r.get("status") in ["dirty", "cleaning"])
            print(f"Total rooms: {len(data)}, Dirty/Cleaning: {dirty_count}")
    
    def test_get_bookings(self, auth_token):
        """Test getting bookings list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/bookings", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Response can be list or dict with bookings key
        if isinstance(data, dict):
            bookings = data.get("bookings", [])
        else:
            bookings = data
        print(f"Bookings count: {len(bookings)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
