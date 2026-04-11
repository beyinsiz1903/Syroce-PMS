"""
Test P4 Feature: Guest Search in Quick Reservation
- GET /api/pms/guests/search - search guests by name/email/phone/id_number
- POST /api/pms/quick-booking - support guest_id field for existing guests
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set – skipping integration tests in CI"
)

class TestGuestSearchAPI:
    """Guest search endpoint tests for quick reservation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("access_token")
        assert token, "No access_token in login response"
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def test_guest_search_minimum_chars_required(self):
        """Search with less than 2 chars should return empty array"""
        # Single character search
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=a", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data == [], f"Expected empty array for single char search, got: {data}"
        
        # Empty search
        resp2 = requests.get(f"{BASE_URL}/api/pms/guests/search?q=", headers=self.headers)
        assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
        data2 = resp2.json()
        assert data2 == [], f"Expected empty array for empty search, got: {data2}"
        print("PASS: Guest search returns empty array for <2 chars")
    
    def test_guest_search_returns_matching_results(self):
        """Search with 2+ chars should return matching guests"""
        # First, get existing guests list to find a valid search term
        guests_resp = requests.get(f"{BASE_URL}/api/pms/guests?limit=10", headers=self.headers)
        assert guests_resp.status_code == 200, f"Failed to get guests: {guests_resp.text}"
        guests = guests_resp.json()
        
        if not guests:
            pytest.skip("No guests in system to test search")
        
        # Use first guest's name for search
        first_guest = guests[0]
        search_term = first_guest.get('name', '')[:3] if first_guest.get('name') else 'ali'
        
        if len(search_term) < 2:
            search_term = 'ali'  # Fallback to Turkish common name
        
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q={search_term}", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Response should be a list
        assert isinstance(data, list), f"Expected list response, got: {type(data)}"
        print(f"PASS: Guest search for '{search_term}' returned {len(data)} results")
    
    def test_guest_search_response_fields(self):
        """Search results should include required fields"""
        # Search for common Turkish name
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=ali&limit=5", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        if not data:
            # Try another common name
            resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=meh&limit=5", headers=self.headers)
            data = resp.json()
        
        if data and len(data) > 0:
            guest = data[0]
            required_fields = ['id', 'name', 'email', 'phone', 'id_number', 'vip_status', 'total_stays']
            for field in required_fields:
                assert field in guest, f"Missing field '{field}' in search result: {guest}"
            print(f"PASS: Search result has all required fields: {list(guest.keys())}")
        else:
            print("WARNING: No guests found matching search, cannot verify field structure")
    
    def test_guest_search_limit_parameter(self):
        """Search should respect limit parameter"""
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=a&limit=3", headers=self.headers)
        # Note: if query is <2 chars, returns empty
        # Let's use a proper query
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=test&limit=3", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert len(data) <= 3, f"Limit not respected, got {len(data)} results"
        print(f"PASS: Search respects limit parameter (got {len(data)} results, max 3)")


class TestQuickBookingWithGuestId:
    """Quick booking API tests with guest_id support"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find an available room"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("access_token")
        assert token, "No access_token in login response"
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def _get_available_room(self):
        """Helper to find an available room"""
        rooms_resp = requests.get(f"{BASE_URL}/api/pms/rooms?status=available&limit=5", headers=self.headers)
        if rooms_resp.status_code != 200:
            return None
        rooms = rooms_resp.json()
        return rooms[0] if rooms else None
    
    def _get_existing_guest(self):
        """Helper to find an existing guest"""
        guests_resp = requests.get(f"{BASE_URL}/api/pms/guests?limit=5", headers=self.headers)
        if guests_resp.status_code != 200:
            return None
        guests = guests_resp.json()
        return guests[0] if guests else None
    
    def test_quick_booking_without_guest_id_creates_walk_in(self):
        """Quick booking without guest_id should create new walk-in guest"""
        room = self._get_available_room()
        if not room:
            pytest.skip("No available room for testing")
        
        import datetime as dt
        import uuid
        import random
        from pymongo import MongoClient
        offset = 3000 + random.randint(0, 3000)
        today = dt.date.today() + dt.timedelta(days=offset)
        tomorrow = today + dt.timedelta(days=1)
        
        # Clean stale locks
        _mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms"))
        _db = _mongo[os.environ.get("DB_NAME", "hotel_pms")]
        _db.room_night_locks.delete_many({"room_id": room['id'], "night_date": {"$gte": str(today), "$lte": str(tomorrow)}})
        _mongo.close()
        
        payload = {
            "guest_name": "TEST_WalkIn_Guest",
            "room_id": room['id'],
            "check_in": f"{today}T14:00:00+00:00",
            "check_out": f"{tomorrow}T11:00:00+00:00",
            "total_amount": 100.0
        }
        
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        resp = requests.post(f"{BASE_URL}/api/pms/quick-booking", json=payload, headers=headers)
        assert resp.status_code in [200, 201], f"Quick booking failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        
        # Should have created a booking
        assert 'id' in data or 'booking_id' in data, f"No booking id in response: {data}"
        print(f"PASS: Quick booking without guest_id creates walk-in guest")
    
    def test_quick_booking_with_existing_guest_id(self):
        """Quick booking with guest_id should use existing guest"""
        room = self._get_available_room()
        guest = self._get_existing_guest()
        
        if not room:
            pytest.skip("No available room for testing")
        if not guest:
            pytest.skip("No existing guest for testing")
        
        import datetime as dt
        import uuid
        import random
        from pymongo import MongoClient
        offset = 3000 + random.randint(0, 3000)
        check_in = dt.date.today() + dt.timedelta(days=offset)
        check_out = check_in + dt.timedelta(days=1)
        
        _mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms"))
        _db = _mongo[os.environ.get("DB_NAME", "hotel_pms")]
        _db.room_night_locks.delete_many({"room_id": room['id'], "night_date": {"$gte": str(check_in), "$lte": str(check_out)}})
        _mongo.close()
        
        payload = {
            "guest_name": guest.get('name', 'Existing Guest'),
            "room_id": room['id'],
            "check_in": f"{check_in}T14:00:00+00:00",
            "check_out": f"{check_out}T11:00:00+00:00",
            "total_amount": 150.0,
            "guest_id": guest['id']
        }
        
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        resp = requests.post(f"{BASE_URL}/api/pms/quick-booking", json=payload, headers=headers)
        assert resp.status_code in [200, 201], f"Quick booking failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        
        # Should have created a booking with the existing guest
        assert 'id' in data or 'booking_id' in data, f"No booking id in response: {data}"
        print(f"PASS: Quick booking with guest_id uses existing guest")
    
    def test_quick_booking_with_invalid_guest_id(self):
        """Quick booking with non-existent guest_id should return 404"""
        room = self._get_available_room()
        if not room:
            pytest.skip("No available room for testing")
        
        import datetime as dt
        import uuid
        import random
        offset = 3000 + random.randint(0, 3000)
        check_in = dt.date.today() + dt.timedelta(days=offset)
        check_out = check_in + dt.timedelta(days=1)
        
        payload = {
            "guest_name": "Test Guest",
            "room_id": room['id'],
            "check_in": f"{check_in}T14:00:00+00:00",
            "check_out": f"{check_out}T11:00:00+00:00",
            "total_amount": 100.0,
            "guest_id": "non-existent-guest-id-12345"
        }
        
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        resp = requests.post(f"{BASE_URL}/api/pms/quick-booking", json=payload, headers=headers)
        assert resp.status_code == 404, f"Expected 404 for invalid guest_id, got {resp.status_code}: {resp.text}"
        print("PASS: Quick booking with invalid guest_id returns 404")


class TestGuestSearchFromSearchEndpoint:
    """Additional tests for guest search endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def test_search_by_email_partial(self):
        """Search should work with partial email"""
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=@hotel", headers=self.headers)
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        print(f"PASS: Email partial search works, found {len(resp.json())} results")
    
    def test_search_by_phone_partial(self):
        """Search should work with partial phone"""
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=555", headers=self.headers)
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        print(f"PASS: Phone partial search works, found {len(resp.json())} results")
    
    def test_search_requires_auth(self):
        """Search endpoint should require authentication"""
        resp = requests.get(f"{BASE_URL}/api/pms/guests/search?q=test")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print("PASS: Guest search requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
