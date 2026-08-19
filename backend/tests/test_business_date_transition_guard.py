from __future__ import annotations

import pytest

from core.business_date_transition_guard import enforce_business_date_transition


class TransitionError(Exception):
    pass


class _TenantSettings:
    def __init__(self, doc):
        self.doc = doc
        self.calls = []

    async def find_one(self, query, projection, session=None):
        self.calls.append((query, projection, session))
        return self.doc


class _DB:
    def __init__(self, settings_doc):
        self.tenant_settings = _TenantSettings(settings_doc)


@pytest.mark.asyncio
async def test_checkin_blocks_when_business_date_is_before_arrival():
    db = _DB({"business_date": "2026-08-14"})

    with pytest.raises(TransitionError, match=r"Cannot check in.*business_date=2026-08-14.*check_in=2026-08-17"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-1",
            booking={"check_in": "2026-08-17T14:00:00+00:00"},
            operation="check_in",
            error_cls=TransitionError,
        )


@pytest.mark.asyncio
async def test_checkin_allows_when_business_date_reaches_arrival():
    db = _DB({"business_date": "2026-08-17"})

    business_date, scheduled_date = await enforce_business_date_transition(
        db,
        tenant_id="tenant-1",
        booking={"check_in": "2026-08-17"},
        operation="check_in",
        error_cls=TransitionError,
    )

    assert business_date.isoformat() == "2026-08-17"
    assert scheduled_date.isoformat() == "2026-08-17"


@pytest.mark.asyncio
async def test_checkout_blocks_when_business_date_is_before_departure_even_for_force_callers():
    db = _DB({"business_date": "2026-08-17"})

    with pytest.raises(TransitionError, match=r"Cannot check out.*business_date=2026-08-17.*check_out=2026-08-18"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-1",
            booking={"check_out": "2026-08-18T11:00:00Z"},
            operation="check_out",
            error_cls=TransitionError,
        )


@pytest.mark.asyncio
async def test_checkout_allows_when_business_date_reaches_departure():
    db = _DB({"business_date": "2026-08-18"})

    business_date, scheduled_date = await enforce_business_date_transition(
        db,
        tenant_id="tenant-1",
        booking={"check_out": "2026-08-18"},
        operation="check_out",
        error_cls=TransitionError,
    )

    assert business_date.isoformat() == "2026-08-18"
    assert scheduled_date.isoformat() == "2026-08-18"


@pytest.mark.asyncio
@pytest.mark.parametrize("settings_doc", [None, {}, {"business_date": ""}])
async def test_missing_business_date_fails_closed(settings_doc):
    db = _DB(settings_doc)

    with pytest.raises(TransitionError, match="business_date.*missing"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-1",
            booking={"check_in": "2026-08-17"},
            operation="check_in",
            error_cls=TransitionError,
        )


@pytest.mark.asyncio
async def test_malformed_business_date_fails_closed():
    db = _DB({"business_date": "not-a-date"})

    with pytest.raises(TransitionError, match="business_date.*invalid"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-1",
            booking={"check_in": "2026-08-17"},
            operation="check_in",
            error_cls=TransitionError,
        )


@pytest.mark.asyncio
async def test_missing_booking_transition_date_fails_closed():
    db = _DB({"business_date": "2026-08-17"})

    with pytest.raises(TransitionError, match="Booking check-in.*missing"):
        await enforce_business_date_transition(
            db,
            tenant_id="tenant-1",
            booking={},
            operation="check_in",
            error_cls=TransitionError,
        )
