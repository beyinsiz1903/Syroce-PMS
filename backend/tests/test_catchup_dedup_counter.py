"""
Catchup Dedup Counter — Restart-safe + multi-instance regression tests
========================================================================

Background
----------
Task #55: previously the counter behind ``[CATCHUP-DEDUP]`` lived only in
a per-process ``collections.deque``. Every backend restart wiped it, and
in a multi-instance deployment each worker reported its own slice of the
truth.

The refactor moves the primary store to a Redis sorted set
(``cm:catchup_dedup:events``) with a 24h sliding window, while keeping
the in-memory deque as a fallback / safety backstop.

These tests pin three properties:
  1. With Redis connected, ``record_skip`` writes survive a simulated
     process restart (i.e. clearing the in-memory deque).
  2. The 24h sliding window is honoured in Redis: backdated events older
     than 1h drop out of the 1h total but stay in the 24h total; older
     than 24h are pruned entirely.
  3. With Redis disconnected, the in-memory fallback returns sensible
     counts and never raises.

Test isolation
--------------
Each test calls ``reset()`` (which clears both stores) at start and end.
Tests that require Redis are skipped automatically when Redis cannot be
reached at the configured ``REDIS_URL``.
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from domains.channel_manager.monitoring import dedup_counter
from infra.redis_cluster import redis_cluster


# ─────────────────────────────────────────────────────────────────────
# Redis bootstrap fixture
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def redis_ready():
    """Connect ``redis_cluster`` to the dev Redis (or skip the module).

    ``conftest.py`` does not set ``REDIS_URL`` — start.sh does — so we
    fall back to the same default the dev environment uses
    (``redis://localhost:6380/0``).
    """
    if not os.environ.get("REDIS_URL"):
        os.environ["REDIS_URL"] = "redis://localhost:6380/0"
    connected = await redis_cluster.connect()
    if not connected:
        pytest.skip(
            f"Redis not reachable at {os.environ.get('REDIS_URL')!r}; "
            "cannot exercise the restart-safe path."
        )
    yield redis_cluster


@pytest.fixture(autouse=True)
async def _clean_state():
    """Fresh state before AND after each test — in-memory + Redis."""
    await dedup_counter.reset()
    yield
    await dedup_counter.reset()


# ─────────────────────────────────────────────────────────────────────
# 1. Restart-safety: data survives clearing the in-memory deque
# ─────────────────────────────────────────────────────────────────────

async def test_skips_survive_simulated_process_restart(redis_ready):
    """Record skips, wipe the in-memory deque, then ensure ``get_counts``
    still returns the recorded skips by reading them back from Redis."""
    await dedup_counter.record_skip("tenant-A", "hotelrunner")
    await dedup_counter.record_skip("tenant-A", "hotelrunner")
    await dedup_counter.record_skip("tenant-B", "hotelrunner")

    # Simulate a restart: drop the in-memory store while leaving Redis intact.
    async with dedup_counter._lock:
        dedup_counter._events.clear()

    counts = await dedup_counter.get_counts()
    assert counts["last_24h_total"] == 3, (
        f"3 skips were recorded before 'restart', got "
        f"{counts['last_24h_total']}: {counts}"
    )
    assert counts["last_1h_total"] == 3
    breakdown = counts["last_24h_by_tenant_provider"]
    assert breakdown.get("hotelrunner/tenant-A") == 2, breakdown
    assert breakdown.get("hotelrunner/tenant-B") == 1, breakdown


# ─────────────────────────────────────────────────────────────────────
# 2. Sliding window honoured in Redis
# ─────────────────────────────────────────────────────────────────────

async def test_sliding_window_prunes_old_events_in_redis(redis_ready):
    """Inject events directly into the Redis ZSET with backdated scores
    and verify the 1h / 24h windows behave correctly.

    Going through ``record_skip`` always uses ``time.time()`` for the
    score, so we cannot test backdating through it. Writing to Redis
    directly is fine for a property test of the read path.
    """
    client = redis_cluster.get_client()
    now = time.time()

    # Three skips: well-inside 1h, just-outside 1h, outside 24h.
    members_with_scores = {
        # inside 1h window
        f"{int((now - 60) * 1000)}:tenant-X:hotelrunner:fresh": now - 60,
        # outside 1h, inside 24h
        f"{int((now - 7200) * 1000)}:tenant-X:hotelrunner:older": now - 7200,
        # outside 24h — should be pruned by get_counts
        f"{int((now - 90000) * 1000)}:tenant-Y:hotelrunner:ancient": now - 90000,
    }
    await client.zadd(dedup_counter._REDIS_KEY, members_with_scores)

    counts = await dedup_counter.get_counts()
    assert counts["last_1h_total"] == 1, counts
    assert counts["last_24h_total"] == 2, counts
    assert counts["last_1h_by_tenant_provider"] == {"hotelrunner/tenant-X": 1}
    assert counts["last_24h_by_tenant_provider"] == {"hotelrunner/tenant-X": 2}

    # The ancient member should also have been removed from the ZSET by
    # the prune that runs inside get_counts.
    remaining = await client.zcard(dedup_counter._REDIS_KEY)
    assert remaining == 2, (
        f"prune should have evicted the >24h member, {remaining} remain"
    )


# ─────────────────────────────────────────────────────────────────────
# 3. Multi-process aggregation: two instances see each other's writes
# ─────────────────────────────────────────────────────────────────────

async def test_concurrent_writers_aggregate_in_redis(redis_ready):
    """Simulate 50 skips from two concurrent 'workers' and verify all
    of them land in Redis.

    This pins the contract that motivated the migration: counts now
    reflect the union across instances rather than only what the
    process serving the monitoring endpoint happened to see.
    """
    async def worker(tag: str, n: int) -> None:
        for i in range(n):
            await dedup_counter.record_skip(f"tenant-{tag}", "hotelrunner")
            # Yield to let the other coroutine interleave.
            if i % 5 == 0:
                await asyncio.sleep(0)

    await asyncio.gather(worker("A", 25), worker("B", 25))

    counts = await dedup_counter.get_counts()
    assert counts["last_24h_total"] == 50, counts
    assert counts["last_24h_by_tenant_provider"]["hotelrunner/tenant-A"] == 25
    assert counts["last_24h_by_tenant_provider"]["hotelrunner/tenant-B"] == 25


# ─────────────────────────────────────────────────────────────────────
# 4. Fallback: in-memory path is used when Redis is unreachable
# ─────────────────────────────────────────────────────────────────────

async def test_fallback_to_in_memory_when_redis_disconnected(monkeypatch):
    """Force ``_get_redis_client`` to return None and verify
    ``record_skip`` + ``get_counts`` still work via the deque."""
    monkeypatch.setattr(dedup_counter, "_get_redis_client", lambda: None)

    await dedup_counter.record_skip("tenant-fallback", "hotelrunner")
    await dedup_counter.record_skip("tenant-fallback", "hotelrunner")
    await dedup_counter.record_skip("tenant-other", "exely")

    counts = await dedup_counter.get_counts()
    assert counts["last_24h_total"] == 3, counts
    assert counts["last_1h_total"] == 3
    breakdown = counts["last_24h_by_tenant_provider"]
    assert breakdown.get("hotelrunner/tenant-fallback") == 2, breakdown
    assert breakdown.get("exely/tenant-other") == 1, breakdown


# ─────────────────────────────────────────────────────────────────────
# 5. Redis errors must never break the ingest path
# ─────────────────────────────────────────────────────────────────────

async def test_record_skip_swallows_redis_errors(monkeypatch):
    """If Redis raises during a write, ``record_skip`` must still return
    cleanly and the in-memory backstop must still hold the data so the
    aggregator does not lose the event entirely."""

    class _BoomClient:
        def pipeline(self, *_args, **_kwargs):
            raise RuntimeError("simulated redis outage")

    monkeypatch.setattr(
        dedup_counter, "_get_redis_client", lambda: _BoomClient()
    )

    # Must not raise.
    await dedup_counter.record_skip("tenant-resilient", "hotelrunner")

    # The in-memory backstop should still hold the event so the per-process
    # aggregator path keeps reporting it.
    async with dedup_counter._lock:
        snapshot = list(dedup_counter._events)
    assert len(snapshot) == 1, (
        f"in-memory backstop must hold the skip even when Redis errors, "
        f"got {snapshot}"
    )
    assert snapshot[0][1:] == ("tenant-resilient", "hotelrunner")


# ─────────────────────────────────────────────────────────────────────
# 6. Read-side fallback: Redis client present but reads raise
# ─────────────────────────────────────────────────────────────────────

async def test_get_counts_falls_back_when_redis_read_raises(monkeypatch):
    """If Redis is reachable but read ops raise (e.g. mid-failover or a
    corrupted member), ``get_counts`` must fall back to the in-memory
    deque rather than propagate or return zeros.

    Without this guard, the monitoring endpoint would either 500 or
    silently report ``last_24h_total: 0`` during a Redis read flap,
    masking real catchup re-ingest storms.
    """
    # Pre-load the in-memory deque so the fallback has data to report.
    # We force a no-op pipeline so record_skip leaves the deque alone
    # if it tried to use Redis on the way in.
    class _NoOpPipe:
        def zadd(self, *_a, **_kw): return self
        def zremrangebyscore(self, *_a, **_kw): return self
        def expire(self, *_a, **_kw): return self
        async def execute(self): return []

    class _ReadBoomClient:
        def pipeline(self, *_args, **_kwargs):
            return _NoOpPipe()
        async def zremrangebyscore(self, *_args, **_kwargs):
            raise RuntimeError("simulated read outage")
        async def zrangebyscore(self, *_args, **_kwargs):
            raise RuntimeError("simulated read outage")
        async def delete(self, *_args, **_kwargs):
            return 0

    monkeypatch.setattr(
        dedup_counter, "_get_redis_client", lambda: _ReadBoomClient()
    )

    await dedup_counter.record_skip("tenant-readfail", "hotelrunner")
    await dedup_counter.record_skip("tenant-readfail", "hotelrunner")

    counts = await dedup_counter.get_counts()
    assert counts["last_24h_total"] == 2, (
        f"read-side Redis failure must fall back to in-memory deque, got {counts}"
    )
    assert counts["last_1h_by_tenant_provider"] == {
        "hotelrunner/tenant-readfail": 2
    }, counts
