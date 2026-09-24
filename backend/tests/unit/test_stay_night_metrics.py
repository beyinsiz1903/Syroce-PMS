from datetime import date

from modules.pms_core.stay_night_metrics import booking_nights, booking_occupies_night, calculate_stay_night_metrics


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


def test_room_number_and_room_id_resolve_to_one_physical_room():
    metrics = calculate_stay_night_metrics(
        [
            {
                "room_id": "r1",
                "status": "confirmed",
                "check_in": "2026-09-23",
                "check_out": "2026-09-24",
                "total_amount": 100,
            },
            {
                "room_number": "201",
                "status": "confirmed",
                "check_in": "2026-09-23",
                "check_out": "2026-09-24",
                "total_amount": 50,
            },
        ],
        [{"id": "r1", "room_number": "201"}],
        date(2026, 9, 23),
        date(2026, 9, 23),
    )

    assert metrics[0]["occupied_rooms"] == 1
    assert metrics[0]["total_rooms"] == 1
    assert metrics[0]["revenue"] == 150
    assert metrics[0]["adr"] == 150


def test_actual_occupancy_excludes_unchecked_confirmed_and_respects_early_checkout():
    rooms = [{"id": "r1"}, {"id": "r2"}]
    bookings = [
        {
            "room_id": "r1",
            "status": "confirmed",
            "check_in": "2026-09-20",
            "check_out": "2026-09-22",
            "total_amount": 2000,
        },
        {
            "room_id": "r2",
            "status": "checked_out",
            "check_in": "2026-09-20",
            "check_out": "2026-09-23",
            "checked_in_at": "2026-09-20T14:00:00Z",
            "checked_out_at": "2026-09-21T09:00:00Z",
            "total_amount": 3000,
        },
    ]

    metrics = calculate_stay_night_metrics(
        bookings,
        rooms,
        date(2026, 9, 20),
        date(2026, 9, 22),
        actual_only=True,
    )

    assert [row["occupied_rooms"] for row in metrics] == [1, 0, 0]
    assert booking_occupies_night(bookings[0], date(2026, 9, 20), actual_only=True) is False
    assert booking_nights(bookings[1]) == 3


def test_checkout_day_is_never_a_room_night():
    booking = {
        "room_id": "r1",
        "status": "checked_out",
        "check_in": "2026-09-20",
        "check_out": "2026-09-21",
    }

    assert booking_occupies_night(booking, date(2026, 9, 20)) is True
    assert booking_occupies_night(booking, date(2026, 9, 21)) is False


def test_legacy_in_house_status_is_realised_occupancy():
    booking = {
        "room_id": "r1",
        "status": "in_house",
        "check_in": "2026-09-20",
        "check_out": "2026-09-22",
        "checked_in_at": "2026-09-20T15:00:00Z",
    }

    assert booking_occupies_night(booking, date(2026, 9, 20), actual_only=True) is True


def test_out_of_order_block_reduces_available_room_nights_only_for_its_interval():
    metrics = calculate_stay_night_metrics(
        [],
        [{"id": "r1"}, {"id": "r2"}],
        date(2026, 9, 20),
        date(2026, 9, 22),
        room_blocks=[
            {
                "room_id": "r1",
                "status": "active",
                "allow_sell": False,
                "start_date": "2026-09-20",
                "end_date": "2026-09-22",
            }
        ],
    )

    assert [row["total_rooms"] for row in metrics] == [1, 1, 2]
