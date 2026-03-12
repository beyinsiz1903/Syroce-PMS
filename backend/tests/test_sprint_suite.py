"""
Comprehensive test suite for the 4 implementation sprints:
- Sprint 1: HotelRunner Sandbox Validation
- Sprint 2: Router Refactoring (integration tests)
- Sprint 3: Scheduled Import Jobs
- Sprint 4: Credential Security
- Provider contract errors
"""
import uuid


# ─── Test Helpers ─────────────────────────────────────────────────

def _tenant_id():
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


def _connector_id():
    return f"test-conn-{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════════
# SPRINT 1: Sandbox Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestSandboxValidation:
    """Tests for the SandboxValidationService."""

    def test_check_result_structure(self):
        """Verify _check_result returns correct structure."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        result = SandboxValidationService._check_result(
            "test_check", True, latency_ms=42,
            request_summary="GET /test",
            response_summary="OK",
            provider_status="pass",
        )
        assert result["check_name"] == "test_check"
        assert result["success"] is True
        assert result["latency_ms"] == 42
        assert result["request_summary"] == "GET /test"

    def test_report_ready(self):
        """Report should show READY when all checks pass."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [
            SandboxValidationService._check_result("auth", True),
            SandboxValidationService._check_result("pull", True),
            SandboxValidationService._check_result("push", True),
        ]
        report = SandboxValidationService._report("c1", "p1", checks, [])
        assert report["passed_checks"] == 3
        assert report["failed_checks"] == 0
        assert "READY" in report["production_recommendation"]

    def test_report_not_ready(self):
        """Report should show NOT_READY when blocker issues exist."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [SandboxValidationService._check_result("auth", False, error="401")]
        report = SandboxValidationService._report("c1", "p1", checks, ["Auth failed"])
        assert report["failed_checks"] == 1
        assert "NOT_READY" in report["production_recommendation"]

    def test_report_conditional(self):
        """Report should show CONDITIONAL for non-critical failures."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [
            SandboxValidationService._check_result("auth", True),
            SandboxValidationService._check_result("pagination", False, error="timeout"),
        ]
        report = SandboxValidationService._report("c1", "p1", checks, [])
        assert report["passed_checks"] == 1
        assert report["failed_checks"] == 1
        assert "CONDITIONAL" in report["production_recommendation"]

    def test_report_includes_warnings_and_mismatches(self):
        """Report should classify warnings and contract mismatches."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [
            SandboxValidationService._check_result("auth", True),
            SandboxValidationService._check_result("parsing", False, error="schema mismatch in response"),
            SandboxValidationService._check_result("ack", False, error="timeout"),
        ]
        report = SandboxValidationService._report("c1", "p1", checks, [])
        assert len(report["contract_mismatches"]) == 1
        assert len(report["warnings"]) == 1

    def test_report_total_latency(self):
        """Report should sum all check latencies."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        checks = [
            SandboxValidationService._check_result("a", True, latency_ms=100),
            SandboxValidationService._check_result("b", True, latency_ms=200),
        ]
        report = SandboxValidationService._report("c1", "p1", checks, [])
        assert report["total_latency_ms"] == 300


# ═══════════════════════════════════════════════════════════════════
# SPRINT 1: Environment Config Tests
# ═══════════════════════════════════════════════════════════════════

class TestEnvironmentConfig:
    """Tests for environment configuration."""

    def test_all_environments_present(self):
        from channel_manager.connectors.hotelrunner.environment_config import ENVIRONMENTS
        assert "mock" in ENVIRONMENTS
        assert "sandbox" in ENVIRONMENTS
        assert "production" in ENVIRONMENTS

    def test_sandbox_config(self):
        from channel_manager.connectors.hotelrunner.environment_config import get_environment_config
        cfg = get_environment_config("sandbox")
        assert cfg.name == "sandbox"
        assert "sandbox" in cfg.api_base_url
        assert cfg.sandbox is True
        assert cfg.credential_encryption_required is True

    def test_production_config(self):
        from channel_manager.connectors.hotelrunner.environment_config import get_environment_config
        cfg = get_environment_config("production")
        assert cfg.name == "production"
        assert cfg.sandbox is False
        assert cfg.enable_raw_logging is False

    def test_mock_config(self):
        from channel_manager.connectors.hotelrunner.environment_config import get_environment_config
        cfg = get_environment_config("mock")
        assert cfg.name == "mock"
        assert "localhost" in cfg.api_base_url
        assert cfg.credential_encryption_required is False

    def test_unknown_env_defaults_to_sandbox(self):
        from channel_manager.connectors.hotelrunner.environment_config import get_environment_config
        cfg = get_environment_config("nonexistent")
        assert cfg.name == "sandbox"

    def test_get_all_environments(self):
        from channel_manager.connectors.hotelrunner.environment_config import get_all_environments
        envs = get_all_environments()
        assert len(envs) == 3
        assert all(isinstance(v, dict) for v in envs.values())


# ═══════════════════════════════════════════════════════════════════
# SPRINT 2: Router Refactoring Tests
# ═══════════════════════════════════════════════════════════════════

class TestRouterRegistry:
    """Verify all routers are properly registered."""

    def test_router_registry_imports(self):
        from channel_manager.interfaces.router_registry import router
        routes = [r.path for r in router.routes]
        assert len(routes) > 0

    def test_connector_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/connectors" in p for p in paths)

    def test_reservation_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/reservations/stats" in p for p in paths)
        assert any("/reservations/batches" in p for p in paths)

    def test_alert_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/alerts" in p for p in paths)
        assert any("/alerts/rules" in p for p in paths)

    def test_metrics_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/metrics/history" in p for p in paths)
        assert any("/metrics/trends" in p for p in paths)

    def test_scheduler_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/import-jobs" in p for p in paths)
        assert any("/environments" in p for p in paths)

    def test_audit_endpoints_registered(self):
        from channel_manager.interfaces.router_registry import router
        paths = [r.path for r in router.routes]
        assert any("/audit" in p for p in paths)
        assert any("/dashboard" in p for p in paths)


# ═══════════════════════════════════════════════════════════════════
# SPRINT 3: Scheduled Import Job Tests
# ═══════════════════════════════════════════════════════════════════

class TestScheduledImportJob:
    """Tests for the ScheduledImportJob model."""

    def test_job_creation(self):
        from channel_manager.application.scheduled_import_service import ScheduledImportJob
        job = ScheduledImportJob(
            tenant_id="t1", connector_id="c1", property_id="p1",
        )
        assert job.status == "pending"
        assert job.retry_count == 0
        assert job.max_retries == 3

    def test_job_to_doc(self):
        from channel_manager.application.scheduled_import_service import ScheduledImportJob
        job = ScheduledImportJob(tenant_id="t1", connector_id="c1")
        doc = job.to_doc()
        assert doc["tenant_id"] == "t1"
        assert doc["connector_id"] == "c1"
        assert doc["status"] == "pending"
        assert "id" in doc

    def test_duplicate_prevention_key(self):
        """Test that _running_jobs dict prevents duplicate entries."""
        from channel_manager.application.scheduled_import_service import _running_jobs
        _running_jobs["test-c1"] = "job-1"
        assert "test-c1" in _running_jobs
        _running_jobs.pop("test-c1", None)
        assert "test-c1" not in _running_jobs


# ═══════════════════════════════════════════════════════════════════
# SPRINT 4: Credential Security Model Tests
# ═══════════════════════════════════════════════════════════════════

class TestCredentialSecurityModels:
    """Tests for credential security data models."""

    def test_connector_credential_creation(self):
        from channel_manager.domain.models.credential_security import ConnectorCredential
        cred = ConnectorCredential(
            tenant_id="t1", connector_id="c1", provider="hotelrunner",
        )
        assert cred.encryption_algorithm == "AES-256-GCM"
        assert cred.key_version == 1
        assert cred.is_active is True

    def test_connector_credential_to_doc(self):
        from channel_manager.domain.models.credential_security import ConnectorCredential
        cred = ConnectorCredential(tenant_id="t1", connector_id="c1")
        doc = cred.to_doc()
        assert "_id" not in doc
        assert doc["encryption_algorithm"] == "AES-256-GCM"

    def test_encrypted_secret_creation(self):
        from channel_manager.domain.models.credential_security import EncryptedSecret
        secret = EncryptedSecret(
            credential_id="cred1", field_name="token",
            encrypted_value="enc123", nonce="n1", tag="t1",
        )
        assert secret.algorithm == "AES-256-GCM"
        assert secret.field_name == "token"

    def test_secret_rotation_log(self):
        from channel_manager.domain.models.credential_security import SecretRotationLog
        log = SecretRotationLog(
            tenant_id="t1", connector_id="c1",
            rotation_type="manual", rotated_by="admin1",
            old_key_version=1, new_key_version=2,
            fields_rotated=["token", "hr_id"],
        )
        doc = log.to_doc()
        assert doc["old_key_version"] == 1
        assert doc["new_key_version"] == 2
        assert len(doc["fields_rotated"]) == 2
        assert "_id" not in doc


# ═══════════════════════════════════════════════════════════════════
# Provider Contract Error Tests
# ═══════════════════════════════════════════════════════════════════

class TestProviderContractErrors:
    """Tests for typed provider contract error classes."""

    def test_invalid_xml_error(self):
        from channel_manager.connectors.hotelrunner.contract_errors import InvalidXmlError
        err = InvalidXmlError("Bad XML", raw_xml="<broken", parse_error="unclosed tag")
        assert err.error_type == "invalid_xml"
        d = err.to_dict()
        assert d["error_type"] == "invalid_xml"
        assert "broken" in d["details"]["raw_xml_snippet"]

    def test_missing_required_field(self):
        from channel_manager.connectors.hotelrunner.contract_errors import MissingRequiredFieldError
        err = MissingRequiredFieldError("guest_name", entity_type="reservation", entity_id="R123")
        assert err.error_type == "missing_required_field"
        assert "guest_name" in str(err)

    def test_schema_mismatch_error(self):
        from channel_manager.connectors.hotelrunner.contract_errors import SchemaMismatchError
        err = SchemaMismatchError("Schema changed", expected="v1", actual="v2")
        assert err.error_type == "schema_mismatch"
        d = err.to_dict()
        assert d["details"]["expected_schema"] == "v1"

    def test_provider_error_response(self):
        from channel_manager.connectors.hotelrunner.contract_errors import ProviderErrorResponseError
        err = ProviderErrorResponseError("HotelRunner", "42", "Invalid hotel code")
        assert err.error_type == "provider_error_response"
        assert "42" in str(err)

    def test_unknown_response_format(self):
        from channel_manager.connectors.hotelrunner.contract_errors import UnknownResponseFormatError
        err = UnknownResponseFormatError(content_type="text/html", raw_response="<html>...")
        assert err.error_type == "unknown_response_format"

    def test_all_errors_inherit_from_base(self):
        from channel_manager.connectors.hotelrunner.contract_errors import (
            ProviderContractError, InvalidXmlError, MissingRequiredFieldError,
            SchemaMismatchError, ProviderErrorResponseError, UnknownResponseFormatError,
        )
        for cls in [InvalidXmlError, MissingRequiredFieldError, SchemaMismatchError,
                     ProviderErrorResponseError, UnknownResponseFormatError]:
            assert issubclass(cls, ProviderContractError)


# ═══════════════════════════════════════════════════════════════════
# Audit Action Enum Tests
# ═══════════════════════════════════════════════════════════════════

class TestAuditActions:
    """Verify all new audit actions are registered."""

    def test_import_job_actions(self):
        from channel_manager.domain.models.audit import AuditAction
        assert AuditAction.IMPORT_JOB_STARTED.value == "import_job_started"
        assert AuditAction.IMPORT_JOB_COMPLETED.value == "import_job_completed"
        assert AuditAction.IMPORT_JOB_RETRYING.value == "import_job_retrying"
        assert AuditAction.IMPORT_JOB_FAILED.value == "import_job_failed"

    def test_credential_security_actions(self):
        from channel_manager.domain.models.audit import AuditAction
        assert AuditAction.CREDENTIAL_ROTATION_STARTED.value == "credential_rotation_started"
        assert AuditAction.CREDENTIAL_ROTATION_COMPLETED.value == "credential_rotation_completed"
        assert AuditAction.CREDENTIAL_VALIDATION_PASSED.value == "credential_validation_passed"

    def test_safety_net_action(self):
        from channel_manager.domain.models.audit import AuditAction
        assert AuditAction.SAFETY_NET_SYNC_RUN.value == "safety_net_sync_run"


# ═══════════════════════════════════════════════════════════════════
# Existing Reservation Engine Regression Tests
# ═══════════════════════════════════════════════════════════════════

class TestReservationImportRegression:
    """Ensure existing reservation import models still work after refactoring."""

    def test_imported_reservation_model(self):
        from channel_manager.domain.models.reservation_import import ImportedReservation
        res = ImportedReservation(
            tenant_id="t1", connector_id="c1", property_id="p1",
            batch_id="b1", external_reservation_id="ER-001",
            external_confirmation_number="CN-001",
            guest_name="Test Guest", channel_name="hotelrunner",
        )
        doc = res.to_doc()
        assert doc["external_reservation_id"] == "ER-001"
        assert doc["import_status"] == "pending"
        assert "_id" not in doc

    def test_reservation_batch_model(self):
        from channel_manager.domain.models.reservation_import import ReservationImportBatch
        batch = ReservationImportBatch(
            tenant_id="t1", connector_id="c1", property_id="p1",
        )
        doc = batch.to_doc()
        assert doc["status"] == "in_progress"
        assert "id" in doc

    def test_fingerprint_computation(self):
        from channel_manager.domain.models.reservation_import import ImportedReservation
        fp1 = ImportedReservation.compute_fingerprint({"arrival_date": "2025-01-01", "total_amount": 100})
        fp2 = ImportedReservation.compute_fingerprint({"arrival_date": "2025-01-01", "total_amount": 100})
        fp3 = ImportedReservation.compute_fingerprint({"arrival_date": "2025-01-02", "total_amount": 200})
        assert fp1 == fp2
        assert fp1 != fp3


# ═══════════════════════════════════════════════════════════════════
# Credential Vault Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestCredentialVault:
    """Test the CredentialVault encryption/masking functionality."""

    def test_mask_credentials(self):
        from channel_manager.infrastructure.credential_vault import CredentialVault
        vault = CredentialVault()
        creds = {"token": "abc12345", "hr_id": "12345678"}
        masked = vault.mask_credentials(creds)
        assert masked["token"] != "abc12345"
        assert "****" in masked["token"]

    def test_encrypt_decrypt_roundtrip(self):
        from channel_manager.infrastructure.encryption_service import EncryptionService
        svc = EncryptionService()
        original = "my-secret-token-12345"
        encrypted = svc.encrypt(original)
        decrypted = svc.decrypt(encrypted)
        assert decrypted == original
        assert encrypted != original
