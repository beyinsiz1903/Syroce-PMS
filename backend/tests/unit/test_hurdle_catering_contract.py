from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domains.pms import catering_router
from domains.revenue import hurdle_router


class _AsyncRows:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        async def _iterate():
            for row in self.rows:
                yield dict(row)

        return _iterate()


def _user():
    return SimpleNamespace(tenant_id="tenant-a", email="admin@example.com")


@pytest.mark.asyncio
async def test_hurdle_check_uses_most_specific_matching_rule():
    hurdles = MagicMock()
    hurdles.find = MagicMock(return_value=_AsyncRows([
        {"id": "all", "name": "Genel", "min_rate": 100, "currency": "TRY"},
        {"id": "specific", "name": "Deluxe OTA", "min_rate": 150, "currency": "TRY", "room_type": "Deluxe", "channel": "booking"},
    ]))
    fake_db = MagicMock(hurdle_rates=hurdles)

    with patch.object(hurdle_router, "get_system_db", return_value=fake_db):
        result = await hurdle_router.check_rate(
            target_date="2026-08-24",
            proposed_rate=140,
            room_type="Deluxe",
            channel="booking",
            user=_user(),
        )

    assert result["applied_hurdle"]["id"] == "specific"
    assert result["allowed"] is False
    assert hurdles.find.call_args.args[0]["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_catering_booking_snapshots_price_and_currency():
    menu_items = MagicMock()
    menu_items.find = MagicMock(return_value=_AsyncRows([
        {"id": "menu-a", "name": "Kahve Molası", "price_per_person": 25, "currency": "TRY", "min_headcount": 2},
    ]))
    booking_menus = MagicMock()
    booking_menus.update_one = AsyncMock()
    fake_db = MagicMock(catering_menu_items=menu_items, catering_booking_menus=booking_menus)

    with (
        patch.object(catering_router, "get_system_db", return_value=fake_db),
        patch.object(catering_router, "_ensure_indexes", new=AsyncMock()),
        patch.object(catering_router, "_booking_exists", new=AsyncMock(return_value={"id": "booking-a"})),
    ):
        result = await catering_router.set_booking_menus(
            booking_id="booking-a",
            payload=catering_router.BookingMenuPayload(
                lines=[catering_router.BookingMenuLine(menu_item_id="menu-a", headcount=10)]
            ),
            user=_user(),
        )

    assert result == {"ok": True, "count": 1, "currency": "TRY"}
    query, update = booking_menus.update_one.await_args.args
    assert query == {"tenant_id": "tenant-a", "booking_id": "booking-a"}
    line = update["$set"]["lines"][0]
    assert line["price_per_person_snapshot"] == 25.0
    assert line["currency_snapshot"] == "TRY"


@pytest.mark.asyncio
async def test_catering_rejects_mixed_currency_booking():
    menu_items = MagicMock()
    menu_items.find = MagicMock(return_value=_AsyncRows([
        {"id": "menu-a", "name": "Kahve", "price_per_person": 25, "currency": "TRY", "min_headcount": 1},
        {"id": "menu-b", "name": "Kokteyl", "price_per_person": 15, "currency": "EUR", "min_headcount": 1},
    ]))
    fake_db = MagicMock(catering_menu_items=menu_items, catering_booking_menus=MagicMock())

    with (
        patch.object(catering_router, "get_system_db", return_value=fake_db),
        patch.object(catering_router, "_ensure_indexes", new=AsyncMock()),
        patch.object(catering_router, "_booking_exists", new=AsyncMock(return_value={"id": "booking-a"})),
    ):
        with pytest.raises(Exception) as exc:
            await catering_router.set_booking_menus(
                booking_id="booking-a",
                payload=catering_router.BookingMenuPayload(lines=[
                    catering_router.BookingMenuLine(menu_item_id="menu-a", headcount=5),
                    catering_router.BookingMenuLine(menu_item_id="menu-b", headcount=5),
                ]),
                user=_user(),
            )

    assert getattr(exc.value, "status_code", None) == 400
