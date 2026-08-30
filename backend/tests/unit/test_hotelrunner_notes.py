from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.ingest.normalizer import (
    compute_canonical_hash,
    normalize_hotelrunner,
)
from domains.channel_manager.providers import sync_engine
from domains.channel_manager.providers.hotelrunner_notes import (
    extract_hotelrunner_note,
    sync_hotelrunner_note,
)


def _collection(**methods):
    defaults = {
        "find_one": AsyncMock(return_value=None),
        "update_one": AsyncMock(
            return_value=SimpleNamespace(matched_count=1, modified_count=1)
        ),
        "delete_one": AsyncMock(
            return_value=SimpleNamespace(deleted_count=1)
        ),
    }
    defaults.update(methods)
    return SimpleNamespace(**defaults)


def test_extracts_root_note_and_unique_room_comments():
    payload = {
        "note": "Smoking Type:UNSPECIFIED Payment Method:HotelCollect",
        "rooms": [
            {
                "comments": [
                    {"body": "Late arrival"},
                    {"body": "Late arrival"},
                ]
            }
        ],
    }

    assert extract_hotelrunner_note(payload) == (
        "Smoking Type:UNSPECIFIED Payment Method:HotelCollect\nLate arrival"
    )


def test_provider_note_participates_in_canonical_change_hash():
    without_note = normalize_hotelrunner({"hr_number": "R-NOTE", "rooms": []})
    with_note = normalize_hotelrunner(
        {"hr_number": "R-NOTE", "note": "Hotel collect", "rooms": []}
    )

    assert with_note["provider_note"] == "Hotel collect"
    assert compute_canonical_hash(without_note) != compute_canonical_hash(with_note)


@pytest.mark.asyncio
async def test_sync_uses_one_deterministic_provider_owned_note():
    notes = _collection()
    database = SimpleNamespace(reservation_notes=notes)

    await sync_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking_id="booking-a",
        external_reservation_id="R-NOTE",
        content="Hotel collect",
        provider_updated_at="2026-08-30T12:00:00Z",
    )
    await sync_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking_id="booking-a",
        external_reservation_id="R-NOTE",
        content="Hotel collect - updated",
        provider_updated_at="2026-08-30T13:00:00Z",
    )

    first_filter = notes.update_one.await_args_list[0].args[0]
    second_filter = notes.update_one.await_args_list[1].args[0]
    assert first_filter == second_filter
    assert notes.update_one.await_args_list[1].kwargs["upsert"] is True
    assert notes.update_one.await_args_list[1].args[1]["$set"]["content"] == (
        "Hotel collect - updated"
    )


@pytest.mark.asyncio
async def test_stale_pull_backfills_missing_note_without_mutating_booking(monkeypatch):
    booking = {
        "id": "booking-a",
        "guest_name": "Guest",
        "status": "confirmed",
        "total_amount": 6000,
        "last_synced_from_provider_at": "2026-08-30T13:00:00Z",
    }
    bookings = _collection(find_one=AsyncMock(return_value=booking))
    notes = _collection()
    fake_db = SimpleNamespace(
        bookings=bookings,
        reservation_notes=notes,
        imported_reservations=_collection(),
        room_mappings=_collection(),
        guests=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(sync_engine, "db", fake_db)

    updated = await sync_engine.sync_reservation_update(
        "tenant-a",
        "R-NOTE",
        {
            "note": "Smoking Type:UNSPECIFIED Payment Method:HotelCollect",
            "total": 6000,
            "rooms": [],
        },
        "confirmed",
        "2026-08-30T12:00:00Z",
    )

    assert updated is True
    bookings.update_one.assert_not_awaited()
    note_update = notes.update_one.await_args.args[1]
    assert "$setOnInsert" in note_update
    assert "$set" not in note_update
    assert note_update["$setOnInsert"]["content"].startswith("Smoking Type")
