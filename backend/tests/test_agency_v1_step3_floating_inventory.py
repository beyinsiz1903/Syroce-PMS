"""
Agency v1 — Floating (oda-tipi) atomik envanter claim birim testleri (ADR Karar 5,
operatör onayli "Floating + ertelenmis otomatik atama" modeli).

Saf test: gercek DB yok; sahte koleksiyonlar room_night_locks unique-index
davranisini (ayni tenant+room+night ikinci insert -> DuplicateKeyError) ve rooms/
bookings'i taklit eder. Burada SADECE seam mantigi dogrulanir: gece-bazli bos-oda
secimi, Tetris cozumu (gece farkli odalar), tukenme -> InventoryConflict(available=0)
+ kismi-claim compensation, persist (room_id=None floating). Atomik dogrulugun
kendisi (unique index) Mongo'nun garantisidir; burada SIMULE edilir, sahte-yesil yok.
"""
from __future__ import annotations

import sys
import types

import pytest
from pymongo.errors import DuplicateKeyError

import routers.agency_v1.inventory as inv


class _Cursor:
    def __init__(self, items):
        self._items = items

    async def to_list(self, n):
        return list(self._items)[:n]


class _Rooms:
    def __init__(self, rooms):
        self._rooms = rooms

    def find(self, query, proj=None):
        t = query["tenant_id"]
        rt = query.get("room_type")
        out = [
            {"id": r["id"]}
            for r in self._rooms
            if r["tenant_id"] == t
            and (rt is None or r["room_type"] == rt)
            and r.get("is_active", True) is not False
        ]
        return _Cursor(out)


class _Locks:
    def __init__(self, seed=None):
        self.docs = list(seed or [])

    def find(self, query, proj=None):
        t = query["tenant_id"]
        night = query["night_date"]
        rid_in = query["room_id"]["$in"]
        out = [
            {"room_id": d["room_id"]}
            for d in self.docs
            if d["tenant_id"] == t and d["night_date"] == night and d["room_id"] in rid_in
        ]
        return _Cursor(out)

    async def insert_one(self, doc):
        for d in self.docs:
            if (
                d["tenant_id"] == doc["tenant_id"]
                and d["room_id"] == doc["room_id"]
                and d["night_date"] == doc["night_date"]
            ):
                raise DuplicateKeyError("ux_room_night")
        self.docs.append(dict(doc))

    async def delete_many(self, query):
        t = query.get("tenant_id")
        bid = query.get("booking_id")
        before = len(self.docs)
        self.docs = [
            d for d in self.docs if not (d["tenant_id"] == t and d["booking_id"] == bid)
        ]

        class _R:
            deleted_count = before - len(self.docs)

        return _R()


class _Bookings:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self, rooms, locks_seed=None):
        self.rooms = _Rooms(rooms)
        self.room_night_locks = _Locks(locks_seed)
        self.bookings = _Bookings()


@pytest.fixture(autouse=True)
def _stub_pii(monkeypatch):
    """encrypt_booking_doc / search_normalize'i kimlik stub'a indir (saf test;
    runtime crypto config gerekmesin)."""
    enc = types.ModuleType("security.encrypted_lookup")
    enc.encrypt_booking_doc = lambda d: d
    monkeypatch.setitem(sys.modules, "security.encrypted_lookup", enc)
    norm = types.ModuleType("security.search_normalize")
    norm.apply_collection_normalized_fields = lambda d, collection=None: None
    monkeypatch.setitem(sys.modules, "security.search_normalize", norm)


def _rooms(tenant, room_type, ids):
    return [{"id": i, "tenant_id": tenant, "room_type": room_type, "is_active": True} for i in ids]


def _booking(**over):
    doc = {
        "id": "AGB-1",
        "tenant_id": "T-1",
        "room_type": "STD",
        "check_in": "2026-07-01",
        "check_out": "2026-07-04",  # 3 gece: 01,02,03
        "guest_name": "Test Guest",
        "status": "confirmed",
    }
    doc.update(over)
    return doc


@pytest.mark.asyncio
async def test_floating_success_persists_unassigned(monkeypatch):
    db = _DB(_rooms("T-1", "STD", ["R-A", "R-B"]))
    monkeypatch.setattr(inv, "db", db)

    out = await inv.claim_floating_inventory(_booking())

    assert out["room_id"] is None  # floating / pending-assignment
    assert out["allocation_source"] == "agency_floating"
    assert len(db.bookings.docs) == 1
    # 3 gece kilitlendi, hepsi bos olan ilk oda (R-A) uzerine
    locks = [d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"]
    assert len(locks) == 3
    assert {d["night_date"] for d in locks} == {"2026-07-01", "2026-07-02", "2026-07-03"}
    assert all(d["lock_type"] == "booking" for d in locks)


@pytest.mark.asyncio
async def test_floating_solves_tetris_across_rooms(monkeypatch):
    # Tetris: R-A 2.geceyi (07-02) baskasinca tutulmus; R-B 1.+3. geceler tutulmus.
    # Tek bir oda tum stay'i karsilamaz ama her gecede >=1 bos oda var -> gecmeli.
    seed = [
        {"tenant_id": "T-1", "room_id": "R-A", "night_date": "2026-07-02", "booking_id": "OTHER"},
        {"tenant_id": "T-1", "room_id": "R-B", "night_date": "2026-07-01", "booking_id": "OTHER"},
        {"tenant_id": "T-1", "room_id": "R-B", "night_date": "2026-07-03", "booking_id": "OTHER"},
    ]
    db = _DB(_rooms("T-1", "STD", ["R-A", "R-B"]), locks_seed=seed)
    monkeypatch.setattr(inv, "db", db)

    out = await inv.claim_floating_inventory(_booking())
    assert out["room_id"] is None
    locks = sorted(
        [d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"],
        key=lambda d: d["night_date"],
    )
    # 07-01 -> R-A (R-B dolu), 07-02 -> R-B (R-A dolu), 07-03 -> R-A (R-B dolu)
    assert [(d["night_date"], d["room_id"]) for d in locks] == [
        ("2026-07-01", "R-A"),
        ("2026-07-02", "R-B"),
        ("2026-07-03", "R-A"),
    ]


@pytest.mark.asyncio
async def test_floating_sold_out_night_conflict_and_compensation(monkeypatch):
    # 07-02 her iki oda da dolu -> o gece tukendi. 07-01 kismi-claim geri salinmali.
    seed = [
        {"tenant_id": "T-1", "room_id": "R-A", "night_date": "2026-07-02", "booking_id": "OTHER"},
        {"tenant_id": "T-1", "room_id": "R-B", "night_date": "2026-07-02", "booking_id": "OTHER"},
    ]
    db = _DB(_rooms("T-1", "STD", ["R-A", "R-B"]), locks_seed=seed)
    monkeypatch.setattr(inv, "db", db)

    with pytest.raises(inv.InventoryConflict) as ei:
        await inv.claim_floating_inventory(_booking())
    assert ei.value.conflict_date == "2026-07-02"
    assert ei.value.available == 0
    # Compensation: AGB-1'in hicbir kilidi kalmamali; booking persist EDILMEMELI.
    assert [d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"] == []
    assert db.bookings.docs == []
    # Baskasinin kilitleri dokunulmaz.
    assert len([d for d in db.room_night_locks.docs if d["booking_id"] == "OTHER"]) == 2


@pytest.mark.asyncio
async def test_floating_no_rooms_of_type_conflict(monkeypatch):
    db = _DB(_rooms("T-1", "DLX", ["R-A"]))  # STD yok
    monkeypatch.setattr(inv, "db", db)

    with pytest.raises(inv.InventoryConflict) as ei:
        await inv.claim_floating_inventory(_booking(room_type="STD"))
    assert ei.value.conflict_type == "no_inventory"
    assert ei.value.conflict_date == "2026-07-01"
    assert ei.value.available == 0
    assert db.bookings.docs == []


@pytest.mark.asyncio
async def test_floating_missing_fields_value_error(monkeypatch):
    db = _DB(_rooms("T-1", "STD", ["R-A"]))
    monkeypatch.setattr(inv, "db", db)
    with pytest.raises(ValueError):
        await inv.claim_floating_inventory(_booking(room_type=None))


@pytest.mark.asyncio
async def test_floating_pii_encryption_unavailable_fail_closed(monkeypatch):
    # FAIL-CLOSED doktrini: PII sifreleme modulu yoksa booking PERSIST EDILMEZ,
    # plaintext PII ASLA yazilmaz; tutulan geceler compensation ile geri salinir.
    db = _DB(_rooms("T-1", "STD", ["R-A", "R-B"]))
    monkeypatch.setattr(inv, "db", db)

    # encrypt_booking_doc attribute'u OLMAYAN modul -> `from ... import` ImportError.
    broken = types.ModuleType("security.encrypted_lookup")
    monkeypatch.setitem(sys.modules, "security.encrypted_lookup", broken)

    with pytest.raises(RuntimeError):
        await inv.claim_floating_inventory(_booking())
    # Plaintext yazim yok + kilitler geri salindi.
    assert db.bookings.docs == []
    assert [d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"] == []


@pytest.mark.asyncio
async def test_floating_release_after_success(monkeypatch):
    db = _DB(_rooms("T-1", "STD", ["R-A", "R-B"]))
    monkeypatch.setattr(inv, "db", db)

    async def fake_release(tenant_id, booking_id, reason="cancelled", correlation_id=None):
        res = await db.room_night_locks.delete_many(
            {"tenant_id": tenant_id, "booking_id": booking_id}
        )
        return res.deleted_count

    import core.atomic_booking as atomic

    monkeypatch.setattr(atomic, "release_booking_nights", fake_release)

    await inv.claim_floating_inventory(_booking())
    assert len([d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"]) == 3
    n = await inv.release_reservation_inventory("T-1", "AGB-1", reason="cancelled")
    assert n == 3
    assert [d for d in db.room_night_locks.docs if d["booking_id"] == "AGB-1"] == []
