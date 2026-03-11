"""
Production Hardening Phase 1-8 Test Suite.

Tests all new functionality:
- Phase 1: Sandbox Validation Service
- Phase 2: Provider Adapters (Inventory + Rate)
- Phase 3: AES-256-GCM Encryption
- Phase 4: RBAC Enforcement
- Phase 5: Reconciliation Health Score
- Phase 6: Scheduler Metrics
- Phase 7: Event-Driven Sync Hardening
- Phase 8: Test Suite Stability
"""
import asyncio
import os
import sys
import uuid
import pytest
import requests

# ── Setup ──
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

BASE_URL = os.environ.get("TEST_API_URL", "")
if not BASE_URL:
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1]

CONNECTOR_ID = ""
PROPERTY_ID = "prop-test-hardening"
TENANT_ID = ""
AUTH_TOKEN = ""


@pytest.fixture(scope="session", autouse=True)
def setup_session():
    global TENANT_ID, AUTH_TOKEN, CONNECTOR_ID
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    data = login_resp.json()
    AUTH_TOKEN = data["access_token"]
    TENANT_ID = data["user"]["tenant_id"]

    # Seed connector
    headers = _headers()
    resp = requests.post(
        f"{BASE_URL}/api/channel-manager/v2/connectors",
        json={
            "display_name": f"Hardening Test {uuid.uuid4().hex[:6]}",
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "credentials": {"token": "test-token", "hr_id": "12345"},
        },
        headers=headers,
    )
    if resp.status_code == 200:
        c = resp.json().get("connector", {})
        CONNECTOR_ID = c.get("id", "")
        # Activate connector for scheduler tests
        requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/activate",
            headers=headers,
        )

    if not CONNECTOR_ID:
        # Fallback: list connectors and pick any active one
        list_resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=headers,
        )
        if list_resp.status_code == 200:
            data = list_resp.json()
            connectors = data.get("connectors", data) if isinstance(data, dict) else data
            if isinstance(connectors, list) and connectors:
                CONNECTOR_ID = connectors[0].get("id", "")

    assert CONNECTOR_ID, "Failed to create or find a test connector"
    yield


def _headers():
    return {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}


# ─── Phase 3: AES-256-GCM Encryption Tests ───────────────────────────

class TestAES256GCMEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        plaintext = "my-secret-token-12345"
        ct = enc.encrypt(plaintext)
        assert ct.startswith("aes256gcm:")
        pt = enc.decrypt(ct)
        assert pt == plaintext

    def test_different_ciphertexts_for_same_plaintext(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        ct1 = enc.encrypt("same-secret")
        ct2 = enc.encrypt("same-secret")
        assert ct1 != ct2  # Different IVs

    def test_tamper_detection(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        ct = enc.encrypt("secret")
        # Tamper with ciphertext
        raw = ct[len("aes256gcm:"):]
        import base64
        decoded = bytearray(base64.b64decode(raw))
        decoded[15] ^= 0xFF  # Flip a byte
        tampered = "aes256gcm:" + base64.b64encode(bytes(decoded)).decode()
        with pytest.raises(Exception):
            enc.decrypt(tampered)

    def test_credential_roundtrip(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        creds = {"token": "abc123", "hr_id": "hotel42", "secret": "x"}
        encrypted = enc.encrypt_credentials(creds)
        for v in encrypted.values():
            assert enc.is_aes_encrypted(v)
        decrypted = enc.decrypt_credentials(encrypted)
        assert decrypted == creds

    def test_is_aes_encrypted(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        assert enc.is_aes_encrypted("aes256gcm:abc123")
        assert not enc.is_aes_encrypted("plaintext")
        assert not enc.is_aes_encrypted("")

    def test_key_management_service(self):
        from channel_manager.infrastructure.encryption_service import KeyManagementService
        kms1 = KeyManagementService("key-A")
        kms2 = KeyManagementService("key-B")
        assert kms1.key != kms2.key
        assert len(kms1.key) == 32  # SHA-256 output

    def test_migration_from_legacy(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        # Simulate legacy XOR ciphertext
        legacy_creds = {"token": "plaintext-token", "hr_id": "plain-id"}
        migrated = enc.migrate_credentials(legacy_creds)
        for v in migrated.values():
            assert enc.is_aes_encrypted(v)
        decrypted = enc.decrypt_credentials(migrated)
        assert decrypted["token"] == "plaintext-token"


# ─── Phase 4: RBAC Tests ─────────────────────────────────────────────

class TestRBACEnforcement:
    def test_admin_can_access_credentials(self):
        """Admin role should be allowed for credential operations."""
        resp = requests.put(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/secure",
            json={"credentials": {"token": "updated-token", "hr_id": "99999"}},
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_rotate(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/rotate",
            json={"credentials": {"token": "rotated-token", "hr_id": "88888"}},
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_view_masked(self):
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/masked",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "credentials" in data
        assert data.get("algorithm") == "AES-256-GCM"

    def test_credential_migrate(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/migrate",
            headers=_headers(),
        )
        assert resp.status_code == 200


# ─── Phase 2: Provider Adapter Tests ─────────────────────────────────

class TestProviderAdapters:
    def test_inventory_push_endpoint(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/providers/inventory/push",
            json={
                "connector_id": CONNECTOR_ID,
                "updates": [{"room_type_code": "TEST", "date_start": "2099-01-01", "date_end": "2099-01-01", "available": 0}],
                "environment": "sandbox",
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "correlation_id" in data
        assert "latency_ms" in data

    def test_rate_push_endpoint(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/providers/rates/push",
            json={
                "connector_id": CONNECTOR_ID,
                "updates": [{"room_type_code": "TEST", "rate_plan_code": "RP", "date_start": "2099-01-01", "date_end": "2099-01-01", "amount_after_tax": 100, "currency": "TRY"}],
                "environment": "sandbox",
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "correlation_id" in data

    def test_push_connector_not_found(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/providers/inventory/push",
            json={
                "connector_id": "nonexistent-connector",
                "updates": [],
                "environment": "sandbox",
            },
            headers=_headers(),
        )
        assert resp.status_code == 404


# ─── Phase 1: Sandbox Validation Tests ────────────────────────────────

class TestSandboxValidation:
    def test_sandbox_validate_endpoint(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/validate/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_checks" in data
        assert "passed_checks" in data
        assert "failed_checks" in data
        assert "blocker_issues" in data
        assert "production_recommendation" in data
        assert "checks" in data
        assert data["total_checks"] > 0

    def test_sandbox_validate_nonexistent(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/validate/nonexistent-id",
            headers=_headers(),
        )
        assert resp.status_code == 404


# ─── Phase 5: Reconciliation Health Score Tests ──────────────────────

class TestReconciliationHealthScore:
    def test_health_score_endpoint(self):
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/health/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert "status" in data
        assert "open_issues" in data
        assert "by_severity" in data
        assert "by_type" in data
        assert 0 <= data["health_score"] <= 100
        assert data["status"] in ("healthy", "degraded", "critical")


# ─── Phase 6 & 7: Scheduler & Event Sync Hardening ──────────────────

class TestSchedulerAndEventSync:
    def test_scheduler_returns_metrics(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/scheduler/run/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        # Connector may be skipped (not active) or return metrics
        if data.get("skipped"):
            assert "reason" in data
        else:
            assert "metrics" in data
            assert "stale_jobs" in data["metrics"]
            assert "requeued_jobs" in data["metrics"]

    def test_event_sync_booking_created(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "booking_created",
                "payload": {"property_id": PROPERTY_ID, "room_id": "R101"},
            },
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_event_sync_rate_changed(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "rate_changed",
                "payload": {"property_id": PROPERTY_ID, "rate_plan_id": "RP1"},
            },
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_event_batch_sync(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync/batch",
            json={
                "events": [
                    {"event_type": "booking_modified", "payload": {"property_id": PROPERTY_ID}},
                    {"event_type": "room_blocked", "payload": {"property_id": PROPERTY_ID}},
                ],
            },
            headers=_headers(),
        )
        assert resp.status_code == 200


# ─── Phase 8: Test Stability (Purely Synthetic) ──────────────────────

class TestSuiteStability:
    def test_all_mapping_engine_tests_exist(self):
        """Verify the mapping engine test file is importable."""
        import tests.test_mapping_engine
        assert hasattr(tests.test_mapping_engine, "test_detect_missing_room_type")

    def test_encryption_module_importable(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService, KeyManagementService
        assert EncryptionService is not None
        assert KeyManagementService is not None

    def test_rbac_module_importable(self):
        from channel_manager.infrastructure.rbac import enforce_credential_access
        assert enforce_credential_access is not None

    def test_sandbox_service_importable(self):
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        assert SandboxValidationService is not None

    def test_provider_adapters_importable(self):
        from channel_manager.application.provider_adapters import InventoryProviderAdapter, RateProviderAdapter
        assert InventoryProviderAdapter is not None
        assert RateProviderAdapter is not None
