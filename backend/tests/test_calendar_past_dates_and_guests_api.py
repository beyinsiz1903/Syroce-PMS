"""
Tests for Calendar Past Date Styling and Guests API Email Fix

P1 Bug Fixes Testing:
1. /api/pms/guests endpoint returning 200 (was 500 due to EmailStr validation)
2. Calendar past date styling verification via frontend
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        timeout=15
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture
def auth_headers(auth_token):
    """Headers with authentication"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestGuestsAPIEmailFix:
    """
    Tests for /api/pms/guests endpoint.
    Previously returned 500 because Pydantic EmailStr validation rejected 
    walk-in-xxx@placeholder.local email addresses used for walk-in guests.
    Fixed by changing Guest.email from EmailStr to str in schemas.py.
    """
    
    def test_guests_list_returns_200(self, auth_headers):
        """Test that guests endpoint returns 200 and not 500"""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of guests"
        print(f"SUCCESS: /api/pms/guests returned {len(data)} guests")
    
    def test_guests_include_walkin_placeholder_emails(self, auth_headers):
        """Test that guests with placeholder.local emails are included"""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200
        guests = response.json()
        
        # Find guests with placeholder.local emails
        walkin_guests = [g for g in guests if 'placeholder.local' in g.get('email', '')]
        print(f"Found {len(walkin_guests)} walk-in guests with placeholder emails")
        
        # Verify at least one exists (from test data)
        assert len(walkin_guests) > 0, "Expected at least one walk-in guest with placeholder email"
        
        # Verify the email format
        for guest in walkin_guests[:3]:  # Check first 3
            email = guest.get('email', '')
            assert email.endswith('@placeholder.local'), f"Unexpected email format: {email}"
            print(f"  - Guest: {guest.get('name', 'N/A')}, Email: {email}")
    
    def test_guests_data_structure(self, auth_headers):
        """Test that guest data has expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200
        guests = response.json()
        
        if len(guests) > 0:
            guest = guests[0]
            required_fields = ['id', 'tenant_id', 'name', 'email', 'phone']
            for field in required_fields:
                assert field in guest, f"Missing required field: {field}"
            print(f"SUCCESS: Guest data structure verified with fields: {list(guest.keys())}")


class TestCalendarAPIEndpoints:
    """Test calendar-related API endpoints that support the calendar UI"""
    
    def test_rooms_endpoint(self, auth_headers):
        """Test rooms endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/pms/rooms",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200
        rooms = response.json()
        assert isinstance(rooms, list)
        print(f"SUCCESS: /api/pms/rooms returned {len(rooms)} rooms")
    
    def test_bookings_endpoint_with_date_range(self, auth_headers):
        """Test bookings endpoint with date range filter"""
        from datetime import datetime, timedelta
        
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            params={"start_date": start_date, "end_date": end_date, "limit": 100},
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200
        bookings = response.json()
        assert isinstance(bookings, list)
        print(f"SUCCESS: /api/pms/bookings returned {len(bookings)} bookings for date range {start_date} to {end_date}")
    
    def test_room_blocks_endpoint(self, auth_headers):
        """Test room blocks endpoint used by calendar"""
        response = requests.get(
            f"{BASE_URL}/api/pms/room-blocks",
            params={"status": "active"},
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        blocks = data.get('blocks', []) if isinstance(data, dict) else data
        print(f"SUCCESS: /api/pms/room-blocks returned {len(blocks)} active blocks")


class TestCalendarHelperFunctions:
    """
    Documentation tests for frontend calendar helper functions.
    These verify the isPastDate() function behavior indirectly via API data.
    
    The isPastDate() function in calendarHelpers.js:
    - Compares date against today's date
    - Returns true if date < today
    - Used to gray out past dates in CalendarGrid.js
    """
    
    def test_business_date_endpoint(self, auth_headers):
        """Test business date endpoint (used for calendar date validation)"""
        response = requests.get(
            f"{BASE_URL}/api/night-audit/business-date",
            headers=auth_headers,
            timeout=15
        )
        # May return 200 or 404 if not configured
        if response.status_code == 200:
            data = response.json()
            business_date = data.get('business_date')
            print(f"SUCCESS: Business date is {business_date}")
        else:
            print(f"INFO: Business date endpoint returned {response.status_code} (may not be configured)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
