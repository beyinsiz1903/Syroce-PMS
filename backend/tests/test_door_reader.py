"""Targeted tests for the internal door-reader verification endpoint.

Pinned contract (POST /api/internal/door-reader/verify):
  * Service-key authenticated, fail-closed:
      - DOOR_READER_SERVICE_KEY unset            -> 503 (service not configured)
      - missing / wrong X-Door-Reader-Key header -> 401
  * The server is the sole authority; the plaintext QR is never trusted:
      - JWT signature/expiry checked server-side (expired -> denied "expired",
        garbage -> denied "invalid_token").
      - The presented token is bound to the *currently active* stored key, so a
        rotated/refreshed token is denied "revoked" even if its signature is
        still valid.
      - Tenant is resolved from the stored key, never from client input.
      - Booking is re-validated in-house server-side (checked-out / cancelled ->
        denied "not_in_house" and the stale key is expired).
      - Optional physical-door binding: a reader that declares its room rejects a
        key for a different room ("wrong_room").
  * No guest PII (name / e-mail) is ever returned.

Uses real JWTs (same JWT_SECRET the app uses) plus an in-memory fake DB so it
runs without a live Mongo, mirroring tests/test_digital_key.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from core.security import generate_time_based_qr_token
from routers import door_reader as dr


# ---------------------------------------------------------------------------
# In-memory fakes (same shape as test_digital_key.py)
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


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return _strip(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        from types import SimpleNamespace
        return SimpleNamespace(inserted_id=doc.get("id"))

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
        self.bookings = _Coll()
        self.digital_keys = _Coll()
        self.lockdown_state = _Coll()
        self.physical_access_logs = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


TENANT = "tenant-A"
SERVICE_KEY = "test-door-reader-key"


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(dr, "get_system_db", lambda: fake)
    monkeypatch.setenv("DOOR_READER_SERVICE_KEY", SERVICE_KEY)
    return fake


def _future(hours=24):
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _past(hours=24):
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _seed_booking(fake, booking_id="B1", status="checked_in", check_out=None,
                  room="101", tenant=TENANT, guest_id="G1"):
    fake.bookings.docs.append({
        "id": booking_id, "tenant_id": tenant, "guest_id": guest_id,
        "status": status, "check_out": check_out or _future(), "room_number": room,
    })


def _seed_key(fake, token, booking_id="B1", status="active", room="101",
              tenant=TENANT, guest_id="G1"):
    fake.digital_keys.docs.append({
        "id": "k1", "key_id": "ABCD1234", "tenant_id": tenant,
        "booking_id": booking_id, "guest_id": guest_id, "room_number": room,
        "token": token, "status": status, "expires_at": _future(), "last_used": None,
    })
    return token


def _req(token, device_id=None, room_number=None):
    return dr.DoorReaderVerifyRequest(token=token, device_id=device_id, room_number=room_number)


async def _call(req, key=SERVICE_KEY):
    return await dr.verify_door_reader(req, x_door_reader_key=key)


# ---------------------------------------------------------------------------
# Auth (fail-closed)
# ---------------------------------------------------------------------------
async def test_unconfigured_service_returns_503(_patch, monkeypatch):
    monkeypatch.delenv("DOOR_READER_SERVICE_KEY", raising=False)
    with pytest.raises(dr.HTTPException) as exc:
        await _call(_req("anything"))
    assert exc.value.status_code == 503


async def test_missing_key_unauthorized(_patch):
    with pytest.raises(dr.HTTPException) as exc:
        await _call(_req("anything"), key=None)
    assert exc.value.status_code == 401


async def test_wrong_key_unauthorized(_patch):
    with pytest.raises(dr.HTTPException) as exc:
        await _call(_req("anything"), key="nope")
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Grant
# ---------------------------------------------------------------------------
async def test_granted_for_active_in_house_key(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch)
    _seed_key(_patch, tok)
    out = await _call(_req(tok, device_id="reader-7"))
    assert out["access"] == "granted"
    assert out["room_number"] == "101"
    assert out["booking_id"] == "B1"
    assert out["guest_id"] == "G1"
    # No PII leak.
    assert "name" not in out and "email" not in out and "tenant_id" not in out
    # Audit recorded on the active key.
    assert _patch.digital_keys.docs[0]["last_used"] is not None
    assert _patch.digital_keys.docs[0]["last_device_id"] == "reader-7"


async def test_room_match_when_reader_declares_room(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch)
    _seed_key(_patch, tok)
    out = await _call(_req(tok, room_number="101"))
    assert out["access"] == "granted"


# ---------------------------------------------------------------------------
# Deny (fail-closed)
# ---------------------------------------------------------------------------
async def test_denied_invalid_token(_patch):
    out = await _call(_req("not-a-jwt"))
    assert out == {"access": "denied", "reason": "invalid_token"}


async def test_denied_expired_token(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=-1)
    _seed_booking(_patch)
    _seed_key(_patch, tok)
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "expired"


async def test_denied_revoked_token_when_key_not_active(_patch):
    """Signature still valid, but the stored key was rotated/expired."""
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch)
    _seed_key(_patch, tok, status="expired")
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "revoked"


async def test_denied_not_in_house_and_key_expired(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch, status="checked_out")
    _seed_key(_patch, tok)
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "not_in_house"
    # Stale key is expired server-side so it can never grant again.
    assert _patch.digital_keys.docs[0]["status"] == "expired"


async def test_denied_past_checkout(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch, check_out=_past())
    _seed_key(_patch, tok)
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "not_in_house"


async def test_denied_wrong_room(_patch):
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch, room="101")
    _seed_key(_patch, tok, room="101")
    out = await _call(_req(tok, room_number="999"))
    assert out["access"] == "denied"
    assert out["reason"] == "wrong_room"


async def test_denied_booking_not_found(_patch):
    """Active key exists but the booking is gone -> fail-closed."""
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_key(_patch, tok)  # key only, no booking
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "booking_not_found"


async def test_grant_denied_when_key_rotated_mid_verify(_patch, monkeypatch):
    """Revocation race: the key is read as active, but a concurrent refresh
    expires it before the final CAS update -> must deny, never grant."""
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    _seed_booking(_patch)
    _seed_key(_patch, tok)

    orig_update_one = _patch.digital_keys.update_one

    async def _race(flt, update, upsert=False):
        # Simulate a concurrent rotation expiring the active key right before
        # the CAS grant update runs.
        for d in _patch.digital_keys.docs:
            d["status"] = "expired"
        return await orig_update_one(flt, update, upsert)

    monkeypatch.setattr(_patch.digital_keys, "update_one", _race)
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "revoked"


async def test_tenant_taken_from_key_not_token(_patch):
    """The token carries no tenant; the booking must be matched on the key's
    tenant. A booking with the same id under a different tenant must not satisfy
    the lookup."""
    tok = generate_time_based_qr_token("B1", expiry_hours=10)
    # Booking only exists under tenant-B, but the active key is tenant-A.
    _seed_booking(_patch, tenant="tenant-B")
    _seed_key(_patch, tok, tenant=TENANT)
    out = await _call(_req(tok))
    assert out["access"] == "denied"
    assert out["reason"] == "booking_not_found"
