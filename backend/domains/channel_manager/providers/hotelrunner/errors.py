"""
HotelRunner Provider — Error Hierarchy
========================================

Every error maps to a specific recovery strategy.
Monitoring and alert engine uses error types for severity classification.
"""


class HotelRunnerError(Exception):
    """Base error for all HotelRunner provider operations."""

    def __init__(self, message: str = "", *, recoverable: bool = False):
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)


class HotelRunnerAuthError(HotelRunnerError):
    """401 / invalid token. No retry. Alert severity: critical."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, recoverable=False)


class HotelRunnerRateLimitError(HotelRunnerError):
    """429. Retry with backoff. Alert severity: medium/high."""

    def __init__(self, retry_after_seconds: int = 60, message: str = "Rate limit exceeded"):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, recoverable=True)


class HotelRunnerTemporaryError(HotelRunnerError):
    """500+, timeout, network error. Retry with backoff."""

    def __init__(self, message: str = "Temporary provider error"):
        super().__init__(message, recoverable=True)


class HotelRunnerPayloadError(HotelRunnerError):
    """400 — bad request payload. No retry."""

    def __init__(self, message: str = "Invalid request payload", details: dict | None = None):
        self.details = details or {}
        super().__init__(message, recoverable=False)


class HotelRunnerParseError(HotelRunnerError):
    """Response parsing failure. No retry (manual inspection needed)."""

    def __init__(self, message: str = "Response parse error", raw_response: str = ""):
        self.raw_response = raw_response[:2000]
        super().__init__(message, recoverable=False)


class HotelRunnerMappingError(HotelRunnerError):
    """Room/rate mapping not found. No retry — produce reconciliation case."""

    def __init__(self, message: str = "Mapping not found", entity_type: str = "", entity_id: str = ""):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message, recoverable=False)


class HotelRunnerPaginationError(HotelRunnerError):
    """Pagination safety limit reached or duplicate page detected."""

    def __init__(self, max_pages: int = 0, fetched_count: int = 0, message: str = ""):
        self.max_pages = max_pages
        self.fetched_count = fetched_count
        msg = message or f"Pagination limit: {max_pages} pages, {fetched_count} items"
        super().__init__(msg, recoverable=False)


class HotelRunnerValidationError(HotelRunnerError):
    """Pre-flight validation failed before sending to provider."""

    def __init__(self, message: str = "Validation failed", field: str = ""):
        self.field = field
        super().__init__(message, recoverable=False)
