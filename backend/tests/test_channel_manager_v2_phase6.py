"""
Channel Manager v2 Phase 6 Production Hardening API Tests

Tests for:
  - Reconciliation API endpoints (8 issue types, lifecycle management)
  - Scheduler API endpoints (run-all, run per connector)
  - Credential API endpoints (secure update, rotate, masked)
  - Event Sync API endpoints (single event, batch events)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://hotel-hardening.preview.emergentagent.com')
CONNECTOR_ID = "c79fd9cb-d240-4344-8b2d-7d8b71d6a681"

class TestChannelManagerV2Phase6:
    """Test all Channel Manager v2 Phase 6 endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for API calls"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token")
        assert token, f"No access_token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    # ─── Reconciliation API Tests ──────────────────────────────────
    
    def test_reconciliation_run(self, headers):
        """POST /api/channel-manager/v2/reconciliation/run"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/run",
            json={"connector_id": CONNECTOR_ID},
            headers=headers
        )
        assert response.status_code == 200, f"Reconciliation run failed: {response.text}"
        data = response.json()
        assert "connector_id" in data
        assert "issues_found" in data
        assert "severity_breakdown" in data
        print(f"Reconciliation run result: {data['issues_found']} issues found")
    
    def test_reconciliation_issues_list_open(self, headers):
        """GET /api/channel-manager/v2/reconciliation/issues?status=open"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues?status=open",
            headers=headers
        )
        assert response.status_code == 200, f"Get issues failed: {response.text}"
        data = response.json()
        assert "issues" in data
        assert "count" in data
        print(f"Open issues count: {data['count']}")
    
    def test_reconciliation_issues_summary(self, headers):
        """GET /api/channel-manager/v2/reconciliation/issues/summary"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues/summary",
            headers=headers
        )
        assert response.status_code == 200, f"Get summary failed: {response.text}"
        data = response.json()
        assert "total_open" in data or "by_type" in data or "by_severity" in data
        print(f"Issue summary: {data}")
    
    def test_reconciliation_create_custom_issue(self, headers):
        """POST /api/channel-manager/v2/reconciliation/issues - create custom issue"""
        test_issue_id = f"TEST_{uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues",
            json={
                "connector_id": CONNECTOR_ID,
                "issue_type": "stale_sync",
                "severity": "medium",
                "description": f"Test issue created by API test - {test_issue_id}",
                "suggested_actions": ["retry_sync"],
                "evidence_payload": {"test": True, "test_id": test_issue_id}
            },
            headers=headers
        )
        assert response.status_code == 200, f"Create issue failed: {response.text}"
        data = response.json()
        assert "issue" in data
        assert data["issue"]["issue_type"] == "stale_sync"
        print(f"Created issue: {data['issue'].get('id', 'unknown')[:8]}")
        return data["issue"]
    
    def test_reconciliation_issue_detail_and_lifecycle(self, headers):
        """Test issue detail and lifecycle: GET, PUT status, resolve, dismiss"""
        # First create an issue to test with
        test_id = f"TEST_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues",
            json={
                "connector_id": CONNECTOR_ID,
                "issue_type": "inventory_mismatch",
                "severity": "low",
                "description": f"Lifecycle test issue - {test_id}",
            },
            headers=headers
        )
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        issue_id = create_resp.json()["issue"]["id"]
        
        # GET issue detail
        detail_resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues/{issue_id}",
            headers=headers
        )
        assert detail_resp.status_code == 200, f"Get detail failed: {detail_resp.text}"
        assert detail_resp.json()["id"] == issue_id
        print(f"Issue detail retrieved: {issue_id[:8]}")
        
        # PUT status - open -> investigating
        status_resp = requests.put(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues/{issue_id}/status",
            json={"status": "investigating"},
            headers=headers
        )
        assert status_resp.status_code == 200, f"Status update failed: {status_resp.text}"
        assert status_resp.json()["status"] == "investigating"
        print(f"Status updated to investigating")
        
        # Resolve the issue
        resolve_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues/{issue_id}/resolve",
            json={"resolution": "Test resolution - API test"},
            headers=headers
        )
        assert resolve_resp.status_code == 200, f"Resolve failed: {resolve_resp.text}"
        assert resolve_resp.json()["status"] == "resolved"
        print(f"Issue resolved")
    
    def test_reconciliation_dismiss_issue(self, headers):
        """POST /api/channel-manager/v2/reconciliation/issues/{issue_id}/dismiss"""
        # Create issue to dismiss
        create_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues",
            json={
                "connector_id": CONNECTOR_ID,
                "issue_type": "rate_mismatch",
                "severity": "low",
                "description": "Dismiss test issue",
            },
            headers=headers
        )
        assert create_resp.status_code == 200
        issue_id = create_resp.json()["issue"]["id"]
        
        # Dismiss it
        dismiss_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues/{issue_id}/dismiss",
            json={"reason": "Test dismiss - not relevant"},
            headers=headers
        )
        assert dismiss_resp.status_code == 200, f"Dismiss failed: {dismiss_resp.text}"
        assert dismiss_resp.json()["status"] == "dismissed"
        print(f"Issue dismissed: {issue_id[:8]}")
    
    # ─── Scheduler API Tests ──────────────────────────────────────
    
    def test_scheduler_run_all(self, headers):
        """POST /api/channel-manager/v2/scheduler/run-all"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/scheduler/run-all",
            headers=headers
        )
        assert response.status_code == 200, f"Scheduler run-all failed: {response.text}"
        data = response.json()
        assert "connectors_checked" in data
        print(f"Scheduler run-all: {data['connectors_checked']} connectors checked")
    
    def test_scheduler_run_connector(self, headers):
        """POST /api/channel-manager/v2/scheduler/run/{connector_id}"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/scheduler/run/{CONNECTOR_ID}",
            headers=headers
        )
        assert response.status_code == 200, f"Scheduler run connector failed: {response.text}"
        data = response.json()
        # Could be skipped if connector is paused
        assert "connector_id" in data or "skipped" in data
        print(f"Scheduler run connector: {data}")
    
    # ─── Credential API Tests ──────────────────────────────────────
    
    def test_credentials_update_secure(self, headers):
        """PUT /api/channel-manager/v2/connectors/{connector_id}/credentials/secure"""
        response = requests.put(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/secure",
            json={"credentials": {"token": "test_secure_token_123", "hr_id": "99999"}},
            headers=headers
        )
        assert response.status_code == 200, f"Secure update failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"Credentials securely updated: {data['message']}")
    
    def test_credentials_rotate(self, headers):
        """POST /api/channel-manager/v2/connectors/{connector_id}/credentials/rotate"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/rotate",
            json={"credentials": {"token": "rotated_token_456", "hr_id": "88888"}},
            headers=headers
        )
        assert response.status_code == 200, f"Rotate failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"Credentials rotated: {data['message']}")
    
    def test_credentials_masked(self, headers):
        """GET /api/channel-manager/v2/connectors/{connector_id}/credentials/masked"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/masked",
            headers=headers
        )
        assert response.status_code == 200, f"Get masked failed: {response.text}"
        data = response.json()
        assert "connector_id" in data
        assert "credentials" in data
        # Verify credentials are masked (contain ****)
        creds = data["credentials"]
        if creds:
            for key, val in creds.items():
                if val:
                    assert "****" in str(val), f"Credential {key} not masked: {val}"
        print(f"Masked credentials retrieved: {list(data['credentials'].keys()) if data['credentials'] else 'empty'}")
    
    # ─── Event Sync API Tests ──────────────────────────────────────
    
    def test_event_sync_booking_created(self, headers):
        """POST /api/channel-manager/v2/events/sync - booking_created event"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "booking_created",
                "payload": {
                    "property_id": "prop-001",
                    "booking_id": f"TEST_booking_{uuid.uuid4().hex[:8]}",
                    "check_in": "2026-02-15",
                    "check_out": "2026-02-18",
                    "room_type_id": "standard",
                }
            },
            headers=headers
        )
        assert response.status_code == 200, f"Event sync failed: {response.text}"
        data = response.json()
        assert "handled" in data
        print(f"Event sync booking_created: handled={data['handled']}")
    
    def test_event_sync_rate_changed(self, headers):
        """POST /api/channel-manager/v2/events/sync - rate_changed event"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "rate_changed",
                "payload": {
                    "property_id": "prop-001",
                    "room_type_id": "standard",
                    "rate_plan_id": "rack",
                    "date_start": "2026-03-01",
                    "date_end": "2026-03-31",
                }
            },
            headers=headers
        )
        assert response.status_code == 200, f"Event sync failed: {response.text}"
        data = response.json()
        assert "handled" in data
        print(f"Event sync rate_changed: handled={data['handled']}")
    
    def test_event_sync_batch(self, headers):
        """POST /api/channel-manager/v2/events/sync/batch"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync/batch",
            json={
                "events": [
                    {
                        "event_type": "booking_created",
                        "payload": {
                            "property_id": "prop-001",
                            "booking_id": f"TEST_batch_1_{uuid.uuid4().hex[:8]}",
                            "check_in": "2026-04-01",
                            "check_out": "2026-04-03",
                        }
                    },
                    {
                        "event_type": "room_blocked",
                        "payload": {
                            "property_id": "prop-001",
                            "room_id": "room-101",
                            "date_start": "2026-04-05",
                            "date_end": "2026-04-07",
                        }
                    },
                    {
                        "event_type": "restriction_changed",
                        "payload": {
                            "property_id": "prop-001",
                            "date_start": "2026-04-10",
                            "date_end": "2026-04-15",
                        }
                    }
                ]
            },
            headers=headers
        )
        assert response.status_code == 200, f"Batch sync failed: {response.text}"
        data = response.json()
        assert "processed" in data
        print(f"Batch event sync: processed={data['processed']} events")
    
    def test_event_sync_unsupported_event(self, headers):
        """POST /api/channel-manager/v2/events/sync - unsupported event type"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "invalid_event_type",
                "payload": {"property_id": "prop-001"}
            },
            headers=headers
        )
        assert response.status_code == 200, f"Event sync failed: {response.text}"
        data = response.json()
        assert data["handled"] is False
        print(f"Unsupported event correctly rejected: {data}")


class TestReconciliationIssueTypes:
    """Test creation of all 8 reconciliation issue types"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    @pytest.mark.parametrize("issue_type,severity", [
        ("inventory_mismatch", "critical"),
        ("rate_mismatch", "high"),
        ("missing_reservation", "high"),
        ("stale_sync", "medium"),
        ("invalid_mapping", "high"),
        ("ack_failed", "high"),
        ("ack_pending_too_long", "medium"),
        ("unprocessed_import", "low"),
    ])
    def test_create_issue_type(self, headers, issue_type, severity):
        """Test creation of each issue type"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/issues",
            json={
                "connector_id": CONNECTOR_ID,
                "issue_type": issue_type,
                "severity": severity,
                "description": f"Test {issue_type} issue with {severity} severity",
            },
            headers=headers
        )
        assert response.status_code == 200, f"Failed to create {issue_type}: {response.text}"
        data = response.json()
        assert data["issue"]["issue_type"] == issue_type
        assert data["issue"]["severity"] == severity
        print(f"Created {issue_type} issue with {severity} severity")


class TestConnectorEndpoints:
    """Test connector-related endpoints that are prerequisites"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_list_connectors(self, headers):
        """GET /api/channel-manager/v2/connectors"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers
        )
        assert response.status_code == 200, f"List connectors failed: {response.text}"
        data = response.json()
        assert "connectors" in data
        print(f"Found {data['count']} connectors")
    
    def test_get_connector(self, headers):
        """GET /api/channel-manager/v2/connectors/{connector_id}"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}",
            headers=headers
        )
        assert response.status_code == 200, f"Get connector failed: {response.text}"
        data = response.json()
        # Response may use "connector_id" or "id" field
        connector_id = data.get("connector_id") or data.get("id")
        assert connector_id == CONNECTOR_ID
        print(f"Connector retrieved: {data.get('display_name', 'unknown')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
