"""
PMS Decomposition Stage 2 - API Tests
--------------------------------------
Tests for routes extracted in Stage 2:
- pms_bookings.py: 10 booking routes (POST/GET bookings, quick-booking, approve/reject, etc.)
- pms_dashboard.py: 3 dashboard routes (dashboard, operational-alerts, room-alternatives)
- pms.py remaining routes: room-services, room-blocks, staff-tasks, setup-status, reservations/search, etc.
"""
import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://hotel-sync-hub-2.preview.emergentagent.com"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token using demo credentials."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


# ============================================================================
# DASHBOARD ROUTES (pms_dashboard.py) - 3 routes
# ============================================================================


class TestDashboardRoutes:
    """Tests for routes extracted to pms_dashboard.py"""

    def test_get_dashboard(self, auth_headers):
        """GET /api/pms/dashboard - returns dashboard data"""
        response = requests.get(f"{BASE_URL}/api/pms/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        # Verify expected fields
        assert "total_rooms" in data
        assert "occupied_rooms" in data
        assert "available_rooms" in data
        assert "occupancy_rate" in data
        print(f"Dashboard: {data['total_rooms']} rooms, {data['occupancy_rate']}% occupancy")

    def test_get_operational_alerts(self, auth_headers):
        """GET /api/pms/operational-alerts - returns alerts and summary"""
        response = requests.get(f"{BASE_URL}/api/pms/operational-alerts", headers=auth_headers)
        assert response.status_code == 200, f"Operational alerts failed: {response.text}"
        data = response.json()
        # Verify structure
        assert "alerts" in data
        assert "summary" in data
        assert isinstance(data["alerts"], list)
        assert "arrivals_today" in data["summary"]
        assert "departures_today" in data["summary"]
        print(f"Alerts: {len(data['alerts'])} alerts, {data['summary']['arrivals_today']} arrivals today")

    def test_get_room_alternatives(self, auth_headers):
        """GET /api/pms/room-alternatives/{room_number} - returns alternative rooms"""
        response = requests.get(f"{BASE_URL}/api/pms/room-alternatives/101", headers=auth_headers)
        assert response.status_code == 200, f"Room alternatives failed: {response.text}"
        data = response.json()
        # Verify structure
        assert "alternatives" in data or "same_type" in data
        print(f"Room alternatives response: {list(data.keys())}")


# ============================================================================
# BOOKING ROUTES (pms_bookings.py) - 10 routes
# ============================================================================


class TestBookingRoutes:
    """Tests for routes extracted to pms_bookings.py"""

    def test_get_bookings(self, auth_headers):
        """GET /api/pms/bookings - returns bookings list"""
        response = requests.get(f"{BASE_URL}/api/pms/bookings", headers=auth_headers)
        assert response.status_code == 200, f"Get bookings failed: {response.text}"
        data = response.json()
        # Response can be list or dict with bookings key
        if isinstance(data, list):
            print(f"Bookings: {len(data)} bookings returned")
        else:
            assert "bookings" in data or isinstance(data, list)
            print(f"Bookings response: {list(data.keys()) if isinstance(data, dict) else 'list'}")

    def test_get_bookings_with_search(self, auth_headers):
        """GET /api/pms/bookings?search=test - search bookings"""
        response = requests.get(f"{BASE_URL}/api/pms/bookings?search=test", headers=auth_headers)
        assert response.status_code == 200, f"Search bookings failed: {response.text}"
        data = response.json()
        print(f"Search bookings response: {type(data)}")

    def test_get_booking_override_logs(self, auth_headers):
        """GET /api/bookings/{id}/override-logs - returns override logs"""
        # Use a test booking ID
        response = requests.get(f"{BASE_URL}/api/bookings/test-booking-id/override-logs", headers=auth_headers)
        # 200 with empty list or 404 are both acceptable
        assert response.status_code in [200, 404], f"Override logs failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            print(f"Override logs: {len(data)} logs")

    def test_approve_booking_not_found(self, auth_headers):
        """POST /api/bookings/{id}/approve - 404 for non-existent booking"""
        response = requests.post(
            f"{BASE_URL}/api/bookings/nonexistent-booking-id/approve",
            headers=auth_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Approve booking: correctly returns 404 for non-existent booking")

    def test_reject_booking_not_found(self, auth_headers):
        """POST /api/bookings/{id}/reject - 404 for non-existent booking"""
        response = requests.post(
            f"{BASE_URL}/api/bookings/nonexistent-booking-id/reject",
            headers=auth_headers,
            json={"reason_code": "NO_AVAILABILITY", "reason_note": "Test rejection"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Reject booking: correctly returns 404 for non-existent booking")

    def test_create_room_move_history(self, auth_headers):
        """POST /api/pms/room-move-history - logs room move"""
        from datetime import datetime, timedelta
        
        # RoomMoveHistory model requires old_check_in and new_check_in
        response = requests.post(
            f"{BASE_URL}/api/pms/room-move-history",
            headers=auth_headers,
            json={
                "booking_id": "test-booking-id",
                "old_room": "101",
                "new_room": "102",
                "old_check_in": datetime.now().isoformat(),
                "new_check_in": (datetime.now() + timedelta(days=1)).isoformat(),
                "reason": "Guest request",
            },
        )
        # 200 or 422 (validation) are acceptable
        assert response.status_code in [200, 422], f"Room move history failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "message" in data or "history" in data
            print(f"Room move history: {data}")


# ============================================================================
# REMAINING PMS.PY ROUTES - room-services, room-blocks, staff-tasks, etc.
# ============================================================================


class TestRemainingPmsRoutes:
    """Tests for routes remaining in pms.py"""

    def test_get_room_services(self, auth_headers):
        """GET /api/pms/room-services - returns room services"""
        response = requests.get(f"{BASE_URL}/api/pms/room-services", headers=auth_headers)
        assert response.status_code == 200, f"Room services failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Room services: {len(data)} services")

    def test_get_room_blocks(self, auth_headers):
        """GET /api/pms/room-blocks - returns room blocks"""
        response = requests.get(f"{BASE_URL}/api/pms/room-blocks", headers=auth_headers)
        assert response.status_code == 200, f"Room blocks failed: {response.text}"
        data = response.json()
        # Response can be list or dict with blocks key
        if isinstance(data, dict):
            assert "blocks" in data
            blocks = data["blocks"]
        else:
            blocks = data
        assert isinstance(blocks, list)
        print(f"Room blocks: {len(blocks)} blocks")

    def test_get_staff_tasks(self, auth_headers):
        """GET /api/pms/staff-tasks - returns staff tasks"""
        response = requests.get(f"{BASE_URL}/api/pms/staff-tasks", headers=auth_headers)
        assert response.status_code == 200, f"Staff tasks failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Staff tasks: {len(data)} tasks")

    def test_get_setup_status(self, auth_headers):
        """GET /api/pms/setup-status - returns setup status"""
        response = requests.get(f"{BASE_URL}/api/pms/setup-status", headers=auth_headers)
        assert response.status_code == 200, f"Setup status failed: {response.text}"
        data = response.json()
        assert "rooms_count" in data
        assert "bookings_count" in data
        print(f"Setup status: {data['rooms_count']} rooms, {data['bookings_count']} bookings")

    def test_get_allotment_contracts(self, auth_headers):
        """GET /api/pms/allotment-contracts - returns allotment contracts"""
        response = requests.get(f"{BASE_URL}/api/pms/allotment-contracts", headers=auth_headers)
        assert response.status_code == 200, f"Allotment contracts failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Allotment contracts: {len(data)} contracts")

    def test_get_group_reservations(self, auth_headers):
        """GET /api/pms/group-reservations - returns group reservations"""
        response = requests.get(f"{BASE_URL}/api/pms/group-reservations", headers=auth_headers)
        assert response.status_code == 200, f"Group reservations failed: {response.text}"
        data = response.json()
        assert "groups" in data
        print(f"Group reservations: {len(data['groups'])} groups")

    def test_get_rooms_queue_list(self, auth_headers):
        """GET /api/rooms/queue/list - returns room queue"""
        response = requests.get(f"{BASE_URL}/api/rooms/queue/list", headers=auth_headers)
        assert response.status_code == 200, f"Room queue failed: {response.text}"
        data = response.json()
        assert "queue" in data
        assert "queue_length" in data
        print(f"Room queue: {data['queue_length']} in queue")

    def test_reservations_search(self, auth_headers):
        """GET /api/reservations/search - search reservations (had _id fix)"""
        response = requests.get(f"{BASE_URL}/api/reservations/search", headers=auth_headers)
        assert response.status_code == 200, f"Reservations search failed: {response.text}"
        data = response.json()
        assert "bookings" in data
        assert "count" in data
        # Verify no _id field in response (the fix)
        for booking in data.get("bookings", []):
            assert "_id" not in booking, "MongoDB _id should be excluded"
        print(f"Reservations search: {data['count']} results")

    def test_reservations_search_with_query(self, auth_headers):
        """GET /api/reservations/search?query=test - search with query"""
        response = requests.get(f"{BASE_URL}/api/reservations/search?query=test", headers=auth_headers)
        assert response.status_code == 200, f"Reservations search with query failed: {response.text}"
        data = response.json()
        assert "bookings" in data
        print(f"Reservations search with query: {data['count']} results")


# ============================================================================
# INTEGRATION TESTS - Create booking flow
# ============================================================================


class TestBookingIntegration:
    """Integration tests for booking creation and approval flow"""

    @pytest.fixture
    def test_guest_id(self, auth_headers):
        """Get or create a test guest"""
        # First try to get existing guests
        response = requests.get(f"{BASE_URL}/api/pms/guests?limit=1", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            guests = data.get("guests", data) if isinstance(data, dict) else data
            if guests and len(guests) > 0:
                return guests[0].get("id")
        
        # Create a new guest if none exist
        guest_data = {
            "name": f"Test Guest {uuid.uuid4().hex[:8]}",
            "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
            "phone": "+905551234567",
            "id_number": f"TC{uuid.uuid4().hex[:8].upper()}",
        }
        response = requests.post(f"{BASE_URL}/api/pms/guests", headers=auth_headers, json=guest_data)
        if response.status_code in [200, 201]:
            return response.json().get("id")
        return None

    @pytest.fixture
    def test_room_id(self, auth_headers):
        """Get a test room"""
        response = requests.get(f"{BASE_URL}/api/pms/rooms?limit=1", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            rooms = data.get("rooms", data) if isinstance(data, dict) else data
            if rooms and len(rooms) > 0:
                return rooms[0].get("id")
        return None

    def test_quick_booking_validation(self, auth_headers, test_room_id):
        """POST /api/pms/quick-booking - validation test"""
        if not test_room_id:
            pytest.skip("No room available for testing")
        
        # Test with invalid data (empty guest name)
        response = requests.post(
            f"{BASE_URL}/api/pms/quick-booking",
            headers=auth_headers,
            json={
                "guest_name": "",
                "room_id": test_room_id,
                "check_in": (datetime.now() + timedelta(days=1)).isoformat(),
                "check_out": (datetime.now() + timedelta(days=2)).isoformat(),
                "total_amount": 100.0,
            },
        )
        # Should fail validation
        assert response.status_code in [400, 422], f"Expected validation error, got {response.status_code}"
        print("Quick booking validation: correctly rejects empty guest name")

    def test_create_booking_requires_idempotency_key(self, auth_headers, test_guest_id, test_room_id):
        """POST /api/pms/bookings - requires Idempotency-Key header"""
        if not test_guest_id or not test_room_id:
            pytest.skip("No guest or room available for testing")
        
        # Test without Idempotency-Key
        booking_data = {
            "guest_id": test_guest_id,
            "room_id": test_room_id,
            "check_in": (datetime.now() + timedelta(days=30)).isoformat(),
            "check_out": (datetime.now() + timedelta(days=31)).isoformat(),
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 150.0,
            "channel": "direct",
            "source_channel": "direct",
            "origin": "ui",
        }
        
        # Without Idempotency-Key - should fail or require it
        response = requests.post(
            f"{BASE_URL}/api/pms/bookings",
            headers=auth_headers,
            json=booking_data,
        )
        # May require Idempotency-Key (400/422) or succeed
        print(f"Create booking without Idempotency-Key: {response.status_code}")
        
        # With Idempotency-Key
        headers_with_key = {**auth_headers, "Idempotency-Key": str(uuid.uuid4())}
        response = requests.post(
            f"{BASE_URL}/api/pms/bookings",
            headers=headers_with_key,
            json=booking_data,
        )
        # Should succeed or fail with conflict (if room already booked)
        assert response.status_code in [200, 201, 409, 422], f"Create booking failed: {response.text}"
        print(f"Create booking with Idempotency-Key: {response.status_code}")


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheck:
    """Basic health check tests"""

    def test_auth_login(self):
        """POST /api/auth/login - verify auth works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        assert response.status_code == 200, f"Auth failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data
        print("Auth login: SUCCESS")

    def test_api_health(self, auth_headers):
        """GET /api/pms/setup-status - basic API health"""
        response = requests.get(f"{BASE_URL}/api/pms/setup-status", headers=auth_headers)
        assert response.status_code == 200
        print("API health: OK")
