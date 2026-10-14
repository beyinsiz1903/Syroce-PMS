"""Concurrent agency sales must not exceed the shared allotment."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import agency_allotment


def _db(rows, used):
    return SimpleNamespace(
        agency_rate_calendar=SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows))),
        bookings=SimpleNamespace(count_documents=AsyncMock(side_effect=used), update_one=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_overrun_reports_first_night_over_cap():
    rows = [{"date": "2026-11-21", "availability": 2}, {"date": "2026-11-20", "availability": 2}]
    db = _db(rows, used=[2, 3])  # sorted: 20th uses 2 (ok), 21st uses 3 (over)
    night = await agency_allotment.marketplace_allotment_overrun(
        db, tenant_id="t", agency_id="a", room_type="Superior", rate_plan_code="BB",
        check_in="2026-11-20", check_out="2026-11-22",
    )
    assert night == "2026-11-21"


@pytest.mark.asyncio
async def test_last_room_of_allotment_is_not_an_overrun():
    db = _db([{"date": "2026-11-20", "availability": 1}], used=[1])
    assert await agency_allotment.marketplace_allotment_overrun(
        db, tenant_id="t", agency_id="a", room_type="Superior", rate_plan_code="BB",
        check_in="2026-11-20", check_out="2026-11-21",
    ) is None


@pytest.mark.asyncio
async def test_unlimited_nights_and_legacy_cap():
    db = _db([{"date": "2026-11-20"}], used=[])
    assert await agency_allotment.marketplace_allotment_overrun(
        db, tenant_id="t", agency_id="a", room_type="Superior", rate_plan_code=None,
        check_in="2026-11-20", check_out="2026-11-21",
    ) is None
    legacy = SimpleNamespace(bookings=SimpleNamespace(count_documents=AsyncMock(return_value=4)))
    assert await agency_allotment.legacy_allotment_overrun(
        legacy, tenant_id="t", agency_id="a", room_ids=["r1"], allotment_count=3, check_in="2026-11-20", check_out="2026-11-21",
    )


@pytest.mark.asyncio
async def test_rollback_cancels_aborts_completion_and_releases_nights(monkeypatch):
    import core.atomic_booking as atomic

    release = AsyncMock(return_value=2)
    monkeypatch.setattr(atomic, "release_booking_nights", release)
    db = SimpleNamespace(bookings=SimpleNamespace(update_one=AsyncMock()))

    await agency_allotment.rollback_oversold_booking(db, tenant_id="t", booking_id="b1")

    update = db.bookings.update_one.await_args.args[1]["$set"]
    assert update["status"] == "cancelled"
    assert update["agency_completion.status"] == "aborted"
    release.assert_awaited_once_with("t", "b1", reason="agency_allotment_exceeded")
