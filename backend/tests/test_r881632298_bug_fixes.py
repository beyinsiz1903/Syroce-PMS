"""
Test R881632298 Bug Fixes - Multi-room reservation handling
============================================================
Tests for:
1. R881632298 bookings have correct status (R881632298 confirmed, R881632298-1 cancelled, R881632298-2 to R881632298-6 confirmed)
2. All bookings have room_type_id field set correctly (Suite, Standard, Deluxe)
3. Guest name is 'murat sutay' for all R881632298 bookings (name change synced)
4. /api/bookings endpoint returns room_type_id field for OTA bookings
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://agency-portal-77.preview.emergentagent.com')


class TestR881632298BugFixes:
    """Test R881632298 multi-room reservation bug fixes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_r881632298_bookings_exist(self):
        """Verify R881632298 bookings are returned by API"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200, f"API failed: {resp.text}"
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        # Filter R881632298 bookings
        r88_bookings = [b for b in bookings if b.get("external_reservation_id", "").startswith("R881632298")]
        
        # Should have 7 bookings (R881632298, R881632298-1 through R881632298-6)
        assert len(r88_bookings) == 7, f"Expected 7 R881632298 bookings, got {len(r88_bookings)}"
    
    def test_r881632298_status_correct(self):
        """Verify R881632298 confirmed, R881632298-1 cancelled, rest confirmed"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        # Build lookup by external_reservation_id
        booking_map = {b.get("external_reservation_id"): b for b in bookings}
        
        # R881632298 should be confirmed
        assert "R881632298" in booking_map, "R881632298 not found"
        assert booking_map["R881632298"]["status"] == "confirmed", f"R881632298 should be confirmed, got {booking_map['R881632298']['status']}"
        
        # R881632298-1 should be cancelled
        assert "R881632298-1" in booking_map, "R881632298-1 not found"
        assert booking_map["R881632298-1"]["status"] == "cancelled", f"R881632298-1 should be cancelled, got {booking_map['R881632298-1']['status']}"
        
        # R881632298-2 through R881632298-6 should be confirmed
        for i in range(2, 7):
            ext_id = f"R881632298-{i}"
            assert ext_id in booking_map, f"{ext_id} not found"
            assert booking_map[ext_id]["status"] == "confirmed", f"{ext_id} should be confirmed, got {booking_map[ext_id]['status']}"
    
    def test_r881632298_room_type_id_set(self):
        """Verify all R881632298 bookings have room_type_id field set"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        r88_bookings = [b for b in bookings if b.get("external_reservation_id", "").startswith("R881632298")]
        
        for b in r88_bookings:
            ext_id = b.get("external_reservation_id")
            room_type_id = b.get("room_type_id")
            assert room_type_id, f"{ext_id} missing room_type_id"
            assert room_type_id in ["Suite", "Standard", "Deluxe"], f"{ext_id} has invalid room_type_id: {room_type_id}"
    
    def test_r881632298_guest_name_synced(self):
        """Verify guest_name is 'murat sutay' for all R881632298 bookings (name change synced)"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        r88_bookings = [b for b in bookings if b.get("external_reservation_id", "").startswith("R881632298")]
        
        for b in r88_bookings:
            ext_id = b.get("external_reservation_id")
            guest_name = b.get("guest_name", "").lower()
            assert guest_name == "murat sutay", f"{ext_id} has wrong guest_name: {guest_name}, expected 'murat sutay'"
    
    def test_r881632298_room_type_mapping(self):
        """Verify room_type_id mapping is correct for each sub-reservation"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        booking_map = {b.get("external_reservation_id"): b for b in bookings}
        
        # Expected room types based on the bug report
        expected_types = {
            "R881632298": "Suite",
            "R881632298-1": "Suite",
            "R881632298-2": "Standard",
            "R881632298-3": "Standard",
            "R881632298-4": "Standard",
            "R881632298-5": "Deluxe",
            "R881632298-6": "Deluxe",
        }
        
        for ext_id, expected_type in expected_types.items():
            assert ext_id in booking_map, f"{ext_id} not found"
            actual_type = booking_map[ext_id].get("room_type_id")
            assert actual_type == expected_type, f"{ext_id} has room_type_id={actual_type}, expected {expected_type}"


class TestBookingsAPIRoomTypeId:
    """Test that /api/bookings returns room_type_id for OTA bookings"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_bookings_api_returns_room_type_id(self):
        """Verify /api/pms/bookings returns room_type_id field"""
        resp = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50, "start_date": "2026-04-01", "end_date": "2026-04-15"},
            headers=self.headers,
            timeout=30
        )
        assert resp.status_code == 200
        
        data = resp.json()
        bookings = data if isinstance(data, list) else data.get("bookings", [])
        
        # Check that at least some bookings have room_type_id
        bookings_with_room_type_id = [b for b in bookings if b.get("room_type_id")]
        assert len(bookings_with_room_type_id) > 0, "No bookings have room_type_id field"
        
        # Verify room_type_id values are valid
        valid_types = ["Suite", "Standard", "Deluxe"]
        for b in bookings_with_room_type_id:
            room_type_id = b.get("room_type_id")
            assert room_type_id in valid_types, f"Invalid room_type_id: {room_type_id}"
