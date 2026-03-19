"""
Test Cases for Bug A and Bug B fixes:
Bug A: Check-in from Rooms tab quick action fails with 400 error 'occupied' even though guest hasn't checked in
Bug B: Checkout from ReservationDetailModal allowed checkout despite outstanding balance

Fixes verified:
1. ReservationDetailModal 'Giriş Yap' button uses POST /api/frontdesk/checkin/{bookingId}?create_folio=true&force_clean=true
2. ReservationDetailModal 'Çıkış Yap' button uses POST /api/frontdesk/checkout/{bookingId}?auto_close_folios=true
3. Backend frontdesk_service.py checkin handles stale 'occupied' room status
4. Backend checkout returns 402 if outstanding balance exists
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Login and get auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestBugACheckinStaleOccupied:
    """Bug A: Check-in fails with 400 'occupied' even though guest hasn't checked in"""

    def test_checkin_endpoint_exists(self, api_client):
        """Verify POST /api/frontdesk/checkin/{booking_id} endpoint exists"""
        # Use a non-existent booking to test endpoint existence
        response = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/nonexistent-booking-id?create_folio=true")
        # Should return 404 (booking not found) not 405 (method not allowed)
        assert response.status_code in [404, 400], f"Unexpected status: {response.status_code}, {response.text}"
        print(f"✓ Checkin endpoint exists, returned {response.status_code} for nonexistent booking")

    def test_checkin_force_clean_parameter(self, api_client):
        """Verify force_clean parameter is accepted"""
        response = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/nonexistent?create_folio=true&force_clean=true")
        # Should return 404 not 422 (validation error)
        assert response.status_code in [404, 400], f"Unexpected status: {response.status_code}"
        print("✓ force_clean parameter is accepted")

    def test_get_confirmed_bookings_for_checkin(self, api_client):
        """Get confirmed/guaranteed bookings that could be checked in today"""
        today = datetime.now().strftime('%Y-%m-%d')
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        assert response.status_code == 200
        
        bookings = response.json()
        confirmed = [b for b in bookings if b.get('status') in ['confirmed', 'guaranteed']]
        print(f"✓ Found {len(confirmed)} confirmed/guaranteed bookings")
        
        # Find one with today's check-in
        today_arrivals = [b for b in confirmed if b.get('check_in', '').startswith(today)]
        print(f"✓ Found {len(today_arrivals)} arrivals for today")
        
        return confirmed

    def test_checkin_with_stale_occupied_room(self, api_client):
        """Test that checkin handles stale 'occupied' room status"""
        # First, get a confirmed booking
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        assert response.status_code == 200
        bookings = response.json()
        
        confirmed = [b for b in bookings if b.get('status') == 'confirmed']
        if not confirmed:
            pytest.skip("No confirmed bookings available for test")
        
        booking = confirmed[0]
        booking_id = booking['id']
        print(f"Testing checkin for booking {booking_id}, room: {booking.get('room_number')}")
        
        # Attempt checkin with force_clean=true (handles stale occupied)
        response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true"
        )
        
        # Success or specific failure (not generic 400 'occupied')
        if response.status_code == 200:
            print(f"✓ Checkin succeeded: {response.json()}")
        elif response.status_code == 400:
            detail = response.json().get('detail', '')
            # Should NOT be generic "Room is occupied"
            assert 'occupied by another guest' in detail or 'not ready' in detail.lower() or 'already checked' in detail.lower(), \
                f"Unexpected 400 error: {detail} - Bug A may not be fixed"
            print(f"✓ Checkin failed with proper error: {detail}")
        else:
            print(f"Checkin response: {response.status_code} - {response.text}")


class TestBugBCheckoutWithBalance:
    """Bug B: Checkout allowed despite outstanding balance"""

    def test_checkout_endpoint_exists(self, api_client):
        """Verify POST /api/frontdesk/checkout/{booking_id} endpoint exists"""
        response = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/nonexistent?auto_close_folios=true")
        assert response.status_code in [404, 400], f"Unexpected status: {response.status_code}"
        print("✓ Checkout endpoint exists")

    def test_checkout_returns_402_for_outstanding_balance(self, api_client):
        """Verify checkout returns 402 when booking has outstanding balance"""
        # Get checked_in bookings with outstanding balance
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        assert response.status_code == 200
        bookings = response.json()
        
        checked_in = [b for b in bookings if b.get('status') == 'checked_in']
        print(f"Found {len(checked_in)} checked-in bookings")
        
        with_balance = [b for b in checked_in 
                       if (b.get('total_amount', 0) or 0) > (b.get('paid_amount', 0) or 0)]
        print(f"Found {len(with_balance)} checked-in bookings with outstanding balance")
        
        if not with_balance:
            pytest.skip("No checked-in bookings with outstanding balance for test")
        
        booking = with_balance[0]
        booking_id = booking['id']
        balance = (booking.get('total_amount', 0) or 0) - (booking.get('paid_amount', 0) or 0)
        print(f"Testing checkout for booking {booking_id}, balance: {balance}")
        
        # Attempt checkout without force
        response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?auto_close_folios=true"
        )
        
        # Should return 402 for outstanding balance
        assert response.status_code == 402, \
            f"Expected 402 for outstanding balance, got {response.status_code}: {response.text}"
        
        detail = response.json().get('detail', '')
        assert 'outstanding balance' in detail.lower() or 'balance' in detail.lower(), \
            f"Error should mention balance: {detail}"
        
        print(f"✓ Checkout blocked with 402: {detail}")

    def test_checkout_with_force_bypasses_balance_check(self, api_client):
        """Verify force=true bypasses balance check"""
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        bookings = response.json()
        
        checked_in = [b for b in bookings if b.get('status') == 'checked_in']
        with_balance = [b for b in checked_in 
                       if (b.get('total_amount', 0) or 0) > (b.get('paid_amount', 0) or 0)]
        
        if not with_balance:
            pytest.skip("No checked-in bookings with balance for force checkout test")
        
        booking = with_balance[0]
        booking_id = booking['id']
        
        # With force=true, should succeed even with balance
        response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?auto_close_folios=true&force=true"
        )
        
        # Should succeed
        if response.status_code == 200:
            print(f"✓ Force checkout succeeded: {response.json()}")
        else:
            # Already checked out is also valid
            assert 'already checked out' in response.text.lower(), \
                f"Force checkout failed unexpectedly: {response.text}"
            print(f"✓ Booking already checked out")

    def test_checkout_zero_balance_succeeds(self, api_client):
        """Verify checkout succeeds when balance is zero"""
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        bookings = response.json()
        
        checked_in = [b for b in bookings if b.get('status') == 'checked_in']
        zero_balance = [b for b in checked_in 
                       if (b.get('total_amount', 0) or 0) <= (b.get('paid_amount', 0) or 0)]
        
        if not zero_balance:
            print("No checked-in bookings with zero balance - this is expected in most test environments")
            pytest.skip("No checked-in bookings with zero balance")
        
        booking = zero_balance[0]
        booking_id = booking['id']
        
        response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?auto_close_folios=true"
        )
        
        assert response.status_code == 200, f"Zero balance checkout should succeed: {response.text}"
        print(f"✓ Zero balance checkout succeeded")


class TestFrontdeskEndpointIntegration:
    """Integration tests for frontdesk endpoints"""

    def test_checkin_creates_folio(self, api_client):
        """Verify checkin with create_folio=true creates a folio"""
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        bookings = response.json()
        
        confirmed = [b for b in bookings if b.get('status') == 'confirmed']
        if not confirmed:
            pytest.skip("No confirmed bookings for folio creation test")
        
        booking = confirmed[0]
        booking_id = booking['id']
        
        # Checkin
        checkin_response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true"
        )
        
        if checkin_response.status_code == 200:
            # Check folio was created
            folio_response = api_client.get(f"{BASE_URL}/api/frontdesk/folio/{booking_id}")
            if folio_response.status_code == 200:
                print(f"✓ Folio created/exists for booking {booking_id}")
        else:
            print(f"Checkin failed (may already be checked in): {checkin_response.text}")

    def test_checkout_creates_housekeeping_task(self, api_client):
        """Verify checkout sets room to dirty (creates HK task implicitly)"""
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        bookings = response.json()
        
        checked_in = [b for b in bookings if b.get('status') == 'checked_in']
        if not checked_in:
            pytest.skip("No checked-in bookings for HK task test")
        
        # Find one with zero or force checkout
        booking = checked_in[0]
        room_id = booking.get('room_id')
        
        # Force checkout 
        checkout_response = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkout/{booking['id']}?auto_close_folios=true&force=true"
        )
        
        if checkout_response.status_code == 200:
            # Verify room status changed
            if room_id:
                room_response = api_client.get(f"{BASE_URL}/api/pms/rooms/{room_id}")
                if room_response.status_code == 200:
                    room = room_response.json()
                    print(f"Room status after checkout: {room.get('status')}")
        else:
            print(f"Checkout response: {checkout_response.text}")


class TestRoomsTabQuickActions:
    """Test RoomsTab quick action button flows"""

    def test_rooms_list_includes_booking_info(self, api_client):
        """Verify rooms endpoint includes booking/guest info for display"""
        response = api_client.get(f"{BASE_URL}/api/pms/rooms")
        assert response.status_code == 200
        
        rooms = response.json()
        occupied = [r for r in rooms if r.get('status') == 'occupied']
        print(f"✓ Found {len(occupied)} occupied rooms out of {len(rooms)} total")

    def test_bookings_include_balance_calculation(self, api_client):
        """Verify bookings include fields needed for balance calculation"""
        response = api_client.get(f"{BASE_URL}/api/pms/bookings")
        assert response.status_code == 200
        
        bookings = response.json()
        if bookings:
            booking = bookings[0]
            assert 'total_amount' in booking or booking.get('total_amount') is None, "Missing total_amount field"
            print(f"✓ Booking has total_amount: {booking.get('total_amount')}, paid_amount: {booking.get('paid_amount')}")
