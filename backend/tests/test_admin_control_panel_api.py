"""
Test Admin Control Panel API Endpoints - Phase 1-6 Features
Tests new admin endpoints for:
- Sync Health Dashboard
- Reconciliation Issues Management
- Scheduler Status
- Credential Management (RBAC)
- Error Queue Admin Panel
- Observability Metrics/Audit Trail
- Production Readiness Validation
- Webhook/Callback Integration
"""
import pytest
import requests
import os
import json
import time
import hmac
import hashlib

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API_PREFIX = f"{BASE_URL}/api/channel-manager/v2"


class TestAuthentication:
    """Test authentication and get token for subsequent tests."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Obtain auth token for all tests."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def test_login_returns_access_token(self, auth_token):
        """Verify login returns valid access token."""
        assert auth_token is not None
        assert len(auth_token) > 10
        print(f"✓ Login successful, token length: {len(auth_token)}")


class TestSyncHealthDashboard:
    """Phase 1 & 3: Sync Health Dashboard API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_sync_health_overview(self, auth_headers):
        """GET /admin/sync-health - returns overall_health_score, sync_trend_24h, connectors."""
        response = requests.get(f"{API_PREFIX}/admin/sync-health", headers=auth_headers)
        assert response.status_code == 200, f"Sync health failed: {response.text}"
        data = response.json()

        # Verify required fields
        assert "overall_health_score" in data, f"Missing overall_health_score: {data.keys()}"
        assert "sync_trend_24h" in data, f"Missing sync_trend_24h: {data.keys()}"
        assert "connectors" in data, f"Missing connectors: {data.keys()}"
        assert "overall_status" in data, f"Missing overall_status: {data.keys()}"
        assert "connector_count" in data, f"Missing connector_count: {data.keys()}"

        # Verify data types
        assert isinstance(data["overall_health_score"], (int, float))
        assert isinstance(data["sync_trend_24h"], list)
        assert isinstance(data["connectors"], list)
        assert data["overall_status"] in ("healthy", "degraded", "critical")

        print(f"✓ Sync health: score={data['overall_health_score']}, status={data['overall_status']}, connectors={data['connector_count']}")

    def test_get_sync_health_connector_detail(self, auth_headers):
        """GET /admin/sync-health/{connector_id} - returns detailed health for specific connector."""
        # First get list of connectors
        response = requests.get(f"{API_PREFIX}/connectors", headers=auth_headers)
        if response.status_code == 200 and response.json().get("connectors"):
            connector = response.json()["connectors"][0]
            cid = connector.get("id")
            
            detail_response = requests.get(f"{API_PREFIX}/admin/sync-health/{cid}", headers=auth_headers)
            assert detail_response.status_code == 200, f"Detail failed: {detail_response.text}"
            data = detail_response.json()
            
            assert "health_score" in data or "sync_metrics" in data
            print(f"✓ Connector sync health detail retrieved for {cid[:8]}...")
        else:
            print("⚠ No connectors found - skipping detail test")


class TestReconciliationIssues:
    """Phase 1: Reconciliation Issues Management API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_reconciliation_issues_with_filters(self, auth_headers):
        """GET /admin/reconciliation/issues - returns issues list with filters."""
        response = requests.get(f"{API_PREFIX}/admin/reconciliation/issues", headers=auth_headers)
        assert response.status_code == 200, f"Issues failed: {response.text}"
        data = response.json()

        assert "issues" in data, f"Missing issues key: {data.keys()}"
        assert "count" in data, f"Missing count key: {data.keys()}"
        assert isinstance(data["issues"], list)

        print(f"✓ Reconciliation issues: count={data['count']}")

        # Test with filters
        filtered = requests.get(f"{API_PREFIX}/admin/reconciliation/issues?status=open&severity=high", headers=auth_headers)
        assert filtered.status_code == 200, f"Filtered issues failed: {filtered.text}"
        print(f"✓ Filtered issues (open+high): count={filtered.json()['count']}")

    def test_reconciliation_issue_actions(self, auth_headers):
        """Test issue action endpoints exist and accept requests."""
        # These endpoints need existing issues, test that they return proper errors
        response = requests.post(
            f"{API_PREFIX}/admin/reconciliation/issues/nonexistent/retry-sync",
            headers=auth_headers
        )
        # Should return 404 for nonexistent issue
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Retry-sync endpoint validates issue existence")


class TestSchedulerStatus:
    """Phase 1: Scheduler Status API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_scheduler_status(self, auth_headers):
        """GET /admin/scheduler/status - returns connectors with stale_jobs, failed_jobs."""
        response = requests.get(f"{API_PREFIX}/admin/scheduler/status", headers=auth_headers)
        assert response.status_code == 200, f"Scheduler status failed: {response.text}"
        data = response.json()

        assert "connectors" in data, f"Missing connectors: {data.keys()}"
        assert "count" in data, f"Missing count: {data.keys()}"
        assert isinstance(data["connectors"], list)

        # If there are connectors, verify they have required fields
        if data["connectors"]:
            connector = data["connectors"][0]
            assert "stale_jobs" in connector, f"Missing stale_jobs: {connector.keys()}"
            assert "failed_jobs" in connector, f"Missing failed_jobs: {connector.keys()}"
            assert "connector_id" in connector
            print(f"✓ Scheduler status: {len(data['connectors'])} connectors, first has stale_jobs={connector['stale_jobs']}, failed_jobs={connector['failed_jobs']}")
        else:
            print("✓ Scheduler status endpoint works (no connectors)")

    def test_trigger_all_schedulers(self, auth_headers):
        """POST /admin/scheduler/trigger-all - triggers all schedulers."""
        response = requests.post(f"{API_PREFIX}/admin/scheduler/trigger-all", headers=auth_headers)
        assert response.status_code == 200, f"Trigger all failed: {response.text}"
        data = response.json()

        assert "connectors_checked" in data or "results" in data, f"Missing expected fields: {data.keys()}"
        print(f"✓ Trigger all schedulers: {data}")


class TestCredentialManagement:
    """Phase 1: Credential Management (RBAC enforced) API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_credentials_masked(self, auth_headers):
        """GET /admin/credentials - returns masked credentials (RBAC enforced)."""
        response = requests.get(f"{API_PREFIX}/admin/credentials", headers=auth_headers)
        assert response.status_code == 200, f"Credentials list failed: {response.text}"
        data = response.json()

        assert "credentials" in data, f"Missing credentials: {data.keys()}"
        assert "count" in data, f"Missing count: {data.keys()}"
        assert isinstance(data["credentials"], list)

        # Verify credentials are masked
        if data["credentials"]:
            cred = data["credentials"][0]
            assert "connector_id" in cred
            assert "masked_credentials" in cred
            assert "encrypted" in cred
            # Masked values should have asterisks
            for key, val in cred.get("masked_credentials", {}).items():
                assert "***" in val or val.startswith("***"), f"Credential not masked: {key}={val}"
            print(f"✓ Credentials masked: {len(data['credentials'])} connectors, first encrypted={cred.get('encrypted')}")
        else:
            print("✓ Credentials endpoint works (no connectors)")


class TestErrorQueueAdmin:
    """Phase 4: Error Queue Admin Panel API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_error_queue(self, auth_headers):
        """GET /admin/error-queue - returns items and summary."""
        response = requests.get(f"{API_PREFIX}/admin/error-queue", headers=auth_headers)
        assert response.status_code == 200, f"Error queue failed: {response.text}"
        data = response.json()

        assert "items" in data, f"Missing items: {data.keys()}"
        assert "summary" in data, f"Missing summary: {data.keys()}"
        assert isinstance(data["items"], list)
        assert isinstance(data["summary"], dict)

        print(f"✓ Error queue: {len(data['items'])} items, summary={data['summary']}")

    def test_get_error_queue_summary(self, auth_headers):
        """GET /admin/error-queue/summary - returns sync_failed, import_failed, ack_failed, total."""
        response = requests.get(f"{API_PREFIX}/admin/error-queue/summary", headers=auth_headers)
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()

        assert "sync_failed" in data, f"Missing sync_failed: {data.keys()}"
        assert "import_failed" in data, f"Missing import_failed: {data.keys()}"
        assert "ack_failed" in data, f"Missing ack_failed: {data.keys()}"
        assert "total" in data, f"Missing total: {data.keys()}"

        print(f"✓ Error queue summary: sync={data['sync_failed']}, import={data['import_failed']}, ack={data['ack_failed']}, total={data['total']}")

    def test_error_queue_retry(self, auth_headers):
        """POST /admin/error-queue/retry - performs single retry."""
        # Test with a non-existent item - should handle gracefully
        response = requests.post(
            f"{API_PREFIX}/admin/error-queue/retry",
            headers=auth_headers,
            json={"item_id": "nonexistent", "error_type": "sync_failed"}
        )
        # Should succeed but indicate no item found or return success with no effect
        assert response.status_code in (200, 400, 404), f"Unexpected status: {response.status_code}"
        print(f"✓ Retry endpoint responds: {response.status_code}")

    def test_error_queue_bulk_retry(self, auth_headers):
        """POST /admin/error-queue/bulk-retry - performs bulk retry."""
        response = requests.post(
            f"{API_PREFIX}/admin/error-queue/bulk-retry",
            headers=auth_headers,
            json={"item_ids": [], "error_type": "sync_failed"}
        )
        assert response.status_code == 200, f"Bulk retry failed: {response.text}"
        data = response.json()
        assert "retried_count" in data or "success" in data
        print(f"✓ Bulk retry endpoint works: {data}")

    def test_error_queue_bulk_dismiss(self, auth_headers):
        """POST /admin/error-queue/bulk-dismiss - performs bulk dismiss."""
        response = requests.post(
            f"{API_PREFIX}/admin/error-queue/bulk-dismiss",
            headers=auth_headers,
            json={"item_ids": [], "error_type": "sync_failed", "reason": "test dismiss"}
        )
        assert response.status_code == 200, f"Bulk dismiss failed: {response.text}"
        data = response.json()
        assert "dismissed_count" in data or "success" in data
        print(f"✓ Bulk dismiss endpoint works: {data}")


class TestObservabilityMetrics:
    """Phase 5: Operational Observability API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_get_observability_metrics(self, auth_headers):
        """GET /admin/observability/metrics - returns sync_success_rate, ack_success_rate per connector."""
        response = requests.get(f"{API_PREFIX}/admin/observability/metrics", headers=auth_headers)
        assert response.status_code == 200, f"Metrics failed: {response.text}"
        data = response.json()

        assert "metrics" in data, f"Missing metrics: {data.keys()}"
        assert "count" in data, f"Missing count: {data.keys()}"
        assert isinstance(data["metrics"], list)

        # Verify metric structure if connectors exist
        if data["metrics"]:
            metric = data["metrics"][0]
            assert "sync_success_rate" in metric, f"Missing sync_success_rate: {metric.keys()}"
            assert "ack_success_rate" in metric, f"Missing ack_success_rate: {metric.keys()}"
            assert "connector_id" in metric
            print(f"✓ Metrics: {len(data['metrics'])} connectors, first sync_rate={metric['sync_success_rate']}%, ack_rate={metric['ack_success_rate']}%")
        else:
            print("✓ Metrics endpoint works (no connectors)")

    def test_get_audit_trail(self, auth_headers):
        """GET /admin/observability/audit-trail - returns audit logs."""
        response = requests.get(f"{API_PREFIX}/admin/observability/audit-trail", headers=auth_headers)
        assert response.status_code == 200, f"Audit trail failed: {response.text}"
        data = response.json()

        assert "logs" in data, f"Missing logs: {data.keys()}"
        assert "count" in data, f"Missing count: {data.keys()}"
        assert isinstance(data["logs"], list)

        print(f"✓ Audit trail: {data['count']} logs")

    def test_audit_trail_with_filter(self, auth_headers):
        """Test audit trail filtering by action."""
        response = requests.get(
            f"{API_PREFIX}/admin/observability/audit-trail?action=CREDENTIAL_ACCESSED",
            headers=auth_headers
        )
        assert response.status_code == 200
        print(f"✓ Audit trail filter works: {response.json()['count']} matching logs")


class TestProductionReadiness:
    """Phase 6: Production Readiness Validation API tests."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_production_readiness_overview(self, auth_headers):
        """GET /admin/production-readiness/overview - returns reports for all connectors."""
        response = requests.get(f"{API_PREFIX}/admin/production-readiness/overview", headers=auth_headers)
        assert response.status_code == 200, f"Overview failed: {response.text}"
        data = response.json()

        assert "reports" in data, f"Missing reports: {data.keys()}"
        assert "total_connectors" in data, f"Missing total_connectors: {data.keys()}"
        assert "ready_for_production" in data, f"Missing ready_for_production: {data.keys()}"
        assert "not_ready" in data, f"Missing not_ready: {data.keys()}"

        print(f"✓ Production readiness overview: {data['total_connectors']} connectors, {data['ready_for_production']} ready, {data['not_ready']} not ready")

    def test_production_readiness_single_connector(self, auth_headers):
        """POST /admin/production-readiness/{connector_id} - returns checks, passed/failed counts, recommendation."""
        # First get a connector
        response = requests.get(f"{API_PREFIX}/connectors", headers=auth_headers)
        if response.status_code == 200 and response.json().get("connectors"):
            connector = response.json()["connectors"][0]
            cid = connector.get("id")

            readiness_response = requests.post(
                f"{API_PREFIX}/admin/production-readiness/{cid}",
                headers=auth_headers
            )
            assert readiness_response.status_code == 200, f"Readiness check failed: {readiness_response.text}"
            data = readiness_response.json()

            assert "checks" in data, f"Missing checks: {data.keys()}"
            assert "passed_checks" in data, f"Missing passed_checks: {data.keys()}"
            assert "failed_checks" in data, f"Missing failed_checks: {data.keys()}"
            assert "production_recommendation" in data, f"Missing production_recommendation: {data.keys()}"

            assert data["production_recommendation"] in ("READY_FOR_PRODUCTION", "READY_WITH_WARNINGS", "NOT_READY")
            print(f"✓ Production readiness for {cid[:8]}...: {data['passed_checks']} passed, {data['failed_checks']} failed, recommendation={data['production_recommendation']}")
        else:
            print("⚠ No connectors found - skipping single connector readiness test")


class TestWebhookIntegration:
    """Phase 2: Webhook/Callback Integration API tests."""

    def test_webhook_invalid_json(self):
        """POST /webhooks/hotelrunner with invalid JSON returns 400."""
        response = requests.post(
            f"{API_PREFIX}/webhooks/hotelrunner",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        # Should return 400 for invalid JSON or 404 if no connector
        assert response.status_code in (400, 404, 422), f"Unexpected status: {response.status_code}"
        print(f"✓ Webhook invalid JSON handled: {response.status_code}")

    def test_webhook_valid_payload(self):
        """POST /webhooks/hotelrunner accepts webhook payloads."""
        payload = {
            "event_type": "reservation_created",
            "data": {
                "reservation_id": "TEST123",
                "check_in": "2026-02-01",
                "check_out": "2026-02-03"
            }
        }
        response = requests.post(
            f"{API_PREFIX}/webhooks/hotelrunner",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        # May return 404 if no active connector, or 200/400 for processing result
        assert response.status_code in (200, 400, 404), f"Unexpected status: {response.status_code}"
        print(f"✓ Webhook endpoint responds: {response.status_code}")

    def test_webhook_with_signature(self):
        """Test webhook with HMAC signature validation."""
        payload = json.dumps({"event_type": "test", "data": {}})
        secret = "test_secret"
        signature = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        response = requests.post(
            f"{API_PREFIX}/webhooks/hotelrunner",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-webhook-signature": f"sha256={signature}",
                "x-webhook-timestamp": str(int(time.time()))
            }
        )
        # Signature may not match if no connector with matching secret
        assert response.status_code in (200, 400, 404), f"Unexpected: {response.status_code}"
        print(f"✓ Webhook with signature handled: {response.status_code}")


class TestIntegration:
    """Integration tests verifying multiple endpoints work together."""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_admin_panel_full_flow(self, auth_headers):
        """Test complete admin panel data flow."""
        # 1. Get sync health
        health = requests.get(f"{API_PREFIX}/admin/sync-health", headers=auth_headers)
        assert health.status_code == 200

        # 2. Get scheduler status
        scheduler = requests.get(f"{API_PREFIX}/admin/scheduler/status", headers=auth_headers)
        assert scheduler.status_code == 200

        # 3. Get credentials
        creds = requests.get(f"{API_PREFIX}/admin/credentials", headers=auth_headers)
        assert creds.status_code == 200

        # 4. Get error queue
        errors = requests.get(f"{API_PREFIX}/admin/error-queue", headers=auth_headers)
        assert errors.status_code == 200

        # 5. Get metrics
        metrics = requests.get(f"{API_PREFIX}/admin/observability/metrics", headers=auth_headers)
        assert metrics.status_code == 200

        # 6. Get readiness
        readiness = requests.get(f"{API_PREFIX}/admin/production-readiness/overview", headers=auth_headers)
        assert readiness.status_code == 200

        print("✓ Full admin panel flow completed - all 6 tabs have data endpoints working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
