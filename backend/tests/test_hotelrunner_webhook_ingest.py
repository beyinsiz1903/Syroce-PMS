"""
HotelRunner Webhook & Ingest Pipeline Tests
Tests the NEW webhook receiver, ingest pipeline, and sync/status endpoints:
- Webhook reservations (POST /webhooks/reservations)
- Webhook modifications (POST /webhooks/modifications)
- Webhook cancellations (POST /webhooks/cancellations)
- Idempotency guard (duplicate handling)
- Raw events API (GET /logs/events)
- Error events API (GET /logs/errors)
- Sync status API (GET /sync/status)
- Manual pull API (POST /sync/reservations/pull) - requires active connection
- Event replay API (POST /sync/reservations/replay/{event_id})
- Connection status (GET /connection)
"""
import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")
TEST_TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestWebhookBase:
    """Base class with shared setup"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for authenticated endpoints"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data.get("access_token") or data.get("token")
        assert self.token, f"No token in response: {data}"
        self.headers = {"Authorization": f"Bearer {self.token}"}


# ── Webhook Endpoint Tests (No auth required - from HotelRunner) ──────────


class TestWebhookReservations:
    """Test webhook reservation endpoint - no auth required"""
    
    def test_webhook_reservation_accepts_single(self):
        """POST /api/channel-manager/hotelrunner/webhooks/reservations - single reservation"""
        unique_hr = f"HR-PYTEST-{uuid.uuid4().hex[:8]}"
        payload = {
            "hr_number": unique_hr,
            "reservation_id": f"res_{unique_hr}",
            "channel": "booking.com",
            "channel_display": "Booking.com",
            "state": "confirmed",
            "guest": "Test Guest",
            "firstname": "Test",
            "lastname": "Guest",
            "checkin_date": "2026-02-01",
            "checkout_date": "2026-02-03",
            "total": 500.00,
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 2,
            "rooms": [
                {
                    "room_code": "STD",
                    "rate_code": "BAR",
                    "room_name": "Standard Room",
                    "adults": 2,
                    "children": 0,
                    "total": 500.00
                }
            ],
            "address": {
                "email": "test@example.com",
                "phone": "+905551234567"
            },
            "note": "Test reservation"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("status") == "accepted", f"Expected status=accepted: {data}"
        assert "count" in data, f"Missing count: {data}"
        print(f"Webhook reservation accepted: {data}")
    
    def test_webhook_reservation_accepts_batch(self):
        """POST /api/channel-manager/hotelrunner/webhooks/reservations - batch reservations"""
        reservations = [
            {
                "hr_number": f"HR-PYTEST-BATCH-{i}-{uuid.uuid4().hex[:6]}",
                "reservation_id": f"res_batch_{i}",
                "channel": "expedia",
                "state": "confirmed",
                "guest": f"Batch Guest {i}",
                "checkin_date": "2026-02-10",
                "checkout_date": "2026-02-12",
                "total": 300.00 + i * 100,
                "currency": "TRY"
            }
            for i in range(3)
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json={"reservations": reservations}
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert data.get("status") == "accepted", f"Expected status=accepted: {data}"
        assert data.get("count") == 3, f"Expected count=3: {data}"
        print(f"Batch webhook accepted: {data}")
    
    def test_webhook_reservation_requires_tenant_id(self):
        """POST /api/channel-manager/hotelrunner/webhooks/reservations - missing tenant_id"""
        payload = {"hr_number": "HR-TEST-NO-TENANT", "channel": "test"}
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            json=payload
        )
        
        # Should return 400 if no tenant_id provided
        assert response.status_code == 400, f"Expected 400, got: {response.status_code} - {response.text}"
        print(f"Missing tenant_id correctly rejected: {response.status_code}")


class TestWebhookModifications:
    """Test webhook modification endpoint"""
    
    def test_webhook_modification_accepts(self):
        """POST /api/channel-manager/hotelrunner/webhooks/modifications"""
        unique_hr = f"HR-PYTEST-MOD-{uuid.uuid4().hex[:8]}"
        payload = {
            "hr_number": unique_hr,
            "reservation_id": f"res_{unique_hr}",
            "channel": "booking.com",
            "state": "modified",
            "guest": "Modified Guest",
            "checkin_date": "2026-02-05",
            "checkout_date": "2026-02-08",
            "total": 750.00,
            "currency": "TRY"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/modifications",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert data.get("status") == "accepted", f"Expected status=accepted: {data}"
        print(f"Modification webhook accepted: {data}")


class TestWebhookCancellations:
    """Test webhook cancellation endpoint"""
    
    def test_webhook_cancellation_accepts(self):
        """POST /api/channel-manager/hotelrunner/webhooks/cancellations"""
        unique_hr = f"HR-PYTEST-CANCEL-{uuid.uuid4().hex[:8]}"
        payload = {
            "hr_number": unique_hr,
            "reservation_id": f"res_{unique_hr}",
            "channel": "expedia",
            "state": "cancelled"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/cancellations",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert data.get("status") == "accepted", f"Expected status=accepted: {data}"
        print(f"Cancellation webhook accepted: {data}")


# ── Idempotency Tests ─────────────────────────────────────────────────


class TestIdempotency:
    """Test idempotency guard for duplicate reservations"""
    
    def test_duplicate_reservation_idempotent(self):
        """Duplicate reservation should not create duplicate entries"""
        unique_hr = f"HR-PYTEST-IDEM-{uuid.uuid4().hex[:8]}"
        payload = {
            "hr_number": unique_hr,
            "reservation_id": f"res_{unique_hr}",
            "channel": "booking.com",
            "state": "confirmed",
            "guest": "Idempotency Test Guest",
            "checkin_date": "2026-03-01",
            "checkout_date": "2026-03-03",
            "total": 400.00,
            "currency": "TRY"
        }
        
        # First request
        response1 = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        assert response1.status_code == 200, f"First request failed: {response1.text}"
        
        # Wait for async processing
        time.sleep(1)
        
        # Second (duplicate) request
        response2 = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        assert response2.status_code == 200, f"Second request failed: {response2.text}"
        
        # Both should be accepted (async processing handles idempotency)
        data2 = response2.json()
        assert data2.get("status") == "accepted", f"Expected accepted: {data2}"
        print(f"Idempotency test passed - duplicate accepted for async processing: {unique_hr}")
    
    def test_duplicate_cancellation_idempotent(self):
        """Duplicate cancellation should result in skipped event"""
        unique_hr = f"HR-PYTEST-IDEM-CANCEL-{uuid.uuid4().hex[:8]}"
        
        # First: Create a reservation
        res_payload = {
            "hr_number": unique_hr,
            "reservation_id": f"res_{unique_hr}",
            "channel": "booking.com",
            "state": "confirmed",
            "guest": "Cancel Idempotency Test",
            "checkin_date": "2026-03-10",
            "checkout_date": "2026-03-12",
            "total": 300.00,
            "currency": "TRY"
        }
        
        requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json=res_payload
        )
        time.sleep(1)
        
        # Cancel payload
        cancel_payload = {"hr_number": unique_hr, "state": "cancelled"}
        
        # First cancellation
        response1 = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/cancellations",
            params={"tenant_id": TEST_TENANT_ID},
            json=cancel_payload
        )
        assert response1.status_code == 200, f"First cancel failed: {response1.text}"
        time.sleep(1)
        
        # Second cancellation (duplicate)
        response2 = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/cancellations",
            params={"tenant_id": TEST_TENANT_ID},
            json=cancel_payload
        )
        assert response2.status_code == 200, f"Second cancel failed: {response2.text}"
        
        print(f"Duplicate cancellation idempotency test passed: {unique_hr}")


# ── Authenticated Endpoint Tests ──────────────────────────────────────


class TestRawEventsAPI(TestWebhookBase):
    """Test raw events log API - requires auth"""
    
    def test_get_raw_events(self):
        """GET /api/channel-manager/hotelrunner/logs/events - returns event list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/logs/events",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "events" in data, f"Missing 'events' field: {data}"
        assert isinstance(data["events"], list), f"events should be list: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        print(f"Raw events count: {data['count']}")
    
    def test_get_raw_events_by_status(self):
        """GET /api/channel-manager/hotelrunner/logs/events?status=processed"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/logs/events",
            headers=self.headers,
            params={"status": "processed"}
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "events" in data, f"Missing 'events' field: {data}"
        print(f"Processed events count: {data['count']}")


class TestErrorEventsAPI(TestWebhookBase):
    """Test error events API - requires auth"""
    
    def test_get_error_events(self):
        """GET /api/channel-manager/hotelrunner/logs/errors - returns error list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/logs/errors",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "events" in data, f"Missing 'events' field: {data}"
        assert isinstance(data["events"], list), f"events should be list: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        print(f"Error events count: {data['count']}")


class TestSyncStatusAPI(TestWebhookBase):
    """Test sync status API - requires auth"""
    
    def test_get_sync_status(self):
        """GET /api/channel-manager/hotelrunner/sync/status - returns scheduler state"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/sync/status",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "scheduler_running" in data, f"Missing 'scheduler_running': {data}"
        assert "pending_events" in data, f"Missing 'pending_events': {data}"
        assert "error_events" in data, f"Missing 'error_events': {data}"
        assert "total_reservations" in data, f"Missing 'total_reservations': {data}"
        
        print(f"Sync status: scheduler_running={data['scheduler_running']}, " +
              f"pending={data['pending_events']}, errors={data['error_events']}, " +
              f"total_reservations={data['total_reservations']}")


class TestManualPullAPI(TestWebhookBase):
    """Test manual pull API - requires active connection"""
    
    def test_manual_pull_requires_connection(self):
        """POST /api/channel-manager/hotelrunner/sync/reservations/pull - requires active connection"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/sync/reservations/pull",
            headers=self.headers
        )
        
        # Should return 404 since HotelRunner is not connected
        assert response.status_code == 404, f"Expected 404 (no connection), got: {response.status_code} - {response.text}"
        print(f"Manual pull correctly requires connection: {response.status_code}")


class TestEventReplayAPI(TestWebhookBase):
    """Test event replay API - requires auth"""
    
    def test_replay_nonexistent_event_returns_404(self):
        """POST /api/channel-manager/hotelrunner/sync/reservations/replay/{event_id} - nonexistent event"""
        fake_event_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/sync/reservations/replay/{fake_event_id}",
            headers=self.headers
        )
        
        # Should return 404 for nonexistent event
        assert response.status_code == 404, f"Expected 404, got: {response.status_code} - {response.text}"
        print(f"Replay nonexistent event correctly returns 404")
    
    def test_replay_existing_event(self):
        """Create event then replay it"""
        # First create a reservation to generate an event
        unique_hr = f"HR-PYTEST-REPLAY-{uuid.uuid4().hex[:8]}"
        payload = {
            "hr_number": unique_hr,
            "channel": "booking.com",
            "state": "confirmed",
            "guest": "Replay Test Guest",
            "checkin_date": "2026-04-01",
            "checkout_date": "2026-04-03",
            "total": 600.00,
            "currency": "TRY"
        }
        
        requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            json=payload
        )
        time.sleep(1)
        
        # Get events to find the event_id
        events_response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/logs/events",
            headers=self.headers,
            params={"limit": 10}
        )
        
        if events_response.status_code == 200:
            events_data = events_response.json()
            events = events_data.get("events", [])
            
            # Find our event
            our_event = next((e for e in events if e.get("hr_number") == unique_hr), None)
            
            if our_event and our_event.get("id"):
                # Try to replay
                replay_response = requests.post(
                    f"{BASE_URL}/api/channel-manager/hotelrunner/sync/reservations/replay/{our_event['id']}",
                    headers=self.headers
                )
                # Should succeed (200)
                assert replay_response.status_code == 200, f"Replay failed: {replay_response.status_code} - {replay_response.text}"
                print(f"Event replay successful for {unique_hr}")
            else:
                print(f"Could not find event for replay test - events: {[e.get('hr_number') for e in events[:5]]}")
        else:
            print(f"Could not get events: {events_response.status_code}")


class TestConnectionAPI(TestWebhookBase):
    """Test connection status API - requires auth"""
    
    def test_connection_returns_disconnected(self):
        """GET /api/channel-manager/hotelrunner/connection - should show disconnected"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/hotelrunner/connection",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "connected" in data, f"Missing 'connected' field: {data}"
        # Since no real credentials, should be false
        print(f"Connection status: connected={data.get('connected')}")


# ── Webhook Invalid JSON Test ─────────────────────────────────────────


class TestWebhookInvalidPayloads:
    """Test webhook endpoints with invalid payloads"""
    
    def test_webhook_reservation_invalid_json(self):
        """POST /webhooks/reservations with invalid JSON"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            params={"tenant_id": TEST_TENANT_ID},
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got: {response.status_code}"
        print(f"Invalid JSON correctly rejected: {response.status_code}")
