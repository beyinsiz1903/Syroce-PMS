"""Task-51 — cashier shift-handover password-gate brute-force throttle.

Verifies the per-user-id and per-IP `SlidingWindowThrottle` policies wired
into `POST /api/cashier/handover-shift`:

  * 6 attempts inside the window pass throttle.check()
  * 7th attempt is rejected with HTTP 429 + Retry-After header
  * Successful credential verify drains the counter (reset() empties window)
  * always_on=True so the dev DISABLE_AUTH_THROTTLE escape hatch is ignored

These are unit tests against the throttle module directly — no live backend
required. The in-memory deque path is exercised by constructing a fresh
non-always_on throttle so the test is deterministic regardless of whether
Mongo/Redis are reachable in the test environment.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi import HTTPException

from security.auth_throttle import (
    CASHIER_HANDOVER_IP,
    CASHIER_HANDOVER_USER,
    SlidingWindowThrottle,
    enforce,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.new_event_loop().run_until_complete(coro)


def test_handover_throttle_policies_registered():
    """Both policies exist with the spec-mandated 6-attempt cap."""
    assert CASHIER_HANDOVER_USER.max == 6
    assert CASHIER_HANDOVER_IP.max == 6
    # 15-minute window — long enough to defeat slow brute-force, short
    # enough that a legitimate operator who locked themselves out can
    # retry within the same shift.
    assert int(CASHIER_HANDOVER_USER.window.total_seconds()) == 900
    assert int(CASHIER_HANDOVER_IP.window.total_seconds()) == 900
    # always_on so DISABLE_AUTH_THROTTLE cannot mask the protection in
    # stress runs or production smoke tests.
    assert CASHIER_HANDOVER_USER.always_on is True
    assert CASHIER_HANDOVER_IP.always_on is True


def test_sliding_window_blocks_seventh_attempt():
    """Six attempts pass, the seventh raises 429 with Retry-After."""
    # Use a fresh non-always_on throttle so we stay on the deterministic
    # in-memory deque path regardless of Mongo/Redis availability.
    t = SlidingWindowThrottle(max_requests=6, window_seconds=900, name="t_handover_test")
    key = "handover:user-under-test"

    async def _drive():
        for i in range(6):
            await enforce(t, key, "vardiya devir denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "vardiya devir denemesi")
        return exc_info.value

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429
    assert "Retry-After" in err.headers
    retry_after = int(err.headers["Retry-After"])
    assert 1 <= retry_after <= 900


def test_sliding_window_reset_drains_counter():
    """A successful gate verify must drain the window so the legitimate
    operator isn't penalised for prior typos."""
    t = SlidingWindowThrottle(max_requests=6, window_seconds=900, name="t_handover_reset")
    key = "handover:user-reset"

    async def _drive():
        for _ in range(6):
            await enforce(t, key, "vardiya devir denemesi")
        # 7th would 429 — reset first.
        await t.reset(key)
        # After reset, a full new budget of 6 is available.
        for _ in range(6):
            await enforce(t, key, "vardiya devir denemesi")
        # 7th of the second burst must now 429.
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "vardiya devir denemesi")
        return exc_info.value

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429


def test_disable_auth_throttle_ignored_for_always_on(monkeypatch):
    """The dev DISABLE_AUTH_THROTTLE escape hatch must NOT bypass the
    handover throttle — it's `always_on=True` precisely so stress/pen
    tests measure the real production guarantee."""
    monkeypatch.setenv("DISABLE_AUTH_THROTTLE", "1")
    monkeypatch.setenv("APP_ENV", "development")

    t = SlidingWindowThrottle(
        max_requests=6, window_seconds=900, always_on=True, name="t_handover_always_on"
    )
    key = "handover:always-on-user"

    async def _drive():
        for _ in range(6):
            await enforce(t, key, "vardiya devir denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "vardiya devir denemesi")
        return exc_info.value

    # Force the in-memory fallback path: temporarily neutralise the Mongo
    # path so the test stays deterministic when MONGO_URL is unset.
    import security.auth_throttle as at

    async def _mongo_index_unavailable():
        return False

    monkeypatch.setattr(at, "_ensure_mongo_throttle_indexes", _mongo_index_unavailable)

    err = asyncio.new_event_loop().run_until_complete(_drive())
    assert err.status_code == 429


def test_separate_keys_have_independent_budgets():
    """Per-user-id and per-IP buckets must be independent — one operator
    using up their budget must not block a different operator on the
    same throttle policy."""
    t = SlidingWindowThrottle(max_requests=6, window_seconds=900, name="t_handover_isolation")

    async def _drive():
        for _ in range(6):
            await enforce(t, "handover:alice", "vardiya devir denemesi")
        # Bob's budget is untouched.
        for _ in range(6):
            await enforce(t, "handover:bob", "vardiya devir denemesi")
        # Alice's 7th must 429.
        with pytest.raises(HTTPException):
            await enforce(t, "handover:alice", "vardiya devir denemesi")
        # Bob's 7th must also 429 (independent but same cap).
        with pytest.raises(HTTPException):
            await enforce(t, "handover:bob", "vardiya devir denemesi")

    asyncio.new_event_loop().run_until_complete(_drive())
