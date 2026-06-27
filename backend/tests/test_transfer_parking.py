"""Targeted tests for the Transfer & Parking resource → folio flow.

Pinned contract (Kademe 1, Modül 2):
  * Slot-lock: a resource cannot be double-booked for an overlapping slot. The
    second overlapping booking is rejected (409) and claims nothing.
  * Folio: booking a resource on an OPEN guest folio posts one idempotent
    charge (dedup source_transport_booking_id, line_no); balance via ledger
    recalc (never $inc).
  * Server computes totals (price * days / per-trip); client total never trusted.
  * Fail-closed: no active booking / no open guest folio -> charge NOT posted,
    routed to a visible transport_late_charges record; resource still reserved.
  * Idempotency-key replay returns the prior booking, no re-charge.
  * Cancellation releases slot locks so the slot can be re-booked.
  * RBAC: bookings restricted to staff roles; catalog to admin tier.

Mirrors tests/test_minibar_consume.py's in-memory fake-DB approach.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms import transfer_parking_router as tr


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        out = [{kk: vv for kk, vv in d.items() if kk != "_id"} for d in self._docs]
        return out[:n] if n else out


class _Coll:
    def __init__(self, unique_keys=None):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self.unique_keys = unique_keys

    def find(self, flt=None, proj=None):
        flt = flt or {}
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, proj=None, sort=None):
        matches = [d for d in self.docs if _match(d, flt)]
        if not matches:
            return None
        return {kk: vv for kk, vv in matches[0].items() if kk != "_id"}

    async def insert_one(self, doc):
        if self.unique_keys:
            for d in self.docs:
                if all(d.get(k) == doc.get(k) for k in self.unique_keys):
                    raise DuplicateKeyError("duplicate compound key")
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            newdoc = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            newdoc.update(update.get("$set", {}))
            newdoc.update(update.get("$setOnInsert", {}))
            self.docs.append(newdoc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.transport_resources = _Coll()
        self.transport_bookings = _Coll()
        self.transport_slot_locks = _Coll(
            unique_keys=("tenant_id", "resource_id", "slot_key")
        )
        self.transport_late_charges = _Coll()
        self.folios = _Coll()
        self.folio_charges = _Coll(
            unique_keys=("tenant_id", "source_transport_booking_id", "line_no")
        )
        self.bookings = _Coll()
        self.rooms = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


TENANT = "tenant-A"


def _user(role="front_desk", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin, name="Staff", email="s@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(tr, "db", fake)

    async def _noop_index():
        return None

    monkeypatch.setattr(tr, "_ensure_slot_lock_index", _noop_index)
    monkeypatch.setattr(tr, "_ensure_charge_index", _noop_index)

    async def _balance(db, tenant_id, folio_id):
        return 0.0

    monkeypatch.setattr(tr, "_recalc_folio_balance", _balance)
    return fake


def _seed_room(fake, room_id="R1", number="101"):
    fake.rooms.docs.append({"id": room_id, "tenant_id": TENANT, "room_number": number})


def _seed_booking(fake, room_id="R1", booking_id="B1", status="checked_in"):
    fake.bookings.docs.append({
        "id": booking_id, "tenant_id": TENANT, "room_id": room_id,
        "status": status, "guest_id": "G1",
    })


def _seed_open_folio(fake, booking_id="B1", folio_id="F1"):
    fake.folios.docs.append({
        "id": folio_id, "tenant_id": TENANT, "booking_id": booking_id,
        "folio_type": "guest", "status": "open", "guest_id": "G1",
    })


def _seed_resource(fake, rid, name, kind, price):
    fake.transport_resources.docs.append({
        "id": rid, "tenant_id": TENANT, "name": name, "kind": kind,
        "price": price, "capacity": 1, "active": True,
    })


async def _create_booking(payload, user):
    return await tr.create_booking(payload=payload, current_user=user)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_parking_booking_charges_open_folio_server_total(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)

    res = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=3),
        _user("front_desk"),
    )
    # 50 * 3 days = 150
    assert res["booking"]["total"] == 150.0
    assert res["folio_charge"]["charged"] is True
    assert _patch.folio_charges.insert_calls == 1
    c = _patch.folio_charges.docs[0]
    assert c["charge_category"] == "parking"
    assert c["total"] == 150.0
    assert c["line_no"] == 0
    # 3 day slots locked.
    assert len(_patch.transport_slot_locks.docs) == 3


async def test_transfer_booking_single_slot_charge(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "V1", "VIP Araç", "transfer_vehicle", 200.0)

    res = await _create_booking(
        tr.BookingIn(resource_id="V1", room_number="101",
                     pickup_at=datetime(2026, 7, 1, 14, 30)),
        _user("concierge"),
    )
    assert res["booking"]["total"] == 200.0
    assert res["folio_charge"]["charged"] is True
    assert _patch.folio_charges.docs[0]["charge_category"] == "transfer"
    assert len(_patch.transport_slot_locks.docs) == 1


async def test_double_booking_overlap_rejected(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)

    await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=2),
        _user("front_desk"),
    )
    # Overlapping second booking (2026-07-02 collides) -> 409, nothing claimed.
    with pytest.raises(HTTPException) as exc:
        await _create_booking(
            tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-02", num_days=2),
            _user("front_desk"),
        )
    assert exc.value.status_code == 409
    # Only the first booking's 2 locks remain (no orphan from rolled-back claim).
    assert len(_patch.transport_slot_locks.docs) == 2


async def test_non_overlapping_same_resource_ok(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)

    await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=1),
        _user("front_desk"),
    )
    res2 = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-02", num_days=1),
        _user("front_desk"),
    )
    assert res2["folio_charge"]["charged"] is True
    assert len(_patch.transport_slot_locks.docs) == 2


async def test_no_open_folio_routes_to_late_charge(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _patch.folios.docs.append({
        "id": "F1", "tenant_id": TENANT, "booking_id": "B1",
        "folio_type": "guest", "status": "closed", "guest_id": "G1",
    })
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)

    res = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=2),
        _user("front_desk"),
    )
    assert res["folio_charge"]["charged"] is False
    assert res["folio_charge"]["reason"] == "no_active_booking_or_folio"
    assert _patch.folio_charges.insert_calls == 0
    lc = _patch.transport_late_charges.docs
    assert len(lc) == 1
    assert lc[0]["status"] == "pending_review"
    assert lc[0]["total"] == 100.0
    # Resource still reserved.
    assert len(_patch.transport_slot_locks.docs) == 2


async def test_no_active_booking_fails_closed(_patch):
    _seed_room(_patch)
    # No PMS booking -> no active guest.
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)
    res = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=1),
        _user("front_desk"),
    )
    assert res["folio_charge"]["charged"] is False
    assert _patch.folio_charges.insert_calls == 0


async def test_idempotency_key_returns_prior_no_recharge(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "V1", "VIP Araç", "transfer_vehicle", 200.0)

    payload = tr.BookingIn(
        resource_id="V1", room_number="101",
        pickup_at=datetime(2026, 7, 1, 9, 0), idempotency_key="K1",
    )
    r1 = await _create_booking(payload, _user("front_desk"))
    r2 = await _create_booking(payload, _user("front_desk"))

    assert r2.get("idempotent") is True
    assert r1["booking"]["id"] == r2["booking"]["id"]
    # No second charge / no second lock.
    assert _patch.folio_charges.insert_calls == 1
    assert len(_patch.transport_slot_locks.docs) == 1


async def test_cancel_releases_slot_locks(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)

    res = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=2),
        _user("front_desk"),
    )
    assert len(_patch.transport_slot_locks.docs) == 2

    out = await tr.cancel_booking(
        transport_booking_id=res["booking"]["id"], current_user=_user("front_desk")
    )
    assert out["status"] == "cancelled"
    assert len(_patch.transport_slot_locks.docs) == 0

    # Slot now re-bookable.
    res2 = await _create_booking(
        tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=1),
        _user("front_desk"),
    )
    assert res2["folio_charge"]["charged"] is True


async def test_booking_rbac_denies_guest(_patch):
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)
    with pytest.raises(HTTPException) as exc:
        await _create_booking(
            tr.BookingIn(resource_id="P1", room_number="101", start_date="2026-07-01", num_days=1),
            _user("guest"),
        )
    assert exc.value.status_code == 403


async def test_missing_schedule_rejected(_patch):
    _seed_resource(_patch, "P1", "Otopark A", "parking_spot", 50.0)
    # parking without start_date/num_days -> 400
    with pytest.raises(HTTPException) as exc:
        await _create_booking(
            tr.BookingIn(resource_id="P1", room_number="101"), _user("front_desk")
        )
    assert exc.value.status_code == 400


# ── Catalog RBAC ──
async def test_catalog_create_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await tr.create_resource(
            tr.ResourceIn(name="Otopark A", kind="parking_spot", price=50.0),
            current_user=_user("front_desk"),
        )
    assert exc.value.status_code == 403


async def test_catalog_create_allows_admin(_patch):
    out = await tr.create_resource(
        tr.ResourceIn(name="Otopark A", kind="parking_spot", price=50.0),
        current_user=_user("admin"),
    )
    assert out["resource"]["kind"] == "parking_spot"
    assert out["resource"]["tenant_id"] == TENANT


async def test_catalog_invalid_kind_rejected(_patch):
    with pytest.raises(HTTPException) as exc:
        await tr.create_resource(
            tr.ResourceIn(name="X", kind="spaceship", price=10.0),
            current_user=_user("admin"),
        )
    assert exc.value.status_code == 400
