"""
Exely Provider — Retry Policy
================================

Exponential backoff with jitter for SOAP transient errors.
Separates retryable from non-retryable errors.

Retry: timeout, network error, 429, 500/502/503/504, transient SOAP faults
No retry: auth error, payload error, parse error, mapping error
"""
import asyncio
import logging
import random
from typing import Any, Callable

from .errors import (
    ExelyAuthError,
    ExelyError,
    ExelyMappingError,
    ExelyParseError,
    ExelyPayloadError,
    ExelyRateLimitError,
    ExelyTemporaryError,
    ExelyValidationError,
)

logger = logging.getLogger("exely.retry")

_NON_RETRYABLE = (
    ExelyAuthError,
    ExelyPayloadError,
    ExelyParseError,
    ExelyMappingError,
    ExelyValidationError,
)


class ExelyRetryPolicy:
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
        if attempt > self.max_retries:
            return False
        if isinstance(error, _NON_RETRYABLE):
            return False
        if isinstance(error, ExelyRateLimitError):
            return True
        if isinstance(error, ExelyTemporaryError):
            return True
        if isinstance(error, ExelyError) and error.recoverable:
            return True
        return False

    def get_backoff_seconds(self, attempt: int, error: Exception | None = None) -> float:
        if isinstance(error, ExelyRateLimitError):
            return float(error.retry_after_seconds)
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        return max(0.5, delay)

    async def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
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
                    "Exely retry %d/%d after %.1fs: %s",
                    attempt + 1, self.max_retries, delay, e,
                )
                await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]
