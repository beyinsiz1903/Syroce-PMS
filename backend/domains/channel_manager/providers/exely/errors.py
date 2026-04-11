"""
Exely Provider — Error Hierarchy
==================================

Every error maps to a specific recovery strategy.
Monitoring and alert engine uses error types for severity classification.

SOAP-specific: differentiates transport errors, SOAP Faults, and OTA-level errors.
"""


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
        self.fault_code = fault_code
        self.fault_string = fault_string
        msg = f"SOAP Fault [{fault_code}]: {fault_string}" if fault_code else fault_string or "SOAP Fault"
        super().__init__(msg, recoverable=recoverable)


class ExelyTemporaryError(ExelyError):
    """HTTP 5xx, timeout, network error. Retry with backoff."""

    def __init__(self, message: str = "Temporary provider error"):
        super().__init__(message, recoverable=True)


class ExelyRateLimitError(ExelyError):
    """429 or throttle. Retry with backoff. Alert severity: medium/high."""

    def __init__(self, retry_after_seconds: int = 60, message: str = "Rate limit exceeded"):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, recoverable=True)


class ExelyPayloadError(ExelyError):
    """400 — bad request / invalid SOAP message. No retry."""

    def __init__(self, message: str = "Invalid request payload", details: dict | None = None):
        self.details = details or {}
        super().__init__(message, recoverable=False)


class ExelyParseError(ExelyError):
    """XML/SOAP response parsing failure. No retry (manual inspection needed)."""

    def __init__(self, message: str = "Response parse error", raw_response: str = ""):
        self.raw_response = raw_response[:2000]
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
