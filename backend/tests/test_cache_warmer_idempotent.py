"""
Cache Warmer — idempotent initialization regression
====================================================

Background
----------
``initialize_cache_warmer`` is invoked from BOTH the ``d_perf`` and
``g_channels`` bootstrap phases. Before the idempotency guard, each call
replaced the module-global warmer and spawned ANOTHER
``background_refresh`` task via ``asyncio.create_task`` without cancelling
the previous one. On the combined deployment a single uvicorn worker
serves BOTH the API and the static SPA chunks, so the accumulated 120s
warmer loops (each doing cross-tenant scans + a synchronous pass over up
to 5000 bookings) starved the one event loop. While the loop was blocked,
the edge proxy could not reach the worker and SPA chunk requests 502'd —
the recurring production white screen.

This test pins the guard down: calling ``initialize_cache_warmer`` twice
(simulating the two bootstrap phases) must leave exactly ONE background
refresh task running and reuse the same warmer instance.
"""
import asyncio

import cache_warmer as cw


class _FakeColl:
    async def find_one(self, *a, **k):
        return {"tenant_id": "tenant-test-1"}


class _FakeDB:
    users = _FakeColl()


async def test_initialize_cache_warmer_is_idempotent(monkeypatch):
    # Neutralise the real warm pass and the infinite refresh loop so the
    # test exercises only the create-once guard, not DB work.
    async def _noop_warm(self, tenant_id):
        return

    async def _sleep_forever(self, tenant_id):
        while True:
            await asyncio.sleep(3600)

    monkeypatch.setattr(cw.CacheWarmer, "warm_all_caches", _noop_warm)
    monkeypatch.setattr(cw.CacheWarmer, "background_refresh", _sleep_forever)

    # Reset module globals for isolation from other tests / import order.
    cw.cache_warmer = None
    cw._cache_warmer_task = None

    try:
        baseline = set(asyncio.all_tasks())

        w1 = await cw.initialize_cache_warmer(_FakeDB())  # d_perf phase
        task1 = cw._cache_warmer_task

        w2 = await cw.initialize_cache_warmer(_FakeDB())  # g_channels phase
        task2 = cw._cache_warmer_task

        new_tasks = [
            t
            for t in asyncio.all_tasks()
            if t not in baseline and t is not asyncio.current_task()
        ]

        # Same warmer instance + same single task reused across both calls.
        assert w1 is w2
        assert task1 is task2
        assert task1 is not None and not task1.done()

        # Exactly ONE background loop, not two.
        assert len(new_tasks) == 1
    finally:
        if cw._cache_warmer_task is not None:
            cw._cache_warmer_task.cancel()
            try:
                await cw._cache_warmer_task
            except (asyncio.CancelledError, Exception):
                pass
        cw.cache_warmer = None
        cw._cache_warmer_task = None
