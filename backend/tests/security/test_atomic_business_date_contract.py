"""Security contract for PMS atomic check-in/check-out business-date guards.

The functional guard is already present on main (PR #352).  These tests pin the
fail-closed contract at the atomic boundary so future refactors cannot silently
re-introduce wall-clock-based early check-in / early checkout behaviour.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.business_date_transition_guard import enforce_business_date_transition


class _TransitionError(Exception):
    pass


def _db_with_business_date(value):
    return SimpleNamespace(
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value={"business_date": value} if value is not None else None),
        )
    )


@pytest.mark.asyncio
async def test_business_date_14_blocks_checkin_for_17_august():
    db = _db_with_business_date("2026-08-14")

    with pytest.raises(
        _TransitionError,
        match=r"Cannot check in.*business_date=2026-08-14.*check_in=2026-08-17",
    ):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={"check_in": "2026-08-17T14:00:00+03:00"},
            operation="check_in",
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
async def test_business_date_17_allows_checkin_for_17_august():
    db = _db_with_business_date("2026-08-17")

    business_date, scheduled = await enforce_business_date_transition(
        db,
        tenant_id="tenant-a",
        booking={"check_in": "2026-08-17"},
        operation="check_in",
        error_cls=_TransitionError,
    )

    assert business_date == date(2026, 8, 17)
    assert scheduled == date(2026, 8, 17)


@pytest.mark.asyncio
async def test_business_date_17_blocks_checkout_for_18_august():
    db = _db_with_business_date("2026-08-17")

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
async def test_business_date_18_allows_checkout_for_18_august():
    db = _db_with_business_date("2026-08-18")

    business_date, scheduled = await enforce_business_date_transition(
        db,
        tenant_id="tenant-a",
        booking={"check_out": "2026-08-18"},
        operation="check_out",
        error_cls=_TransitionError,
    )

    assert business_date == date(2026, 8, 18)
    assert scheduled == date(2026, 8, 18)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", "not-a-date"])
async def test_missing_or_invalid_business_date_fails_closed(value):
    db = _db_with_business_date(value)

    with pytest.raises(_TransitionError):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={"check_in": "2026-08-17"},
            operation="check_in",
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "field"),
    [("check_in", "check_in"), ("check_out", "check_out")],
)
async def test_missing_booking_transition_date_fails_closed(operation, field):
    db = _db_with_business_date("2026-08-17")

    with pytest.raises(_TransitionError, match="missing"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-a",
            booking={field: None},
            operation=operation,
            error_cls=_TransitionError,
        )


@pytest.mark.asyncio
async def test_guard_preserves_transaction_session_on_business_date_read():
    db = _db_with_business_date("2026-08-17")
    session = object()

    await enforce_business_date_transition(
        db,
        tenant_id="tenant-a",
        booking={"check_in": "2026-08-17"},
        operation="check_in",
        error_cls=_TransitionError,
        session=session,
    )

    assert db.tenant_settings.find_one.await_args.kwargs["session"] is session
