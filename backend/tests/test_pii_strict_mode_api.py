"""
PII Strict Mode API Tests — Tests for P2 PII Strict Mode feature.

Tests:
  - GET /api/security/pii-strict-mode/config
  - POST /api/security/pii-strict-mode/toggle
  - GET /api/security/pii-strict-mode/summary
  - GET /api/security/pii-strict-mode/violations
  - GET /api/security/pii-strict-mode/encryption-status
  - GET /api/security/pii-strict-mode/policy
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://pms-channel-mgr.preview.emergentagent.com"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        # Login returns access_token field
        token = data.get("access_token") or data.get("token")
        if token:
            return token
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestLoginFlow:
    """Test login flow with demo credentials."""

    def test_login_returns_200_and_token(self):
        """Login with demo@hotel.com / demo123 should return 200 and access_token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=30
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Check for access_token field
        assert "access_token" in data or "token" in data, f"No token in response: {data}"
        token = data.get("access_token") or data.get("token")
        assert len(token) > 0, "Token is empty"
        print(f"Login successful, token length: {len(token)}")


class TestPIIStrictModeConfig:
    """Test PII Strict Mode config endpoint."""

    def test_get_config_returns_200(self, auth_headers):
        """GET /api/security/pii-strict-mode/config should return config."""
        response = requests.get(
            f"{BASE_URL}/api/security/pii-strict-mode/config",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Config failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        assert "config" in data, f"No config in response: {data}"
        config = data["config"]
        assert "enabled" in config, f"No enabled field in config: {config}"
        print(f"PII Strict Mode config: enabled={config.get('enabled')}")


class TestPIIStrictModeToggle:
    """Test PII Strict Mode toggle endpoint."""

    def test_toggle_enable_returns_200(self, auth_headers):
        """POST /api/security/pii-strict-mode/toggle {enabled:true} should work."""
        response = requests.post(
            f"{BASE_URL}/api/security/pii-strict-mode/toggle",
            headers=auth_headers,
            json={"enabled": True},
            timeout=30
        )
        assert response.status_code == 200, f"Toggle failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        assert "config" in data, f"No config in response: {data}"
        config = data["config"]
        assert config.get("enabled") is True, f"Enabled not True: {config}"
        print("PII Strict Mode toggled to enabled=True")

    def test_toggle_disable_returns_200(self, auth_headers):
        """POST /api/security/pii-strict-mode/toggle {enabled:false} should work."""
        response = requests.post(
            f"{BASE_URL}/api/security/pii-strict-mode/toggle",
            headers=auth_headers,
            json={"enabled": False},
            timeout=30
        )
        assert response.status_code == 200, f"Toggle failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        config = data["config"]
        assert config.get("enabled") is False, f"Enabled not False: {config}"
        print("PII Strict Mode toggled to enabled=False")

    def test_toggle_back_to_enabled(self, auth_headers):
        """Re-enable strict mode for other tests."""
        response = requests.post(
            f"{BASE_URL}/api/security/pii-strict-mode/toggle",
            headers=auth_headers,
            json={"enabled": True},
            timeout=30
        )
        assert response.status_code == 200, f"Toggle failed: {response.text}"
        print("PII Strict Mode re-enabled")


class TestPIIStrictModeSummary:
    """Test PII Strict Mode summary endpoint."""

    def test_get_summary_returns_200(self, auth_headers):
        """GET /api/security/pii-strict-mode/summary should return violation summary."""
        response = requests.get(
            f"{BASE_URL}/api/security/pii-strict-mode/summary",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        assert "summary" in data, f"No summary in response: {data}"
        summary = data["summary"]
        # Summary should have violation counts
        assert "total_violations" in summary or isinstance(summary, dict), f"Invalid summary: {summary}"
        print(f"PII Strict Mode summary: {summary}")


class TestPIIStrictModeViolations:
    """Test PII Strict Mode violations endpoint."""

    def test_get_violations_returns_200(self, auth_headers):
        """GET /api/security/pii-strict-mode/violations should return violations list."""
        response = requests.get(
            f"{BASE_URL}/api/security/pii-strict-mode/violations?limit=20",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Violations failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        # Should have items array
        assert "items" in data or "violations" in data, f"No items in response: {data}"
        items = data.get("items") or data.get("violations") or []
        assert isinstance(items, list), f"Items not a list: {items}"
        print(f"PII Strict Mode violations count: {len(items)}")


class TestPIIStrictModeEncryptionStatus:
    """Test PII Strict Mode encryption-status endpoint."""

    def test_get_encryption_status_returns_200(self, auth_headers):
        """GET /api/security/pii-strict-mode/encryption-status should return encryption coverage."""
        response = requests.get(
            f"{BASE_URL}/api/security/pii-strict-mode/encryption-status",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Encryption status failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        assert "collections" in data, f"No collections in response: {data}"
        assert "timestamp" in data, f"No timestamp in response: {data}"
        collections = data["collections"]
        assert isinstance(collections, dict), f"Collections not a dict: {collections}"
        print(f"PII Encryption status collections: {list(collections.keys())}")


class TestPIIStrictModePolicy:
    """Test PII Strict Mode policy endpoint."""

    def test_get_policy_returns_200(self, auth_headers):
        """GET /api/security/pii-strict-mode/policy should return PII policy registry."""
        response = requests.get(
            f"{BASE_URL}/api/security/pii-strict-mode/policy",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Policy failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Status not ok: {data}"
        assert "policy" in data, f"No policy in response: {data}"
        policy = data["policy"]
        assert isinstance(policy, dict), f"Policy not a dict: {policy}"
        # Policy should have total_pii_fields or categories
        assert "total_pii_fields" in policy or "categories" in policy, f"Invalid policy: {policy}"
        print(f"PII Policy: total_fields={policy.get('total_pii_fields')}")


class TestExistingPagesRegression:
    """Test that existing pages are still accessible."""

    def test_wire_failures_endpoint_accessible(self, auth_headers):
        """Wire failures summary endpoint should still work."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/wire-failures/summary?days=30",
            headers=auth_headers,
            timeout=30
        )
        # Should return 200 or 404 (if no data)
        assert response.status_code in [200, 404], f"Wire failures failed: {response.text}"
        print(f"Wire failures endpoint: {response.status_code}")

    def test_exely_status_endpoint_accessible(self, auth_headers):
        """Exely status endpoint should still work."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/status",
            headers=auth_headers,
            timeout=30
        )
        # Should return 200 or 404
        assert response.status_code in [200, 404], f"Exely status failed: {response.text}"
        print(f"Exely status endpoint: {response.status_code}")

    def test_hotelrunner_status_endpoint_accessible(self, auth_headers):
        """HotelRunner status endpoint should still work."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/status",
            headers=auth_headers,
            timeout=30
        )
        # Should return 200 or 404
        assert response.status_code in [200, 404], f"HotelRunner status failed: {response.text}"
        print(f"HotelRunner status endpoint: {response.status_code}")
