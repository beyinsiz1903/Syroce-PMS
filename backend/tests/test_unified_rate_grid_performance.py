"""Regression coverage for rate-manager grid occupancy calculation."""

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
