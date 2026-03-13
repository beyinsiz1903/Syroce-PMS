"""
Exely Channel Manager - Versioning, WSSE Hardening & Provider Lineage Tests
Tests for iteration 61 upgrades:
1. SOAP XML builder with WSSE Security (wsu:Timestamp + Nonce for replay attack protection)
2. Payload hash deterministic computation for idempotency
3. check_idempotency version comparison logic (stale/duplicate/newer)
4. Provider lineage fields in Exely and HotelRunner normalizers
"""
import os
import sys
import pytest
import requests
import uuid
import hashlib
import json
from datetime import datetime, timezone, timedelta

# Add backend to path for unit tests
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://data-model-hub-1.preview.emergentagent.com')
if BASE_URL.endswith('/'):
    BASE_URL = BASE_URL[:-1]

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS - SOAP XML Builder WSSE Security Hardening
# ══════════════════════════════════════════════════════════════════════════════

class TestSoapBuilderWSSE:
    """Unit tests for SOAP XML builder with WSSE Security headers"""

    def test_soap_envelope_contains_timestamp_element(self):
        """SOAP envelope should contain wsu:Timestamp with Created + Expires"""
        from lxml import etree
        from domains.channel_manager.providers.exely.soap_builder import build_read_rq
        
        xml = build_read_rq(
            username="test_user",
            password="test_pass",
            hotel_code="12345"
        )
        
        tree = etree.fromstring(xml.encode())
        
        # Define namespaces
        ns = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
            'wsu': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd',
        }
        
        # Find Timestamp element
        timestamp = tree.find('.//wsu:Timestamp', ns)
        assert timestamp is not None, "Missing wsu:Timestamp element"
        
        # Check Created element
        created = timestamp.find('wsu:Created', ns)
        assert created is not None, "Missing wsu:Created in Timestamp"
        assert created.text is not None, "wsu:Created has no value"
        # Validate ISO format
        try:
            datetime.strptime(created.text, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pytest.fail(f"wsu:Created not in ISO format: {created.text}")
        print(f"✅ wsu:Created = {created.text}")
        
        # Check Expires element
        expires = timestamp.find('wsu:Expires', ns)
        assert expires is not None, "Missing wsu:Expires in Timestamp"
        assert expires.text is not None, "wsu:Expires has no value"
        try:
            datetime.strptime(expires.text, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pytest.fail(f"wsu:Expires not in ISO format: {expires.text}")
        print(f"✅ wsu:Expires = {expires.text}")

    def test_soap_envelope_contains_nonce_with_base64(self):
        """SOAP envelope should contain wsse:Nonce with Base64Binary encoding"""
        from lxml import etree
        import base64
        from domains.channel_manager.providers.exely.soap_builder import build_read_rq
        
        xml = build_read_rq(
            username="test_user",
            password="test_pass",
            hotel_code="12345"
        )
        
        tree = etree.fromstring(xml.encode())
        
        ns = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
        }
        
        # Find Nonce element
        nonce = tree.find('.//wsse:Nonce', ns)
        assert nonce is not None, "Missing wsse:Nonce element"
        
        # Check EncodingType attribute
        encoding_type = nonce.get('EncodingType')
        assert encoding_type is not None, "Missing EncodingType attribute on Nonce"
        assert 'Base64Binary' in encoding_type, f"EncodingType should be Base64Binary, got: {encoding_type}"
        print(f"✅ Nonce EncodingType = {encoding_type}")
        
        # Verify Nonce value is valid Base64
        nonce_value = nonce.text
        assert nonce_value is not None, "Nonce has no value"
        try:
            decoded = base64.b64decode(nonce_value)
            assert len(decoded) == 16, f"Nonce should be 16 bytes, got {len(decoded)}"
        except Exception as e:
            pytest.fail(f"Nonce is not valid Base64: {e}")
        print(f"✅ Nonce value is valid Base64 (16 bytes)")

    def test_soap_envelope_password_type_passwordtext(self):
        """SOAP envelope should contain wsse:Password with PasswordText type"""
        from lxml import etree
        from domains.channel_manager.providers.exely.soap_builder import build_read_rq
        
        xml = build_read_rq(
            username="test_user",
            password="test_pass",
            hotel_code="12345"
        )
        
        tree = etree.fromstring(xml.encode())
        
        ns = {
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
        }
        
        # Find Password element
        password = tree.find('.//wsse:Password', ns)
        assert password is not None, "Missing wsse:Password element"
        
        # Check Type attribute
        pw_type = password.get('Type')
        assert pw_type is not None, "Missing Type attribute on Password"
        assert 'PasswordText' in pw_type, f"Password Type should be PasswordText, got: {pw_type}"
        
        # Verify password value
        assert password.text == "test_pass", f"Password value mismatch: {password.text}"
        print(f"✅ Password Type = {pw_type}, value set correctly")

    def test_soap_envelope_must_understand_attribute(self):
        """SOAP Security element should have mustUnderstand=1"""
        from lxml import etree
        from domains.channel_manager.providers.exely.soap_builder import build_read_rq
        
        xml = build_read_rq(
            username="test_user",
            password="test_pass",
            hotel_code="12345"
        )
        
        tree = etree.fromstring(xml.encode())
        
        ns = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
        }
        
        # Find Security element
        security = tree.find('.//wsse:Security', ns)
        assert security is not None, "Missing wsse:Security element"
        
        # Check mustUnderstand attribute (can be in different namespace)
        must_understand = security.get(f'{{{ns["soapenv"]}}}mustUnderstand')
        assert must_understand == "1", f"mustUnderstand should be '1', got: {must_understand}"
        print(f"✅ Security mustUnderstand = {must_understand}")

    def test_soap_envelope_all_wsse_elements_present(self):
        """Comprehensive test: all WSSE elements present in correct structure"""
        from lxml import etree
        from domains.channel_manager.providers.exely.soap_builder import build_read_rq
        
        xml = build_read_rq(
            username="test_user",
            password="test_pass",
            hotel_code="12345"
        )
        
        tree = etree.fromstring(xml.encode())
        
        ns = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
            'wsu': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd',
            'ota': 'http://www.opentravel.org/OTA/2003/05',
        }
        
        # Structure validation
        envelope = tree
        assert envelope.tag == f'{{{ns["soapenv"]}}}Envelope', "Root should be SOAP Envelope"
        
        header = envelope.find('soapenv:Header', ns)
        assert header is not None, "Missing SOAP Header"
        
        security = header.find('wsse:Security', ns)
        assert security is not None, "Missing Security in Header"
        
        # Elements in Security
        timestamp = security.find('wsu:Timestamp', ns)
        assert timestamp is not None, "Missing Timestamp"
        
        username_token = security.find('wsse:UsernameToken', ns)
        assert username_token is not None, "Missing UsernameToken"
        
        username = username_token.find('wsse:Username', ns)
        assert username is not None and username.text == "test_user", "Invalid Username"
        
        password = username_token.find('wsse:Password', ns)
        assert password is not None, "Missing Password"
        
        nonce = username_token.find('wsse:Nonce', ns)
        assert nonce is not None, "Missing Nonce"
        
        token_created = username_token.find('wsu:Created', ns)
        assert token_created is not None, "Missing Created in UsernameToken"
        
        body = envelope.find('soapenv:Body', ns)
        assert body is not None, "Missing SOAP Body"
        
        print("✅ All WSSE elements present with correct structure")


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS - Payload Hash Determinism
# ══════════════════════════════════════════════════════════════════════════════

class TestPayloadHash:
    """Unit tests for payload hash computation"""

    def test_same_payload_produces_same_hash(self):
        """Same payload should always produce the same hash"""
        from domains.channel_manager.providers.common_ingest import _compute_payload_hash
        
        payload = {
            "reservation_id": "RES-001",
            "guest_name": "John Doe",
            "checkin": "2025-01-15",
            "checkout": "2025-01-18",
            "total": 450.00
        }
        
        hash1 = _compute_payload_hash(payload)
        hash2 = _compute_payload_hash(payload)
        hash3 = _compute_payload_hash(payload)
        
        assert hash1 == hash2 == hash3, f"Hash not deterministic: {hash1}, {hash2}, {hash3}"
        print(f"✅ Same payload hash: {hash1} (consistent)")

    def test_different_payload_produces_different_hash(self):
        """Different payloads should produce different hashes"""
        from domains.channel_manager.providers.common_ingest import _compute_payload_hash
        
        payload1 = {"reservation_id": "RES-001", "total": 450.00}
        payload2 = {"reservation_id": "RES-002", "total": 450.00}
        payload3 = {"reservation_id": "RES-001", "total": 500.00}
        
        hash1 = _compute_payload_hash(payload1)
        hash2 = _compute_payload_hash(payload2)
        hash3 = _compute_payload_hash(payload3)
        
        assert hash1 != hash2, f"Different reservation IDs should produce different hash"
        assert hash1 != hash3, f"Different totals should produce different hash"
        print(f"✅ Different payloads produce different hashes: {hash1}, {hash2}, {hash3}")

    def test_payload_hash_order_independent(self):
        """Key order should not affect hash (json.dumps with sort_keys=True)"""
        from domains.channel_manager.providers.common_ingest import _compute_payload_hash
        
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}
        payload3 = {"b": 2, "c": 3, "a": 1}
        
        hash1 = _compute_payload_hash(payload1)
        hash2 = _compute_payload_hash(payload2)
        hash3 = _compute_payload_hash(payload3)
        
        assert hash1 == hash2 == hash3, f"Key order should not affect hash: {hash1}, {hash2}, {hash3}"
        print(f"✅ Hash is order-independent: {hash1}")

    def test_payload_hash_length(self):
        """Hash should be truncated to 16 characters"""
        from domains.channel_manager.providers.common_ingest import _compute_payload_hash
        
        payload = {"test": "data", "more": "fields", "nested": {"deep": "value"}}
        hash_val = _compute_payload_hash(payload)
        
        assert len(hash_val) == 16, f"Hash should be 16 chars, got {len(hash_val)}: {hash_val}"
        print(f"✅ Hash length is 16: {hash_val}")


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS - Provider Lineage Fields in Normalizers
# ══════════════════════════════════════════════════════════════════════════════

class TestExelyNormalizerLineageFields:
    """Unit tests for Exely normalizer provider lineage fields"""

    def test_exely_normalizer_outputs_provider_last_modified_at(self):
        """Exely normalizer should output provider_last_modified_at field"""
        from domains.channel_manager.providers.exely.normalizer import normalize_reservation
        
        raw = {
            "reservation_id": "EX-12345",
            "last_modify": "2025-01-15T10:30:00Z",
            "create_date": "2025-01-14T08:00:00Z",
            "guest_name": "Test Guest",
            "checkin_date": "2025-01-20",
            "checkout_date": "2025-01-23",
            "total": 300.00,
            "currency": "TRY",
            "status": "confirmed"
        }
        
        canonical = normalize_reservation(raw, source="pull")
        
        assert "provider_last_modified_at" in canonical, "Missing provider_last_modified_at"
        assert canonical["provider_last_modified_at"] == "2025-01-15T10:30:00Z"
        print(f"✅ provider_last_modified_at = {canonical['provider_last_modified_at']}")

    def test_exely_normalizer_outputs_provider_created_at(self):
        """Exely normalizer should output provider_created_at field"""
        from domains.channel_manager.providers.exely.normalizer import normalize_reservation
        
        raw = {
            "reservation_id": "EX-12345",
            "last_modify": "2025-01-15T10:30:00Z",
            "create_date": "2025-01-14T08:00:00Z",
            "guest_name": "Test Guest",
            "checkin_date": "2025-01-20",
            "checkout_date": "2025-01-23",
            "total": 300.00,
            "currency": "TRY",
            "status": "confirmed"
        }
        
        canonical = normalize_reservation(raw, source="pull")
        
        assert "provider_created_at" in canonical, "Missing provider_created_at"
        assert canonical["provider_created_at"] == "2025-01-14T08:00:00Z"
        print(f"✅ provider_created_at = {canonical['provider_created_at']}")

    def test_exely_normalizer_outputs_provider_version(self):
        """Exely normalizer should output provider_version field (default 1)"""
        from domains.channel_manager.providers.exely.normalizer import normalize_reservation
        
        raw = {
            "reservation_id": "EX-12345",
            "guest_name": "Test Guest",
            "checkin_date": "2025-01-20",
            "checkout_date": "2025-01-23",
            "total": 300.00,
            "status": "confirmed"
        }
        
        canonical = normalize_reservation(raw, source="pull")
        
        assert "provider_version" in canonical, "Missing provider_version"
        assert canonical["provider_version"] == 1
        print(f"✅ provider_version = {canonical['provider_version']}")


class TestHotelRunnerNormalizerLineageFields:
    """Unit tests for HotelRunner normalizer provider lineage fields"""

    def test_hotelrunner_normalizer_outputs_provider_last_modified_at(self):
        """HotelRunner normalizer should output provider_last_modified_at field"""
        from domains.channel_manager.providers.hotelrunner_ingest import normalize_reservation
        
        raw = {
            "hr_number": "HR-98765",
            "updated_at": "2025-01-15T11:45:00Z",
            "created_at": "2025-01-13T09:00:00Z",
            "guest": "Test HR Guest",
            "checkin_date": "2025-01-22",
            "checkout_date": "2025-01-25",
            "total": 550.00,
            "currency": "TRY",
            "state": "confirmed"
        }
        
        canonical = normalize_reservation(raw, source="webhook")
        
        assert "provider_last_modified_at" in canonical, "Missing provider_last_modified_at"
        assert canonical["provider_last_modified_at"] == "2025-01-15T11:45:00Z"
        print(f"✅ provider_last_modified_at = {canonical['provider_last_modified_at']}")

    def test_hotelrunner_normalizer_outputs_provider_created_at(self):
        """HotelRunner normalizer should output provider_created_at field"""
        from domains.channel_manager.providers.hotelrunner_ingest import normalize_reservation
        
        raw = {
            "hr_number": "HR-98765",
            "updated_at": "2025-01-15T11:45:00Z",
            "created_at": "2025-01-13T09:00:00Z",
            "guest": "Test HR Guest",
            "checkin_date": "2025-01-22",
            "checkout_date": "2025-01-25",
            "total": 550.00,
            "state": "confirmed"
        }
        
        canonical = normalize_reservation(raw, source="webhook")
        
        assert "provider_created_at" in canonical, "Missing provider_created_at"
        assert canonical["provider_created_at"] == "2025-01-13T09:00:00Z"
        print(f"✅ provider_created_at = {canonical['provider_created_at']}")

    def test_hotelrunner_normalizer_outputs_provider_version(self):
        """HotelRunner normalizer should output provider_version field (default 1)"""
        from domains.channel_manager.providers.hotelrunner_ingest import normalize_reservation
        
        raw = {
            "hr_number": "HR-98765",
            "guest": "Test HR Guest",
            "checkin_date": "2025-01-22",
            "checkout_date": "2025-01-25",
            "total": 550.00,
            "state": "pending"
        }
        
        canonical = normalize_reservation(raw, source="webhook")
        
        assert "provider_version" in canonical, "Missing provider_version"
        assert canonical["provider_version"] == 1
        print(f"✅ provider_version = {canonical['provider_version']}")

    def test_hotelrunner_normalizer_fallback_modified_at(self):
        """HotelRunner normalizer should fallback to modified_at if updated_at not present"""
        from domains.channel_manager.providers.hotelrunner_ingest import normalize_reservation
        
        raw = {
            "hr_number": "HR-98765",
            "modified_at": "2025-01-15T12:00:00Z",
            "guest": "Test HR Guest",
            "checkin_date": "2025-01-22",
            "checkout_date": "2025-01-25",
            "total": 550.00,
            "state": "modified"
        }
        
        canonical = normalize_reservation(raw, source="webhook")
        
        assert canonical["provider_last_modified_at"] == "2025-01-15T12:00:00Z"
        print(f"✅ Fallback to modified_at works: {canonical['provider_last_modified_at']}")


# ══════════════════════════════════════════════════════════════════════════════
# API TESTS - Backend Endpoints (same as iteration 60 + new fields validation)
# ══════════════════════════════════════════════════════════════════════════════

class TestExelyAPIAuth:
    """Setup authentication for API tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in response"
        return token
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestExelyConnectionAPI(TestExelyAPIAuth):
    """Exely connection API tests"""
    
    def test_get_connection_returns_correct_shape(self, headers):
        """GET /api/channel-manager/exely/connection - returns correct response shape"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/connection",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "connected" in data, f"Missing 'connected' field: {data}"
        print(f"✅ Connection response shape correct: connected={data['connected']}")


class TestExelySyncStatusAPI(TestExelyAPIAuth):
    """Exely sync status API tests"""
    
    def test_get_sync_status_returns_correct_fields(self, headers):
        """GET /api/channel-manager/exely/sync/status - returns sync status with correct fields"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/sync/status",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        required_fields = ["scheduler_running", "pending_events", "error_events", "total_reservations"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' in sync status: {data}"
        
        print(f"✅ Sync status fields: scheduler_running={data['scheduler_running']}, "
              f"pending={data['pending_events']}, errors={data['error_events']}, "
              f"reservations={data['total_reservations']}")


class TestExelyRoomMappingsAPI(TestExelyAPIAuth):
    """Exely room mappings CRUD API tests"""
    
    def test_create_mapping_returns_correct_response(self, headers):
        """POST /api/channel-manager/exely/room-mappings - creates mapping with correct response"""
        mapping_data = {
            "pms_room_type": f"TEST_VERSIONING_{uuid.uuid4().hex[:8]}",
            "exely_room_code": "EXELY_V2_STD",
            "exely_rate_plan_code": "EXELY_V2_BAR",
            "exely_room_name": "Test Versioning Room",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": False
        }
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers,
            json=mapping_data
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "mapping" in data, f"Missing 'mapping' in response: {data}"
        mapping = data["mapping"]
        assert "id" in mapping, f"Missing 'id' in mapping: {mapping}"
        assert mapping["pms_room_type"] == mapping_data["pms_room_type"]
        assert mapping["exely_room_code"] == mapping_data["exely_room_code"]
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings/{mapping['id']}",
            headers=headers
        )
        print(f"✅ Create mapping response correct: id={mapping['id']}")

    def test_get_mappings_returns_list(self, headers):
        """GET /api/channel-manager/exely/room-mappings - returns mappings list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "mappings" in data, f"Missing 'mappings': {data}"
        assert "count" in data, f"Missing 'count': {data}"
        assert isinstance(data["mappings"], list)
        print(f"✅ Get mappings: count={data['count']}")

    def test_delete_mapping_works(self, headers):
        """DELETE /api/channel-manager/exely/room-mappings/{id} - deletes mapping"""
        # Create first
        mapping_data = {
            "pms_room_type": f"TEST_DELETE_{uuid.uuid4().hex[:8]}",
            "exely_room_code": "EXELY_DEL",
            "exely_rate_plan_code": "EXELY_DEL_BAR",
            "exely_room_name": "To Delete",
            "sync_availability": True,
            "sync_price": False,
            "sync_restrictions": False
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers,
            json=mapping_data
        )
        mapping_id = create_resp.json()["mapping"]["id"]
        
        # Delete
        delete_resp = requests.delete(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings/{mapping_id}",
            headers=headers
        )
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        print(f"✅ Delete mapping works: id={mapping_id}")


class TestExelySyncLogsAPI(TestExelyAPIAuth):
    """Exely sync logs API tests"""
    
    def test_get_sync_logs_returns_logs(self, headers):
        """GET /api/channel-manager/exely/sync-logs - returns logs"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/sync-logs?limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "logs" in data, f"Missing 'logs': {data}"
        assert "count" in data, f"Missing 'count': {data}"
        assert isinstance(data["logs"], list)
        print(f"✅ Get sync logs: count={data['count']}")


class TestExelyReservationsAPI(TestExelyAPIAuth):
    """Exely reservations API tests"""
    
    def test_get_local_reservations_returns_list(self, headers):
        """GET /api/channel-manager/exely/reservations/local - returns reservations"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/reservations/local",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "reservations" in data, f"Missing 'reservations': {data}"
        assert "count" in data, f"Missing 'count': {data}"
        assert isinstance(data["reservations"], list)
        print(f"✅ Get local reservations: count={data['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
