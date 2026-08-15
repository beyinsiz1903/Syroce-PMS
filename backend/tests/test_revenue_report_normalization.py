from datetime import UTC, date, datetime
from decimal import Decimal

from domains.revenue.revenue_report_normalization import (
    calculate_booking_revenue,
    cancellation_lead_bucket,
    normalize_dimension_label,
    parse_booking_datetime,
    safe_amount,
)


def test_parse_booking_datetime_accepts_date_timestamp_and_z_suffix():
    assert parse_booking_datetime("2026-08-14") == datetime(2026, 8, 14, tzinfo=UTC)
    assert parse_booking_datetime("2026-08-14T09:30:00Z") == datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    assert parse_booking_datetime(date(2026, 8, 14)) == datetime(2026, 8, 14, tzinfo=UTC)
    assert parse_booking_datetime(None) is None
    assert parse_booking_datetime("not-a-date") is None


def test_calculate_booking_revenue_handles_incomplete_legacy_rows():
    assert calculate_booking_revenue({}) == Decimal("0")
    assert calculate_booking_revenue({"total_amount": "125.50"}) == Decimal("125.50")
    assert calculate_booking_revenue(
        {
            "check_in": "2026-08-14",
            "check_out": "2026-08-17",
            "rate_per_night": "100",
        }
    ) == Decimal("300")
    assert safe_amount(float("nan")) == Decimal("0")


def test_cancellation_lead_bucket_tracks_unclassifiable_rows():
    assert cancellation_lead_bucket({"check_in": "2026-08-14"}) is None
    assert (
        cancellation_lead_bucket(
            {
                "check_in": "2026-08-14",
                "cancelled_at": "2026-08-10T12:00:00Z",
            }
        )
        == "4_7_days"
    )
    assert (
        cancellation_lead_bucket(
            {
                "check_in": "2026-08-14",
                "cancelled_at": "2026-08-15T12:00:00Z",
            }
        )
        == "same_day"
    )


def test_normalize_dimension_label_handles_legacy_structured_values():
    assert normalize_dimension_label({"name": "HotelRunner"}) == "HotelRunner"
    assert normalize_dimension_label({"code": 42}) == "42"
    assert normalize_dimension_label({"source": {"name": "nested"}}) == "direct"
    assert normalize_dimension_label(["unsafe", "shape"]) == "direct"
