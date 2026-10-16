"""Guest reservation reads preserve the original amount and its own currency."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from domains.guest.experience_router import guest_app


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, *_args):
        return [dict(row) for row in self.rows]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)

        return iterate()


@pytest.mark.asyncio
@pytest.mark.parametrize("currency", ["USD", "EUR", None])
async def test_guest_booking_serializes_original_currency_without_try_or_fx(monkeypatch, currency):
    import security.encrypted_lookup

    monkeypatch.setattr(security.encrypted_lookup, "build_guest_pii_query", lambda field, value: {field: value})
    booking = {
        "id": "booking-1", "tenant_id": "tenant-1", "guest_id": "guest-1", "room_id": "room-1",
        "check_in": "2026-10-16", "check_out": "2026-10-18", "status": "checked_out",
        "total_amount": 1234.56,
    }
    if currency:
        booking["currency"] = currency
    guest = {"id": "guest-1", "tenant_id": "tenant-1", "name": "Test Guest"}
    guests = SimpleNamespace(find=MagicMock(side_effect=lambda *_args, **_kwargs: Cursor([guest])))
    bookings = SimpleNamespace(find=MagicMock(return_value=Cursor([booking])))
    monkeypatch.setattr(guest_app, "db", SimpleNamespace(
        guests=guests,
        bookings=bookings,
        rooms=SimpleNamespace(find=MagicMock(return_value=Cursor([{"id": "room-1", "room_number": "101"}]))),
        tenants=SimpleNamespace(find=MagicMock(return_value=Cursor([{"id": "tenant-1", "property_name": "Test Hotel"}]))),
    ))

    result = await guest_app.get_guest_bookings(SimpleNamespace(tenant_id="tenant-1", email="guest@example.invalid", name="Test Guest"))

    returned = result["past_bookings"][0]
    assert returned["total_amount"] == 1234.56
    assert returned["currency"] == currency
    assert guests.find.call_args_list[0].args[0]["tenant_id"] == "tenant-1"
