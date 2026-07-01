"""Targeted tests for the Laundry order → folio flow.

Pinned contract (Kademe 1, Modül 1):
  * Delivering an order on an OPEN guest folio posts one folio_charge per line,
    tagged charge_category="laundry", with a dedup source
    (source_laundry_order_id, line_no). Balance is recomputed via the ledger
    recalc (never $inc).
  * Server recomputes line totals from the catalog price * service multiplier;
    the client-supplied total is never trusted.
  * Fail-closed: no active booking / no open guest folio -> charge NOT posted,
    routed to a visible laundry_late_charges record; folio_charge.charged=False.
  * Idempotent: charging the same order twice never double-posts (dedup index).
  * Workflow guard: invalid status transitions are rejected (409).
  * RBAC: order mutations restricted to staff roles; catalog to admin tier.

Mirrors tests/test_minibar_consume.py's in-memory fake-DB approach so they run
without a live Mongo.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms import laundry_router as lr


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
        self.laundry_items = _Coll()
        self.laundry_orders = _Coll()
        self.laundry_late_charges = _Coll()
        self.folios = _Coll()
        self.folio_charges = _Coll(
            unique_keys=("tenant_id", "source_laundry_order_id", "line_no")
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
    monkeypatch.setattr(lr, "db", fake)

    async def _noop_index():
        return None

    monkeypatch.setattr(lr, "_ensure_laundry_charge_index", _noop_index)

    async def _balance(db, tenant_id, folio_id):
        return 0.0

    monkeypatch.setattr(lr, "_recalc_folio_balance", _balance)
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


def _seed_item(fake, code, name, price):
    fake.laundry_items.docs.append({
        "id": f"id-{code}", "tenant_id": TENANT, "code": code, "name": name,
        "price": price, "active": True,
    })


def _order_payload(lines, room="101", service="wash_iron", booking_id=None):
    return lr.OrderIn(
        room_number=room,
        service_type=service,
        booking_id=booking_id,
        items=[lr.OrderLine(code=c, quantity=q) for c, q in lines],
    )


async def _create(fake, payload, user):
    return (await lr.create_order(payload=payload, current_user=user))["order"]


async def _patch_status(order_id, status, user):
    return await lr.update_order_status(
        order_id=order_id, payload=lr.StatusUpdate(status=status), current_user=user
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_create_order_recomputes_total_server_side(_patch):
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    _seed_item(_patch, "pants", "Pantolon", 40.0)
    # dry_clean multiplier = 1.5 → (2*30 + 1*40) * 1.5 = 150
    order = await _create(
        _patch, _order_payload([("shirt", 2), ("pants", 1)], service="dry_clean"),
        _user("front_desk"),
    )
    assert order["total"] == 150.0
    assert order["status"] == "pending"
    assert order["service_multiplier"] == 1.5
    assert len(order["items"]) == 2


async def test_deliver_posts_charge_per_line_to_open_folio(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    _seed_item(_patch, "pants", "Pantolon", 40.0)

    order = await _create(
        _patch, _order_payload([("shirt", 2), ("pants", 1)]), _user("front_desk")
    )
    res = await _patch_status(order["id"], "delivered", _user("housekeeping"))

    assert res["status"] == "delivered"
    assert res["folio_charge"]["charged"] is True
    assert _patch.folio_charges.insert_calls == 2
    charges = _patch.folio_charges.docs
    assert all(c["charge_category"] == "laundry" for c in charges)
    assert all(c["voided"] is False for c in charges)
    assert {c["line_no"] for c in charges} == {0, 1}
    assert len({c["source_laundry_order_id"] for c in charges}) == 1
    assert sorted(c["total"] for c in charges) == [40.0, 60.0]
    # Order flagged folio_charged.
    assert _patch.laundry_orders.docs[0]["folio_charged"] is True


async def test_deliver_resolves_booking_by_room_number(_patch):
    _seed_room(_patch, number="202")
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    # No booking_id supplied -> resolved via room number.
    order = await _create(_patch, _order_payload([("shirt", 1)], room="202"), _user("front_desk"))
    res = await _patch_status(order["id"], "delivered", _user("front_desk"))
    assert res["folio_charge"]["charged"] is True
    assert _patch.folio_charges.insert_calls == 1


async def test_deliver_no_open_folio_routes_to_late_charge(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    # Only a CLOSED folio -> must not write to it.
    _patch.folios.docs.append({
        "id": "F1", "tenant_id": TENANT, "booking_id": "B1",
        "folio_type": "guest", "status": "closed", "guest_id": "G1",
    })
    _seed_item(_patch, "shirt", "Gomlek", 30.0)

    order = await _create(_patch, _order_payload([("shirt", 3)]), _user("front_desk"))
    res = await _patch_status(order["id"], "delivered", _user("front_desk"))

    assert res["folio_charge"]["charged"] is False
    assert res["folio_charge"]["reason"] == "no_active_booking_or_folio"
    assert _patch.folio_charges.insert_calls == 0
    lc = _patch.laundry_late_charges.docs
    assert len(lc) == 1
    assert lc[0]["status"] == "pending_review"
    assert lc[0]["total"] == 90.0


async def test_deliver_no_active_booking_fails_closed(_patch):
    _seed_room(_patch)
    # No booking seeded -> no active guest.
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    order = await _create(_patch, _order_payload([("shirt", 1)]), _user("front_desk"))
    res = await _patch_status(order["id"], "delivered", _user("front_desk"))
    assert res["folio_charge"]["charged"] is False
    assert res["folio_charge"]["reason"] == "no_active_booking_or_folio"
    assert _patch.folio_charges.insert_calls == 0


async def test_charge_is_idempotent_no_double_post(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    order = await _create(_patch, _order_payload([("shirt", 2)]), _user("front_desk"))
    order_doc = _patch.laundry_orders.docs[0]

    r1 = await lr._charge_order_to_folio(TENANT, "u1", order_doc)
    r2 = await lr._charge_order_to_folio(TENANT, "u1", order_doc)

    assert r1["charged"] is True
    assert r2["charged"] is True
    # Second pass writes nothing new — dedup index rejects re-insert.
    assert _patch.folio_charges.insert_calls == 1


async def test_invalid_transition_rejected(_patch):
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    order = await _create(_patch, _order_payload([("shirt", 1)]), _user("front_desk"))
    # delivered then trying to move out of terminal state -> 409
    _patch.laundry_orders.docs[0]["status"] = "delivered"
    with pytest.raises(HTTPException) as exc:
        await _patch_status(order["id"], "in_progress", _user("front_desk"))
    assert exc.value.status_code == 409


async def test_status_update_rbac_denies_guest(_patch):
    _seed_item(_patch, "shirt", "Gomlek", 30.0)
    order = await _create(_patch, _order_payload([("shirt", 1)]), _user("front_desk"))
    with pytest.raises(HTTPException) as exc:
        await _patch_status(order["id"], "in_progress", _user("guest"))
    assert exc.value.status_code == 403


async def test_create_order_invalid_item_rejected(_patch):
    # No items seeded.
    with pytest.raises(HTTPException) as exc:
        await _create(_patch, _order_payload([("ghost", 1)]), _user("front_desk"))
    assert exc.value.status_code == 400


# ── Catalog RBAC ──
async def test_catalog_create_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await lr.create_item(
            lr.LaundryItemIn(code="shirt", name="Gomlek", price=30.0),
            current_user=_user("front_desk"),
        )
    assert exc.value.status_code == 403


async def test_catalog_create_allows_admin(_patch):
    out = await lr.create_item(
        lr.LaundryItemIn(code="Shirt", name="Gomlek", price=30.0),
        current_user=_user("admin"),
    )
    assert out["item"]["code"] == "shirt"  # normalized lower
    assert out["item"]["tenant_id"] == TENANT
    assert _patch.laundry_items.insert_calls == 1
