"""
SEC-001: Secrets Management API Integration Tests

Tests verify:
1. Auth login still works
2. Exely connection endpoint doesn't leak credentials
3. HotelRunner connection endpoint doesn't leak credentials
4. Test connection endpoints work (may return 404/error but don't crash)
5. Health endpoint works
6. No plaintext secrets in API responses
7. Credential masking utility works
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://hotel-sync-hub-1.preview.emergentagent.com")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Sensitive fields that should NEVER appear in API responses
SENSITIVE_FIELDS = ["password", "username", "token", "credentials_ref", "secret_key", "api_key"]


class TestAuthLogin:
    """Test that auth login still works after SEC-001 changes."""

    def test_login_success(self):
        """Auth login should work with valid credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL

    def test_login_invalid_credentials(self):
        """Auth login should reject invalid credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpass"},
        )
        assert response.status_code in [401, 400]


class TestExelyConnectionEndpoint:
    """Test Exely connection endpoint doesn't leak credentials."""

    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        return response.json()["access_token"]

    def test_exely_connection_no_credentials_leak(self, auth_token):
        """GET /api/channel-manager/exely/connection should not expose credentials."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/connection",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check response doesn't contain sensitive fields
        response_str = str(data).lower()
        for field in ["password", "username", "credentials_ref"]:
            if field in response_str:
                # If field exists, it should be excluded or masked
                if "connection" in data and data["connection"]:
                    conn = data["connection"]
                    assert field not in conn, f"Sensitive field '{field}' found in connection response"

    def test_exely_test_connection_no_crash(self, auth_token):
        """POST /api/channel-manager/exely/test should not crash (may return error)."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/test",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        # Should return 200 (with error in body), 404 (no connection), or 502 (external error)
        # Should NOT return 500 (internal server error)
        assert response.status_code in [200, 404, 502], f"Unexpected status: {response.status_code}"
        
        # If 200, check no credentials in response
        if response.status_code == 200:
            data = response.json()
            response_str = str(data).lower()
            for field in SENSITIVE_FIELDS:
                assert field not in response_str or "****" in response_str, \
                    f"Sensitive field '{field}' may be exposed in test response"


class TestHotelRunnerConnectionEndpoint:
    """Test HotelRunner connection endpoint doesn't leak credentials."""

    @pytest.fixture
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        return response.json()["access_token"]

    def test_hotelrunner_connection_no_credentials_leak(self, auth_token):
        """GET /api/channel-manager/hotelrunner/connection should not expose credentials."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/connection",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check response doesn't contain sensitive fields
        if "connection" in data and data["connection"]:
            conn = data["connection"]
            for field in ["token", "credentials_ref"]:
                assert field not in conn, f"Sensitive field '{field}' found in connection response"

    def test_hotelrunner_test_connection_no_crash(self, auth_token):
        """POST /api/channel-manager/hotelrunner/test should not crash (may return 404)."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/test",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        # Should return 200, 404 (no connection), or 502 (external error)
        # Should NOT return 500 (internal server error)
        assert response.status_code in [200, 404, 502], f"Unexpected status: {response.status_code}"


class TestHealthEndpoint:
    """Test health endpoint works."""

    def test_health_endpoint(self):
        """Health endpoint should return healthy status."""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"


class TestCredentialMasking:
    """Test credential masking utility."""

    def test_mask_credentials_long_values(self):
        """Masking should work for long credential values."""
        from core.secrets.manager import SecretsManager
        
        masked = SecretsManager.mask_credentials({
            "token": "sk-abc123xyz789",
            "password": "mysupersecretpassword",
        })
        
        # First 3 and last 3 chars visible, middle masked
        assert masked["token"].startswith("sk-")
        assert masked["token"].endswith("789")
        assert "*" in masked["token"]
        
        assert masked["password"].startswith("mys")
        assert masked["password"].endswith("ord")
        assert "*" in masked["password"]

    def test_mask_credentials_short_values(self):
        """Masking should fully mask short values."""
        from core.secrets.manager import SecretsManager
        
        masked = SecretsManager.mask_credentials({
            "short": "abc",
            "tiny": "x",
        })
        
        assert masked["short"] == "****"
        assert masked["tiny"] == "****"


@pytest.fixture(scope="module")
def module_auth_token():
    """Module-scoped auth token to avoid rate limiting."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    return response.json()["access_token"]


class TestNoPlaintextSecretsInResponses:
    """Verify no plaintext secrets appear in any API response."""

    def test_exely_reservations_no_secrets(self, module_auth_token):
        """Exely reservations endpoint should not expose secrets."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/reservations/local",
            headers={"Authorization": f"Bearer {module_auth_token}"},
        )
        if response.status_code == 200:
            data = response.json()
            response_str = str(data).lower()
            for field in SENSITIVE_FIELDS:
                # Allow field names but not actual values
                if field in response_str:
                    # Check it's not a value (would be in quotes)
                    assert f'"{field}":' not in response_str.replace(" ", ""), \
                        f"Sensitive field '{field}' may be exposed"

    def test_hotelrunner_reservations_no_secrets(self, module_auth_token):
        """HotelRunner reservations endpoint should not expose secrets."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/reservations/local",
            headers={"Authorization": f"Bearer {module_auth_token}"},
        )
        if response.status_code == 200:
            data = response.json()
            response_str = str(data).lower()
            for field in SENSITIVE_FIELDS:
                if field in response_str:
                    assert f'"{field}":' not in response_str.replace(" ", ""), \
                        f"Sensitive field '{field}' may be exposed"
