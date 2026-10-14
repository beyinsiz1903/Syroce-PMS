"""Test-data deactivation never deletes and is gated by an explicit opt-in."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import deactivate_test_records as cleanup


@pytest.mark.parametrize("name,junk", [
    ("=cmd|'/c calc'!A1", True), ("TEST_B2B_Revoke_050620", True), ("+1+1", True), ("@SUM", True),
    ("Syroce Travel", False), ("Antalya Sun Tours", False), ("Test Turizm", False),
])
def test_junk_agency_names(name, junk):
    assert cleanup.is_junk_agency(name) is junk


@pytest.mark.asyncio
async def test_apply_requires_env_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_TEST_DATA_DEACTIVATION", raising=False)
    assert await cleanup.main(["--tenant-id", "t1", "--apply"]) == 2


@pytest.mark.asyncio
async def test_apply_deactivates_and_cancels_without_deleting(monkeypatch):
    import core.atomic_booking as atomic

    monkeypatch.setattr(atomic, "release_booking_nights", AsyncMock(return_value=3))
    database = SimpleNamespace(
        agencies=SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock(), delete_many=AsyncMock()),
        bookings=SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock(), delete_many=AsyncMock()),
    )
    targets = {"agencies": [{"id": "a1", "status": "active"}], "bookings": [{"id": "b1", "status": "confirmed"}]}

    result = await cleanup.apply_targets(database, "t1", targets, "run-1")

    assert result == {"agencies": 1, "bookings": 1, "released_nights": 3}
    assert database.agencies.update_one.await_args.args[1]["$set"]["status"] == "inactive"
    booking_set = database.bookings.update_one.await_args.args[1]["$set"]
    assert (booking_set["status"], booking_set["cancellation_reason"]) == ("cancelled", "test_data_cleanup")
    for coll in (database.agencies, database.bookings):
        coll.delete_one.assert_not_awaited()
        coll.delete_many.assert_not_awaited()
