"""
Exely Provider — Error Hierarchy
==================================

Every error maps to a specific recovery strategy.
Monitoring and alert engine uses error types for severity classification.

SOAP-specific: differentiates transport errors, SOAP Faults, and OTA-level errors.
"""

import hashlib
import re


def _safe_provider_code(value: str) -> str:
    candidate = str(value or "")[:64]
    return candidate if re.fullmatch(r"[A-Za-z0-9_.:-]+", candidate) else ""


class ExelyError(Exception):
    """Base error for all Exely provider operations."""

    def __init__(self, message: str = "", *, recoverable: bool = False):
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)


class ExelyAuthError(ExelyError):
    """WSSE authentication failure. No retry. Alert severity: critical."""

    def __init__(self, message: str = "WSSE authentication failed"):
        super().__init__(message, recoverable=False)


class ExelySOAPFaultError(ExelyError):
    """SOAP Fault received from server. May or may not be retryable."""

    def __init__(self, fault_code: str = "", fault_string: str = "", *, recoverable: bool = False):
        self.fault_code = _safe_provider_code(fault_code)
        self.fault_string = ""
        msg = f"SOAP Fault [{self.fault_code}]" if self.fault_code else "SOAP Fault"
        super().__init__(msg, recoverable=recoverable)


class ExelyTemporaryError(ExelyError):
    """HTTP 5xx, timeout, network error. Retry with backoff."""

    def __init__(self, message: str = "Temporary provider error"):
        super().__init__(message, recoverable=True)


class ExelyRateLimitError(ExelyError):
    """429 or throttle. Retry with backoff. Alert severity: medium/high."""

    def __init__(
        self,
        retry_after_seconds: int = 60,
        message: str = "Rate limit exceeded",
        *,
        provider_code: str = "",
        source: str = "provider",
    ):
        self.retry_after_seconds = retry_after_seconds
        self.provider_code = _safe_provider_code(provider_code)
        self.source = source if source in {"provider", "local_quota"} else "provider"
        super().__init__(message, recoverable=True)


class ExelyPayloadError(ExelyError):
    """400 — bad request / invalid SOAP message. No retry."""

    def __init__(self, message: str = "Invalid request payload", details: dict | None = None):
        self.detail_fields = sorted(str(key) for key in (details or {}))
        self.details = {}
        super().__init__(message, recoverable=False)


class ExelyParseError(ExelyError):
    """XML/SOAP response parsing failure. No retry (manual inspection needed)."""

    def __init__(self, message: str = "Response parse error", raw_response: str = ""):
        encoded = raw_response.encode("utf-8", errors="replace")
        self.raw_response = ""
        self.response_size_bytes = len(encoded)
        self.response_sha256 = hashlib.sha256(encoded).hexdigest() if encoded else ""
        super().__init__(message, recoverable=False)


class ExelyMappingError(ExelyError):
    """Room/rate mapping not found. No retry — produce reconciliation case."""

    def __init__(self, message: str = "Mapping not found", entity_type: str = "", entity_id: str = ""):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message, recoverable=False)


class ExelyValidationError(ExelyError):
    """Pre-flight validation failed before sending to provider."""

    def __init__(self, message: str = "Validation failed", field: str = ""):
        self.field = field
        super().__init__(message, recoverable=False)
