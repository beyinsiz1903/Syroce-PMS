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
    resolve_legacy_hotelrunner_note,
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


@pytest.mark.asyncio
async def test_resolves_legacy_note_from_linked_import_record():
    imported = _collection(
        find_one=AsyncMock(
            return_value={
                "provider": "hotelrunner",
                "provider_note": "Late arrival requested by Expedia",
                "provider_updated_at": "2026-08-30T14:00:00Z",
            }
        )
    )
    lineage = _collection()
    database = SimpleNamespace(
        imported_reservations=imported,
        reservation_lineage=lineage,
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-NOTE",
            "source": {
                "provider": "hotelrunner",
                "import_record_id": "import-a",
            },
        },
    )

    assert note is not None
    assert note["content"] == "Late arrival requested by Expedia"
    assert note["source"] == "hotelrunner"
    assert note["created_by"] == "HotelRunner / Acente"
    imported.find_one.assert_awaited_once_with(
        {"id": "import-a", "tenant_id": "tenant-a"},
        {
            "_id": 0,
            "provider": 1,
            "provider_note": 1,
            "raw_payload": 1,
            "payload": 1,
            "provider_updated_at": 1,
            "provider_last_modified_at": 1,
            "received_at": 1,
            "updated_at": 1,
            "created_at": 1,
        },
    )
    lineage.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolves_legacy_note_from_lineage_when_import_has_no_snapshot():
    imported = _collection(find_one=AsyncMock(return_value=None))
    lineage = _collection(
        find_one=AsyncMock(
            return_value={
                "provider_note": "Agency requested a quiet room",
                "provider_last_modified_at": "2026-08-30T15:00:00Z",
            }
        )
    )
    database = SimpleNamespace(
        imported_reservations=imported,
        reservation_lineage=lineage,
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-NOTE",
            "source": {"provider": "hotelrunner"},
        },
    )

    assert note is not None
    assert note["content"] == "Agency requested a quiet room"
    assert note["created_at"] == "2026-08-30T15:00:00Z"
    assert imported.find_one.await_count == 1
    lineage.find_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_note_resolver_ignores_non_hotelrunner_booking():
    database = SimpleNamespace(
        imported_reservations=_collection(),
        reservation_lineage=_collection(),
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-NOTE",
            "source": {"provider": "other-provider"},
        },
    )

    assert note is None
    database.imported_reservations.find_one.assert_not_awaited()
    database.reservation_lineage.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolves_old_hotelrunner_booking_without_source_metadata():
    imported = _collection(
        find_one=AsyncMock(
            return_value={
                "provider": "hotelrunner",
                "provider_note": "High floor requested by the agency",
            }
        )
    )
    database = SimpleNamespace(
        imported_reservations=imported,
        reservation_lineage=_collection(),
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-OLD-NOTE",
            "source": {"import_record_id": "import-a"},
        },
    )

    assert note is not None
    assert note["content"] == "High floor requested by the agency"
    assert note["source"] == "hotelrunner"


@pytest.mark.asyncio
async def test_resolves_old_note_from_unified_raw_event_when_snapshot_has_none():
    imported = _collection(
        find_one=AsyncMock(return_value={"provider": "hotelrunner"})
    )
    raw_events = _collection(
        find_one=AsyncMock(
            return_value={
                "raw_payload": {
                    "note": "Smoking Type:UNSPECIFIED Payment Method:HotelCollect",
                    "rooms": [{"comments": [{"body": "Late arrival"}]}],
                },
                "received_at": "2026-08-30T16:00:00Z",
            }
        )
    )
    database = SimpleNamespace(
        imported_reservations=imported,
        reservation_lineage=_collection(),
        raw_channel_events=raw_events,
        hotelrunner_raw_events=_collection(),
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-OLD-NOTE",
            "source": {
                "provider": "hotelrunner",
                "import_record_id": "import-a",
            },
        },
    )

    assert note is not None
    assert note["content"] == (
        "Smoking Type:UNSPECIFIED Payment Method:HotelCollect\nLate arrival"
    )
    assert note["created_at"] == "2026-08-30T16:00:00Z"
    raw_events.find_one.assert_awaited_once_with(
        {
            "tenant_id": "tenant-a",
            "provider": "hotelrunner",
            "external_reservation_id": "R-OLD-NOTE",
            "raw_payload": {"$type": "object"},
        },
        {
            "_id": 0,
            "raw_payload": 1,
            "provider_timestamp": 1,
            "received_at": 1,
        },
        sort=[("received_at", -1)],
    )


@pytest.mark.asyncio
async def test_resolves_old_note_from_legacy_hotelrunner_raw_event():
    legacy_events = _collection(
        find_one=AsyncMock(
            return_value={
                "payload": {"comments": [{"body": "Agency airport transfer"}]},
                "received_at": "2026-08-30T17:00:00Z",
            }
        )
    )
    database = SimpleNamespace(
        imported_reservations=_collection(),
        reservation_lineage=_collection(),
        raw_channel_events=_collection(),
        hotelrunner_raw_events=legacy_events,
    )

    note = await resolve_legacy_hotelrunner_note(
        database,
        tenant_id="tenant-a",
        booking={
            "id": "booking-a",
            "external_reservation_id": "R-LEGACY-NOTE",
            "source": {"provider": "hotelrunner"},
        },
    )

    assert note is not None
    assert note["content"] == "Agency airport transfer"
    assert note["created_at"] == "2026-08-30T17:00:00Z"
