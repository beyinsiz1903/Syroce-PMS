"""
Auto Room Mapping Wizard API Tests.

Tests the 3 mapping wizard endpoints:
- GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rooms
- GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rates
- POST /api/channel-manager/v2/mapping-wizard/{connector_id}/bulk-create
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://direct-smtp-whatsapp.preview.emergentagent.com")
TEST_CONNECTOR_ID = "27cc2aa6-68c8-4f62-95e0-076ef2c2f634"


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


class TestMappingWizardSuggestRooms:
    """Tests for GET /mapping-wizard/{connector_id}/suggest-rooms endpoint."""

    def test_suggest_rooms_returns_suggestions(self, headers):
        """Test that suggest-rooms returns room type suggestions with confidence scores."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "connector_id" in data
        assert data["connector_id"] == TEST_CONNECTOR_ID
        assert "suggestions" in data
        assert "already_mapped" in data
        assert "pms_room_types" in data
        assert "external_room_types" in data
        assert "summary" in data

    def test_suggest_rooms_has_confidence_scores(self, headers):
        """Test that suggestions include confidence scores."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        for suggestion in data["suggestions"]:
            assert "confidence" in suggestion
            assert isinstance(suggestion["confidence"], int)
            assert 0 <= suggestion["confidence"] <= 100
            assert "status" in suggestion
            assert suggestion["status"] in ["auto", "review", "unmatched"]

    def test_suggest_rooms_summary_counts(self, headers):
        """Test that summary contains correct count fields."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        summary = data["summary"]
        assert "total_pms" in summary
        assert "total_external" in summary
        assert "already_mapped" in summary
        assert "auto_matched" in summary
        assert "needs_review" in summary
        assert "unmatched" in summary

    def test_suggest_rooms_invalid_connector_returns_404(self, headers):
        """Test that invalid connector ID returns 404."""
        fake_connector = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{fake_connector}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 404

    def test_suggest_rooms_no_duplicate_external_assignments(self, headers):
        """Test that each external room type is assigned to at most one PMS room type."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rooms",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        external_ids = [s["external_entity_id"] for s in data["suggestions"] if s["external_entity_id"]]
        assert len(external_ids) == len(set(external_ids)), "Duplicate external entity assignments found"


class TestMappingWizardSuggestRates:
    """Tests for GET /mapping-wizard/{connector_id}/suggest-rates endpoint."""

    def test_suggest_rates_returns_suggestions(self, headers):
        """Test that suggest-rates returns rate plan suggestions."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rates",
            headers=headers,
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert "connector_id" in data
        assert data["connector_id"] == TEST_CONNECTOR_ID
        assert "suggestions" in data
        assert "already_mapped" in data
        assert "external_rate_plans" in data
        assert "summary" in data

    def test_suggest_rates_has_confidence_scores(self, headers):
        """Test that rate suggestions include confidence scores."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rates",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        for suggestion in data["suggestions"]:
            assert "confidence" in suggestion
            assert isinstance(suggestion["confidence"], int)
            assert 0 <= suggestion["confidence"] <= 100
            assert "status" in suggestion
            assert suggestion["status"] in ["auto", "review", "unmatched"]

    def test_suggest_rates_invalid_connector_returns_404(self, headers):
        """Test that invalid connector ID returns 404."""
        fake_connector = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{fake_connector}/suggest-rates",
            headers=headers,
        )
        assert response.status_code == 404


class TestMappingWizardBulkCreate:
    """Tests for POST /mapping-wizard/{connector_id}/bulk-create endpoint."""

    def test_bulk_create_single_mapping(self, headers):
        """Test creating a single mapping via bulk-create."""
        unique_id = str(uuid.uuid4())[:8]
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            headers=headers,
            json={
                "entity_type": "room_type",
                "pairs": [
                    {
                        "pms_entity_id": f"TEST_Room_{unique_id}",
                        "pms_entity_name": f"Test Room {unique_id}",
                        "external_entity_id": f"ext-test-{unique_id}",
                        "external_entity_name": f"External Test {unique_id}",
                    }
                ],
            },
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert "created" in data
        assert "failed" in data
        assert "total" in data
        assert data["created"] == 1
        assert data["failed"] == 0
        assert data["total"] == 1

    def test_bulk_create_multiple_mappings(self, headers):
        """Test creating multiple mappings at once."""
        unique_id = str(uuid.uuid4())[:8]
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            headers=headers,
            json={
                "entity_type": "room_type",
                "pairs": [
                    {
                        "pms_entity_id": f"TEST_Multi1_{unique_id}",
                        "pms_entity_name": f"Multi Test 1 {unique_id}",
                        "external_entity_id": f"ext-multi1-{unique_id}",
                        "external_entity_name": f"External Multi 1 {unique_id}",
                    },
                    {
                        "pms_entity_id": f"TEST_Multi2_{unique_id}",
                        "pms_entity_name": f"Multi Test 2 {unique_id}",
                        "external_entity_id": f"ext-multi2-{unique_id}",
                        "external_entity_name": f"External Multi 2 {unique_id}",
                    },
                ],
            },
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert data["created"] == 2
        assert data["failed"] == 0
        assert data["total"] == 2

    def test_bulk_create_rate_plan_mapping(self, headers):
        """Test creating rate plan mappings."""
        unique_id = str(uuid.uuid4())[:8]
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            headers=headers,
            json={
                "entity_type": "rate_plan",
                "pairs": [
                    {
                        "pms_entity_id": f"TEST_Rate_{unique_id}",
                        "pms_entity_name": f"Test Rate {unique_id}",
                        "external_entity_id": f"ext-rate-{unique_id}",
                        "external_entity_name": f"External Rate {unique_id}",
                    }
                ],
            },
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()

        assert data["created"] == 1
        assert data["failed"] == 0

    def test_bulk_create_empty_pairs_returns_400(self, headers):
        """Test that empty pairs list returns 400."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            headers=headers,
            json={
                "entity_type": "room_type",
                "pairs": [],
            },
        )
        assert response.status_code == 400

    def test_bulk_create_invalid_connector_returns_404(self, headers):
        """Test that invalid connector ID returns 404."""
        fake_connector = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{fake_connector}/bulk-create",
            headers=headers,
            json={
                "entity_type": "room_type",
                "pairs": [
                    {
                        "pms_entity_id": "TEST_Invalid",
                        "pms_entity_name": "Test",
                        "external_entity_id": "ext-invalid",
                        "external_entity_name": "External",
                    }
                ],
            },
        )
        assert response.status_code == 404

    def test_bulk_create_missing_entity_ids_fails(self, headers):
        """Test that pairs with missing entity IDs fail gracefully."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            headers=headers,
            json={
                "entity_type": "room_type",
                "pairs": [
                    {
                        "pms_entity_id": "",
                        "pms_entity_name": "Test",
                        "external_entity_id": "ext-test",
                        "external_entity_name": "External",
                    }
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["failed"] == 1
        assert data["created"] == 0


class TestMappingWizardAuth:
    """Tests for authentication requirements."""

    def test_suggest_rooms_requires_auth(self):
        """Test that suggest-rooms requires authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rooms",
        )
        assert response.status_code == 401

    def test_suggest_rates_requires_auth(self):
        """Test that suggest-rates requires authentication."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/suggest-rates",
        )
        assert response.status_code == 401

    def test_bulk_create_requires_auth(self):
        """Test that bulk-create requires authentication."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{TEST_CONNECTOR_ID}/bulk-create",
            json={"entity_type": "room_type", "pairs": []},
        )
        assert response.status_code == 401
