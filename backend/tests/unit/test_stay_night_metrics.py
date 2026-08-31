from datetime import date

from modules.pms_core.stay_night_metrics import calculate_stay_night_metrics


def test_room_nights_are_unique_checkout_exclusive_and_revenue_is_allocated():
    rooms = [{"id": "r1"}, {"id": "r2"}, {"id": "inactive", "is_active": False}]
    bookings = [
        {
            "id": "old",
            "room_id": "r1",
            "status": "checked_out",
            "check_in": "2026-08-28T14:00:00+00:00",
            "check_out": "2026-08-30T11:00:00+00:00",
            "total_amount": 4000,
        },
        {
            "id": "duplicate-room",
            "room_id": "r1",
            "status": "confirmed",
            "check_in": "2026-08-29",
            "check_out": "2026-08-30",
            "total_amount": 1000,
        },
        {
            "id": "second-room",
            "room_id": "r2",
            "status": "checked_in",
            "check_in": "2026-08-29",
            "check_out": "2026-08-31",
            "total_amount": 2000,
        },
        {
            "id": "cancelled",
            "room_id": "r2",
            "status": "cancelled",
            "check_in": "2026-08-29",
            "check_out": "2026-08-30",
            "total_amount": 9999,
        },
    ]

    metrics = calculate_stay_night_metrics(bookings, rooms, date(2026, 8, 29), date(2026, 8, 31))

    assert metrics[0] == {
        "date": "2026-08-29",
        "occupied_rooms": 2,
        "total_rooms": 2,
        "occupancy_rate": 100.0,
        "revenue": 4000.0,
        "adr": 2000.0,
        "revpar": 2000.0,
    }
    assert metrics[1]["occupied_rooms"] == 1
    assert metrics[1]["revenue"] == 1000.0
    assert metrics[2]["occupied_rooms"] == 0
    assert metrics[2]["revenue"] == 0.0


def test_unassigned_booking_does_not_inflate_room_occupancy():
    metrics = calculate_stay_night_metrics(
        [{"status": "confirmed", "check_in": "2026-08-29", "check_out": "2026-08-30", "total_amount": 4000}],
        [{"id": "r1"}],
        date(2026, 8, 29),
        date(2026, 8, 29),
    )
    assert metrics[0]["occupied_rooms"] == 0
    assert metrics[0]["revenue"] == 0.0
