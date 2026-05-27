"""Task-120 — cashier peer-verify PIN-gate brute-force throttle.

Verifies the per-user-id and per-IP `SlidingWindowThrottle` policies wired
into `POST /api/cashier/peer-verify`:

  * 10 attempts inside the window pass throttle.check()
  * 11th attempt is rejected with HTTP 429 + Retry-After header
  * Successful PIN verify drains the counter (reset() empties window)
  * always_on=True so the dev DISABLE_AUTH_THROTTLE escape hatch is ignored
  * Per-user and per-IP buckets are independent

Unit tests against the throttle module directly — no live backend required.
The in-memory deque path is exercised by constructing a fresh non-always_on
throttle so the test is deterministic regardless of whether Mongo/Redis
are reachable in the test environment.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from security.auth_throttle import (
    CASHIER_PEER_VERIFY_IP,
    CASHIER_PEER_VERIFY_USER,
    SlidingWindowThrottle,
    enforce,
)


def test_peer_verify_throttle_policies_registered():
    """Both policies exist with the spec-mandated 10-attempt cap."""
    assert CASHIER_PEER_VERIFY_USER.max == 10
    assert CASHIER_PEER_VERIFY_IP.max == 10
    # 15-minute window — matches the established handover-pattern.
    assert int(CASHIER_PEER_VERIFY_USER.window.total_seconds()) == 900
    assert int(CASHIER_PEER_VERIFY_IP.window.total_seconds()) == 900
    # always_on so DISABLE_AUTH_THROTTLE cannot mask the protection in
    # stress runs or production smoke tests.
    assert CASHIER_PEER_VERIFY_USER.always_on is True
    assert CASHIER_PEER_VERIFY_IP.always_on is True


def test_sliding_window_blocks_eleventh_attempt():
    """Ten attempts pass, the eleventh raises 429 with Retry-After."""
    t = SlidingWindowThrottle(max_requests=10, window_seconds=900, name="t_peer_verify_test")
    key = "peer_verify:user-under-test"

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "PIN denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "PIN denemesi")
        return exc_info.value

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429
    assert "Retry-After" in err.headers
    retry_after = int(err.headers["Retry-After"])
    assert 1 <= retry_after <= 900


def test_sliding_window_reset_drains_counter():
    """A successful PIN verify must drain the window so the legitimate
    operator isn't penalised for prior typos."""
    t = SlidingWindowThrottle(max_requests=10, window_seconds=900, name="t_peer_verify_reset")
    key = "peer_verify:user-reset"

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "PIN denemesi")
        # 11th would 429 — reset first.
        await t.reset(key)
        # After reset, a full new budget of 10 is available.
        for _ in range(10):
            await enforce(t, key, "PIN denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "PIN denemesi")
        return exc_info.value

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429


def test_disable_auth_throttle_ignored_for_always_on(monkeypatch):
    """The dev DISABLE_AUTH_THROTTLE escape hatch must NOT bypass the
    peer-verify throttle — it's `always_on=True` precisely so stress/pen
    tests measure the real production guarantee."""
    monkeypatch.setenv("DISABLE_AUTH_THROTTLE", "1")
    monkeypatch.setenv("APP_ENV", "development")

    t = SlidingWindowThrottle(
        max_requests=10, window_seconds=900, always_on=True, name="t_peer_verify_always_on"
    )
    key = "peer_verify:always-on-user"

    # Force the in-memory fallback path: temporarily neutralise the Mongo
    # path so the test stays deterministic when MONGO_URL is unset.
    import security.auth_throttle as at

    async def _mongo_index_unavailable():
        return False

    monkeypatch.setattr(at, "_ensure_mongo_throttle_indexes", _mongo_index_unavailable)

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "PIN denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "PIN denemesi")
        return exc_info.value

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429


def test_separate_keys_have_independent_budgets():
    """Per-user-id and per-IP buckets must be independent — one operator
    using up their budget must not block a different operator on the
    same throttle policy."""
    t = SlidingWindowThrottle(max_requests=10, window_seconds=900, name="t_peer_verify_isolation")

    async def _drive():
        for _ in range(10):
            await enforce(t, "peer_verify:alice", "PIN denemesi")
        # Bob's budget is untouched.
        for _ in range(10):
            await enforce(t, "peer_verify:bob", "PIN denemesi")
        with pytest.raises(HTTPException):
            await enforce(t, "peer_verify:alice", "PIN denemesi")
        with pytest.raises(HTTPException):
            await enforce(t, "peer_verify:bob", "PIN denemesi")

    asyncio.new_event_loop().run_until_complete(_drive())
