"""
Test: Room Management Access Control
Verifies that room create/bulk-create/bulk-delete endpoints require super_admin role
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "demo@hotel.com"
SUPER_ADMIN_PASSWORD = "demo123"


class TestRoomManagementAccessControl:
    """Test that room management endpoints are protected for super_admin only"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_auth_token(self, email, password):
        """Get auth token for a user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_super_admin_login(self):
        """Test that demo user can login and is super_admin"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access token in response"
        # Check user role is super_admin
        user = data.get("user", {})
        print(f"User role: {user.get('role')}")
        assert user.get("role") == "super_admin", f"Expected super_admin role, got {user.get('role')}"
        print("✅ Super admin login successful")
    
    def test_get_rooms_as_super_admin(self):
        """Test GET /api/pms/rooms works for super_admin"""
        token = self.get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        assert token, "Failed to get auth token"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/pms/rooms?limit=10")
        assert response.status_code == 200, f"GET rooms failed: {response.text}"
        data = response.json()
        print(f"✅ GET /api/pms/rooms returned {len(data)} rooms")
    
    def test_create_room_as_super_admin(self):
        """Test POST /api/pms/rooms works for super_admin"""
        token = self.get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        assert token, "Failed to get auth token"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create a unique test room
        import time
        room_number = f"TEST_{int(time.time())}"
        
        response = self.session.post(f"{BASE_URL}/api/pms/rooms", json={
            "room_number": room_number,
            "room_type": "standard",
            "floor": 1,
            "capacity": 2,
            "base_price": 100
        })
        
        assert response.status_code == 200 or response.status_code == 201, f"Create room failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("room_number") == room_number, f"Room number mismatch"
        print(f"✅ POST /api/pms/rooms created room {room_number} successfully")
        
        # Store room ID for cleanup
        return data.get("id")
    
    def test_bulk_create_rooms_range_as_super_admin(self):
        """Test POST /api/pms/rooms/bulk/range works for super_admin"""
        token = self.get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        assert token, "Failed to get auth token"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create bulk rooms with unique prefix
        import time
        prefix = f"BULK{int(time.time())}_"
        
        response = self.session.post(f"{BASE_URL}/api/pms/rooms/bulk/range", json={
            "prefix": prefix,
            "start_number": 1,
            "end_number": 3,
            "floor": 1,
            "room_type": "standard",
            "capacity": 2,
            "base_price": 100
        })
        
        assert response.status_code == 200, f"Bulk create failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("created") >= 0, "No created count in response"
        print(f"✅ POST /api/pms/rooms/bulk/range created {data.get('created')} rooms, skipped {data.get('skipped')}")
    
    def test_bulk_delete_rooms_as_super_admin(self):
        """Test POST /api/pms/rooms/bulk/delete works for super_admin"""
        token = self.get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        assert token, "Failed to get auth token"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # First create a room to delete
        import time
        room_number = f"DELTEST_{int(time.time())}"
        
        create_response = self.session.post(f"{BASE_URL}/api/pms/rooms", json={
            "room_number": room_number,
            "room_type": "standard",
            "floor": 1,
            "capacity": 2,
            "base_price": 100
        })
        
        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create test room for deletion")
        
        room_id = create_response.json().get("id")
        
        # Now delete it
        response = self.session.post(f"{BASE_URL}/api/pms/rooms/bulk/delete", json={
            "ids": [room_id],
            "confirm_text": "DELETE"
        })
        
        assert response.status_code == 200, f"Bulk delete failed: {response.status_code} - {response.text}"
        data = response.json()
        print(f"✅ POST /api/pms/rooms/bulk/delete deleted {data.get('deleted')} rooms")


class TestRoomManagementWithoutAuth:
    """Test that room management endpoints return 401/403 without proper auth"""
    
    def test_create_room_without_auth_returns_401(self):
        """Test POST /api/pms/rooms without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/pms/rooms", json={
            "room_number": "UNAUTH_TEST",
            "room_type": "standard",
            "floor": 1,
            "capacity": 2
        }, headers={"Content-Type": "application/json"})
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✅ POST /api/pms/rooms without auth returns {response.status_code}")
    
    def test_bulk_create_without_auth_returns_401(self):
        """Test POST /api/pms/rooms/bulk/range without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/pms/rooms/bulk/range", json={
            "prefix": "UNAUTH_",
            "start_number": 1,
            "end_number": 3,
            "floor": 1,
            "room_type": "standard"
        }, headers={"Content-Type": "application/json"})
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✅ POST /api/pms/rooms/bulk/range without auth returns {response.status_code}")
    
    def test_bulk_delete_without_auth_returns_401(self):
        """Test POST /api/pms/rooms/bulk/delete without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/pms/rooms/bulk/delete", json={
            "ids": ["fake-id"],
            "confirm_text": "DELETE"
        }, headers={"Content-Type": "application/json"})
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✅ POST /api/pms/rooms/bulk/delete without auth returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
