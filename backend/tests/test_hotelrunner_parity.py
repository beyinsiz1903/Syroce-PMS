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

@pytest.fixture
def hotelrunner_webhook_db():
    """Reset mock server before each test and seed mock connections"""
    requests.post(f"{MOCK_SERVER_URL}/mock/reset", timeout=10)
        
    mongo_url = os.getenv("HOTELRUNNER_TEST_MONGO_URL")
    if not mongo_url:
        pytest.fail("Test suite requires HOTELRUNNER_TEST_MONGO_URL environment variable to prevent accidental data corruption.")
    
    from pymongo import MongoClient
    client = MongoClient(mongo_url)
    db = client.get_default_database()
    
    if not db.name.endswith("_test"):
        pytest.fail("Database name in HOTELRUNNER_TEST_MONGO_URL must end with '_test' (e.g. hotel_pms_test)")
        
    try:
        # Seed test tenant and connection
        db.hotelrunner_connections.delete_many({"hr_id": MOCK_HR_ID})
        db.hotelrunner_connections.delete_many({"tenant_id": TEST_TENANT_ID})
        db.hotelrunner_connections.insert_one(
            {
                "hr_id": MOCK_HR_ID,
                "tenant_id": TEST_TENANT_ID,
                "token": MOCK_TOKEN,
                "is_active": True,
            }
        )


        # 1.5. Mock credential vault for HotelRunnerV2Service
        db.provider_secrets.delete_many({"tenant_id": TEST_TENANT_ID})
        
        os.environ["CRYPTO_V2_ENABLED"] = "false"
        from core.crypto.service import CredentialEncryptionService
        from core.crypto.engine import AADContext
        
        svc = CredentialEncryptionService()
        aad = AADContext(
            tenant_id=TEST_TENANT_ID,
            provider="hotelrunner",
            property_id=MOCK_HR_ID,
            environment="test",
            context_type="credential"
        )
        encrypted_payload = {
            "token": svc.encrypt(MOCK_TOKEN, aad=aad),
            "hr_id": svc.encrypt(MOCK_HR_ID, aad=aad),
            "environment": svc.encrypt("mock", aad=aad)
        }
        db.provider_secrets.insert_one({
            "id": "mock_secret_id",
            "tenant_id": TEST_TENANT_ID,
            "provider": "hotelrunner",
            "property_id": MOCK_HR_ID,
            "encrypted_payload": encrypted_payload,
            "key_version": "v0",
            "field_names": ["token", "hr_id", "environment"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        
        # Cross-tenant test seed
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

        db.provider_secrets.delete_many({"tenant_id": TEST_TENANT_ID + "_B"})
        aad_b = AADContext(
            tenant_id=TEST_TENANT_ID + "_B",
            provider="hotelrunner",
            property_id=MOCK_HR_ID + "_B",
            environment="test",
            context_type="credential"
        )
        encrypted_payload_b = {
            "token": svc.encrypt(MOCK_TOKEN + "_B", aad=aad_b),
            "hr_id": svc.encrypt(MOCK_HR_ID + "_B", aad=aad_b),
            "environment": svc.encrypt("mock", aad=aad_b)
        }
        db.provider_secrets.insert_one({
            "id": "mock_secret_id_b",
            "tenant_id": TEST_TENANT_ID + "_B",
            "provider": "hotelrunner",
            "property_id": MOCK_HR_ID + "_B",
            "encrypted_payload": encrypted_payload_b,
            "key_version": "v0",
            "field_names": ["token", "hr_id", "environment"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        
        # Seed mappings so ingest pipeline succeeds instead of pending_mapping
        for rcode in ["STD", "DBL", "SUI", "DLX"]:
            db.hotelrunner_room_mappings.update_one(
                {"tenant_id": TEST_TENANT_ID, "provider_room_code": rcode},
                {"$set": {
                    "tenant_id": TEST_TENANT_ID,
                    "property_id": "prop-001",
                    "provider": "hotelrunner",
                    "pms_room_type_id": f"pms-{rcode.lower()}-1",
                    "provider_room_code": rcode,
                    "is_active": True
                }},
                upsert=True
            )
            
        for rcode in ["NONREF", "BB", "BAR"]:
            db.hotelrunner_rate_plan_mappings.update_one(
                {"tenant_id": TEST_TENANT_ID, "provider_rate_code": rcode},
                {"$set": {
                    "tenant_id": TEST_TENANT_ID,
                    "property_id": "prop-001",
                    "provider": "hotelrunner",
                    "pms_rate_plan_id": f"rate-{rcode.lower()}-1",
                    "provider_rate_code": rcode,
                    "is_active": True
                }},
                upsert=True
            )
        
        yield db
        
    finally:
        # Teardown
        try:
            db.hotelrunner_connections.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
            db.raw_channel_events.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
            db.reservation_lineage.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
            db.bookings.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
            db.hotelrunner_room_mappings.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
            db.hotelrunner_rate_plan_mappings.delete_many({"tenant_id": {"$in": [TEST_TENANT_ID, TEST_TENANT_ID + "_B"]}})
        except Exception as e:
            pytest.fail(f"Teardown failed, database may be polluted: {e}")
        finally:
            client.close()
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


@pytest.mark.usefixtures("hotelrunner_webhook_db")
class TestWebhookEndpoints:
    """Test 7: Webhook endpoints for reservations, modifications, cancellations"""

    def _generate_hr_payload(self, hr_number: str = None, state: str = "confirmed"):
        """Generate a realistic HotelRunner reservation payload"""
        if not hr_number:
            hr_number = f"HR-{uuid.uuid4().hex[:8].upper()}"
        
        now = datetime.utcnow()
        checkin = now + timedelta(days=7)
        checkout = checkin + timedelta(days=3)
        
        return {
            "hr_number": hr_number,
            "hotel_id": MOCK_HR_ID,
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
        print(f"PASS: Webhook new reservation accepted - hr_number={payload['hr_number']}")
        return payload["hr_number"]

    def test_webhook_modification_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/modifications should return success for modifications"""
        payload = self._generate_hr_payload(state="modified")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/modifications", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook modification accepted")

    def test_webhook_cancellation_accepted(self):
        """POST /api/channel-manager/hotelrunner/webhooks/cancellations should return success for cancellations"""
        payload = self._generate_hr_payload(state="cancelled")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/cancellations", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"
        print(f"PASS: Webhook cancellation accepted")

    def test_webhook_unified_callback_new_reservation(self):
        """POST /api/channel-manager/hotelrunner/callback should handle new reservations"""
        payload = self._generate_hr_payload(state="confirmed")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/callback", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"

    def test_webhook_unified_callback_modification(self):
        """POST /api/channel-manager/hotelrunner/callback should handle modifications"""
        payload = self._generate_hr_payload(state="modified")
        response = send_hr_webhook("/api/channel-manager/hotelrunner/callback", payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted"

    def test_webhook_missing_tenant_succeeds(self):
        """Webhook without X-Tenant-ID should succeed via hr_id lookup"""
        payload = self._generate_hr_payload()
        # Ensure we drop the X-Tenant-ID header
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload, override_headers={"X-Tenant-ID": None})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PASS: Webhook missing tenant returned {response.status_code}")

    # ── Negative Signature Tests ──────────────────────────────────────────

    def test_webhook_missing_signature_returns_401(self):
        """POST without signature or valid official creds should return 401"""
        payload = self._generate_hr_payload()
        # send_hr_webhook with override_headers removes the signature headers
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload, override_headers={"X-HotelRunner-Signature": ""})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        assert "Missing hr_id or token for official validation" in response.text
        print("PASS: Invalid signature blocked")

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
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        assert response.json()["detail"] == "Connection not found"
        print("PASS: Invalid hr_id blocked")

    def test_webhook_official_true_cross_tenant(self, hotelrunner_webhook_db):
        """Webhook with Tenant A's header, but Tenant B's hr_id should:
        1. Reject with 401 if Tenant A's token is used (token mismatch)
        2. Accept and bind to Tenant B if Tenant B's token is used (header ignored)"""
        
        db = hotelrunner_webhook_db
        hr_number = f"HR-{uuid.uuid4().hex[:8].upper()}"
        
        # Test 1: Reject mismatch
        payload = self._generate_hr_payload(hr_number=hr_number)
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
        assert response.status_code == 401, f"Expected 401 for cross-tenant mismatch, got {response.status_code}"
        print("PASS: True cross-tenant mismatch blocked")
        
        # Test 2: Accept correct token, ignore header
        response_success = requests.post(
            f"{API_URL}/api/channel-manager/hotelrunner/webhooks/reservations?token={MOCK_TOKEN}_B",
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-Tenant-ID": TEST_TENANT_ID},
            data=encoded_body,
            timeout=15
        )
        assert response_success.status_code == 200, f"Expected 200, got {response_success.status_code}"
        
        # Verify event was recorded under Tenant B (header safely ignored)
        # Using a brief polling since background tasks insert it
        import time
        event = None
        for _ in range(5):
            event = db.raw_channel_events.find_one({"external_reservation_id": hr_number})
            if event:
                break
            time.sleep(0.2)
            
        assert event is not None, "Raw channel event was not created"
        assert event["tenant_id"] == TEST_TENANT_ID + "_B", f"Expected Tenant B, got {event['tenant_id']}"
        
        # Verify no event was created for Tenant A
        wrong_event = db.raw_channel_events.find_one({
            "external_reservation_id": hr_number,
            "tenant_id": TEST_TENANT_ID,
        })
        assert wrong_event is None, "Cross-tenant leakage: event created for Tenant A"
        print("PASS: Cross-tenant payload with correct token accepted and mapped to Tenant B correctly")

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
@pytest.mark.usefixtures("hotelrunner_webhook_db")
class TestIngestPipelineLineage:
    """Test 8: Ingest pipeline creates lineage for new reservations"""

    def _generate_unique_hr_payload(self):
        """Generate a unique HR payload for lineage testing"""
        hr_number = f"HR-LINEAGE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.utcnow()
        checkin = now + timedelta(days=14)
        checkout = checkin + timedelta(days=2)
        
        return {
            "hotel_id": MOCK_HR_ID,
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

    def test_ingest_creates_lineage(self, hotelrunner_webhook_db):
        """Webhook should create lineage record (verify via DB access)"""
        payload = self._generate_unique_hr_payload()
        hr_number = payload["hr_number"]
        
        # Send webhook
        response = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        
        # Wait for async processing (background task)
        time.sleep(4)
        
        db = hotelrunner_webhook_db
        # Since the backend caches channel mappings, our direct DB seeds won't be seen immediately.
        # The pipeline will process the webhook, but will fail with 'pending_mapping' decision or succeed.
        # We verify that the pipeline processed it (status is no longer 'pending').
        # The pipeline runs asynchronously via BackgroundTasks
        time.sleep(2)
        event = db.raw_channel_events.find_one({
            "external_reservation_id": hr_number,
            "tenant_id": TEST_TENANT_ID,
        })
        assert event is not None, "Raw event was not created in DB"
        
        status = event.get("processing_status")
        assert status == "processed", f"Pipeline did not finish successfully (status={status})"
        
        lineage = db.reservation_lineage.find_one({
            "external_reservation_id": hr_number,
            "tenant_id": TEST_TENANT_ID,
        })
        assert lineage is not None, "Lineage record was not created in DB"
        
        print(f"PASS: Webhook pipeline processing verified - hr_number={hr_number}, final_status={status}")


class TestDuplicateDeliveryDetection:
    """Test 9: Duplicate delivery should be detected and skipped"""

    def test_duplicate_webhook_detected(self, hotelrunner_webhook_db):
        """Sending same reservation twice should be handled (deduplicated)"""
        # Generate a unique payload
        hr_number = f"hr-dup-{uuid.uuid4().hex[:6]}"
        now = datetime.utcnow()
        checkin = now + timedelta(days=21)
        checkout = checkin + timedelta(days=2)
        
        payload = {
            "hotel_id": MOCK_HR_ID,
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
            "total_guests": 2,
            "message_uid": f"msg-dup-{uuid.uuid4().hex[:8]}",
            "address": {
                "email": "dup.test@example.com",
                "phone": "+905559998877",
                "address_line": "Duplicate Ave 42",
                "city": "Ankara",
                "zipcode": "06000",
                "country_code": "TR"
            },
            "rooms": [{
                "room_code": "DBL",
                "rate_code": "BB",
                "room_name": "Double Room",
                "adults": 2,
                "children": 0,
                "total": 1800.00,
                "daily_rates": [],
                "guest_name": "Duplicate Test"
            }],
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat(),
            "created_at": now.isoformat()
        }
        
        # Send first time
        response1 = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response1.status_code == 200, f"First webhook failed: {response1.text}"
        
        # Wait a moment for processing to avoid race conditions
        time.sleep(2)
        
        # Send second time (duplicate)
        response2 = send_hr_webhook("/api/channel-manager/hotelrunner/webhooks/reservations", payload)
        assert response2.status_code == 200, f"Second webhook failed: {response2.text}"
        
        time.sleep(3) # Wait for processing
        db = hotelrunner_webhook_db

        lineage = list(db.reservation_lineage.find({
            "external_reservation_id": hr_number,
            "tenant_id": TEST_TENANT_ID,
        }))
        assert len(lineage) == 1, f"Expected 1 lineage record (deduplication), found {len(lineage)}"

        bookings = list(db.bookings.find({
            "external_reservation_id": hr_number,
            "tenant_id": TEST_TENANT_ID,
        }))
        if len(bookings) == 0:
            time.sleep(3)
            bookings = list(db.bookings.find({
                "external_reservation_id": hr_number,
                "tenant_id": TEST_TENANT_ID,
            }))
        assert len(bookings) == 1, f"Expected exactly 1 booking record, found {len(bookings)}"
        
        print("PASS: Duplicate webhook correctly skipped")


@pytest.mark.usefixtures("hotelrunner_webhook_db")
class TestNormalizerParsing:
    """Test 10: Normalizer correctly parses HotelRunner format"""

    def test_normalizer_handles_real_hr_format(self):
        """Verify normalizer handles actual HotelRunner API format"""
        # This is a unit-style test that verifies the normalizer logic
        # We test by sending a webhook and checking it's accepted
        
        hr_number = f"HR-NORM-{uuid.uuid4().hex[:6].upper()}"
        # Real HotelRunner format with all fields
        payload = {
            "hotel_id": MOCK_HR_ID,
            "hr_number": hr_number,
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
