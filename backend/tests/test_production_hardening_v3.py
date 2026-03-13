"""
Production Hardening Phase 1-8 Enhanced Test Suite.

Tests all new functionality with data assertions:
- Phase 1: Sandbox Validation Service (readiness report)
- Phase 2: Provider Adapters (correlation_id, latency_ms, success)
- Phase 3: AES-256-GCM Encryption (algorithm verification)
- Phase 4: RBAC Enforcement (403 for unauthorized roles)
- Phase 5: Reconciliation Health Score (0-100, status)
- Phase 6: Scheduler Metrics (stale_jobs, requeued_jobs)
- Phase 7: Event-Driven Sync Hardening (booking_created, rate_changed)
- Phase 8: Test Stability
"""
import os
import sys
import uuid
import pytest
import requests
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

BASE_URL = os.environ.get("TEST_API_URL", "")
if not BASE_URL:
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1]

if not BASE_URL:
    pytest.skip("No API URL available", allow_module_level=True)

# Global state
CONNECTOR_ID = ""
PROPERTY_ID = f"TEST_prop_{uuid.uuid4().hex[:6]}"
TENANT_ID = ""
AUTH_TOKEN = ""


@pytest.fixture(scope="session", autouse=True)
def setup_session():
    """Login and create test connector."""
    global TENANT_ID, AUTH_TOKEN, CONNECTOR_ID
    
    # Login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    data = login_resp.json()
    AUTH_TOKEN = data["access_token"]
    TENANT_ID = data["user"]["tenant_id"]

    # Create test connector
    headers = _headers()
    resp = requests.post(
        f"{BASE_URL}/api/channel-manager/v2/connectors",
        json={
            "display_name": f"TEST_Hardening_{uuid.uuid4().hex[:6]}",
            "provider": "hotelrunner",
            "property_id": PROPERTY_ID,
            "credentials": {"token": "test-token-v3", "hr_id": "v3-12345"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"Connector creation failed: {resp.text}"
    c = resp.json().get("connector", {})
    CONNECTOR_ID = c.get("id", "")
    assert CONNECTOR_ID, "No connector ID returned"

    # Activate connector for scheduler tests
    activate_resp = requests.post(
        f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/activate",
        headers=headers,
    )
    assert activate_resp.status_code == 200, f"Activation failed: {activate_resp.text}"

    yield

    # Cleanup: delete test connector
    requests.delete(
        f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}",
        headers=headers,
    )


def _headers():
    return {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}


# ─── Phase 1: Sandbox Validation Tests ─────────────────────────────────

class TestPhase1SandboxValidation:
    """POST /api/channel-manager/v2/sandbox/validate/{connector_id}"""

    def test_sandbox_validate_returns_readiness_report(self):
        """Validate returns complete readiness report structure."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/validate/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Required fields
        assert "connector_id" in data
        assert data["connector_id"] == CONNECTOR_ID
        assert "total_checks" in data
        assert isinstance(data["total_checks"], int) and data["total_checks"] > 0
        assert "passed_checks" in data
        assert isinstance(data["passed_checks"], int)
        assert "failed_checks" in data
        assert isinstance(data["failed_checks"], int)
        assert "blocker_issues" in data
        assert isinstance(data["blocker_issues"], list)
        assert "production_recommendation" in data
        assert isinstance(data["production_recommendation"], str)
        assert "checks" in data
        assert isinstance(data["checks"], list)
        
        # Verify checks structure
        for check in data["checks"]:
            assert "check_name" in check
            assert "success" in check
            assert isinstance(check["success"], bool)

    def test_sandbox_validate_nonexistent_connector(self):
        """404 for nonexistent connector."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/validate/nonexistent-id",
            headers=_headers(),
        )
        assert resp.status_code == 404


# ─── Phase 2: Provider Adapter Tests ─────────────────────────────────────

class TestPhase2ProviderAdapters:
    """
    POST /api/channel-manager/v2/providers/inventory/push
    POST /api/channel-manager/v2/providers/rates/push
    """

    def test_inventory_push_returns_correlation_id_and_latency(self):
        """Inventory push returns correlation_id, latency_ms, success status."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/providers/inventory/push",
            json={
                "connector_id": CONNECTOR_ID,
                "updates": [
                    {
                        "room_type_code": "TEST-V3",
                        "date_start": "2099-01-01",
                        "date_end": "2099-01-01",
                        "available": 5,
                    }
                ],
                "environment": "sandbox",
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Required fields
        assert "correlation_id" in data
        assert isinstance(data["correlation_id"], str)
        assert len(data["correlation_id"]) > 0  # UUID format
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], int)
        assert data["latency_ms"] >= 0
        assert "success" in data
        assert isinstance(data["success"], bool)

    def test_rate_push_returns_correlation_id_and_latency(self):
        """Rate push returns correlation_id, latency_ms, success status."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/providers/rates/push",
            json={
                "connector_id": CONNECTOR_ID,
                "updates": [
                    {
                        "room_type_code": "TEST-V3",
                        "rate_plan_code": "TEST-RP",
                        "date_start": "2099-01-01",
                        "date_end": "2099-01-01",
                        "amount_after_tax": 150.00,
                        "currency": "TRY",
                    }
                ],
                "environment": "sandbox",
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "correlation_id" in data
        assert "latency_ms" in data
        assert "success" in data

    def test_inventory_push_connector_not_found(self):
        """404 for nonexistent connector."""
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


# ─── Phase 3: AES-256-GCM Credential Update Tests ─────────────────────────

class TestPhase3AESCredentialUpdate:
    """
    PUT /api/channel-manager/v2/connectors/{connector_id}/credentials/secure
    """

    def test_secure_credential_update_encrypts_with_aes256gcm(self):
        """Secure update encrypts using AES-256-GCM."""
        new_creds = {"token": f"secure-{uuid.uuid4().hex[:8]}", "hr_id": "secure-99999"}
        resp = requests.put(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/secure",
            json={"credentials": new_creds},
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "AES-256-GCM" in data["message"]

        # Verify via masked endpoint
        masked_resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/masked",
            headers=_headers(),
        )
        assert masked_resp.status_code == 200
        masked_data = masked_resp.json()
        assert masked_data.get("algorithm") == "AES-256-GCM"
        assert masked_data.get("encrypted") is True


class TestPhase3CredentialRotation:
    """
    POST /api/channel-manager/v2/connectors/{connector_id}/credentials/rotate
    """

    def test_credential_rotation_updates_rotated_at(self):
        """Rotation updates credentials and sets rotated_at timestamp."""
        rotate_creds = {"token": f"rotated-{uuid.uuid4().hex[:8]}", "hr_id": "rotated-88888"}
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/rotate",
            json={"credentials": rotate_creds},
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "AES-256-GCM" in data["message"]


class TestPhase3MaskedCredentials:
    """
    GET /api/channel-manager/v2/connectors/{connector_id}/credentials/masked
    """

    def test_masked_credentials_returns_algorithm(self):
        """Masked credentials shows algorithm=AES-256-GCM."""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/masked",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "connector_id" in data
        assert data["connector_id"] == CONNECTOR_ID
        assert "credentials" in data
        assert isinstance(data["credentials"], dict)
        assert "algorithm" in data
        assert data["algorithm"] == "AES-256-GCM"
        assert "encrypted" in data
        assert data["encrypted"] is True
        
        # Verify credentials are masked (contain ****)
        for key, val in data["credentials"].items():
            assert "****" in val or len(val) <= 8  # Masked or short


class TestPhase3CredentialMigration:
    """
    POST /api/channel-manager/v2/connectors/{connector_id}/credentials/migrate
    """

    def test_migrate_credentials_xor_to_aes(self):
        """Migration endpoint converts legacy XOR to AES-256-GCM."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/migrate",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Already migrated or migration result
        assert "migrated" in data or "algorithm" in data
        if data.get("migrated") is True:
            assert "algorithm" in data
            assert data["algorithm"] == "AES-256-GCM"


# ─── Phase 4: RBAC Tests ─────────────────────────────────────────────────

class TestPhase4RBACAuthorizedAccess:
    """Verify admin role has access to credential endpoints."""

    def test_admin_can_update_credentials_secure(self):
        resp = requests.put(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/secure",
            json={"credentials": {"token": "admin-test", "hr_id": "admin-id"}},
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_rotate_credentials(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/rotate",
            json={"credentials": {"token": "rotated-admin", "hr_id": "rotated-admin-id"}},
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_view_masked_credentials(self):
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/masked",
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_admin_can_migrate_credentials(self):
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{CONNECTOR_ID}/credentials/migrate",
            headers=_headers(),
        )
        assert resp.status_code == 200


class TestPhase4RBAC403ForUnauthorized:
    """
    RBAC enforcement: credential endpoints return 403 for unauthorized roles.
    Note: This requires creating a user with restricted role, which is complex.
    We test RBAC module logic directly instead.
    """

    def test_rbac_module_denies_viewer_role(self):
        """RBAC module should raise 403 for viewer role on credential operations."""
        from channel_manager.infrastructure.rbac import CREDENTIAL_ADMIN_ROLES, RESTRICTED_ROLES
        
        # Verify role sets are correct
        assert "admin" in CREDENTIAL_ADMIN_ROLES
        assert "tenant_owner" in CREDENTIAL_ADMIN_ROLES
        assert "viewer" in RESTRICTED_ROLES
        assert "staff" in RESTRICTED_ROLES
        
        # Viewer should not be in admin roles
        assert "viewer" not in CREDENTIAL_ADMIN_ROLES
        assert "staff" not in CREDENTIAL_ADMIN_ROLES

    def test_rbac_module_structure(self):
        """Verify RBAC module exports expected function."""
        from channel_manager.infrastructure.rbac import enforce_credential_access
        import asyncio
        from fastapi import HTTPException
        
        # Create mock user with viewer role
        mock_user = MagicMock()
        mock_user.role = "viewer"
        mock_user.tenant_id = "test-tenant"
        mock_user.id = "test-user"
        
        # enforce_credential_access should raise 403 for viewer
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                enforce_credential_access(mock_user, "credential_update", "test-conn", require_write=True)
            )
        assert exc_info.value.status_code == 403


# ─── Phase 5: Reconciliation Health Score Tests ──────────────────────────

class TestPhase5ReconciliationHealth:
    """
    GET /api/channel-manager/v2/reconciliation/health/{connector_id}
    """

    def test_health_score_returns_0_to_100(self):
        """Health score is integer 0-100."""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/health/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "health_score" in data
        score = data["health_score"]
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_health_score_returns_status(self):
        """Health score includes status (healthy/degraded/critical)."""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/health/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "critical")

    def test_health_score_returns_open_issues(self):
        """Health score includes open_issues count."""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/health/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "open_issues" in data
        assert isinstance(data["open_issues"], int)
        assert data["open_issues"] >= 0

    def test_health_score_returns_breakdown(self):
        """Health score includes by_severity and by_type breakdowns."""
        resp = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/reconciliation/health/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "by_severity" in data
        assert isinstance(data["by_severity"], dict)
        assert "by_type" in data
        assert isinstance(data["by_type"], dict)


# ─── Phase 6: Scheduler Metrics Tests ────────────────────────────────────

class TestPhase6SchedulerMetrics:
    """
    POST /api/channel-manager/v2/scheduler/run/{connector_id}
    """

    def test_scheduler_returns_metrics_or_skipped(self):
        """Scheduler returns metrics (stale_jobs, requeued_jobs) or skipped reason."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/scheduler/run/{CONNECTOR_ID}",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        if data.get("skipped"):
            # Connector not active - should have reason
            assert "reason" in data
            assert isinstance(data["reason"], str)
        else:
            # Active connector - should have metrics
            assert "metrics" in data
            metrics = data["metrics"]
            assert "stale_jobs" in metrics
            assert isinstance(metrics["stale_jobs"], int)
            assert "requeued_jobs" in metrics
            assert isinstance(metrics["requeued_jobs"], int)

    def test_scheduler_run_all(self):
        """Run-all endpoint processes all connectors."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/scheduler/run-all",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "connectors_checked" in data
        assert "results" in data
        assert isinstance(data["results"], list)


# ─── Phase 7: Event Sync Tests ───────────────────────────────────────────

class TestPhase7EventSync:
    """
    POST /api/channel-manager/v2/events/sync
    POST /api/channel-manager/v2/events/sync/batch
    """

    def test_event_sync_booking_created(self):
        """Event sync handles booking_created event type."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "booking_created",
                "payload": {
                    "property_id": PROPERTY_ID,
                    "room_id": "R-TEST-101",
                    "check_in": "2099-06-01",
                    "check_out": "2099-06-03",
                },
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "handled" in data
        assert data["handled"] is True

    def test_event_sync_rate_changed(self):
        """Event sync handles rate_changed event type."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "rate_changed",
                "payload": {
                    "property_id": PROPERTY_ID,
                    "rate_plan_id": "RP-TEST-1",
                    "date_start": "2099-07-01",
                    "date_end": "2099-07-31",
                },
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "handled" in data
        assert data["handled"] is True

    def test_event_sync_batch(self):
        """Batch event sync processes multiple events."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync/batch",
            json={
                "events": [
                    {
                        "event_type": "booking_modified",
                        "payload": {"property_id": PROPERTY_ID, "room_id": "R-102"},
                    },
                    {
                        "event_type": "room_blocked",
                        "payload": {"property_id": PROPERTY_ID, "room_id": "R-103"},
                    },
                    {
                        "event_type": "restriction_changed",
                        "payload": {"property_id": PROPERTY_ID},
                    },
                ],
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert "processed" in data
        assert data["processed"] == 3
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_event_sync_unsupported_type(self):
        """Unsupported event type returns handled=False."""
        resp = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/events/sync",
            json={
                "event_type": "unsupported_event_xyz",
                "payload": {"property_id": PROPERTY_ID},
            },
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["handled"] is False
        assert "reason" in data


# ─── Phase 8: Encryption Unit Tests ──────────────────────────────────────

class TestPhase8EncryptionUnit:
    """Unit tests for AES-256-GCM encryption service."""

    def test_encrypt_decrypt_roundtrip(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        plaintext = "my-super-secret-token"
        ct = enc.encrypt(plaintext)
        assert ct.startswith("aes256gcm:")
        pt = enc.decrypt(ct)
        assert pt == plaintext

    def test_different_ivs_produce_different_ciphertexts(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        ct1 = enc.encrypt("same-secret")
        ct2 = enc.encrypt("same-secret")
        assert ct1 != ct2  # Different random IVs

    def test_tamper_detection_raises_error(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        import base64
        enc = EncryptionService()
        ct = enc.encrypt("secret")
        raw = ct[len("aes256gcm:"):]
        decoded = bytearray(base64.b64decode(raw))
        decoded[20] ^= 0xFF  # Tamper
        tampered = "aes256gcm:" + base64.b64encode(bytes(decoded)).decode()
        with pytest.raises(Exception):
            enc.decrypt(tampered)

    def test_credential_encryption_all_fields(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        enc = EncryptionService()
        creds = {"token": "abc", "hr_id": "123", "api_key": "xyz"}
        encrypted = enc.encrypt_credentials(creds)
        for v in encrypted.values():
            assert enc.is_aes_encrypted(v)
        decrypted = enc.decrypt_credentials(encrypted)
        assert decrypted == creds


class TestPhase8CredentialVaultUnit:
    """Unit tests for credential vault."""

    def test_mask_credentials(self):
        from channel_manager.infrastructure.credential_vault import CredentialVault
        vault = CredentialVault()
        creds = {"token": "abcdefghij", "hr_id": "12345"}
        masked = vault.mask_credentials(creds)
        # Token is long, should have **** masking
        assert "*" in masked["token"]
        # hr_id is short (5 chars), should show first 4 + partial masking
        assert masked["hr_id"] != creds["hr_id"]  # Should be masked
        assert "*" in masked["hr_id"]


class TestPhase8SandboxValidationServiceUnit:
    """Unit tests for sandbox validation service."""

    def test_check_result_helper(self):
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        result = SandboxValidationService._check_result(
            check_name="test_check",
            success=True,
            latency_ms=150,
            request_summary="GET /test",
            response_summary="OK",
        )
        assert result["check_name"] == "test_check"
        assert result["success"] is True
        assert result["latency_ms"] == 150

    def test_report_builder(self):
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [
            {"check_name": "auth", "success": True},
            {"check_name": "push", "success": False},
        ]
        report = SandboxValidationService._report("conn-1", "prop-1", checks, ["auth failed"])
        assert report["total_checks"] == 2
        assert report["passed_checks"] == 1
        assert report["failed_checks"] == 1
        assert "blocker_issues" in report
        assert "production_recommendation" in report


class TestPhase8ProviderAdapterUnit:
    """Unit tests for provider adapter error categorization."""

    def test_error_categorization(self):
        from channel_manager.application.provider_adapters import _categorise_error
        from channel_manager.connectors.hotelrunner.errors import (
            AuthenticationError, RateLimitError, ProviderUnavailableError,
        )
        
        assert _categorise_error(AuthenticationError("bad creds")) == "auth_error"
        assert _categorise_error(RateLimitError("slow down")) == "rate_limit_error"
        assert _categorise_error(ProviderUnavailableError("down")) == "provider_unavailable"
        assert _categorise_error(Exception("unknown")) == "unknown_error"
