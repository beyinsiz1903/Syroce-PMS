from datetime import UTC, datetime

from domains.revenue.forecast_router import _allocate_booking, _build_forecast_rows


def test_forecast_uses_real_history_caps_capacity_and_reports_source():
    today = datetime(2026, 8, 24, tzinfo=UTC)
    daily = {"2026-08-24": {"rooms": 2.0, "revenue": 400.0}}
    history = {
        "2026-08-17": {"rooms": 8.0, "revenue": 1200.0},
        "2026-08-10": {"rooms": 12.0, "revenue": 1800.0},
    }

    rows, quality = _build_forecast_rows(daily, history, total_rooms=9, today=today)

    assert rows[0]["rooms_otb"] == 2
    assert rows[0]["rooms_forecast"] == 9.0
    assert rows[0]["occupancy_pct"] == 100.0
    assert rows[0]["revenue_forecast"] == 1450.0
    assert rows[0]["source"] == "otb_plus_historical_weekday"
    assert quality["historical_room_nights"] == 20


def test_forecast_does_not_fabricate_pickup_without_history():
    today = datetime(2026, 8, 24, tzinfo=UTC)
    rows, quality = _build_forecast_rows(
        {"2026-08-24": {"rooms": 3.0, "revenue": 600.0}},
        {},
        total_rooms=10,
        today=today,
    )
    assert rows[0]["rooms_forecast"] == 3.0
    assert rows[0]["revenue_forecast"] == 600.0
    assert rows[0]["source"] == "on_the_books_only"
    assert quality["warning"]


def test_booking_allocation_includes_stay_started_before_window():
    start = datetime(2026, 8, 24, tzinfo=UTC)
    end = datetime(2026, 8, 26, tzinfo=UTC)
    daily = {
        "2026-08-24": {"rooms": 0.0, "revenue": 0.0},
        "2026-08-25": {"rooms": 0.0, "revenue": 0.0},
    }
    _allocate_booking(
        {"check_in": "2026-08-23", "check_out": "2026-08-26", "total_amount": 900},
        start,
        end,
        daily,
    )
    assert daily["2026-08-24"] == {"rooms": 1.0, "revenue": 300.0}
    assert daily["2026-08-25"] == {"rooms": 1.0, "revenue": 300.0}

