"""
PMS Decomposition Stage 1 - API Regression Tests
=================================================
Tests for Room CRUD, Guest CRUD, Booking API, and Companies route
after Stage 1 decomposition (rooms + guests extracted to pms_rooms.py / pms_guests.py).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://revenue-insight-17.preview.emergentagent.com")
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ── Health Check ──

class TestHealthCheck:
    """Health endpoint tests."""

    def test_health_endpoint_via_internal(self, auth_headers):
        """Health endpoint should return healthy status."""
        # The /health endpoint returns frontend HTML via ingress
        # Test via internal API call
        response = requests.get(f"{BASE_URL}/api/pms/setup-status", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "rooms_count" in data
        assert "bookings_count" in data


# ── Room CRUD (pms_rooms.py) ──

class TestRoomCRUD:
    """Room CRUD API tests - extracted to pms_rooms.py."""

    def test_get_rooms(self, auth_headers):
        """GET /api/pms/rooms should return list of rooms."""
        response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have rooms (demo data)
        assert len(data) > 0
        # Verify room structure
        room = data[0]
        assert "id" in room
        assert "room_number" in room
        assert "room_type" in room
        assert "status" in room

    def test_create_room(self, auth_headers):
        """POST /api/pms/rooms should create a new room."""
        room_number = f"TEST_{uuid.uuid4().hex[:6]}"
        payload = {
            "room_number": room_number,
            "room_type": "standard",
            "floor": 1,
            "capacity": 2,
            "base_price": 100.0,
            "amenities": ["wifi", "tv"],
            "status": "available"
        }
        response = requests.post(f"{BASE_URL}/api/pms/rooms", json=payload, headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data["room_number"] == room_number
        assert data["room_type"] == "standard"
        assert data["floor"] == 1
        assert "id" in data
        return data["id"]

    def test_update_room(self, auth_headers):
        """PUT /api/pms/rooms/{id} should update a room."""
        # First create a room
        room_number = f"UPD_{uuid.uuid4().hex[:6]}"
        create_payload = {
            "room_number": room_number,
            "room_type": "standard",
            "floor": 2,
            "capacity": 2,
            "base_price": 150.0
        }
        create_response = requests.post(f"{BASE_URL}/api/pms/rooms", json=create_payload, headers=auth_headers, timeout=30)
        assert create_response.status_code == 200
        room_id = create_response.json()["id"]

        # Update the room
        update_payload = {"base_price": 200.0, "status": "maintenance"}
        update_response = requests.put(f"{BASE_URL}/api/pms/rooms/{room_id}", json=update_payload, headers=auth_headers, timeout=30)
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["base_price"] == 200.0
        assert updated["status"] == "maintenance"


# ── Guest CRUD (pms_guests.py) ──

class TestGuestCRUD:
    """Guest CRUD API tests - extracted to pms_guests.py."""

    def test_get_guests(self, auth_headers):
        """GET /api/pms/guests should return list of guests."""
        response = requests.get(f"{BASE_URL}/api/pms/guests", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_guest(self, auth_headers):
        """POST /api/pms/guests should create a new guest."""
        guest_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "name": "Test Guest",
            "email": guest_email,
            "phone": "+905551234567",
            "id_number": "12345678901"
        }
        response = requests.post(f"{BASE_URL}/api/pms/guests", json=payload, headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Guest"
        assert data["email"] == guest_email
        assert "id" in data
        return data["id"]

    def test_search_guests(self, auth_headers):
        """GET /api/pms/guests/search?q=test should search guests."""
        response = requests.get(f"{BASE_URL}/api/pms/guests/search?q=test", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_update_guest(self, auth_headers):
        """PUT /api/pms/guests/{id} should update a guest."""
        # First create a guest (phone and id_number are required)
        guest_email = f"upd_{uuid.uuid4().hex[:8]}@example.com"
        create_payload = {
            "name": "Update Test Guest",
            "email": guest_email,
            "phone": "+905559876543",
            "id_number": "98765432101"
        }
        create_response = requests.post(f"{BASE_URL}/api/pms/guests", json=create_payload, headers=auth_headers, timeout=30)
        assert create_response.status_code == 200, f"Create guest failed: {create_response.text}"
        guest_id = create_response.json()["id"]

        # Update the guest
        update_payload = {"name": "Updated Guest Name", "phone": "+905551111111"}
        update_response = requests.put(f"{BASE_URL}/api/pms/guests/{guest_id}", json=update_payload, headers=auth_headers, timeout=30)
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Updated Guest Name"
        assert updated["phone"] == "+905551111111"


# ── Booking API (pms.py) ──

class TestBookingAPI:
    """Booking API tests - still in pms.py."""

    def test_get_bookings(self, auth_headers):
        """GET /api/pms/bookings should return bookings."""
        response = requests.get(f"{BASE_URL}/api/pms/bookings", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        # Can be list or dict with 'bookings' key
        if isinstance(data, dict):
            assert "bookings" in data or "total" in data
        else:
            assert isinstance(data, list)

    def test_create_booking(self, auth_headers):
        """POST /api/pms/bookings should create a booking."""
        # First get a room and guest
        rooms_response = requests.get(f"{BASE_URL}/api/pms/rooms?limit=1", headers=auth_headers, timeout=30)
        assert rooms_response.status_code == 200
        rooms = rooms_response.json()
        if not rooms:
            pytest.skip("No rooms available for booking test")
        room_id = rooms[0]["id"]

        # Create a guest (phone and id_number are required)
        guest_email = f"booking_{uuid.uuid4().hex[:8]}@example.com"
        guest_response = requests.post(
            f"{BASE_URL}/api/pms/guests",
            json={
                "name": "Booking Test Guest",
                "email": guest_email,
                "phone": "+905551234567",
                "id_number": "12345678901"
            },
            headers=auth_headers,
            timeout=30
        )
        assert guest_response.status_code == 200, f"Create guest failed: {guest_response.text}"
        guest_id = guest_response.json()["id"]

        # Create booking (guests_count is required, Idempotency-Key header required)
        check_in = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT14:00:00Z")
        check_out = (datetime.now(timezone.utc) + timedelta(days=32)).strftime("%Y-%m-%dT11:00:00Z")
        
        payload = {
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2,
            "children": 0,
            "guests_count": 2,
            "total_amount": 500.0,
            "channel": "direct",
            "source_channel": "direct"
        }
        headers_with_idempotency = {
            **auth_headers,
            "Idempotency-Key": str(uuid.uuid4())
        }
        response = requests.post(f"{BASE_URL}/api/pms/bookings", json=payload, headers=headers_with_idempotency, timeout=30)
        # May return 200 or 201 or 409 (conflict if room already booked)
        assert response.status_code in [200, 201, 409], f"Unexpected status: {response.status_code}, {response.text}"


# ── Companies Route (pms_rooms.py) ──

class TestCompaniesRoute:
    """Companies route test - in pms_rooms.py."""

    def test_get_companies(self, auth_headers):
        """GET /api/pms/companies should return companies list."""
        response = requests.get(f"{BASE_URL}/api/pms/companies", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ── Dashboard & Operational Alerts ──

class TestDashboardAPIs:
    """Dashboard and operational APIs."""

    def test_dashboard(self, auth_headers):
        """GET /api/pms/dashboard should return dashboard data."""
        response = requests.get(f"{BASE_URL}/api/pms/dashboard", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "total_rooms" in data
        assert "occupied_rooms" in data
        assert "available_rooms" in data

    def test_operational_alerts(self, auth_headers):
        """GET /api/pms/operational-alerts should return alerts."""
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=auth_headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "summary" in data


# ── Room Availability ──

class TestRoomAvailability:
    """Room availability API tests."""

    def test_check_availability(self, auth_headers):
        """GET /api/pms/rooms/availability should check room availability."""
        check_in = (datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%d")
        check_out = (datetime.now(timezone.utc) + timedelta(days=62)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
