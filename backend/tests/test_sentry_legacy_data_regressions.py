import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from domains.guest.experience_router import crm_guest
from domains.revenue.pricing_router import revenue_mobile
from domains.revenue.rms_router import security_mobile
from modules.platform_scaling import revenue_ml


def _cursor(rows):
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=rows)
    return cursor


@pytest.mark.asyncio
async def test_connection_status_normalizes_string_and_naive_datetimes(monkeypatch):
    monkeypatch.setattr(
        security_mobile,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-a")),
    )
    monkeypatch.setattr(
        security_mobile.db,
        "pos_transactions",
        SimpleNamespace(find_one=AsyncMock(return_value={"created_at": "2026-08-14T22:30:00Z"})),
    )
    monkeypatch.setattr(
        security_mobile.db,
        "channel_manager_syncs",
        SimpleNamespace(find_one=AsyncMock(return_value={"sync_timestamp": "2026-08-14T22:30:00"})),
    )

    result = await security_mobile.get_connection_status_mobile(credentials=object())

    assert result["connections"]["pos"]["last_activity"].endswith("+00:00")
    assert result["connections"]["channel_manager"]["last_sync"].endswith("+00:00")
    assert isinstance(result["connections"]["pos"]["minutes_since_activity"], int)


@pytest.mark.asyncio
async def test_portfolio_conversion_accepts_structured_source(monkeypatch):
    bookings = MagicMock()
    bookings.find.return_value = _cursor(
        [
            {"source": {"name": "HotelRunner"}, "status": "checked_out"},
            {"source": {"name": "HotelRunner"}, "status": "cancelled"},
            {"source": {"unexpected": {"nested": True}}, "status": "confirmed"},
        ]
    )
    monkeypatch.setattr(revenue_ml.db, "bookings", bookings)

    result = await revenue_ml.BookingProbabilityModel().get_portfolio_conversion_rates("tenant-a")

    by_source = {row["source"]: row for row in result["by_source"]}
    assert by_source["HotelRunner"]["total_bookings"] == 2
    assert by_source["direct"]["total_bookings"] == 1


@pytest.mark.asyncio
async def test_cancellation_report_accepts_mixed_timezone_filters(monkeypatch):
    monkeypatch.setattr(
        revenue_mobile,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-a")),
    )
    bookings = MagicMock()
    bookings.find.return_value = _cursor([])
    monkeypatch.setattr(revenue_mobile.db, "bookings", bookings)

    result = await revenue_mobile.get_cancellation_report_mobile(
        start_date="2026-08-01",
        end_date="2026-08-15T00:00:00+00:00",
        credentials=object(),
    )

    assert result["summary"]["total_bookings"] == 0


@pytest.mark.asyncio
async def test_guest_360_handles_legacy_dates_source_and_profile_race(monkeypatch):
    monkeypatch.setattr("security.encrypted_lookup.decrypt_guest_doc", lambda doc: doc)
    monkeypatch.setattr(
        crm_guest.db,
        "guests",
        SimpleNamespace(find_one=AsyncMock(return_value={"id": "guest-a", "name": "Test Guest"})),
    )
    bookings = MagicMock()
    bookings.find.return_value = _cursor(
        [
            {
                "status": "checked_out",
                "check_in": "2026-08-10",
                "check_out": "2026-08-12T00:00:00+00:00",
                "total_amount": "200.00",
                "ota_channel": {"name": "Exely"},
            },
            {"check_in": "invalid", "check_out": None},
        ]
    )
    monkeypatch.setattr(crm_guest.db, "bookings", bookings)
    monkeypatch.setattr(
        crm_guest.db,
        "guest_preferences",
        SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(
        crm_guest.db,
        "guest_behavior",
        SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    guest_profiles = SimpleNamespace(
        find_one=AsyncMock(side_effect=[None, {"id": "profile-a", "guest_id": "guest-a"}]),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(crm_guest.db, "guest_profiles", guest_profiles)
    upsells = MagicMock()
    upsells.find.return_value = _cursor([])
    monkeypatch.setattr(crm_guest.db, "upsell_offers", upsells)

    result = await crm_guest.get_guest_360(
        guest_id="guest-a",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )

    assert result["stats"]["total_nights"] == 2
    assert result["stats"]["lifetime_value"] == 200.0
    assert result["stats"]["channel_distribution"] == {"Exely": 1, "direct": 1}
    guest_profiles.update_one.assert_awaited_once()
