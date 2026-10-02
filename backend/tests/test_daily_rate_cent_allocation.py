"""Daily-rate fallback allocations must preserve the reservation total exactly."""

from routers.reservation_detail import _allocate_daily_rates


def test_allocate_daily_rates_preserves_a_remainder_cent():
    rates = _allocate_daily_rates(
        100.01,
        ["2026-10-01", "2026-10-02", "2026-10-03"],
    )

    assert rates == {
        "2026-10-01": 33.34,
        "2026-10-02": 33.34,
        "2026-10-03": 33.33,
    }
    assert sum(round(rate * 100) for rate in rates.values()) == 10001


def test_allocate_daily_rates_preserves_an_exact_total():
    rates = _allocate_daily_rates(120.00, ["2026-10-01", "2026-10-02", "2026-10-03"])

    assert rates == {
        "2026-10-01": 40.00,
        "2026-10-02": 40.00,
        "2026-10-03": 40.00,
    }
