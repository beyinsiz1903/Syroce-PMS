"""
Provider Circuit Breaker — Integration Tests
=============================================

Pinpoints the per-connection circuit breaker wrapping for HotelRunner
(`push_daily_inventory`, `push_date_range_inventory`) and Exely (`push_ari`)
push methods. The breaker prevents log/CPU spam during persistent gateway
outages by short-circuiting after `failure_threshold` failures.

Reference: CM-Hardening Stop-Sale Circuit Breaker tour, May 2026.
"""
import time
import pytest
from unittest.mock import AsyncMock, patch

from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider
from domains.channel_manager.providers.hotelrunner.client import HttpResult
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerTemporaryError,
)
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.errors import ExelyError
from domains.channel_manager.provider_failover import (
    provider_failover,
    CircuitState,
)


def _ok_http(data=None, status_code=200):
    return HttpResult(
        success=True,
        status_code=status_code,
        data=data or {},
        error="",
        duration_ms=10,
        correlation_id="t-1",
    )


def _fail_http(status_code=504, error="Gateway Timeout"):
    return HttpResult(
        success=False,
        status_code=status_code,
        data={},
        error=error,
        duration_ms=10,
        correlation_id="t-1",
    )


@pytest.fixture(autouse=True)
def _reset_breakers():
    """Each test starts with a clean breaker registry."""
    provider_failover._breakers.clear()
    yield
    provider_failover._breakers.clear()


# ══════════════════════════════════════════════════════════════════════
# T1 — Successful push leaves breaker CLOSED, no fail-fast
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t1_hr_push_success_keeps_breaker_closed():
    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-A",
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.return_value = _ok_http(data={"ok": True})
        result = await provider.push_daily_inventory(payload)

    assert result.success is True
    breaker = provider_failover.get_breaker("hotelrunner:conn-A")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


# ══════════════════════════════════════════════════════════════════════
# T2 — N persistent failures trip breaker, next call fails fast (no HTTP)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t2_hr_failure_threshold_trips_breaker_short_circuits_next_call():
    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-B", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.side_effect = HotelRunnerTemporaryError("upstream 504")
        for _ in range(5):
            r = await provider.push_daily_inventory(payload)
            assert r.success is False

        breaker = provider_failover.get_breaker("hotelrunner:conn-B")
        assert breaker.state == CircuitState.OPEN

        call_count_before = mput.await_count
        r = await provider.push_daily_inventory(payload)

    assert r.success is False
    assert r.error_type == "CircuitOpen"
    assert r.metadata.get("circuit_open") is True
    assert "circuit_open" in r.error
    assert mput.await_count == call_count_before, "HTTP call must NOT happen when breaker OPEN"


# ══════════════════════════════════════════════════════════════════════
# T3 — After recovery_timeout, breaker enters HALF_OPEN; success closes it
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t3_hr_recovery_half_open_to_closed_on_success():
    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-C", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.side_effect = HotelRunnerTemporaryError("upstream 504")
        for _ in range(5):
            await provider.push_daily_inventory(payload)
        breaker = provider_failover.get_breaker("hotelrunner:conn-C")
        assert breaker.state == CircuitState.OPEN

        breaker.last_failure_time = time.time() - (breaker.recovery_timeout + 1)

        mput.side_effect = None
        for _ in range(breaker.half_open_max_calls):
            mput.return_value = _ok_http(data={"ok": True})
            r = await provider.push_daily_inventory(payload)
            assert r.success is True

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


# ══════════════════════════════════════════════════════════════════════
# T4 — HALF_OPEN failure trips breaker back to OPEN
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t4_hr_half_open_failure_returns_to_open():
    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-D", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.side_effect = HotelRunnerTemporaryError("boom")
        for _ in range(5):
            await provider.push_daily_inventory(payload)

        breaker = provider_failover.get_breaker("hotelrunner:conn-D")
        breaker.last_failure_time = time.time() - (breaker.recovery_timeout + 1)
        assert breaker.is_available is True
        assert breaker.state == CircuitState.HALF_OPEN

        r = await provider.push_daily_inventory(payload)

    assert r.success is False
    assert breaker.state == CircuitState.OPEN


# ══════════════════════════════════════════════════════════════════════
# T5 — Per-connection isolation: tenant A trip does NOT block tenant B
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t5_per_connection_isolation():
    provider_a = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-A", max_retries=0,
    )
    provider_b = HotelRunnerProvider(
        token="t" * 12, hr_id="hr2", connection_id="conn-B", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider_a._client, "put", new_callable=AsyncMock) as mput_a:
        mput_a.side_effect = HotelRunnerTemporaryError("A down")
        for _ in range(5):
            await provider_a.push_daily_inventory(payload)

    breaker_a = provider_failover.get_breaker("hotelrunner:conn-A")
    breaker_b = provider_failover.get_breaker("hotelrunner:conn-B")
    assert breaker_a.state == CircuitState.OPEN

    with patch.object(provider_b._client, "put", new_callable=AsyncMock) as mput_b:
        mput_b.return_value = _ok_http(data={"ok": True})
        r = await provider_b.push_daily_inventory(payload)

    assert r.success is True
    assert breaker_b.state == CircuitState.CLOSED
    assert mput_b.await_count == 1


# ══════════════════════════════════════════════════════════════════════
# T6 — Exely push_ari wrapped by separate breaker namespace
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t6_exely_push_ari_circuit_open_short_circuits_soap():
    provider = ExelyProvider(
        username="u", password="p", hotel_code="hc",
        connection_id="exely-conn-X", max_retries=0,
    )

    with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as msoap:
        msoap.side_effect = ExelyError("upstream gateway")
        for _ in range(5):
            r = await provider.push_ari(
                room_type_code="STD", rate_plan_code="BAR",
                start_date="2026-06-01", end_date="2026-06-05",
                availability=10, stop_sell=False,
            )
            assert r.success is False

        breaker = provider_failover.get_breaker("exely:exely-conn-X")
        assert breaker.state == CircuitState.OPEN

        soap_calls_before = msoap.await_count
        r = await provider.push_ari(
            room_type_code="STD", rate_plan_code="BAR",
            start_date="2026-06-01", end_date="2026-06-05",
            availability=10, stop_sell=False,
        )

    assert r.success is False
    assert r.error_type == "CircuitOpen"
    assert r.metadata.get("circuit_open") is True
    assert msoap.await_count == soap_calls_before, "SOAP must NOT be sent when Exely breaker OPEN"

    hr_breaker_present = "hotelrunner:exely-conn-X" in provider_failover._breakers
    assert hr_breaker_present is False, "Namespaces must not collide"


# ══════════════════════════════════════════════════════════════════════
# T6b — Concurrent HALF_OPEN admission is bounded by half_open_max_calls
# (regression guard for non-atomic is_available + record_success race)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t6b_half_open_admission_is_bounded_under_concurrency():
    import asyncio as _asyncio

    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-CONC", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.side_effect = HotelRunnerTemporaryError("boom")
        for _ in range(5):
            await provider.push_daily_inventory(payload)

        breaker = provider_failover.get_breaker("hotelrunner:conn-CONC")
        assert breaker.state == CircuitState.OPEN
        breaker.last_failure_time = time.time() - (breaker.recovery_timeout + 1)

        gate = _asyncio.Event()

        async def _slow_put(*a, **kw):
            await gate.wait()
            return _ok_http(data={"ok": True})

        mput.side_effect = _slow_put

        n_concurrent = breaker.half_open_max_calls + 5
        tasks = [
            _asyncio.create_task(provider.push_daily_inventory(payload))
            for _ in range(n_concurrent)
        ]
        await _asyncio.sleep(0.05)
        gate.set()
        results = await _asyncio.gather(*tasks)

    admitted = sum(1 for r in results if r.error_type != "CircuitOpen")
    rejected = sum(1 for r in results if r.error_type == "CircuitOpen")
    assert admitted == breaker.half_open_max_calls, (
        f"Expected exactly {breaker.half_open_max_calls} admitted in HALF_OPEN, got {admitted} "
        f"(rejected={rejected}, total={n_concurrent})"
    )
    assert rejected == n_concurrent - breaker.half_open_max_calls


# ══════════════════════════════════════════════════════════════════════
# T7 — push_date_range_inventory shares the same per-connection breaker
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_t7_hr_daily_and_daterange_share_same_breaker():
    provider = HotelRunnerProvider(
        token="t" * 12, hr_id="hr1", connection_id="conn-S", max_retries=0,
    )
    payload = {"inv_code": "STD", "date": "2026-06-01", "availability": 5}
    range_payload = {"inv_code": "STD", "start_date": "2026-06-01", "end_date": "2026-06-05", "availability": 5}

    with patch.object(provider._client, "put", new_callable=AsyncMock) as mput:
        mput.side_effect = HotelRunnerTemporaryError("boom")
        for _ in range(5):
            await provider.push_daily_inventory(payload)

        breaker = provider_failover.get_breaker("hotelrunner:conn-S")
        assert breaker.state == CircuitState.OPEN

        calls_before = mput.await_count
        r = await provider.push_date_range_inventory(range_payload)

    assert r.success is False
    assert r.error_type == "CircuitOpen"
    assert mput.await_count == calls_before


# ══════════════════════════════════════════════════════════════════════
# Cross-instance shared state (Task #396)
# ══════════════════════════════════════════════════════════════════════
#
# These tests stand up a minimal in-memory async Redis fake whose ``eval``
# re-implements the three Lua scripts shipped in the store (matched by
# script-constant *identity*, so the test exercises the real script text /
# arg order, not a re-typed copy). This proves the distributed admission and
# accounting semantics without a live Redis (fakeredis is not installed).

from domains.channel_manager.provider_failover import CircuitBreaker
from infra.circuit_breaker_store import (
    _ACQUIRE_LUA,
    _RECORD_FAILURE_LUA,
    _RECORD_SUCCESS_LUA,
    circuit_breaker_store,
)


class _FakeRedis:
    """In-memory async stand-in for the pooled Redis client.

    Implements only the surface the store uses: ``eval`` (the 3 Lua
    scripts), ``hgetall``, ``delete`` and ``scan``. ``now`` is a settable
    monotonic clock standing in for the Redis server ``TIME`` so tests can
    fast-forward past the recovery timeout deterministically.
    """

    def __init__(self):
        self._store: dict[str, dict[str, str]] = {}
        self.now = 1_000_000

    async def eval(self, script, numkeys, *args):
        keys = args[:numkeys]
        argv = args[numkeys:]
        key = keys[0]
        h = self._store.setdefault(key, {})
        if script is _ACQUIRE_LUA:
            return self._acquire(h, argv)
        if script is _RECORD_FAILURE_LUA:
            return self._record_failure(h, argv)
        if script is _RECORD_SUCCESS_LUA:
            return self._record_success(h, argv)
        raise AssertionError("unknown script passed to fake eval")

    def _acquire(self, h, argv):
        recovery_timeout = int(argv[0])
        half_open_max = int(argv[1])
        state = h.get("state")
        if not state or state == "closed":
            return ["closed", 1]
        if state == "open":
            lft = float(h.get("last_failure_time", "0") or "0")
            if lft > 0 and (self.now - lft) >= recovery_timeout:
                h.update(state="half_open", half_open_calls="1", success_count="0")
                return ["half_open", 1]
            return ["open", 0]
        if state == "half_open":
            hoc = int(h.get("half_open_calls", "0") or "0")
            if hoc < half_open_max:
                h["half_open_calls"] = str(hoc + 1)
                return ["half_open", 1]
            return ["half_open", 0]
        return ["closed", 1]

    def _record_failure(self, h, argv):
        failure_threshold = int(argv[0])
        state = h.get("state") or "closed"
        h["last_failure_time"] = str(self.now)
        if state == "half_open":
            h["state"] = "open"
            return "open"
        fc = int(h.get("failure_count", "0") or "0") + 1
        h["failure_count"] = str(fc)
        if fc >= failure_threshold:
            h["state"] = "open"
            return "open"
        return state

    def _record_success(self, h, argv):
        half_open_max = int(argv[0])
        state = h.get("state") or "closed"
        if state == "half_open":
            sc = int(h.get("success_count", "0") or "0") + 1
            h["success_count"] = str(sc)
            if sc >= half_open_max:
                h.update(
                    state="closed", failure_count="0",
                    success_count="0", half_open_calls="0",
                )
                return "closed"
            return "half_open"
        fc = int(h.get("failure_count", "0") or "0")
        if fc > 0:
            h["failure_count"] = str(fc - 1)
        return state

    async def hgetall(self, key):
        return dict(self._store.get(key, {}))

    async def delete(self, key):
        self._store.pop(key, None)

    async def scan(self, cursor=0, match=None, count=100):
        prefix = (match or "").rstrip("*")
        keys = [k for k in self._store if k.startswith(prefix)]
        return 0, keys


@pytest.fixture
def shared_store():
    """Wire the singleton store to a fresh fake, tear it down after."""
    fake = _FakeRedis()
    circuit_breaker_store.set_redis(fake)
    try:
        yield fake
    finally:
        circuit_breaker_store.set_redis(None)


# ── CB1 — One worker tripping OPEN fail-fasts the whole fleet ──────────

@pytest.mark.asyncio
async def test_cb1_open_propagates_across_instances(shared_store):
    # Two CircuitBreaker objects = two workers' views of the same connection.
    worker_a = CircuitBreaker("hotelrunner:cross-1", failure_threshold=5)
    worker_b = CircuitBreaker("hotelrunner:cross-1", failure_threshold=5)

    # Worker A sees the outage and trips the breaker.
    for _ in range(5):
        await worker_a.record_failure()
    assert worker_a.state == CircuitState.OPEN

    # Worker B never saw a single failure locally, yet must fail-fast because
    # admission reads the shared Redis state.
    assert worker_b.state == CircuitState.CLOSED  # local field still stale...
    admitted = await worker_b.try_acquire()
    assert admitted is False, "OPEN must propagate to a worker that saw no failures"
    assert worker_b.state == CircuitState.OPEN  # ...synced from shared view


# ── CB2 — Fleet-wide HALF_OPEN probe budget is bounded, not per-worker ──

@pytest.mark.asyncio
async def test_cb2_half_open_admission_bounded_fleet_wide(shared_store):
    half_open_max = 3
    workers = [
        CircuitBreaker(
            "hotelrunner:cap-1", failure_threshold=5,
            recovery_timeout=60, half_open_max_calls=half_open_max,
        )
        for _ in range(6)
    ]

    # Trip OPEN on one worker.
    for _ in range(5):
        await workers[0].record_failure()
    assert workers[0].state == CircuitState.OPEN

    # Advance the (shared) clock past the recovery timeout.
    shared_store.now += 61

    # Six different workers each attempt one probe — the fleet must admit at
    # most half_open_max total, not half_open_max per worker.
    admissions = [await w.try_acquire() for w in workers]
    assert sum(1 for a in admissions if a) == half_open_max
    assert sum(1 for a in admissions if not a) == len(workers) - half_open_max


# ── CB3 — Fleet HALF_OPEN success closes for everyone ─────────────────

@pytest.mark.asyncio
async def test_cb3_half_open_success_closes_shared(shared_store):
    half_open_max = 3
    worker_a = CircuitBreaker(
        "hotelrunner:recov-1", failure_threshold=5,
        recovery_timeout=60, half_open_max_calls=half_open_max,
    )
    worker_b = CircuitBreaker(
        "hotelrunner:recov-1", failure_threshold=5,
        recovery_timeout=60, half_open_max_calls=half_open_max,
    )
    for _ in range(5):
        await worker_a.record_failure()
    shared_store.now += 61

    # half_open_max successful probes (spread across workers) close the fleet.
    for i in range(half_open_max):
        w = worker_a if i % 2 == 0 else worker_b
        assert await w.try_acquire() is True
        await w.record_success()

    # A fresh worker now sees CLOSED and is admitted.
    worker_c = CircuitBreaker(
        "hotelrunner:recov-1", failure_threshold=5,
        recovery_timeout=60, half_open_max_calls=half_open_max,
    )
    assert await worker_c.try_acquire() is True
    assert worker_c.state == CircuitState.CLOSED


# ── CB4 — Redis-absent: pure in-process fallback still trips/blocks ────

@pytest.mark.asyncio
async def test_cb4_redis_absent_local_fallback():
    # No shared_store fixture → store stays disabled.
    assert circuit_breaker_store.enabled is False
    breaker = CircuitBreaker("hotelrunner:fallback-1", failure_threshold=5)
    for _ in range(5):
        await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert await breaker.try_acquire() is False


# ── CB5 — reset_breaker_shared clears local AND shared state ───────────

@pytest.mark.asyncio
async def test_cb5_reset_shared_clears_redis(shared_store):
    key = "hotelrunner:reset-1"
    worker = CircuitBreaker(key, failure_threshold=5)
    # Use the registry breaker so reset_breaker_shared resets the same object.
    provider_failover._breakers[key] = worker
    for _ in range(5):
        await worker.record_failure()
    assert worker.state == CircuitState.OPEN
    assert await circuit_breaker_store.get_state(key) is not None

    await provider_failover.reset_breaker_shared(key)

    assert worker.state == CircuitState.CLOSED
    assert await circuit_breaker_store.get_state(key) is None
    # A new worker now sees a clean CLOSED breaker.
    fresh = CircuitBreaker(key, failure_threshold=5)
    assert await fresh.try_acquire() is True


# ══════════════════════════════════════════════════════════════════════
# Super-admin cache cross-context eviction (Task #396)
# ══════════════════════════════════════════════════════════════════════
#
# The super-admin lookup cache must drop an entry on the SAME user-doc
# invalidation that profile/password/role changes already broadcast — both
# locally (security.invalidate_user_doc_cache) and remotely (the pub/sub
# listener). Only the eviction crosses Redis; super_admin=True is always
# re-read from the DB (fail-closed).


def test_supercache_local_evict_on_user_doc_invalidation():
    import time as _t

    from core import entitlement
    from core.security import invalidate_user_doc_cache

    entitlement._SUPER_ADMIN_CACHE["user-local-1"] = (True, _t.time())
    entitlement._SUPER_ADMIN_CACHE["user-local-2"] = (False, _t.time())

    # The same call that profile/password/role mutations trigger.
    invalidate_user_doc_cache("user-local-1")

    assert "user-local-1" not in entitlement._SUPER_ADMIN_CACHE
    # Targeted evict must not touch unrelated users.
    assert "user-local-2" in entitlement._SUPER_ADMIN_CACHE
    entitlement._SUPER_ADMIN_CACHE.clear()


@pytest.mark.asyncio
async def test_supercache_remote_evict_via_pubsub_listener():
    import json as _json
    import time as _t

    from core import entitlement
    from infra.auth_cache_pubsub import CHANNEL_USER, auth_cache_pubsub

    entitlement._SUPER_ADMIN_CACHE["user-remote-1"] = (True, _t.time())

    # Simulate a broadcast from ANOTHER worker (different instance id, so the
    # loop guard does not skip it).
    message = {
        "channel": CHANNEL_USER,
        "data": _json.dumps({"id": "user-remote-1", "instance": "other-worker"}),
    }
    await auth_cache_pubsub._handle_message(message)

    assert "user-remote-1" not in entitlement._SUPER_ADMIN_CACHE
    entitlement._SUPER_ADMIN_CACHE.clear()


def test_supercache_full_flush_on_empty_target():
    import time as _t

    from core import entitlement

    entitlement._SUPER_ADMIN_CACHE["a"] = (True, _t.time())
    entitlement._SUPER_ADMIN_CACHE["b"] = (False, _t.time())
    entitlement._local_evict_super_admin(None)
    assert entitlement._SUPER_ADMIN_CACHE == {}
