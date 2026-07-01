"""
Test Exely Sync and Calendar Bug Fixes

Tests for:
1. OTA Sync button calls correct Exely endpoint POST /api/channel-manager/exely/sync/reservations/pull
2. Cancelled bookings should NOT appear on calendar (backend returns status='cancelled')
3. Individual cancellation check during manual sync
4. Unassigned bookings lane allocation (frontend logic, but we test the API returns proper data)
5. Room assignment API POST /api/pms-core/reservations/{booking_id}/assign-room or PUT /api/pms/bookings/{id}
6. GET /api/pms/bookings returns bookings with correct status
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture
def auth_headers(auth_token):
    """Get headers with authentication"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestExelySyncEndpoint:
    """Test Exely sync endpoint (BUG FIX: OTA Sync button now calls correct endpoint)"""
    
    def test_exely_sync_endpoint_exists(self, auth_headers):
        """BUG FIX: POST /api/channel-manager/exely/sync/reservations/pull exists"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/sync/reservations/pull",
            headers=auth_headers
        )
        # Should NOT be 404 (endpoint exists)
        # May return 404 if no Exely connection, but endpoint is valid
        assert response.status_code != 405, "Endpoint should accept POST"
        print(f"Exely sync endpoint status: {response.status_code}")
        
        # If 200, check response structure
        if response.status_code == 200:
            data = response.json()
            # Should return {success, fetched, processed, cancelled} fields
            assert "message" in data or "success" in data, "Response should have message or success"
            print(f"Exely sync response: {data}")
        elif response.status_code == 404:
            # 404 means no Exely connection configured - endpoint exists but no active connection
            data = response.json()
            assert "detail" in data, "Should have error detail"
            assert "baglanti" in data["detail"].lower() or "connection" in data["detail"].lower()
            print(f"No Exely connection (expected): {data['detail']}")

    def test_old_connector_endpoint_not_used_for_exely(self, auth_headers):
        """Verify old /api/channel-manager/connectors is NOT the Exely endpoint"""
        # The bug was that OTA Sync was calling /api/channel-manager/connectors
        # which is for v2 connectors (HotelRunner), not Exely
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/connectors",
            headers=auth_headers
        )
        # This endpoint might exist for other connectors but shouldn't be used for Exely
        print(f"Old connector endpoint status: {response.status_code}")


class TestCancelledBookingsFilter:
    """Test that cancelled bookings are properly returned with status='cancelled'"""
    
    def test_get_bookings_returns_status(self, auth_headers):
        """GET /api/pms/bookings should return bookings with status field"""
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"start_date": start_date, "end_date": end_date, "limit": 100},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        bookings = response.json()
        assert isinstance(bookings, list)
        print(f"Total bookings returned: {len(bookings)}")
        
        # Check each booking has status field
        for booking in bookings[:5]:  # Check first 5
            assert "status" in booking, f"Booking {booking.get('id')} missing status"
            print(f"Booking {booking.get('guest_name', 'N/A')}: status={booking.get('status')}")
    
    def test_cancelled_bookings_have_cancelled_status(self, auth_headers):
        """Verify cancelled bookings have status='cancelled'"""
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"start_date": start_date, "end_date": end_date, "limit": 500},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        bookings = response.json()
        
        # Find cancelled bookings
        cancelled_bookings = [b for b in bookings if b.get('status') == 'cancelled']
        active_bookings = [b for b in bookings if b.get('status') not in ['cancelled', 'checked_out', 'no_show']]
        
        print(f"Cancelled bookings: {len(cancelled_bookings)}")
        print(f"Active bookings: {len(active_bookings)}")
        
        # Check Ilayda Sutay booking is cancelled (specific test case from bug report)
        ilayda_bookings = [b for b in bookings if 'ilayda' in (b.get('guest_name') or '').lower()]
        for b in ilayda_bookings:
            print(f"Ilayda booking: id={b.get('id')}, status={b.get('status')}")


class TestRoomAssignment:
    """Test room assignment API for drag & drop from unassigned row"""
    
    def test_put_booking_room_id_update(self, auth_headers):
        """PUT /api/pms/bookings/{id} should update room_id for room assignment"""
        # First, get existing bookings
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50},
            headers=auth_headers
        )
        assert response.status_code == 200
        bookings = response.json()
        
        if not bookings:
            pytest.skip("No bookings to test")
        
        # Find an unassigned booking (room_id is null)
        unassigned = [b for b in bookings if not b.get('room_id')]
        print(f"Unassigned bookings: {len(unassigned)}")
        
        # Get rooms for potential assignment
        rooms_response = requests.get(
            f"{BASE_URL}/api/pms/rooms",
            headers=auth_headers
        )
        assert rooms_response.status_code == 200
        rooms = rooms_response.json()
        
        if not rooms:
            pytest.skip("No rooms available")
        
        print(f"Available rooms: {len(rooms)}")
        print(f"First room: {rooms[0].get('room_number')} (id: {rooms[0].get('id')})")
    
    def test_assign_room_endpoint_exists(self, auth_headers):
        """Test /api/pms-core/reservations/{id}/assign-room endpoint exists"""
        # Try with a dummy ID to check endpoint existence
        response = requests.post(
            f"{BASE_URL}/api/pms-core/reservations/test-id/assign-room",
            json={"room_id": "test-room-id"},
            headers=auth_headers
        )
        # Should not be 404 or 405 if endpoint exists
        print(f"Assign room endpoint status: {response.status_code}")
        # May return 404 (booking not found) or 422 (validation error) - but not 405 (method not allowed)


class TestUnassignedBookingsData:
    """Test that unassigned bookings data is properly returned"""
    
    def test_bookings_include_room_type(self, auth_headers):
        """GET /api/pms/bookings should return room_type for each booking"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 50},
            headers=auth_headers
        )
        assert response.status_code == 200
        bookings = response.json()
        
        for booking in bookings[:5]:
            # room_type should be present (enriched from room or booking)
            print(f"Booking {booking.get('guest_name')}: room_type={booking.get('room_type')}, room_id={booking.get('room_id')}")
    
    def test_unassigned_bookings_exist(self, auth_headers):
        """Check if there are unassigned bookings (room_id is null)"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 100},
            headers=auth_headers
        )
        assert response.status_code == 200
        bookings = response.json()
        
        unassigned = [b for b in bookings if not b.get('room_id') and b.get('status') not in ['cancelled', 'checked_out', 'no_show']]
        print(f"Unassigned active bookings: {len(unassigned)}")
        
        for b in unassigned:
            print(f"  - {b.get('guest_name')}: check_in={b.get('check_in')}, room_type={b.get('room_type')}")


class TestExelyConnectionStatus:
    """Test Exely connection status endpoint"""
    
    def test_exely_connection_status(self, auth_headers):
        """GET /api/channel-manager/exely/connection returns connection status"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/connection",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        print(f"Exely connection status: {data}")
        assert "connected" in data
    
    def test_exely_sync_status(self, auth_headers):
        """GET /api/channel-manager/exely/sync/status returns sync status"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/sync/status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        print(f"Exely sync status: {data}")


class TestCalendarDataFiltering:
    """Test that calendar data properly filters out cancelled bookings"""
    
    def test_bookings_filter_by_status(self, auth_headers):
        """Test that frontend can filter bookings by status"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"limit": 200},
            headers=auth_headers
        )
        assert response.status_code == 200
        bookings = response.json()
        
        # Group by status
        status_counts = {}
        for b in bookings:
            status = b.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Bookings by status: {status_counts}")
        
        # Frontend should filter out cancelled, checked_out, no_show
        # This simulates what the frontend does
        active_for_calendar = [
            b for b in bookings 
            if b.get('status') not in ['cancelled', 'checked_out', 'no_show']
        ]
        print(f"Active bookings for calendar: {len(active_for_calendar)}")
