from types import SimpleNamespace

import pytest

from domains.guest.experience_router import upsell


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class _Collection:
    def __init__(self, *, document=None, rows=None):
        self.document = document
        self.rows = rows or []
        self.inserted = []
        self.find_one_queries = []

    async def find_one(self, query, *_args, **_kwargs):
        self.find_one_queries.append(query)
        return self.document

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)

    async def count_documents(self, *_args, **_kwargs):
        return 0

    async def insert_many(self, rows):
        self.inserted.extend(rows)


@pytest.mark.asyncio
async def test_unassigned_booking_still_generates_service_offers(monkeypatch):
    booking = {
        "id": "booking-1",
        "tenant_id": "tenant-1",
        "guest_id": "guest-1",
        "guest_name": "Joan Doremus",
        "room_id": None,
        "check_in": "2099-10-23",
        "check_out": "2099-10-26",
    }
    offers = _Collection()
    fake_db = SimpleNamespace(
        bookings=_Collection(document=booking),
        guests=_Collection(document={"id": "guest-1", "name": "Joan Doremus"}),
        rooms=_Collection(rows=[]),
        upsell_settings=_Collection(document=None),
        upsell_offers=offers,
    )
    monkeypatch.setattr(upsell, "db", fake_db)

    result = await upsell.generate_upsell_offers(
        booking_id="booking-1",
        current_user=SimpleNamespace(tenant_id="tenant-1"),
    )

    assert result["total_offers"] == 3
    assert {offer["type"] for offer in result["offers"]} == {
        "early_checkin",
        "late_checkout",
        "airport_transfer",
    }
    assert all(offer["booking_id"] == "booking-1" for offer in offers.inserted)


@pytest.mark.asyncio
async def test_stale_ui_id_can_resolve_by_stable_booking_reference(monkeypatch):
    booking = {
        "id": "canonical-booking-id",
        "booking_number": "R370795907",
        "tenant_id": "tenant-1",
        "guest_id": "guest-1",
        "guest_name": "İrfan Ayaz",
        "room_id": "room-208",
        "check_in": "2099-10-10",
        "check_out": "2099-10-11",
    }
    bookings = _Collection(document=booking)
    offers = _Collection()
    fake_db = SimpleNamespace(
        bookings=bookings,
        guests=_Collection(document={"id": "guest-1", "name": "İrfan Ayaz"}),
        rooms=_Collection(document={"id": "room-208", "base_price": 6000}, rows=[]),
        upsell_settings=_Collection(document=None),
        upsell_offers=offers,
    )
    monkeypatch.setattr(upsell, "db", fake_db)

    result = await upsell.generate_upsell_offers(
        booking_id="R370795907",
        current_user=SimpleNamespace(tenant_id="tenant-1"),
    )

    lookup = bookings.find_one_queries[0]
    assert lookup["tenant_id"] == "tenant-1"
    assert {"booking_number": "R370795907"} in lookup["$or"]
    assert result["booking_id"] == "canonical-booking-id"
    assert all(offer["booking_id"] == "canonical-booking-id" for offer in offers.inserted)
