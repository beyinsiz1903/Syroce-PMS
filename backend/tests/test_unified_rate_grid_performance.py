"""Regression coverage for rate-manager grid occupancy calculation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domains.channel_manager import unified_rate_manager_router as rate_router
from domains.channel_manager.unified_rate_manager_router import _build_dates, _build_sold_count_index


def test_precomputed_sold_counts_match_grid_availability():
    room_ids_by_type = {"standard": ["room-1", "room-2"]}
    bookings = [
        {"room_id": "room-1", "check_in": "2026-10-02", "check_out": "2026-10-04"},
        {"room_id": "room-2", "check_in": "2026-10-03", "check_out": "2026-10-05"},
    ]

    sold_counts = _build_sold_count_index(room_ids_by_type, bookings, "2026-10-01", "2026-10-05")
    dates = _build_dates(
        "2026-10-01",
        "2026-10-05",
        "standard",
        "BAR",
        {},
        "standard",
        {"total": 5, "available": 5},
        room_ids_by_type,
        bookings,
        sold_counts,
    )

    assert [row["sold"] for row in dates] == [0, 1, 2, 1, 0]
    assert [row["availability"] for row in dates] == [5, 4, 3, 4, 5]


def test_precomputed_sold_counts_ignore_invalid_and_outside_bookings():
    sold_counts = _build_sold_count_index(
        {"standard": ["room-1"]},
        [
            {"room_id": "room-1", "check_in": "invalid", "check_out": "2026-10-04"},
            {"room_id": "other-room", "check_in": "2026-10-02", "check_out": "2026-10-04"},
            {"room_id": "room-1", "check_in": "2026-09-29", "check_out": "2026-10-02"},
        ],
        "2026-10-01",
        "2026-10-03",
    )

    assert sold_counts == {("standard", "2026-10-01"): 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(("start_date", "end_date", "next_date"), [
    ("2026-10-01", "2026-10-03", "2026-10-04"),
    ("2026-10-03", "2026-10-03", "2026-10-04"),
    ("2026-10-31", "2026-10-31", "2026-11-01"),
    ("2026-12-31", "2026-12-31", "2027-01-01"),
])
@pytest.mark.parametrize("time_suffix", ["", "T15:00:00+03:00"])
async def test_grid_query_includes_arrivals_on_its_inclusive_last_day(
    monkeypatch, start_date, end_date, next_date, time_suffix,
):
    """Exercise query filtering as well as the in-memory occupancy index.

    A grid's last date is a sellable night, not an exclusive checkout date.
    Cover a single-day view and timestamp-shaped reservation dates too.
    """
    bookings = [
        {"room_id": "room-1", "check_in": f"{end_date}{time_suffix}", "check_out": next_date},
        {"room_id": "room-2", "check_in": next_date, "check_out": "2027-01-05"},
        {"room_id": "room-3", "check_in": "2026-09-29", "check_out": start_date},
    ]

    def find(query, projection):
        assert query["tenant_id"] == "tenant-test"
        assert query["status"] == {"$in": ["pending", "confirmed", "guaranteed", "checked_in"]}
        assert projection == {"_id": 0, "room_id": 1, "room_type": 1, "check_in": 1, "check_out": 1}
        matching = [
            row for row in bookings
            if row["check_in"] < query["check_in"]["$lt"]
            and row["check_out"] > query["check_out"]["$gt"]
        ]
        return SimpleNamespace(to_list=AsyncMock(return_value=matching))

    collection = SimpleNamespace(find=MagicMock(side_effect=find))
    monkeypatch.setattr(rate_router, "db", SimpleNamespace(bookings=collection))
    active = await rate_router._get_active_bookings("tenant-test", start_date, end_date)

    assert active == [bookings[0]]
    assert collection.find.call_args.args[0]["check_in"] == {"$lt": next_date}
    room_ids = {"standard": ["room-1", "room-2", "room-3"]}
    sold = _build_sold_count_index(room_ids, active, start_date, end_date)
    dates = _build_dates(
        start_date, end_date, "standard", "BAR", {}, "standard",
        {"total": 3}, room_ids, active, sold,
    )
    assert dates[-1]["sold"] == 1
    assert dates[-1]["availability"] == 2


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("room_id", [None, "", "removed-or-placeholder-room"])
def test_unassigned_mapped_room_type_consumes_each_stay_night(indexed, room_id):
    rooms = {"standard": ["std-1", "std-2"], "deluxe": ["dlx-1"]}
    bookings = [
        {"room_id": room_id, "room_type": "standard", "check_in": "2026-11-10", "check_out": "2026-11-12"},
        {"room_id": None, "room_type": "deluxe", "check_in": "2026-11-10", "check_out": "2026-11-11"},
    ]
    sold = _build_sold_count_index(rooms, bookings, "2026-11-09", "2026-11-12") if indexed else None
    dates = _build_dates(
        "2026-11-09", "2026-11-12", "STD", "BAR", {}, "standard",
        {"total": 2}, rooms, bookings, sold,
    )
    assert [row["sold"] for row in dates] == [0, 1, 1, 0]
    assert [row["availability"] for row in dates] == [2, 1, 1, 2]


def test_assignment_overrides_stale_type_without_counting_the_booking_twice():
    rooms = {"standard": ["std-1"], "deluxe": ["dlx-1"]}
    bookings = [{"room_id": "dlx-1", "room_type": "standard", "check_in": "2026-11-10", "check_out": "2026-11-11"}]
    assert _build_sold_count_index(rooms, bookings, "2026-11-10", "2026-11-10") == {("deluxe", "2026-11-10"): 1}


def test_missing_or_foreign_room_type_is_not_guessed():
    bookings = [
        {"room_id": None, "check_in": "2026-11-10", "check_out": "2026-11-11"},
        {"room_id": None, "room_type": "foreign-category", "check_in": "2026-11-10", "check_out": "2026-11-11"},
    ]
    assert _build_sold_count_index({"standard": ["std-1"]}, bookings, "2026-11-10", "2026-11-10") == {}


@pytest.mark.asyncio
async def test_exely_import_fields_survive_grid_projection_and_count_before_assignment(monkeypatch):
    from domains.channel_manager.providers.exely.pms_lifecycle import _booking_fields

    imported = _booking_fields(
        tenant_id="synthetic-test", property_id="TEST-PROPERTY",
        reservation={"external_id": "SYNTHETIC-UNASSIGNED", "currency": "USD"},
        version_doc={"provider_version_key": "synthetic-version"},
        room={"check_in": "2026-11-10", "check_out": "2026-11-11", "amount": 120, "adults": 2},
        mapping={"pms_room_type": "deluxe"}, slot=0, guest_id="synthetic-guest", booking_id="synthetic-booking",
    )
    assert imported["room_id"] is None
    assert imported["status"] == "confirmed"

    def find(query, projection):
        assert query["tenant_id"] == imported["tenant_id"]
        assert imported["status"] in query["status"]["$in"]
        # Apply the real MongoDB projection: manually passing the full booking
        # would conceal the original lost-room-type query defect.
        projected = {key: imported[key] for key, include in projection.items() if include and key in imported}
        return SimpleNamespace(to_list=AsyncMock(return_value=[projected]))

    monkeypatch.setattr(rate_router, "db", SimpleNamespace(bookings=SimpleNamespace(find=find)))
    bookings = await rate_router._get_active_bookings("synthetic-test", "2026-11-10", "2026-11-10")
    assert _build_sold_count_index({"deluxe": ["dlx-1"]}, bookings, "2026-11-10", "2026-11-10") == {
        ("deluxe", "2026-11-10"): 1,
    }
