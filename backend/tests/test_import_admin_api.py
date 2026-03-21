"""
DATA-001: Import Admin API Tests
=================================
Tests the import admin router endpoints via HTTP:
  - GET  /api/imports/status
  - GET  /api/imports/review-queue
  - GET  /api/imports/events
  - POST /api/imports/{id}/retry
  - POST /api/imports/{id}/approve-and-import
  - POST /api/imports/{id}/dismiss
  - GET  /health/deep (import_bridge section)
"""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test data identifiers
TEST_PREFIX = "TEST_IMPORT_API_"


class TestImportStatusEndpoint:
    """Tests for GET /api/imports/status"""

    def test_status_returns_correct_structure(self):
        """Verify /api/imports/status returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/imports/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify all required count fields
        required_counts = [
            "pending_auto_import", "processing", "imported",
            "review_required", "retry", "failed", "duplicate"
        ]
        for field in required_counts:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"{field} should be int"
        
        # Verify optional fields
        assert "oldest_pending_seconds" in data
        assert "last_imported_at" in data
        assert "provider_failures" in data
        assert isinstance(data["provider_failures"], dict)
        
        # Verify worker metrics
        assert "worker" in data
        worker = data["worker"]
        assert "running" in worker
        assert "worker_id" in worker
        print(f"Import status: pending={data['pending_auto_import']}, imported={data['imported']}, worker.running={worker['running']}")

    def test_worker_is_running(self):
        """Verify import worker is running"""
        response = requests.get(f"{BASE_URL}/api/imports/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["worker"]["running"] is True, "Import worker should be running"
        print(f"Worker ID: {data['worker']['worker_id']}")


class TestReviewQueueEndpoint:
    """Tests for GET /api/imports/review-queue"""

    def test_review_queue_returns_paginated_list(self):
        """Verify /api/imports/review-queue returns paginated structure"""
        response = requests.get(f"{BASE_URL}/api/imports/review-queue?limit=10&offset=0")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        assert data["limit"] == 10
        assert data["offset"] == 0
        print(f"Review queue: {data['total']} items")

    def test_review_queue_with_provider_filter(self):
        """Verify provider filter works"""
        response = requests.get(f"{BASE_URL}/api/imports/review-queue?provider=exely&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        # All items should have provider=exely (if any)
        for item in data["items"]:
            assert item.get("provider") == "exely"
        print(f"Review queue (exely): {data['total']} items")

    def test_review_queue_with_tenant_filter(self):
        """Verify tenant_id filter works"""
        response = requests.get(f"{BASE_URL}/api/imports/review-queue?tenant_id=test-tenant&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        # All items should have tenant_id=test-tenant (if any)
        for item in data["items"]:
            assert item.get("tenant_id") == "test-tenant"
        print(f"Review queue (test-tenant): {data['total']} items")


class TestEventsEndpoint:
    """Tests for GET /api/imports/events"""

    def test_events_returns_paginated_list(self):
        """Verify /api/imports/events returns paginated structure"""
        response = requests.get(f"{BASE_URL}/api/imports/events?limit=10&offset=0")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        print(f"Import events: {data['total']} total")

    def test_events_with_status_filter(self):
        """Verify status filter works"""
        for status in ["pending_auto_import", "processing", "imported", "review_required", "retry", "failed", "duplicate"]:
            response = requests.get(f"{BASE_URL}/api/imports/events?status={status}&limit=5")
            assert response.status_code == 200, f"Failed for status={status}"
            
            data = response.json()
            # All items should have the filtered status (if any)
            for item in data["items"]:
                assert item.get("import_status") == status
            print(f"Events (status={status}): {data['total']} items")

    def test_events_with_provider_filter(self):
        """Verify provider filter works"""
        response = requests.get(f"{BASE_URL}/api/imports/events?provider=exely&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        for item in data["items"]:
            assert item.get("provider") == "exely"
        print(f"Events (provider=exely): {data['total']} items")

    def test_events_with_tenant_filter(self):
        """Verify tenant_id filter works"""
        response = requests.get(f"{BASE_URL}/api/imports/events?tenant_id=test-tenant&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        for item in data["items"]:
            assert item.get("tenant_id") == "test-tenant"
        print(f"Events (tenant_id=test-tenant): {data['total']} items")


class TestRetryEndpoint:
    """Tests for POST /api/imports/{id}/retry"""

    def test_retry_returns_404_for_nonexistent_id(self):
        """Verify retry returns 404 for non-existent import ID"""
        fake_id = f"{TEST_PREFIX}nonexistent-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/imports/{fake_id}/retry")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert fake_id in data["detail"]
        print(f"Retry 404 response: {data['detail']}")


class TestApproveAndImportEndpoint:
    """Tests for POST /api/imports/{id}/approve-and-import"""

    def test_approve_returns_404_for_nonexistent_id(self):
        """Verify approve-and-import returns 404 for non-existent import ID"""
        fake_id = f"{TEST_PREFIX}nonexistent-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/imports/{fake_id}/approve-and-import")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert fake_id in data["detail"]
        print(f"Approve 404 response: {data['detail']}")


class TestDismissEndpoint:
    """Tests for POST /api/imports/{id}/dismiss"""

    def test_dismiss_returns_404_for_nonexistent_id(self):
        """Verify dismiss returns 404 for non-existent import ID"""
        fake_id = f"{TEST_PREFIX}nonexistent-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/imports/{fake_id}/dismiss")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert fake_id in data["detail"]
        print(f"Dismiss 404 response: {data['detail']}")


class TestHealthDeepImportBridge:
    """Tests for GET /health/deep import_bridge section"""

    def test_health_deep_includes_import_bridge(self):
        """Verify /health/deep includes import_bridge section"""
        response = requests.get(f"{BASE_URL}/health/deep")
        # May return 503 if Redis is down, but should still have import_bridge
        assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        assert "import_bridge" in data, "Missing import_bridge section in /health/deep"
        
        ib = data["import_bridge"]
        
        # Verify required fields
        assert "status" in ib
        assert ib["status"] in ["ok", "degraded", "critical", "unknown"]
        
        # Verify count fields
        count_fields = ["pending_auto_import", "processing", "retry", "review_required", "failed"]
        for field in count_fields:
            assert field in ib, f"Missing field: {field}"
        
        # Verify optional fields
        assert "oldest_pending_seconds" in ib
        assert "last_imported_at" in ib
        assert "provider_failures" in ib
        assert isinstance(ib["provider_failures"], dict)
        
        print(f"Import bridge health: status={ib['status']}, pending={ib['pending_auto_import']}, failed={ib['failed']}")

    def test_health_deep_import_bridge_status_logic(self):
        """Verify import_bridge status reflects actual state"""
        response = requests.get(f"{BASE_URL}/health/deep")
        data = response.json()
        
        ib = data["import_bridge"]
        
        # Status should be 'ok' if failed < 5 and review_required < 20
        # Status should be 'degraded' if failed >= 5 or review_required >= 20
        # Status should be 'critical' if failed >= 50
        
        if ib["failed"] >= 50:
            assert ib["status"] == "critical"
        elif ib["failed"] >= 5 or ib["review_required"] >= 20:
            assert ib["status"] == "degraded"
        else:
            assert ib["status"] == "ok"
        
        print(f"Status logic verified: failed={ib['failed']}, review={ib['review_required']}, status={ib['status']}")


class TestImportAdminIntegration:
    """Integration tests for import admin workflow"""

    def test_status_counts_match_events_totals(self):
        """Verify status counts match events endpoint totals"""
        # Get status counts
        status_resp = requests.get(f"{BASE_URL}/api/imports/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        
        # Verify each status count matches events endpoint
        for status_name in ["pending_auto_import", "processing", "imported", "review_required", "retry", "failed", "duplicate"]:
            events_resp = requests.get(f"{BASE_URL}/api/imports/events?status={status_name}&limit=1")
            assert events_resp.status_code == 200
            events_data = events_resp.json()
            
            # The total from events should match the count from status
            assert events_data["total"] == status_data[status_name], \
                f"Mismatch for {status_name}: status={status_data[status_name]}, events={events_data['total']}"
        
        print("Status counts match events totals - PASS")

    def test_review_queue_matches_review_required_count(self):
        """Verify review-queue total matches review_required count"""
        status_resp = requests.get(f"{BASE_URL}/api/imports/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        
        queue_resp = requests.get(f"{BASE_URL}/api/imports/review-queue?limit=1")
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()
        
        assert queue_data["total"] == status_data["review_required"], \
            f"Mismatch: status.review_required={status_data['review_required']}, queue.total={queue_data['total']}"
        
        print(f"Review queue total matches review_required count: {queue_data['total']}")
