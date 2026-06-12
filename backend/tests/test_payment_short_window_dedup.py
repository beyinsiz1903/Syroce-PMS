"""Short-window auto-dedup guard (claim_short_window_dedup).

Covers the server-side anti-double-submit primitive that protects payment
endpoints which carry NO explicit Idempotency-Key/reference:

* a second identical fingerprint INSIDE the window -> rejected (duplicate),
* a stale lock OUTSIDE the window -> reclaimed via CAS delete -> acquired,
* a concurrent reclaim that loses the CAS race -> duplicate (never two winners),
* an explicit release -> the next attempt may acquire immediately,
* distinct fingerprints never collide,
* the window is env-tunable and floored at 1s.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from shared_kernel import idempotency as idem


class _FakeIdemCollection:
    """Faithful in-memory stand-in for the idempotency_keys collection."""

    def __init__(self):
        self.store: dict = {}
        self.force_delete_miss = False

    async def insert_one(self, doc):
        _id = doc["_id"]
        if _id in self.store:
            raise DuplicateKeyError("E11000 duplicate key")
        self.store[_id] = dict(doc)
        return SimpleNamespace(inserted_id=_id)

    async def find_one(self, filt):
        doc = self.store.get(filt.get("_id"))
        return dict(doc) if doc else None

    async def delete_one(self, filt):
        # Simulate a competing racer winning the reclaim CAS exactly once.
        if self.force_delete_miss:
            self.force_delete_miss = False
            return SimpleNamespace(deleted_count=0)
        _id = filt.get("_id")
        doc = self.store.get(_id)
        if not doc:
            return SimpleNamespace(deleted_count=0)
        if "created_at" in filt and doc.get("created_at") != filt["created_at"]:
            return SimpleNamespace(deleted_count=0)
        del self.store[_id]
        return SimpleNamespace(deleted_count=1)


class _FakeDB:
    def __init__(self):
        self.idempotency_keys = _FakeIdemCollection()


async def test_inside_window_is_duplicate():
    db = _FakeDB()
    first = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f"
    )
    assert first["status"] == "acquired"
    second = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f"
    )
    assert second["status"] == "duplicate"


async def test_backdated_lock_is_reclaimed():
    db = _FakeDB()
    first = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f", window_seconds=5
    )
    lock_id = first["lock_id"]
    # Age the stored lock beyond the window: a distinct, later payment.
    db.idempotency_keys.store[lock_id]["created_at"] = (
        datetime.now(UTC) - timedelta(seconds=60)
    ).isoformat()

    again = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f", window_seconds=5
    )
    assert again["status"] == "acquired"


async def test_concurrent_reclaim_cas_miss_is_duplicate():
    db = _FakeDB()
    first = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f", window_seconds=5
    )
    lock_id = first["lock_id"]
    db.idempotency_keys.store[lock_id]["created_at"] = (
        datetime.now(UTC) - timedelta(seconds=60)
    ).isoformat()
    # Another racer wins the reclaim delete first -> our CAS delete matches 0.
    db.idempotency_keys.force_delete_miss = True

    loser = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f", window_seconds=5
    )
    assert loser["status"] == "duplicate"


async def test_release_allows_immediate_retry():
    db = _FakeDB()
    first = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f"
    )
    await idem.release_idempotency(db, lock_id=first["lock_id"])
    again = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="f"
    )
    assert again["status"] == "acquired"


async def test_distinct_fingerprints_dont_collide():
    db = _FakeDB()
    a = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="100.0|cash|final"
    )
    b = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="s", fingerprint="200.0|cash|final"
    )
    assert a["status"] == "acquired"
    assert b["status"] == "acquired"


async def test_distinct_scopes_dont_collide():
    db = _FakeDB()
    a = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="folio:1", fingerprint="f"
    )
    b = await idem.claim_short_window_dedup(
        db, tenant_id="t", scope="folio:2", fingerprint="f"
    )
    assert a["status"] == "acquired"
    assert b["status"] == "acquired"


def test_window_env_override_and_floor(monkeypatch):
    monkeypatch.setenv("PAYMENT_DEDUP_WINDOW_SECONDS", "30")
    assert idem.payment_dedup_window_seconds() == 30
    # Floored at 1s so the guard can never be disabled to 0.
    monkeypatch.setenv("PAYMENT_DEDUP_WINDOW_SECONDS", "0")
    assert idem.payment_dedup_window_seconds() == 1
    # Garbage -> safe default.
    monkeypatch.setenv("PAYMENT_DEDUP_WINDOW_SECONDS", "abc")
    assert idem.payment_dedup_window_seconds() == 10
    monkeypatch.delenv("PAYMENT_DEDUP_WINDOW_SECONDS", raising=False)
    assert idem.payment_dedup_window_seconds() == 10
