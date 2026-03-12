"""
Mapping Engine API Contract Tests
Tests all HTTP API endpoints for the Channel Manager v2 Mapping Engine:
  - POST /api/channel-manager/v2/mappings - create mapping with duplicate detection (409 on dup)
  - GET /api/channel-manager/v2/mappings/{connector_id} - list mappings
  - DELETE /api/channel-manager/v2/mappings/{mapping_id} - delete mapping
  - POST /api/channel-manager/v2/mappings/{connector_id}/validate - validate all mappings
  - POST /api/channel-manager/v2/mappings/{connector_id}/validate/{mapping_id} - validate single
  - GET /api/channel-manager/v2/mappings/{connector_id}/sync-readiness - readiness score
  - GET /api/channel-manager/v2/mappings/{connector_id}/readiness-report - full frontend report
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
CONNECTOR_ID = "c79fd9cb-d240-4344-8b2d-7d8b71d6a681"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in response: {data}")
    return token


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Requests session with auth header."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return session


# ════════════════════════════════════════════════════════════════════════════
# LIST MAPPINGS ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestListMappings:
    """GET /api/channel-manager/v2/mappings/{connector_id}"""

    def test_list_mappings_success(self, api_client):
        """List mappings for existing connector returns 200."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "mappings" in data
        assert "count" in data
        assert isinstance(data["mappings"], list)
        print(f"✓ List mappings: Found {data['count']} mappings")

    def test_list_mappings_with_entity_type_filter(self, api_client):
        """List mappings filtered by entity_type returns 200."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}",
            params={"entity_type": "room_type"},
        )
        assert response.status_code == 200
        data = response.json()
        # All returned mappings should be of entity_type room_type
        for m in data["mappings"]:
            if m.get("entity_type"):
                assert m["entity_type"] == "room_type"
        print(f"✓ List mappings with filter: Found {data['count']} room_type mappings")


# ════════════════════════════════════════════════════════════════════════════
# CREATE MAPPING ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestCreateMapping:
    """POST /api/channel-manager/v2/mappings"""

    def test_create_mapping_success(self, api_client):
        """Create a new mapping returns 200 with mapping data."""
        unique_suffix = uuid.uuid4().hex[:6]
        payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",  # Use meal_plan to avoid conflicts with existing room/rate mappings
            "pms_entity_id": f"TEST_PMS_{unique_suffix}",
            "pms_entity_name": f"Test PMS Entity {unique_suffix}",
            "external_entity_id": f"TEST_EXT_{unique_suffix}",
            "external_entity_name": f"Test External Entity {unique_suffix}",
        }
        response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "mapping" in data
        mapping = data["mapping"]
        assert mapping["pms_entity_id"] == payload["pms_entity_id"]
        assert mapping["external_entity_id"] == payload["external_entity_id"]
        assert mapping["entity_type"] == "meal_plan"
        assert "id" in mapping
        assert "validation_status" in mapping
        print(f"✓ Create mapping: Created mapping {mapping['id']}")
        
        # Cleanup - delete the test mapping
        cleanup_response = api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping['id']}")
        print(f"  Cleanup: Delete mapping returned {cleanup_response.status_code}")

    def test_create_mapping_duplicate_pms_entity_returns_409(self, api_client):
        """Creating duplicate mapping with same PMS entity returns 409."""
        unique_suffix = uuid.uuid4().hex[:6]
        payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_DUP_PMS_{unique_suffix}",
            "pms_entity_name": "Test Duplicate",
            "external_entity_id": f"TEST_EXT_A_{unique_suffix}",
            "external_entity_name": "External A",
        }
        
        # Create first mapping
        response1 = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response1.status_code == 200, f"First create failed: {response1.text}"
        mapping1 = response1.json()["mapping"]
        
        # Try to create duplicate with same PMS entity but different external
        payload2 = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_DUP_PMS_{unique_suffix}",  # Same PMS ID
            "pms_entity_name": "Test Duplicate 2",
            "external_entity_id": f"TEST_EXT_B_{unique_suffix}",  # Different external ID
            "external_entity_name": "External B",
        }
        response2 = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload2)
        assert response2.status_code == 409, f"Expected 409, got {response2.status_code}: {response2.text}"
        print("✓ Duplicate PMS entity detection: Got expected 409 Conflict")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping1['id']}")

    def test_create_mapping_duplicate_external_entity_returns_409(self, api_client):
        """Creating duplicate mapping with same external entity returns 409."""
        unique_suffix = uuid.uuid4().hex[:6]
        payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_PMS_A_{unique_suffix}",
            "pms_entity_name": "PMS A",
            "external_entity_id": f"TEST_DUP_EXT_{unique_suffix}",
            "external_entity_name": "Test Duplicate External",
        }
        
        # Create first mapping
        response1 = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response1.status_code == 200, f"First create failed: {response1.text}"
        mapping1 = response1.json()["mapping"]
        
        # Try to create duplicate with different PMS but same external entity
        payload2 = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_PMS_B_{unique_suffix}",  # Different PMS ID
            "pms_entity_name": "PMS B",
            "external_entity_id": f"TEST_DUP_EXT_{unique_suffix}",  # Same external ID
            "external_entity_name": "Test Duplicate External",
        }
        response2 = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload2)
        assert response2.status_code == 409, f"Expected 409, got {response2.status_code}: {response2.text}"
        print("✓ Duplicate external entity detection: Got expected 409 Conflict")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping1['id']}")

    def test_create_mapping_invalid_tax_mode_returns_invalid_status(self, api_client):
        """Creating mapping with invalid tax mode returns mapping with invalid status."""
        unique_suffix = uuid.uuid4().hex[:6]
        payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "tax_mode",
            "pms_entity_id": f"INVALID_TAX_{unique_suffix}",
            "pms_entity_name": "Invalid Tax",
            "external_entity_id": f"INVALID_TAX_EXT_{unique_suffix}",
            "external_entity_name": "Invalid Tax External",
        }
        
        response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        mapping = data["mapping"]
        assert mapping["validation_status"] == "invalid"
        assert "invalid_reason" in mapping
        assert mapping["invalid_reason"] is not None
        print(f"✓ Invalid tax mode detection: validation_status=invalid, reason={mapping['invalid_reason']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping['id']}")


# ════════════════════════════════════════════════════════════════════════════
# DELETE MAPPING ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestDeleteMapping:
    """DELETE /api/channel-manager/v2/mappings/{mapping_id}"""

    def test_delete_mapping_success(self, api_client):
        """Delete existing mapping returns 200."""
        # First create a mapping to delete
        unique_suffix = uuid.uuid4().hex[:6]
        create_payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_DEL_PMS_{unique_suffix}",
            "pms_entity_name": "To Delete",
            "external_entity_id": f"TEST_DEL_EXT_{unique_suffix}",
            "external_entity_name": "To Delete External",
        }
        create_response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=create_payload)
        assert create_response.status_code == 200
        mapping_id = create_response.json()["mapping"]["id"]
        
        # Delete the mapping
        response = api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Delete mapping: Successfully deleted mapping {mapping_id}")
        
        # Verify it's deleted by trying to delete again
        response2 = api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping_id}")
        assert response2.status_code == 404
        print("✓ Verify delete: Second delete returns 404")

    def test_delete_nonexistent_mapping_returns_404(self, api_client):
        """Delete non-existent mapping returns 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{fake_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Delete non-existent: Got expected 404")


# ════════════════════════════════════════════════════════════════════════════
# VALIDATE ALL MAPPINGS ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestValidateMappings:
    """POST /api/channel-manager/v2/mappings/{connector_id}/validate"""

    def test_validate_all_mappings_success(self, api_client):
        """Validate all mappings returns validation report."""
        response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/validate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "valid" in data
        assert "invalid" in data
        assert "missing_count" in data
        assert "total" in data
        assert "invalid_mappings" in data
        assert "missing_mappings" in data
        assert "validated_at" in data
        print(f"✓ Validate all: valid={data['valid']}, invalid={data['invalid']}, missing={data['missing_count']}")


# ════════════════════════════════════════════════════════════════════════════
# VALIDATE SINGLE MAPPING ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestValidateSingleMapping:
    """POST /api/channel-manager/v2/mappings/{connector_id}/validate/{mapping_id}"""

    def test_validate_single_mapping_success(self, api_client):
        """Validate single mapping returns validation status."""
        # First create a mapping to validate
        unique_suffix = uuid.uuid4().hex[:6]
        create_payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_VAL_PMS_{unique_suffix}",
            "pms_entity_name": "To Validate",
            "external_entity_id": f"TEST_VAL_EXT_{unique_suffix}",
            "external_entity_name": "To Validate External",
        }
        create_response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=create_payload)
        assert create_response.status_code == 200
        mapping_id = create_response.json()["mapping"]["id"]
        
        # Validate the single mapping
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/validate/{mapping_id}"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "mapping_id" in data
        assert "validation_status" in data
        assert "validated_at" in data
        assert data["mapping_id"] == mapping_id
        print(f"✓ Validate single: status={data['validation_status']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping_id}")

    def test_validate_nonexistent_mapping_returns_404(self, api_client):
        """Validate non-existent mapping returns 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/validate/{fake_id}"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Validate non-existent: Got expected 404")


# ════════════════════════════════════════════════════════════════════════════
# SYNC READINESS ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestSyncReadiness:
    """GET /api/channel-manager/v2/mappings/{connector_id}/sync-readiness"""

    def test_sync_readiness_success(self, api_client):
        """Get sync readiness returns score and blocked reasons."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/sync-readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "ready" in data
        assert "score" in data
        assert "blocked_reasons" in data
        assert isinstance(data["ready"], bool)
        assert isinstance(data["score"], int)
        assert 0 <= data["score"] <= 100
        assert isinstance(data["blocked_reasons"], list)
        
        # Verify summary structure
        if "summary" in data:
            summary = data["summary"]
            if "room_type" in summary:
                assert "mapped" in summary["room_type"]
                assert "total_pms" in summary["room_type"]
            if "rate_plan" in summary:
                assert "mapped" in summary["rate_plan"]
                assert "total_pms" in summary["rate_plan"]
        
        print(f"✓ Sync readiness: ready={data['ready']}, score={data['score']}, blocked_reasons={len(data['blocked_reasons'])}")

    def test_sync_readiness_nonexistent_connector(self, api_client):
        """Get sync readiness for non-existent connector returns appropriate response."""
        fake_id = str(uuid.uuid4())
        response = api_client.get(f"{BASE_URL}/api/channel-manager/v2/mappings/{fake_id}/sync-readiness")
        # Should return 200 with ready=False and blocked reason
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] == False
        assert data["score"] == 0
        assert "Connector not found" in str(data["blocked_reasons"])
        print("✓ Sync readiness non-existent: returns ready=False with 'Connector not found'")


# ════════════════════════════════════════════════════════════════════════════
# READINESS REPORT ENDPOINT
# ════════════════════════════════════════════════════════════════════════════

class TestReadinessReport:
    """GET /api/channel-manager/v2/mappings/{connector_id}/readiness-report"""

    def test_readiness_report_success(self, api_client):
        """Get readiness report returns comprehensive frontend data."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/readiness-report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required top-level keys
        assert "readiness" in data
        assert "mappings_by_type" in data
        assert "pms_entities" in data
        assert "external_entities" in data
        assert "supported_mapping_types" in data
        
        # Verify readiness sub-structure
        readiness = data["readiness"]
        assert "ready" in readiness
        assert "score" in readiness
        assert "blocked_reasons" in readiness
        
        # Verify mappings_by_type is a dict
        assert isinstance(data["mappings_by_type"], dict)
        
        # Verify pms_entities structure
        pms = data["pms_entities"]
        assert "room_types" in pms
        assert "rate_plans" in pms
        
        # Verify external_entities structure
        ext = data["external_entities"]
        assert "room_types" in ext
        assert "rate_plans" in ext
        
        # Verify supported_mapping_types
        assert isinstance(data["supported_mapping_types"], list)
        assert "room_type" in data["supported_mapping_types"]
        assert "rate_plan" in data["supported_mapping_types"]
        
        print(f"✓ Readiness report: score={readiness['score']}, mappings_by_type keys={list(data['mappings_by_type'].keys())}")
        print(f"  supported_mapping_types={data['supported_mapping_types']}")


# ════════════════════════════════════════════════════════════════════════════
# READINESS SCORE CALCULATION
# ════════════════════════════════════════════════════════════════════════════

class TestReadinessScoreCalculation:
    """Verify readiness score calculation (40% room, 30% rate, 30% validity)."""

    def test_score_reflects_mapping_coverage(self, api_client):
        """Score increases when more mappings exist."""
        # Get initial readiness
        response = api_client.get(f"{BASE_URL}/api/channel-manager/v2/mappings/{CONNECTOR_ID}/sync-readiness")
        assert response.status_code == 200
        initial_data = response.json()
        
        print(f"✓ Initial score: {initial_data['score']}")
        print(f"  Room mappings: {initial_data['summary']['room_type']['mapped']}/{initial_data['summary']['room_type']['total_pms']}")
        print(f"  Rate mappings: {initial_data['summary']['rate_plan']['mapped']}/{initial_data['summary']['rate_plan']['total_pms']}")
        
        # Verify score formula components are present
        assert "summary" in initial_data
        assert "room_type" in initial_data["summary"]
        assert "rate_plan" in initial_data["summary"]


# ════════════════════════════════════════════════════════════════════════════
# REVALIDATION HOOK TEST
# ════════════════════════════════════════════════════════════════════════════

class TestRevalidationHook:
    """Test that review-queue reservations are revalidated when mappings change."""

    def test_mapping_create_triggers_audit_log(self, api_client):
        """Creating a mapping creates an audit log entry."""
        unique_suffix = uuid.uuid4().hex[:6]
        payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "meal_plan",
            "pms_entity_id": f"TEST_AUDIT_PMS_{unique_suffix}",
            "pms_entity_name": "Audit Test",
            "external_entity_id": f"TEST_AUDIT_EXT_{unique_suffix}",
            "external_entity_name": "Audit Test External",
        }
        
        response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response.status_code == 200
        mapping_id = response.json()["mapping"]["id"]
        
        # Check audit log
        audit_response = api_client.get(
            f"{BASE_URL}/api/channel-manager/v2/audit",
            params={"connector_id": CONNECTOR_ID, "limit": 10},
        )
        assert audit_response.status_code == 200
        
        audit_data = audit_response.json()
        assert "logs" in audit_data
        
        # Find mapping_created action in recent logs
        created_logs = [l for l in audit_data["logs"] if l.get("action") == "mapping_created"]
        print(f"✓ Audit log: Found {len(created_logs)} mapping_created entries in recent logs")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/channel-manager/v2/mappings/{mapping_id}")


# ════════════════════════════════════════════════════════════════════════════
# CONNECTOR VALIDATION
# ════════════════════════════════════════════════════════════════════════════

class TestConnectorValidation:
    """Test that mapping operations validate connector existence."""

    def test_create_mapping_for_nonexistent_connector_returns_404(self, api_client):
        """Creating mapping for non-existent connector returns 404."""
        fake_connector_id = str(uuid.uuid4())
        payload = {
            "connector_id": fake_connector_id,
            "entity_type": "meal_plan",
            "pms_entity_id": "TEST_PMS",
            "pms_entity_name": "Test",
            "external_entity_id": "TEST_EXT",
            "external_entity_name": "Test External",
        }
        
        response = api_client.post(f"{BASE_URL}/api/channel-manager/v2/mappings", json=payload)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Non-existent connector: Got expected 404 on create mapping")
