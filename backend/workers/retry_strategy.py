"""
Workers — Retry Strategy
Configurable retry with exponential backoff, jitter, and max attempts.
"""
import asyncio
import logging
import random
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class RetryStrategy:
    """Configurable retry mechanism with exponential backoff and jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] | None = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (Exception,)

    def _calculate_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.backoff_factor ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay

    async def execute(self, fn: Callable[..., Awaitable], *args, **kwargs) -> dict[str, Any]:
        """Execute function with retry strategy."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                return {
                    "status": "success",
                    "attempt": attempt + 1,
                    "result": result,
                }
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(f"Retry {attempt + 1}/{self.max_retries} after {delay:.1f}s: {e}")
                    await asyncio.sleep(delay)

        return {
            "status": "failed",
            "attempts": self.max_retries + 1,
            "error": str(last_error),
        }


# Pre-configured strategies
gentle_retry = RetryStrategy(max_retries=3, base_delay=2.0, max_delay=30.0)
aggressive_retry = RetryStrategy(max_retries=5, base_delay=0.5, max_delay=60.0)
critical_retry = RetryStrategy(max_retries=10, base_delay=1.0, max_delay=120.0, backoff_factor=3.0)
