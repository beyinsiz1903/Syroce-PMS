"""Targeted tests for the Minibar consume → folio flow.

Pinned contract (Kademe 1, Modül 1):
  * Consume on an OPEN guest folio posts one folio_charge per line, tagged
    charge_category="minibar", with a dedup source (source_minibar_log_id,
    line_no). Balance is recomputed via the ledger recalc (never $inc).
  * Fail-closed: no active (checked-in) booking on the room -> 409, no charge.
  * Folio not open -> never writes to a closed folio; routes to a visible
    minibar_late_charges record (status pending_review), posted_to_folio=False.
  * RBAC: consume restricted to staff roles; catalog mutations to admin tier.
  * Idempotency-key replay returns the prior consumption, no re-post.

These mirror tests/test_folio_idempotency.py's in-memory fake-DB approach so
they run without a live Mongo.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms import minibar_router as mr


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


class _FakeDB:
    def __init__(self):
        self.minibar_items = _Coll()
        self.minibar_consumptions = _Coll(unique_keys=("tenant_id", "idempotency_key"))
        self.minibar_late_charges = _Coll()
        self.folios = _Coll()
        self.folio_charges = _Coll(
            unique_keys=("tenant_id", "source_minibar_log_id", "line_no")
        )
        self.bookings = _Coll()
        self.rooms = _Coll()
        self.inventory = _Coll()
        self.inventory_movements = _Coll()

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

    monkeypatch.setattr(mr, "db", fake)

    async def _noop_index():
        return None

    monkeypatch.setattr(mr, "_ensure_minibar_charge_index", _noop_index)
    monkeypatch.setattr(mr, "_ensure_minibar_consumption_index", _noop_index)

    async def _balance(db, tenant_id, folio_id):
        return 0.0

    monkeypatch.setattr(mr, "_recalc_folio_balance", _balance)
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


def _seed_item(fake, item_id, name, price, inv=None):
    fake.minibar_items.docs.append({
        "id": item_id, "tenant_id": TENANT, "name": name, "price": price,
        "category": "drink", "active": True, "inventory_product_id": inv,
    })


def _consume_payload(lines, room_id="R1", key=None):
    return mr.ConsumeIn(
        room_id=room_id,
        lines=[mr.ConsumeLine(item_id=i, quantity=q) for i, q in lines],
        idempotency_key=key,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_consume_posts_one_charge_per_line_to_open_folio(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0)
    _seed_item(_patch, "I2", "Cola", 30.0)

    res = await consume_call(
        _consume_payload([("I1", 2), ("I2", 1)]), _user("front_desk")
    )

    assert res["posted_to_folio"] is True
    assert _patch.folio_charges.insert_calls == 2
    charges = _patch.folio_charges.docs
    assert all(c["charge_category"] == "minibar" for c in charges)
    assert all(c["voided"] is False for c in charges)
    # Distinct dedup line numbers, shared source log id.
    assert {c["line_no"] for c in charges} == {0, 1}
    assert len({c["source_minibar_log_id"] for c in charges}) == 1
    # Line totals: 2*20 and 1*30.
    assert sorted(c["total"] for c in charges) == [30.0, 40.0]
    assert _patch.minibar_consumptions.docs[0]["status"] == "posted"


async def test_consume_fail_closed_without_active_booking(_patch):
    _seed_room(_patch)
    _seed_item(_patch, "I1", "Su", 20.0)
    # No booking seeded -> no active guest.
    with pytest.raises(HTTPException) as exc:
        await consume_call(_consume_payload([("I1", 1)]), _user("front_desk"))
    assert exc.value.status_code == 409
    assert _patch.folio_charges.insert_calls == 0
    assert _patch.minibar_consumptions.docs == []


async def test_consume_routes_to_late_charge_when_no_open_folio(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    # Only a CLOSED folio exists -> must not write to it.
    _patch.folios.docs.append({
        "id": "F1", "tenant_id": TENANT, "booking_id": "B1",
        "folio_type": "guest", "status": "closed", "guest_id": "G1",
    })
    _seed_item(_patch, "I1", "Su", 20.0)

    res = await consume_call(_consume_payload([("I1", 3)]), _user("housekeeping"))

    assert res["posted_to_folio"] is False
    assert _patch.folio_charges.insert_calls == 0
    lc = _patch.minibar_late_charges.docs
    assert len(lc) == 1
    assert lc[0]["status"] == "pending_review"
    assert lc[0]["total"] == 60.0
    assert _patch.minibar_consumptions.docs[0]["status"] == "late_charge"


async def test_consume_rbac_denies_non_staff(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0)
    with pytest.raises(HTTPException) as exc:
        await consume_call(_consume_payload([("I1", 1)]), _user("guest"))
    assert exc.value.status_code == 403
    assert _patch.folio_charges.insert_calls == 0


async def test_consume_idempotency_key_returns_prior(_patch):
    _patch.minibar_consumptions.docs.append({
        "id": "L1", "tenant_id": TENANT, "idempotency_key": "K1",
        "status": "posted", "total": 99.0,
    })
    res = await consume_call(
        _consume_payload([("I1", 1)], key="K1"), _user("front_desk")
    )
    assert res.get("idempotent") is True
    assert res["consumption"]["id"] == "L1"
    # No booking/folio lookups should have inserted anything.
    assert _patch.folio_charges.insert_calls == 0


async def test_consume_invalid_item_rejected(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    # No items seeded.
    with pytest.raises(HTTPException) as exc:
        await consume_call(_consume_payload([("GHOST", 1)]), _user("front_desk"))
    assert exc.value.status_code == 400
    assert _patch.folio_charges.insert_calls == 0


async def test_consume_depletes_linked_inventory(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0, inv="P1")
    _patch.inventory.docs.append({
        "id": "P1", "tenant_id": TENANT, "quantity": 10, "product_name": "Su",
    })

    res = await consume_call(_consume_payload([("I1", 3)]), _user("front_desk"))

    assert res["posted_to_folio"] is True
    assert _patch.inventory.docs[0]["quantity"] == 7
    mv = _patch.inventory_movements.docs
    assert len(mv) == 1
    assert mv[0]["quantity"] == -3
    assert mv[0]["reason"] == "minibar_consumption"


async def test_consume_insufficient_stock_does_not_block_billing(_patch):
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0, inv="P1")
    _patch.inventory.docs.append({
        "id": "P1", "tenant_id": TENANT, "quantity": 1, "product_name": "Su",
    })

    res = await consume_call(_consume_payload([("I1", 5)]), _user("front_desk"))

    # Billing succeeds; stock untouched and reported (not silent).
    assert res["posted_to_folio"] is True
    assert _patch.folio_charges.insert_calls == 1
    assert _patch.inventory.docs[0]["quantity"] == 1
    assert res["stock"][0]["status"] == "insufficient_stock"


async def test_consume_retry_after_partial_failure_does_not_double_charge(_patch):
    """Charge'lar yazıldıktan SONRA akış patlasa (consumption insert vb.), aynı
    idempotency_key ile retry deterministik log_id üretir → folio_charges dedup
    index satırları reddeder → çift faturalama olmaz."""
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0)

    key = "RETRY-KEY"
    log_id = mr._stable_log_id(TENANT, key)
    # Simüle: önceki (başarısız) denemede charge zaten yazılmış, ama consumption
    # logu yazılamamış (prior-check'i bulamayacak).
    _patch.folio_charges.docs.append({
        "id": "pre", "tenant_id": TENANT, "source_minibar_log_id": log_id,
        "line_no": 0, "charge_category": "minibar", "total": 20.0, "voided": False,
    })

    res = await consume_call(_consume_payload([("I1", 1)], key=key), _user("front_desk"))

    # Retry yeni charge YAZMAMALI (dedup index reddeder).
    assert _patch.folio_charges.insert_calls == 0
    assert res["posted_to_folio"] is True


async def test_consume_concurrent_same_key_single_consumption(_patch):
    """Üst prior-check'i iki istek de geçse, consumption insert'te DB-level
    (tenant, idempotency_key) unique kaybedeni ayırır; charge'lar dedup ile tek."""
    _seed_room(_patch)
    _seed_booking(_patch)
    _seed_open_folio(_patch)
    _seed_item(_patch, "I1", "Su", 20.0)

    key = "CONC-KEY"
    r1 = await consume_call(_consume_payload([("I1", 1)], key=key), _user("front_desk"))
    # İkinci istek üst prior-check'i bulur ve idempotent döner; yine de garanti
    # olarak charge sayısı 1'de kalmalı.
    r2 = await consume_call(_consume_payload([("I1", 1)], key=key), _user("front_desk"))

    assert _patch.folio_charges.insert_calls == 1
    assert len(_patch.minibar_consumptions.docs) == 1
    assert r2.get("idempotent") is True
    assert r1["consumption"]["id"] == r2["consumption"]["id"]


# ── Catalog RBAC ──
async def test_catalog_create_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await mr.create_item(
            mr.MinibarItemIn(name="Su", price=20.0), current_user=_user("front_desk")
        )
    assert exc.value.status_code == 403


async def test_catalog_create_allows_admin(_patch):
    out = await mr.create_item(
        mr.MinibarItemIn(name="Su", price=20.0), current_user=_user("admin")
    )
    assert out["item"]["name"] == "Su"
    assert out["item"]["tenant_id"] == TENANT
    assert _patch.minibar_items.insert_calls == 1


# Convenience wrapper to call the route fn with the keyword contract.
async def consume_call(payload, user):
    return await mr.consume(payload=payload, current_user=user)
