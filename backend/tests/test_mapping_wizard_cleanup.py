"""
Room Mapping Wizard Cleanup Tests.

Tests for the cleaned-up Room Mapping Wizard after DB cleanup:
- POST /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external
- GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rooms
- GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rate-plans
- GET /api/channel-manager/v2/connectors

Expected behavior:
- fetch-external returns 400 with credential error (test credentials are invalid)
- suggest-rooms returns PMS room types with 0 external rooms
- suggest-rate-plans returns PMS rate plans with 0 external rate plans
- connectors returns exactly 3 connectors (no duplicates)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://channel-sync-hub-2.preview.emergentagent.com")

# Connector IDs from the cleanup (actual IDs from DB)
HOTELRUNNER_SANDBOX_ID = "c79fd9cb-d240-4344-8b2d-7d8b71d6a681"
SANDBOX_EXELY_ID = "sandbox-exely-sim-e1fca6dc1c5b"
SANDBOX_HOTELRUNNER_ID = "sandbox-hotelrunner-sim-e1fca6dc1c5b"

EXPECTED_CONNECTOR_IDS = {HOTELRUNNER_SANDBOX_ID, SANDBOX_EXELY_ID, SANDBOX_HOTELRUNNER_ID}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in response"
    return data["access_token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    """Return headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


class TestConnectorsList:
    """Tests for GET /api/channel-manager/v2/connectors endpoint after cleanup."""

    def test_connectors_returns_exactly_3(self, headers):
        """Test that connectors endpoint returns exactly 3 connectors after cleanup."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "connectors" in data, "Response should have 'connectors' key"
        connectors = data["connectors"]
        
        # Should have exactly 3 connectors
        assert len(connectors) == 3, f"Expected 3 connectors, got {len(connectors)}: {[c.get('display_name', c.get('id')) for c in connectors]}"

    def test_connectors_have_expected_ids(self, headers):
        """Test that connectors have the expected IDs after cleanup."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        connector_ids = {c["id"] for c in data["connectors"]}
        
        # Check that all expected connectors are present
        assert HOTELRUNNER_SANDBOX_ID in connector_ids, f"HotelRunner Sandbox connector not found. Found: {connector_ids}"
        assert SANDBOX_EXELY_ID in connector_ids, f"Sandbox Exely connector not found. Found: {connector_ids}"
        assert SANDBOX_HOTELRUNNER_ID in connector_ids, f"Sandbox HotelRunner connector not found. Found: {connector_ids}"

    def test_no_duplicate_connectors(self, headers):
        """Test that there are no duplicate connectors."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        connector_ids = [c["id"] for c in data["connectors"]]
        assert len(connector_ids) == len(set(connector_ids)), "Duplicate connector IDs found"

    def test_connectors_have_required_fields(self, headers):
        """Test that each connector has required fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        for connector in data["connectors"]:
            assert "id" in connector, "Connector missing 'id'"
            assert "display_name" in connector, "Connector missing 'display_name'"
            assert "provider" in connector, "Connector missing 'provider'"
            assert "status" in connector, "Connector missing 'status'"


class TestFetchExternal:
    """Tests for POST /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external endpoint."""

    def test_fetch_external_returns_400_for_invalid_credentials(self, headers):
        """Test that fetch-external returns 400 with credential error for HotelRunner Sandbox."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/fetch-external",
            headers=headers,
            json={},
        )
        # Expected: 400 because test credentials are not valid real tokens
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Response should have 'detail' key with error message"
        # The error should mention something about credentials or data fetch failure
        error_msg = data["detail"].lower()
        assert any(word in error_msg for word in ["veri", "cekilemedi", "auth", "kimlik", "hata"]), \
            f"Error message should indicate credential/fetch issue: {data['detail']}"

    def test_fetch_external_requires_auth(self):
        """Test that fetch-external requires authentication."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/fetch-external",
            json={},
        )
        assert response.status_code == 401


class TestSuggestRoomsAfterCleanup:
    """Tests for GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rooms after cleanup."""

    def test_suggest_rooms_returns_pms_types_with_zero_external(self, headers):
        """Test that suggest-rooms returns PMS room types with 0 external rooms."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have PMS room types
        assert "pms_room_types" in data
        assert "external_room_types" in data
        assert "suggestions" in data
        assert "summary" in data
        
        # External room types should be 0 (cleaned up)
        assert data["summary"]["total_external"] == 0, \
            f"Expected 0 external room types, got {data['summary']['total_external']}"

    def test_suggest_rooms_has_pms_room_types(self, headers):
        """Test that PMS room types are present."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have PMS room types (6 expected: Standard, Deluxe, Superior, Suite, Junior Suite, Family)
        pms_count = data["summary"]["total_pms"]
        assert pms_count >= 6, f"Expected at least 6 PMS room types, got {pms_count}"

    def test_suggest_rooms_all_unmatched(self, headers):
        """Test that all suggestions are unmatched (no external data)."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # All suggestions should be unmatched since there are no external room types
        for suggestion in data["suggestions"]:
            assert suggestion["status"] == "unmatched", \
                f"Expected all suggestions to be 'unmatched', got '{suggestion['status']}' for {suggestion['pms_entity_name']}"
            assert suggestion["external_entity_id"] == "", \
                f"Expected empty external_entity_id, got '{suggestion['external_entity_id']}'"


class TestSuggestRatePlansAfterCleanup:
    """Tests for GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rates after cleanup."""

    def test_suggest_rates_returns_pms_plans_with_zero_external(self, headers):
        """Test that suggest-rates returns PMS rate plans with 0 external rate plans."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rates",
            headers=headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have structure
        assert "external_rate_plans" in data
        assert "suggestions" in data
        assert "summary" in data
        
        # External rate plans should be 0 (cleaned up)
        assert data["summary"]["total_external"] == 0, \
            f"Expected 0 external rate plans, got {data['summary']['total_external']}"

    def test_suggest_rates_all_unmatched(self, headers):
        """Test that all rate suggestions are unmatched (no external data)."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rates",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # All suggestions should be unmatched since there are no external rate plans
        for suggestion in data["suggestions"]:
            assert suggestion["status"] == "unmatched", \
                f"Expected all suggestions to be 'unmatched', got '{suggestion['status']}'"


class TestConnectorSpecificEndpoints:
    """Tests for endpoints with specific connector IDs."""

    def test_hotelrunner_sandbox_suggest_rooms(self, headers):
        """Test suggest-rooms for HotelRunner Sandbox connector."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{HOTELRUNNER_SANDBOX_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connector_id"] == HOTELRUNNER_SANDBOX_ID

    def test_sandbox_exely_suggest_rooms(self, headers):
        """Test suggest-rooms for Sandbox Exely connector."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{SANDBOX_EXELY_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connector_id"] == SANDBOX_EXELY_ID

    def test_sandbox_hotelrunner_suggest_rooms(self, headers):
        """Test suggest-rooms for Sandbox HotelRunner connector."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{SANDBOX_HOTELRUNNER_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connector_id"] == SANDBOX_HOTELRUNNER_ID
