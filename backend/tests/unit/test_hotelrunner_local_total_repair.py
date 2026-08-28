from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.ingest.hotelrunner_total_repair import (
    reconcile_hotelrunner_guest_totals_from_local_events,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, *_args):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return self.rows[:length]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()


def _database(*, booking_total=5357.14, modified_count=1):
    payload = {
        "hr_number": "R017934708",
        "total": 6000,
        "rooms": [{"price": 5357.14, "total": 6000}],
    }
    raw_events = SimpleNamespace(
        find=lambda *_args: _Cursor(
            [
                {
                    "tenant_id": "tenant-a",
                    "external_reservation_id": "R017934708",
                    "raw_payload": payload,
                    "received_at": "2026-08-27T12:00:00Z",
                }
            ]
        )
    )
    bookings = SimpleNamespace(
        find=lambda *_args: _Cursor(
            [
                {
                    "id": "booking-1",
                    "tenant_id": "tenant-a",
                    "external_reservation_id": "R017934708",
                    "total_amount": booking_total,
                }
            ]
        ),
        update_one=AsyncMock(
            return_value=SimpleNamespace(modified_count=modified_count)
        ),
    )
    imported = SimpleNamespace(update_one=AsyncMock())
    return SimpleNamespace(
        raw_channel_events=raw_events,
        bookings=bookings,
        imported_reservations=imported,
    )


@pytest.mark.asyncio
async def test_repairs_exact_legacy_net_total_from_local_event_without_provider_io():
    database = _database()

    repaired = await reconcile_hotelrunner_guest_totals_from_local_events(database)

    assert repaired == 1
    booking_filter = database.bookings.update_one.await_args.args[0]
    booking_set = database.bookings.update_one.await_args.args[1]["$set"]
    assert booking_filter["total_amount"] == 5357.14
    assert booking_set["total_amount"] == 6000
    assert booking_set["provider_total_amount"] == 6000
    assert booking_set["pricing_tax_inclusive"] is True
    assert booking_set["hotelrunner_total_reconciliation_source"] == "local_raw_event"
    imported_set = database.imported_reservations.update_one.await_args.args[1]["$set"]
    assert imported_set["total_amount"] == 6000


@pytest.mark.asyncio
async def test_preserves_operator_adjusted_total():
    database = _database(booking_total=5700)

    repaired = await reconcile_hotelrunner_guest_totals_from_local_events(database)

    assert repaired == 0
    database.bookings.update_one.assert_not_awaited()
    database.imported_reservations.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_and_set_prevents_double_repair_across_replicas():
    database = _database(modified_count=0)

    repaired = await reconcile_hotelrunner_guest_totals_from_local_events(database)

    assert repaired == 0
    database.imported_reservations.update_one.assert_not_awaited()
