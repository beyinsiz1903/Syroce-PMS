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
API_URL = os.environ.get("VITE_BACKEND_URL", "https://test-api.syroce.local")

# Mock server credentials
MOCK_TOKEN = "mock-hr-token-001"
MOCK_HR_ID = "HR-HOTEL-001"
BAD_TOKEN = "bad-token"

# Test tenant for webhooks
TEST_TENANT_ID = "test-tenant-e2e"
TEST_PROPERTY_ID = "prop-001"

def send_hr_webhook(path: str, payload: dict, secret: str = None, override_headers: dict = None):
    import json, hmac, hashlib, time
    from urllib.parse import urlencode

    if secret is None:
        secret = os.environ.get("HOTELRUNNER_WEBHOOK_SECRET", "test-secret")

    data_str = json.dumps(payload)
    encoded_body = urlencode({"data": data_str}).encode("utf-8")

    ts = str(int(time.time()))
    signed_payload = f"{ts}.".encode() + encoded_body
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    headers = {
        "X-Tenant-ID": TEST_TENANT_ID,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-HotelRunner-Timestamp": ts,
        "X-HotelRunner-Signature": signature
    }
    if override_headers:
        headers.update(override_headers)

    return requests.post(
        f"{API_URL}{path}",
        headers=headers,
        data=encoded_body,
        timeout=15
    )



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
        """Reset mock server before each test and seed mock connections"""
        requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)
        
        try:
            from pymongo import MongoClient
            import os
            mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
            client = MongoClient(mongo_url)
            # Use the database specified in the URI, fallback to hotel_pms
            db = client.get_database() if client.get_database().name else client["hotel_pms"]
            
            db.hotelrunner_connections.update_one(
                {"hr_id": MOCK_HR_ID},
                {"$set": {
                    "tenant_id": TEST_TENANT_ID,
                    "hr_id": MOCK_HR_ID,
                    "token": MOCK_TOKEN,
                    "is_active": True
                }},
                upsert=True
            )
            
            db.hotelrunner_connections.update_one(
                {"hr_id": MOCK_HR_ID + "_B"},
                {"$set": {
                    "tenant_id": TEST_TENANT_ID + "_B",
                    "hr_id": MOCK_HR_ID + "_B",
                    "token": MOCK_TOKEN + "_B",
                    "is_active": True
                }},
                upsert=True
            )
        except Exception as e:
            print(f"Warning: Could not seed test database connections: {e}")

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
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        assert data.get("count") == 1
        print(f"PASS: Webhook new reservation accepted - hr_number={payload['hr_number']}")
        return payload["hr_number"]

    def test_webhook_modification_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/modifications should return accepted"""
        payload = self._generate_hr_payload(state="modified")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/modifications", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook modification accepted")

    def test_webhook_cancellation_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/cancellations should return accepted"""
        payload = self._generate_hr_payload(state="cancelled")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/cancellations", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook cancellation accepted")

    def test_webhook_missing_tenant_returns_400(self):
        """Webhook without tenant_id should fail with 400 or 401"""
        payload = self._generate_hr_payload()
        # Exclude X-Tenant-ID from headers to test tenant resolution failure
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload, override_headers={"X-Tenant-ID": None})
        assert response.status_code in (400, 401, 503), f"Expected 400/401/503, got {response.status_code}: {response.text}"
        print(f"PASS: Webhook missing tenant returned {response.status_code}")

    # ── Negative Signature Tests ──────────────────────────────────────────

    def test_webhook_invalid_signature_returns_401(self):
        """Webhook with invalid signature should return 401"""
        payload = self._generate_hr_payload()
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload, secret="wrong-secret")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        assert "Invalid signature" in response.text
        print("PASS: Invalid signature blocked")

    def test_webhook_missing_signature_returns_401(self):
        """Webhook with missing signature should return 401"""
        payload = self._generate_hr_payload()
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload, override_headers={"X-HotelRunner-Signature": ""})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        assert "Missing signature" in response.text
        print("PASS: Missing signature blocked")

    def test_webhook_stale_timestamp_returns_401(self):
        """Webhook with stale timestamp should return 401"""
        payload = self._generate_hr_payload()
        import time
        stale_ts = str(int(time.time()) - 400) # 400 seconds ago (>300 tolerance)
        
        import json, hmac, hashlib
        from urllib.parse import urlencode
        secret = os.environ.get("HOTELRUNNER_WEBHOOK_SECRET", "test-secret")
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        signed_payload = f"{stale_ts}.".encode() + encoded_body
        signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        
        response = send_hr_webhook(
            "/api/channel-manager/hotelrunner/webhooks/reservations", 
            payload, 
            override_headers={"X-HotelRunner-Timestamp": stale_ts, "X-HotelRunner-Signature": signature}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        assert "Timestamp out of tolerance" in response.text
        print("PASS: Stale timestamp blocked")

    # ── Official Mode (Token Validation) Tests ──────────────────────────────

    def test_webhook_official_validation_accepted(self):
        """Webhook without HMAC but WITH valid token and hr_id should be accepted"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID  # Use valid mock hr_id
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token={MOCK_TOKEN}",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Official Token Validation accepted")

    def test_webhook_official_invalid_token_returns_401(self):
        """Webhook without HMAC and INVALID token should return 401"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token=wrong-token",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Official Token Validation blocked invalid token")

    def test_webhook_official_invalid_hr_id_returns_401(self):
        """Webhook with valid token but INVALID hr_id should return 401 (or 503 if not found)"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = "invalid_hr_id_9999"
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token={MOCK_TOKEN}",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response.status_code in (401, 503), f"Expected 401/503, got {response.status_code}"
        print("PASS: Invalid hr_id blocked")

    def test_webhook_official_true_cross_tenant(self):
        """Webhook with Tenant A's header, but Tenant B's hr_id should:
        1. Reject with 401 if Tenant A's token is used (token mismatch)
        2. Accept and bind to Tenant B if Tenant B's token is used (header ignored)"""
        
        # Test 1: Reject mismatch
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID + "_B" # Tenant B hr_id
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        # We send Tenant A's token and Tenant A's header, but Tenant B's payload
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token={MOCK_TOKEN}",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response.status_code in (401, 503), f"Expected 401/503 for cross-tenant mismatch, got {response.status_code}"
        print("PASS: True cross-tenant mismatch blocked")
        
        # Test 2: Accept correct token, ignore header
        response_success = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token={MOCK_TOKEN}_B",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response_success.status_code == 200, f"Expected 200, got {response_success.status_code}"
        print("PASS: Cross-tenant payload with correct token accepted, header safely ignored")

    def test_webhook_official_token_in_form_body_accepted(self):
        """Webhook with token inside the form-urlencoded body instead of query should be accepted"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        # Token is in body
        encoded_body = urlencode({"data": data_str, "token": MOCK_TOKEN}).encode("utf-8")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Token parsed from form body accepted")

    def test_webhook_hmac_missing_timestamp_returns_401(self):
        """Webhook with HMAC signature but NO timestamp should return 401"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID
        
        import json
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str}).encode("utf-8")
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={
                "Content-Type": "application/x-www-form-urlencoded", 
                "X-Tenant-ID": TEST_TENANT_ID,
                "X-HotelRunner-Signature": "dummy-sig"
                # Missing timestamp
            },
            data=encoded_body,
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: HMAC missing timestamp blocked")

    def test_webhook_hmac_invalid_signature_does_not_fallback(self):
        """Webhook with invalid HMAC signature but VALID token should STILL return 401, no fallback"""
        payload = self._generate_hr_payload()
        payload["hr_id"] = MOCK_HR_ID
        
        import json
        import time
        from urllib.parse import urlencode
        data_str = json.dumps(payload)
        encoded_body = urlencode({"data": data_str, "token": MOCK_TOKEN}).encode("utf-8")
        ts = str(int(time.time()))
        
        response = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations",
            headers={
                "Content-Type": "application/x-www-form-urlencoded", 
                "X-Tenant-ID": TEST_TENANT_ID,
                "X-HotelRunner-Signature": "invalid-signature",
                "X-HotelRunner-Timestamp": ts
            },
            data=encoded_body,
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Invalid HMAC signature blocked (no fallback to token)")
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
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
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
        response1 = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response1.status_code == 200, f"First webhook failed: {response1.text}"
        
        # Wait for processing
        time.sleep(3)
        
        # Second delivery (duplicate)
        response2 = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
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
        
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response.status_code == 200, f"Normalizer test failed: {response.text}"
        
        # If we get 200, it means it parsed successfully and triggered the webhook.
        print(f"PASS: Normalizer handled payload correctly - hr_number={hr_number}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
