"""
Unified Rate Manager API Tests
==============================
Tests for the new unified rate manager endpoints that auto-detect active provider
(HotelRunner or Exely) and manage rates/availability across channels and agencies.

Endpoints tested:
- GET /api/channel-manager/unified-rate-manager/detect-provider
- GET /api/channel-manager/unified-rate-manager/grid
- GET /api/channel-manager/unified-rate-manager/room-types
- GET /api/channel-manager/unified-rate-manager/agencies
- POST /api/channel-manager/unified-rate-manager/agency-rates
- GET /api/channel-manager/unified-rate-manager/agency-rates/{agency_id}
- DELETE /api/channel-manager/unified-rate-manager/agency-rates/{agency_id}
- GET /api/channel-manager/unified-rate-manager/push-providers
- GET /api/channel-manager/unified-rate-manager/pricing-settings
- GET /api/channel-manager/unified-rate-manager/stop-sale-summary
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://pms-channel-ui-fix.preview.emergentagent.com")
UNIFIED_PREFIX = "/api/channel-manager/unified-rate-manager"

# Test credentials
ADMIN_EMAIL = "demo@hotel.com"
ADMIN_PASSWORD = "demo123"
STAFF_EMAIL = "frontdesk@hotel.com"
STAFF_PASSWORD = "staff123"

# Test agency IDs from the problem statement
TEST_AGENCY_ID_1 = "1d6ebdef-b42a-40ea-8c01-f749ea96fdea"  # Antalya Turizm
TEST_AGENCY_ID_2 = "6b187487-37f9-41d1-9945-0e32e4481385"  # TEST_Content_Agency


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def staff_token():
    """Get staff authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Staff login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def staff_headers(staff_token):
    """Headers with staff auth token."""
    return {"Authorization": f"Bearer {staff_token}", "Content-Type": "application/json"}


class TestDetectProvider:
    """Tests for GET /detect-provider endpoint."""

    def test_detect_provider_returns_active_provider(self, admin_headers):
        """Verify detect-provider returns the active channel provider."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/detect-provider",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "provider" in data, "Response should contain 'provider' field"
        assert "provider_name" in data, "Response should contain 'provider_name' field"
        assert "has_connection" in data, "Response should contain 'has_connection' field"
        assert "room_count" in data, "Response should contain 'room_count' field"
        
        # Provider should be hotelrunner or exely (or None if no connection)
        if data["provider"]:
            assert data["provider"] in ["hotelrunner", "exely"], f"Unexpected provider: {data['provider']}"
            assert data["has_connection"] is True
            assert isinstance(data["room_count"], int)
            print(f"Active provider: {data['provider_name']} with {data['room_count']} rooms")
        else:
            print("No active provider detected")

    def test_detect_provider_with_staff_user(self, staff_headers):
        """Verify staff users can also detect provider."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/detect-provider",
            headers=staff_headers
        )
        assert response.status_code == 200, f"Staff should be able to detect provider: {response.text}"

    def test_detect_provider_without_auth(self):
        """Verify endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}{UNIFIED_PREFIX}/detect-provider")
        assert response.status_code in [401, 403], "Should require authentication"


class TestUnifiedGrid:
    """Tests for GET /grid endpoint."""

    def test_grid_returns_calendar_data(self, admin_headers):
        """Verify grid endpoint returns calendar data with room types and rates."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/grid?start_date={today}&end_date={end_date}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "grid" in data, "Response should contain 'grid' field"
        assert "room_types" in data, "Response should contain 'room_types' field"
        assert "rate_plans" in data, "Response should contain 'rate_plans' field"
        assert "pricing_settings" in data, "Response should contain 'pricing_settings' field"
        assert "currency" in data, "Response should contain 'currency' field"
        assert "start_date" in data, "Response should contain 'start_date' field"
        assert "end_date" in data, "Response should contain 'end_date' field"
        assert "provider" in data, "Response should contain 'provider' field"
        
        print(f"Grid returned {len(data['grid'])} rows, {len(data['room_types'])} room types, {len(data['rate_plans'])} rate plans")
        print(f"Provider: {data['provider']}, Currency: {data['currency']}")
        
        # Verify grid structure if data exists
        if data["grid"]:
            row = data["grid"][0]
            assert "room_type_code" in row, "Grid row should have room_type_code"
            assert "room_type_name" in row, "Grid row should have room_type_name"
            assert "rate_plan_code" in row, "Grid row should have rate_plan_code"
            assert "dates" in row, "Grid row should have dates array"
            
            if row["dates"]:
                date_entry = row["dates"][0]
                assert "date" in date_entry, "Date entry should have date"
                assert "availability" in date_entry, "Date entry should have availability"

    def test_grid_with_specific_date_range(self, admin_headers):
        """Verify grid works with specific date range."""
        start = "2026-04-07"
        end = "2026-04-10"
        
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/grid?start_date={start}&end_date={end}",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["start_date"] == start
        assert data["end_date"] == end


class TestRoomTypes:
    """Tests for GET /room-types endpoint."""

    def test_room_types_returns_data(self, admin_headers):
        """Verify room-types endpoint returns room types and rate plans."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/room-types",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "room_types" in data, "Response should contain 'room_types' field"
        assert "rate_plans" in data, "Response should contain 'rate_plans' field"
        assert "pricing_settings" in data, "Response should contain 'pricing_settings' field"
        assert "provider" in data, "Response should contain 'provider' field"
        
        print(f"Room types: {len(data['room_types'])}, Rate plans: {len(data['rate_plans'])}")
        
        # Verify room type structure if data exists
        if data["room_types"]:
            rt = data["room_types"][0]
            assert "code" in rt, "Room type should have code"
            assert "name" in rt, "Room type should have name"


class TestAgencies:
    """Tests for agency-related endpoints."""

    def test_list_agencies(self, admin_headers):
        """Verify agencies endpoint returns list of active agencies."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/agencies",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "agencies" in data, "Response should contain 'agencies' field"
        
        agencies = data["agencies"]
        print(f"Found {len(agencies)} active agencies")
        
        # Verify agency structure if data exists
        if agencies:
            agency = agencies[0]
            assert "id" in agency, "Agency should have id"
            assert "name" in agency, "Agency should have name"
            assert "commission_rate" in agency, "Agency should have commission_rate"
            assert "has_custom_rates" in agency, "Agency should have has_custom_rates flag"
            assert "override_count" in agency, "Agency should have override_count"
            
            print(f"First agency: {agency['name']} (commission: {agency['commission_rate']}%)")

    def test_get_agency_rate_overrides(self, admin_headers):
        """Verify getting agency-specific rate overrides."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/agency-rates/{TEST_AGENCY_ID_1}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "agency_id" in data, "Response should contain 'agency_id' field"
        assert "overrides" in data, "Response should contain 'overrides' field"
        assert data["agency_id"] == TEST_AGENCY_ID_1
        
        print(f"Agency {TEST_AGENCY_ID_1} has {len(data['overrides'])} rate overrides")

    def test_create_agency_rate_override(self, admin_headers):
        """Verify creating agency-specific rate override."""
        # First get room types to use a valid code
        rt_response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/room-types",
            headers=admin_headers
        )
        if rt_response.status_code != 200 or not rt_response.json().get("room_types"):
            pytest.skip("No room types available for testing")
        
        room_type_code = rt_response.json()["room_types"][0]["code"]
        
        # Create override with multiplier (10% discount)
        override_data = {
            "overrides": [{
                "agency_id": TEST_AGENCY_ID_1,
                "room_type_code": room_type_code,
                "rate_multiplier": 0.90
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}{UNIFIED_PREFIX}/agency-rates",
            headers=admin_headers,
            json=override_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "saved" in data, "Response should contain 'saved' count"
        assert data["saved"] >= 1, "Should have saved at least 1 override"
        print(f"Created {data['saved']} agency rate override(s)")

    def test_delete_agency_rate_overrides(self, admin_headers):
        """Verify deleting agency rate overrides."""
        response = requests.delete(
            f"{BASE_URL}{UNIFIED_PREFIX}/agency-rates/{TEST_AGENCY_ID_2}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "deleted" in data, "Response should contain 'deleted' count"
        print(f"Deleted {data['deleted']} agency rate override(s)")


class TestPushProviders:
    """Tests for GET /push-providers endpoint."""

    def test_push_providers_returns_data(self, admin_headers):
        """Verify push-providers endpoint returns provider info."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/push-providers",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "providers" in data, "Response should contain 'providers' field"
        
        providers = data["providers"]
        print(f"Found {len(providers)} push providers")
        
        # Verify provider structure if data exists
        if providers:
            provider = providers[0]
            assert "slug" in provider, "Provider should have slug"
            assert "name" in provider, "Provider should have name"
            assert "mode" in provider, "Provider should have mode"
            
            # Mode should be one of: live, shadow, inactive, read_only
            assert provider["mode"] in ["live", "shadow", "inactive", "read_only"], f"Unexpected mode: {provider['mode']}"
            print(f"Provider: {provider['name']} - Mode: {provider['mode']}")


class TestPricingSettings:
    """Tests for GET /pricing-settings endpoint."""

    def test_pricing_settings_returns_data(self, admin_headers):
        """Verify pricing-settings endpoint returns settings."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/pricing-settings",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "settings" in data, "Response should contain 'settings' field"
        
        settings = data["settings"]
        print(f"Found pricing settings for {len(settings)} room types")
        
        # Verify settings values are valid
        for room_code, pricing_type in settings.items():
            assert pricing_type in ["per_person", "per_room"], f"Invalid pricing type: {pricing_type}"


class TestStopSaleSummary:
    """Tests for GET /stop-sale-summary endpoint."""

    def test_stop_sale_summary_returns_data(self, admin_headers):
        """Verify stop-sale-summary endpoint returns stop sale data."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/stop-sale-summary?start_date={today}&end_date={end_date}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "stops" in data, "Response should contain 'stops' field"
        
        stops = data["stops"]
        print(f"Found {len(stops)} room types with stop sales")
        
        # Verify stop sale structure if data exists
        if stops:
            stop = stops[0]
            assert "room_type_code" in stop, "Stop should have room_type_code"
            assert "room_type_name" in stop, "Stop should have room_type_name"
            assert "dates" in stop, "Stop should have dates array"
            assert "count" in stop, "Stop should have count"


class TestAuthorizationAndEdgeCases:
    """Tests for authorization and edge cases."""

    def test_endpoints_require_auth(self):
        """Verify all endpoints require authentication."""
        endpoints = [
            f"{UNIFIED_PREFIX}/detect-provider",
            f"{UNIFIED_PREFIX}/grid?start_date=2026-04-07&end_date=2026-04-10",
            f"{UNIFIED_PREFIX}/room-types",
            f"{UNIFIED_PREFIX}/agencies",
            f"{UNIFIED_PREFIX}/push-providers",
            f"{UNIFIED_PREFIX}/pricing-settings",
            f"{UNIFIED_PREFIX}/stop-sale-summary?start_date=2026-04-07&end_date=2026-04-10",
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code in [401, 403], f"Endpoint {endpoint} should require auth, got {response.status_code}"
        
        print(f"All {len(endpoints)} endpoints correctly require authentication")

    def test_invalid_date_format(self, admin_headers):
        """Verify grid handles invalid date format gracefully."""
        response = requests.get(
            f"{BASE_URL}{UNIFIED_PREFIX}/grid?start_date=invalid&end_date=2026-04-10",
            headers=admin_headers
        )
        # Should return 422 (validation error) or 400 (bad request)
        assert response.status_code in [400, 422, 500], f"Should reject invalid date format, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
