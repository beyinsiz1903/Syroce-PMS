"""Distributed Exely PMSConnect request and change quotas.

The PMSConnect 1.17.1 contract limits each HotelCode to 650 requests/hour,
30 OTA_ReadRQ requests/hour, and several ARI change windows.  One Redis Lua
decision covers every applicable window so reservation reads and ARI writes
share the same property budget across all workers.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("exely.provider_quota")

TOTAL_REQUESTS_PER_HOUR = 650
READ_REQUESTS_PER_HOUR = 30
CHANGES_PER_SECOND = 1460
CHANGES_PER_THREE_MINUTES = 4380
CHANGES_PER_HOUR = 13140
CHANGES_PER_DAY = 43800
MAX_RETRY_AFTER_SECONDS = 3600

_RESERVE_SCRIPT = """
local cooldown_ttl = redis.call('TTL', KEYS[1])
if cooldown_ttl > 0 then
  return {0, 1, cooldown_ttl}
end

for i = 2, #KEYS do
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  local cost = tonumber(ARGV[(i - 2) * 3 + 1])
  local limit = tonumber(ARGV[(i - 2) * 3 + 2])
  if current + cost > limit then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 1 then ttl = tonumber(ARGV[(i - 2) * 3 + 3]) end
    return {0, i, ttl}
  end
end

for i = 2, #KEYS do
  local cost = tonumber(ARGV[(i - 2) * 3 + 1])
  local ttl = tonumber(ARGV[(i - 2) * 3 + 3])
  redis.call('INCRBY', KEYS[i], cost)
  if redis.call('TTL', KEYS[i]) < 0 then redis.call('EXPIRE', KEYS[i], ttl) end
end
return {1, 0, 0}
"""


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    retry_after_seconds: int = 0


class ExelyProviderQuota:
    """Fail-closed distributed quota for one tenant/property pair."""

    def __init__(self, tenant_id: str, property_id: str, *, redis_client: Any | None = None):
        if not tenant_id or not property_id:
            raise ValueError("tenant_id and property_id are required for Exely quota")
        scope = hashlib.sha256(f"{tenant_id}|{property_id}".encode()).hexdigest()[:24]
        self._tag = f"{{{scope}}}"
        self._redis_client = redis_client

    async def reserve(self, *, operation: str, change_count: int = 0) -> QuotaDecision:
        client = self._redis_client or await _shared_redis_client()
        if client is None:
            return QuotaDecision(False, "QUOTA_BACKEND_UNAVAILABLE")

        now = datetime.now(UTC)
        windows = _quota_windows(operation, change_count, now)

        keys = [self._key("cooldown"), *(self._key(name) for name, _cost, _limit, _ttl in windows)]
        args = [item for _name, cost, limit, ttl in windows for item in (cost, limit, ttl)]
        try:
            raw = await client.eval(_RESERVE_SCRIPT, len(keys), *keys, *args)
        except Exception as exc:
            logger.error("Exely quota unavailable exception_class=%s", type(exc).__name__)
            return QuotaDecision(False, "QUOTA_BACKEND_UNAVAILABLE")

        allowed = bool(int(raw[0]))
        if allowed:
            return QuotaDecision(True, "QUOTA_RESERVED")
        blocked_index = int(raw[1])
        retry_after = _bounded_seconds(raw[2], default=60)
        reason = "PROVIDER_COOLDOWN" if blocked_index == 1 else "PROVIDER_QUOTA_EXCEEDED"
        return QuotaDecision(False, reason, retry_after)

    async def record_cooldown(self, retry_after_seconds: int) -> None:
        client = self._redis_client or await _shared_redis_client()
        if client is None:
            return
        ttl = _bounded_seconds(retry_after_seconds, default=60)
        try:
            await client.set(self._key("cooldown"), "1", ex=ttl)
        except Exception as exc:
            logger.error("Exely quota cooldown unavailable exception_class=%s", type(exc).__name__)

    def _key(self, suffix: str) -> str:
        return f"exely:provider-quota:{self._tag}:{suffix}"


def _quota_windows(operation: str, change_count: int, now: datetime) -> list[tuple[str, int, int, int]]:
    total = (f"total:{now:%Y%m%d%H}", 1, TOTAL_REQUESTS_PER_HOUR, 3700)
    if operation == "reservation_read":
        return [(f"read:{now:%Y%m%d%H}", 1, READ_REQUESTS_PER_HOUR, 3700), total]
    if change_count > 0:
        epoch = int(now.timestamp())
        return [
            (f"changes:second:{epoch}", change_count, CHANGES_PER_SECOND, 2),
            total,
            (f"changes:3m:{epoch // 180}", change_count, CHANGES_PER_THREE_MINUTES, 190),
            (f"changes:hour:{now:%Y%m%d%H}", change_count, CHANGES_PER_HOUR, 3700),
            (f"changes:day:{now:%Y%m%d}", change_count, CHANGES_PER_DAY, 90000),
        ]
    return [total]


async def _shared_redis_client() -> Any | None:
    try:
        from infra.redis_cluster import redis_cluster

        client = redis_cluster.get_client()
        if client is None and await redis_cluster.connect():
            client = redis_cluster.get_client()
        return client
    except Exception as exc:
        logger.error("Exely quota backend resolution failed exception_class=%s", type(exc).__name__)
        return None


def _bounded_seconds(value: Any, *, default: int) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = default
    return max(1, min(seconds, MAX_RETRY_AFTER_SECONDS))
