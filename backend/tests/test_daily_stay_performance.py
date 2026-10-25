from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.pms_core.daily_stay_performance import channel_group, daily_stay_performance
from routers.reports_pkg import flash_email, standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
DAY = date(2026, 10, 24)
ROOMS = [{"id": "r", "room_number": "101"}, {"id": "virtual", "is_virtual": True}, {"id": "old", "is_active": False}]


def stay(**extra):
    return {"id": "b", "room_id": "r", "status": "checked_in", "check_in": "2026-10-22", "check_out": "2026-10-26", **extra}


@pytest.mark.parametrize("booking,expected", [
    ({"source_channel": "direct"}, "direct"), ({"source_channel": "phone"}, "direct"),
    ({"ota_channel": "booking_com", "source_channel": "direct"}, "ota"),
    ({"source_channel": "Booking.com"}, "ota"), ({"booking_source": "expedia"}, "ota"),
    ({"channel": "walk_in"}, "direct"), ({"channel": "web sitesi"}, "direct"),
    ({"source_channel": "agency", "channel": "direct"}, "agency"),
    ({"source_channel": "exely", "channel": "direct"}, "unknown"),
    ({"source_channel": "hotelrunner"}, "unknown"), ({}, "unknown"),
    ({"source_channel": "manual"}, "unknown"), ({"source_channel": "a made-up OTA"}, "unknown"),
])
def test_classification_never_infers_direct_from_missing_provider_data(booking, expected):
    assert channel_group(booking) == expected


def test_same_actual_night_cohort_and_reservation_denominator():
    bookings = [stay(source_channel="direct"), stay(id="ota", ota_channel="airbnb", check_in="2026-10-23"),
                stay(id="agency", source_channel="agency"), stay(id="unknown"), stay(source_channel="direct"),
                stay(id="future", status="confirmed"), stay(id="cancel", status="cancelled"),
                stay(id="noshow", status="no_show"), stay(id="departure", check_out="2026-10-24"),
                stay(id="late", checked_in_business_date="2026-10-25"),
                stay(id="early", checked_out_business_date="2026-10-24"),
                stay(id="virtual", room_id="virtual"), stay(id="old", room_id="old"),
                stay(id="dangling", room_id="missing", room_number="101")]
    result = daily_stay_performance(bookings, ROOMS, DAY)
    assert result["reservation_count"] == 4
    assert result["booked_stay_nights"] == 15
    assert result["average_stay_nights"] == 3.75
    assert result["channel_counts"] == {"ota": 1, "direct": 1, "agency": 1, "unknown": 1}
    assert all(value == 25 for value in result["channel_share_pct"].values())
    assert result["channel_classification_complete"] is False


def test_empty_cohort_is_unavailable_not_successful_zero():
    data = daily_stay_performance([], ROOMS, DAY)
    assert data["reservation_count"] == 0
    assert data["average_stay_nights"] is None
    assert all(value is None for value in data["channel_share_pct"].values())


def test_legacy_number_and_bson_dates_remain_supported():
    data = daily_stay_performance([stay(room_id=None, room_number="101", check_in=datetime(2026, 10, 22, tzinfo=UTC), source_channel="direct")], ROOMS, DAY)
    assert data["reservation_count"] == 1 and data["average_stay_nights"] == 4
    assert data["channel_share_pct"]["ota"] == 0


async def test_live_loader_is_tenant_scoped_includes_stayovers_and_business_date_not_wall_clock(ledger_db, monkeypatch):
    monkeypatch.setattr(flash_email, "db", ledger_db)
    monkeypatch.setattr(flash_email, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": DAY.isoformat()}))
    monkeypatch.setattr(standard_reports, "_posted_revenue_rows", AsyncMock(return_value=[]))
    await ledger_db.rooms.insert_many([{"tenant_id": "A", **room} for room in ROOMS])
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", **stay(source_channel="direct")},
        {"tenant_id": "A", **stay(id="ota", ota_channel="booking_com", check_in=datetime(2026, 10, 23, tzinfo=UTC))},
        {"tenant_id": "A", **stay(id="virtual", room_id="virtual")},
        {"tenant_id": "B", **stay(id="other-tenant", ota_channel="expedia")},
    ])
    result = await flash_email.get_daily_flash_report.__wrapped__(current_user=SimpleNamespace(tenant_id="A"))
    assert result["date"] == "2026-10-24"
    assert result["performance"]["reservation_count"] == 2
    assert result["performance"]["average_stay_nights"] == 3.5
    assert result["performance"]["channel_share_pct"] == {"ota": 50, "direct": 50, "agency": 0, "unknown": 0}
