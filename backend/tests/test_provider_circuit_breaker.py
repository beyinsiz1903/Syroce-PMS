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
