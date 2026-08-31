from types import SimpleNamespace

import pytest

from domains.pms.frontdesk_service import FrontdeskService


class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._index = 0

    async def to_list(self, _limit):
        return list(self._rows)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._index]
        self._index += 1
        return row


class _Collection:
    def __init__(self, rows):
        self._rows = list(rows)
        self.queries = []

    def find(self, query, _projection=None):
        self.queries.append(query)
        wanted_ids = set(query.get("id", {}).get("$in", []))
        wanted_booking_ids = set(query.get("booking_id", {}).get("$in", []))
        rows = [
            row
            for row in self._rows
            if row.get("tenant_id") == query.get("tenant_id")
            and (not wanted_ids or row.get("id") in wanted_ids)
            and (not wanted_booking_ids or row.get("booking_id") in wanted_booking_ids)
            and (query.get("status") is None or row.get("status") == query.get("status"))
        ]
        return _Cursor(rows)


@pytest.mark.asyncio
async def test_inhouse_enrichment_exposes_real_folio_balance_for_quick_payment():
    db = SimpleNamespace(
        bookings=_Collection(
            [
                {
                    "id": "booking-1",
                    "tenant_id": "tenant-1",
                    "guest_id": "guest-1",
                    "room_id": "room-1",
                    "status": "checked_in",
                    "total_amount": 100,
                    "check_out": "2026-08-30T12:00:00+00:00",
                }
            ]
        ),
        guests=_Collection(
            [{"id": "guest-1", "tenant_id": "tenant-1", "name": "Test Misafir"}]
        ),
        rooms=_Collection(
            [{"id": "room-1", "tenant_id": "tenant-1", "room_number": "107"}]
        ),
        folio_charges=_Collection(
            [
                {
                    "booking_id": "booking-1",
                    "tenant_id": "tenant-1",
                    "total": 100,
                    "charge_type": "room_charge",
                }
            ]
        ),
        payments=_Collection(
            [{"booking_id": "booking-1", "tenant_id": "tenant-1", "amount": 40, "status": "paid"}]
        ),
        extra_charges=_Collection(
            [{"booking_id": "booking-1", "tenant_id": "tenant-1", "charge_amount": 50}]
        ),
    )
    service = FrontdeskService.__new__(FrontdeskService)
    service._db = db

    result = await service.get_inhouse(SimpleNamespace(tenant_id="tenant-1"))

    assert result.ok is True
    assert result.data == [
        {
            "id": "booking-1",
            "tenant_id": "tenant-1",
            "guest_id": "guest-1",
            "room_id": "room-1",
            "status": "checked_in",
            "total_amount": 100,
            "check_out": "2026-08-30T12:00:00+00:00",
            "guest": {"id": "guest-1", "tenant_id": "tenant-1", "name": "Test Misafir"},
            "room": {"id": "room-1", "tenant_id": "tenant-1", "room_number": "107"},
            "guest_name": "Test Misafir",
            "room_number": "107",
            "balance": 110.0,
        }
    ]
    for collection in (db.bookings, db.guests, db.rooms, db.folio_charges, db.payments, db.extra_charges):
        assert all(query.get("tenant_id") == "tenant-1" for query in collection.queries)
