"""
Catchup Pre-Insert Dedup Counter
=================================

In-memory sliding-window counter for the pre-insert duplicate guard fired by
HotelRunner sync/catchup paths. Counts the number of times the guard short-
circuited a re-insert of an already-recorded provider_event_id (`[CATCHUP-DEDUP]`
log tag).

Why in-memory:
- Mirrors the existing pattern used by `_monitoring_state` and worker state in
  `monitoring_worker.py` and `ingest/workers.py`. No new collection needed.
- Catchup retry storms are bounded by sync interval and provider event volume;
  worst-case in-memory size stays well under a few thousand per day.

Multi-process note:
- If the backend is ever scaled to multiple processes, each process holds its
  own counter. The aggregator already runs on a single monitoring worker
  process, so the counts seen via `/monitoring/*` reflect that process. A
  follow-up task can move this to Redis if multi-instance attribution becomes
  important.
"""
import asyncio
import time
from collections import deque
from typing import Any

_RETENTION_SECONDS = 24 * 3600  # 24 hours

# (epoch_seconds, tenant_id, provider)
_events: deque[tuple[float, str, str]] = deque()
_lock = asyncio.Lock()


def _prune_locked(now: float) -> None:
    """Drop events older than the retention window. Caller must hold the lock."""
    cutoff = now - _RETENTION_SECONDS
    while _events and _events[0][0] < cutoff:
        _events.popleft()


async def record_skip(tenant_id: str, provider: str) -> None:
    """Record one pre-insert duplicate guard skip."""
    now = time.time()
    async with _lock:
        _prune_locked(now)
        _events.append((now, tenant_id or "unknown", provider or "unknown"))


def _breakdown(events: list[tuple[float, str, str]]) -> dict[str, int]:
    """Aggregate by 'provider/tenant' key for per-tenant alerting."""
    out: dict[str, int] = {}
    for _, t, p in events:
        key = f"{p}/{t}"
        out[key] = out.get(key, 0) + 1
    return out


async def get_counts() -> dict[str, Any]:
    """Return current sliding-window counts (last 1h and last 24h)."""
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
    """Test helper: clear all recorded events."""
    async with _lock:
        _events.clear()
