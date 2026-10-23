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
        assert projection == {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1}
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
