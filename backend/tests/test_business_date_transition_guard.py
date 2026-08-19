import pytest

from core.business_date_guard import enforce_business_date_not_before


class GuardError(Exception):
    pass


def _guard(business_date, boundary_date, *, operation, boundary_field):
    return enforce_business_date_not_before(
        business_date=business_date,
        boundary_date=boundary_date,
        operation=operation,
        boundary_field=boundary_field,
        error_type=GuardError,
    )


def test_checkin_blocks_before_arrival_business_date():
    with pytest.raises(GuardError, match=r"business_date 2026-08-14 is before check_in 2026-08-17"):
        _guard(
            "2026-08-14",
            "2026-08-17",
            operation="check in booking",
            boundary_field="check_in",
        )


def test_checkin_allows_on_arrival_business_date():
    _guard(
        "2026-08-17",
        "2026-08-17",
        operation="check in booking",
        boundary_field="check_in",
    )


def test_checkout_blocks_before_departure_business_date():
    with pytest.raises(GuardError, match=r"business_date 2026-08-17 is before check_out 2026-08-18"):
        _guard(
            "2026-08-17",
            "2026-08-18",
            operation="check out booking",
            boundary_field="check_out",
        )


def test_checkout_allows_on_departure_business_date():
    _guard(
        "2026-08-18",
        "2026-08-18",
        operation="check out booking",
        boundary_field="check_out",
    )


@pytest.mark.parametrize(
    ("business_date", "boundary_date", "expected"),
    [
        (None, "2026-08-17", "business_date is missing"),
        ("2026-08-17", None, "check_in is missing"),
        ("not-a-date", "2026-08-17", "business_date has invalid date value"),
    ],
)
def test_guard_fails_closed_on_missing_or_invalid_dates(business_date, boundary_date, expected):
    with pytest.raises(GuardError, match=expected):
        _guard(
            business_date,
            boundary_date,
            operation="check in booking",
            boundary_field="check_in",
        )
