"""
Test Suite: README Files and Past-Date Booking Validation
Tests:
1. README files contain correct tech stack info (Syroce PMS, React 19, Python 3.11+, Node 20+, MongoDB 7.0+)
2. Past-date booking rejection works correctly
3. Future-date booking succeeds
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestReadmeFiles:
    """Verify README files contain correct tech stack information"""
    
    def test_root_readme_exists_and_has_syroce_pms(self):
        """Root README.md should say 'Syroce PMS' not 'RoomOps'"""
        readme_path = '/app/README.md'
        assert os.path.exists(readme_path), "Root README.md should exist"
        
        with open(readme_path, 'r') as f:
            content = f.read()
        
        # Should contain Syroce PMS
        assert 'Syroce PMS' in content, "README should mention 'Syroce PMS'"
        # Should NOT contain RoomOps
        assert 'RoomOps' not in content, "README should NOT mention 'RoomOps'"
        
    def test_root_readme_has_react_19(self):
        """Root README.md should mention React 19"""
        with open('/app/README.md', 'r') as f:
            content = f.read()
        assert 'React' in content and '19' in content, "README should mention React 19"
        
    def test_root_readme_has_python_311(self):
        """Root README.md should mention Python 3.11+"""
        with open('/app/README.md', 'r') as f:
            content = f.read()
        assert 'Python' in content and '3.11' in content, "README should mention Python 3.11+"
        
    def test_root_readme_has_node_20(self):
        """Root README.md should mention Node.js 20+"""
        with open('/app/README.md', 'r') as f:
            content = f.read()
        assert 'Node' in content and '20' in content, "README should mention Node.js 20+"
        
    def test_root_readme_has_mongodb_70(self):
        """Root README.md should mention MongoDB 7.0+"""
        with open('/app/README.md', 'r') as f:
            content = f.read()
        assert 'MongoDB' in content and '7.0' in content, "README should mention MongoDB 7.0+"
        
    def test_backend_readme_exists(self):
        """Backend README.md should exist at /app/backend/README.md"""
        readme_path = '/app/backend/README.md'
        assert os.path.exists(readme_path), "Backend README.md should exist"
        
    def test_backend_readme_has_syroce_pms(self):
        """Backend README.md should say 'Syroce PMS'"""
        with open('/app/backend/README.md', 'r') as f:
            content = f.read()
        assert 'Syroce PMS' in content, "Backend README should mention 'Syroce PMS'"
        
    def test_backend_readme_has_python_311(self):
        """Backend README.md should mention Python 3.11+"""
        with open('/app/backend/README.md', 'r') as f:
            content = f.read()
        assert 'Python 3.11' in content, "Backend README should mention Python 3.11+"
        
    def test_backend_readme_has_mongodb_70(self):
        """Backend README.md should mention MongoDB 7.0+"""
        with open('/app/backend/README.md', 'r') as f:
            content = f.read()
        assert 'MongoDB 7.0' in content, "Backend README should mention MongoDB 7.0+"
        
    def test_frontend_readme_exists(self):
        """Frontend README.md should exist"""
        readme_path = '/app/frontend/README.md'
        assert os.path.exists(readme_path), "Frontend README.md should exist"
        
    def test_frontend_readme_has_react_19(self):
        """Frontend README.md should mention React 19"""
        with open('/app/frontend/README.md', 'r') as f:
            content = f.read()
        assert 'React 19' in content, "Frontend README should mention React 19"


class TestBookingDateValidation:
    """Test past-date booking rejection and future-date booking success"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture
    def test_room_id(self, auth_token):
        """Get a valid room ID for testing"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=headers)
        if response.status_code == 200:
            rooms = response.json()
            if isinstance(rooms, list) and len(rooms) > 0:
                return rooms[0].get('id')
        return None
    
    def test_past_date_booking_rejected(self, auth_token, test_room_id):
        """POST /api/pms/quick-booking with past date check_in should return error"""
        if not test_room_id:
            pytest.skip("No room available for testing")
        
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4())
        }
        
        # Use a past date (2 days ago)
        past_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT14:00:00+00:00")
        checkout_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT11:00:00+00:00")
        
        booking_data = {
            "guest_name": "TEST Past Date Guest",
            "room_id": test_room_id,
            "check_in": past_date,
            "check_out": checkout_date,
            "total_amount": 100.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/pms/quick-booking",
            headers=headers,
            json=booking_data
        )
        
        # Should return 400 Bad Request
        assert response.status_code == 400, f"Expected 400 for past date booking, got {response.status_code}: {response.text}"
        
        # Should contain Turkish error message "Gecmis tarihe rezervasyon yapilamaz"
        response_text = response.text.lower()
        assert "gecmis" in response_text, \
            f"Error message should mention past date restriction: {response.text}"
    
    def test_future_date_booking_succeeds(self, auth_token, test_room_id):
        """POST /api/pms/quick-booking with future dates should create booking"""
        if not test_room_id:
            pytest.skip("No room available for testing")
        
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4())
        }
        
        # Use future dates (30 days from now)
        checkin_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT14:00:00+00:00")
        checkout_date = (datetime.now() + timedelta(days=32)).strftime("%Y-%m-%dT11:00:00+00:00")
        
        booking_data = {
            "guest_name": "TEST Future Date Guest",
            "room_id": test_room_id,
            "check_in": checkin_date,
            "check_out": checkout_date,
            "total_amount": 200.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/pms/quick-booking",
            headers=headers,
            json=booking_data
        )
        
        # Should succeed (200 or 201)
        assert response.status_code in [200, 201], \
            f"Expected 200/201 for future date booking, got {response.status_code}: {response.text}"
        
        # Should return booking data
        data = response.json()
        assert 'id' in data, "Response should contain booking ID"


class TestLoginAndDashboard:
    """Test login flow and dashboard access"""
    
    def test_login_with_demo_credentials(self):
        """Login with demo@hotel.com / demo123 should work"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Should return token
        assert 'access_token' in data or 'token' in data, "Response should contain access token"
        
        # Should return user info
        assert 'user' in data, "Response should contain user info"
    
    def test_dashboard_stats_accessible(self):
        """Dashboard should be accessible after login"""
        # First login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_response.status_code == 200
        token = login_response.json().get('access_token') or login_response.json().get('token')
        
        # Access dashboard stats
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try rooms endpoint (part of dashboard data) - correct endpoint is /api/pms/rooms
        rooms_response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=headers)
        assert rooms_response.status_code == 200, f"Rooms endpoint failed: {rooms_response.text}"
        
        # Try guests endpoint - correct endpoint is /api/pms/guests
        guests_response = requests.get(f"{BASE_URL}/api/pms/guests", headers=headers)
        assert guests_response.status_code == 200, f"Guests endpoint failed: {guests_response.text}"
