"""
Test No-Show Analytics API and No-Show Reason Feature
Tests:
1. POST /api/pms/bookings/no-show-virtual - accepts no_show_reason field
2. GET /api/pms/no-show-analytics - returns analytics data
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://pms-channel-split.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed - skipping tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestNoShowAnalyticsAPI:
    """Test No-Show Analytics endpoint"""

    def test_get_no_show_analytics_default_30_days(self, auth_headers):
        """GET /api/pms/no-show-analytics returns analytics data for default 30 days"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "total_no_shows" in data, "Missing total_no_shows field"
        assert "total_revenue_loss" in data, "Missing total_revenue_loss field"
        assert "period_days" in data, "Missing period_days field"
        assert "daily" in data, "Missing daily field"
        assert "by_room_type" in data, "Missing by_room_type field"
        assert "by_channel" in data, "Missing by_channel field"
        assert "by_reason" in data, "Missing by_reason field"
        assert "recent" in data, "Missing recent field"
        
        # Verify default period is 30 days
        assert data["period_days"] == 30, f"Expected period_days=30, got {data['period_days']}"
        
        print(f"✓ No-show analytics returned: {data['total_no_shows']} no-shows, {data['total_revenue_loss']} TL loss")

    def test_get_no_show_analytics_7_days(self, auth_headers):
        """GET /api/pms/no-show-analytics?days=7 returns 7-day analytics"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["period_days"] == 7
        print(f"✓ 7-day analytics: {data['total_no_shows']} no-shows")

    def test_get_no_show_analytics_90_days(self, auth_headers):
        """GET /api/pms/no-show-analytics?days=90 returns 90-day analytics"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=90",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["period_days"] == 90
        print(f"✓ 90-day analytics: {data['total_no_shows']} no-shows")

    def test_get_no_show_analytics_365_days(self, auth_headers):
        """GET /api/pms/no-show-analytics?days=365 returns 1-year analytics"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["period_days"] == 365
        print(f"✓ 365-day analytics: {data['total_no_shows']} no-shows")

    def test_no_show_analytics_by_reason_structure(self, auth_headers):
        """Verify by_reason field has correct structure"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        by_reason = data.get("by_reason", [])
        
        # Each reason entry should have reason, label, count
        for reason_entry in by_reason:
            assert "reason" in reason_entry, "Missing reason field in by_reason entry"
            assert "label" in reason_entry, "Missing label field in by_reason entry"
            assert "count" in reason_entry, "Missing count field in by_reason entry"
        
        print(f"✓ by_reason structure valid with {len(by_reason)} reason types")

    def test_no_show_analytics_by_room_type_structure(self, auth_headers):
        """Verify by_room_type field has correct structure"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        by_room_type = data.get("by_room_type", [])
        
        for rt_entry in by_room_type:
            assert "room_type" in rt_entry, "Missing room_type field"
            assert "count" in rt_entry, "Missing count field"
            assert "revenue_loss" in rt_entry, "Missing revenue_loss field"
        
        print(f"✓ by_room_type structure valid with {len(by_room_type)} room types")

    def test_no_show_analytics_by_channel_structure(self, auth_headers):
        """Verify by_channel field has correct structure"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        by_channel = data.get("by_channel", [])
        
        for ch_entry in by_channel:
            assert "channel" in ch_entry, "Missing channel field"
            assert "count" in ch_entry, "Missing count field"
            assert "revenue_loss" in ch_entry, "Missing revenue_loss field"
        
        print(f"✓ by_channel structure valid with {len(by_channel)} channels")

    def test_no_show_analytics_recent_structure(self, auth_headers):
        """Verify recent field has correct structure"""
        response = requests.get(
            f"{BASE_URL}/pms/no-show-analytics?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        recent = data.get("recent", [])
        
        for rec in recent:
            assert "id" in rec, "Missing id field in recent entry"
            assert "guest_name" in rec, "Missing guest_name field"
            assert "room_type" in rec, "Missing room_type field"
            assert "channel" in rec, "Missing channel field"
            assert "reason" in rec, "Missing reason field"
            assert "reason_label" in rec, "Missing reason_label field"
            assert "amount" in rec, "Missing amount field"
            assert "date" in rec, "Missing date field"
        
        print(f"✓ recent structure valid with {len(recent)} entries")


class TestNoShowVirtualEndpoint:
    """Test No-Show Virtual Room Assignment endpoint"""

    def test_no_show_virtual_endpoint_exists(self, auth_headers):
        """POST /api/pms/bookings/no-show-virtual endpoint exists"""
        # Test with invalid booking_id to verify endpoint exists
        response = requests.post(
            f"{BASE_URL}/pms/bookings/no-show-virtual",
            json={"booking_id": "invalid_booking_id_12345"},
            headers=auth_headers
        )
        # Should return 404 for invalid booking, not 405 (method not allowed)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        print(f"✓ No-show virtual endpoint exists (returned {response.status_code} for invalid booking)")

    def test_no_show_virtual_accepts_reason_field(self, auth_headers):
        """POST /api/pms/bookings/no-show-virtual accepts no_show_reason field"""
        # Test with invalid booking but valid reason to verify field is accepted
        response = requests.post(
            f"{BASE_URL}/pms/bookings/no-show-virtual",
            json={
                "booking_id": "invalid_booking_id_12345",
                "charge_first_night": False,
                "no_show_reason": "misafir_gelmedi"
            },
            headers=auth_headers
        )
        # Should return 404 for invalid booking, not 422 (validation error)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}: {response.text}"
        print(f"✓ No-show virtual endpoint accepts no_show_reason field")

    def test_no_show_virtual_all_reason_values(self, auth_headers):
        """POST /api/pms/bookings/no-show-virtual accepts all valid reason values"""
        valid_reasons = ["misafir_gelmedi", "iptal_gec_islendi", "overbooking"]
        
        for reason in valid_reasons:
            response = requests.post(
                f"{BASE_URL}/pms/bookings/no-show-virtual",
                json={
                    "booking_id": "invalid_booking_id_12345",
                    "charge_first_night": False,
                    "no_show_reason": reason
                },
                headers=auth_headers
            )
            # Should return 404 for invalid booking, not 422 (validation error)
            assert response.status_code in [404, 400], f"Reason '{reason}' failed: {response.status_code}"
        
        print(f"✓ All valid reasons accepted: {valid_reasons}")


class TestNoShowWithRealBooking:
    """Test No-Show with real booking data (if available)"""

    def test_find_confirmed_booking_for_noshow(self, auth_headers):
        """Find a confirmed booking that can be marked as no-show"""
        # Get bookings
        response = requests.get(
            f"{BASE_URL}/pms/bookings?status=confirmed&limit=10",
            headers=auth_headers
        )
        
        if response.status_code != 200:
            pytest.skip("Could not fetch bookings")
        
        bookings = response.json()
        if not bookings:
            pytest.skip("No confirmed bookings available for testing")
        
        # Find a booking without room_id (unassigned) for safer testing
        unassigned = [b for b in bookings if not b.get("room_id")]
        if unassigned:
            print(f"✓ Found {len(unassigned)} unassigned confirmed bookings for potential no-show testing")
        else:
            print(f"✓ Found {len(bookings)} confirmed bookings (all assigned)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
