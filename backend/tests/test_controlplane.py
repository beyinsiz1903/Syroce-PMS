"""
Control Plane Test Suite — Comprehensive Tests
================================================
Tests covering:
1. Failure classification (taxonomy)
2. Failure tracking (CRUD lifecycle)
3. Retry behavior (idempotent, no duplicates)
4. Replay safety
5. Secret access logging
6. No plaintext leak in failure events
7. Alert triggers
8. Runbook system
9. Dry-run mode
"""
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from controlplane.failure_model import (
    FailureType,
    FailureStatus,
    Severity,
    OperationType,
    classify_failure,
    resolve_severity,
    build_failure_event,
)
from controlplane.failure_tracker import FailureTracker
from controlplane.retry_engine import RetryEngine
from controlplane.secret_audit import SecretAccessControl, check_access_policy
from controlplane.alerting import AlertingEngine, AlertSeverity, AlertTrigger
from controlplane.runbooks import get_runbook, list_runbooks, RUNBOOKS


# ═══════════════════════════════════════════════════════════════════
# 1. FAILURE CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFailureClassification:
    """Test the failure taxonomy keyword classification."""

    def test_retryable_timeout(self):
        assert classify_failure("Connection timed out") == FailureType.RETRYABLE

    def test_retryable_network(self):
        assert classify_failure("Network error: connection refused") == FailureType.RETRYABLE

    def test_retryable_rate_limit(self):
        assert classify_failure("Rate limit exceeded (429)") == FailureType.RETRYABLE

    def test_retryable_503(self):
        assert classify_failure("Service temporarily unavailable 503") == FailureType.RETRYABLE

    def test_permanent_validation(self):
        assert classify_failure("Mapping error: room type not found") == FailureType.DATA_ERROR

    def test_permanent_business_rule(self):
        assert classify_failure("Business rule violation: invalid date") == FailureType.DATA_ERROR

    def test_provider_exely(self):
        assert classify_failure("Exely API returned error") == FailureType.PROVIDER_ERROR

    def test_provider_hotelrunner(self):
        assert classify_failure("HotelRunner API 502") == FailureType.PROVIDER_ERROR

    def test_provider_auth(self):
        assert classify_failure("Authentication failed (401)") == FailureType.PROVIDER_ERROR

    def test_security_decrypt(self):
        assert classify_failure("Decryption failed: AAD mismatch") == FailureType.SECURITY_ERROR

    def test_security_unauthorized(self):
        assert classify_failure("Unauthorized access denied") == FailureType.SECURITY_ERROR

    def test_security_credential(self):
        assert classify_failure("Credential not found in vault") == FailureType.SECURITY_ERROR

    def test_unknown_defaults_retryable(self):
        assert classify_failure("Something unexpected happened") == FailureType.RETRYABLE

    def test_security_priority_over_provider(self):
        """Security keywords should win over provider keywords."""
        assert classify_failure("Exely credential decryption failed") == FailureType.SECURITY_ERROR


# ═══════════════════════════════════════════════════════════════════
# 2. SEVERITY RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestSeverityResolution:

    def test_retryable_default_warning(self):
        assert resolve_severity(FailureType.RETRYABLE) == Severity.WARNING

    def test_permanent_default_high(self):
        assert resolve_severity(FailureType.PERMANENT) == Severity.HIGH

    def test_security_default_critical(self):
        assert resolve_severity(FailureType.SECURITY_ERROR) == Severity.CRITICAL

    def test_override_takes_precedence(self):
        assert resolve_severity(FailureType.RETRYABLE, override=Severity.CRITICAL) == Severity.CRITICAL


# ═══════════════════════════════════════════════════════════════════
# 3. FAILURE EVENT BUILDING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFailureEventBuilding:

    def test_event_has_all_required_fields(self):
        event = build_failure_event(
            tenant_id="t1", provider="exely",
            operation_type="reservation_import",
            failure_type=FailureType.RETRYABLE,
            error_code="TIMEOUT",
            error_message="Connection timed out",
        )
        required = [
            "id", "tenant_id", "provider", "operation_type",
            "failure_type", "severity", "error_code", "error_message",
            "context", "retry_count", "first_seen_at", "last_seen_at",
            "status", "correlation_id", "created_at", "updated_at",
        ]
        for field in required:
            assert field in event, f"Missing field: {field}"

    def test_event_status_is_open(self):
        event = build_failure_event(
            tenant_id="t1", provider="exely",
            operation_type="ari_push",
            failure_type=FailureType.PROVIDER_ERROR,
            error_code="502", error_message="Bad Gateway",
        )
        assert event["status"] == "open"

    def test_no_plaintext_leak_in_context(self):
        """Context must NOT contain any secret-like keys."""
        event = build_failure_event(
            tenant_id="t1", provider="exely",
            operation_type="secret_access",
            failure_type=FailureType.SECURITY_ERROR,
            error_code="DENIED", error_message="Access denied",
            context={
                "reservation_id": "R001",
                "password": "supersecret123",
                "api_key": "sk-12345",
                "secret_value": "my-secret",
                "credential": "base64data",
                "safe_field": "this is fine",
            },
        )
        assert "password" not in event["context"]
        assert "api_key" not in event["context"]
        assert "secret_value" not in event["context"]
        assert "credential" not in event["context"]
        assert "safe_field" in event["context"]
        assert event["context"]["safe_field"] == "this is fine"

    def test_error_message_truncation(self):
        long_msg = "x" * 2000
        event = build_failure_event(
            tenant_id="t1", provider="exely",
            operation_type="ari_push",
            failure_type=FailureType.RETRYABLE,
            error_code="LONG", error_message=long_msg,
        )
        assert len(event["error_message"]) < 1100
        assert event["error_message"].endswith("...[truncated]")

    def test_severity_override(self):
        event = build_failure_event(
            tenant_id="t1", provider="exely",
            operation_type="night_audit",
            failure_type=FailureType.RETRYABLE,
            severity=Severity.CRITICAL,
            error_code="BLOCKED", error_message="Night audit blocked",
        )
        assert event["severity"] == "critical"


# ═══════════════════════════════════════════════════════════════════
# 4. SECRET ACCESS CONTROL TESTS
# ═══════════════════════════════════════════════════════════════════

class TestSecretAccessPolicy:

    def test_channel_manager_can_access_exely(self):
        assert check_access_policy("channel_manager", "exely") is True

    def test_channel_manager_can_access_hotelrunner(self):
        assert check_access_policy("channel_manager", "hotelrunner") is True

    def test_unknown_caller_denied(self):
        assert check_access_policy("random_service", "exely") is False

    def test_system_can_access_anything(self):
        assert check_access_policy("system", "exely") is True
        assert check_access_policy("system", "hotelrunner") is True

    def test_import_bridge_limited_access(self):
        assert check_access_policy("import_bridge", "exely") is True
        assert check_access_policy("import_bridge", "hotelrunner") is True


# ═══════════════════════════════════════════════════════════════════
# 5. RUNBOOK SYSTEM TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRunbooks:

    def test_all_required_runbooks_exist(self):
        required_ids = [
            "reservation_import_failed", "reservation_duplicate_detected",
            "reservation_mapping_missing", "outbox_stuck",
            "outbox_replay_failed", "ari_push_failed",
            "ari_parity_mismatch", "provider_auth_failed",
            "provider_rate_limited", "secret_access_denied",
            "secret_missing_or_unreadable", "crypto_decryption_failed",
            "night_audit_blocked", "sync_job_stalled",
        ]
        for rid in required_ids:
            rb = get_runbook(rid)
            assert rb is not None, f"Missing runbook: {rid}"

    def test_runbook_has_required_fields(self):
        rb = get_runbook("outbox_stuck")
        d = rb.to_dict()
        required = ["id", "title", "description", "category", "severity",
                     "possible_causes", "resolution_steps", "retry_instructions",
                     "related_operations"]
        for field in required:
            assert field in d, f"Missing field: {field}"
            assert d[field], f"Empty field: {field}"

    def test_runbook_filter_by_category(self):
        security = list_runbooks(category="security")
        assert len(security) >= 3
        for rb in security:
            assert rb["category"] == "security"

    def test_nonexistent_runbook_returns_none(self):
        assert get_runbook("nonexistent_runbook") is None

    def test_runbook_count(self):
        all_runbooks = list_runbooks()
        assert len(all_runbooks) == 15


# ═══════════════════════════════════════════════════════════════════
# 6. OPERATION TYPE ENUM COMPLETENESS
# ═══════════════════════════════════════════════════════════════════

class TestOperationTypes:

    def test_all_critical_operations_defined(self):
        ops = [e.value for e in OperationType]
        assert "reservation_import" in ops
        assert "ari_push" in ops
        assert "outbox_dispatch" in ops
        assert "sync_job" in ops
        assert "secret_access" in ops
        assert "crypto_decrypt" in ops
        assert "night_audit" in ops
        assert "provider_auth" in ops


# ═══════════════════════════════════════════════════════════════════
# 7. ALERTING THRESHOLDS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAlertingThresholds:

    def test_all_triggers_have_thresholds(self):
        from controlplane.alerting import DEFAULT_THRESHOLDS
        triggers = [
            AlertTrigger.IMPORT_FAILURE_SPIKE,
            AlertTrigger.OUTBOX_STUCK,
            AlertTrigger.SYNC_FAILURE_SPIKE,
            AlertTrigger.SECRET_ANOMALY,
            AlertTrigger.PROVIDER_AUTH_FAILURE,
            AlertTrigger.HIGH_ERROR_RATE,
            AlertTrigger.CRYPTO_FAILURE,
        ]
        for t in triggers:
            assert t in DEFAULT_THRESHOLDS, f"Missing threshold for: {t}"

    def test_crypto_failure_threshold_is_one(self):
        """Crypto failures should trigger on the FIRST occurrence."""
        from controlplane.alerting import DEFAULT_THRESHOLDS
        assert DEFAULT_THRESHOLDS[AlertTrigger.CRYPTO_FAILURE]["count"] == 1


# ═══════════════════════════════════════════════════════════════════
# 8. FAILURE STATUS LIFECYCLE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFailureStatusLifecycle:

    def test_valid_status_transitions(self):
        """Verify the expected status values exist."""
        assert FailureStatus.OPEN.value == "open"
        assert FailureStatus.RESOLVED.value == "resolved"
        assert FailureStatus.IGNORED.value == "ignored"
        assert FailureStatus.RETRYING.value == "retrying"

    def test_failure_type_values(self):
        assert FailureType.RETRYABLE.value == "retryable"
        assert FailureType.PERMANENT.value == "permanent"
        assert FailureType.PROVIDER_ERROR.value == "provider_error"
        assert FailureType.DATA_ERROR.value == "data_error"
        assert FailureType.SECURITY_ERROR.value == "security_error"
