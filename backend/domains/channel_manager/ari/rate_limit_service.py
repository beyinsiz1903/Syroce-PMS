"""
ARI Rate Limit Service.

Per-provider per-property rate limiter using token bucket algorithm.
Prevents exceeding provider API limits.
"""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

# Provider rate limits (requests per minute)
PROVIDER_RATE_LIMITS = {
    "hotelrunner": {"rpm": 5, "daily": 250},
    "exely": {"rpm": 30, "daily": 5000},
}


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: int, capacity: int):
        self.rate = rate  # tokens per minute
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * (self.rate / 60.0))
        self.last_refill = now

    def try_consume(self) -> bool:
        self._refill()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    def wait_time(self) -> float:
        self._refill()
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / (self.rate / 60.0)


class ARIRateLimitService:
    """Manages per-provider per-property rate limits."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._daily_counts: dict[str, int] = defaultdict(int)
        self._daily_reset: dict[str, float] = {}

    def _get_key(self, provider: str, property_id: str) -> str:
        return f"{provider}|{property_id}"

    def _get_bucket(self, provider: str, property_id: str) -> TokenBucket:
        key = self._get_key(provider, property_id)
        if key not in self._buckets:
            limits = PROVIDER_RATE_LIMITS.get(provider, {"rpm": 10, "daily": 1000})
            self._buckets[key] = TokenBucket(limits["rpm"], limits["rpm"])
        return self._buckets[key]

    def _check_daily(self, provider: str, property_id: str) -> bool:
        key = self._get_key(provider, property_id)
        now = time.monotonic()
        if key not in self._daily_reset or now - self._daily_reset[key] >= 86400:
            self._daily_counts[key] = 0
            self._daily_reset[key] = now
        limits = PROVIDER_RATE_LIMITS.get(provider, {"rpm": 10, "daily": 1000})
        return self._daily_counts[key] < limits["daily"] - 5  # safety margin

    async def acquire(self, provider: str, property_id: str) -> bool:
        """Try to acquire a rate limit token. Returns True if allowed."""
        if not self._check_daily(provider, property_id):
            logger.warning(f"ARI rate limit: daily limit approaching for {provider}/{property_id}")
            return False

        bucket = self._get_bucket(provider, property_id)
        if bucket.try_consume():
            key = self._get_key(provider, property_id)
            self._daily_counts[key] += 1
            return True

        # Wait for token
        wait = bucket.wait_time()
        if wait > 0 and wait < 30:
            logger.debug(f"ARI rate limit: waiting {wait:.1f}s for {provider}/{property_id}")
            await asyncio.sleep(wait)
            if bucket.try_consume():
                key = self._get_key(provider, property_id)
                self._daily_counts[key] += 1
                return True

        return False

    def record_429(self, provider: str, property_id: str):
        """Record a 429 response - reduce available tokens."""
        bucket = self._get_bucket(provider, property_id)
        bucket.tokens = 0  # drain tokens, forcing wait

    def get_stats(self, provider: str | None = None) -> dict:
        stats = {}
        for key, bucket in self._buckets.items():
            p, prop = key.split("|", 1)
            if provider and p != provider:
                continue
            stats[key] = {
                "provider": p,
                "property_id": prop,
                "available_tokens": round(bucket.tokens, 1),
                "daily_used": self._daily_counts.get(key, 0),
                "daily_limit": PROVIDER_RATE_LIMITS.get(p, {}).get("daily", 1000),
            }
        return stats


# Singleton
rate_limiter = ARIRateLimitService()
