"""
HotelRunner Retry Policy - Exponential backoff with jitter for failed requests.
"""
import asyncio
import logging
import random
from typing import Any, Callable, Optional

from .errors import AuthenticationError, ConnectorError, ProviderUnavailableError, RateLimitError

logger = logging.getLogger("channel_manager.hotelrunner.retry")


class RetryPolicy:
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
        if attempt >= self.max_retries:
            return False
        if isinstance(error, AuthenticationError):
            return False  # Auth errors are never retried
        if isinstance(error, (RateLimitError, ProviderUnavailableError)):
            return True
        if isinstance(error, ConnectorError) and error.recoverable:
            return True
        return False

    def get_delay(self, attempt: int, error: Optional[Exception] = None) -> float:
        """Calculate delay before next retry with exponential backoff + jitter."""
        if isinstance(error, RateLimitError):
            return float(error.retry_after_seconds)
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        return max(0.5, delay)

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute an async function with retry logic."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if not self.should_retry(e, attempt + 1):
                    raise
                delay = self.get_delay(attempt, e)
                logger.warning(
                    "Retry attempt %d/%d after %.1fs for %s: %s",
                    attempt + 1, self.max_retries, delay,
                    func.__name__, str(e),
                )
                await asyncio.sleep(delay)
        raise last_error
