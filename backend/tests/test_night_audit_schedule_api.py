"""
Night Audit Schedule API Tests
Tests for automatic midnight scheduling feature: GET/PUT /api/night-audit/schedule, GET /api/night-audit/schedule/status
"""
import pytest
import requests
import os

# Use VITE_BACKEND_URL from environment
BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestNightAuditScheduleAPI:
    """Night Audit Schedule API endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        token_data = login_response.json()
        access_token = token_data.get("access_token")
        assert access_token, f"No access_token in response: {token_data}"
        
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})
        yield
        # Cleanup - disable schedule after tests
        try:
            self.session.put(
                f"{BASE_URL}/api/night-audit/schedule",
                json={"enabled": False}
            )
        except:
            pass
    
    # ── GET /api/night-audit/schedule Tests ────────────────────────────────
    def test_get_schedule_returns_default_config(self):
        """GET /api/night-audit/schedule returns default schedule config"""
        response = self.session.get(f"{BASE_URL}/api/night-audit/schedule")
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "enabled" in data, "Response should contain 'enabled' field"
        assert "scheduled_hour" in data, "Response should contain 'scheduled_hour' field"
        assert "scheduled_minute" in data, "Response should contain 'scheduled_minute' field"
        assert "timezone" in data, "Response should contain 'timezone' field"
        assert "skip_validations" in data, "Response should contain 'skip_validations' field"
        assert "auto_retry" in data, "Response should contain 'auto_retry' field"
        
        # Validate data types
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
        assert isinstance(data["scheduled_hour"], int), "scheduled_hour should be integer"
        assert isinstance(data["scheduled_minute"], int), "scheduled_minute should be integer"
        assert isinstance(data["timezone"], str), "timezone should be string"
        
        print(f"✓ GET /api/night-audit/schedule returned config: enabled={data['enabled']}, time={data['scheduled_hour']}:{data['scheduled_minute']}")
    
    def test_get_schedule_without_auth_fails(self):
        """GET /api/night-audit/schedule without authentication returns 401"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/night-audit/schedule")
        
        # Should return 401 or 403 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ GET /api/night-audit/schedule without auth returns 401/403")
    
    # ── PUT /api/night-audit/schedule Tests ────────────────────────────────
    def test_update_schedule_enable(self):
        """PUT /api/night-audit/schedule enables scheduler"""
        schedule_config = {
            "enabled": True,
            "scheduled_hour": 23,
            "scheduled_minute": 30,
            "timezone": "Europe/Istanbul",
            "skip_validations": False,
            "auto_retry": True,
            "max_retries": 3,
            "notify_on_complete": True,
            "notify_on_failure": True
        }
        
        response = self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json=schedule_config
        )
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data["enabled"] == True, "enabled should be True"
        assert data["scheduled_hour"] == 23, "scheduled_hour should be 23"
        assert data["scheduled_minute"] == 30, "scheduled_minute should be 30"
        assert data["timezone"] == "Europe/Istanbul", "timezone should be Europe/Istanbul"
        assert data["auto_retry"] == True, "auto_retry should be True"
        assert data["max_retries"] == 3, "max_retries should be 3"
        
        print(f"✓ PUT /api/night-audit/schedule enabled at {data['scheduled_hour']}:{data['scheduled_minute']}")
        
        # Verify persistence with GET
        get_response = self.session.get(f"{BASE_URL}/api/night-audit/schedule")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["enabled"] == True, "Schedule should persist as enabled"
        assert get_data["scheduled_hour"] == 23, "Hour should persist"
        print("✓ Schedule change persisted correctly")
    
    def test_update_schedule_disable(self):
        """PUT /api/night-audit/schedule disables scheduler"""
        # First enable
        self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json={"enabled": True, "scheduled_hour": 0, "scheduled_minute": 0}
        )
        
        # Then disable
        response = self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json={"enabled": False}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == False, "enabled should be False"
        
        print("✓ PUT /api/night-audit/schedule disabled successfully")
    
    def test_update_schedule_change_timezone(self):
        """PUT /api/night-audit/schedule updates timezone"""
        timezones = ["Europe/Istanbul", "Europe/Berlin", "UTC", "Europe/London"]
        
        for tz in timezones:
            response = self.session.put(
                f"{BASE_URL}/api/night-audit/schedule",
                json={"timezone": tz}
            )
            assert response.status_code == 200, f"Failed for timezone {tz}"
            data = response.json()
            assert data["timezone"] == tz, f"timezone should be {tz}"
        
        print(f"✓ PUT /api/night-audit/schedule updated timezones: {timezones}")
    
    def test_update_schedule_retry_settings(self):
        """PUT /api/night-audit/schedule updates retry settings"""
        response = self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json={
                "auto_retry": True,
                "max_retries": 5,
                "skip_validations": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["auto_retry"] == True, "auto_retry should be True"
        assert data["max_retries"] == 5, "max_retries should be 5"
        assert data["skip_validations"] == True, "skip_validations should be True"
        
        print("✓ PUT /api/night-audit/schedule updated retry settings")
    
    def test_update_schedule_without_auth_fails(self):
        """PUT /api/night-audit/schedule without authentication returns 401"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        response = no_auth_session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json={"enabled": True}
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ PUT /api/night-audit/schedule without auth returns 401/403")
    
    # ── GET /api/night-audit/schedule/status Tests ─────────────────────────
    def test_get_schedule_status(self):
        """GET /api/night-audit/schedule/status returns scheduler status and logs"""
        response = self.session.get(f"{BASE_URL}/api/night-audit/schedule/status")
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "enabled" in data, "Response should contain 'enabled' field"
        assert "scheduled_hour" in data, "Response should contain 'scheduled_hour' field"
        assert "scheduled_minute" in data, "Response should contain 'scheduled_minute' field"
        assert "timezone" in data, "Response should contain 'timezone' field"
        assert "recent_logs" in data, "Response should contain 'recent_logs' field"
        
        # Validate types
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
        assert isinstance(data["recent_logs"], list), "recent_logs should be a list"
        
        print(f"✓ GET /api/night-audit/schedule/status: enabled={data['enabled']}, logs_count={len(data['recent_logs'])}")
    
    def test_get_schedule_status_contains_last_auto_run(self):
        """GET /api/night-audit/schedule/status contains last_auto_run field"""
        response = self.session.get(f"{BASE_URL}/api/night-audit/schedule/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # These fields may be null if never run, but should exist
        assert "last_auto_run" in data, "Response should contain 'last_auto_run' field"
        assert "last_auto_run_status" in data, "Response should contain 'last_auto_run_status' field"
        
        print(f"✓ GET /api/night-audit/schedule/status has last_auto_run fields")
    
    def test_get_schedule_status_without_auth_fails(self):
        """GET /api/night-audit/schedule/status without authentication returns 401"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/night-audit/schedule/status")
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ GET /api/night-audit/schedule/status without auth returns 401/403")
    
    # ── Existing Night Audit Endpoints Still Work ──────────────────────────
    def test_existing_business_date_endpoint(self):
        """GET /api/night-audit/business-date still works"""
        response = self.session.get(f"{BASE_URL}/api/night-audit/business-date")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "business_date" in data, "Response should contain 'business_date'"
        print(f"✓ GET /api/night-audit/business-date: {data['business_date']}")
    
    def test_existing_history_endpoint(self):
        """GET /api/night-audit/history still works"""
        response = self.session.get(f"{BASE_URL}/api/night-audit/history")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "runs" in data, "Response should contain 'runs'"
        assert "total" in data, "Response should contain 'total'"
        assert isinstance(data["runs"], list), "runs should be a list"
        print(f"✓ GET /api/night-audit/history: {data['total']} total runs")


class TestNightAuditScheduleIntegration:
    """Integration tests for schedule feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert login_response.status_code == 200
        
        token_data = login_response.json()
        access_token = token_data.get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})
        yield
        # Cleanup - disable schedule
        try:
            self.session.put(
                f"{BASE_URL}/api/night-audit/schedule",
                json={"enabled": False}
            )
        except:
            pass
    
    def test_full_schedule_workflow(self):
        """Test complete schedule workflow: GET default -> PUT update -> GET verify -> GET status"""
        # Step 1: Get default schedule
        get_default = self.session.get(f"{BASE_URL}/api/night-audit/schedule")
        assert get_default.status_code == 200
        default_data = get_default.json()
        print(f"Step 1: Default schedule - enabled={default_data.get('enabled')}")
        
        # Step 2: Update schedule with custom settings
        update_config = {
            "enabled": True,
            "scheduled_hour": 2,
            "scheduled_minute": 15,
            "timezone": "Europe/Istanbul",
            "skip_validations": False,
            "auto_retry": True,
            "max_retries": 2
        }
        put_response = self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json=update_config
        )
        assert put_response.status_code == 200
        put_data = put_response.json()
        assert put_data["enabled"] == True
        assert put_data["scheduled_hour"] == 2
        print(f"Step 2: Updated schedule - {put_data['scheduled_hour']}:{put_data['scheduled_minute']}")
        
        # Step 3: Verify with GET
        get_verify = self.session.get(f"{BASE_URL}/api/night-audit/schedule")
        assert get_verify.status_code == 200
        verify_data = get_verify.json()
        assert verify_data["enabled"] == True
        assert verify_data["scheduled_hour"] == 2
        assert verify_data["scheduled_minute"] == 15
        print(f"Step 3: Verified schedule persisted correctly")
        
        # Step 4: Check status endpoint
        status_response = self.session.get(f"{BASE_URL}/api/night-audit/schedule/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["enabled"] == True
        assert "recent_logs" in status_data
        print(f"Step 4: Status endpoint shows enabled={status_data['enabled']}, logs={len(status_data['recent_logs'])}")
        
        # Step 5: Disable schedule
        disable_response = self.session.put(
            f"{BASE_URL}/api/night-audit/schedule",
            json={"enabled": False}
        )
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] == False
        print(f"Step 5: Schedule disabled successfully")
        
        print("✓ Full schedule workflow completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
