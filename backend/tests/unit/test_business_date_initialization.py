from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from core.business_date_service import ensure_business_date_initialized
from domains.pms.night_audit.schemas import RunNightAuditRequest


def _db(*, settings_reads, latest_run=None, bookings=None):
    tenant_settings = SimpleNamespace(
        find_one=AsyncMock(side_effect=settings_reads),
        update_one=AsyncMock(),
    )
    night_audit_runs = SimpleNamespace(find_one=AsyncMock(return_value=latest_run))
    booking_cursor = MagicMock()
    booking_cursor.to_list = AsyncMock(return_value=bookings or [])
    booking_collection = SimpleNamespace(find=MagicMock(return_value=booking_cursor))
    return SimpleNamespace(
        tenant_settings=tenant_settings,
        night_audit_runs=night_audit_runs,
        bookings=booking_collection,
    )


@pytest.mark.asyncio
async def test_existing_business_date_is_authoritative_and_not_reinitialized():
    database = _db(settings_reads=[{
        "tenant_id": "t1",
        "business_date": "2026-08-22",
        "business_date_update_source": "night_audit",
        "business_date_audit_run_id": "run-1",
    }])

    result = await ensure_business_date_initialized(database, "t1", today=date(2026, 8, 24))

    assert result["business_date"] == "2026-08-22"
    assert result["audit_run_id"] == "run-1"
    database.tenant_settings.update_one.assert_not_awaited()
    database.night_audit_runs.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_date_without_audit_metadata_is_labeled_legacy():
    database = _db(settings_reads=[{
        "tenant_id": "t1",
        "business_date": "2026-08-22",
    }])

    result = await ensure_business_date_initialized(database, "t1", today=date(2026, 8, 24))

    assert result["update_source"] == "legacy_record"
    assert result["audit_run_id"] is None


@pytest.mark.asyncio
async def test_missing_business_date_starts_at_earliest_unresolved_arrival():
    stored = {
        "tenant_id": "t1",
        "business_date": "2026-08-22",
        "business_date_initialization_reason": "earliest_unresolved_arrival",
        "business_date_update_source": "initialization",
    }
    database = _db(
        settings_reads=[None, stored],
        bookings=[
            {"check_in": "2026-08-26T14:00:00+03:00"},
            {"check_in": "2026-08-22T14:00:00+03:00"},
            {"check_in": "invalid"},
        ],
    )

    result = await ensure_business_date_initialized(database, "t1", today=date(2026, 8, 24))

    assert result["business_date"] == "2026-08-22"
    assert result["initialization_reason"] == "earliest_unresolved_arrival"
    update = database.tenant_settings.update_one.await_args
    assert update.kwargs["upsert"] is True
    assert isinstance(update.args[1], list)


@pytest.mark.asyncio
async def test_successful_audit_history_wins_over_older_imported_booking():
    stored = {
        "tenant_id": "t1",
        "business_date": "2026-08-24",
        "business_date_initialization_reason": "night_audit_history",
        "business_date_update_source": "initialization",
    }
    database = _db(
        settings_reads=[{}, stored],
        latest_run={"business_date": "2026-08-23"},
        bookings=[{"check_in": "2026-08-20"}],
    )

    result = await ensure_business_date_initialized(database, "t1", today=date(2026, 8, 24))

    assert result["business_date"] == "2026-08-24"
    assert result["initialization_reason"] == "night_audit_history"
    database.bookings.find.assert_not_called()


@pytest.mark.asyncio
async def test_clean_tenant_starts_on_first_operational_use_day():
    stored = {
        "tenant_id": "t1",
        "business_date": "2026-08-24",
        "business_date_initialization_reason": "first_operational_use",
        "business_date_update_source": "initialization",
    }
    database = _db(settings_reads=[None, stored])

    result = await ensure_business_date_initialized(database, "t1", today=date(2026, 8, 24))

    assert result["business_date"] == "2026-08-24"
    assert result["initialization_reason"] == "first_operational_use"


@pytest.mark.asyncio
async def test_run_endpoint_rejects_stale_client_business_date():
    from domains.pms.night_audit.router import run_night_audit

    user = SimpleNamespace(
        id="user-1",
        tenant_id="tenant-1",
        role="admin",
        email="manager@example.com",
    )
    request = RunNightAuditRequest(business_date="2026-08-24")
    start_mock = AsyncMock()

    with (
        patch(
            "core.business_date_service.ensure_business_date_initialized",
            new=AsyncMock(return_value={"business_date": "2026-08-22"}),
        ),
        patch("core.night_audit_hardened.start_night_audit", new=start_mock),
    ):
        with pytest.raises(HTTPException) as exc:
            await run_night_audit(request, current_user=user, _perm=None)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "BUSINESS_DATE_MISMATCH"
    assert exc.value.detail["current_business_date"] == "2026-08-22"
    start_mock.assert_not_awaited()
