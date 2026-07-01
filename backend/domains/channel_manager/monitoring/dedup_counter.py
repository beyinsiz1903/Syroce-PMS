"""
Catchup Pre-Insert Dedup Counter
=================================

Sliding-window counter for the pre-insert duplicate guard fired by
HotelRunner sync/catchup paths. Counts the number of times the guard
short-circuited a re-insert of an already-recorded provider_event_id
(``[CATCHUP-DEDUP]`` log tag).

Storage
-------
- **Primary (when Redis is connected):** Redis sorted set
  ``cm:catchup_dedup:events`` with score = epoch seconds and member =
  ``"{epoch_ms}:{tenant_id}:{provider}:{uuid}"``. Survives backend
  restarts and is shared across multiple backend instances. The key
  carries a 25h TTL as a final safety net.
- **Fallback (Redis disabled or any Redis error):** the original
  in-memory ``collections.deque``. The deque is also used as a backstop
  even when Redis is connected, so a transient Redis outage does not
  silently lose the most recent skips a single process saw.

The ingest path (``hotelrunner_shared._persist_and_process``) calls
``record_skip`` in its hot loop. It must never raise, so every Redis
operation is wrapped in ``try/except`` and degrades to the in-memory
path.

Read priority in ``get_counts``: if Redis is available we return the
shared, restart-safe counts. The in-memory deque is consulted only as
a last resort, which keeps single-instance dev setups working without
Redis configured.
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Any

logger = logging.getLogger("monitoring.dedup_counter")

_RETENTION_SECONDS = 24 * 3600  # 24 hours
_REDIS_KEY = "cm:catchup_dedup:events"
# Safety TTL: longer than the retention window so an idle key does not
# vanish before the next prune; ZREMRANGEBYSCORE handles the real
# eviction every time we touch the set.
_REDIS_KEY_TTL = _RETENTION_SECONDS + 3600

# (epoch_seconds, tenant_id, provider) — in-memory backstop / fallback.
_events: deque[tuple[float, str, str]] = deque()
_lock = asyncio.Lock()


def _prune_locked(now: float) -> None:
    """Drop in-memory events older than the retention window.

    Caller must hold ``_lock``.
    """
    cutoff = now - _RETENTION_SECONDS
    while _events and _events[0][0] < cutoff:
        _events.popleft()


def _get_redis_client() -> Any | None:
    """Return the connected Redis client, or ``None`` if unavailable.

    Imported lazily to keep this module importable in test environments
    where the redis client module is not installed or not configured.
    """
    try:
        from infra.redis_cluster import redis_cluster
    except Exception:
        return None
    if not getattr(redis_cluster, "connected", False):
        return None
    try:
        client = redis_cluster.get_client()
    except Exception:
        return None
    return client


def _build_member(now: float, tenant_id: str, provider: str) -> str:
    """Compose a unique sorted-set member.

    The ``uuid`` suffix prevents same-millisecond collisions for the
    same (tenant, provider) pair, which would otherwise be deduped by
    ZADD (sorted-set members are unique).
    """
    epoch_ms = int(now * 1000)
    return f"{epoch_ms}:{tenant_id}:{provider}:{uuid.uuid4().hex[:8]}"


def _parse_member(member: str) -> tuple[str, str] | None:
    """Extract (tenant_id, provider) from a stored member string."""
    parts = member.split(":", 3)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


async def _record_redis(client: Any, now: float, tenant_id: str, provider: str) -> bool:
    """Append to the Redis ZSET and prune. Returns True on success."""
    try:
        cutoff = now - _RETENTION_SECONDS
        member = _build_member(now, tenant_id, provider)
        pipe = client.pipeline(transaction=False)
        pipe.zadd(_REDIS_KEY, {member: now})
        pipe.zremrangebyscore(_REDIS_KEY, 0, cutoff)
        pipe.expire(_REDIS_KEY, _REDIS_KEY_TTL)
        await pipe.execute()
        return True
    except Exception as e:
        logger.warning(f"dedup_counter: Redis record_skip failed: {e}")
        return False


async def record_skip(tenant_id: str, provider: str) -> None:
    """Record one pre-insert duplicate guard skip.

    Always writes to the in-memory backstop. Additionally writes to
    Redis when available so other instances and post-restart reads
    can see the skip. Redis errors are swallowed.
    """
    now = time.time()
    tid = tenant_id or "unknown"
    prov = provider or "unknown"

    # In-memory backstop — never fails.
    async with _lock:
        _prune_locked(now)
        _events.append((now, tid, prov))

    # Best-effort Redis write; degraded silently on any failure.
    client = _get_redis_client()
    if client is not None:
        await _record_redis(client, now, tid, prov)


def _breakdown(events: list[tuple[float, str, str]]) -> dict[str, int]:
    """Aggregate by ``"{provider}/{tenant}"`` for per-tenant alerting."""
    out: dict[str, int] = {}
    for _, t, p in events:
        key = f"{p}/{t}"
        out[key] = out.get(key, 0) + 1
    return out


async def _get_counts_redis(client: Any) -> dict[str, Any] | None:
    """Read counts from the Redis ZSET. Returns None on any failure."""
    try:
        now = time.time()
        cutoff = now - _RETENTION_SECONDS
        one_hour_ago = now - 3600
        # Prune first so totals reflect the live retention window.
        await client.zremrangebyscore(_REDIS_KEY, 0, cutoff)
        # ``withscores=True`` lets us split 1h vs 24h locally without
        # issuing a second ZRANGEBYSCORE round-trip.
        raw = await client.zrangebyscore(
            _REDIS_KEY,
            cutoff,
            "+inf",
            withscores=True,
        )
        snapshot_24h: list[tuple[float, str, str]] = []
        for member, score in raw:
            parsed = _parse_member(member)
            if not parsed:
                continue
            t, p = parsed
            snapshot_24h.append((float(score), t, p))
        snapshot_1h = [e for e in snapshot_24h if e[0] >= one_hour_ago]
        return {
            "last_1h_total": len(snapshot_1h),
            "last_24h_total": len(snapshot_24h),
            "last_1h_by_tenant_provider": _breakdown(snapshot_1h),
            "last_24h_by_tenant_provider": _breakdown(snapshot_24h),
        }
    except Exception as e:
        logger.warning(f"dedup_counter: Redis get_counts failed: {e}")
        return None


async def get_counts() -> dict[str, Any]:
    """Return current sliding-window counts (last 1h and last 24h).

    Prefers the Redis-backed shared counter when reachable, so values
    survive backend restarts and aggregate across instances. Falls back
    to the per-process in-memory deque otherwise.
    """
    client = _get_redis_client()
    if client is not None:
        redis_counts = await _get_counts_redis(client)
        if redis_counts is not None:
            return redis_counts

    now = time.time()
    one_hour_ago = now - 3600
    async with _lock:
        _prune_locked(now)
        snapshot_24h = list(_events)
    snapshot_1h = [e for e in snapshot_24h if e[0] >= one_hour_ago]
    return {
        "last_1h_total": len(snapshot_1h),
        "last_24h_total": len(snapshot_24h),
        "last_1h_by_tenant_provider": _breakdown(snapshot_1h),
        "last_24h_by_tenant_provider": _breakdown(snapshot_24h),
    }


async def reset() -> None:
    """Test helper: clear all recorded events (in-memory + Redis)."""
    async with _lock:
        _events.clear()
    client = _get_redis_client()
    if client is not None:
        try:
            await client.delete(_REDIS_KEY)
        except Exception as e:
            logger.warning(f"dedup_counter: Redis reset failed: {e}")
