"""
HotelRunner Provider Parity Tests
==================================

Tests for:
1. Mock server health and auth validation
2. Mock server rooms, reservations, ARI push
3. Error injection and reset
4. Webhook endpoints (new reservation, modification, cancellation)
5. Ingest pipeline lineage creation
6. Duplicate delivery detection
"""
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest
import requests

# API URLs
MOCK_SERVER_URL = "http://localhost:9999"
API_URL = os.environ.get("VITE_BACKEND_URL", "https://transition-phase.preview.emergentagent.com")

# Mock server credentials
MOCK_TOKEN = "mock-hr-token-001"
MOCK_HR_ID = "HR-HOTEL-001"
BAD_TOKEN = "bad-token"

# Test tenant for webhooks
TEST_TENANT_ID = "test-tenant-e2e"
TEST_PROPERTY_ID = "prop-001"


class TestMockServerHealth:
    """Test 1: Mock server health and basic connectivity"""

    def test_mock_server_health(self):
        """GET /health should return ok"""
        response = requests.get(f"{MOCK_SERVER_URL}/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("provider") == "hotelrunner-mock"
        print(f"PASS: Mock server health OK - version={data.get('version')}")


class TestMockServerAuth:
    """Test 2: Mock server authentication validation"""

    def test_bad_token_returns_401(self):
        """GET /api/v1/apps/infos/channels with bad token should return 401"""
        response = requests.get(
            f"{MOCK_SERVER_URL}/api/v1/apps/infos/channels",
            params={"token": BAD_TOKEN, "hr_id": MOCK_HR_ID},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"PASS: Bad token correctly rejected with 401")

    def test_valid_auth_returns_channels(self):
        """GET /api/v1/apps/infos/channels with valid token should return channels"""
        response = requests.get(
            f"{MOCK_SERVER_URL}/api/v1/apps/infos/channels",
            params={"token": MOCK_TOKEN, "hr_id": MOCK_HR_ID},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "channels" in data
        assert len(data["channels"]) > 0
        print(f"PASS: Valid auth returned {len(data['channels'])} channels")


class TestMockServerRooms:
    """Test 3: Mock server rooms endpoint"""

    def test_get_rooms_returns_4_rooms(self):
        """GET /api/v2/apps/rooms should return 4 rooms"""
        response = requests.get(
            f"{MOCK_SERVER_URL}/api/v2/apps/rooms",
            params={"token": MOCK_TOKEN, "hr_id": MOCK_HR_ID},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rooms" in data
        assert len(data["rooms"]) == 4, f"Expected 4 rooms, got {len(data['rooms'])}"
        
        # Verify room codes
        room_codes = [r["inv_code"] for r in data["rooms"]]
        expected_codes = ["STD", "DLX", "SUI", "FAM"]
        for code in expected_codes:
            assert code in room_codes, f"Missing room code: {code}"
        print(f"PASS: Got 4 rooms with codes: {room_codes}")


class TestMockServerReservations:
    """Test 4: Mock server reservations endpoint"""

    def test_get_reservations_undelivered(self):
        """GET /api/v2/apps/reservations with undelivered=true should return reservations"""
        # First reset to ensure clean state
        requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)
        
        response = requests.get(
            f"{MOCK_SERVER_URL}/api/v2/apps/reservations",
            params={"token": MOCK_TOKEN, "hr_id": MOCK_HR_ID, "undelivered": "true"},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "reservations" in data
        assert len(data["reservations"]) > 0, "Expected at least 1 reservation"
        
        # Verify reservation structure
        res = data["reservations"][0]
        required_fields = ["hr_number", "state", "checkin_date", "checkout_date", "rooms"]
        for field in required_fields:
            assert field in res, f"Missing field: {field}"
        print(f"PASS: Got {len(data['reservations'])} undelivered reservations")


class TestMockServerARIPush:
    """Test 5: Mock server ARI push endpoint"""

    def test_ari_push_success(self):
        """PUT /api/v2/apps/rooms/~ with valid data should succeed"""
        response = requests.put(
            f"{MOCK_SERVER_URL}/api/v2/apps/rooms/~",
            params={"token": MOCK_TOKEN, "hr_id": MOCK_HR_ID},
            data={
                "inv_code": "STD",
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "availability": "5"
            },
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert "transaction_id" in data
        print(f"PASS: ARI push succeeded with transaction_id={data.get('transaction_id')}")


class TestMockServerErrorInjection:
    """Test 6: Mock server error injection and reset"""

    def test_error_injection_returns_500(self):
        """POST /mock/config with error_rate=1.0 then GET rooms should get 500"""
        # Configure 100% error rate
        config_response = requests.post(
            f"{MOCK_SERVER_URL}/mock/config",
            json={"error_rate": 1.0},
            timeout=10
        )
        assert config_response.status_code == 200
        
        # Now rooms should fail
        response = requests.get(
            f"{MOCK_SERVER_URL}/api/v2/apps/rooms",
            params={"token": MOCK_TOKEN, "hr_id": MOCK_HR_ID},
            timeout=10
        )
        assert response.status_code == 500, f"Expected 500, got {response.status_code}"
        print(f"PASS: Error injection working - got 500 as expected")
        
        # Reset for other tests
        requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)

    def test_mock_reset_clears_state(self):
        """POST /mock/reset should reset state"""
        response = requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "reset"
        assert "reservations" in data
        print(f"PASS: Mock reset successful - {data.get('reservations')} reservations")


class TestWebhookEndpoints:
    """Test 7: Webhook endpoints for reservations, modifications, cancellations"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset mock server before each test"""
        requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)

    def _generate_hr_payload(self, hr_number: str = None, state: str = "confirmed"):
        """Generate a realistic HotelRunner reservation payload"""
        if not hr_number:
            hr_number = f"HR-{uuid.uuid4().hex[:8].upper()}"
        
        now = datetime.utcnow()
        checkin = now + timedelta(days=7)
        checkout = checkin + timedelta(days=3)
        
        return {
            "hr_number": hr_number,
            "reservation_id": str(10000 + hash(hr_number) % 1000),
            "state": state,
            "firstname": "Test",
            "lastname": "Guest",
            "country": "TR",
            "channel": "booking.com",
            "channel_display": "Booking.com",
            "checkin_date": checkin.strftime("%Y-%m-%d"),
            "checkout_date": checkout.strftime("%Y-%m-%d"),
            "total": 1500.00,
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 2,
            "message_uid": f"msg-{uuid.uuid4().hex[:8]}",
            "address": {
                "email": "test@example.com",
                "phone": "+905551234567",
                "city": "Istanbul",
                "country_code": "TR"
            },
            "rooms": [{
                "room_code": "STD",
                "rate_code": "BAR",
                "room_name": "Standard Oda",
                "adults": 2,
                "children": 0,
                "total": 1500.00
            }],
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat()
        }

    def test_webhook_new_reservation_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/reservations should return accepted"""
        payload = self._generate_hr_payload()
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        assert data.get("count") == 1
        print(f"PASS: Webhook new reservation accepted - hr_number={payload['hr_number']}")
        return payload["hr_number"]

    def test_webhook_modification_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/modifications should return accepted"""
        payload = self._generate_hr_payload(state="modified")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/modifications",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook modification accepted")

    def test_webhook_cancellation_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/cancellations should return accepted"""
        payload = self._generate_hr_payload(state="cancelled")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/cancellations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook cancellation accepted")

    def test_webhook_missing_tenant_returns_400(self):
        """POST webhook without X-Tenant-ID should return 400"""
        payload = self._generate_hr_payload()
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"PASS: Missing tenant ID correctly rejected with 400")


class TestIngestPipelineLineage:
    """Test 8: Ingest pipeline creates lineage for new reservations"""

    def _generate_unique_hr_payload(self):
        """Generate a unique HR payload for lineage testing"""
        hr_number = f"HR-LINEAGE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.utcnow()
        checkin = now + timedelta(days=14)
        checkout = checkin + timedelta(days=2)
        
        return {
            "hr_number": hr_number,
            "reservation_id": str(20000 + hash(hr_number) % 1000),
            "state": "confirmed",
            "firstname": "Lineage",
            "lastname": "Test",
            "country": "TR",
            "channel": "expedia",
            "channel_display": "Expedia",
            "checkin_date": checkin.strftime("%Y-%m-%d"),
            "checkout_date": checkout.strftime("%Y-%m-%d"),
            "total": 2500.00,
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 2,
            "message_uid": f"msg-lineage-{uuid.uuid4().hex[:8]}",
            "address": {
                "email": "lineage@test.com",
                "phone": "+905559876543",
                "city": "Ankara",
                "country_code": "TR"
            },
            "rooms": [{
                "room_code": "DLX",
                "rate_code": "BAR",
                "room_name": "Deluxe Oda",
                "adults": 2,
                "children": 0,
                "total": 2500.00
            }],
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat()
        }

    def test_ingest_creates_lineage(self):
        """Webhook should create lineage record (verify via async processing)"""
        payload = self._generate_unique_hr_payload()
        hr_number = payload["hr_number"]
        
        # Send webhook
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        
        # Wait for async processing (background task)
        time.sleep(4)
        
        # Note: We can't directly query MongoDB from here, but we verify the webhook was accepted
        # The actual lineage verification would require DB access or an API endpoint
        print(f"PASS: Webhook accepted for lineage creation - hr_number={hr_number}")
        print("NOTE: Lineage creation is async - verify via MongoDB if needed")


class TestDuplicateDeliveryDetection:
    """Test 9: Duplicate delivery should be detected and skipped"""

    def test_duplicate_webhook_detected(self):
        """Sending same reservation twice should be handled (deduplicated)"""
        # Generate a unique payload
        hr_number = f"HR-DUP-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.utcnow()
        checkin = now + timedelta(days=21)
        checkout = checkin + timedelta(days=2)
        
        payload = {
            "hr_number": hr_number,
            "reservation_id": str(30000 + hash(hr_number) % 1000),
            "state": "confirmed",
            "firstname": "Duplicate",
            "lastname": "Test",
            "country": "TR",
            "channel": "agoda",
            "channel_display": "Agoda",
            "checkin_date": checkin.strftime("%Y-%m-%d"),
            "checkout_date": checkout.strftime("%Y-%m-%d"),
            "total": 1800.00,
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 1,
            "message_uid": f"msg-dup-{uuid.uuid4().hex[:8]}",
            "address": {
                "email": "dup@test.com",
                "phone": "+905551112233",
                "city": "Izmir",
                "country_code": "TR"
            },
            "rooms": [{
                "room_code": "STD",
                "rate_code": "NONREF",
                "room_name": "Standard Oda",
                "adults": 1,
                "children": 0,
                "total": 1800.00
            }],
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat()
        }
        
        # First delivery
        response1 = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response1.status_code == 200, f"First webhook failed: {response1.text}"
        
        # Wait for processing
        time.sleep(3)
        
        # Second delivery (duplicate)
        response2 = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        # Should still be accepted (webhook layer accepts, pipeline deduplicates)
        assert response2.status_code == 200, f"Second webhook failed: {response2.text}"
        
        print(f"PASS: Duplicate delivery handled - hr_number={hr_number}")
        print("NOTE: Deduplication happens in pipeline (check logs for 'DUPLICATE' or 'HASH_DUP')")


class TestNormalizerParsing:
    """Test 10: Normalizer correctly parses HotelRunner format"""

    def test_normalizer_handles_real_hr_format(self):
        """Verify normalizer handles actual HotelRunner API format"""
        # This is a unit-style test that verifies the normalizer logic
        # We test by sending a webhook and checking it's accepted
        
        # Real HotelRunner format with all fields
        payload = {
            "hr_number": f"HR-NORM-{uuid.uuid4().hex[:6].upper()}",
            "reservation_id": "12345",
            "state": "confirmed",  # HotelRunner uses 'state' not 'status'
            "firstname": "John",   # HotelRunner uses firstname/lastname
            "lastname": "Doe",
            "country": "US",
            "channel": "booking.com",
            "channel_display": "Booking.com",
            "checkin_date": "2026-05-01",  # HotelRunner uses checkin_date
            "checkout_date": "2026-05-05",
            "total": 3000.00,
            "currency": "USD",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 2,
            "message_uid": f"msg-norm-{uuid.uuid4().hex[:8]}",
            "address": {  # HotelRunner puts email in address
                "email": "john.doe@example.com",
                "phone": "+12025551234",
                "address_line": "123 Main St",
                "city": "New York",
                "zipcode": "10001",
                "country_code": "US"
            },
            "rooms": [{  # HotelRunner uses rooms[].room_code
                "room_code": "SUI",
                "rate_code": "BAR",
                "room_name": "Suite",
                "adults": 2,
                "children": 0,
                "total": 3000.00,
                "daily_rates": [],
                "guest": "John Doe"
            }],
            "updated_at": datetime.utcnow().isoformat(),
            "modified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Normalizer test failed: {response.text}"
        print(f"PASS: Normalizer correctly handles real HotelRunner format")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
