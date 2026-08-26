from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from common.context import OperationContext
from common.result import ServiceResult
from core.business_date_transition_guard import enforce_business_date_transition
from core.night_audit_hardened import (
    _normalize_booking_date,
    _partition_due_bookings,
    _partition_stays_for_business_date,
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
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value={"business_date": "2026-08-17"}),
        ),
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
            "check_in": "2026-08-17",
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
            "check_in": "2026-08-17",
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


@pytest.mark.asyncio
async def test_standard_frontdesk_checkin_blocks_future_arrival_for_business_date():
    service = _service_with_db(
        {
            "id": "booking-future",
            "tenant_id": "tenant-a",
            "status": "confirmed",
            "room_id": "room-a",
            "guest_id": "guest-a",
            "check_in": "2026-08-26",
        },
        {
            "id": "room-a",
            "tenant_id": "tenant-a",
            "status": "available",
            "room_number": "101",
        },
    )
    service._db.tenant_settings.find_one.return_value = {"business_date": "2026-08-23"}

    result = await FrontdeskService.checkin.__wrapped__(
        service,
        _context(),
        "booking-future",
    )

    assert result.ok is False
    assert result.code == "BUSINESS_DATE_MISMATCH"
    assert "business_date=2026-08-23" in result.error
    service._db.bookings.update_one.assert_not_awaited()
    service._db.rooms.update_one.assert_not_awaited()
    service._db.folios.insert_one.assert_not_awaited()


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


def test_room_charge_stays_are_scoped_to_the_business_date():
    active, future, ended, invalid = _partition_stays_for_business_date(
        [
            {"id": "active", "check_in": "2026-05-01", "check_out": "2026-05-08"},
            {"id": "starts-today", "check_in": "2026-05-05T15:00:00+03:00", "check_out": "2026-05-06"},
            {"id": "future", "check_in": "2026-10-13", "check_out": "2026-10-14"},
            {"id": "ended", "check_in": "2026-05-01", "check_out": "2026-05-05"},
            {"id": "bad-order", "check_in": "2026-05-05", "check_out": "2026-05-04"},
            {"id": "bad-date", "check_in": "legacy", "check_out": "2026-05-06"},
        ],
        "2026-05-05",
    )

    assert {booking["id"] for booking in active} == {"active", "starts-today"}
    assert [booking["id"] for booking in future] == ["future"]
    assert [booking["id"] for booking in ended] == ["ended"]
    assert {booking["id"] for booking in invalid} == {"bad-order", "bad-date"}


class _TransitionError(Exception):
    pass


def _business_date_guard_db(settings_doc):
    return SimpleNamespace(
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value=settings_doc),
        )
    )


@pytest.mark.asyncio
async def test_atomic_business_date_guard_blocks_future_checkin():
    db = _business_date_guard_db({"business_date": "2026-08-14"})

    with pytest.raises(
        _TransitionError,
        match=r"Cannot check in.*business_date=2026-08-14.*check_in=2026-08-17",
    ):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={"check_in": "2026-08-17T14:00:00+00:00"},
            operation="check_in",
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
async def test_atomic_business_date_guard_allows_checkin_on_arrival_date():
    db = _business_date_guard_db({"business_date": "2026-08-17"})

    business_date, scheduled_date = await enforce_business_date_transition(
        db,
        tenant_id="tenant-a",
        booking={"check_in": "2026-08-17"},
        operation="check_in",
        error_cls=_TransitionError,
    )

    assert business_date == date(2026, 8, 17)
    assert scheduled_date == date(2026, 8, 17)


@pytest.mark.asyncio
async def test_atomic_business_date_guard_blocks_future_checkout_even_if_force_is_used_upstream():
    db = _business_date_guard_db({"business_date": "2026-08-17"})

    with pytest.raises(
        _TransitionError,
        match=r"Cannot check out.*business_date=2026-08-17.*check_out=2026-08-18",
    ):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={"check_out": "2026-08-18T11:00:00Z"},
            operation="check_out",
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
async def test_atomic_business_date_guard_allows_checkout_on_departure_date():
    db = _business_date_guard_db({"business_date": "2026-08-18"})

    business_date, scheduled_date = await enforce_business_date_transition(
        db,
        tenant_id="tenant-a",
        booking={"check_out": "2026-08-18"},
        operation="check_out",
        error_cls=_TransitionError,
    )

    assert business_date == date(2026, 8, 18)
    assert scheduled_date == date(2026, 8, 18)


@pytest.mark.asyncio
@pytest.mark.parametrize("settings_doc", [None, {}, {"business_date": ""}])
async def test_atomic_business_date_guard_fails_closed_without_business_date(settings_doc):
    db = _business_date_guard_db(settings_doc)

    with pytest.raises(_TransitionError, match="business_date.*missing"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={"check_in": "2026-08-17"},
            operation="check_in",
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
async def test_atomic_checkin_path_blocks_future_business_date_before_room_or_mutation(monkeypatch):
    import core.atomic_checkin_checkout as atomic

    fake_db = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": "confirmed",
                    "check_in": "2026-08-17",
                    "room_id": "room-a",
                }
            )
        ),
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value={"business_date": "2026-08-14"})
        ),
    )
    monkeypatch.setattr(atomic, "db", fake_db)
    monkeypatch.setenv("MONGO_DISABLE_TRANSACTIONS", "1")

    with pytest.raises(
        atomic.CheckInError,
        match=r"Cannot check in.*business_date=2026-08-14.*check_in=2026-08-17",
    ):
        await atomic.check_in_booking_atomic(
            "booking-a",
            "tenant-a",
            "operator",
        )


@pytest.mark.asyncio
async def test_atomic_checkout_path_blocks_future_business_date_even_with_force(monkeypatch):
    import core.atomic_checkin_checkout as atomic

    fake_db = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": "checked_in",
                    "check_out": "2026-08-18",
                    "room_id": "room-a",
                }
            )
        ),
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value={"business_date": "2026-08-17"})
        ),
    )
    monkeypatch.setattr(atomic, "db", fake_db)
    monkeypatch.setenv("MONGO_DISABLE_TRANSACTIONS", "1")

    with pytest.raises(
        atomic.CheckOutError,
        match=r"Cannot check out.*business_date=2026-08-17.*check_out=2026-08-18",
    ):
        await atomic.check_out_booking_atomic(
            "booking-a",
            "tenant-a",
            "operator",
            force=True,
        )
