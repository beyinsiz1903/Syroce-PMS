"""
Test suite for Hotel Business Date validation in reservations
Features tested:
1. GET /api/night-audit/business-date - returns hotel business date
2. POST /api/pms/bookings - rejects check_in before business date
3. POST /api/pms/bookings - allows check_in on business date
4. POST /api/pms/bookings - allows check_in on today and future dates
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set - integration tests require a running server"
)


class TestBusinessDateAPI:
    """Test business date endpoint and reservation validation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        
        data = login_res.json()
        self.token = data.get("access_token")
        assert self.token, "No access_token in login response"
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get room and guest for booking tests
        rooms_res = self.session.get(f"{BASE_URL}/api/pms/rooms")
        assert rooms_res.status_code == 200, f"Failed to get rooms: {rooms_res.text}"
        rooms = rooms_res.json()
        assert len(rooms) > 0, "No rooms available"
        self.room_id = rooms[0]["id"]
        
        guests_res = self.session.get(f"{BASE_URL}/api/pms/guests")
        assert guests_res.status_code == 200, f"Failed to get guests: {guests_res.text}"
        guests = guests_res.json()
        assert len(guests) > 0, "No guests available"
        self.guest_id = guests[0]["id"]
        
        # Get business date
        bd_res = self.session.get(f"{BASE_URL}/api/night-audit/business-date")
        assert bd_res.status_code == 200, f"Failed to get business date: {bd_res.text}"
        bd_data = bd_res.json()
        self.business_date = bd_data.get("business_date")
        assert self.business_date, "No business_date in response"
        print(f"Setup complete: business_date={self.business_date}, room_id={self.room_id}, guest_id={self.guest_id}")
    
    def test_get_business_date(self):
        """Test GET /api/night-audit/business-date returns business_date field"""
        res = self.session.get(f"{BASE_URL}/api/night-audit/business-date")
        
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "business_date" in data, "Response missing 'business_date' field"
        assert data["business_date"] is not None, "business_date should not be null"
        
        # Verify date format YYYY-MM-DD
        bd = data["business_date"]
        parts = bd.split("-")
        assert len(parts) == 3, f"Invalid date format: {bd}"
        assert len(parts[0]) == 4, f"Year should be 4 digits: {bd}"
        print(f"PASS: Business date is {bd}")
    
    def test_booking_rejected_before_business_date(self):
        """Test POST /api/pms/bookings rejects check_in before business date with error message"""
        # Business date is 2026-03-13, try to book 2026-03-10 (before)
        check_in = "2026-03-10"
        check_out = "2026-03-11"
        
        booking_data = {
            "guest_id": self.guest_id,
            "room_id": self.room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 100.0,
            "status": "confirmed"
        }
        
        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_data,
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        
        assert res.status_code == 400, f"Expected 400 for past date, got {res.status_code}: {res.text}"
        
        error_data = res.json()
        detail = error_data.get("detail", "")
        
        # Error message should mention business date
        assert self.business_date in detail or "is gunu" in detail.lower(), \
            f"Error should mention business date ({self.business_date}), got: {detail}"
        print(f"PASS: Booking before business date rejected with message: {detail}")
    
    def test_booking_allowed_on_business_date(self):
        """Test POST /api/pms/bookings allows check_in on business date (2026-03-13)"""
        check_in = self.business_date  # 2026-03-13
        check_out = "2026-03-14"
        
        booking_data = {
            "guest_id": self.guest_id,
            "room_id": self.room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 100.0,
            "status": "confirmed"
        }
        
        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_data,
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        
        # Should be 200/201 (success) or 409 if room already booked
        if res.status_code in [200, 201]:
            data = res.json()
            assert data.get("id"), "Booking should have an ID"
            assert data.get("check_in") == check_in or check_in in data.get("check_in", ""), \
                f"Check-in date mismatch: expected {check_in}"
            print(f"PASS: Booking on business date created successfully, id={data.get('id')}")
        elif res.status_code == 409:
            print(f"PASS: 409 - Room likely already booked for that date (acceptable)")
        else:
            pytest.fail(f"Expected 200/201/409, got {res.status_code}: {res.text}")
    
    def test_booking_allowed_on_future_date(self):
        """Test POST /api/pms/bookings allows check_in on future dates (2026-03-25)"""
        check_in = "2026-03-25"
        check_out = "2026-03-26"
        
        booking_data = {
            "guest_id": self.guest_id,
            "room_id": self.room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 100.0,
            "status": "confirmed"
        }
        
        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_data,
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        
        # Should be 200/201 (success) or 409 if room already booked
        if res.status_code in [200, 201]:
            data = res.json()
            assert data.get("id"), "Booking should have an ID"
            print(f"PASS: Booking on future date created successfully, id={data.get('id')}")
        elif res.status_code == 409:
            print(f"PASS: 409 - Room likely already booked for that date (acceptable)")
        else:
            pytest.fail(f"Expected 200/201/409, got {res.status_code}: {res.text}")
    
    def test_booking_allowed_on_today(self):
        """Test POST /api/pms/bookings allows check_in on today (2026-03-19)"""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow = "2026-03-20"
        
        booking_data = {
            "guest_id": self.guest_id,
            "room_id": self.room_id,
            "check_in": today,
            "check_out": tomorrow,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 100.0,
            "status": "confirmed"
        }
        
        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_data,
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        
        # Should be 200/201 (success) or 409 if room already booked
        if res.status_code in [200, 201]:
            data = res.json()
            assert data.get("id"), "Booking should have an ID"
            print(f"PASS: Booking on today ({today}) created successfully, id={data.get('id')}")
        elif res.status_code == 409:
            print(f"PASS: 409 - Room likely already booked for today (acceptable)")
        else:
            pytest.fail(f"Expected 200/201/409, got {res.status_code}: {res.text}")
    
    def test_booking_rejected_day_before_business_date(self):
        """Test booking rejected for day before business date (2026-03-12)"""
        check_in = "2026-03-12"  # Day before business date 2026-03-13
        check_out = "2026-03-13"
        
        booking_data = {
            "guest_id": self.guest_id,
            "room_id": self.room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 100.0,
            "status": "confirmed"
        }
        
        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_data,
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        
        assert res.status_code == 400, f"Expected 400 for date before business date, got {res.status_code}: {res.text}"
        
        error_data = res.json()
        detail = error_data.get("detail", "")
        assert self.business_date in detail, \
            f"Error should mention business date ({self.business_date}), got: {detail}"
        print(f"PASS: Booking on 2026-03-12 (before business date) rejected: {detail}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
