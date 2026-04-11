"""
P0 Verification Tests — 9-Collection Data Model & Reservation Ingest Pipeline
===============================================================================

This test suite validates the P0 requirements for the Hotel PMS Channel Manager:
- 9-collection data model schema
- HotelRunner (REST/webhook) provider
- Exely (SOAP/pull) provider
- Full reservation ingest pipeline

Providers: HotelRunner + Exely
Collections: 9 (provider_connections, room_mappings, rate_plan_mappings, 
              raw_channel_events, reservation_lineage, ari_change_sets,
              ari_outbound_logs, ari_drift_state, channel_reconciliation_cases)
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')
pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set — requires live server")
PROPERTY_ID = "prop-001"


@pytest.fixture(scope="module")
def auth_token():
    """Login with demo@hotel.com / demo123"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert "access_token" in data, "Missing access_token in login response"
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers with Bearer token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Authentication Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    """Verify login endpoint works with demo credentials"""

    def test_login_demo_user(self):
        """POST /api/auth/login with demo@hotel.com / demo123"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "access_token" in data, "Missing access_token"
        assert "user" in data, "Missing user object"
        assert "tenant" in data, "Missing tenant object"
        
        # Verify user data
        user = data["user"]
        assert user.get("email") == "demo@hotel.com", f"Email mismatch: {user.get('email')}"
        
        print(f"✓ Login successful: user_id={user.get('id')}, tenant_id={data.get('tenant', {}).get('id')}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Data Model Schema Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataModelSchema:
    """Verify 9-collection schema endpoint"""

    def test_get_schema(self, auth_headers):
        """GET /api/channel-manager/model/schema - returns 9 collection schema"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/schema",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Schema endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify model version
        assert data.get("model_version") == "2.0", f"Expected v2.0, got {data.get('model_version')}"
        
        # Verify providers
        assert set(data.get("providers", [])) == {"hotelrunner", "exely"}, \
            f"Expected hotelrunner+exely, got {data.get('providers')}"
        
        # Verify 9 collections
        assert data.get("total_collections") == 9, f"Expected 9 collections, got {data.get('total_collections')}"
        
        # Verify collection names
        expected_collections = [
            "provider_connections",
            "room_mappings", 
            "rate_plan_mappings",
            "raw_channel_events",
            "reservation_lineage",
            "ari_change_sets",
            "ari_outbound_logs",
            "ari_drift_state",
            "channel_reconciliation_cases"
        ]
        actual_collections = [c["name"] for c in data.get("collections", [])]
        for coll in expected_collections:
            assert coll in actual_collections, f"Missing collection: {coll}"
        
        print(f"✓ Schema verified: v{data['model_version']} with {data['total_collections']} collections")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Provider Connections Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderConnections:
    """Verify connections endpoint returns hotelrunner and exely"""

    def test_get_connections(self, auth_headers):
        """GET /api/channel-manager/model/connections - returns provider connections"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/connections",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Connections endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "connections" in data, "Missing connections array"
        assert "count" in data, "Missing count field"
        
        connections = data["connections"]
        providers_found = [c.get("provider") for c in connections]
        
        # Check for hotelrunner and exely
        assert "hotelrunner" in providers_found, f"Missing hotelrunner connection. Found: {providers_found}"
        assert "exely" in providers_found, f"Missing exely connection. Found: {providers_found}"
        
        print(f"✓ Connections verified: {len(connections)} connections with providers {providers_found}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Room Mappings Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoomMappings:
    """Verify room mappings for prop-001"""

    def test_get_room_mappings(self, auth_headers):
        """GET /api/channel-manager/model/room-mappings?property_id=prop-001"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/room-mappings?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Room mappings endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "mappings" in data, "Missing mappings array"
        assert "count" in data, "Missing count field"
        
        mappings = data["mappings"]
        
        # Check for expected room mappings (STD for hotelrunner, DLX for exely)
        hr_mappings = [m for m in mappings if m.get("provider") == "hotelrunner"]
        ex_mappings = [m for m in mappings if m.get("provider") == "exely"]
        
        # Verify STD mapping exists for hotelrunner
        hr_std = [m for m in hr_mappings if m.get("provider_room_code") == "STD"]
        assert len(hr_std) > 0, f"Missing STD room mapping for hotelrunner. Found: {[m.get('provider_room_code') for m in hr_mappings]}"
        
        # Verify DLX mapping exists for exely
        ex_dlx = [m for m in ex_mappings if m.get("provider_room_code") == "DLX"]
        assert len(ex_dlx) > 0, f"Missing DLX room mapping for exely. Found: {[m.get('provider_room_code') for m in ex_mappings]}"
        
        print(f"✓ Room mappings verified: {len(mappings)} mappings (HR:{len(hr_mappings)}, EX:{len(ex_mappings)})")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Lineage Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestReservationLineage:
    """Verify reservation lineage for prop-001"""

    def test_get_lineage(self, auth_headers):
        """GET /api/channel-manager/model/lineage?property_id=prop-001"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Lineage endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "lineages" in data, "Missing lineages array"
        assert "count" in data, "Missing count field"
        
        lineages = data["lineages"]
        
        # Verify lineage records have required fields
        if lineages:
            lineage = lineages[0]
            required_fields = [
                "id", "provider", "external_reservation_id", 
                "version", "last_decision", "status"
            ]
            for field in required_fields:
                assert field in lineage, f"Lineage missing field: {field}"
        
        print(f"✓ Lineage verified: {len(lineages)} reservation lineage records")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Ingest Pipeline Status Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestStatus:
    """Verify ingest pipeline status with events, lineage, recon stats"""

    def test_get_ingest_status(self, auth_headers):
        """GET /api/channel-manager/ingest/status - returns pipeline status"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/status?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Ingest status failed: {resp.text}"
        data = resp.json()
        
        # Verify pipeline section
        assert "pipeline" in data, "Missing pipeline stats"
        pipeline = data["pipeline"]
        assert "raw_events" in pipeline, "Missing raw_events stats"
        assert "lineage" in pipeline, "Missing lineage stats"
        assert "reconciliation" in pipeline, "Missing reconciliation stats"
        
        # Verify workers section
        assert "workers" in data, "Missing workers status"
        workers = data["workers"]
        expected_workers = ["hotelrunner_pull", "exely_pull", "ingest_processor", "replay_worker"]
        for worker in expected_workers:
            assert worker in workers, f"Missing worker: {worker}"
        
        print(f"✓ Ingest status: events={pipeline['raw_events'].get('total', 0)}, "
              f"lineage={pipeline['lineage'].get('total', 0)}, "
              f"workers={len(workers)}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Ingest Events Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestEvents:
    """Verify raw channel events endpoint"""

    def test_get_ingest_events(self, auth_headers):
        """GET /api/channel-manager/ingest/events?property_id=prop-001"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/events?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Events list failed: {resp.text}"
        data = resp.json()
        
        assert "events" in data, "Missing events array"
        assert "count" in data, "Missing count field"
        
        events = data["events"]
        if events:
            event = events[0]
            required_fields = ["id", "provider", "event_type", "processing_status"]
            for field in required_fields:
                assert field in event, f"Event missing field: {field}"
        
        print(f"✓ Raw events: {len(events)} events")

    def test_get_event_stats(self, auth_headers):
        """GET /api/channel-manager/ingest/events/stats"""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/ingest/events/stats?property_id={PROPERTY_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Event stats failed: {resp.text}"
        data = resp.json()
        
        assert "total" in data, "Missing total count"
        print(f"✓ Event stats: total={data.get('total')}, processed={data.get('processed')}, "
              f"pending={data.get('pending')}, failed={data.get('failed')}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. HotelRunner Inject-and-Process Flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestHotelRunnerIngestFlow:
    """Test HotelRunner CREATE flow with inject-and-process"""

    def test_hotelrunner_create_flow(self, auth_headers):
        """POST /api/channel-manager/ingest/inject-and-process - HotelRunner CREATE"""
        unique_id = f"HR-TEST-{uuid.uuid4().hex[:6].upper()}"
        
        payload = {
            "provider": "hotelrunner",
            "event_type": "reservation_create",
            "property_id": PROPERTY_ID,
            "payload": {
                "hr_number": unique_id,
                "guest": {
                    "first_name": "Test",
                    "last_name": "User",
                    "email": "test@t.com"
                },
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "room_type": "STD",
                "rate_plan": "BAR",
                "adults": 2,
                "children": 0,
                "currency": "TRY",
                "total": 5000,
                "status": "confirmed",
                "last_modified": "2026-03-14T15:00:00Z",
                "channel": "booking.com"
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/inject-and-process",
            headers=auth_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Inject-and-process failed: {resp.text}"
        data = resp.json()
        
        # Verify response
        assert "event_id" in data, "Missing event_id"
        assert "pipeline_result" in data, "Missing pipeline_result"
        
        result = data["pipeline_result"]
        assert "decision" in result, "Missing decision in pipeline_result"
        assert "status" in result, "Missing status in pipeline_result"
        
        # Decision can be create, skip (duplicate), or pending_mapping
        valid_decisions = ["create", "skip", "pending_mapping", "update"]
        assert result["decision"] in valid_decisions, \
            f"Unexpected decision: {result['decision']}. Valid: {valid_decisions}"
        
        print(f"✓ HotelRunner inject-and-process: {unique_id} → "
              f"decision={result['decision']}, status={result['status']}")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Exely Inject-and-Process Flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestExelyIngestFlow:
    """Test Exely CREATE flow with inject-and-process"""

    def test_exely_create_flow(self, auth_headers):
        """POST /api/channel-manager/ingest/inject-and-process - Exely CREATE"""
        unique_id = f"EX-TEST-{uuid.uuid4().hex[:6].upper()}"
        
        payload = {
            "provider": "exely",
            "event_type": "reservation_create",
            "property_id": PROPERTY_ID,
            "payload": {
                "UniqueID": unique_id,
                "ResStatus": "Commit",
                "LastModifyDateTime": "2026-03-14T15:00:00Z",
                "RoomStay": {
                    "RoomTypeCode": "DLX",
                    "RatePlanCode": "RACK",
                    "StartDate": "2026-08-01",
                    "EndDate": "2026-08-05"
                },
                "GuestCount": {
                    "adults": 2,
                    "children": 0
                },
                "ResGuest": {
                    "GivenName": "Exely",
                    "Surname": "Tester",
                    "Email": "exely@t.com"
                },
                "Total": {
                    "Amount": 7000,
                    "CurrencyCode": "TRY"
                },
                "Source": "expedia"
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/inject-and-process",
            headers=auth_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Exely inject-and-process failed: {resp.text}"
        data = resp.json()
        
        # Verify response
        assert "event_id" in data, "Missing event_id"
        assert "pipeline_result" in data, "Missing pipeline_result"
        
        result = data["pipeline_result"]
        valid_decisions = ["create", "skip", "pending_mapping", "update"]
        assert result["decision"] in valid_decisions, \
            f"Unexpected decision: {result['decision']}. Valid: {valid_decisions}"
        
        print(f"✓ Exely inject-and-process: {unique_id} → "
              f"decision={result['decision']}, status={result['status']}")


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Worker Control Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkerControls:
    """Test worker trigger endpoints"""

    def test_trigger_process_worker(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/process"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/process",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Process worker trigger failed: {resp.text}"
        data = resp.json()
        assert "result" in data, "Missing result in response"
        print(f"✓ Process worker triggered: {data.get('result', {})}")

    def test_trigger_replay_worker(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/replay"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/replay",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Replay worker trigger failed: {resp.text}"
        data = resp.json()
        assert "result" in data, "Missing result in response"
        print(f"✓ Replay worker triggered: {data.get('result', {})}")

    def test_trigger_hotelrunner_pull_worker(self, auth_headers):
        """POST /api/channel-manager/ingest/workers/pull/hotelrunner - MOCKED"""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/ingest/workers/pull/hotelrunner",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"HR pull worker trigger failed: {resp.text}"
        data = resp.json()
        assert "result" in data, "Missing result in response"
        print(f"✓ HotelRunner pull worker triggered (MOCKED): {data.get('result', {})}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
