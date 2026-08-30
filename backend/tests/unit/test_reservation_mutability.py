from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.reservation_mutability import ensure_reservation_mutable, reservation_is_historical


def test_terminal_reservations_are_read_only_immediately():
    for status in ("checked_out", "cancelled", "no_show"):
        assert reservation_is_historical(
            {"status": status, "check_out": "2026-08-30T12:00:00"},
            "2026-08-30",
        )


def test_legacy_active_reservation_is_read_only_after_departure_day():
    assert reservation_is_historical(
        {"status": "confirmed", "check_out": "2026-08-29T12:00:00"},
        "2026-08-30",
    )
    assert reservation_is_historical(
        {"status": "confirmed", "check_out": datetime(2026, 8, 29, 12, tzinfo=UTC)},
        date(2026, 8, 30),
    )


def test_current_and_future_active_reservations_remain_editable():
    assert not reservation_is_historical(
        {"status": "checked_in", "check_out": "2026-08-30T12:00:00"},
        "2026-08-30",
    )
    assert not reservation_is_historical(
        {"status": "confirmed", "check_out": "2026-08-31T12:00:00"},
        "2026-08-30",
    )


def test_overdue_in_house_reservation_stays_operable_until_checkout():
    assert not reservation_is_historical(
        {"status": "checked_in", "check_out": "2026-08-29T12:00:00"},
        "2026-08-30",
    )


@pytest.mark.asyncio
async def test_terminal_reservation_rejects_without_business_date_lookup():
    with pytest.raises(HTTPException) as exc_info:
        await ensure_reservation_mutable(
            SimpleNamespace(),
            "tenant-a",
            {"status": "checked_out"},
        )

    assert exc_info.value.status_code == 409
