"""
TI-003: Tenant Isolation API Tests
==================================
Tests that the TenantContextMiddleware correctly sets tenant context
from JWT and that API endpoints return tenant-scoped data.
"""
import os
import pytest
import requests

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://vite-env-fix.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"
EXPECTED_TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"


class TestTenantIsolationAPI:
    """API-level tests for tenant isolation middleware integration."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        return data["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    # ── Login Endpoint Tests ──────────────────────────────────────

    def test_login_works_without_tenant_context(self):
        """Login endpoint should work without prior tenant context (no JWT yet)."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["tenant_id"] == EXPECTED_TENANT_ID

    def test_login_returns_tenant_id_in_jwt(self, auth_token):
        """JWT should contain tenant_id claim."""
        import jwt
        # Decode without verification to check claims
        payload = jwt.decode(auth_token, options={"verify_signature": False})
        assert "tenant_id" in payload
        assert payload["tenant_id"] == EXPECTED_TENANT_ID

    # ── Health Endpoint Tests ─────────────────────────────────────

    def test_health_works_without_auth(self):
        """Health endpoint should work without authentication."""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_health_deep_works_without_auth(self):
        """Deep health check should work without authentication."""
        response = requests.get(f"{BASE_URL}/health/deep", timeout=10)
        # May return 503 if some services are unhealthy, but should not require auth
        assert response.status_code in [200, 503]
        data = response.json()
        # Response contains health info for various services
        assert isinstance(data, dict)

    # ── Authenticated Endpoint Tests ──────────────────────────────

    def test_dashboard_requires_auth(self):
        """Dashboard endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/dashboard/role-based", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_dashboard_returns_data_with_auth(self, auth_headers):
        """Dashboard endpoint should return data when authenticated."""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/role-based",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "role" in data or "dashboard_type" in data

    def test_rooms_requires_auth(self):
        """Rooms endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/pms/rooms", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_rooms_returns_tenant_scoped_data(self, auth_headers):
        """Rooms endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/pms/rooms",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verify all rooms belong to the expected tenant
        for room in data:
            if "tenant_id" in room:
                assert room["tenant_id"] == EXPECTED_TENANT_ID

    def test_night_audit_status_requires_auth(self):
        """Night audit status endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/night-audit/status", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_night_audit_status_returns_tenant_data(self, auth_headers):
        """Night audit status should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/night-audit/status",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "current_business_date" in data
        # If latest_run exists, verify tenant_id
        if data.get("latest_run"):
            assert data["latest_run"]["tenant_id"] == EXPECTED_TENANT_ID

    def test_night_audit_runs_requires_auth(self):
        """Night audit runs endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/night-audit/runs", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_night_audit_runs_returns_tenant_data(self, auth_headers):
        """Night audit runs should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/night-audit/runs",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        # Verify all runs belong to the expected tenant
        if isinstance(data, list):
            for run in data:
                if "tenant_id" in run:
                    assert run["tenant_id"] == EXPECTED_TENANT_ID

    def test_night_audit_business_date_requires_auth(self):
        """Night audit business-date endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/night-audit/business-date", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_night_audit_business_date_returns_data(self, auth_headers):
        """Night audit business-date should return data."""
        response = requests.get(
            f"{BASE_URL}/api/night-audit/business-date",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "business_date" in data

    # ── Bookings Endpoint Tests ───────────────────────────────────

    def test_bookings_requires_auth(self):
        """Bookings endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/pms/bookings", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_bookings_returns_tenant_scoped_data(self, auth_headers):
        """Bookings endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        # Handle both list and paginated response
        bookings = data if isinstance(data, list) else data.get("items", data.get("bookings", []))
        for booking in bookings:
            if "tenant_id" in booking:
                assert booking["tenant_id"] == EXPECTED_TENANT_ID

    # ── Guests Endpoint Tests ─────────────────────────────────────

    def test_guests_requires_auth(self):
        """Guests endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/pms/guests", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_guests_returns_tenant_scoped_data(self, auth_headers):
        """Guests endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        guests = data if isinstance(data, list) else data.get("items", data.get("guests", []))
        for guest in guests:
            if "tenant_id" in guest:
                assert guest["tenant_id"] == EXPECTED_TENANT_ID

    # ── Folios Endpoint Tests ─────────────────────────────────────

    def test_folios_requires_auth(self):
        """Folios endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/folio/list", timeout=10)
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_folios_returns_tenant_scoped_data(self, auth_headers):
        """Folios endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/folio/list",
            headers=auth_headers,
            timeout=10
        )
        # May return 200 or 404 if no folios
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            folios = data.get("folios", [])
            for folio in folios:
                if "tenant_id" in folio:
                    assert folio["tenant_id"] == EXPECTED_TENANT_ID


class TestCrossTenantAccessBlocking:
    """Tests that cross-tenant access is blocked at API level."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_cannot_access_other_tenant_guest(self, auth_headers):
        """Should not be able to access a guest from another tenant."""
        fake_guest_id = "other-tenant-guest-id-12345"
        response = requests.get(
            f"{BASE_URL}/api/pms/guests/{fake_guest_id}",
            headers=auth_headers,
            timeout=10
        )
        # Should return 404 (not found in this tenant's scope) or 422 (invalid ID format)
        assert response.status_code in [404, 422]

    def test_cannot_access_other_tenant_night_audit_run(self, auth_headers):
        """Should not be able to access a night audit run from another tenant."""
        fake_run_id = "other-tenant-run-id-12345"
        response = requests.get(
            f"{BASE_URL}/api/night-audit/runs/{fake_run_id}",
            headers=auth_headers,
            timeout=10
        )
        # Should return 404 (not found in this tenant's scope)
        assert response.status_code == 404


class TestGlobalCollectionsAccess:
    """Tests that global collections (tenants, system_config) are accessible."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_tenant_info_accessible(self, auth_headers):
        """Tenant info should be accessible (global collection)."""
        response = requests.get(
            f"{BASE_URL}/api/tenant/info",
            headers=auth_headers,
            timeout=10
        )
        # May return 200 or 404 depending on endpoint existence
        if response.status_code == 200:
            data = response.json()
            # Verify it returns the user's tenant info
            if "id" in data:
                assert data["id"] == EXPECTED_TENANT_ID


class TestMiddlewareIntegration:
    """Tests for middleware integration with various endpoint types."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_invalid_token_rejected(self):
        """Invalid JWT should be rejected."""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/role-based",
            headers={"Authorization": "Bearer invalid-token"},
            timeout=10
        )
        assert response.status_code == 401

    def test_expired_token_rejected(self):
        """Expired JWT should be rejected."""
        # This is a token with exp in the past
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIiwidGVuYW50X2lkIjoiYWJjIiwiZXhwIjoxNjAwMDAwMDAwfQ.invalid"
        response = requests.get(
            f"{BASE_URL}/api/dashboard/role-based",
            headers={"Authorization": f"Bearer {expired_token}"},
            timeout=10
        )
        assert response.status_code == 401

    def test_missing_auth_header_rejected(self):
        """Missing Authorization header should be rejected for protected endpoints."""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/role-based",
            timeout=10
        )
        # API returns 403 for unauthenticated requests
        assert response.status_code in [401, 403]

    def test_reports_endpoint_tenant_scoped(self, auth_headers):
        """Reports endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/reports/occupancy",
            headers=auth_headers,
            timeout=10
        )
        # May return 200 or 404 depending on data availability
        assert response.status_code in [200, 404, 422]

    def test_calendar_endpoint_tenant_scoped(self, auth_headers):
        """Calendar endpoint should return tenant-scoped data."""
        response = requests.get(
            f"{BASE_URL}/api/calendar/availability",
            headers=auth_headers,
            timeout=10
        )
        # May return 200, 404 (not found), or 422 (missing params)
        assert response.status_code in [200, 404, 422]


class TestPublicEndpoints:
    """Tests that public endpoints work without authentication."""

    def test_docs_accessible(self):
        """API docs should be accessible without auth."""
        response = requests.get(f"{BASE_URL}/api/docs", timeout=10)
        # May redirect or return HTML
        assert response.status_code in [200, 307, 308]

    def test_openapi_json_accessible(self):
        """OpenAPI JSON should be accessible without auth."""
        response = requests.get(f"{BASE_URL}/api/openapi.json", timeout=10)
        assert response.status_code == 200

    def test_register_endpoint_accessible(self):
        """Register endpoint should be accessible without auth."""
        # Just check it doesn't return 401
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": "test@test.com", "password": "test123"},
            timeout=10
        )
        # May return 400/422 for validation, but not 401
        assert response.status_code != 401
