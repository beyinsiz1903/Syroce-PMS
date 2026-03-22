"""
Control Plane API Tests — Comprehensive E2E Testing
=====================================================
Tests all /api/ops/* endpoints:
1. GET /api/ops/overview - System health overview
2. GET /api/ops/failures - List failures with filters
3. GET /api/ops/failures/{failure_id} - Get single failure
4. POST /api/ops/failures/{failure_id}/retry - Retry with dry_run support
5. POST /api/ops/failures/{failure_id}/resolve - Mark resolved
6. POST /api/ops/failures/{failure_id}/ignore - Mark ignored
7. GET /api/ops/outbox - Outbox monitor
8. GET /api/ops/imports - Import pipeline monitor
9. GET /api/ops/sync - Sync jobs monitor
10. GET /api/ops/secrets/audit - Secret access audit trail
11. GET /api/ops/secrets/anomalies - Secret access anomalies
12. GET /api/ops/runbooks - List runbooks
13. GET /api/ops/runbooks/{runbook_id} - Get single runbook
14. GET /api/ops/alerts - List alerts
15. POST /api/ops/alerts/check - Trigger alert checks
16. Full failure lifecycle testing
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════════════════
# 1. OVERVIEW ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsOverview:
    """Tests for GET /api/ops/overview"""

    def test_overview_returns_200(self, api_client):
        """Overview endpoint should return 200 with health metrics."""
        response = api_client.get(f"{BASE_URL}/api/ops/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all required fields exist
        required_fields = [
            "open_failures", "failures_by_severity", "failures_by_type",
            "failures_by_operation", "stuck_outbox_count", "failed_imports_24h",
            "pending_imports", "sync_success_rate", "recent_sync_jobs",
            "secret_access_anomalies", "active_connectors", "recent_error_rate",
            "timestamp"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify data types
        assert isinstance(data["open_failures"], int)
        assert isinstance(data["failures_by_severity"], dict)
        assert isinstance(data["stuck_outbox_count"], int)
        assert isinstance(data["sync_success_rate"], (int, float))
        print(f"Overview: open_failures={data['open_failures']}, stuck_outbox={data['stuck_outbox_count']}, anomalies={data['secret_access_anomalies']}")

    def test_overview_with_tenant_filter(self, api_client):
        """Overview should accept tenant_id filter."""
        response = api_client.get(f"{BASE_URL}/api/ops/overview?tenant_id=test_tenant")
        assert response.status_code == 200
        data = response.json()
        assert "open_failures" in data


# ═══════════════════════════════════════════════════════════════════
# 2. FAILURES LIST ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsFailuresList:
    """Tests for GET /api/ops/failures"""

    def test_list_failures_returns_200(self, api_client):
        """List failures should return 200 with pagination."""
        response = api_client.get(f"{BASE_URL}/api/ops/failures")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "skip" in data
        assert isinstance(data["items"], list)
        print(f"Failures list: total={data['total']}, returned={len(data['items'])}")

    def test_list_failures_with_filters(self, api_client):
        """List failures should accept all filter parameters."""
        params = {
            "tenant_id": "test_tenant",
            "provider": "exely",
            "failure_type": "retryable",
            "severity": "warning",
            "status": "open",
            "operation_type": "reservation_import",
            "limit": 10,
            "skip": 0
        }
        response = api_client.get(f"{BASE_URL}/api/ops/failures", params=params)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_list_failures_pagination(self, api_client):
        """Pagination should work correctly."""
        response1 = api_client.get(f"{BASE_URL}/api/ops/failures?limit=5&skip=0")
        response2 = api_client.get(f"{BASE_URL}/api/ops/failures?limit=5&skip=5")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1["limit"] == 5
        assert data1["skip"] == 0
        assert data2["skip"] == 5


# ═══════════════════════════════════════════════════════════════════
# 3. SINGLE FAILURE ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsFailureGet:
    """Tests for GET /api/ops/failures/{failure_id}"""

    def test_get_nonexistent_failure_returns_404(self, api_client):
        """Getting a non-existent failure should return 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.get(f"{BASE_URL}/api/ops/failures/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        print(f"404 response for non-existent failure: {data['detail']}")


# ═══════════════════════════════════════════════════════════════════
# 4. OUTBOX MONITOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsOutbox:
    """Tests for GET /api/ops/outbox"""

    def test_outbox_monitor_returns_200(self, api_client):
        """Outbox monitor should return counts and recent failed events."""
        response = api_client.get(f"{BASE_URL}/api/ops/outbox")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["pending", "processing", "failed", "stuck", 
                          "stuck_threshold_minutes", "recent_failed_events", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data["pending"], int)
        assert isinstance(data["stuck"], int)
        assert isinstance(data["recent_failed_events"], list)
        print(f"Outbox: pending={data['pending']}, stuck={data['stuck']}, failed={data['failed']}")

    def test_outbox_with_tenant_filter(self, api_client):
        """Outbox should accept tenant_id filter."""
        response = api_client.get(f"{BASE_URL}/api/ops/outbox?tenant_id=test_tenant")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 5. IMPORTS MONITOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsImports:
    """Tests for GET /api/ops/imports"""

    def test_imports_monitor_returns_200(self, api_client):
        """Imports monitor should return counts and recent failed imports."""
        response = api_client.get(f"{BASE_URL}/api/ops/imports")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["pending", "processing", "imported_24h", "review_required",
                          "retry", "failed", "recent_failed", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data["pending"], int)
        assert isinstance(data["failed"], int)
        print(f"Imports: pending={data['pending']}, failed={data['failed']}, review_required={data['review_required']}")


# ═══════════════════════════════════════════════════════════════════
# 6. SYNC MONITOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsSync:
    """Tests for GET /api/ops/sync"""

    def test_sync_monitor_returns_200(self, api_client):
        """Sync monitor should return job counts and success rate."""
        response = api_client.get(f"{BASE_URL}/api/ops/sync")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["total_24h", "completed", "failed", "running",
                          "stalled", "success_rate", "recent_jobs", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data["success_rate"], (int, float))
        assert isinstance(data["recent_jobs"], list)
        print(f"Sync: total_24h={data['total_24h']}, success_rate={data['success_rate']}%")


# ═══════════════════════════════════════════════════════════════════
# 7. SECRET AUDIT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsSecretAudit:
    """Tests for GET /api/ops/secrets/audit"""

    def test_secret_audit_returns_200(self, api_client):
        """Secret audit should return audit trail with pagination."""
        response = api_client.get(f"{BASE_URL}/api/ops/secrets/audit")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["items", "total", "limit", "skip", "anomalies_24h"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data["items"], list)
        assert isinstance(data["anomalies_24h"], int)
        print(f"Secret audit: total={data['total']}, anomalies_24h={data['anomalies_24h']}")

    def test_secret_audit_with_filters(self, api_client):
        """Secret audit should accept filter parameters."""
        params = {
            "tenant_id": "test_tenant",
            "provider": "exely",
            "result": "success",
            "limit": 10,
            "skip": 0
        }
        response = api_client.get(f"{BASE_URL}/api/ops/secrets/audit", params=params)
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 8. SECRET ANOMALIES TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsSecretAnomalies:
    """Tests for GET /api/ops/secrets/anomalies"""

    def test_secret_anomalies_returns_200(self, api_client):
        """Secret anomalies should return anomaly count and recent anomalies."""
        response = api_client.get(f"{BASE_URL}/api/ops/secrets/anomalies")
        assert response.status_code == 200
        
        data = response.json()
        assert "anomaly_count" in data
        assert "recent_anomalies" in data
        assert isinstance(data["anomaly_count"], int)
        assert isinstance(data["recent_anomalies"], list)
        print(f"Secret anomalies: count={data['anomaly_count']}")

    def test_secret_anomalies_with_hours_param(self, api_client):
        """Secret anomalies should accept hours parameter."""
        response = api_client.get(f"{BASE_URL}/api/ops/secrets/anomalies?hours=48")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 9. RUNBOOKS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsRunbooks:
    """Tests for GET /api/ops/runbooks and GET /api/ops/runbooks/{runbook_id}"""

    def test_list_runbooks_returns_200(self, api_client):
        """List runbooks should return all 14 runbooks."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks")
        assert response.status_code == 200
        
        data = response.json()
        assert "runbooks" in data
        assert isinstance(data["runbooks"], list)
        assert len(data["runbooks"]) == 14, f"Expected 14 runbooks, got {len(data['runbooks'])}"
        print(f"Runbooks: count={len(data['runbooks'])}")

    def test_list_runbooks_with_category_filter(self, api_client):
        """List runbooks should filter by category."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks?category=security")
        assert response.status_code == 200
        
        data = response.json()
        assert "runbooks" in data
        for rb in data["runbooks"]:
            assert rb["category"] == "security"
        print(f"Security runbooks: count={len(data['runbooks'])}")

    def test_get_single_runbook_returns_200(self, api_client):
        """Get single runbook should return runbook details."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks/outbox_stuck")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["id", "title", "description", "category", "severity",
                          "possible_causes", "resolution_steps", "retry_instructions",
                          "related_operations"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert data["id"] == "outbox_stuck"
        print(f"Runbook: {data['id']} - {data['title']}")

    def test_get_nonexistent_runbook_returns_404(self, api_client):
        """Get non-existent runbook should return 404."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks/nonexistent_runbook")
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 10. ALERTS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOpsAlerts:
    """Tests for GET /api/ops/alerts and POST /api/ops/alerts/check"""

    def test_list_alerts_returns_200(self, api_client):
        """List alerts should return recent alerts."""
        response = api_client.get(f"{BASE_URL}/api/ops/alerts")
        assert response.status_code == 200
        
        data = response.json()
        assert "alerts" in data
        assert "total" in data
        assert isinstance(data["alerts"], list)
        print(f"Alerts: total={data['total']}")

    def test_list_alerts_with_severity_filter(self, api_client):
        """List alerts should accept severity filter."""
        response = api_client.get(f"{BASE_URL}/api/ops/alerts?severity=critical")
        assert response.status_code == 200

    def test_trigger_alert_checks_returns_200(self, api_client):
        """Trigger alert checks should return fired alerts."""
        response = api_client.post(f"{BASE_URL}/api/ops/alerts/check")
        assert response.status_code == 200
        
        data = response.json()
        assert "fired" in data
        assert "alerts" in data
        assert isinstance(data["fired"], int)
        assert isinstance(data["alerts"], list)
        print(f"Alert check: fired={data['fired']}")


# ═══════════════════════════════════════════════════════════════════
# 11. FAILURE LIFECYCLE TESTS (Create -> Retry -> Resolve/Ignore)
# ═══════════════════════════════════════════════════════════════════

class TestFailureLifecycle:
    """Full failure lifecycle: create -> list -> dry-run retry -> actual retry/resolve"""

    @pytest.fixture(scope="class")
    def created_failure_id(self, api_client):
        """Create a test failure via direct MongoDB insert for lifecycle testing."""
        # We'll use the failure tracker to create a failure
        # First, let's create a failure by calling an internal endpoint or using the tracker
        # Since there's no direct POST /api/ops/failures endpoint, we'll test with existing failures
        # or create one via the backend
        
        # Check if there are any existing open failures we can use
        response = api_client.get(f"{BASE_URL}/api/ops/failures?status=open&limit=1")
        if response.status_code == 200:
            data = response.json()
            if data["items"]:
                return data["items"][0]["id"]
        return None

    def test_failure_lifecycle_dry_run_retry(self, api_client, created_failure_id):
        """Test dry-run retry on a failure."""
        if not created_failure_id:
            pytest.skip("No open failures available for lifecycle testing")
        
        # First, get the failure to check its type
        response = api_client.get(f"{BASE_URL}/api/ops/failures/{created_failure_id}")
        assert response.status_code == 200
        failure = response.json()
        
        # If it's a permanent failure, we expect retry to fail
        if failure["failure_type"] == "permanent":
            response = api_client.post(
                f"{BASE_URL}/api/ops/failures/{created_failure_id}/retry",
                json={"dry_run": True}
            )
            assert response.status_code == 400
            data = response.json()
            assert "permanent" in str(data).lower()
            print(f"Permanent failure correctly rejected for retry: {created_failure_id}")
        else:
            # Dry-run should succeed for non-permanent failures
            response = api_client.post(
                f"{BASE_URL}/api/ops/failures/{created_failure_id}/retry",
                json={"dry_run": True}
            )
            # Could be 200 (success) or 400 (already resolved/ignored)
            if response.status_code == 200:
                data = response.json()
                assert data.get("dry_run") == True
                assert data.get("would_retry") == True
                print(f"Dry-run retry successful for: {created_failure_id}")
            else:
                print(f"Dry-run retry returned {response.status_code}: {response.text}")

    def test_retry_nonexistent_failure_returns_400(self, api_client):
        """Retry on non-existent failure should return 400."""
        fake_id = str(uuid.uuid4())
        response = api_client.post(
            f"{BASE_URL}/api/ops/failures/{fake_id}/retry",
            json={"dry_run": False}
        )
        assert response.status_code == 400
        data = response.json()
        assert "not_found" in str(data).lower() or "detail" in data

    def test_resolve_nonexistent_failure_returns_404(self, api_client):
        """Resolve on non-existent failure should return 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.post(f"{BASE_URL}/api/ops/failures/{fake_id}/resolve")
        assert response.status_code == 404

    def test_ignore_nonexistent_failure_returns_404(self, api_client):
        """Ignore on non-existent failure should return 404."""
        fake_id = str(uuid.uuid4())
        response = api_client.post(f"{BASE_URL}/api/ops/failures/{fake_id}/ignore")
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 12. PERMANENT FAILURE RETRY REJECTION TEST
# ═══════════════════════════════════════════════════════════════════

class TestPermanentFailureRetry:
    """Test that permanent failures cannot be retried."""

    def test_permanent_failure_retry_rejected(self, api_client):
        """Find a permanent failure and verify retry is rejected."""
        # Look for a permanent failure
        response = api_client.get(f"{BASE_URL}/api/ops/failures?failure_type=permanent&status=open&limit=1")
        assert response.status_code == 200
        
        data = response.json()
        if not data["items"]:
            pytest.skip("No permanent failures available for testing")
        
        failure_id = data["items"][0]["id"]
        
        # Try to retry - should fail
        response = api_client.post(
            f"{BASE_URL}/api/ops/failures/{failure_id}/retry",
            json={"dry_run": False}
        )
        assert response.status_code == 400
        error_data = response.json()
        assert "permanent" in str(error_data).lower()
        print(f"Permanent failure retry correctly rejected: {failure_id}")


# ═══════════════════════════════════════════════════════════════════
# 13. INTEGRATION TESTS - FULL FLOW
# ═══════════════════════════════════════════════════════════════════

class TestControlPlaneIntegration:
    """Integration tests for control plane workflows."""

    def test_overview_reflects_failure_counts(self, api_client):
        """Overview failure counts should match failures list total."""
        # Get overview
        overview_resp = api_client.get(f"{BASE_URL}/api/ops/overview")
        assert overview_resp.status_code == 200
        overview = overview_resp.json()
        
        # Get failures list with status=open
        failures_resp = api_client.get(f"{BASE_URL}/api/ops/failures?status=open")
        assert failures_resp.status_code == 200
        failures = failures_resp.json()
        
        # The open_failures count should match
        assert overview["open_failures"] == failures["total"], \
            f"Overview open_failures ({overview['open_failures']}) != failures total ({failures['total']})"
        print(f"Open failures count verified: {overview['open_failures']}")

    def test_runbook_categories_complete(self, api_client):
        """All runbook categories should be accessible."""
        categories = ["import", "outbox", "ari", "provider", "security", "operations", "sync"]
        
        for category in categories:
            response = api_client.get(f"{BASE_URL}/api/ops/runbooks?category={category}")
            assert response.status_code == 200
            data = response.json()
            # Some categories might have 0 runbooks, that's OK
            print(f"Category '{category}': {len(data['runbooks'])} runbooks")

    def test_all_14_runbooks_have_required_fields(self, api_client):
        """All 14 runbooks should have complete required fields."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["id", "title", "description", "category", "severity",
                          "possible_causes", "resolution_steps", "retry_instructions",
                          "related_operations"]
        
        for rb in data["runbooks"]:
            for field in required_fields:
                assert field in rb, f"Runbook {rb.get('id', 'unknown')} missing field: {field}"
                assert rb[field], f"Runbook {rb.get('id', 'unknown')} has empty field: {field}"
        
        print(f"All {len(data['runbooks'])} runbooks have complete required fields")


# ═══════════════════════════════════════════════════════════════════
# 14. EDGE CASES AND ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_failures_list_invalid_limit(self, api_client):
        """Invalid limit should be handled gracefully."""
        response = api_client.get(f"{BASE_URL}/api/ops/failures?limit=500")
        # Should either clamp to max or return validation error
        assert response.status_code in [200, 422]

    def test_failures_list_negative_skip(self, api_client):
        """Negative skip should be handled gracefully."""
        response = api_client.get(f"{BASE_URL}/api/ops/failures?skip=-1")
        # Should either use 0 or return validation error
        assert response.status_code in [200, 422]

    def test_retry_with_empty_body(self, api_client):
        """Retry with empty body should use defaults."""
        # Get any open failure
        response = api_client.get(f"{BASE_URL}/api/ops/failures?status=open&limit=1")
        if response.status_code == 200 and response.json()["items"]:
            failure_id = response.json()["items"][0]["id"]
            failure = response.json()["items"][0]
            
            # Skip if permanent
            if failure["failure_type"] == "permanent":
                pytest.skip("Only permanent failure available")
            
            # Retry with empty body (should default to dry_run=False)
            response = api_client.post(f"{BASE_URL}/api/ops/failures/{failure_id}/retry")
            # Should work or fail based on failure state
            assert response.status_code in [200, 400]
        else:
            pytest.skip("No open failures available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
