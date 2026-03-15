"""
HotelRunner Provider — Retry Policy
=====================================

Exponential backoff with jitter.
Separates retryable from non-retryable errors.

Retry: timeout, network error, 429, 500/502/503/504
No retry: 400, 401, 403, mapping error, malformed response
"""
import asyncio
import random
import logging
from typing import Callable, Any

from .errors import (
    HotelRunnerError,
    HotelRunnerAuthError,
    HotelRunnerPayloadError,
    HotelRunnerParseError,
    HotelRunnerMappingError,
    HotelRunnerValidationError,
    HotelRunnerRateLimitError,
    HotelRunnerTemporaryError,
)

logger = logging.getLogger("hotelrunner.retry")

# Errors that must NOT be retried
_NON_RETRYABLE = (
    HotelRunnerAuthError,
    HotelRunnerPayloadError,
    HotelRunnerParseError,
    HotelRunnerMappingError,
    HotelRunnerValidationError,
)


class HotelRunnerRetryPolicy:
    """Configurable retry policy with exponential backoff and jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 120.0,
        jitter: float = 0.5,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if the error warrants a retry."""
        if attempt > self.max_retries:
            return False
        if isinstance(error, _NON_RETRYABLE):
            return False
        if isinstance(error, HotelRunnerRateLimitError):
            return True
        if isinstance(error, HotelRunnerTemporaryError):
            return True
        if isinstance(error, HotelRunnerError) and error.recoverable:
            return True
        return False

    def get_backoff_seconds(self, attempt: int, error: Exception | None = None) -> float:
        """Calculate delay before next retry."""
        if isinstance(error, HotelRunnerRateLimitError):
            return float(error.retry_after_seconds)
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        return max(0.5, delay)

    async def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute an async function with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if not self.should_retry(e, attempt + 1):
                    raise
                delay = self.get_backoff_seconds(attempt, e)
                logger.warning(
                    "HotelRunner retry %d/%d after %.1fs: %s",
                    attempt + 1, self.max_retries, delay, e,
                )
                await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]
