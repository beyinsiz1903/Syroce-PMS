from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from common.context import OperationContext
from common.result import ServiceResult
from core.night_audit_hardened import (
    _normalize_booking_date,
    _partition_due_bookings,
    _split_pending_arrivals,
)
from domains.pms.frontdesk_service import FrontdeskService


def _context(tenant_id: str = "tenant-a") -> OperationContext:
    return OperationContext(tenant_id=tenant_id, actor_id="operator")


def _service_with_db(booking: dict, room: dict | None = None):
    service = object.__new__(FrontdeskService)
    service._db = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(return_value=booking),
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        ),
        rooms=SimpleNamespace(
            find_one=AsyncMock(return_value=room),
            update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a"}),
            insert_one=AsyncMock(),
        ),
        guests=SimpleNamespace(update_one=AsyncMock()),
    )
    return service


@pytest.mark.asyncio
async def test_confirmed_booking_without_room_returns_controlled_failure_without_mutation():
    service = _service_with_db(
        {
            "id": "booking-a",
            "tenant_id": "tenant-a",
            "status": "confirmed",
            "guest_id": "guest-a",
        }
    )

    result = await FrontdeskService.checkin.__wrapped__(
        service,
        _context(),
        "booking-a",
    )

    assert result.ok is False
    assert result.code == "ROOM_ASSIGNMENT_REQUIRED"
    service._db.rooms.find_one.assert_not_awaited()
    service._db.bookings.update_one.assert_not_awaited()
    service._db.folios.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkin_rejects_non_eligible_status_before_room_lookup():
    service = _service_with_db(
        {
            "id": "booking-a",
            "tenant_id": "tenant-a",
            "status": "cancelled",
            "room_id": "room-a",
        }
    )

    result = await FrontdeskService.checkin.__wrapped__(
        service,
        _context(),
        "booking-a",
    )

    assert result.ok is False
    assert result.code == "INVALID_BOOKING_STATUS"
    service._db.rooms.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_frontdesk_route_maps_room_assignment_failure_to_http_400(monkeypatch):
    import domains.pms.frontdesk_router as router_module

    checkin = AsyncMock(
        return_value=ServiceResult.fail(
            "Assign a room before check-in",
            "ROOM_ASSIGNMENT_REQUIRED",
        )
    )
    monkeypatch.setattr(router_module.frontdesk_service, "checkin", checkin)
    user = SimpleNamespace(
        id="operator",
        tenant_id="tenant-a",
        email="operator@example.test",
        role="admin",
        property_id=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await router_module.check_in_guest(
            "booking-a",
            current_user=user,
            _perm=None,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Assign a room before check-in"


@pytest.mark.asyncio
async def test_successful_checkin_scopes_room_folio_booking_and_guest_to_tenant():
    service = _service_with_db(
        {
            "id": "booking-a",
            "tenant_id": "tenant-a",
            "status": "confirmed",
            "room_id": "room-a",
            "guest_id": "guest-a",
        },
        {
            "id": "room-a",
            "tenant_id": "tenant-a",
            "status": "available",
            "room_number": "101",
        },
    )

    result = await FrontdeskService.checkin.__wrapped__(
        service,
        _context(),
        "booking-a",
    )

    assert result.ok is True
    assert service._db.rooms.find_one.await_args.args[0] == {
        "id": "room-a",
        "tenant_id": "tenant-a",
    }
    assert service._db.folios.find_one.await_args.args[0]["tenant_id"] == "tenant-a"
    assert service._db.bookings.update_one.await_args.args[0]["tenant_id"] == "tenant-a"
    assert service._db.rooms.update_one.await_args.args[0]["tenant_id"] == "tenant-a"
    assert service._db.guests.update_one.await_args.args[0] == {
        "id": "guest-a",
        "tenant_id": "tenant-a",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-05-05", date(2026, 5, 5)),
        ("2026-05-05T10:30:00+00:00", date(2026, 5, 5)),
        (datetime(2026, 5, 5, 10, 30, tzinfo=UTC), date(2026, 5, 5)),
        ("not-a-date", None),
        (None, None),
    ],
)
def test_booking_dates_are_normalized_without_string_ordering(value, expected):
    assert _normalize_booking_date(value) == expected


def test_stale_timestamp_and_date_only_bookings_share_business_date_boundary():
    due, invalid = _partition_due_bookings(
        [
            {"id": "old", "check_in": "2026-04-02T16:31:20+00:00"},
            {"id": "same-day-date", "check_in": "2026-05-05"},
            {"id": "same-day-time", "check_in": "2026-05-05T23:59:59+03:00"},
            {"id": "future", "check_in": "2026-05-06T00:00:00+03:00"},
            {"id": "invalid", "check_in": "legacy-value"},
        ],
        "check_in",
        "2026-05-05",
    )

    assert {booking["id"] for booking in due} == {
        "old",
        "same-day-date",
        "same-day-time",
    }
    assert [booking["id"] for booking in invalid] == ["invalid"]


def test_pending_arrivals_without_room_are_separate_data_integrity_blockers():
    with_room, without_room = _split_pending_arrivals(
        [
            {"id": "assigned", "room_id": "room-a"},
            {"id": "missing"},
            {"id": "empty", "room_id": ""},
        ]
    )

    assert [booking["id"] for booking in with_room] == ["assigned"]
    assert {booking["id"] for booking in without_room} == {"missing", "empty"}
