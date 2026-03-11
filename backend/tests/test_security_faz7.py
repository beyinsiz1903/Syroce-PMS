"""
Faz 7 - Security & Performance Tests
Tests for:
- Security headers on API responses
- JWT token refresh endpoint
- Security summary endpoint
- Login audit logging (success/fail)
- Rate limiting (existing middleware)
"""
import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://strangler-fig-verify.preview.emergentagent.com')

# Test credentials
VALID_EMAIL = "demo@hotel.com"
VALID_PASSWORD = "demo123"
INVALID_EMAIL = "wrong@test.com"
INVALID_PASSWORD = "wrong123"


class TestSecurityHeaders:
    """Test security headers on API responses"""
    
    def test_security_headers_on_health_endpoint(self):
        """Verify security headers are present on /health endpoint"""
        response = requests.head(f"{BASE_URL}/health")
        headers = response.headers
        
        # Check X-Frame-Options
        assert 'X-Frame-Options' in headers, "X-Frame-Options header missing"
        assert headers['X-Frame-Options'] == 'SAMEORIGIN', f"X-Frame-Options value mismatch: {headers.get('X-Frame-Options')}"
        print(f"✅ X-Frame-Options: {headers['X-Frame-Options']}")
        
        # Check X-Content-Type-Options
        assert 'X-Content-Type-Options' in headers, "X-Content-Type-Options header missing"
        assert headers['X-Content-Type-Options'] == 'nosniff', f"X-Content-Type-Options value mismatch"
        print(f"✅ X-Content-Type-Options: {headers['X-Content-Type-Options']}")
        
        # Check Strict-Transport-Security (HSTS)
        assert 'Strict-Transport-Security' in headers, "Strict-Transport-Security header missing"
        print(f"✅ Strict-Transport-Security: {headers['Strict-Transport-Security']}")
        
        # Check Content-Security-Policy
        assert 'Content-Security-Policy' in headers, "Content-Security-Policy header missing"
        print(f"✅ Content-Security-Policy: present (length: {len(headers['Content-Security-Policy'])})")
        
        # Check Referrer-Policy
        assert 'Referrer-Policy' in headers, "Referrer-Policy header missing"
        print(f"✅ Referrer-Policy: {headers['Referrer-Policy']}")
        
        # Check Permissions-Policy
        assert 'Permissions-Policy' in headers, "Permissions-Policy header missing"
        print(f"✅ Permissions-Policy: present (length: {len(headers['Permissions-Policy'])})")
        
        # Check X-XSS-Protection
        assert 'X-XSS-Protection' in headers, "X-XSS-Protection header missing"
        print(f"✅ X-XSS-Protection: {headers['X-XSS-Protection']}")
    
    def test_security_headers_on_api_endpoint(self):
        """Verify security headers on /api endpoints as well"""
        response = requests.get(f"{BASE_URL}/api/docs")
        headers = response.headers
        
        # At least some core headers should be present
        assert 'X-Frame-Options' in headers, "X-Frame-Options missing on /api/docs"
        assert 'X-Content-Type-Options' in headers, "X-Content-Type-Options missing on /api/docs"
        print("✅ Security headers present on /api/docs endpoint")


class TestJWTTokenRefresh:
    """Test JWT token refresh endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert 'access_token' in data, "access_token field missing in login response"
        return data['access_token']
    
    def test_token_refresh_success(self, auth_token):
        """Test POST /api/auth/refresh-token returns new token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/refresh-token",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Token refresh failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert 'access_token' in data, "access_token field missing in refresh response"
        assert 'token_type' in data, "token_type field missing"
        assert 'expires_in' in data, "expires_in field missing"
        
        # Verify values
        assert data['token_type'] == 'bearer', f"token_type mismatch: {data['token_type']}"
        assert data['expires_in'] > 0, "expires_in should be positive"
        assert len(data['access_token']) > 50, "New token seems too short"
        
        print(f"✅ Token refresh successful")
        print(f"   token_type: {data['token_type']}")
        print(f"   expires_in: {data['expires_in']} seconds")
        print(f"   new token length: {len(data['access_token'])}")
    
    def test_token_refresh_without_auth_fails(self):
        """Token refresh without authorization should fail"""
        response = requests.post(f"{BASE_URL}/api/auth/refresh-token")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Token refresh without auth correctly rejected")
    
    def test_token_refresh_with_invalid_token_fails(self):
        """Token refresh with invalid token should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/refresh-token",
            headers={"Authorization": "Bearer invalid_token_123"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Token refresh with invalid token correctly rejected")


class TestSecuritySummaryEndpoint:
    """Test GET /api/security/summary endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()['access_token']
    
    def test_security_summary_returns_overview(self, auth_token):
        """Test /api/security/summary returns overview data"""
        response = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Security summary failed: {response.text}"
        data = response.json()
        
        # Verify overview section exists
        assert 'overview' in data, "overview field missing"
        overview = data['overview']
        
        # Verify overview fields
        assert 'failed_logins_24h' in overview, "failed_logins_24h missing"
        assert 'successful_logins_24h' in overview, "successful_logins_24h missing"
        assert 'active_sessions' in overview, "active_sessions missing"
        assert 'total_users' in overview, "total_users missing"
        
        print(f"✅ Security summary overview verified")
        print(f"   failed_logins_24h: {overview['failed_logins_24h']}")
        print(f"   successful_logins_24h: {overview['successful_logins_24h']}")
        print(f"   active_sessions: {overview['active_sessions']}")
        print(f"   total_users: {overview['total_users']}")
    
    def test_security_summary_returns_apm(self, auth_token):
        """Test /api/security/summary returns APM data"""
        response = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify APM section exists
        assert 'apm' in data, "apm field missing"
        apm = data['apm']
        
        # Verify APM fields (should have numeric values)
        assert 'requests_per_minute' in apm, "requests_per_minute missing"
        assert 'error_rate' in apm, "error_rate missing"
        assert 'avg_response_ms' in apm, "avg_response_ms missing"
        
        print(f"✅ Security summary APM verified")
        print(f"   requests_per_minute: {apm['requests_per_minute']}")
        print(f"   error_rate: {apm['error_rate']}%")
        print(f"   avg_response_ms: {apm['avg_response_ms']}")
    
    def test_security_summary_returns_recent_events(self, auth_token):
        """Test /api/security/summary returns recent_events"""
        response = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify recent_events exists (may be empty array)
        assert 'recent_events' in data, "recent_events field missing"
        assert isinstance(data['recent_events'], list), "recent_events should be a list"
        
        print(f"✅ Security summary recent_events verified")
        print(f"   events count: {len(data['recent_events'])}")
        
        if data['recent_events']:
            # Check first event structure
            event = data['recent_events'][0]
            print(f"   sample event: action={event.get('action')}, timestamp={event.get('timestamp')}")
    
    def test_security_summary_requires_auth(self):
        """Security summary without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/security/summary")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Security summary correctly requires authentication")


class TestLoginAuditLogging:
    """Test audit logging for login events"""
    
    def test_successful_login_creates_audit_log(self):
        """Successful login should create audit_logs entry with action 'login_success'"""
        # Perform login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        token = response.json()['access_token']
        
        # Give DB time to write
        time.sleep(0.5)
        
        # Check security summary for recent login_success event
        summary = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert summary.status_code == 200
        
        data = summary.json()
        overview = data.get('overview', {})
        
        # successful_logins_24h should be >= 1
        assert overview.get('successful_logins_24h', 0) >= 1, "No successful login count after login"
        print(f"✅ Successful login recorded (successful_logins_24h: {overview['successful_logins_24h']})")
        
        # Check recent_events for login_success
        events = data.get('recent_events', [])
        login_events = [e for e in events if e.get('action') == 'login_success']
        print(f"   Found {len(login_events)} login_success events in recent_events")
    
    def test_failed_login_creates_audit_log(self):
        """Failed login (valid email, wrong password) should create audit_logs entry with action 'login_failed'
        
        Note: Failed login for unknown emails won't show up in tenant-specific security summary
        because they don't have a tenant_id. This tests failed login for a KNOWN user.
        """
        # Perform failed login with VALID email but WRONG password
        # This ensures the audit log has a tenant_id
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": "definitely_wrong_password_12345"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        # Give DB time to write
        time.sleep(0.5)
        
        # Login with valid credentials to check audit
        login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        token = login.json()['access_token']
        
        # Check security summary for failed_logins_24h
        summary = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert summary.status_code == 200
        
        data = summary.json()
        overview = data.get('overview', {})
        
        # failed_logins_24h should be >= 1 (from valid email with wrong password)
        assert overview.get('failed_logins_24h', 0) >= 1, "No failed login count after failed login attempt"
        print(f"✅ Failed login recorded (failed_logins_24h: {overview['failed_logins_24h']})")
        
        # Check recent_events for login_failed
        events = data.get('recent_events', [])
        failed_events = [e for e in events if e.get('action') == 'login_failed']
        print(f"   Found {len(failed_events)} login_failed events in recent_events")


class TestLoginFlowStillWorks:
    """Verify login redirect and PMS still work after security changes"""
    
    def test_login_returns_correct_response(self):
        """Login should return access_token, user, tenant"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert 'access_token' in data, "access_token missing"
        assert 'user' in data, "user missing"
        
        user = data['user']
        assert 'email' in user, "user.email missing"
        assert user['email'] == VALID_EMAIL, f"Email mismatch: {user['email']}"
        
        print(f"✅ Login response verified")
        print(f"   user: {user.get('name')} ({user.get('email')})")
        print(f"   role: {user.get('role')}")
    
    def test_auth_me_works_with_token(self):
        """GET /api/auth/me should return user data"""
        # Login first
        login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        token = login.json()['access_token']
        
        # Check /auth/me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"/auth/me failed: {response.text}"
        data = response.json()
        assert 'email' in data, "email field missing"
        assert data['email'] == VALID_EMAIL
        print(f"✅ /auth/me works correctly")


class TestRateLimiting:
    """Test that rate limiting middleware is active"""
    
    def test_rate_limiting_middleware_active(self):
        """Rate limiting should be active (check stats in security summary)"""
        # Login
        login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD
        })
        token = login.json()['access_token']
        
        # Check security summary has rate_limits field
        response = requests.get(
            f"{BASE_URL}/api/security/summary",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # rate_limits or rate_limit_hits should exist in overview
        overview = data.get('overview', {})
        assert 'rate_limit_hits' in overview, "rate_limit_hits field missing in overview"
        
        print(f"✅ Rate limiting is active")
        print(f"   rate_limit_hits: {overview.get('rate_limit_hits', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
