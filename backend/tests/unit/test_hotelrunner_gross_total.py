from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.ingest.normalizer import normalize_hotelrunner
from domains.channel_manager.providers import sync_engine
from domains.channel_manager.providers.hotelrunner_shared import explode_multi_room_reservation


def _hotelrunner_room(*, before_tax=5357.14, after_tax=6000.0, code="room-1"):
    return {
        "inv_code": code,
        "price": before_tax,
        "total": after_tax,
        "total_adult": 2,
    }


def test_single_room_preserves_hotelrunner_guest_payable_grand_total():
    payload = {
        "hr_number": "R017934708",
        "total": 6000,
        "sub_total": 5357.14,
        "tax_total": 642.86,
        "rooms": [_hotelrunner_room()],
    }

    canonical = normalize_hotelrunner(payload)

    assert canonical["total_amount"] == 6000


def test_exploded_rooms_use_each_room_after_tax_total():
    payload = {
        "hr_number": "R-MULTI",
        "total": 8400,
        "rooms": [
            _hotelrunner_room(before_tax=3571.43, after_tax=4000, code="room-1"),
            _hotelrunner_room(before_tax=3928.57, after_tax=4400, code="room-2"),
        ],
    }

    exploded = explode_multi_room_reservation(payload)

    assert [item["total"] for item in exploded] == [4000, 4400]
    assert [normalize_hotelrunner(item)["total_amount"] for item in exploded] == [4000, 4400]


def test_before_tax_price_is_only_a_compatibility_fallback():
    canonical = normalize_hotelrunner(
        {"hr_number": "R-LEGACY", "rooms": [{"inv_code": "room-1", "price": 2500}]}
    )

    assert canonical["total_amount"] == 2500


def _collection(**methods):
    defaults = {
        "find_one": AsyncMock(return_value=None),
        "update_one": AsyncMock(return_value=SimpleNamespace(matched_count=1, modified_count=1)),
    }
    defaults.update(methods)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_pull_sync_repairs_exact_legacy_net_import_even_when_timestamp_is_stale(monkeypatch):
    booking = {
        "id": "booking-1",
        "external_reservation_id": "R017934708",
        "guest_name": "Murat Aslan",
        "status": "confirmed",
        "total_amount": 5357.14,
        "last_synced_from_provider_at": "2026-08-27T12:00:00Z",
    }
    bookings = _collection(find_one=AsyncMock(return_value=booking))
    imported = _collection()
    fake_db = SimpleNamespace(
        bookings=bookings,
        imported_reservations=imported,
        room_mappings=_collection(),
        guests=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(sync_engine, "db", fake_db)
    monkeypatch.setattr(sync_engine, "publish_booking_change", AsyncMock(return_value=True))
    monkeypatch.setattr(sync_engine, "_timeline_append", AsyncMock())

    updated = await sync_engine.sync_reservation_update(
        "tenant-a",
        "R017934708",
        {
            "firstname": "Older",
            "lastname": "Provider Name",
            "total": 6000,
            "rooms": [_hotelrunner_room()],
        },
        "confirmed",
        "2026-08-26T12:00:00Z",
    )

    assert updated is True
    booking_set = bookings.update_one.await_args.args[1]["$set"]
    assert booking_set["total_amount"] == 6000
    assert booking_set["provider_total_amount"] == 6000
    assert booking_set["pricing_tax_inclusive"] is True
    assert booking_set["pricing_source"] == "channel_manager"
    assert booking_set["hotelrunner_total_reconciled_from"] == 5357.14
    assert "last_synced_from_provider_at" not in booking_set
    assert "guest_name" not in booking_set
    imported_set = imported.update_one.await_args.args[1]["$set"]
    assert imported_set["total_amount"] == 6000
    assert "provider_updated_at" not in imported_set


@pytest.mark.asyncio
async def test_current_single_room_pull_prefers_reservation_grand_total(monkeypatch):
    booking = {
        "id": "booking-2",
        "guest_name": "Guest",
        "status": "confirmed",
        "total_amount": 100,
    }
    bookings = _collection(find_one=AsyncMock(return_value=booking))
    fake_db = SimpleNamespace(
        bookings=bookings,
        imported_reservations=_collection(),
        room_mappings=_collection(),
        guests=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(sync_engine, "db", fake_db)
    monkeypatch.setattr(sync_engine, "publish_booking_change", AsyncMock(return_value=True))
    monkeypatch.setattr(sync_engine, "_timeline_append", AsyncMock())

    await sync_engine.sync_reservation_update(
        "tenant-a",
        "R-ROOT-WINS",
        {"total": 6000, "rooms": [_hotelrunner_room(after_tax=5900)]},
        "confirmed",
        "2026-08-28T12:00:00Z",
    )

    booking_set = bookings.update_one.await_args.args[1]["$set"]
    assert booking_set["total_amount"] == 6000
