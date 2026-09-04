from __future__ import annotations

import pytest

from routers import kbs


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


class _Db:
    def __init__(self, bookings, rooms):
        self.bookings = _Collection(bookings)
        self.rooms = _Collection(rooms)
        self.guests = _Collection([])


def _booking(**overrides):
    booking = {
        "tenant_id": "tenant-1",
        "id": "booking-1",
        "guest_name": "Test Misafir",
        "guest_nationality": "TC",
        "guest_phone": "",
        "room_id": "room-109",
        "room_number": "",
        "check_in": "2026-08-30T14:00:00+03:00",
        "check_out": "2026-08-31T12:00:00+03:00",
    }
    booking.update(overrides)
    return booking


@pytest.mark.asyncio
async def test_snapshot_resolves_room_number_from_canonical_room(monkeypatch):
    fake_db = _Db(
        [_booking()],
        [{"tenant_id": "tenant-1", "id": "room-109", "room_number": "109"}],
    )
    monkeypatch.setattr(kbs, "db", fake_db)

    booking, _guest, snapshot = await kbs._build_payload_snapshot("tenant-1", "booking-1")

    assert booking["room_id"] == "room-109"
    assert snapshot["room_number"] == "109"


@pytest.mark.asyncio
async def test_canonical_room_overrides_stale_booking_room_number(monkeypatch):
    fake_db = _Db(
        [_booking(room_number="108")],
        [{"tenant_id": "tenant-1", "id": "room-109", "room_number": "109"}],
    )
    monkeypatch.setattr(kbs, "db", fake_db)

    _booking_doc, _guest, snapshot = await kbs._build_payload_snapshot("tenant-1", "booking-1")

    assert snapshot["room_number"] == "109"


@pytest.mark.asyncio
async def test_snapshot_keeps_booking_room_number_when_room_id_is_absent(monkeypatch):
    fake_db = _Db([_booking(room_id=None, room_number="105")], [])
    monkeypatch.setattr(kbs, "db", fake_db)

    _booking_doc, _guest, snapshot = await kbs._build_payload_snapshot("tenant-1", "booking-1")

    assert snapshot["room_number"] == "105"


@pytest.mark.parametrize(
    "error",
    [
        "jandarma_GirdiHatasi: Oda Numarası Eksik.",
        "payload_incomplete: room_number",
        "missing_room_number",
        "HTTP 400: bad request",
        "jandarma_VTHatasi: Müşteri Tesiste Zaten Kayıtlı.",
        "jandarma_VTHatasi: String or binary data would be truncated.",
    ],
)
def test_permanent_kbs_errors_are_not_retried(error):
    assert kbs._is_permanent_kbs_error(error)


@pytest.mark.parametrize("error", ["network: timeout", "HTTP 503: unavailable", "soap_fault: temporary"])
def test_transient_kbs_errors_remain_retryable(error):
    assert not kbs._is_permanent_kbs_error(error)
