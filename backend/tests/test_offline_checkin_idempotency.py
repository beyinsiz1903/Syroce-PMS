"""
Offline check-in — v2 service idempotency & conflict surfacing (Task #569).

Cevrimdisi kuyruk, internet dondugunde idempotent `POST /frontdesk/v2/checkin`
ucuna replay eder. Ayni rezervasyon birden cok kez gonderilse bile (Background
Sync + sayfa-baglami yedek iki replay surucusu) cift booking / cift folyo
olusmamali; gercek is hatalari (oda dolu vb.) yapilandirilmis kodla yuzeye
cikmali.

Bu test, FrontdeskServiceV2._do_checkin / checkin mantigini altyapi
gerektirmeden (mongod/canli backend yok) hafif bir bellek-ici async Mongo
sahtesiyle dogrudan dogrular.
"""
import uuid

import pytest

from common.context import OperationContext
from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2


# ---------------------------------------------------------------------------
# Minimal in-memory async Mongo fake (sadece servisin kullandigi operatorler)
# ---------------------------------------------------------------------------
def _matches(doc, flt):
    for key, cond in flt.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
            continue
        val = doc.get(key)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                if op == "$lt":
                    if not (val is not None and val < operand):
                        return False
                elif op == "$exists":
                    exists = key in doc
                    if exists != operand:
                        return False
                elif op == "$in":
                    if val not in operand:
                        return False
                else:
                    raise NotImplementedError(op)
        else:
            if val != cond:
                return False
    return True


class _Result:
    def __init__(self, modified_count=0, upserted_id=None, inserted_id=None):
        self.modified_count = modified_count
        self.upserted_id = upserted_id
        self.inserted_id = inserted_id


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.insert_calls = 0

    async def find_one(self, flt, projection=None):
        for d in self.docs:
            if _matches(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return _Result(inserted_id=doc.get("id"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _matches(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        d[k] = d.get(k, 0) + v
                return _Result(modified_count=1)
        if upsert:
            new_doc = {}
            for k, v in flt.items():
                if k != "$or" and not isinstance(v, dict):
                    new_doc[k] = v
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    new_doc[k] = v
            new_doc.setdefault("id", str(uuid.uuid4()))
            self.docs.append(new_doc)
            return _Result(upserted_id=new_doc["id"])
        return _Result(modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _matches(d, flt):
                del self.docs[i]
                return _Result(modified_count=1)
        return _Result(modified_count=0)

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _matches(d, flt))


class FakeDB:
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        # FakeDB().bookings gibi attribute erisimi.
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collections.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        # @audited dekoratoru self._db[col_name] seklinde erisir.
        return self._collections.setdefault(name, FakeCollection())


TENANT = "tenant-test-569"


def _ctx():
    return OperationContext(tenant_id=TENANT, actor_id="user-1", actor_role="front_desk")


def _make_service():
    svc = FrontdeskServiceV2()
    svc._db = FakeDB()
    return svc


def _seed_ready_booking(db, booking_id="bk-1", room_id="rm-1", status="confirmed", room_status="available"):
    db.bookings.docs.append({
        "id": booking_id,
        "tenant_id": TENANT,
        "status": status,
        "room_id": room_id,
        "guest_id": "guest-1",
        "currency": "TRY",
    })
    db.rooms.docs.append({
        "id": room_id,
        "tenant_id": TENANT,
        "status": room_status,
        "room_number": "101",
    })
    db.guests.docs.append({"id": "guest-1", "tenant_id": TENANT, "total_stays": 0})


@pytest.mark.asyncio
async def test_first_checkin_succeeds_and_creates_single_folio():
    svc = _make_service()
    _seed_ready_booking(svc._db)

    res = await svc.checkin(_ctx(), "bk-1", idempotency_key="checkin-bk-1")

    assert res.ok is True
    assert res.data["booking_id"] == "bk-1"
    assert svc._db.bookings.docs[0]["status"] == "checked_in"
    assert svc._db.rooms.docs[0]["status"] == "occupied"
    assert svc._db.guests.docs[0]["total_stays"] == 1
    assert svc._db.folios.insert_calls == 1


@pytest.mark.asyncio
async def test_replay_same_key_is_idempotent_no_double_booking_or_folio():
    """Ayni idempotency anahtariyla tekrar oynatma cift booking/folyo URETMEZ."""
    svc = _make_service()
    _seed_ready_booking(svc._db)
    key = "checkin-bk-1"

    first = await svc.checkin(_ctx(), "bk-1", idempotency_key=key)
    assert first.ok is True
    assert svc._db.folios.insert_calls == 1

    # Replay (Background Sync + sayfa yedek surucusu cift replay edebilir).
    second = await svc.checkin(_ctx(), "bk-1", idempotency_key=key)
    third = await svc.checkin(_ctx(), "bk-1", idempotency_key=key)

    assert second.ok is True
    assert second.data.get("idempotent") is True
    assert third.ok is True
    assert third.data.get("idempotent") is True

    # Tek booking, tek folyo, total_stays yalniz bir kez artmis.
    assert len([d for d in svc._db.bookings.docs if d["id"] == "bk-1"]) == 1
    assert svc._db.bookings.docs[0]["status"] == "checked_in"
    assert svc._db.folios.insert_calls == 1
    assert svc._db.guests.docs[0]["total_stays"] == 1


@pytest.mark.asyncio
async def test_conflict_room_occupied_surfaces_structured_code():
    svc = _make_service()
    _seed_ready_booking(svc._db, room_status="occupied")

    res = await svc.checkin(_ctx(), "bk-1", idempotency_key="checkin-bk-1")

    assert res.ok is False
    assert res.code == "ROOM_OCCUPIED"
    # Booking durumu degismemis (cakisma -> mutasyon yok).
    assert svc._db.bookings.docs[0]["status"] == "confirmed"
    assert svc._db.folios.insert_calls == 0


@pytest.mark.asyncio
async def test_conflict_invalid_status_surfaces_code():
    svc = _make_service()
    _seed_ready_booking(svc._db, status="cancelled")

    res = await svc.checkin(_ctx(), "bk-1", idempotency_key="checkin-bk-1")

    assert res.ok is False
    assert res.code == "INVALID_STATUS"


@pytest.mark.asyncio
async def test_conflict_no_room_surfaces_code():
    svc = _make_service()
    svc._db.bookings.docs.append({
        "id": "bk-2",
        "tenant_id": TENANT,
        "status": "confirmed",
        "room_id": "missing-room",
        "guest_id": "guest-1",
    })

    res = await svc.checkin(_ctx(), "bk-2", idempotency_key="checkin-bk-2")

    assert res.ok is False
    assert res.code == "NO_ROOM"


@pytest.mark.asyncio
async def test_existing_folio_not_duplicated_on_checkin():
    """Folyo zaten varsa (kismi onceki deneme) ikinci kez olusturulmaz."""
    svc = _make_service()
    _seed_ready_booking(svc._db)
    svc._db.folios.docs.append({
        "id": "existing-folio",
        "tenant_id": TENANT,
        "booking_id": "bk-1",
        "folio_type": "guest",
        "status": "open",
    })

    res = await svc.checkin(_ctx(), "bk-1", idempotency_key="checkin-bk-1")

    assert res.ok is True
    assert res.data["folio_id"] == "existing-folio"
    assert svc._db.folios.insert_calls == 0
