import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-tests")

import pytest
from fastapi import HTTPException

from routers.reports_pkg.dashboard_lists import (
    _booking_occupied_on,
    _date_part,
    _guest_identity,
    _guest_link_active_on,
    _nightly_booking_rate,
    _normalized_room_status,
    _payment_is_collection,
    _payment_is_effective,
    _payment_method,
    _period_performance,
)
from routers.reports_pkg.flash_email import _report_date


def test_occupied_night_uses_half_open_stay_interval():
    booking = {
        "status": "checked_out",
        "check_in": "2026-09-21T14:00:00+03:00",
        "check_out": "2026-09-23T11:00:00+03:00",
    }

    assert _booking_occupied_on(booking, "2026-09-21") is True
    assert _booking_occupied_on(booking, "2026-09-22") is True
    assert _booking_occupied_on(booking, "2026-09-23") is False


def test_confirmed_booking_is_arrival_not_in_house():
    booking = {
        "status": "confirmed",
        "check_in": "2026-09-22",
        "check_out": "2026-09-24",
    }

    assert _booking_occupied_on(booking, "2026-09-22") is False


def test_legacy_in_house_status_is_included_in_daily_lists():
    booking = {
        "status": "in_house",
        "check_in": "2026-09-22",
        "check_out": "2026-09-24",
    }

    assert _booking_occupied_on(booking, "2026-09-23") is True


def test_actual_checkout_prevents_false_historical_occupancy():
    booking = {
        "status": "checked_out",
        "check_in": "2026-09-20",
        "check_out": "2026-09-25",
        "checked_in_at": "2026-09-20T15:00:00Z",
        "checked_out_at": "2026-09-22T09:00:00Z",
    }

    assert _booking_occupied_on(booking, "2026-09-21") is True
    assert _booking_occupied_on(booking, "2026-09-22") is False


def test_guest_identity_supports_canonical_and_legacy_fields():
    assert _guest_identity({"id_number": "11111111111"}, {}) == ("11111111111", None)
    assert _guest_identity({"id_type": "passport", "id_number": "P1234"}, {}) == ("P1234", "P1234")
    assert _guest_identity({}, {"tc_identity_number": "22222222222", "passport_number": "P9"}) == (
        "22222222222",
        "P9",
    )


def test_payment_normalization_excludes_voided_and_failed_rows():
    assert _payment_method({"payment_method": "credit_card", "method": "cash"}) == "credit_card"
    assert _payment_is_effective({"status": "paid", "voided": False}) is True
    assert _payment_is_effective({"status": "failed"}) is False
    assert _payment_is_effective({"status": "paid", "voided": True}) is False


def test_cashier_collection_excludes_non_cash_folio_settlements():
    assert _payment_is_collection({"status": "paid", "method": "cash"}) is True
    assert _payment_is_collection({"status": "paid", "method": "credit_card"}) is True
    assert _payment_is_collection({"status": "paid", "method": "discount"}) is False
    assert _payment_is_collection({"status": "paid", "method": "city_ledger"}) is False


def test_nightly_rate_prefers_date_specific_reservation_rate():
    booking = {
        "check_in": "2026-09-22",
        "check_out": "2026-09-24",
        "base_rate": 100,
        "total_amount": 200,
    }
    assert _nightly_booking_rate(booking, "2026-09-23", {"rate": 175}) == 175
    assert _nightly_booking_rate(booking, "2026-09-23") == 100


def test_date_part_accepts_date_only_and_datetime_values():
    assert _date_part("2026-09-23") == "2026-09-23"
    assert _date_part("2026-09-23T14:15:00+03:00") == "2026-09-23"


def test_additional_guest_link_respects_its_checkout_date():
    link = {"checkout_date": "2026-09-23T09:00:00Z"}
    assert _guest_link_active_on(link, "2026-09-22") is True
    assert _guest_link_active_on(link, "2026-09-23") is False


def test_period_performance_uses_accrued_revenue_until_all_room_nights_are_posted():
    metrics = [
        {"date": "2026-09-22", "occupied_rooms": 2, "total_rooms": 10, "revenue": 2000},
        {"date": "2026-09-23", "occupied_rooms": 1, "total_rooms": 10, "revenue": 1500},
    ]

    result = _period_performance(metrics, {"2026-09-22": 2000})

    assert result["revenue_source"] == "accrued"
    assert result["room_revenue"] == 3500
    assert result["posting_gap_days"] == ["2026-09-23"]
    assert result["adr"] == 1166.67
    assert result["revpar"] == 175


def test_period_performance_uses_posted_revenue_when_period_is_complete():
    metrics = [{"date": "2026-09-23", "occupied_rooms": 2, "total_rooms": 10, "revenue": 2000}]

    result = _period_performance(metrics, {"2026-09-23": 2400})

    assert result["revenue_source"] == "posted"
    assert result["room_revenue"] == 2400
    assert result["adr"] == 1200
    assert result["revpar"] == 240


def test_room_status_normalization_keeps_report_buckets_consistent():
    assert _normalized_room_status("checked_in") == "occupied"
    assert _normalized_room_status("Kirli") == "dirty"
    assert _normalized_room_status("bakım") == "maintenance"
    assert _normalized_room_status("sale-closed") == "out_of_order"
    assert _normalized_room_status("clean") == "available"
    assert _normalized_room_status("unexpected_legacy_value") == "out_of_order"


def test_report_date_rejects_invalid_values_instead_of_returning_server_error():
    assert _report_date("2026-09-24").isoformat() == "2026-09-24"
    with pytest.raises(HTTPException) as exc_info:
        _report_date("not-a-date")
    assert exc_info.value.status_code == 422
