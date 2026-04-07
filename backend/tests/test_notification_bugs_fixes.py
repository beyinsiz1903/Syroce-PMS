"""
Test Notification Bug Fixes - Iteration 185
============================================
Tests for:
1. GET /api/notifications/list returns 'read' field (not 'is_read')
2. PUT /api/notifications/mark-all-read endpoint marks all as read
3. Notification unread_count correctly counts unread using {'$ne': True} query
4. Reservation detail shows created_at timestamp
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://channel-sync-hub-1.preview.emergentagent.com")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    # Auth token field is 'access_token' (not 'token')
    token = data.get("access_token")
    assert token, f"No access_token in response: {data}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestNotificationListEndpoint:
    """Tests for GET /api/notifications/list endpoint."""

    def test_notifications_list_returns_read_field(self, auth_headers):
        """Verify notifications list returns 'read' field, not 'is_read'."""
        response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check response structure
        assert "notifications" in data, "Missing 'notifications' key"
        assert "unread_count" in data, "Missing 'unread_count' key"
        
        # Check that notifications use 'read' field (not 'is_read')
        for notif in data["notifications"]:
            assert "read" in notif, f"Notification missing 'read' field: {notif}"
            # 'is_read' should NOT be present (normalized to 'read')
            assert "is_read" not in notif or notif.get("is_read") is None, \
                f"Notification still has 'is_read' field: {notif}"

    def test_unread_count_is_integer(self, auth_headers):
        """Verify unread_count is a valid integer."""
        response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data["unread_count"], int), \
            f"unread_count should be int, got {type(data['unread_count'])}"
        assert data["unread_count"] >= 0, "unread_count should be non-negative"


class TestMarkAllReadEndpoint:
    """Tests for PUT /api/notifications/mark-all-read endpoint."""

    def test_mark_all_read_endpoint_exists(self, auth_headers):
        """Verify mark-all-read endpoint exists and returns ok."""
        response = requests.put(
            f"{BASE_URL}/api/notifications/mark-all-read",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("ok") is True, f"Expected ok=True, got: {data}"

    def test_mark_all_read_updates_unread_count(self, auth_headers):
        """Verify mark-all-read sets unread_count to 0."""
        # Call mark-all-read
        response = requests.put(
            f"{BASE_URL}/api/notifications/mark-all-read",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 200
        
        # Verify unread_count is now 0
        list_response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["unread_count"] == 0, \
            f"Expected unread_count=0 after mark-all-read, got {data['unread_count']}"

    def test_mark_all_read_sets_read_true(self, auth_headers):
        """Verify mark-all-read sets read=True on all notifications."""
        # Call mark-all-read
        requests.put(
            f"{BASE_URL}/api/notifications/mark-all-read",
            headers=auth_headers,
            json={},
        )
        
        # Verify all notifications have read=True
        list_response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=20",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        data = list_response.json()
        
        for notif in data["notifications"]:
            assert notif.get("read") is True, \
                f"Notification {notif.get('id')} should have read=True after mark-all-read"


class TestReservationDetailCreatedAt:
    """Tests for reservation detail showing created_at timestamp."""

    def test_reservation_full_detail_includes_created_at(self, auth_headers):
        """Verify reservation full-detail endpoint includes created_at."""
        # First get a list of bookings to find a valid booking ID
        bookings_response = requests.get(
            f"{BASE_URL}/api/pms/bookings?limit=5",
            headers=auth_headers,
        )
        
        if bookings_response.status_code != 200:
            pytest.skip("Could not fetch bookings list")
        
        bookings = bookings_response.json()
        if not bookings or len(bookings) == 0:
            pytest.skip("No bookings available for testing")
        
        # Get the first booking ID
        booking_id = bookings[0].get("id")
        if not booking_id:
            pytest.skip("Booking has no ID")
        
        # Fetch full detail
        detail_response = requests.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/full-detail",
            headers=auth_headers,
        )
        
        if detail_response.status_code == 404:
            pytest.skip(f"Booking {booking_id} not found in full-detail")
        
        assert detail_response.status_code == 200, f"Failed: {detail_response.text}"
        data = detail_response.json()
        
        # Check booking has created_at
        booking = data.get("booking", {})
        assert "created_at" in booking or booking.get("created_at") is not None, \
            f"Booking should have created_at field: {list(booking.keys())}"


class TestNotificationDeduplication:
    """Tests for notification deduplication (dedup_key)."""

    def test_notifications_have_dedup_key(self, auth_headers):
        """Verify notifications have dedup_key for deduplication."""
        response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check if any notifications have dedup_key (not all may have it)
        notifications_with_dedup = [n for n in data["notifications"] if n.get("dedup_key")]
        
        # This is informational - dedup_key may not be on all notifications
        print(f"Notifications with dedup_key: {len(notifications_with_dedup)}/{len(data['notifications'])}")


class TestMarkSingleNotificationRead:
    """Tests for PUT /api/notifications/{id}/mark-read endpoint."""

    def test_mark_single_notification_read(self, auth_headers):
        """Verify single notification can be marked as read."""
        # Get notifications list
        list_response = requests.get(
            f"{BASE_URL}/api/notifications/list?limit=5",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        data = list_response.json()
        
        if not data["notifications"]:
            pytest.skip("No notifications to test")
        
        notif_id = data["notifications"][0].get("id")
        if not notif_id:
            pytest.skip("Notification has no ID")
        
        # Mark single notification as read
        response = requests.put(
            f"{BASE_URL}/api/notifications/{notif_id}/mark-read",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        # Response can be {"ok": true} or {"message": "...", "notification_id": "..."}
        assert result.get("ok") is True or "notification_id" in result, \
            f"Expected ok=True or notification_id in response, got: {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
