"""
Test Security Hardening Consolidated Dashboard APIs
Tests for:
- /api/security-hardening/tenant-scope/check (was 500, now should be 200)
- /api/security/pii-strict-mode/config
- /api/security/pii-strict-mode/summary
- /api/infra/summary
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://guest-list-hub.preview.emergentagent.com").rstrip("/")


class TestSecurityHardeningAPIs:
    """Test Security Hardening consolidated dashboard APIs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for all tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
        yield
    
    def test_tenant_scope_check_returns_200(self):
        """Test /api/security-hardening/tenant-scope/check returns 200 (was 500 before fix)"""
        response = self.session.get(f"{BASE_URL}/api/security-hardening/tenant-scope/check")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "tenant_id" in data or "isolation_score" in data or "collections_checked" in data, \
            f"Response missing expected fields: {data}"
    
    def test_pii_strict_mode_config_returns_200(self):
        """Test /api/security/pii-strict-mode/config returns 200"""
        response = self.session.get(f"{BASE_URL}/api/security/pii-strict-mode/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response has config
        assert "config" in data, f"Response missing 'config' field: {data}"
    
    def test_pii_strict_mode_summary_returns_200(self):
        """Test /api/security/pii-strict-mode/summary returns 200"""
        response = self.session.get(f"{BASE_URL}/api/security/pii-strict-mode/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response has summary
        assert "summary" in data, f"Response missing 'summary' field: {data}"
    
    def test_infra_summary_returns_200(self):
        """Test /api/infra/summary returns 200"""
        response = self.session.get(f"{BASE_URL}/api/infra/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response has expected infrastructure fields
        assert any(key in data for key in ["redis_cluster", "worker_queues", "backup", "secrets"]), \
            f"Response missing expected infra fields: {list(data.keys())}"
    
    def test_security_hardening_property_permissions(self):
        """Test /api/security-hardening/property-permissions returns 200"""
        response = self.session.get(f"{BASE_URL}/api/security-hardening/property-permissions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_security_hardening_vault_status(self):
        """Test /api/security-hardening/vault/status returns 200"""
        response = self.session.get(f"{BASE_URL}/api/security-hardening/vault/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_security_hardening_audit_completeness(self):
        """Test /api/security-hardening/audit-completeness returns 200"""
        response = self.session.get(f"{BASE_URL}/api/security-hardening/audit-completeness?hours=24")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
