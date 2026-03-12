"""
System Health Normalized API Tests
Tests the normalized health endpoints, role-based dashboard, and service-wired domain endpoints.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Auth credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestAuth:
    """Authentication and token tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]
    
    def test_login_success(self):
        """Test login with demo credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0


class TestNormalizedHealthEndpoints:
    """Test the normalized health API endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for API calls"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_role_dashboard_endpoint(self, auth_headers):
        """Test /api/system-health/role-dashboard returns role, scope, panels"""
        response = requests.get(f"{BASE_URL}/api/system-health/role-dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate required fields
        assert "role" in data, f"Missing 'role' field: {data}"
        assert "scope" in data, f"Missing 'scope' field: {data}"
        assert "panels" in data, f"Missing 'panels' field: {data}"
        assert "tenant_id" in data, f"Missing 'tenant_id' field: {data}"
        
        # Validate panels structure
        assert isinstance(data["panels"], dict)
        print(f"Role dashboard response: role={data['role']}, scope={data['scope']}, panels={list(data['panels'].keys())}")
    
    def test_normalized_overview_endpoint(self, auth_headers):
        """Test /api/system-health/normalized/overview returns overall_status, subsystems"""
        response = requests.get(f"{BASE_URL}/api/system-health/normalized/overview", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate required fields
        assert "overall_status" in data, f"Missing 'overall_status': {data}"
        assert "overall_severity" in data, f"Missing 'overall_severity': {data}"
        assert "subsystems" in data, f"Missing 'subsystems': {data}"
        assert "last_updated_at" in data, f"Missing 'last_updated_at': {data}"
        assert "live_capable" in data, f"Missing 'live_capable': {data}"
        
        # Validate subsystems structure
        subsystems = data["subsystems"]
        assert "channel_manager" in subsystems
        assert "workers" in subsystems
        assert "security" in subsystems
        assert "observability" in subsystems
        
        print(f"Normalized overview: status={data['overall_status']}, severity={data['overall_severity']}")
    
    def test_normalized_channel_manager_endpoint(self, auth_headers):
        """Test /api/system-health/normalized/channel-manager returns standardized fields"""
        response = requests.get(f"{BASE_URL}/api/system-health/normalized/channel-manager", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate standardized health response fields
        required_fields = ["status", "severity", "scope_type", "last_updated_at", "live_capable", "detail"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' field: {data}"
        
        # Validate suggested_action and action_available
        assert "action_available" in data
        assert "suggested_action" in data
        
        print(f"Channel manager normalized: status={data['status']}, severity={data['severity']}, scope={data['scope_type']}")
    
    def test_normalized_workers_endpoint(self, auth_headers):
        """Test /api/system-health/normalized/workers returns standardized health fields"""
        response = requests.get(f"{BASE_URL}/api/system-health/normalized/workers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate standardized health response fields
        required_fields = ["status", "severity", "scope_type", "scope_id", "last_updated_at", "live_capable", "detail"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' field: {data}"
        
        print(f"Workers normalized: status={data['status']}, severity={data['severity']}")
    
    def test_normalized_security_endpoint(self, auth_headers):
        """Test /api/system-health/normalized/security returns standardized health fields"""
        response = requests.get(f"{BASE_URL}/api/system-health/normalized/security", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate standardized health response fields
        required_fields = ["status", "severity", "scope_type", "scope_id", "last_updated_at", "live_capable", "detail"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' field: {data}"
        
        print(f"Security normalized: status={data['status']}, severity={data['severity']}")


class TestServiceWiredEndpoints:
    """Test service-wired domain endpoints (frontdesk, night_audit)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for API calls"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_arrivals_today_endpoint(self, auth_headers):
        """Test /api/arrivals/today returns arrivals array (service-wired)"""
        response = requests.get(f"{BASE_URL}/api/arrivals/today", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return arrivals data (could be list or dict with arrivals)
        assert data is not None
        print(f"Arrivals today: {type(data).__name__}")
    
    def test_unified_today_arrivals_endpoint(self, auth_headers):
        """Test /api/unified/today-arrivals returns arrivals (service-wired)"""
        response = requests.get(f"{BASE_URL}/api/unified/today-arrivals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return arrivals data
        assert data is not None
        print(f"Unified arrivals: {type(data).__name__}")
    
    def test_frontdesk_audit_checklist_endpoint(self, auth_headers):
        """Test /api/frontdesk/audit-checklist returns audit checklist data"""
        response = requests.get(f"{BASE_URL}/api/frontdesk/audit-checklist", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return checklist data
        assert data is not None
        print(f"Audit checklist: {type(data).__name__}")
    
    def test_audit_logs_endpoint(self, auth_headers):
        """Test /api/audit-logs returns logs with count (service-wired)"""
        response = requests.get(f"{BASE_URL}/api/audit-logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "logs" in data or isinstance(data, list), f"Unexpected response: {data}"
        if "logs" in data:
            assert "count" in data, f"Missing 'count' field: {data}"
            print(f"Audit logs: count={data.get('count', len(data.get('logs', [])))}")
        else:
            print(f"Audit logs: count={len(data)}")
    
    def test_error_logs_endpoint(self, auth_headers):
        """Test /api/logs/errors returns error logs (service-wired)"""
        response = requests.get(f"{BASE_URL}/api/logs/errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return logs data
        assert data is not None
        print(f"Error logs: {type(data).__name__}")
    
    def test_night_audit_logs_endpoint(self, auth_headers):
        """Test /api/logs/night-audit returns night audit logs (service-wired)"""
        response = requests.get(f"{BASE_URL}/api/logs/night-audit", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return logs data
        assert data is not None
        print(f"Night audit logs: {type(data).__name__}")


class TestChannelManagerHardening:
    """Test channel manager runtime endpoints (MOCKED)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for API calls"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_channel_manager_runtime_status(self, auth_headers):
        """Test /api/channel-manager/runtime/status (placeholder data)"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should have health-related fields
        assert "health" in data or "status" in data, f"Missing health field: {data}"
        print(f"CM runtime status: {data.get('health', data.get('status', 'unknown'))}")


class TestWorkerQueueHealth:
    """Test worker queue health endpoints (MOCKED)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for API calls"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_workers_queues_health(self, auth_headers):
        """Test /api/workers/queues/health (placeholder data)"""
        response = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should have health-related fields
        assert "health" in data or "status" in data, f"Missing health field: {data}"
        print(f"Workers queue health: {data.get('health', data.get('status', 'unknown'))}")


class TestSecurityEndpoints:
    """Test security runtime endpoints (MOCKED)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for API calls"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_security_audit_status(self, auth_headers):
        """Test /api/security/audit/status (placeholder data)"""
        response = requests.get(f"{BASE_URL}/api/security/audit/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        print(f"Security audit status: {type(data).__name__}")
    
    def test_security_rate_limit_status(self, auth_headers):
        """Test /api/security/rate-limit/status (placeholder data)"""
        response = requests.get(f"{BASE_URL}/api/security/rate-limit/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        print(f"Security rate limit status: {type(data).__name__}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
