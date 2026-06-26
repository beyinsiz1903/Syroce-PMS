"""
Agency v1 — Adim 3 router wiring entegrasyon testleri (create + cancel uctan uca).

Kapsam: HMAC dependency override (imza T3'te ayri test edildi) altinda; FAKE db
(idempotency_cache 5'li scope unique + bookings/rooms/room_night_locks). Dogrulanan
sozlesme davranisi:
  - create: 201 + floating persist (room_id=None); idempotent replay (ayni key+govde)
    -> ayni 201; ayni key FARKLI govde -> 422 idempotency_conflict; sold-out -> 409
    inventory_conflict (conflict_date/room_type_id/available).
  - cancel: 200 + DB-atomik release + status=cancelled; bulunamadi -> 404; terminal/
    in-house -> 409 terminal_state.
  - availability / modify: kimlik dogrulanmis ama fail-closed 503 (no fake-green).

Saf: gercek DB/crypto yok. seal/unseal kimlik round-trip'e indirilir (replay govdesi
anlamli test edilsin); PII modulleri stub. Atomik dogruluk (unique index) simule.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import routers.agency_v1.idempotency_runtime as idem
import routers.agency_v1.inventory as inv
from routers.agency_v1.auth import verify_agency_signature

# NOT: modul adi (`router`) icindeki APIRouter degiskeni (`router`) ile cakisir;
# `import ... as rt` APIRouter'i baglayabilir. import_module modulu kesin doner.
rt = importlib.import_module("routers.agency_v1.router")

_SCOPE_KEYS = ("tenant_id", "agency_id", "method", "path", "idempotency_key")


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
    def __init__(self):
        self.docs = []

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

    @staticmethod
    def _match(doc, query):
        for k, v in query.items():
            if isinstance(v, dict) and "$ne" in v:
                if doc.get(k) == v["$ne"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if self._match(d, query):
                return dict(d)
        return None

    async def update_one(self, query, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update["$set"])

                class _R:
                    matched_count = 1

                return _R()

        class _R0:
            matched_count = 0

        return _R0()


class _IdemCache:
    def __init__(self):
        self.docs = []

    def _key(self, scope):
        return tuple(scope[k] for k in _SCOPE_KEYS)

    async def insert_one(self, doc):
        k = self._key(doc)
        for d in self.docs:
            if self._key(d) == k:
                raise DuplicateKeyError("ux_idempotency_cache_scope")
        self.docs.append(dict(doc))

    async def find_one(self, scope, proj=None):
        k = self._key(scope)
        for d in self.docs:
            if self._key(d) == k:
                return dict(d)
        return None

    async def update_one(self, scope, update):
        k = self._key(scope)
        for d in self.docs:
            if self._key(d) == k:
                d.update(update["$set"])

                class _R:
                    matched_count = 1

                return _R()

        class _R0:
            matched_count = 0

        return _R0()

    async def delete_one(self, scope):
        k = self._key(scope)
        self.docs = [d for d in self.docs if self._key(d) != k]


class _DB:
    def __init__(self, rooms):
        self.rooms = _Rooms(rooms)
        self.room_night_locks = _Locks()
        self.bookings = _Bookings()
        self.idempotency_cache = _IdemCache()


def _rooms(ids, tenant="T-1", room_type="STD"):
    return [{"id": i, "tenant_id": tenant, "room_type": room_type, "is_active": True} for i in ids]


@pytest.fixture
def client(monkeypatch):
    db = _DB(_rooms(["R-A", "R-B"]))
    monkeypatch.setattr(rt, "db", db)
    monkeypatch.setattr(inv, "db", db)

    # seal/unseal -> kimlik round-trip (replay govdesi anlamli test edilsin).
    monkeypatch.setattr(idem, "seal_response_body", lambda body: {"_rb": body})
    monkeypatch.setattr(idem, "unseal_response_body", lambda existing: existing.get("_rb"))

    # PII modulleri stub (saf test; runtime crypto config gerekmesin).
    enc = types.ModuleType("security.encrypted_lookup")
    enc.encrypt_booking_doc = lambda d: d
    monkeypatch.setitem(sys.modules, "security.encrypted_lookup", enc)
    norm = types.ModuleType("security.search_normalize")
    norm.apply_collection_normalized_fields = lambda d, collection=None: None
    monkeypatch.setitem(sys.modules, "security.search_normalize", norm)

    # release -> ayni fake locks'tan sil.
    async def fake_release(tenant_id, booking_id, reason="cancelled", correlation_id=None):
        res = await db.room_night_locks.delete_many(
            {"tenant_id": tenant_id, "booking_id": booking_id}
        )
        return res.deleted_count

    import core.atomic_booking as atomic

    monkeypatch.setattr(atomic, "release_booking_nights", fake_release)

    app = FastAPI()
    app.include_router(rt.router)
    app.dependency_overrides[verify_agency_signature] = lambda: {
        "key_id": "K",
        "tenant_id": "T-1",
        "agency_id": "A-1",
    }
    c = TestClient(app)
    c._db = db  # testte erisim icin
    return c


def _create_body(**over):
    body = {
        "schema_version": "2026-06",
        "agency_reservation_id": "AG-100",
        "arrival_date": "2026-07-01",
        "departure_date": "2026-07-04",
        "room_type_id": "STD",
        "rate_plan_id": "BAR",
        "occupancy": {"adults": 2, "children": 0},
        "pricing": {"total": 300.0, "currency": "TRY"},
    }
    body.update(over)
    return body


def _hdr(key="idem-1"):
    return {"Idempotency-Key": key}


def test_create_success_floating(client):
    r = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "confirmed"
    assert data["pms_reservation_id"]
    # Floating persist: booking room_id None + 3 gece kilit.
    booking = client._db.bookings.docs[0]
    assert booking["room_id"] is None
    assert booking["allocation_source"] == "agency_floating"
    assert len(client._db.room_night_locks.docs) == 3


def test_create_idempotent_replay(client):
    r1 = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k-r"))
    r2 = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k-r"))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["pms_reservation_id"] == r2.json()["pms_reservation_id"]
    # Replay: ikinci cagri YENI booking/kilit URETMEZ.
    assert len(client._db.bookings.docs) == 1
    assert len(client._db.room_night_locks.docs) == 3


def test_create_idempotency_conflict_same_key_diff_body(client):
    client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k-c"))
    r = client.post(
        "/api/agency/v1/reservations",
        json=_create_body(agency_reservation_id="AG-999"),
        headers=_hdr("k-c"),
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "idempotency_conflict"


def test_create_inventory_conflict_sold_out(client):
    # 2 oda var; 3 odali istek -> her gece sadece 2 alinabilir -> 409.
    r = client.post(
        "/api/agency/v1/reservations",
        json=_create_body(room_count=3),
        headers=_hdr("k-sold"),
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error_code"] == "inventory_conflict"
    assert body["conflict_date"] == "2026-07-01"
    assert body["room_type_id"] == "STD"
    assert body["available"] == 2
    # Kalici hicbir sey yazilmadi (compensation).
    assert client._db.bookings.docs == []
    assert client._db.room_night_locks.docs == []


def test_cancel_success_releases_inventory(client):
    cr = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k1"))
    pms_id = cr.json()["pms_reservation_id"]
    assert len(client._db.room_night_locks.docs) == 3

    dr = client.request(
        "DELETE", "/api/agency/v1/reservations/AG-100", headers=_hdr("k-del")
    )
    assert dr.status_code == 200, dr.text
    assert dr.json()["status"] == "cancelled"
    assert dr.json()["pms_reservation_id"] == pms_id
    booking = client._db.bookings.docs[0]
    assert booking["status"] == "cancelled"
    # DB-atomik release: kilitler silindi.
    assert client._db.room_night_locks.docs == []


def test_cancel_not_found(client):
    dr = client.request(
        "DELETE", "/api/agency/v1/reservations/NOPE", headers=_hdr("k-nf")
    )
    assert dr.status_code == 404
    assert dr.json()["error_code"] == "not_found"


def test_cancel_terminal_state_guard(client):
    client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k2"))
    # Misafir check-in oldu -> acente iptal edemez.
    client._db.bookings.docs[0]["status"] = "checked_in"
    dr = client.request(
        "DELETE", "/api/agency/v1/reservations/AG-100", headers=_hdr("k-term")
    )
    assert dr.status_code == 409
    assert dr.json()["error_code"] == "terminal_state"
    # Kilitler korunur (iptal reddedildi).
    assert len(client._db.room_night_locks.docs) == 3


def test_create_domain_guard_blocks_duplicate_after_sweep(client):
    # Birinci create basarili. Sonra idempotency slotu "sweep" simule edilir
    # (cache temizlenir). AYNI external_id ile FARKLI idempotency key retry ->
    # domain-guard mukerrer booking/claim URETMEZ; mevcut rezervasyonu doner.
    r1 = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k-d1"))
    pms_id = r1.json()["pms_reservation_id"]
    client._db.idempotency_cache.docs = []  # processing slot sweep simulasyonu

    r2 = client.post("/api/agency/v1/reservations", json=_create_body(), headers=_hdr("k-d2"))
    assert r2.status_code == 201
    assert r2.json()["pms_reservation_id"] == pms_id  # ayni rezervasyon
    # Mukerrer kayit/kilit YOK.
    assert len(client._db.bookings.docs) == 1
    assert len(client._db.room_night_locks.docs) == 3


def test_availability_and_modify_fail_closed(client):
    av = client.get(
        "/api/agency/v1/availability",
        params={
            "room_type_id": "STD",
            "arrival_date": "2026-07-01",
            "departure_date": "2026-07-04",
        },
    )
    assert av.status_code == 503
    assert av.json()["error_code"] == "not_configured"

    md = client.patch(
        "/api/agency/v1/reservations/AG-100",
        json={"schema_version": "2026-06", "special_requests": "late checkout"},
        headers=_hdr("k-mod"),
    )
    assert md.status_code == 503
    assert md.json()["error_code"] == "not_configured"
