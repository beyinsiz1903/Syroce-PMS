"""Wave 4 § rate_limit_boundary — SlidingWindowThrottle policy assertions.

These tests assert the *policy*, not a guess: a fresh throttle with a known
cap eventually returns 429 with a Retry-After header, normal sub-cap usage is
never blocked, and distinct keys (per-IP vs per-account) are counted
independently. They run against the in-memory fallback path (Redis absent in
the test environment), which is deterministic.

Note: `enforce()` has a dev escape hatch (`DISABLE_AUTH_THROTTLE=1` in
dev/test). The boundary tests therefore exercise `throttle.check()` directly
for the cap math, and explicitly clear the escape hatch when asserting the
429 + Retry-After contract of `enforce()`.
"""

import pytest

from security.auth_throttle import (
    LOGIN_ACCOUNT,
    LOGIN_IP,
    SlidingWindowThrottle,
    enforce,
)


def test_main_login_policies_are_cross_instance_always_on():
    """WATCH E#11 regression — the main `/api/auth/login` per-IP and
    per-account throttles MUST be `always_on=True` (Mongo-backed,
    cross-instance) so a wrong-credential burst fanned out across Replit
    autoscale instances still trips the cap. They were the last login
    surfaces left on the per-instance Redis/in-memory backend while every
    peer (AGENCY/VENDOR/CASHIER/TWOFA/RESET) had already been promoted; a
    60-request spray distributed across N instances saw ~60/N < cap and
    never returned 429 (Run #204 rate_limit_boundary P2). Caps mirror the
    peer login policies; namespaces are stable + distinct."""
    assert LOGIN_IP.max == 20
    assert int(LOGIN_IP.window.total_seconds()) == 60
    assert LOGIN_ACCOUNT.max == 10
    assert int(LOGIN_ACCOUNT.window.total_seconds()) == 300
    assert LOGIN_IP.always_on is True
    assert LOGIN_ACCOUNT.always_on is True
    assert LOGIN_IP.name == "login_ip"
    assert LOGIN_ACCOUNT.name == "login_account"
    assert LOGIN_IP.name != LOGIN_ACCOUNT.name


@pytest.mark.asyncio
async def test_burst_eventually_blocked():
    t = SlidingWindowThrottle(max_requests=3, window_seconds=60, name="wave4-burst")
    # First `max` requests pass.
    for _ in range(3):
        ok, retry = await t.check("ip:1.2.3.4")
        assert ok is True
        assert retry == 0
    # The next one is blocked with a positive retry-after.
    ok, retry = await t.check("ip:1.2.3.4")
    assert ok is False
    assert retry >= 1


@pytest.mark.asyncio
async def test_normal_usage_not_blocked():
    t = SlidingWindowThrottle(max_requests=5, window_seconds=60, name="wave4-normal")
    for _ in range(5):
        ok, _retry = await t.check("ip:9.9.9.9")
        assert ok is True


@pytest.mark.asyncio
async def test_per_key_separation():
    # Distinct keys (e.g. per-IP vs per-account) must not share a counter.
    t = SlidingWindowThrottle(max_requests=2, window_seconds=60, name="wave4-sep")
    assert (await t.check("ip:a"))[0] is True
    assert (await t.check("ip:a"))[0] is True
    assert (await t.check("ip:a"))[0] is False  # ip:a exhausted
    # A different key starts fresh.
    assert (await t.check("acct:user-1"))[0] is True
    assert (await t.check("acct:user-1"))[0] is True
    assert (await t.check("acct:user-1"))[0] is False


@pytest.mark.asyncio
async def test_reset_drains_counter():
    t = SlidingWindowThrottle(max_requests=1, window_seconds=60, name="wave4-reset")
    assert (await t.check("ip:r"))[0] is True
    assert (await t.check("ip:r"))[0] is False
    await t.reset("ip:r")
    assert (await t.check("ip:r"))[0] is True


@pytest.mark.asyncio
async def test_enforce_raises_429_with_retry_after(monkeypatch):
    # Ensure the dev escape hatch cannot mask the policy.
    monkeypatch.delenv("DISABLE_AUTH_THROTTLE", raising=False)
    t = SlidingWindowThrottle(max_requests=1, window_seconds=60, name="wave4-enforce")
    await enforce(t, "ip:e", label="giris denemesi")  # first allowed
    with pytest.raises(Exception) as ei:
        await enforce(t, "ip:e", label="giris denemesi")
    exc = ei.value
    assert getattr(exc, "status_code", None) == 429
    assert "Retry-After" in getattr(exc, "headers", {})
    assert int(exc.headers["Retry-After"]) >= 1
