"""Reservation date edits must preserve operational history."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from modules.reservations.services.update_reservation_service import UpdateReservationService

TENANT = "tenant-date-guard"


def _booking(status="confirmed"):
    return {
        "id": "booking-110",
        "tenant_id": TENANT,
        "status": status,
        "room_id": "room-110",
        "check_in": "2026-08-29T14:00:00+03:00",
        "check_out": "2026-08-30T12:00:00+03:00",
    }


def _service(settings=None):
    repo = SimpleNamespace(get_calendar_settings_for_tenant=AsyncMock(return_value=settings or {"business_date": "2026-08-29", "timezone": "Europe/Istanbul"}))
    return UpdateReservationService(repository=repo), repo


@pytest.mark.asyncio
async def test_checked_in_arrival_date_cannot_be_backdated():
    service, _ = _service()

    with pytest.raises(HTTPException) as exc:
        await service._validate_date_changes(
            tenant_id=TENANT,
            existing_booking=_booking("checked_in"),
            booking_data={
                "check_in": "2026-08-28T00:00:00+00:00",
                "check_out": "2026-08-29T00:00:00+00:00",
            },
        )

    assert exc.value.status_code == 409
    assert "Giris yapilmis" in exc.value.detail


@pytest.mark.asyncio
async def test_confirmed_booking_cannot_move_before_business_date():
    service, _ = _service()

    with pytest.raises(HTTPException) as exc:
        await service._validate_date_changes(
            tenant_id=TENANT,
            existing_booking=_booking("confirmed"),
            booking_data={
                "check_in": "2020-01-01T00:00:00+00:00",
                "check_out": "2020-01-02T00:00:00+00:00",
            },
        )

    assert exc.value.status_code == 400
    assert "Gecmis tarihe" in exc.value.detail


@pytest.mark.asyncio
async def test_checked_in_same_arrival_day_allows_room_only_move():
    service, repo = _service()

    await service._validate_date_changes(
        tenant_id=TENANT,
        existing_booking=_booking("checked_in"),
        booking_data={
            "check_in": "2026-08-29T00:00:00+00:00",
            "check_out": "2026-08-30T00:00:00+00:00",
        },
    )

    repo.get_calendar_settings_for_tenant.assert_not_awaited()


@pytest.mark.asyncio
async def test_checked_out_dates_are_immutable():
    service, _ = _service()

    with pytest.raises(HTTPException) as exc:
        await service._validate_date_changes(
            tenant_id=TENANT,
            existing_booking=_booking("checked_out"),
            booking_data={"check_out": "2026-08-31T12:00:00+03:00"},
        )

    assert exc.value.status_code == 409
    assert "Cikis yapilmis" in exc.value.detail
