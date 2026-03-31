"""
P1 Features Test Suite - Mapping Manager, Reservation Lineage, Test Booking Verification
Tests for Hotel Management System (Syroce PMS) P1 features:
1. Mapping UI Improvement - Enhanced PMS entity ↔ Provider entity mapping interface
2. Reservation Lineage - Tracking import history and duplicate/stale detection UI
3. Test Booking via Exely - OTA_ReadRQ verification workflow
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://orphan-removal.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Known connector ID with active mappings
CONNECTOR_ID = "27cc2aa6-68c8-4f62-95e0-076ef2c2f634"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    # Auth token field is 'access_token' not 'token'
    token = data.get("access_token")
    assert token, "No access_token in login response"
    return token


@pytest.fixture(scope="module")
def headers(auth_token):
    """Get headers with authorization."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestMappingManagerV2API:
    """Tests for MappingManager v2 API endpoints."""
    
    def test_get_connectors(self, headers):
        """GET /api/channel-manager/v2/connectors - List all connectors."""
        response = requests.get(f"{BASE_URL}/channel-manager/v2/connectors", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "connectors" in data, "Response should have 'connectors' field"
        assert isinstance(data["connectors"], list), "Connectors should be a list"
        print(f"Found {len(data['connectors'])} connectors")
    
    def test_get_readiness_report(self, headers):
        """GET /api/channel-manager/v2/mappings/{connector_id}/readiness-report - Get readiness report."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/mappings/{CONNECTOR_ID}/readiness-report",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check readiness structure
        assert "readiness" in data, "Response should have 'readiness' field"
        readiness = data["readiness"]
        assert "score" in readiness, "Readiness should have 'score'"
        assert "ready" in readiness, "Readiness should have 'ready'"
        assert "blocked_reasons" in readiness, "Readiness should have 'blocked_reasons'"
        
        # Check mappings_by_type
        assert "mappings_by_type" in data, "Response should have 'mappings_by_type'"
        
        print(f"Readiness score: {readiness['score']}, Ready: {readiness['ready']}")
        print(f"Blocked reasons: {len(readiness['blocked_reasons'])}")
    
    def test_validate_all_mappings(self, headers):
        """POST /api/channel-manager/v2/mappings/{connector_id}/validate - Validate all mappings."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/v2/mappings/{CONNECTOR_ID}/validate",
            headers=headers,
            json={}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check validation result structure
        assert "valid" in data, "Response should have 'valid' count"
        assert "invalid" in data, "Response should have 'invalid' count"
        assert "total" in data, "Response should have 'total' count"
        assert "validated_at" in data, "Response should have 'validated_at' timestamp"
        
        print(f"Validation: {data['valid']} valid, {data['invalid']} invalid, {data['total']} total")
    
    def test_create_and_delete_mapping(self, headers):
        """POST /api/channel-manager/v2/mappings - Create mapping, then DELETE."""
        # Create a test mapping
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "connector_id": CONNECTOR_ID,
            "entity_type": "room_type",
            "pms_entity_id": f"TEST_PMS_{unique_id}",
            "pms_entity_name": "Test PMS Room",
            "external_entity_id": f"TEST_EXT_{unique_id}",
            "external_entity_name": "Test External Room"
        }
        
        # Create
        response = requests.post(
            f"{BASE_URL}/channel-manager/v2/mappings",
            headers=headers,
            json=create_payload
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert "mapping" in data, "Response should have 'mapping' field"
        mapping_id = data["mapping"]["id"]
        print(f"Created mapping: {mapping_id}")
        
        # Delete
        response = requests.delete(
            f"{BASE_URL}/channel-manager/v2/mappings/{mapping_id}",
            headers=headers
        )
        assert response.status_code == 200, f"Delete failed: {response.text}"
        print(f"Deleted mapping: {mapping_id}")
    
    def test_delete_nonexistent_mapping(self, headers):
        """DELETE /api/channel-manager/v2/mappings/{id} - Should return 404 for non-existent."""
        response = requests.delete(
            f"{BASE_URL}/channel-manager/v2/mappings/non-existent-id-12345",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Correctly returned 404 for non-existent mapping")


class TestReservationLineageAPI:
    """Tests for Reservation Lineage API endpoints."""
    
    def test_get_reservation_stats(self, headers):
        """GET /api/channel-manager/v2/reservations/stats - Get reservation statistics."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/reservations/stats",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check stats structure
        assert "total_reservations" in data, "Response should have 'total_reservations'"
        assert "by_status" in data, "Response should have 'by_status'"
        assert "review_queue_count" in data, "Response should have 'review_queue_count'"
        assert "ack_failed_count" in data, "Response should have 'ack_failed_count'"
        assert "success_rate" in data, "Response should have 'success_rate'"
        
        print(f"Total reservations: {data['total_reservations']}")
        print(f"Success rate: {data['success_rate']}%")
    
    def test_get_imported_reservations(self, headers):
        """GET /api/channel-manager/v2/reservations/imported - List imported reservations."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/reservations/imported?limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "reservations" in data, "Response should have 'reservations' field"
        assert "count" in data, "Response should have 'count' field"
        assert isinstance(data["reservations"], list), "Reservations should be a list"
        
        print(f"Found {data['count']} imported reservations")
    
    def test_get_imported_reservations_with_filters(self, headers):
        """GET /api/channel-manager/v2/reservations/imported with status filter."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/reservations/imported?status=created&limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "reservations" in data
        print(f"Found {data['count']} reservations with status=created")
    
    def test_get_lineage_nonexistent(self, headers):
        """GET /api/channel-manager/v2/reservations/lineage/{id} - Should return 404."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/reservations/lineage/non-existent-reservation-id",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "detail" in data, "Response should have 'detail' field"
        print("Correctly returned 404 for non-existent reservation lineage")


class TestExelyTestBookingVerification:
    """Tests for Exely Test Booking Verification endpoint."""
    
    def test_verify_test_booking_empty(self, headers):
        """POST /api/channel-manager/exely/test-booking/verify - Empty payload."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/exely/test-booking/verify",
            headers=headers,
            json={}
        )
        # May return 200 (not_found) or 404 (no connection)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "verification_status" in data, "Response should have 'verification_status'"
            assert "before_count" in data, "Response should have 'before_count'"
            assert "after_count" in data, "Response should have 'after_count'"
            print(f"Verification status: {data['verification_status']}")
            print(f"Before: {data['before_count']}, After: {data['after_count']}")
        else:
            print("Exely connection not configured (expected in test environment)")
    
    def test_verify_test_booking_with_reservation_id(self, headers):
        """POST /api/channel-manager/exely/test-booking/verify - With reservation_id."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/exely/test-booking/verify",
            headers=headers,
            json={"reservation_id": "test-reservation-123"}
        )
        # May return 200 (error due to Exely sandbox) or 404 (no connection)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "verification_status" in data
            # Exely sandbox returns 500, so we expect 'error' status
            print(f"Verification status: {data['verification_status']}")
            if data.get("errors"):
                print(f"Errors (expected - Exely sandbox issue): {data['errors']}")
    
    def test_verify_test_booking_with_guest_name(self, headers):
        """POST /api/channel-manager/exely/test-booking/verify - With guest_name filter."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/exely/test-booking/verify",
            headers=headers,
            json={"guest_name": "Test Guest"}
        )
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "verification_status" in data
            print(f"Verification status: {data['verification_status']}")


class TestNavigationAndRoutes:
    """Tests for API route accessibility (protected by authentication)."""
    
    def test_api_requires_auth(self):
        """Verify API endpoints require authentication."""
        # Without auth header, should return 401 or 403
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/connectors"
        )
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("API correctly requires authentication")
    
    def test_api_with_invalid_token(self):
        """Verify API rejects invalid tokens."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/connectors",
            headers={"Authorization": "Bearer invalid-token-12345"}
        )
        assert response.status_code == 401, f"Expected 401 with invalid token, got {response.status_code}"
        print("API correctly rejects invalid tokens")


class TestEntityTypeTabs:
    """Tests for entity type tabs in MappingManager."""
    
    def test_supported_mapping_types(self, headers):
        """Verify supported mapping types are returned in readiness report."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/v2/mappings/{CONNECTOR_ID}/readiness-report",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check supported_mapping_types
        supported_types = data.get("supported_mapping_types", [])
        expected_types = ["room_type", "rate_plan"]
        
        for expected in expected_types:
            assert expected in supported_types, f"Expected '{expected}' in supported types"
        
        print(f"Supported mapping types: {supported_types}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
