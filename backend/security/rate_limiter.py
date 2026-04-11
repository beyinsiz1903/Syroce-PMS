"""
Security — Rate Limiter
Configurable per-tenant and per-endpoint rate limiting.
"""
import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # tokens per second
        self.capacity = capacity  # max burst
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class TenantRateLimiter:
    """Per-tenant rate limiting with configurable tiers."""

    _TIER_LIMITS = {
        "basic":       {"rate": 10, "capacity": 50},    # 10 req/s, burst 50
        "professional": {"rate": 50, "capacity": 200},  # 50 req/s, burst 200
        "enterprise":  {"rate": 200, "capacity": 1000},  # 200 req/s, burst 1000
    }

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._stats: dict[str, dict[str, int]] = defaultdict(lambda: {"allowed": 0, "rejected": 0})

    def get_bucket(self, tenant_id: str, tier: str = "enterprise") -> TokenBucket:
        key = f"{tenant_id}:{tier}"
        if key not in self._buckets:
            config = self._TIER_LIMITS.get(tier, self._TIER_LIMITS["enterprise"])
            self._buckets[key] = TokenBucket(config["rate"], config["capacity"])
        return self._buckets[key]

    def allow_request(self, tenant_id: str, tier: str = "enterprise") -> bool:
        bucket = self.get_bucket(tenant_id, tier)
        allowed = bucket.consume()
        if allowed:
            self._stats[tenant_id]["allowed"] += 1
        else:
            self._stats[tenant_id]["rejected"] += 1
            logger.warning(f"Rate limit hit for tenant {tenant_id} (tier={tier})")
        return allowed

    def get_stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        if tenant_id:
            return dict(self._stats.get(tenant_id, {"allowed": 0, "rejected": 0}))
        return {tid: dict(stats) for tid, stats in self._stats.items()}


tenant_rate_limiter = TenantRateLimiter()
