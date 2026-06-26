"""
Agency v1 — Karar 7 (Fan-Out / dagitim) testleri.
==================================================
core/agency_fanout.py icin birim testleri. Mongo'ya BAGLANMAZ; rooms/bookings
icin sahte (fake) tenant-scoped db kullanir, list_active_agencies_for_tenant ve
enqueue_agency_webhook_event monkeypatch'lenir (asyncio_mode=auto).

Kapsam:
  - _derive_agency_event: her kaynak tip -> dogru agency_event_type + anonim payload
  - Anonimlik: guest_id / cancellation_reason / marked_by ASLA acente payload'unda
  - allow_sell=True blok/kaldirma -> fan-out yok (None)
  - import_bridge seyrek booking payload -> bookings.find_one ile cozum (PII proje YOK)
  - room_type/date cozulemez -> fail-closed None (room_id sizmaz)
  - fan_out_agency_events: per-agency enqueue, rekursiyon yok, no-agency->0, ASLA raise
  - Idempotency key: (kaynak event_id) sabit, agency basina ayri
"""
import pytest

import core.agency_fanout as fanout
from core.agency_webhook import (
    AGENCY_INVENTORY_UPDATED,
    AGENCY_RATE_UPDATED,
    AGENCY_RESTRICTION_UPDATED,
)
from core.outbox_service import (
    BOOKING_CANCELLED,
    BOOKING_CREATED,
    BOOKING_NOSHOW,
    INVENTORY_BLOCKED,
    INVENTORY_RELEASED,
    RATE_UPDATED,
    RESTRICTION_UPDATED,
    _build_idempotency_key,
)

TENANT = "tenant-1"
ROOM_ID = "room-aaa"
ROOM_TYPE = "deluxe-king"

# PII degerleri — turetilmis acente payload'unda hicbiri gorunmemeli.
PII_VALUES = {"guest-secret-123", "Murat Yilmaz", "kart iadesi talebi", "front-desk-7"}
PII_KEYS = {
    "guest_id", "guest", "guest_name", "cancellation_reason", "marked_by",
    "cancelled_by", "special_requests", "pricing", "commission", "payment_type",
    "room_id", "booking_id",
}


# ─── Sahte tenant-scoped db ───────────────────────────────────────────────
class _FakeRooms:
    def __init__(self, mapping):
        self.mapping = mapping  # id -> room_type

    async def find_one(self, query, projection=None):
        rid = query.get("id")
        if rid in self.mapping:
            return {"room_type": self.mapping[rid]}
        return None


class _FakeBookings:
    def __init__(self, mapping):
        self.mapping = mapping  # id -> doc

    async def find_one(self, query, projection=None):
        return self.mapping.get(query.get("id"))


class _FakeDB:
    def __init__(self, rooms=None, bookings=None):
        self.rooms = _FakeRooms(rooms if rooms is not None else {ROOM_ID: ROOM_TYPE})
        self.bookings = _FakeBookings(bookings or {})


def _evt(event_type, payload, *, event_id="src-1", entity_id="ent-1", correlation_id="corr-1"):
    return {
        "id": event_id,
        "tenant_id": TENANT,
        "event_type": event_type,
        "entity_id": entity_id,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def _assert_no_pii(payload: dict):
    for k in payload:
        assert k not in PII_KEYS, f"PII anahtari sizdi: {k}"
    flat = " ".join(str(v) for v in payload.values())
    for v in PII_VALUES:
        assert v not in flat, f"PII degeri sizdi: {v}"


# ─── _derive_agency_event: envanter degisimi ailesi ───────────────────────
async def test_derive_booking_created_decrease():
    db = _FakeDB()
    payload = {
        "booking_id": "bk-1", "room_id": ROOM_ID,
        "check_in": "2026-07-01", "check_out": "2026-07-03",
        "guest_id": "guest-secret-123", "status": "confirmed",
    }
    out = await fanout._derive_agency_event(db, _evt(BOOKING_CREATED, payload))
    assert out is not None
    ev_type, base = out
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["room_type_id"] == ROOM_TYPE
    assert base["date_from"] == "2026-07-01"
    assert base["date_to"] == "2026-07-03"
    assert base["change_kind"] == "decrease"
    assert base["change"] == -1
    _assert_no_pii(base)


async def test_derive_booking_cancelled_increase():
    db = _FakeDB()
    payload = {
        "booking_id": "bk-1", "room_id": ROOM_ID,
        "check_in": "2026-07-01", "check_out": "2026-07-03",
        "guest_id": "guest-secret-123",
        "cancellation_reason": "kart iadesi talebi", "cancelled_by": "front-desk-7",
    }
    ev_type, base = await fanout._derive_agency_event(db, _evt(BOOKING_CANCELLED, payload))
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["change_kind"] == "increase"
    assert base["change"] == 1
    _assert_no_pii(base)


async def test_derive_booking_noshow_increase_no_pii():
    db = _FakeDB()
    payload = {
        "booking_id": "bk-1", "room_id": ROOM_ID,
        "check_in": "2026-07-01", "check_out": "2026-07-03",
        "guest_id": "guest-secret-123", "marked_by": "front-desk-7",
        "inventory_released": True,
    }
    ev_type, base = await fanout._derive_agency_event(db, _evt(BOOKING_NOSHOW, payload))
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["change"] == 1
    _assert_no_pii(base)


async def test_derive_inventory_blocked_decrease():
    db = _FakeDB()
    payload = {
        "room_id": ROOM_ID, "allow_sell": False,
        "date_start": "2026-08-01", "date_end": "2026-08-05",
    }
    ev_type, base = await fanout._derive_agency_event(db, _evt(INVENTORY_BLOCKED, payload))
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["change"] == -1
    assert base["date_from"] == "2026-08-01"
    _assert_no_pii(base)


async def test_derive_inventory_released_increase():
    db = _FakeDB()
    payload = {
        "room_id": ROOM_ID, "allow_sell": False, "room_type": ROOM_TYPE,
        "start_date": "2026-08-01", "end_date": "2026-08-05",
    }
    ev_type, base = await fanout._derive_agency_event(db, _evt(INVENTORY_RELEASED, payload))
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["change"] == 1


async def test_derive_allow_sell_true_skipped():
    db = _FakeDB()
    blocked = {"room_id": ROOM_ID, "allow_sell": True,
               "date_start": "2026-08-01", "date_end": "2026-08-05"}
    released = {"room_id": ROOM_ID, "allow_sell": True,
                "start_date": "2026-08-01", "end_date": "2026-08-05"}
    assert await fanout._derive_agency_event(db, _evt(INVENTORY_BLOCKED, blocked)) is None
    assert await fanout._derive_agency_event(db, _evt(INVENTORY_RELEASED, released)) is None


# ─── _derive_agency_event: fiyat / restriksiyon ───────────────────────────
async def test_derive_rate_updated():
    db = _FakeDB(rooms={})  # rate room lookup yapmamali
    payload = {"date": "2026-09-01", "recommended_rate": 1250.0, "strategy": "occupancy"}
    ev_type, base = await fanout._derive_agency_event(db, _evt(RATE_UPDATED, payload))
    assert ev_type == AGENCY_RATE_UPDATED
    assert base["date"] == "2026-09-01"
    assert base["rate"] == 1250.0
    assert base["strategy"] == "occupancy"
    assert "room_id" not in base


async def test_derive_rate_updated_missing_date_none():
    db = _FakeDB(rooms={})
    assert await fanout._derive_agency_event(db, _evt(RATE_UPDATED, {"recommended_rate": 1})) is None


async def test_derive_restriction_passthrough_safe():
    db = _FakeDB(rooms={})
    payload = {"room_type": ROOM_TYPE, "date": "2026-09-01",
               "restriction_type": "min_los", "value": 2}
    ev_type, base = await fanout._derive_agency_event(db, _evt(RESTRICTION_UPDATED, payload))
    assert ev_type == AGENCY_RESTRICTION_UPDATED
    assert base["room_type_id"] == ROOM_TYPE
    assert base["restriction_type"] == "min_los"
    assert base["value"] == 2


# ─── import_bridge seyrek payload -> bookings.find_one ile cozum ───────────
async def test_derive_import_bridge_sparse_booking_resolved():
    db = _FakeDB(bookings={
        "bk-import": {
            "room_id": ROOM_ID, "check_in": "2026-10-01", "check_out": "2026-10-04",
            "guest_id": "guest-secret-123", "guest": {"name": "Murat Yilmaz"},
        }
    })
    # import_bridge payload: room_id/date YOK, sadece booking_id/source/provider.
    payload = {"booking_id": "bk-import", "source": "ota_import", "provider": "exely"}
    ev = _evt(BOOKING_CREATED, payload, entity_id="bk-import")
    ev_type, base = await fanout._derive_agency_event(db, ev)
    assert ev_type == AGENCY_INVENTORY_UPDATED
    assert base["room_type_id"] == ROOM_TYPE
    assert base["date_from"] == "2026-10-01"
    assert base["change"] == -1
    _assert_no_pii(base)


# ─── Fail-closed ──────────────────────────────────────────────────────────
async def test_derive_unresolved_room_type_failclosed():
    db = _FakeDB(rooms={})  # room_id bulunamaz
    payload = {"room_id": "ghost", "date_start": "2026-08-01", "date_end": "2026-08-02",
               "allow_sell": False}
    assert await fanout._derive_agency_event(db, _evt(INVENTORY_BLOCKED, payload)) is None


async def test_derive_missing_dates_failclosed():
    db = _FakeDB()
    payload = {"room_id": ROOM_ID, "allow_sell": False}  # tarih yok
    assert await fanout._derive_agency_event(db, _evt(INVENTORY_BLOCKED, payload)) is None


# ─── fan_out_agency_events: dagitim davranisi ─────────────────────────────
class _Capture:
    def __init__(self):
        self.calls = []

    async def __call__(self, db, *, tenant_id, agency_id, event_type, entity_type,
                       entity_id, payload, correlation_id=None, idempotency_key=None,
                       session=None):
        self.calls.append({
            "tenant_id": tenant_id, "agency_id": agency_id, "event_type": event_type,
            "entity_type": entity_type, "entity_id": entity_id,
            "payload": payload, "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
        })
        return {"id": f"out-{len(self.calls)}"}


class _DedupCapture:
    """enqueue_outbox_event'in unique-index + DuplicateKey no-op davranisini taklit
    eder: ayni idempotency_key ikinci kez gelirse yeni kayit YAZILMAZ (sessiz no-op)."""
    def __init__(self):
        self.records = {}  # idempotency_key -> kayit

    async def __call__(self, db, *, idempotency_key=None, payload, agency_id, **kw):
        if idempotency_key in self.records:
            return self.records[idempotency_key]
        self.records[idempotency_key] = {"agency_id": agency_id, "payload": payload}
        return self.records[idempotency_key]


def _patch(monkeypatch, *, agencies, capture=None, db=None):
    monkeypatch.setattr("core.database.db", db if db is not None else _FakeDB(), raising=False)

    async def _list(tenant_id, on_date=None):
        return list(agencies)

    monkeypatch.setattr(
        "routers.agency_contracts.list_active_agencies_for_tenant", _list, raising=True
    )
    if capture is not None:
        monkeypatch.setattr(
            "core.agency_webhook.enqueue_agency_webhook_event", capture, raising=True
        )


async def test_fan_out_per_agency(monkeypatch):
    cap = _Capture()
    _patch(monkeypatch, agencies=["agency-A", "agency-B"], capture=cap)
    payload = {"booking_id": "bk-1", "room_id": ROOM_ID,
               "check_in": "2026-07-01", "check_out": "2026-07-03",
               "guest_id": "guest-secret-123"}
    n = await fanout.fan_out_agency_events(_evt(BOOKING_CREATED, payload, event_id="SRC-9"))
    assert n == 2
    assert {c["agency_id"] for c in cap.calls} == {"agency-A", "agency-B"}
    for c in cap.calls:
        assert c["event_type"] == AGENCY_INVENTORY_UPDATED
        assert c["entity_type"] == "agency_fanout"
        assert c["entity_id"] == "SRC-9"  # idempotency: kaynak event_id
        assert c["tenant_id"] == TENANT
        # Stabil, payload'dan bagimsiz dedup key (kaynak+agency basina ayri).
        assert c["idempotency_key"] == (
            f"agency_fanout:{TENANT}:{c['agency_id']}:SRC-9:{AGENCY_INVENTORY_UPDATED}"
        )
        _assert_no_pii(c["payload"])
    # Key'ler agency basina ayrik.
    assert len({c["idempotency_key"] for c in cap.calls}) == 2


async def test_fan_out_idempotent_across_payload_drift(monkeypatch):
    """Ayni kaynak event iki kez fan-out edilse (worker retry) ve arada canli booking
    verisi (room/date) DEGISSE bile, (kaynak+agency) basina TEK outbox kaydi yazilir."""
    cap = _DedupCapture()
    _patch(monkeypatch, agencies=["agency-A"], capture=cap)
    sparse = {"booking_id": "bk-x", "source": "ota_import"}
    ev = _evt(BOOKING_CREATED, sparse, event_id="SRC-DRIFT", entity_id="bk-x")

    # 1. deneme: booking room/date = A
    db1 = _FakeDB(
        rooms={ROOM_ID: ROOM_TYPE},
        bookings={"bk-x": {"room_id": ROOM_ID,
                           "check_in": "2026-07-01", "check_out": "2026-07-03"}},
    )
    monkeypatch.setattr("core.database.db", db1, raising=False)
    assert await fanout.fan_out_agency_events(ev) == 1

    # 2. deneme (retry): booking drift etti -> farkli room_type + tarih
    db2 = _FakeDB(
        rooms={ROOM_ID: ROOM_TYPE, "room-bbb": "suite-ocean"},
        bookings={"bk-x": {"room_id": "room-bbb",
                           "check_in": "2026-09-09", "check_out": "2026-09-11"}},
    )
    monkeypatch.setattr("core.database.db", db2, raising=False)
    await fanout.fan_out_agency_events(ev)

    # Drift'e ragmen tek kayit (ilk turetilen payload kalir).
    assert len(cap.records) == 1
    only = next(iter(cap.records.values()))
    assert only["payload"]["room_type_id"] == ROOM_TYPE
    assert only["payload"]["date_from"] == "2026-07-01"


async def test_fan_out_no_recursion_on_agency_event(monkeypatch):
    cap = _Capture()
    _patch(monkeypatch, agencies=["agency-A"], capture=cap)
    ev = _evt(AGENCY_INVENTORY_UPDATED, {"room_type_id": ROOM_TYPE})
    assert await fanout.fan_out_agency_events(ev) == 0
    assert cap.calls == []


async def test_fan_out_non_source_type(monkeypatch):
    cap = _Capture()
    _patch(monkeypatch, agencies=["agency-A"], capture=cap)
    assert await fanout.fan_out_agency_events(_evt("some.other.event", {})) == 0
    assert cap.calls == []


async def test_fan_out_no_active_agencies(monkeypatch):
    cap = _Capture()
    _patch(monkeypatch, agencies=[], capture=cap)
    payload = {"room_id": ROOM_ID, "allow_sell": False,
               "date_start": "2026-08-01", "date_end": "2026-08-02"}
    assert await fanout.fan_out_agency_events(_evt(INVENTORY_BLOCKED, payload)) == 0
    assert cap.calls == []


async def test_fan_out_never_raises(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("enqueue patladi")

    _patch(monkeypatch, agencies=["agency-A"], capture=_boom)
    payload = {"room_id": ROOM_ID, "allow_sell": False,
               "date_start": "2026-08-01", "date_end": "2026-08-02"}
    # Tek acente hata verse de fonksiyon raise etmez, basari sayisi 0 doner.
    assert await fanout.fan_out_agency_events(_evt(INVENTORY_BLOCKED, payload)) == 0


async def test_fan_out_missing_tenant_or_id(monkeypatch):
    cap = _Capture()
    _patch(monkeypatch, agencies=["agency-A"], capture=cap)
    ev = _evt(BOOKING_CREATED, {"room_id": ROOM_ID, "check_in": "x", "check_out": "y"})
    ev["tenant_id"] = ""
    assert await fanout.fan_out_agency_events(ev) == 0
    assert cap.calls == []


# ─── Idempotency key: kaynak sabit, agency ayrik ──────────────────────────
def test_idempotency_key_deterministic_and_per_agency():
    base = {"room_type_id": ROOM_TYPE, "date_from": "2026-07-01",
            "date_to": "2026-07-03", "change_kind": "decrease", "change": -1,
            "source_event_type": BOOKING_CREATED}
    source_id = "SRC-9"

    def key_for(agency_id):
        enriched = {**base, "agency_id": agency_id}
        return _build_idempotency_key(TENANT, AGENCY_INVENTORY_UPDATED, source_id, enriched)

    # Ayni (kaynak, agency) -> ayni key (retry'da cift fan-out yok).
    assert key_for("agency-A") == key_for("agency-A")
    # Farkli agency -> farkli key (her acente ayri teslim alir).
    assert key_for("agency-A") != key_for("agency-B")
