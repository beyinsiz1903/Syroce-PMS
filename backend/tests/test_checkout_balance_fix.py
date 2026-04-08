"""
P0 Bug Fix: Checkout Balance Check Tests
Tests the fix in frontdesk_service.py checkout() method.

The bug was: checkout endpoint only checked folio balance (which could be 0)
but not booking-level balance (total_amount - paid_amount).

Fix: effective_balance = max(folio_balance, booking_balance)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)
if not BASE_URL:
    BASE_URL = "https://hotel-content-sync.preview.emergentagent.com"


class TestCheckoutBalanceFix:
    """Tests for the P0 checkout balance check fix"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        # Cleanup happens in individual tests

    # ========================================================
    # Test 1: Checkout with outstanding booking balance returns 402
    # ========================================================
    def test_checkout_with_outstanding_balance_returns_402(self):
        """
        CRITICAL TEST: Checkout should return 402 when booking has
        outstanding balance (total_amount > paid_amount), even if
        folio balance is 0.
        
        Test booking: 495769cf (room 109, total=700, paid=0)
        """
        booking_id = "495769cf"
        
        # First, get the booking to verify it has outstanding balance
        bookings_resp = self.session.get(f"{BASE_URL}/api/pms/bookings?limit=100")
        assert bookings_resp.status_code == 200, f"Get bookings failed: {bookings_resp.text}"
        
        bookings = bookings_resp.json()
        target_booking = None
        for b in bookings:
            if b.get("id", "").startswith(booking_id):
                target_booking = b
                break
        
        if not target_booking:
            pytest.skip(f"Booking {booking_id} not found in list")
        
        full_booking_id = target_booking["id"]
        total_amount = target_booking.get("total_amount", 0) or 0
        paid_amount = target_booking.get("paid_amount", 0) or 0
        balance = total_amount - paid_amount
        
        print(f"\nBooking: {full_booking_id}")
        print(f"Total Amount: {total_amount}")
        print(f"Paid Amount: {paid_amount}")
        print(f"Balance: {balance}")
        
        # Verify booking has outstanding balance
        assert balance > 0, f"Booking {full_booking_id} has no outstanding balance"
        
        # Check booking status - need to check it in first if status is 'confirmed'
        if target_booking.get("status") == "confirmed":
            # Check-in first
            checkin_resp = self.session.post(
                f"{BASE_URL}/api/frontdesk/checkin/{full_booking_id}"
            )
            # May fail if room not ready - that's ok for this test
            if checkin_resp.status_code == 200:
                print("Checked in successfully for testing")
            else:
                print(f"Check-in failed: {checkin_resp.text}")
        
        # Try checkout WITHOUT force - should return 402
        checkout_resp = self.session.post(
            f"{BASE_URL}/api/frontdesk/checkout/{full_booking_id}?force=false"
        )
        
        print(f"Checkout Response Status: {checkout_resp.status_code}")
        print(f"Checkout Response: {checkout_resp.text}")
        
        # CRITICAL ASSERTION: Should return 402 Outstanding Balance
        assert checkout_resp.status_code == 402, (
            f"Expected 402 for outstanding balance, got {checkout_resp.status_code}. "
            f"Response: {checkout_resp.text}"
        )
        
        # Verify error message mentions balance
        error_detail = checkout_resp.json().get("detail", "")
        assert "balance" in error_detail.lower() or "Outstanding" in error_detail, (
            f"Error should mention balance. Got: {error_detail}"
        )

    # ========================================================
    # Test 2: Force checkout succeeds even with outstanding balance
    # ========================================================
    def test_force_checkout_succeeds_with_balance(self):
        """
        Force checkout should succeed even when booking has outstanding balance.
        Uses force=true query parameter.
        
        We'll create a test booking for this.
        """
        # First get a room that's available
        rooms_resp = self.session.get(f"{BASE_URL}/api/pms/rooms?status=available&limit=5")
        if rooms_resp.status_code != 200 or not rooms_resp.json():
            pytest.skip("No available rooms for test")
        
        available_rooms = rooms_resp.json()
        if not available_rooms:
            pytest.skip("No available rooms for test")
        
        test_room = available_rooms[0]
        room_id = test_room.get("id")
        
        # Create a test guest
        guest_resp = self.session.post(
            f"{BASE_URL}/api/pms/guests",
            json={
                "name": "TEST_ForceCheckout Guest",
                "email": f"test_forcecheckout_{os.urandom(4).hex()}@test.com",
                "phone": "5551234567",
                "id_number": "TEST12345",
            },
        )
        if guest_resp.status_code != 200:
            pytest.skip(f"Could not create test guest: {guest_resp.text}")
        
        guest_id = guest_resp.json().get("id")
        
        # Create a test booking with outstanding balance
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        booking_resp = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": today,
                "check_out": tomorrow,
                "adults": 1,
                "children": 0,
                "total_amount": 500.0,  # Outstanding balance
                "paid_amount": 0.0,
                "status": "confirmed",
            },
        )
        
        if booking_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create test booking: {booking_resp.text}")
        
        booking_data = booking_resp.json()
        booking_id = booking_data.get("id") or booking_data.get("booking_id")
        
        print(f"\nCreated test booking: {booking_id}")
        
        try:
            # Check-in first
            checkin_resp = self.session.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}")
            print(f"Check-in response: {checkin_resp.status_code}")
            
            # Now try force checkout with outstanding balance
            checkout_resp = self.session.post(
                f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true"
            )
            
            print(f"Force Checkout Response Status: {checkout_resp.status_code}")
            print(f"Force Checkout Response: {checkout_resp.text}")
            
            # ASSERTION: Force checkout should succeed (200)
            assert checkout_resp.status_code == 200, (
                f"Force checkout should succeed. Got {checkout_resp.status_code}: {checkout_resp.text}"
            )
            
            # Verify checkout message
            checkout_data = checkout_resp.json()
            assert "Check-out completed" in checkout_data.get("message", "") or checkout_data.get("checked_out_at"), (
                f"Checkout should show completion message. Got: {checkout_data}"
            )
        
        finally:
            # Cleanup - delete test booking (soft delete by setting status)
            pass  # Booking is already checked out

    # ========================================================
    # Test 3: Checkout succeeds when balance is zero
    # ========================================================
    def test_checkout_succeeds_with_zero_balance(self):
        """
        Checkout should succeed when booking has zero balance
        (total_amount == paid_amount).
        """
        # First get a room that's available
        rooms_resp = self.session.get(f"{BASE_URL}/api/pms/rooms?status=available&limit=5")
        if rooms_resp.status_code != 200 or not rooms_resp.json():
            pytest.skip("No available rooms for test")
        
        available_rooms = rooms_resp.json()
        if not available_rooms:
            pytest.skip("No available rooms for test")
        
        test_room = available_rooms[0]
        room_id = test_room.get("id")
        
        # Create a test guest
        guest_resp = self.session.post(
            f"{BASE_URL}/api/pms/guests",
            json={
                "name": "TEST_ZeroBalance Guest",
                "email": f"test_zerobalance_{os.urandom(4).hex()}@test.com",
                "phone": "5551234568",
                "id_number": "TEST12346",
            },
        )
        if guest_resp.status_code != 200:
            pytest.skip(f"Could not create test guest: {guest_resp.text}")
        
        guest_id = guest_resp.json().get("id")
        
        # Create a test booking with ZERO balance (paid == total)
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        booking_resp = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": today,
                "check_out": tomorrow,
                "adults": 1,
                "children": 0,
                "total_amount": 300.0,
                "paid_amount": 300.0,  # Fully paid!
                "status": "confirmed",
            },
        )
        
        if booking_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create test booking: {booking_resp.text}")
        
        booking_data = booking_resp.json()
        booking_id = booking_data.get("id") or booking_data.get("booking_id")
        
        print(f"\nCreated test booking with zero balance: {booking_id}")
        
        try:
            # Check-in first
            checkin_resp = self.session.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}")
            print(f"Check-in response: {checkin_resp.status_code}")
            
            # Now try regular checkout (no force) - should succeed
            checkout_resp = self.session.post(
                f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=false"
            )
            
            print(f"Checkout Response Status: {checkout_resp.status_code}")
            print(f"Checkout Response: {checkout_resp.text}")
            
            # ASSERTION: Checkout should succeed (200)
            assert checkout_resp.status_code == 200, (
                f"Checkout with zero balance should succeed. Got {checkout_resp.status_code}: {checkout_resp.text}"
            )
            
        finally:
            pass  # Booking is already checked out


class TestGuestEndpoints:
    """Tests for GET/PUT /api/pms/guests/{guest_id} endpoints (added in this fix)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield

    def test_get_single_guest(self):
        """GET /api/pms/guests/{guest_id} returns single guest data"""
        # First get list of guests to find a valid ID
        guests_resp = self.session.get(f"{BASE_URL}/api/pms/guests?limit=5")
        assert guests_resp.status_code == 200, f"Get guests failed: {guests_resp.text}"
        
        guests = guests_resp.json()
        if not guests:
            pytest.skip("No guests in system")
        
        guest_id = guests[0].get("id")
        
        # Now get single guest
        single_resp = self.session.get(f"{BASE_URL}/api/pms/guests/{guest_id}")
        
        print(f"\nGET /api/pms/guests/{guest_id}")
        print(f"Response Status: {single_resp.status_code}")
        print(f"Response: {single_resp.text[:500]}")
        
        assert single_resp.status_code == 200, (
            f"GET single guest should return 200. Got {single_resp.status_code}: {single_resp.text}"
        )
        
        guest_data = single_resp.json()
        assert guest_data.get("id") == guest_id, "Guest ID mismatch"
        assert "name" in guest_data, "Guest should have name field"

    def test_update_guest_identity(self):
        """PUT /api/pms/guests/{guest_id} updates guest identity fields"""
        # Create a test guest first
        guest_resp = self.session.post(
            f"{BASE_URL}/api/pms/guests",
            json={
                "name": "TEST_UpdateGuest Original",
                "email": f"test_update_{os.urandom(4).hex()}@test.com",
                "phone": "5559876543",
                "id_number": "ORIG123",
            },
        )
        
        if guest_resp.status_code != 200:
            pytest.skip(f"Could not create test guest: {guest_resp.text}")
        
        guest_id = guest_resp.json().get("id")
        
        # Update guest identity
        update_data = {
            "name": "TEST_UpdateGuest Modified",
            "id_type": "passport",
            "id_number": "MOD456789",
            "nationality": "TR",
            "date_of_birth": "1990-01-15",
        }
        
        update_resp = self.session.put(
            f"{BASE_URL}/api/pms/guests/{guest_id}",
            json=update_data,
        )
        
        print(f"\nPUT /api/pms/guests/{guest_id}")
        print(f"Update data: {update_data}")
        print(f"Response Status: {update_resp.status_code}")
        print(f"Response: {update_resp.text[:500]}")
        
        assert update_resp.status_code == 200, (
            f"PUT guest update should return 200. Got {update_resp.status_code}: {update_resp.text}"
        )
        
        # Verify the update persisted
        verify_resp = self.session.get(f"{BASE_URL}/api/pms/guests/{guest_id}")
        assert verify_resp.status_code == 200
        
        updated_guest = verify_resp.json()
        assert updated_guest.get("name") == "TEST_UpdateGuest Modified", "Name should be updated"
        assert updated_guest.get("id_number") == "MOD456789", "ID number should be updated"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
