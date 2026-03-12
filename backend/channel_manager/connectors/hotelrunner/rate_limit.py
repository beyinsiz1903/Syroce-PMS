"""
HotelRunner Rate Limiter - Token bucket algorithm for API rate limiting.
Prevents hitting HotelRunner's API rate limits by throttling outgoing requests.
"""
import asyncio
import time


class RateLimiter:
    """Token-bucket rate limiter for HotelRunner API calls."""

    def __init__(self, max_per_minute: int = 60, max_per_hour: int = 1000):
        self._max_per_minute = max_per_minute
        self._max_per_hour = max_per_hour
        self._minute_tokens = max_per_minute
        self._hour_tokens = max_per_hour
        self._last_minute_refill = time.monotonic()
        self._last_hour_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 120.0) -> bool:
        """Wait until a token is available. Returns False if timeout exceeded."""
        deadline = time.monotonic() + timeout
        while True:
            async with self._lock:
                self._refill()
                if self._minute_tokens > 0 and self._hour_tokens > 0:
                    self._minute_tokens -= 1
                    self._hour_tokens -= 1
                    return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(1.0)

    def _refill(self):
        now = time.monotonic()
        # Minute bucket
        elapsed_min = now - self._last_minute_refill
        if elapsed_min >= 60.0:
            self._minute_tokens = self._max_per_minute
            self._last_minute_refill = now
        # Hour bucket
        elapsed_hr = now - self._last_hour_refill
        if elapsed_hr >= 3600.0:
            self._hour_tokens = self._max_per_hour
            self._last_hour_refill = now

    @property
    def available_minute_tokens(self) -> int:
        self._refill()
        return self._minute_tokens

    @property
    def available_hour_tokens(self) -> int:
        self._refill()
        return self._hour_tokens
