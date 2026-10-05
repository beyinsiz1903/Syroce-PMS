from routers import reservation_detail


def test_partial_daily_rate_plan_is_completed_through_checkout_exclusive():
    booking = {
        "check_in": "2026-09-28T14:00:00",
        "check_out": "2026-10-03T12:00:00",
        "total_amount": 17500,
    }
    persisted_rates = [
        {"id": "rate-1", "date": "2026-09-28", "rate": 2500},
        {"id": "rate-2", "date": "2026-09-29", "rate": 2500},
        {"id": "rate-3", "date": "2026-09-30", "rate": 2500},
        {"id": "rate-4", "date": "2026-10-01", "rate": 2500},
    ]

    completed = reservation_detail._complete_daily_rates_for_stay(persisted_rates, booking)

    assert [row["date"] for row in completed] == [
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
    ]
    assert completed[-1] == {
        "date": "2026-10-02",
        "rate": 7500,
        "generated": True,
        "generated_reason": "missing_daily_rate",
    }
    assert sum(row["rate"] for row in completed) == 17500


def test_empty_daily_rate_plan_distributes_every_cent_across_stay():
    completed = reservation_detail._complete_daily_rates_for_stay(
        [],
        {
            "check_in": "2026-10-01",
            "check_out": "2026-10-04",
            "total_amount": 100,
        },
    )

    assert [row["date"] for row in completed] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert [row["rate"] for row in completed] == [33.34, 33.33, 33.33]
    assert sum(round(row["rate"] * 100) for row in completed) == 10000


def test_completion_preserves_existing_nights_and_drops_out_of_stay_rows():
    persisted = [
        {"id": "outside", "date": "2026-09-30", "rate": 999},
        {"id": "kept", "date": "2026-10-01", "rate": 40},
        {"id": "duplicate", "date": "2026-10-01", "rate": 4000},
    ]

    completed = reservation_detail._complete_daily_rates_for_stay(
        persisted,
        {"check_in": "2026-10-01", "check_out": "2026-10-03", "total_amount": 100},
    )

    assert completed[0] == persisted[1]
    assert completed[1]["date"] == "2026-10-02"
    assert completed[1]["rate"] == 60
