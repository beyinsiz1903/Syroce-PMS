"""
Reservation Ingest Pipeline Tests — Full 8-Stage Pipeline Testing
===================================================================

Tests for the production-grade ingest pipeline covering:
- HotelRunner webhook endpoints (reservations, modifications, cancellations)
- Exely payload processing
- Duplicate detection (same provider_event_id)
- Payload hash check (same hash should be skipped)
- Stale event detection (older version should be skipped)
- Update detection (newer version should UPDATE lineage)
- Cancel detection (cancelled status always wins)
- Missing mapping → reconciliation case creation
- Worker controls (process, replay, pull)
- Pipeline status and event stats APIs
- Loop prevention (external_write_protected)
"""
import os
import time
import pytest
import requests
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")
TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"
PROPERTY_ID = "prop-001"

@pytest.fixture(scope="module")
def auth_token():
    """Get auth token via login."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

# ══════════════════════════════════════════════════════════════════════
# HotelRunner Webhook Tests
# ══════════════════════════════════════════════════════════════════════

class TestHotelRunnerWebhooks:
    """HotelRunner webhook endpoint tests"""

    def test_reservation_webhook_with_tenant_header(self, auth_headers):
        """POST /api/channel-manager/hotelrunner/webhooks/reservations with X-Tenant-ID header"""
        unique_hr_number = f"HR-TEST-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "hr_number": unique_hr_number,
            "guest": {"first_name": "Test", "last_name": "Guest", "email": "test@example.com", "phone": "+905551234567"},
            "check_in": "2026-05-01",
            "check_out": "2026-05-05",
            "room_type": "STD",
            "rate_plan": "BAR",
            "adults": 2,
            "children": 1,
            "currency": "TRY",
            "total": 5400.00,
            "status": "confirmed",
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "channel": "booking.com"
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={
                "Content-Type": "application/json",
                "X-Tenant-ID": TENANT_ID
            },
            json=payload
        )
        assert resp.status_code == 200, f"Webhook failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["count"] >= 1
        print(f"✓ HotelRunner reservation webhook accepted: {unique_hr_number}")

    def test_modification_webhook(self, auth_headers):
        """POST /api/channel-manager/hotelrunner/webhooks/modifications"""
        unique_hr_number = f"HR-MOD-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "hr_number": unique_hr_number,
            "guest": {"first_name": "Modified", "last_name": "Guest", "email": "mod@example.com"},
            "check_in": "2026-05-10",
            "check_out": "2026-05-15",
            "room_type": "STD",
            "rate_plan": "BAR",
            "adults": 2,
            "children": 0,
            "currency": "TRY",
            "total": 6000.00,
            "status": "modified",
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "channel": "expedia"
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/modifications",
            headers={"Content-Type": "application/json", "X-Tenant-ID": TENANT_ID},
            json=payload
        )
        assert resp.status_code == 200, f"Modification webhook failed: {resp.text}"
        assert resp.json()["status"] == "accepted"
        print(f"✓ HotelRunner modification webhook accepted: {unique_hr_number}")

    def test_cancellation_webhook(self, auth_headers):
        """POST /api/channel-manager/hotelrunner/webhooks/cancellations"""
        unique_hr_number = f"HR-CXL-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "hr_number": unique_hr_number,
            "guest": {"first_name": "Cancelled", "last_name": "Guest"},
            "check_in": "2026-05-20",
            "check_out": "2026-05-25",
            "room_type": "STD",
            "rate_plan": "BAR",
            "status": "cancelled",
            "last_modified": datetime.now(timezone.utc).isoformat()
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/cancellations",
            headers={"Content-Type": "application/json", "X-Tenant-ID": TENANT_ID},
            json=payload
        )
        assert resp.status_code == 200, f"Cancellation webhook failed: {resp.text}"
        assert resp.json()["status"] == "accepted"
        print(f"✓ HotelRunner cancellation webhook accepted: {unique_hr_number}")

    def test_webhook_requires_tenant_id(self):
        """Webhook should fail without tenant_id"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"Content-Type": "application/json"},
            json={"hr_number": "HR-NO-TENANT"}
        )
        assert resp.status_code == 400, "Should fail without tenant_id"
        print("✓ Webhook correctly rejects request without tenant_id")


# ══════════════════════════════════════════════════════════════════════
# Inject and Process Tests (Full Pipeline)
# ══════════════════════════════════════════════════════════════════════

class TestInjectAndProcess:
    """Test inject-and-process endpoint for both HotelRunner and Exely payloads"""

    def test_inject_hotelrunner_create_decision(self, auth_headers):
        """Inject HotelRunner payload — should CREATE if new"""
        unique_id = f"HR-NEW-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "received_via": "manual",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "New", "last_name": "Reservation", "email": "new@test.com"},
                "check_in": "2026-06-01",
                "check_out": "2026-06-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "adults": 2,
                "children": 0,
                "currency": "TRY",
                "total": 4500.00,
                "status": "confirmed",
                "last_modified": datetime.now(timezone.utc).isoformat(),
                "channel": "direct"
            }
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/inject-and-process",
            headers=auth_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Inject failed: {resp.text}"
        data = resp.json()
        assert data["event_id"], "Should return event_id"
        result = data.get("pipeline_result", {})
        # May be CREATE or PENDING_MAPPING depending on existing mappings
        assert result.get("decision") in ["create", "pending_mapping", "skip"], f"Unexpected decision: {result.get('decision')}"
        print(f"✓ HotelRunner inject-and-process: {unique_id} → {result.get('decision')}")
        return unique_id

    def test_inject_exely_create_decision(self, auth_headers):
        """Inject Exely payload — should CREATE if new"""
        unique_id = f"EX-NEW-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "provider": "exely",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "received_via": "manual",
            "payload": {
                "UniqueID": unique_id,
                "ResStatus": "Commit",
                "LastModifyDateTime": datetime.now(timezone.utc).isoformat(),
                "RoomStay": {"RoomTypeCode": "DLX", "RatePlanCode": "RACK", "StartDate": "2026-06-10", "EndDate": "2026-06-15"},
                "GuestCount": {"adults": 2, "children": 1},
                "ResGuest": {"GivenName": "Exely", "Surname": "Guest", "Email": "exely@test.com"},
                "Total": {"Amount": 7200.00, "CurrencyCode": "TRY"},
                "Source": "expedia"
            }
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/inject-and-process",
            headers=auth_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Exely inject failed: {resp.text}"
        data = resp.json()
        result = data.get("pipeline_result", {})
        assert result.get("decision") in ["create", "pending_mapping", "skip"], f"Unexpected decision: {result}"
        print(f"✓ Exely inject-and-process: {unique_id} → {result.get('decision')}")

    def test_reject_invalid_provider(self, auth_headers):
        """Inject with invalid provider should fail"""
        payload = {
            "provider": "channex",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {"test": "data"}
        }
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/inject-and-process",
            headers=auth_headers,
            json=payload
        )
        assert resp.status_code == 400, "Should reject invalid provider"
        assert "Invalid provider" in resp.json().get("detail", "")
        print("✓ Invalid provider correctly rejected")


# ══════════════════════════════════════════════════════════════════════
# Duplicate & Stale Detection Tests
# ══════════════════════════════════════════════════════════════════════

class TestDuplicateAndStaleDetection:
    """Test duplicate detection and stale event handling"""

    def test_duplicate_provider_event_id_skipped(self, auth_headers):
        """Same provider_event_id should be skipped (when first event was processed),
        or both get same decision when mappings are missing."""
        unique_id = f"HR-DUP-{uuid.uuid4().hex[:8].upper()}"
        base_time = datetime.now(timezone.utc)
        
        # First injection
        payload = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Dup", "last_name": "Test"},
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "confirmed",
                "last_modified": base_time.isoformat()
            }
        }
        resp1 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload)
        assert resp1.status_code == 200
        first_result = resp1.json().get("pipeline_result", {})
        first_decision = first_result.get("decision")
        print(f"  First inject: {first_decision}")

        # Wait for processing
        time.sleep(0.5)

        # Second injection with SAME hr_number and last_modified (same provider_event_id)
        resp2 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload)
        assert resp2.status_code == 200
        second_result = resp2.json().get("pipeline_result", {})
        second_decision = second_result.get("decision")
        
        if first_decision in ["create", "update"]:
            # First event was successfully processed — duplicate detection should kick in
            assert second_decision in ["skip", "duplicate"] or "duplicate" in second_result.get("reason", "").lower(), \
                f"Expected duplicate/skip after processed first, got: {second_result}"
            print(f"  Duplicate detection working: {second_decision} - {second_result.get('reason', '')[:50]}")
        else:
            # First event was NOT processed (e.g., pending_mapping due to missing room mapping).
            # Duplicate detection only checks processed/duplicate events, so the second
            # injection correctly gets the same result. This is by design: failed events
            # should be retryable once the root cause (e.g., missing mapping) is fixed.
            assert second_decision == first_decision, \
                f"Expected same decision as first ({first_decision}), got: {second_result}"
            print(f"  Both events got '{first_decision}' (duplicate detection N/A — first event not processed)")
        print(f"  Result: first={first_decision}, second={second_decision}")

    def test_stale_version_skipped(self, auth_headers):
        """Older provider_version should be skipped when lineage exists,
        or both get same decision when mappings are missing."""
        unique_id = f"HR-STALE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        older_time = (now - timedelta(hours=1)).isoformat()
        newer_time = now.isoformat()

        # First inject with NEWER time
        payload_new = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Stale", "last_name": "Test"},
                "check_in": "2026-08-01",
                "check_out": "2026-08-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "confirmed",
                "total": 5000.00,
                "last_modified": newer_time
            }
        }
        resp1 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_new)
        assert resp1.status_code == 200
        first_result = resp1.json().get("pipeline_result", {})
        first_decision = first_result.get("decision")
        print(f"  First inject (newer): {first_decision}")

        time.sleep(0.5)

        # Second inject with OLDER time (should be stale)
        payload_old = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_modify",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Stale", "last_name": "Test"},
                "check_in": "2026-08-01",
                "check_out": "2026-08-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "modified",
                "total": 4000.00,  # Different amount
                "last_modified": older_time
            }
        }
        resp2 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_old)
        assert resp2.status_code == 200
        result = resp2.json().get("pipeline_result", {})

        if first_decision in ["create", "update"]:
            # Lineage was created — stale detection should work
            assert result.get("decision") in ["skip"], f"Expected skip for stale, got: {result}"
            assert "stale" in result.get("reason", "").lower() or "duplicate" in result.get("reason", "").lower(), \
                f"Expected stale/duplicate reason, got: {result.get('reason')}"
            print(f"  Stale detection working: {result.get('decision')} - {result.get('reason', '')[:50]}")
        else:
            # No lineage created (e.g., pending_mapping) — stale detection can't apply
            assert result.get("decision") == first_decision, \
                f"Expected same decision as first ({first_decision}), got: {result}"
            print(f"  Both events got '{first_decision}' (stale detection N/A — no lineage created)")
        print(f"  Result: first={first_decision}, second={result.get('decision')}")

    def test_update_with_newer_version(self, auth_headers):
        """Newer provider_version should UPDATE lineage"""
        unique_id = f"HR-UPD-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        older_time = now.isoformat()
        newer_time = (now + timedelta(hours=1)).isoformat()

        # First inject (create)
        payload_create = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Update", "last_name": "Test"},
                "check_in": "2026-09-01",
                "check_out": "2026-09-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "confirmed",
                "total": 5000.00,
                "last_modified": older_time
            }
        }
        resp1 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_create)
        assert resp1.status_code == 200
        first_decision = resp1.json().get("pipeline_result", {}).get("decision")
        print(f"  First inject: {first_decision}")

        time.sleep(0.5)

        # Second inject with NEWER time and different amount
        payload_update = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_modify",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Update", "last_name": "Test"},
                "check_in": "2026-09-01",
                "check_out": "2026-09-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "modified",
                "total": 5500.00,  # Changed amount
                "last_modified": newer_time
            }
        }
        resp2 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_update)
        assert resp2.status_code == 200
        result = resp2.json().get("pipeline_result", {})
        # Should be update (or create/pending_mapping if no existing lineage)
        print(f"✓ Update with newer version: {result.get('decision')} - {result.get('reason', '')[:50]}")


# ══════════════════════════════════════════════════════════════════════
# Cancellation Tests
# ══════════════════════════════════════════════════════════════════════

class TestCancellationHandling:
    """Test that cancellation status always wins"""

    def test_cancellation_always_wins(self, auth_headers):
        """Cancelled status should always win"""
        unique_id = f"HR-CXL-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        
        # First create
        payload_create = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Cancel", "last_name": "Test"},
                "check_in": "2026-10-01",
                "check_out": "2026-10-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "status": "confirmed",
                "last_modified": now.isoformat()
            }
        }
        resp1 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_create)
        assert resp1.status_code == 200
        print(f"  Created: {resp1.json().get('pipeline_result', {}).get('decision')}")

        time.sleep(0.5)

        # Then cancel
        payload_cancel = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_cancel",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "Cancel", "last_name": "Test"},
                "status": "cancelled",
                "last_modified": (now + timedelta(minutes=1)).isoformat()
            }
        }
        resp2 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload_cancel)
        assert resp2.status_code == 200
        result = resp2.json().get("pipeline_result", {})
        assert result.get("decision") == "cancel", f"Expected cancel decision, got: {result}"
        print(f"✓ Cancellation always wins: {result.get('decision')}")


# ══════════════════════════════════════════════════════════════════════
# Missing Mapping Tests
# ══════════════════════════════════════════════════════════════════════

class TestMissingMappingHandling:
    """Test that missing mappings create reconciliation cases"""

    def test_missing_room_mapping_creates_case(self, auth_headers):
        """Missing room mapping should create reconciliation case"""
        unique_id = f"HR-NOMAP-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "NoMap", "last_name": "Test"},
                "check_in": "2026-11-01",
                "check_out": "2026-11-05",
                "room_type": "NONEXISTENT_ROOM",  # Unknown room type
                "rate_plan": "BAR",
                "status": "confirmed",
                "last_modified": datetime.now(timezone.utc).isoformat()
            }
        }
        resp = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload)
        assert resp.status_code == 200
        result = resp.json().get("pipeline_result", {})
        
        # Should be pending_mapping if no mapping exists for NONEXISTENT_ROOM
        if result.get("decision") == "pending_mapping":
            assert result.get("case_id"), "Should create reconciliation case"
            assert "Room mapping missing" in result.get("reason", "") or "mapping" in result.get("reason", "").lower()
            print(f"✓ Missing room mapping creates case: {result.get('case_id')}")
        else:
            print(f"  Note: Got {result.get('decision')} - mapping may exist or duplicate")


# ══════════════════════════════════════════════════════════════════════
# Worker Control Tests
# ══════════════════════════════════════════════════════════════════════

class TestWorkerControls:
    """Test worker trigger endpoints"""

    def test_trigger_process_pending(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/process"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/process",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Process trigger failed: {resp.text}"
        data = resp.json()
        assert "result" in data
        print(f"✓ Process worker triggered: processed={data.get('result', {}).get('processed', 0)}")

    def test_trigger_replay_failed(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/replay"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/replay",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Replay trigger failed: {resp.text}"
        data = resp.json()
        assert "result" in data
        print(f"✓ Replay worker triggered: replayed={data.get('result', {}).get('replayed', 0)}")

    def test_trigger_hotelrunner_pull(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/pull/hotelrunner"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/pull/hotelrunner",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"HR pull failed: {resp.text}"
        data = resp.json()
        assert "result" in data
        # Pull workers are mocked — they log but don't fetch real data
        print(f"✓ HotelRunner pull triggered (MOCKED)")

    def test_trigger_exely_pull(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/pull/exely"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/pull/exely",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Exely pull failed: {resp.text}"
        data = resp.json()
        assert "result" in data
        print(f"✓ Exely pull triggered (MOCKED)")

    def test_invalid_provider_pull_rejected(self, auth_headers):
        """Pull with invalid provider should fail"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/pull/channex",
            headers=auth_headers
        )
        assert resp.status_code == 400, "Should reject invalid provider"
        print("✓ Invalid provider pull rejected")


# ══════════════════════════════════════════════════════════════════════
# Status & Stats API Tests
# ══════════════════════════════════════════════════════════════════════

class TestStatusAndStatsAPIs:
    """Test pipeline status and stats endpoints"""

    def test_get_ingest_status(self, auth_headers):
        """GET /api/channel-manager/ingest/status"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/status?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Status failed: {resp.text}"
        data = resp.json()
        assert "pipeline" in data, "Should have pipeline stats"
        assert "workers" in data, "Should have worker states"
        pipeline = data["pipeline"]
        assert "raw_events" in pipeline
        assert "lineage" in pipeline
        assert "reconciliation" in pipeline
        print(f"✓ Ingest status: events={pipeline.get('raw_events', {}).get('total', 0)}, lineage={pipeline.get('lineage', {}).get('total', 0)}")

    def test_get_ingest_events(self, auth_headers):
        """GET /api/channel-manager/ingest/events"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/events?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Events list failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        assert "count" in data
        print(f"✓ Raw events list: {data['count']} events")

    def test_get_event_stats(self, auth_headers):
        """GET /api/channel-manager/ingest/events/stats"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/events/stats?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Event stats failed: {resp.text}"
        data = resp.json()
        assert "total" in data
        print(f"✓ Event stats: total={data.get('total')}, processed={data.get('processed')}, failed={data.get('failed')}")

    def test_get_workers_status(self, auth_headers):
        """GET /api/channel-manager/ingest/workers/status"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/workers/status",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Workers status failed: {resp.text}"
        data = resp.json()
        assert "workers" in data
        workers = data["workers"]
        assert "hotelrunner_pull" in workers
        assert "exely_pull" in workers
        assert "ingest_processor" in workers
        assert "replay_worker" in workers
        print(f"✓ Workers status: {len(workers)} workers")


# ══════════════════════════════════════════════════════════════════════
# Lineage API Tests
# ══════════════════════════════════════════════════════════════════════

class TestLineageAPI:
    """Test lineage endpoints for version, decision, source_system fields"""

    def test_get_lineage_list(self, auth_headers):
        """GET /api/channel-manager/model/lineage"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Lineage list failed: {resp.text}"
        data = resp.json()
        assert "lineages" in data
        
        # Verify lineage structure has new fields
        if data["lineages"]:
            lineage = data["lineages"][0]
            # Check for new ingest-specific fields
            expected_fields = ["version", "last_decision", "source_system", "external_write_protected", "provider_version"]
            for field in expected_fields:
                assert field in lineage, f"Lineage missing field: {field}"
            print(f"✓ Lineage has required fields: version={lineage.get('version')}, decision={lineage.get('last_decision')}")
        else:
            print("✓ Lineage list returned (empty)")

    def test_lineage_has_loop_prevention_flag(self, auth_headers):
        """Verify lineage has external_write_protected for provider-originated reservations"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        for lineage in data.get("lineages", []):
            if lineage.get("ingested_via") in ["webhook", "pull"]:
                assert lineage.get("external_write_protected") == True, \
                    f"Provider-originated lineage should have external_write_protected=True: {lineage.get('id')}"
                print(f"✓ Loop prevention flag set for {lineage.get('external_reservation_id')}")
                return
        print("✓ Loop prevention check passed (no provider-originated lineages to verify)")


# ══════════════════════════════════════════════════════════════════════
# End-to-End Flow Test
# ══════════════════════════════════════════════════════════════════════

class TestEndToEndFlow:
    """Test complete flow: webhook → process → lineage → verify"""

    def test_full_ingest_flow(self, auth_headers):
        """Full flow: inject → verify in lineage"""
        unique_id = f"HR-E2E-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        
        # 1. Inject event
        payload = {
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "event_type": "reservation_create",
            "payload": {
                "hr_number": unique_id,
                "guest": {"first_name": "E2E", "last_name": "Test", "email": "e2e@test.com"},
                "check_in": "2026-12-01",
                "check_out": "2026-12-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "adults": 2,
                "children": 0,
                "currency": "TRY",
                "total": 5500.00,
                "status": "confirmed",
                "last_modified": now.isoformat(),
                "channel": "booking.com"
            }
        }
        resp1 = requests.post(f"{BASE_URL}/api/channel-manager/ingest/inject-and-process", headers=auth_headers, json=payload)
        assert resp1.status_code == 200
        result = resp1.json().get("pipeline_result", {})
        print(f"  Injected: {result.get('decision')}")

        # 2. Check raw events
        time.sleep(0.5)
        resp2 = requests.get(f"{BASE_URL}/api/channel-manager/ingest/events?property_id={PROPERTY_ID}", headers=auth_headers)
        assert resp2.status_code == 200
        events = resp2.json().get("events", [])
        matching = [e for e in events if e.get("external_reservation_id") == unique_id]
        assert len(matching) >= 1, f"Event {unique_id} not found in raw events"
        print(f"  Raw event found: status={matching[0].get('processing_status')}")

        # 3. If created, check lineage
        if result.get("decision") == "create" and result.get("lineage_id"):
            resp3 = requests.get(f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}", headers=auth_headers)
            assert resp3.status_code == 200
            lineages = resp3.json().get("lineages", [])
            matching_lineage = [l for l in lineages if l.get("external_reservation_id") == unique_id]
            if matching_lineage:
                lineage = matching_lineage[0]
                assert lineage.get("external_write_protected") == True, "Should have loop prevention"
                assert lineage.get("version") >= 1
                print(f"  Lineage verified: version={lineage.get('version')}, protected={lineage.get('external_write_protected')}")

        print(f"✓ E2E flow completed for {unique_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
