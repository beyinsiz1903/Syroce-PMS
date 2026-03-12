"""
Tests for Backend Router Modularization - server.py split into routers/
Tests auth, housekeeping, and department endpoints after extraction.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSetup:
    """Initial setup and credentials"""
    
    @pytest.fixture(scope="class")
    def demo_token(self):
        """Get auth token using demo credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed - demo@hotel.com not available")
        return None
    
    @pytest.fixture(scope="class")
    def housekeeping_token(self):
        """Get auth token for housekeeping user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "housekeeping@hotel.com",
            "password": "staff123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        # Skip if housekeeping user doesn't exist
        return None
    
    @pytest.fixture
    def auth_headers(self, demo_token):
        """Return headers with demo user auth token"""
        return {"Authorization": f"Bearer {demo_token}"}


class TestAuthRouter(TestSetup):
    """Test auth router endpoints extracted from server.py"""
    
    def test_login_success(self):
        """Test /api/auth/login works after router extraction"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "Response missing access_token"
        assert "user" in data, "Response missing user object"
        assert data["user"]["email"] == "demo@hotel.com"
        print(f"✅ Auth login works - user: {data['user']['name']}")
    
    def test_login_invalid_credentials(self):
        """Test login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Invalid credentials correctly rejected")
    
    def test_auth_me_endpoint(self, auth_headers):
        """Test /api/auth/me returns current user"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200, f"/auth/me failed: {response.text}"
        
        data = response.json()
        assert "email" in data
        assert data["email"] == "demo@hotel.com"
        print(f"✅ Auth /me endpoint works - {data['email']}")
    
    def test_security_summary_endpoint(self, auth_headers):
        """Test /api/security/summary extracted to auth router"""
        response = requests.get(f"{BASE_URL}/api/security/summary", headers=auth_headers)
        assert response.status_code == 200, f"/security/summary failed: {response.text}"
        
        data = response.json()
        assert "overview" in data, "Response missing overview"
        assert "failed_logins_24h" in data.get("overview", {})
        print(f"✅ Security summary works - failed logins 24h: {data['overview'].get('failed_logins_24h', 0)}")


class TestHousekeepingRouter(TestSetup):
    """Test housekeeping router endpoints extracted from server.py"""
    
    def test_housekeeping_tasks(self, auth_headers):
        """Test /api/housekeeping/tasks endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/tasks", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/tasks failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of tasks"
        print(f"✅ Housekeeping tasks works - {len(data)} tasks found")
    
    def test_housekeeping_room_status(self, auth_headers):
        """Test /api/housekeeping/room-status endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/room-status", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/room-status failed: {response.text}"
        
        data = response.json()
        assert "rooms" in data, "Response missing rooms"
        assert "status_counts" in data, "Response missing status_counts"
        assert "total_rooms" in data, "Response missing total_rooms"
        print(f"✅ Room status works - {data['total_rooms']} total rooms")
    
    def test_housekeeping_due_out(self, auth_headers):
        """Test /api/housekeeping/due-out endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/due-out", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/due-out failed: {response.text}"
        
        data = response.json()
        assert "due_out_rooms" in data
        assert "count" in data
        print(f"✅ Due-out endpoint works - {data['count']} rooms due out")
    
    def test_housekeeping_stayovers(self, auth_headers):
        """Test /api/housekeeping/stayovers endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/stayovers", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/stayovers failed: {response.text}"
        
        data = response.json()
        assert "stayover_rooms" in data
        assert "count" in data
        print(f"✅ Stayovers endpoint works - {data['count']} stayover rooms")
    
    def test_housekeeping_room_status_report(self, auth_headers):
        """Test /api/housekeeping/room-status-report endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/room-status-report", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/room-status-report failed: {response.text}"
        
        data = response.json()
        assert "summary" in data, "Response missing summary"
        assert "dnd_rooms" in data
        assert "sleep_out" in data
        assert "out_of_order" in data
        print(f"✅ Room status report works - {data['summary'].get('total_rooms', 0)} rooms")
    
    def test_housekeeping_staff_performance(self, auth_headers):
        """Test /api/housekeeping/staff-performance-detailed endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/staff-performance-detailed", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/staff-performance-detailed failed: {response.text}"
        
        data = response.json()
        assert "staff_performance" in data
        assert "total_staff" in data
        print(f"✅ Staff performance works - {data['total_staff']} staff members")
    
    def test_housekeeping_arrivals(self, auth_headers):
        """Test /api/housekeeping/arrivals endpoint"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/arrivals", headers=auth_headers)
        assert response.status_code == 200, f"/housekeeping/arrivals failed: {response.text}"
        
        data = response.json()
        assert "arrival_rooms" in data
        assert "count" in data
        print(f"✅ Arrivals endpoint works - {data['count']} arrivals")


class TestDepartmentRouter(TestSetup):
    """Test department dashboard endpoints extracted from server.py"""
    
    def test_front_office_dashboard(self, auth_headers):
        """Test /api/department/front-office/dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/department/front-office/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/department/front-office/dashboard failed: {response.text}"
        
        data = response.json()
        assert "checkins_today" in data, "Response missing checkins_today"
        assert "total_checkins" in data
        print(f"✅ Front office dashboard works - {data['total_checkins']} check-ins today")
    
    def test_housekeeping_manager_dashboard(self, auth_headers):
        """Test /api/department/housekeeping/dashboard endpoint (renamed from housekeeping-manager)"""
        response = requests.get(f"{BASE_URL}/api/department/housekeeping/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/department/housekeeping/dashboard failed: {response.text}"
        
        data = response.json()
        assert "status_summary" in data
        assert "dirty_rooms_list" in data
        assert "cleaning_rooms_list" in data
        print(f"✅ HK manager dashboard works - {data['status_summary'].get('dirty', 0)} dirty rooms")
    
    def test_finance_dashboard(self, auth_headers):
        """Test /api/department/finance/dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/department/finance/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/department/finance/dashboard failed: {response.text}"
        
        data = response.json()
        assert "ar_summary" in data
        assert "integrations" in data
        print(f"✅ Finance dashboard works - {data['ar_summary'].get('pending_invoices', 0)} pending invoices")
    
    def test_it_system_info(self, auth_headers):
        """Test /api/department/it/system-info endpoint"""
        response = requests.get(f"{BASE_URL}/api/department/it/system-info", headers=auth_headers)
        assert response.status_code == 200, f"/department/it/system-info failed: {response.text}"
        
        data = response.json()
        assert "api_architecture" in data
        assert "scalability" in data
        print(f"✅ IT system info works - API type: {data['api_architecture'].get('type')}")
    
    def test_ai_activity_feed(self, auth_headers):
        """Test /api/ai/activity-feed endpoint"""
        response = requests.get(f"{BASE_URL}/api/ai/activity-feed", headers=auth_headers)
        assert response.status_code == 200, f"/ai/activity-feed failed: {response.text}"
        
        data = response.json()
        assert "activities" in data
        assert "total_count" in data
        print(f"✅ AI activity feed works - {data['total_count']} activities")
    
    def test_ai_dashboard_briefing(self, auth_headers):
        """Test /api/ai/dashboard/briefing endpoint"""
        response = requests.get(f"{BASE_URL}/api/ai/dashboard/briefing", headers=auth_headers)
        assert response.status_code == 200, f"/ai/dashboard/briefing failed: {response.text}"
        
        data = response.json()
        assert "summary" in data or "briefing" in data
        assert "metrics" in data
        print(f"✅ AI briefing works - occupancy: {data['metrics'].get('occupancy_rate', 0)}%")


class TestMainServerEndpoints(TestSetup):
    """Test endpoints that remained in server.py after extraction"""
    
    def test_pms_dashboard(self, auth_headers):
        """Test /api/pms/dashboard still works from main server.py"""
        response = requests.get(f"{BASE_URL}/api/pms/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/pms/dashboard failed: {response.text}"
        
        data = response.json()
        assert "total_rooms" in data or "rooms" in data
        print("✅ PMS dashboard works")


class TestRoomBlocks(TestSetup):
    """Test room block endpoints in housekeeping router"""
    
    def test_get_room_blocks(self, auth_headers):
        """Test /api/pms/room-blocks endpoint"""
        response = requests.get(f"{BASE_URL}/api/pms/room-blocks", headers=auth_headers)
        assert response.status_code == 200, f"/pms/room-blocks failed: {response.text}"
        
        data = response.json()
        # API returns either a list or {"blocks": [...], "count": ...}
        if isinstance(data, list):
            print(f"✅ Room blocks works - {len(data)} blocks found (list format)")
        else:
            assert "blocks" in data
            print(f"✅ Room blocks works - {data.get('count', len(data.get('blocks', [])))} blocks found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
