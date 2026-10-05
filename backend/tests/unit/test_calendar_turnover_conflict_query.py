from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers import pms_reservations


@pytest.mark.asyncio
async def test_double_booking_check_excludes_a_same_day_departure(monkeypatch):
    """The calendar conflict badge must not block a room turnover day."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    bookings = SimpleNamespace(find=MagicMock(return_value=cursor))
    monkeypatch.setattr(pms_reservations, "db", SimpleNamespace(bookings=bookings))

    result = await pms_reservations.check_double_booking_conflicts(
        date="2026-09-20",
        current_user=SimpleNamespace(tenant_id="tenant-1"),
    )

    assert result["status"] == "no_conflicts"
    query = bookings.find.call_args.args[0]
    assert query["check_in"] == {"$lt": "2026-09-21"}
    assert query["check_out"] == {"$gt": "2026-09-20T23:59:59.999999"}
