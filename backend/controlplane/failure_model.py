"""
Failure Model — Strict Taxonomy for the Entire System
======================================================
Every failure across reservation ingest, ARI push, outbox events,
sync jobs, and secret access MUST be classified using this taxonomy.

No silent failures. No unclassified errors.
"""
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    """Strict failure classification. Every failure MUST map to one of these."""
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
    PROVIDER_ERROR = "provider_error"
    DATA_ERROR = "data_error"
    SECURITY_ERROR = "security_error"


class Severity(str, Enum):
    """Failure severity for alerting and prioritization."""
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class FailureStatus(str, Enum):
    """Lifecycle status of a failure event."""
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    RETRYING = "retrying"


class OperationType(str, Enum):
    """Every operation that can fail."""
    RESERVATION_PULL = "reservation_pull"
    RESERVATION_IMPORT = "reservation_import"
    ARI_PUSH = "ari_push"
    OUTBOX_DISPATCH = "outbox_dispatch"
    SYNC_JOB = "sync_job"
    SECRET_ACCESS = "secret_access"
    SECRET_ROTATE = "secret_rotate"
    CRYPTO_DECRYPT = "crypto_decrypt"
    CRYPTO_ENCRYPT = "crypto_encrypt"
    PROVIDER_AUTH = "provider_auth"
    PROVIDER_SYNC = "provider_sync"
    NIGHT_AUDIT = "night_audit"
    CONFIRM_DELIVERY = "confirm_delivery"
    MAPPING_RESOLVE = "mapping_resolve"
    RECONCILIATION = "reconciliation"


# ── Severity Defaults by FailureType ───────────────────────────────
DEFAULT_SEVERITY: dict[FailureType, Severity] = {
    FailureType.RETRYABLE: Severity.WARNING,
    FailureType.PERMANENT: Severity.HIGH,
    FailureType.PROVIDER_ERROR: Severity.HIGH,
    FailureType.DATA_ERROR: Severity.WARNING,
    FailureType.SECURITY_ERROR: Severity.CRITICAL,
}

# ── Classification Keywords ────────────────────────────────────────
_RETRYABLE_KEYWORDS = [
    "timeout", "timed out", "connection refused", "connection reset",
    "temporary", "unavailable", "network", "write conflict",
    "lock", "replica", "rate limit", "throttl", "429", "503",
]

_PERMANENT_KEYWORDS = [
    "mapping error", "invalid payload", "validation",
    "business rule", "not found", "schema",
    "unsupported", "deprecated", "rejected",
]

_PROVIDER_KEYWORDS = [
    "exely", "hotelrunner", "ota", "provider", "api key",
    "wsse", "authentication failed", "403", "401", "502",
]

_SECURITY_KEYWORDS = [
    "decrypt", "encrypt", "credential", "secret",
    "unauthorized", "forbidden", "denied", "key not found",
    "tamper", "integrity", "aad mismatch",
]


def classify_failure(
    error_message: str,
    *,
    operation_type: str | None = None,
) -> FailureType:
    """Classify an error message into the failure taxonomy.

    Classification priority: SECURITY > PROVIDER > DATA > RETRYABLE > PERMANENT
    """
    lower = error_message.lower()

    # Security errors take highest priority
    for kw in _SECURITY_KEYWORDS:
        if kw in lower:
            return FailureType.SECURITY_ERROR

    # Provider errors
    for kw in _PROVIDER_KEYWORDS:
        if kw in lower:
            return FailureType.PROVIDER_ERROR

    # Permanent data errors
    for kw in _PERMANENT_KEYWORDS:
        if kw in lower:
            return FailureType.DATA_ERROR

    # Retryable transient errors
    for kw in _RETRYABLE_KEYWORDS:
        if kw in lower:
            return FailureType.RETRYABLE

    # Default: retryable (optimistic — retry before giving up)
    return FailureType.RETRYABLE


def resolve_severity(
    failure_type: FailureType,
    *,
    override: Severity | None = None,
) -> Severity:
    """Get severity for a failure type, with optional override."""
    if override:
        return override
    return DEFAULT_SEVERITY.get(failure_type, Severity.WARNING)


def build_failure_event(
    *,
    tenant_id: str,
    provider: str,
    operation_type: str,
    failure_type: FailureType,
    error_code: str,
    error_message: str,
    severity: Severity | None = None,
    context: dict[str, Any] | None = None,
    retry_count: int = 0,
    correlation_id: str | None = None,
    property_id: str | None = None,
) -> dict[str, Any]:
    """Build a structured failure event document.

    This is the canonical failure schema used across the entire system.
    Context must contain ONLY safe metadata — no secrets, no plaintext credentials.
    """
    now = datetime.now(UTC).isoformat()
    resolved_severity = resolve_severity(failure_type, override=severity)

    # Sanitize context: strip any keys that might leak secrets
    safe_context = _sanitize_context(context or {})

    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "provider": provider,
        "property_id": property_id or "",
        "operation_type": operation_type,
        "failure_type": failure_type.value,
        "severity": resolved_severity.value,
        "error_code": error_code,
        "error_message": _sanitize_error_message(error_message),
        "context": safe_context,
        "retry_count": retry_count,
        "first_seen_at": now,
        "last_seen_at": now,
        "status": FailureStatus.OPEN.value,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
    }


# ── Sanitization ───────────────────────────────────────────────────

_FORBIDDEN_CONTEXT_KEYS = {
    "password", "secret", "key", "token", "credential",
    "api_key", "apikey", "auth_token", "private_key",
    "plaintext", "decrypted", "raw_value",
}


def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Remove any keys that might contain sensitive data."""
    return {
        k: v for k, v in context.items()
        if k.lower() not in _FORBIDDEN_CONTEXT_KEYS
        and not any(s in k.lower() for s in ("secret", "password", "credential", "key"))
    }


def _sanitize_error_message(msg: str, max_length: int = 1000) -> str:
    """Truncate and strip potential secrets from error messages."""
    if len(msg) > max_length:
        msg = msg[:max_length] + "...[truncated]"
    return msg
