"""Task-55 — peer login surfaces brute-force throttle.

Verifies the per-IP and per-account `SlidingWindowThrottle` policies
wired into:

  * `POST /api/agency-portal/auth/login`  (super_admin + agency staff)
  * `POST /api/supplies-market/vendor/login`  (vendor accounts)

Both endpoints bcrypt-verify a password and were previously uncovered
by `LOGIN_IP`/`LOGIN_ACCOUNT`, leaving an unbounded credential-spray
window. The new policies are `always_on=True` so DISABLE_AUTH_THROTTLE
cannot mask the protection in stress/pen runs.

These are unit tests against the throttle module directly — no live
backend required. We exercise a fresh non-always_on `SlidingWindowThrottle`
to stay on the deterministic in-memory deque path regardless of whether
Mongo/Redis are reachable in the test environment.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from security.auth_throttle import (
    AGENCY_LOGIN_ACCOUNT,
    AGENCY_LOGIN_IP,
    VENDOR_LOGIN_ACCOUNT,
    VENDOR_LOGIN_IP,
    SlidingWindowThrottle,
    enforce,
    normalize_identity,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_peer_login_policies_registered():
    """All four policies exist with the spec-mandated caps + always_on."""
    # Per-IP layer mirrors LOGIN_IP (20 / 60s).
    assert AGENCY_LOGIN_IP.max == 20
    assert VENDOR_LOGIN_IP.max == 20
    assert int(AGENCY_LOGIN_IP.window.total_seconds()) == 60
    assert int(VENDOR_LOGIN_IP.window.total_seconds()) == 60
    # Per-account layer mirrors LOGIN_ACCOUNT (10 / 300s).
    assert AGENCY_LOGIN_ACCOUNT.max == 10
    assert VENDOR_LOGIN_ACCOUNT.max == 10
    assert int(AGENCY_LOGIN_ACCOUNT.window.total_seconds()) == 300
    assert int(VENDOR_LOGIN_ACCOUNT.window.total_seconds()) == 300
    # always_on so the dev escape hatch cannot mask the protection.
    for t in (
        AGENCY_LOGIN_IP,
        AGENCY_LOGIN_ACCOUNT,
        VENDOR_LOGIN_IP,
        VENDOR_LOGIN_ACCOUNT,
    ):
        assert t.always_on is True


def test_peer_login_throttles_have_distinct_namespaces():
    """Each surface must use a distinct Redis/Mongo key namespace so an
    agency-login burst doesn't accidentally evict vendor-login budget."""
    names = {
        AGENCY_LOGIN_IP.name,
        AGENCY_LOGIN_ACCOUNT.name,
        VENDOR_LOGIN_IP.name,
        VENDOR_LOGIN_ACCOUNT.name,
    }
    assert len(names) == 4


def test_per_account_blocks_eleventh_attempt():
    """10 attempts pass per account, the 11th raises 429 + Retry-After."""
    # Mirror the AGENCY/VENDOR_LOGIN_ACCOUNT policy on a fresh
    # non-always_on throttle so the test exercises the deterministic
    # in-memory deque path regardless of Mongo availability.
    t = SlidingWindowThrottle(
        max_requests=10, window_seconds=300, name="t_peer_login_acct_test"
    )
    key = "agency_login_acct:alice@example.com"

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "giris denemesi")
        return exc_info.value

    err = _run(_drive())
    assert err.status_code == 429
    assert "Retry-After" in err.headers
    retry_after = int(err.headers["Retry-After"])
    assert 1 <= retry_after <= 300


def test_per_ip_blocks_twentyfirst_attempt():
    """20 attempts pass per IP, the 21st raises 429."""
    t = SlidingWindowThrottle(
        max_requests=20, window_seconds=60, name="t_peer_login_ip_test"
    )
    key = "agency_login_ip:198.51.100.7"

    async def _drive():
        for _ in range(20):
            await enforce(t, key, "giris denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "giris denemesi")
        return exc_info.value

    err = _run(_drive())
    assert err.status_code == 429


def test_successful_login_drains_counter():
    """Successful credential verify must reset() the window so a
    legitimate user who mistyped before succeeding isn't penalised."""
    t = SlidingWindowThrottle(
        max_requests=10, window_seconds=300, name="t_peer_login_reset"
    )
    key = "agency_login_acct:bob@example.com"

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        # Simulate the post-success reset that the router runs.
        await t.reset(key)
        # Full budget restored.
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "giris denemesi")
        return exc_info.value

    err = _run(_drive())
    assert err.status_code == 429


def test_per_account_isolation_across_emails():
    """One account's exhausted budget must not block a different account
    on the same throttle policy."""
    t = SlidingWindowThrottle(
        max_requests=10, window_seconds=300, name="t_peer_login_acct_isolation"
    )

    async def _drive():
        for _ in range(10):
            await enforce(t, "agency_login_acct:alice@example.com", "giris denemesi")
        # Bob's budget is untouched.
        for _ in range(10):
            await enforce(t, "agency_login_acct:bob@example.com", "giris denemesi")
        with pytest.raises(HTTPException):
            await enforce(t, "agency_login_acct:alice@example.com", "giris denemesi")
        with pytest.raises(HTTPException):
            await enforce(t, "agency_login_acct:bob@example.com", "giris denemesi")

    _run(_drive())


def test_email_normalization_buckets_case_and_whitespace_variants():
    """The router passes the email through `normalize_identity` before
    bucketing, so `Alice@Example.COM`, ` alice@example.com `, and the
    Unicode fullwidth `Ａｌｉｃｅ@example.com` must all collapse to the
    same throttle bucket — otherwise an attacker trivially evades the
    per-account cap by varying case."""
    canonical = normalize_identity("alice@example.com")
    assert normalize_identity("Alice@Example.COM") == canonical
    assert normalize_identity(" alice@example.com ") == canonical
    assert normalize_identity("Ａｌｉｃｅ@example.com") == canonical


class _FakeThrottleHits:
    """Minimal in-list stand-in for the Mongo `throttle_hits` collection,
    implementing only the four ops `_check_mongo`/`reset` use."""

    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def count_documents(self, q):
        key = q["key"]
        gt = q.get("score", {}).get("$gt")
        return sum(
            1 for d in self.docs
            if d["key"] == key and (gt is None or d["score"] > gt)
        )

    async def delete_one(self, q):
        _id = q["_id"]
        self.docs = [d for d in self.docs if d["_id"] != _id]

    async def delete_many(self, q):
        key = q["key"]
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["key"] != key]
        return type("R", (), {"deleted_count": before - len(self.docs)})()

    async def find_one(self, q, sort=None, projection=None):
        key = q["key"]
        gt = q.get("score", {}).get("$gt")
        rows = [
            d for d in self.docs
            if d["key"] == key and (gt is None or d["score"] > gt)
        ]
        if not rows:
            return None
        if sort:
            field, direction = sort[0]
            rows.sort(key=lambda d: d[field], reverse=direction < 0)
        return rows[0]


class _FakeRawDB:
    def __init__(self):
        self.throttle_hits = _FakeThrottleHits()


def test_mongo_backed_reset_clears_throttle_hits(monkeypatch):
    """Regression for the success-drain no-op: `always_on` throttles record
    hits in the shared Mongo `throttle_hits` collection, so `reset()` MUST
    delete from Mongo too. Before the fix `reset()` only touched Redis +
    in-memory, leaving the Mongo counter at cap — the live 98D spec saw the
    (cap+1)th post-success attempt trip 429 immediately (trip_index=0).

    This drives the real Mongo backend (via a fake `_raw_db`) end to end:
    10 hits → reset → 10 more must pass → 11th raises. Without the Mongo
    delete in reset() the second batch would 429 on its first attempt."""
    import core.database as _coredb
    import security.auth_throttle as at

    fake_db = _FakeRawDB()
    monkeypatch.setattr(_coredb, "_raw_db", fake_db, raising=False)

    async def _mongo_index_ready():
        return True

    # Pin the Mongo path on; never fall through to Redis/in-memory.
    monkeypatch.setattr(at, "_ensure_mongo_throttle_indexes", _mongo_index_ready)

    async def _no_redis():
        return None

    monkeypatch.setattr(at, "_get_redis", _no_redis)

    t = SlidingWindowThrottle(
        max_requests=10,
        window_seconds=300,
        always_on=True,
        name="t_peer_login_mongo_reset",
    )
    key = "agency_login_acct:mongo-reset@example.com"

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        # Mongo backend now holds 10 hits for this key.
        assert len(fake_db.throttle_hits.docs) == 10
        await t.reset(key)
        # Post-success drain must have emptied the Mongo counter.
        remaining = [d for d in fake_db.throttle_hits.docs if d["key"].endswith(key)]
        assert remaining == [], f"reset() left {len(remaining)} Mongo hits"
        # Full budget restored — 10 pass, 11th trips.
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "giris denemesi")
        return exc_info.value

    err = _run(_drive())
    assert err.status_code == 429


def test_disable_auth_throttle_ignored_for_always_on(monkeypatch):
    """DISABLE_AUTH_THROTTLE must NOT bypass these throttles — they are
    `always_on=True` precisely so stress/pen tests measure the real
    production guarantee."""
    monkeypatch.setenv("DISABLE_AUTH_THROTTLE", "1")
    monkeypatch.setenv("APP_ENV", "development")

    t = SlidingWindowThrottle(
        max_requests=10,
        window_seconds=300,
        always_on=True,
        name="t_peer_login_always_on",
    )
    key = "agency_login_acct:always-on@example.com"

    # Force the in-memory fallback path so the test stays deterministic
    # when MONGO_URL is unset in the test environment.
    import security.auth_throttle as at

    async def _mongo_index_unavailable():
        return False

    monkeypatch.setattr(at, "_ensure_mongo_throttle_indexes", _mongo_index_unavailable)

    async def _drive():
        for _ in range(10):
            await enforce(t, key, "giris denemesi")
        with pytest.raises(HTTPException) as exc_info:
            await enforce(t, key, "giris denemesi")
        return exc_info.value

    err = _run(_drive())
    assert err.status_code == 429
