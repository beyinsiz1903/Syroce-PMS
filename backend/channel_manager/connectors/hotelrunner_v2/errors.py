"""
HotelRunner v2 — Error Taxonomy
=================================

Every error type carries:
  - category   (auth | validation | rate_limit | timeout | server | parse | unknown)
  - retryable  (bool)
  - status_code hint for upstream callers
"""


class HRv2Error(Exception):
    """Base error for v2 connector."""

    category: str = "unknown"
    retryable: bool = False
    status_hint: int = 500

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class HRv2AuthError(HRv2Error):
    category = "auth"
    retryable = False
    status_hint = 401


class HRv2ValidationError(HRv2Error):
    category = "validation"
    retryable = False
    status_hint = 400


class HRv2RateLimitError(HRv2Error):
    category = "rate_limit"
    retryable = True
    status_hint = 429

    def __init__(self, message: str, *, retry_after: int = 60, cause: Exception | None = None):
        super().__init__(message, cause=cause)
        self.retry_after = retry_after


class HRv2TimeoutError(HRv2Error):
    category = "timeout"
    retryable = True
    status_hint = 504


class HRv2ServerError(HRv2Error):
    category = "server"
    retryable = True
    status_hint = 502


class HRv2ParseError(HRv2Error):
    category = "parse"
    retryable = False
    status_hint = 502
