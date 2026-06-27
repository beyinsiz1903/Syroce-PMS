"""Targeted tests for the guest digital-key flow (web guest portal).

Pinned contract:
  * GET /guest/digital-key/{booking_id}
      - Owner + tenant scoped: a guest only ever resolves their own booking.
      - Auto-mints a key for an in-house (checked_in) stay; returns the trimmed
        guest-facing contract (key_id, room_number, guest_id, token, status,
        expires_at) and never leaks internal _id / tenant_id.
      - Fail-closed: not checked_in / past checkout -> 404, stale active key
        is expired server-side.
  * POST /guest/digital-key/{booking_id}/refresh
      - Owner + tenant enforced (regression guard for the prior IDOR where any
        booking_id minted a working key): a non-owner / unknown booking -> 404,
        no key minted, no crash.
      - Rotates: previous active keys are expired, a fresh bound key is minted.

Mirrors tests/test_laundry_orders.py's in-memory fake-DB approach so they run
without a live Mongo.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.guest import operations_router as op


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------
def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


class _Cursor:
    def __init__(self, docs):
        self._docs = [_strip(d) for d in docs]

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()

    async def to_list(self, n=None):
        return self._docs[:n] if n else self._docs


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0

    def find(self, flt=None, proj=None):
        flt = flt or {}
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return _strip(d)
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, flt, update):
        n = 0
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                n += 1
        return SimpleNamespace(matched_count=n, modified_count=n)


class _FakeDB:
    def __init__(self):
        self.guests = _Coll()
        self.bookings = _Coll()
        self.digital_keys = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


TENANT = "tenant-A"


def _guest_user(email="guest@a.com", tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role="guest_app",
        is_super_admin=False, name="Guest", email=email,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(op, "db", fake)
    # Hermetic, deterministic token (avoids JWT_SECRET dependency in tests).
    monkeypatch.setattr(op, "generate_time_based_qr_token", lambda bid, **k: f"tok-{bid}")
    # Match guests on plaintext email in the fake store.
    monkeypatch.setattr(
        "security.encrypted_lookup.build_guest_pii_query",
        lambda field, val: {field: val},
    )
    return fake


def _future(hours=24):
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _past(hours=24):
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _seed_guest(fake, gid="G1", email="guest@a.com", tenant=TENANT):
    fake.guests.docs.append({"id": gid, "tenant_id": tenant, "email": email})


def _seed_booking(fake, booking_id="B1", guest_id="G1", status="checked_in",
                  check_out=None, room="101", tenant=TENANT):
    fake.bookings.docs.append({
        "id": booking_id, "tenant_id": tenant, "guest_id": guest_id,
        "status": status, "check_out": check_out or _future(), "room_number": room,
    })


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
async def test_get_mints_key_for_checked_in_owner(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch)
    out = await op.get_digital_key("B1", current_user=_guest_user())
    assert out["status"] == "active"
    assert out["room_number"] == "101"
    assert out["guest_id"] == "G1"
    assert out["token"] == "tok-B1"
    # Trimmed contract — no internal leakage.
    assert "id" not in out and "tenant_id" not in out and "last_used" not in out
    assert _patch.digital_keys.insert_calls == 1


async def test_get_reuses_existing_active_key(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch)
    await op.get_digital_key("B1", current_user=_guest_user())
    out = await op.get_digital_key("B1", current_user=_guest_user())
    assert out["status"] == "active"
    # No second key minted.
    assert _patch.digital_keys.insert_calls == 1


async def test_get_not_checked_in_returns_404(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch, status="confirmed")
    with pytest.raises(HTTPException) as exc:
        await op.get_digital_key("B1", current_user=_guest_user())
    assert exc.value.status_code == 404
    assert _patch.digital_keys.insert_calls == 0


async def test_get_expires_stale_key_past_checkout(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch, check_out=_past())
    # A stale active key exists from when the guest was in-house.
    _patch.digital_keys.docs.append({
        "id": "k0", "key_id": "OLD", "tenant_id": TENANT, "booking_id": "B1",
        "guest_id": "G1", "room_number": "101", "token": "tok-B1",
        "status": "active", "expires_at": _past(),
    })
    with pytest.raises(HTTPException) as exc:
        await op.get_digital_key("B1", current_user=_guest_user())
    assert exc.value.status_code == 404
    # Stale key expired server-side.
    assert _patch.digital_keys.docs[0]["status"] == "expired"


async def test_get_backfills_token_on_legacy_key(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch)
    _patch.digital_keys.docs.append({
        "id": "k0", "key_id": "LEG", "tenant_id": TENANT, "booking_id": "B1",
        "guest_id": "G1", "room_number": "101", "status": "active",
        "expires_at": _future(),
    })
    out = await op.get_digital_key("B1", current_user=_guest_user())
    assert out["token"] == "tok-B1"
    assert _patch.digital_keys.docs[0]["token"] == "tok-B1"


async def test_get_other_guest_booking_returns_404(_patch):
    _seed_guest(_patch, gid="G1", email="guest@a.com")
    _seed_guest(_patch, gid="G2", email="other@a.com")
    _seed_booking(_patch, booking_id="B2", guest_id="G2")
    with pytest.raises(HTTPException) as exc:
        await op.get_digital_key("B2", current_user=_guest_user(email="guest@a.com"))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# REFRESH — IDOR regression guards
# ---------------------------------------------------------------------------
async def test_refresh_owner_rotates_key(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch)
    # Existing active key to rotate out.
    _patch.digital_keys.docs.append({
        "id": "k0", "key_id": "OLD", "tenant_id": TENANT, "booking_id": "B1",
        "guest_id": "G1", "room_number": "101", "token": "tok-B1",
        "status": "active", "expires_at": _future(),
    })
    out = await op.refresh_digital_key("B1", current_user=_guest_user())
    assert out["status"] == "active"
    assert out["key_id"] != "OLD"
    # Old key expired, exactly one new key minted.
    assert _patch.digital_keys.docs[0]["status"] == "expired"
    assert _patch.digital_keys.insert_calls == 1


async def test_refresh_other_guest_booking_denied_no_mint(_patch):
    """Regression: previously any booking_id minted a working key (IDOR)."""
    _seed_guest(_patch, gid="G1", email="guest@a.com")
    _seed_guest(_patch, gid="G2", email="other@a.com")
    _seed_booking(_patch, booking_id="B2", guest_id="G2")
    with pytest.raises(HTTPException) as exc:
        await op.refresh_digital_key("B2", current_user=_guest_user(email="guest@a.com"))
    assert exc.value.status_code == 404
    # No key minted for the victim's booking.
    assert _patch.digital_keys.insert_calls == 0
    assert _patch.digital_keys.docs == []


async def test_refresh_unknown_booking_no_crash(_patch):
    _seed_guest(_patch)
    with pytest.raises(HTTPException) as exc:
        await op.refresh_digital_key("ZZZ", current_user=_guest_user())
    assert exc.value.status_code == 404
    assert _patch.digital_keys.insert_calls == 0


async def test_refresh_past_checkout_denied(_patch):
    _seed_guest(_patch)
    _seed_booking(_patch, check_out=_past())
    with pytest.raises(HTTPException) as exc:
        await op.refresh_digital_key("B1", current_user=_guest_user())
    assert exc.value.status_code == 404
    assert _patch.digital_keys.insert_calls == 0


async def test_token_expiry_bound_to_checkout(_patch, monkeypatch):
    """Signed token lifetime must not outlive the stay (<= remaining to checkout)."""
    captured: dict = {}

    def _rec(bid, expiry_hours=72, **k):
        captured["hours"] = expiry_hours
        return f"tok-{bid}"

    monkeypatch.setattr(op, "generate_time_based_qr_token", _rec)
    _seed_guest(_patch)
    _seed_booking(_patch, check_out=_future(hours=10))
    await op.get_digital_key("B1", current_user=_guest_user())
    assert 0 < captured["hours"] <= 10.0


async def test_token_expiry_capped_at_72h_for_long_stay(_patch, monkeypatch):
    captured: dict = {}

    def _rec(bid, expiry_hours=72, **k):
        captured["hours"] = expiry_hours
        return f"tok-{bid}"

    monkeypatch.setattr(op, "generate_time_based_qr_token", _rec)
    _seed_guest(_patch)
    _seed_booking(_patch, check_out=_future(hours=240))
    await op.get_digital_key("B1", current_user=_guest_user())
    assert captured["hours"] == 72.0
