"""
Test suite for PMS Rooms Tab Quick Actions (Check-in/Check-out buttons, Identity dialog, Payment)
Tests the new features added to RoomsTab.js:
- C/In button for rooms with check-in date = today and status confirmed/guaranteed
- C/Out button for rooms with check-out date = today and status checked_in
- Checkout balance warning dialog when there's outstanding balance
- Identity dialog for guest name click
- Payment button for checked_in rooms
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set - integration tests require a running server"
)
TODAY = datetime.now().strftime('%Y-%m-%d')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "No access token in response"
    return token

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestCheckInEndpoint:
    """Tests for POST /api/frontdesk/checkin/{booking_id}"""
    
    def test_checkin_nonexistent_booking_returns_404(self, auth_headers):
        """Check-in with non-existent booking ID should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/frontdesk/checkin/nonexistent-booking-id",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "not found" in data.get("detail", "").lower()
        print("✅ Check-in with non-existent booking returns 404")
    
    def test_checkin_valid_booking(self, auth_headers):
        """Check-in with valid booking should succeed"""
        # Get a confirmed booking with today's check-in date
        bookings_resp = requests.get(
            f"{BASE_URL}/api/pms/bookings?limit=100",
            headers=auth_headers
        )
        assert bookings_resp.status_code == 200
        bookings = bookings_resp.json()
        
        # Find a confirmed booking with today's check-in
        test_booking = None
        for b in bookings:
            status = b.get('status', '')
            check_in = (b.get('check_in') or '')[:10]
            if status == 'confirmed' and check_in == TODAY and b.get('room_number'):
                test_booking = b
                break
        
        if not test_booking:
            pytest.skip("No confirmed booking with today's check-in date found")
        
        booking_id = test_booking['id']
        response = requests.post(
            f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true",
            headers=auth_headers
        )
        
        # Accept either success or already checked in
        assert response.status_code in [200, 400], f"Unexpected status {response.status_code}: {response.text}"
        data = response.json()
        
        if response.status_code == 200:
            assert "message" in data or "checked_in_at" in data
            print(f"✅ Check-in successful for booking {booking_id}")
        else:
            detail = data.get("detail", "").lower()
            # Accept various expected error conditions
            assert any(x in detail for x in ["already", "not ready", "not available"]), f"Unexpected error: {detail}"
            print(f"✅ Check-in blocked with expected reason: {data.get('detail')}")


class TestCheckOutEndpoint:
    """Tests for POST /api/frontdesk/checkout/{booking_id}"""
    
    def test_checkout_nonexistent_booking_returns_404(self, auth_headers):
        """Check-out with non-existent booking ID should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/frontdesk/checkout/nonexistent-booking-id",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "not found" in data.get("detail", "").lower()
        print("✅ Check-out with non-existent booking returns 404")
    
    def test_checkout_with_force_parameter(self, auth_headers):
        """Check-out with force=true should work even with balance"""
        # Find a checked_in booking
        bookings_resp = requests.get(
            f"{BASE_URL}/api/pms/bookings?limit=100",
            headers=auth_headers
        )
        assert bookings_resp.status_code == 200
        bookings = bookings_resp.json()
        
        test_booking = None
        for b in bookings:
            if b.get('status') == 'checked_in':
                test_booking = b
                break
        
        if not test_booking:
            pytest.skip("No checked_in booking found")
        
        booking_id = test_booking['id']
        response = requests.post(
            f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true",
            headers=auth_headers
        )
        
        # Accept either success or already checked out
        assert response.status_code in [200, 400], f"Unexpected status {response.status_code}: {response.text}"
        data = response.json()
        
        if response.status_code == 200:
            assert "message" in data or "checked_out_at" in data
            print(f"✅ Check-out successful for booking {booking_id}")
        else:
            assert "already" in data.get("detail", "").lower()
            print(f"✅ Booking {booking_id} was already checked out")


class TestGuestEndpoints:
    """Tests for guest identity dialog API calls"""
    
    def test_get_single_guest_endpoint_missing(self, auth_headers):
        """GET /api/pms/guests/{id} - ISSUE: This endpoint doesn't exist"""
        # Get a guest ID first
        guests_resp = requests.get(
            f"{BASE_URL}/api/pms/guests?limit=5",
            headers=auth_headers
        )
        assert guests_resp.status_code == 200
        guests = guests_resp.json()
        
        if not guests:
            pytest.skip("No guests found")
        
        guest_id = guests[0]['id']
        
        response = requests.get(
            f"{BASE_URL}/api/pms/guests/{guest_id}",
            headers=auth_headers
        )
        
        # Endpoint now exists and should return guest data
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ GET /api/pms/guests/{{id}} works correctly - status {response.status_code}")
    
    def test_put_single_guest_endpoint_missing(self, auth_headers):
        """PUT /api/pms/guests/{id} - ISSUE: This endpoint doesn't exist"""
        guests_resp = requests.get(
            f"{BASE_URL}/api/pms/guests?limit=5",
            headers=auth_headers
        )
        assert guests_resp.status_code == 200
        guests = guests_resp.json()
        
        if not guests:
            pytest.skip("No guests found")
        
        guest_id = guests[0]['id']
        
        # This endpoint should exist but doesn't
        response = requests.put(
            f"{BASE_URL}/api/pms/guests/{guest_id}",
            headers=auth_headers,
            json={
                "name": "Test Update",
                "id_type": "national_id",
                "id_number": "12345678901"
            }
        )
        
        # Endpoint now exists and works correctly
        assert response.status_code == 200, f"PUT /api/pms/guests/{{id}} should return 200, got {response.status_code}"
        print(f"✅ PUT /api/pms/guests/{{id}} returns {response.status_code} - endpoint is working")


class TestBookingsData:
    """Tests for bookings data that RoomsTab uses"""
    
    def test_get_bookings_returns_expected_fields(self, auth_headers):
        """Verify bookings have all fields needed by RoomsTab roomGuestMap"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings?limit=20",
            headers=auth_headers
        )
        assert response.status_code == 200
        bookings = response.json()
        
        required_fields = ['id', 'status', 'check_in', 'check_out', 'room_number', 
                          'guest_id', 'guest_name', 'total_amount', 'paid_amount']
        
        for booking in bookings[:5]:  # Check first 5
            for field in required_fields:
                assert field in booking, f"Missing field: {field} in booking {booking.get('id')}"
        
        print(f"✅ Bookings have all required fields for RoomsTab")
    
    def test_get_rooms_returns_expected_fields(self, auth_headers):
        """Verify rooms have all fields needed by RoomsTab"""
        response = requests.get(
            f"{BASE_URL}/api/pms/rooms?limit=20",
            headers=auth_headers
        )
        assert response.status_code == 200
        rooms = response.json()
        
        required_fields = ['id', 'room_number', 'room_type', 'status', 'floor', 'capacity']
        
        for room in rooms[:5]:  # Check first 5
            for field in required_fields:
                assert field in room, f"Missing field: {field} in room {room.get('room_number')}"
        
        print(f"✅ Rooms have all required fields for RoomsTab")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
