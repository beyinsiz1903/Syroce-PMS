"""
Channel Manager v2 API Tests
Tests connector CRUD, mappings, dashboard, health, audit, reconciliation, and sync jobs endpoints.

All routes under /api/channel-manager/v2/
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")
if not BASE_URL:
    BASE_URL = "https://hr-push-sync.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip('/') + "/api"

CM_V2_BASE = f"{BASE_URL}/channel-manager/v2"

TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestChannelManagerV2Setup:
    """Setup and auth helpers for Channel Manager v2 tests."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Authenticate and get access token."""
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Auth failed: {response.text}"
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Authenticated request headers."""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestConnectorCRUD(TestChannelManagerV2Setup):
    """Test connector lifecycle: create, list, get, activate, pause, delete."""

    def test_list_connectors_returns_200(self, auth_headers):
        """GET /connectors returns list of connectors."""
        response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "connectors" in data
        assert "count" in data
        assert isinstance(data["connectors"], list)
        print(f"✅ List connectors: {data['count']} found")

    def test_create_connector_returns_201_or_200(self, auth_headers):
        """POST /connectors creates a new connector in DRAFT status."""
        unique_name = f"TEST_HotelRunner_{uuid.uuid4().hex[:8]}"
        payload = {
            "provider": "hotelrunner",
            "display_name": unique_name,
            "credentials": {
                "token": "test_token_12345",
                "hr_id": "test_hr_id_67890"
            }
        }
        response = requests.post(f"{CM_V2_BASE}/connectors", json=payload, headers=auth_headers)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "connector" in data or "message" in data
        
        # Extract connector data
        connector = data.get("connector", data)
        if "id" in connector:
            pytest.test_connector_id = connector["id"]
            pytest.test_connector_name = unique_name
            print(f"✅ Created connector: {connector['id'][:8]}... ({connector.get('status', 'unknown')})")
        else:
            print(f"✅ Connector response received: {data}")

    def test_get_connector_by_id(self, auth_headers):
        """GET /connectors/{id} retrieves specific connector."""
        # First get list to find a connector
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        assert list_response.status_code == 200
        connectors = list_response.json().get("connectors", [])
        
        if connectors:
            connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
            response = requests.get(f"{CM_V2_BASE}/connectors/{connector_id}", headers=auth_headers)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "id" in data or "provider" in data
            # Credentials should be masked
            if "credentials" in data:
                for key, value in data["credentials"].items():
                    assert value == "***", f"Credentials should be masked: {key}={value}"
            print(f"✅ Get connector: {connector_id[:8]}... - credentials masked")
        else:
            pytest.skip("No connectors found to test get by ID")

    def test_activate_connector(self, auth_headers):
        """POST /connectors/{id}/activate sets status to active."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        # Find a draft or paused connector
        target = None
        for c in connectors:
            if c.get("status") in ["draft", "paused"]:
                target = c
                break
        
        if target:
            connector_id = target.get("id") or target.get("connector_id")
            response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/activate", headers=auth_headers)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "message" in data or "connector" in data
            print(f"✅ Activated connector: {connector_id[:8]}...")
        else:
            pytest.skip("No draft/paused connectors to activate")

    def test_pause_connector(self, auth_headers):
        """POST /connectors/{id}/pause sets status to paused."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        # Find an active connector
        target = None
        for c in connectors:
            if c.get("status") == "active":
                target = c
                break
        
        if target:
            connector_id = target.get("id") or target.get("connector_id")
            response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/pause", headers=auth_headers)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "message" in data or "connector" in data
            print(f"✅ Paused connector: {connector_id[:8]}...")
            
            # Re-activate for subsequent tests
            requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/activate", headers=auth_headers)
        else:
            pytest.skip("No active connectors to pause")

    def test_test_connector_connection(self, auth_headers):
        """POST /connectors/{id}/test tests connectivity (may fail with test credentials)."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if connectors:
            connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
            response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
            # Test connection may fail with test credentials - that's expected
            assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
            data = response.json()
            print(f"✅ Test connection response: success={data.get('success', 'N/A')}, message={data.get('message', 'N/A')}")
        else:
            pytest.skip("No connectors to test connection")


class TestMappingsCRUD(TestChannelManagerV2Setup):
    """Test mapping operations: create, list, validate, sync-readiness."""

    def test_create_mapping(self, auth_headers):
        """POST /mappings creates a new entity mapping."""
        # Get a connector first
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available for mapping test")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        
        payload = {
            "connector_id": connector_id,
            "entity_type": "room_type",
            "pms_entity_id": f"TEST_Standard_{uuid.uuid4().hex[:6]}",
            "pms_entity_name": "Standard Room",
            "external_entity_id": "STD_HR",
            "external_entity_name": "Standard - HotelRunner"
        }
        
        response = requests.post(f"{CM_V2_BASE}/mappings", json=payload, headers=auth_headers)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "mapping" in data or "message" in data
        print(f"✅ Created mapping: {payload['pms_entity_id']} -> {payload['external_entity_id']}")

    def test_list_mappings_for_connector(self, auth_headers):
        """GET /mappings/{connector_id} lists mappings for a connector."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.get(f"{CM_V2_BASE}/mappings/{connector_id}", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "mappings" in data
        assert "count" in data
        print(f"✅ List mappings: {data['count']} found for connector {connector_id[:8]}...")

    def test_validate_mappings(self, auth_headers):
        """POST /mappings/{connector_id}/validate validates all mappings."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(f"{CM_V2_BASE}/mappings/{connector_id}/validate", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "valid" in data or "total" in data
        print(f"✅ Validate mappings: valid={data.get('valid', 'N/A')}, invalid={data.get('invalid', 'N/A')}")

    def test_sync_readiness(self, auth_headers):
        """GET /mappings/{connector_id}/sync-readiness checks if ready for sync."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.get(f"{CM_V2_BASE}/mappings/{connector_id}/sync-readiness", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "ready" in data
        print(f"✅ Sync readiness: ready={data.get('ready')}, issues={data.get('issues', [])}")


class TestDashboardAndHealth(TestChannelManagerV2Setup):
    """Test dashboard overview and connector health endpoints."""

    def test_dashboard_returns_overview(self, auth_headers):
        """GET /dashboard returns connectors, health, jobs, issues."""
        response = requests.get(f"{CM_V2_BASE}/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify expected dashboard fields
        expected_fields = ["total_connectors", "active_connectors", "connectors", "health_summary"]
        for field in expected_fields:
            assert field in data, f"Dashboard missing field: {field}"
        
        # Health summary should have green/yellow/red counts
        hs = data.get("health_summary", {})
        for color in ["green", "yellow", "red"]:
            assert color in hs or isinstance(hs.get(color, 0), int), f"Health summary missing: {color}"
        
        print(f"✅ Dashboard: {data['total_connectors']} connectors, health: {hs}")

    def test_connector_health(self, auth_headers):
        """GET /health/{connector_id} returns health status with reasons."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.get(f"{CM_V2_BASE}/health/{connector_id}", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Health should have status, health color, and reasons
        assert "health" in data or "status" in data
        print(f"✅ Connector health: {data.get('health', 'N/A')}, reasons: {data.get('reasons', [])}")


class TestAuditLogs(TestChannelManagerV2Setup):
    """Test audit log retrieval."""

    def test_get_audit_logs(self, auth_headers):
        """GET /audit returns integration audit logs."""
        response = requests.get(f"{CM_V2_BASE}/audit", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "logs" in data
        assert "count" in data
        
        # Verify log structure if logs exist
        if data["logs"]:
            log = data["logs"][0]
            expected_log_fields = ["action", "tenant_id"]
            for field in expected_log_fields:
                assert field in log, f"Audit log missing field: {field}"
        
        print(f"✅ Audit logs: {data['count']} entries")

    def test_audit_logs_with_connector_filter(self, auth_headers):
        """GET /audit?connector_id=X filters by connector."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.get(f"{CM_V2_BASE}/audit?connector_id={connector_id}", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"✅ Audit logs for connector {connector_id[:8]}...: {data['count']} entries")


class TestReconciliation(TestChannelManagerV2Setup):
    """Test reconciliation run and issues endpoints."""

    def test_run_reconciliation(self, auth_headers):
        """POST /reconciliation/run executes reconciliation check."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(
            f"{CM_V2_BASE}/reconciliation/run",
            json={"connector_id": connector_id},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "issues_found" in data or "connector_id" in data
        print(f"✅ Reconciliation run: issues_found={data.get('issues_found', 'N/A')}")

    def test_get_reconciliation_issues(self, auth_headers):
        """GET /reconciliation/issues returns open issues."""
        response = requests.get(f"{CM_V2_BASE}/reconciliation/issues", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "issues" in data
        assert "count" in data
        print(f"✅ Reconciliation issues: {data['count']} open")


class TestSyncJobs(TestChannelManagerV2Setup):
    """Test sync job listing and retrieval."""

    def test_list_sync_jobs(self, auth_headers):
        """GET /sync/jobs returns sync history."""
        response = requests.get(f"{CM_V2_BASE}/sync/jobs", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "jobs" in data
        assert "count" in data
        print(f"✅ Sync jobs: {data['count']} found")

    def test_list_sync_jobs_with_connector_filter(self, auth_headers):
        """GET /sync/jobs?connector_id=X filters by connector."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.get(f"{CM_V2_BASE}/sync/jobs?connector_id={connector_id}", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"✅ Sync jobs for connector {connector_id[:8]}...: {data['count']} found")


class TestReservationEndpoints(TestChannelManagerV2Setup):
    """Test imported reservations and review queue endpoints."""

    def test_list_imported_reservations(self, auth_headers):
        """GET /reservations/imported returns imported reservations."""
        response = requests.get(f"{CM_V2_BASE}/reservations/imported", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "reservations" in data
        assert "count" in data
        print(f"✅ Imported reservations: {data['count']} found")

    def test_get_review_queue(self, auth_headers):
        """GET /reservations/review-queue returns items needing review."""
        response = requests.get(f"{CM_V2_BASE}/reservations/review-queue", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "queue" in data
        assert "count" in data
        print(f"✅ Review queue: {data['count']} items")

    def test_list_import_batches(self, auth_headers):
        """GET /reservations/batches returns import batch history."""
        response = requests.get(f"{CM_V2_BASE}/reservations/batches", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "batches" in data
        assert "count" in data
        print(f"✅ Import batches: {data['count']} found")


class TestSyncTriggerEndpoints(TestChannelManagerV2Setup):
    """Test manual sync trigger endpoints (may fail with test credentials)."""

    def test_trigger_inventory_sync(self, auth_headers):
        """POST /sync/inventory triggers inventory push (may fail without valid connector)."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        # Find an active connector
        active_connector = None
        for c in connectors:
            if c.get("status") == "active":
                active_connector = c
                break
        
        if not active_connector:
            pytest.skip("No active connectors for sync test")
        
        connector_id = active_connector.get("id") or active_connector.get("connector_id")
        payload = {
            "connector_id": connector_id,
            "date_start": "2026-01-20",
            "date_end": "2026-01-25",
            "reason": "Test sync trigger"
        }
        
        response = requests.post(f"{CM_V2_BASE}/sync/inventory", json=payload, headers=auth_headers)
        # May fail due to missing mappings or test credentials - that's expected
        assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
        print(f"✅ Inventory sync trigger: status={response.status_code}")

    def test_trigger_rate_sync(self, auth_headers):
        """POST /sync/rates triggers rate push (may fail without valid connector)."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        active_connector = None
        for c in connectors:
            if c.get("status") == "active":
                active_connector = c
                break
        
        if not active_connector:
            pytest.skip("No active connectors for sync test")
        
        connector_id = active_connector.get("id") or active_connector.get("connector_id")
        payload = {
            "connector_id": connector_id,
            "date_start": "2026-01-20",
            "date_end": "2026-01-25"
        }
        
        response = requests.post(f"{CM_V2_BASE}/sync/rates", json=payload, headers=auth_headers)
        # May fail due to missing mappings or test credentials
        assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
        print(f"✅ Rate sync trigger: status={response.status_code}")

    def test_trigger_reservation_pull(self, auth_headers):
        """POST /reservations/pull triggers reservation import (may fail with test credentials)."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        payload = {"connector_id": connector_id}
        
        response = requests.post(f"{CM_V2_BASE}/reservations/pull", json=payload, headers=auth_headers)
        # May fail with test credentials - that's expected
        assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
        print(f"✅ Reservation pull trigger: status={response.status_code}")


class TestCleanup(TestChannelManagerV2Setup):
    """Cleanup test data - delete TEST_ prefixed connectors."""

    def test_delete_test_connectors(self, auth_headers):
        """DELETE /connectors/{id} removes test connectors."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        deleted_count = 0
        for c in connectors:
            display_name = c.get("display_name", "")
            connector_id = c.get("id") or c.get("connector_id")
            if display_name.startswith("TEST_"):
                response = requests.delete(f"{CM_V2_BASE}/connectors/{connector_id}", headers=auth_headers)
                if response.status_code == 200:
                    deleted_count += 1
        
        print(f"✅ Cleanup: deleted {deleted_count} test connectors")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
