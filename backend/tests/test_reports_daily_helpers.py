import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-tests")

import pytest
from fastapi import HTTPException

from core.night_audit_hardened import _money_breakdown
from routers.reports_pkg.dashboard_lists import (
    _booking_occupied_on,
    _complimentary_night_info,
    _currency_breakdown,
    _date_part,
    _guest_identity,
    _guest_link_active_on,
    _merge_currency_breakdowns,
    _nightly_booking_rate,
    _normalized_nationality,
    _normalized_room_status,
    _normalized_room_type,
    _payment_is_collection,
    _payment_is_effective,
    _payment_method,
    _period_performance,
    _received_payment_amount,
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


def test_wall_clock_checkin_does_not_hide_older_pms_business_date():
    booking = {
        "status": "checked_in",
        "check_in": "2026-09-05",
        "check_out": "2026-09-06",
        "checked_in_at": "2026-09-27T10:00:00Z",
    }

    assert _booking_occupied_on(booking, "2026-09-05") is True


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


def test_received_payment_uses_physical_currency_from_converter_note():
    payment = {
        "amount": 121.21,
        "currency": "EUR",
        "notes": "[Döviz Çevirici] 121.21 EUR = 138.10 USD. Kur: 1 EUR = 1.1393 USD",
    }
    assert _received_payment_amount(payment) == {"amount": 138.1, "currency": "USD"}


def test_received_payment_prefers_structured_currency_fields():
    payment = {
        "amount": 121.21,
        "currency": "EUR",
        "received_amount": 138.1,
        "received_currency": "USD",
        "notes": "legacy free text that must not drive accounting",
    }
    assert _received_payment_amount(payment) == {"amount": 138.1, "currency": "USD"}


def test_report_currency_breakdown_never_adds_unlike_currencies():
    rows = [
        {"total": 100, "currency": "eur"},
        {"total": 50, "currency": "EUR"},
        {"total": 80, "currency": "USD"},
    ]
    assert _currency_breakdown(rows, lambda row: row["total"], lambda row: row["currency"]) == {
        "EUR": 150,
        "USD": 80,
    }


def test_report_currency_breakdowns_merge_only_matching_currencies():
    assert _merge_currency_breakdowns({"EUR": 100}, {"USD": 80}, {"EUR": 25}) == {
        "EUR": 125,
        "USD": 80,
    }


def test_night_audit_money_breakdown_keeps_postings_in_original_currency():
    items = [
        {"total": 121.21, "currency": "EUR"},
        {"total": 138.10, "currency": "USD"},
        {"total": 10, "currency": "eur"},
    ]
    assert _money_breakdown(items, "total") == {"EUR": 131.21, "USD": 138.1}


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


def test_comp_night_info_marks_full_stay_and_exposes_reason():
    result = _complimentary_night_info(
        {
            "is_complimentary": True,
            "complimentary_mode": "entire_stay",
            "complimentary_reason": "Yönetim ikramı",
        },
        "2026-09-23",
        {"rate": 5000},
    )

    assert result == {
        "is_complimentary_night": True,
        "complimentary_reason": "Yönetim ikramı",
        "complimentary_mode": "entire_stay",
    }


def test_comp_night_info_marks_only_the_adjusted_closed_date():
    booking = {
        "is_partially_complimentary": True,
        "complimentary_mode": "closed_nights_adjustment",
        "complimentary_reason": "Hizmet telafisi",
    }
    payments = [{"payment_type": "comp_adjustment", "comp_dates": ["2026-09-22"]}]

    assert _complimentary_night_info(booking, "2026-09-22", payments=payments)["is_complimentary_night"] is True
    assert _complimentary_night_info(booking, "2026-09-23", payments=payments)["is_complimentary_night"] is False


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


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("TR", "Türkiye"),
        ("tur", "Türkiye"),
        ("Turkey", "Türkiye"),
        ("sau", "Suudi Arabistan"),
        ("CN", "Çin"),
        ("İSVİÇRE", "İsviçre"),
        (None, "Belirtilmemiş"),
    ],
)
def test_nationality_normalization_merges_country_aliases(raw_value, expected):
    assert _normalized_nationality(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("standard", "Standart"),
        ("standart", "Standart"),
        ("Jakuzili ağaçev", "Jakuzili ağaç ev"),
        ("Jakuzisizağaç ev", "Jakuzisiz ağaç ev"),
        ("Dublex AğaçEv", "Dubleks ağaç ev"),
        ("Suit Oda + Oturma Odası + Jakuzi + Şömine", "Jakuzili ve şömineli süit"),
    ],
)
def test_room_type_normalization_merges_legacy_names(raw_value, expected):
    assert _normalized_room_type(raw_value) == expected


def test_report_date_rejects_invalid_values_instead_of_returning_server_error():
    assert _report_date("2026-09-24").isoformat() == "2026-09-24"
    with pytest.raises(HTTPException) as exc_info:
        _report_date("not-a-date")
    assert exc_info.value.status_code == 422
