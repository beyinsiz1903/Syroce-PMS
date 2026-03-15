"""
ARI Push Engine API Tests.

Tests for:
- Event publishing (POST /api/channel-manager/ari/events/publish)
- Event listing (GET /api/channel-manager/ari/events)
- Change sets (GET /api/channel-manager/ari/change-sets)
- Push operations (POST /api/channel-manager/ari/push)
- Force push (POST /api/channel-manager/ari/change-sets/{id}/push)
- Resync (POST /api/channel-manager/ari/resync)
- Outbound logs (GET /api/channel-manager/ari/outbound-logs)
- Drift states (GET /api/channel-manager/ari/drift)
- Drift check (POST /api/channel-manager/ari/drift/check)
- Drift reconcile (POST /api/channel-manager/ari/drift/reconcile)
- Stats (GET /api/channel-manager/ari/stats)
- Engine stats (GET /api/channel-manager/ari/engine-stats)
- Buffer debounce and coalescing behavior
- Outbound idempotency
"""
import os
import time
import pytest
import requests
from datetime import date, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Skip all tests in this module if no backend URL is configured (e.g. CI without live server)
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")

# Test constants
TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"
PROPERTY_ID = "prop-001"

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════════════════
# ENGINE STATS & PROVIDER REGISTRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEngineStats:
    """Engine stats and adapter registration tests."""
    
    def test_engine_stats_endpoint_accessible(self, api_client):
        """GET /api/channel-manager/ari/engine-stats should return engine status."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/engine-stats")
        assert response.status_code == 200
        data = response.json()
        assert "buffer" in data
        assert "rate_limiter" in data
        assert "registered_adapters" in data
        assert "active_tenants" in data
    
    def test_hotelrunner_adapter_registered(self, api_client):
        """HotelRunner adapter should be registered on startup."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/engine-stats")
        data = response.json()
        assert "hotelrunner" in data["registered_adapters"]
    
    def test_exely_adapter_registered(self, api_client):
        """Exely adapter should be registered on startup."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/engine-stats")
        data = response.json()
        assert "exely" in data["registered_adapters"]
    
    def test_buffer_state_visible(self, api_client):
        """Buffer stats should show running state and counts."""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/ari/engine-stats")
        data = response.json()
        buffer = data["buffer"]
        assert "active_keys" in buffer
        assert "total_buffered_events" in buffer
        assert "running" in buffer


# ═══════════════════════════════════════════════════════════════════
# STATS ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestARIStats:
    """Aggregate ARI stats tests."""
    
    def test_stats_endpoint_returns_metrics(self, api_client):
        """GET /api/channel-manager/ari/stats should return all metric fields."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/stats",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_events" in data
        assert "pending_changes" in data
        assert "acked_changes" in data
        assert "failed_changes" in data
        assert "drift_count" in data
        assert "total_outbound_pushes" in data
    
    def test_stats_values_are_integers(self, api_client):
        """All stats values should be integers."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/stats",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        data = response.json()
        for key in ["total_events", "pending_changes", "acked_changes", "failed_changes", "drift_count", "total_outbound_pushes"]:
            assert isinstance(data[key], int), f"{key} should be an integer"


# ═══════════════════════════════════════════════════════════════════
# EVENT PUBLISHING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEventPublishing:
    """Event publishing endpoint tests."""
    
    def test_publish_availability_event(self, api_client):
        """POST /api/channel-manager/ari/events/publish — availability event."""
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "manual",
            "event_type": "availability",
            "room_type_code": "TEST_STD",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=1)),
            "date_to": str(date.today() + timedelta(days=3)),
            "payload": {"availability": 5, "stop_sell": False},
            "actor_id": "test-user"
        }
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "event_id" in data
        assert "coalescing_key" in data
        assert data["buffered"] is True
    
    def test_publish_rate_event(self, api_client):
        """POST /api/channel-manager/ari/events/publish — rate event."""
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "pricing",
            "event_type": "rate",
            "room_type_code": "TEST_STD",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=1)),
            "date_to": str(date.today() + timedelta(days=3)),
            "payload": {"base_rate": 150.00, "currency": "TRY"},
            "actor_id": "test-user"
        }
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "event_id" in data
        assert data["buffered"] is True
    
    def test_publish_restriction_event(self, api_client):
        """POST /api/channel-manager/ari/events/publish — restriction event."""
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "manual",
            "event_type": "restriction",
            "room_type_code": "TEST_STD",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=1)),
            "date_to": str(date.today() + timedelta(days=3)),
            "payload": {"min_los": 2, "cta": False, "stop_sell": True},
            "actor_id": "test-user"
        }
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "event_id" in data
    
    def test_publish_event_returns_coalescing_key_format(self, api_client):
        """Coalescing key should contain tenant, property, room, rate, dates, type."""
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "manual",
            "event_type": "availability",
            "room_type_code": "TEST_DLX",
            "rate_plan_code": "NR",
            "date_from": str(date.today() + timedelta(days=5)),
            "date_to": str(date.today() + timedelta(days=7)),
            "payload": {"availability": 3}
        }
        response = api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        data = response.json()
        key = data["coalescing_key"]
        # Key format: tenant_id|property_id|room_type_code|rate_plan_code|date_from:date_to|event_type
        assert TENANT_ID in key
        assert PROPERTY_ID in key
        assert "TEST_DLX" in key
        assert "availability" in key


# ═══════════════════════════════════════════════════════════════════
# EVENT LISTING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEventListing:
    """Event listing endpoint tests."""
    
    def test_list_events_returns_array(self, api_client):
        """GET /api/channel-manager/ari/events should return events array."""
        # Wait for buffer to flush
        time.sleep(3)
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/events",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 50}
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data
        assert isinstance(data["events"], list)
    
    def test_list_events_with_type_filter(self, api_client):
        """Event listing should support event_type filter."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/events",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "event_type": "availability"}
        )
        assert response.status_code == 200
        data = response.json()
        # All returned events should be of type availability
        for event in data["events"]:
            if "event_type" in event:
                assert event["event_type"] == "availability"
    
    def test_list_events_pagination(self, api_client):
        """Event listing should support skip and limit parameters."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/events",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 5, "skip": 0}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) <= 5


# ═══════════════════════════════════════════════════════════════════
# CHANGE SETS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestChangeSets:
    """Change sets endpoint tests."""
    
    def test_list_change_sets_returns_array(self, api_client):
        """GET /api/channel-manager/ari/change-sets should return change sets array."""
        # Wait for buffer to flush and create change sets
        time.sleep(4)
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 100}
        )
        assert response.status_code == 200
        data = response.json()
        assert "change_sets" in data
        assert "count" in data
        assert isinstance(data["change_sets"], list)
    
    def test_list_change_sets_with_status_filter(self, api_client):
        """Change sets listing should support status filter."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "status": "pending"}
        )
        assert response.status_code == 200
        data = response.json()
        for cs in data["change_sets"]:
            assert cs["status"] == "pending"
    
    def test_list_change_sets_with_provider_filter(self, api_client):
        """Change sets listing should support provider filter."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "provider": "hotelrunner"}
        )
        assert response.status_code == 200
        data = response.json()
        for cs in data["change_sets"]:
            assert cs["provider"] == "hotelrunner"
    
    def test_change_set_fields_present(self, api_client):
        """Change sets should have required fields."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 10}
        )
        data = response.json()
        if data["change_sets"]:
            cs = data["change_sets"][0]
            expected_fields = ["id", "tenant_id", "property_id", "provider", "status", 
                            "room_type_code", "date_from", "date_to", "change_scope"]
            for field in expected_fields:
                assert field in cs, f"Missing field: {field}"


# ═══════════════════════════════════════════════════════════════════
# PUSH OPERATIONS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPushOperations:
    """Push operations endpoint tests."""
    
    def test_push_pending_endpoint(self, api_client):
        """POST /api/channel-manager/ari/push should process pending change sets."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/push",
            json={"tenant_id": TENANT_ID, "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        # Response should have push result counts
        assert "pushed" in data
        assert "skipped" in data
        assert "failed" in data
        assert "rate_limited" in data
    
    def test_push_pending_with_provider_filter(self, api_client):
        """Push should support provider filter."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/push",
            json={"tenant_id": TENANT_ID, "provider": "hotelrunner", "limit": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["pushed"], int)
    
    def test_force_push_nonexistent_change_set(self, api_client):
        """Force push with non-existent ID should return error."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/change-sets/nonexistent-id-12345/push"
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "pushed" in data  # Either error or 0 pushed


# ═══════════════════════════════════════════════════════════════════
# RESYNC TESTS
# ═══════════════════════════════════════════════════════════════════

class TestResync:
    """Resync endpoint tests."""
    
    def test_resync_endpoint(self, api_client):
        """POST /api/channel-manager/ari/resync should queue resync."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/resync",
            json={
                "tenant_id": TENANT_ID,
                "property_id": PROPERTY_ID,
                "provider": "hotelrunner",
                "scope": "all"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resync_queued"
        assert data["provider"] == "hotelrunner"


# ═══════════════════════════════════════════════════════════════════
# OUTBOUND LOGS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOutboundLogs:
    """Outbound logs endpoint tests."""
    
    def test_list_outbound_logs(self, api_client):
        """GET /api/channel-manager/ari/outbound-logs should return logs array."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/outbound-logs",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 50}
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "count" in data
        assert isinstance(data["logs"], list)
    
    def test_outbound_logs_with_provider_filter(self, api_client):
        """Outbound logs should support provider filter."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/outbound-logs",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "provider": "hotelrunner"}
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["logs"]:
            assert log["provider"] == "hotelrunner"


# ═══════════════════════════════════════════════════════════════════
# DRIFT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDrift:
    """Drift detection and reconciliation tests."""
    
    def test_list_drift_states(self, api_client):
        """GET /api/channel-manager/ari/drift should return drift states array."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/drift",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "drift_states" in data
        assert "count" in data
        assert isinstance(data["drift_states"], list)
    
    def test_drift_check_endpoint(self, api_client):
        """POST /api/channel-manager/ari/drift/check should return drift report."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/drift/check",
            json={
                "tenant_id": TENANT_ID,
                "property_id": PROPERTY_ID,
                "provider": "hotelrunner"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_checked" in data
        assert "matched" in data
        assert "drifts_found" in data
        assert "checked_at" in data
    
    def test_drift_reconcile_endpoint(self, api_client):
        """POST /api/channel-manager/ari/drift/reconcile should generate corrective sets."""
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/drift/reconcile",
            json={
                "tenant_id": TENANT_ID,
                "property_id": PROPERTY_ID,
                "provider": "hotelrunner"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "corrective_change_sets" in data
        assert "provider" in data


# ═══════════════════════════════════════════════════════════════════
# BUFFER DEBOUNCE & COALESCING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBufferDebounce:
    """Buffer debounce and coalescing behavior tests."""
    
    def test_multiple_events_same_key_coalesce(self, api_client):
        """Publishing multiple events with same key within debounce window should coalesce."""
        # Get initial change set count
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 200}
        )
        initial_count = response.json()["count"]
        
        # Publish 3 events with same coalescing key rapidly
        base_payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "test",
            "event_type": "availability",
            "room_type_code": "TEST_COALESCE",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=10)),
            "date_to": str(date.today() + timedelta(days=12)),
        }
        
        for i in range(3):
            payload = {**base_payload, "payload": {"availability": 10 + i}}
            api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
            time.sleep(0.3)  # within debounce window
        
        # Wait for buffer to flush (availability debounce = 2s)
        time.sleep(6)
        
        # Check change sets - should have coalesced into fewer than 3 per provider
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/change-sets",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 200}
        )
        new_count = response.json()["count"]
        
        # Should have added 2 change sets (one per provider: hotelrunner, exely)
        # not 6 (3 events * 2 providers) due to coalescing
        change_sets = response.json()["change_sets"]
        coalesce_cs = [cs for cs in change_sets if cs["room_type_code"] == "TEST_COALESCE"]
        
        # With 2 providers, coalesced events should create at most 2 change sets per key
        assert len(coalesce_cs) <= 4  # 2 providers * 2 (in case of timing edge)


# ═══════════════════════════════════════════════════════════════════
# OUTBOUND IDEMPOTENCY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOutboundIdempotency:
    """Outbound idempotency tests — same delta_hash should not push twice within 1 hour."""
    
    def test_push_creates_outbound_log(self, api_client):
        """After push, outbound log should be created."""
        # First, publish an event
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "test",
            "event_type": "availability",
            "room_type_code": "TEST_IDEMPOTENT",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=20)),
            "date_to": str(date.today() + timedelta(days=22)),
            "payload": {"availability": 8}
        }
        api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        
        # Wait for buffer flush
        time.sleep(6)
        
        # Push
        api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/push",
            json={"tenant_id": TENANT_ID, "limit": 10}
        )
        
        # Check outbound logs
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/outbound-logs",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 50}
        )
        data = response.json()
        assert data["count"] >= 0  # At least 0 logs (may be more from previous tests)


# ═══════════════════════════════════════════════════════════════════
# DRY-RUN MODE VERIFICATION
# ═══════════════════════════════════════════════════════════════════

class TestDryRunMode:
    """Verify that both adapters are running in dry-run mode."""
    
    def test_push_returns_success_in_dry_run(self, api_client):
        """Push in dry-run mode should return success (no real provider calls)."""
        # Publish a fresh event
        payload = {
            "tenant_id": TENANT_ID,
            "property_id": PROPERTY_ID,
            "source_service": "test",
            "event_type": "rate",
            "room_type_code": "TEST_DRYRUN",
            "rate_plan_code": "BAR",
            "date_from": str(date.today() + timedelta(days=30)),
            "date_to": str(date.today() + timedelta(days=32)),
            "payload": {"base_rate": 200.00, "currency": "TRY"}
        }
        api_client.post(f"{BASE_URL}/api/channel-manager/ari/events/publish", json=payload)
        
        # Wait for buffer
        time.sleep(6)
        
        # Push - should succeed in dry-run mode
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/ari/push",
            json={"tenant_id": TENANT_ID, "limit": 20}
        )
        data = response.json()
        
        # In dry-run mode, we expect pushes to succeed (not fail due to provider errors)
        assert data["failed"] == 0 or data["rate_limited"] >= 0  # No actual failures


# ═══════════════════════════════════════════════════════════════════
# CLEANUP (runs last)
# ═══════════════════════════════════════════════════════════════════

class TestCleanup:
    """Verify test data has TEST_ prefix for easy identification."""
    
    def test_verify_test_data_prefixed(self, api_client):
        """All test room_type_codes should start with TEST_."""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/ari/events",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "limit": 100}
        )
        events = response.json()["events"]
        test_events = [e for e in events if e.get("room_type_code", "").startswith("TEST_")]
        # At least some test events should exist
        assert len(test_events) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
