from copy import deepcopy

import pytest

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


def exely_booking():
    return {"check_in": "2030-11-10", "check_out": "2030-11-12", "total_amount": 220,
            "booking_source": "exely", "daily_rates": [
                {"date": "2030-11-10", "amount": 90}, {"date": "2030-11-11", "amount": 130}]}


def test_exely_source_nightly_prices_are_not_replaced_with_a_uniform_average():
    booking = exely_booking()
    before = deepcopy(booking)
    rows = reservation_detail._complete_daily_rates_for_stay([], booking)
    assert [row['rate'] for row in rows] == [90, 130]
    assert all(row['generated_reason'] == 'provider_daily_rate' for row in rows)
    assert booking == before


def test_provider_readback_keeps_persisted_closed_night_and_fills_only_missing():
    existing = {'id': 'closed-night', 'date': '2030-11-10', 'rate': 90}
    rows = reservation_detail._complete_daily_rates_for_stay([existing], exely_booking())
    assert rows[0] == existing
    assert rows[1]['rate'] == 130
    assert rows[1]['generated_reason'] == 'provider_daily_rate'


@pytest.mark.parametrize('rates', [
    [{'date': '2030-11-10', 'amount': 90}],
    [{'date': '2030-11-10', 'amount': 90}, {'date': '2030-11-10', 'amount': 130}],
    [{'date': '2030-11-10', 'amount': 90}, {'date': '2030-11-11', 'amount': 999}],
    [{'date': '2030-11-10', 'amount': -10}, {'date': '2030-11-11', 'amount': 230}],
    [{'date': '2030-11-10', 'amount': 'NaN'}, {'date': '2030-11-11', 'amount': 130}],
    [{'date': '2030-11-10', 'amount': True}, {'date': '2030-11-11', 'amount': 219}],
])
def test_invalid_provider_plan_is_never_labelled_verified_source_prices(rates):
    booking = {**exely_booking(), 'daily_rates': rates}
    rows = reservation_detail._complete_daily_rates_for_stay([], booking)
    assert all(row['generated_reason'] == 'missing_daily_rate' for row in rows)


def test_provider_prices_never_override_explicit_pms_prices_or_non_exely_booking():
    existing = [{'date': '2030-11-10', 'rate': 80}]
    rows = reservation_detail._complete_daily_rates_for_stay(existing, exely_booking())
    assert [row['rate'] for row in rows] == [80, 140]
    direct = {**exely_booking(), 'booking_source': 'direct'}
    assert [row['rate'] for row in reservation_detail._complete_daily_rates_for_stay([], direct)] == [110, 110]
