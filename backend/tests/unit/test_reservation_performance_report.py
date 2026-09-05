from datetime import date

from routers.reports_pkg.reservation_performance import aggregate_reservation_performance


def test_aggregate_reservation_performance_separates_cancellations_and_channels():
    payload = aggregate_reservation_performance(
        [
            {
                "id": "confirmed-direct",
                "guest_name": "Ada Guest",
                "room_number": "101",
                "check_in": "2026-09-10T14:00:00+00:00",
                "check_out": "2026-09-13T12:00:00+00:00",
                "created_at": "2026-08-31T09:00:00+00:00",
                "status": "confirmed",
                "channel": "direct",
                "total_amount": 4500,
            },
            {
                "id": "cancelled-ota",
                "guest_name": "Cancelled Guest",
                "room_number": "102",
                "check_in": "2026-09-11T14:00:00+00:00",
                "check_out": "2026-09-12T12:00:00+00:00",
                "created_at": "2026-09-01T09:00:00+00:00",
                "status": "cancelled",
                "ota_channel": "agoda",
                "total_amount": 1200,
            },
            {
                "id": "no-show-ota",
                "guest_name": "No Show Guest",
                "room_number": "103",
                "check_in": "2026-09-12T14:00:00+00:00",
                "check_out": "2026-09-14T12:00:00+00:00",
                "created_at": "2026-09-12T10:00:00+00:00",
                "status": "no_show",
                "source_channel": "booking_com",
                "total_amount": 2500,
            },
        ],
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 12),
    )

    assert payload["summary"] == {
        "total_bookings": 3,
        "commercial_bookings": 1,
        "booked_revenue": 4500.0,
        "total_room_nights": 3,
        "average_stay": 3.0,
        "average_lead_time": 6.7,
        "cancelled_count": 1,
        "no_show_count": 1,
        "cancellation_rate": 33.3,
        "cancelled_value": 3700.0,
    }
    assert [(item["channel"], item["bookings"], item["revenue"], item["cancelled"]) for item in payload["channel_breakdown"]] == [
        ("agoda", 1, 0.0, 1),
        ("booking_com", 1, 0.0, 1),
        ("direct", 1, 4500.0, 0),
    ]
    assert payload["daily_arrivals"] == [
        {"date": "2026-09-10", "reservations": 1, "commercial_reservations": 1, "revenue": 4500.0},
        {"date": "2026-09-11", "reservations": 1, "commercial_reservations": 0, "revenue": 0.0},
        {"date": "2026-09-12", "reservations": 1, "commercial_reservations": 0, "revenue": 0.0},
    ]
    assert {item["bucket"]: item["count"] for item in payload["lead_time_breakdown"]} == {
        "same_day": 1,
        "one_to_three": 0,
        "four_to_seven": 0,
        "eight_to_fourteen": 2,
        "fifteen_to_thirty": 0,
        "thirty_plus": 0,
    }


def test_aggregate_reservation_performance_handles_legacy_invalid_dates_without_losing_row():
    payload = aggregate_reservation_performance(
        [{"id": "legacy", "guest_name": "Legacy", "check_in": "not-a-date", "status": "confirmed", "total_amount": "200"}],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )

    assert payload["summary"]["total_bookings"] == 1
    assert payload["summary"]["booked_revenue"] == 200.0
    assert payload["rows"] == [
        {
            "booking_id": "legacy",
            "guest_name": "Legacy",
            "room_number": "-",
            "check_in": "not-a-date",
            "check_out": "",
            "status": "confirmed",
            "status_label": "Onaylandı",
            "channel": "direct",
            "total_amount": 200.0,
            "nights": 0,
            "lead_time_days": None,
        }
    ]
