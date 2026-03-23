"""
Test suite for Hotel Business Date validation in reservations
Features tested:
1. GET /api/night-audit/business-date - returns hotel business date
2. POST /api/pms/bookings - rejects check_in before business date
3. POST /api/pms/bookings - allows check_in on business date
4. POST /api/pms/bookings - allows check_in on today and future dates

Restored from quarantine: stale_dates — all hardcoded dates replaced with dynamic offsets.
"""

import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)


class TestBusinessDateAPI:
    """Test business date endpoint and reservation validation"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        data = login_res.json()
        self.token = data.get("access_token")
        assert self.token, "No access_token in login response"
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

        rooms_res = self.session.get(f"{BASE_URL}/api/pms/rooms")
        assert rooms_res.status_code == 200
        rooms = rooms_res.json()
        assert len(rooms) > 0, "No rooms available"
        self.room_id = rooms[0]["id"]

        guests_res = self.session.get(f"{BASE_URL}/api/pms/guests")
        assert guests_res.status_code == 200
        guests = guests_res.json()
        assert len(guests) > 0, "No guests available"
        self.guest_id = guests[0]["id"]

        bd_res = self.session.get(f"{BASE_URL}/api/night-audit/business-date")
        assert bd_res.status_code == 200
        bd_data = bd_res.json()
        self.business_date = bd_data.get("business_date")
        assert self.business_date, "No business_date in response"

    def test_get_business_date(self):
        """Test GET /api/night-audit/business-date returns business_date field"""
        res = self.session.get(f"{BASE_URL}/api/night-audit/business-date")
        assert res.status_code == 200
        data = res.json()
        assert "business_date" in data
        assert data["business_date"] is not None
        parts = data["business_date"].split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4

    def test_booking_rejected_before_business_date(self):
        """Booking with check_in before business date must be rejected."""
        bd = datetime.strptime(self.business_date, "%Y-%m-%d")
        past_date = (bd - timedelta(days=3)).strftime("%Y-%m-%d")
        past_date_next = (bd - timedelta(days=2)).strftime("%Y-%m-%d")

        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": self.guest_id,
                "room_id": self.room_id,
                "check_in": past_date,
                "check_out": past_date_next,
                "adults": 1, "children": 0, "guests_count": 1,
                "total_amount": 100.0, "status": "confirmed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert res.status_code == 400

    def test_booking_allowed_on_business_date(self):
        """Booking on business date should succeed (or 409 if room already booked)."""
        bd = datetime.strptime(self.business_date, "%Y-%m-%d")
        next_day = (bd + timedelta(days=1)).strftime("%Y-%m-%d")

        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": self.guest_id,
                "room_id": self.room_id,
                "check_in": self.business_date,
                "check_out": next_day,
                "adults": 1, "children": 0, "guests_count": 1,
                "total_amount": 100.0, "status": "confirmed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert res.status_code in [200, 201, 409]

    def test_booking_allowed_on_future_date(self):
        """Booking on a future date should succeed (or 409 if room already booked)."""
        future = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")
        future_next = (datetime.now(timezone.utc) + timedelta(days=91)).strftime("%Y-%m-%d")

        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": self.guest_id,
                "room_id": self.room_id,
                "check_in": future,
                "check_out": future_next,
                "adults": 1, "children": 0, "guests_count": 1,
                "total_amount": 100.0, "status": "confirmed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert res.status_code in [200, 201, 409]

    def test_booking_allowed_on_today(self):
        """Booking on today should succeed (or 409 if room already booked)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": self.guest_id,
                "room_id": self.room_id,
                "check_in": today,
                "check_out": tomorrow,
                "adults": 1, "children": 0, "guests_count": 1,
                "total_amount": 100.0, "status": "confirmed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert res.status_code in [200, 201, 409]

    def test_booking_rejected_day_before_business_date(self):
        """Booking one day before business date must be rejected."""
        bd = datetime.strptime(self.business_date, "%Y-%m-%d")
        day_before = (bd - timedelta(days=1)).strftime("%Y-%m-%d")

        res = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json={
                "guest_id": self.guest_id,
                "room_id": self.room_id,
                "check_in": day_before,
                "check_out": self.business_date,
                "adults": 1, "children": 0, "guests_count": 1,
                "total_amount": 100.0, "status": "confirmed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert res.status_code == 400
