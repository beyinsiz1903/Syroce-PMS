"""Sustainability room-night denominator against a real (local, disposable)
Mongo: review findings on #1370 (BSON dates, never-arrived and cancelled
bookings, early check-out)."""
from datetime import UTC, date, datetime

from routers import sustainability as module

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
OCT_1, OCT_31 = date(2026, 10, 1), date(2026, 10, 31)


async def _nights(ledger_db, monkeypatch, *bookings):
    monkeypatch.setattr(module, "db", ledger_db)
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": f"r{i}"} for i in range(1, 6)])
    if bookings:
        await ledger_db.bookings.insert_many([{"tenant_id": "A", **b} for b in bookings])
    return await module.occupied_room_nights("A", OCT_1, OCT_31)


async def test_bson_stay_dates_count(ledger_db, monkeypatch):
    nights = await _nights(ledger_db, monkeypatch, {"room_id": "r1", "status": "checked_out",
        "check_in": datetime(2026, 10, 1, tzinfo=UTC), "check_out": datetime(2026, 10, 3, tzinfo=UTC)})
    assert nights == 2


async def test_bookings_that_never_stayed_do_not_count(ledger_db, monkeypatch):
    nights = await _nights(ledger_db, monkeypatch,
        {"room_id": "r1", "status": "pending", "check_in": "2026-10-01", "check_out": "2026-10-03"},
        {"room_id": "r2", "status": "canceled", "check_in": "2026-10-01", "check_out": "2026-10-03"},
        {"room_id": "r3", "status": "cancelled", "check_in": "2026-10-01", "check_out": "2026-10-03"},
        {"room_id": "r4", "status": "no_show", "check_in": "2026-10-01", "check_out": "2026-10-03"})
    assert nights == 0


async def test_early_check_out_counts_the_nights_actually_stayed(ledger_db, monkeypatch):
    nights = await _nights(ledger_db, monkeypatch, {"room_id": "r1", "status": "checked_out",
        "check_in": "2026-10-01", "check_out": "2026-10-05",
        "checked_in_at": "2026-10-01T15:00:00+00:00", "checked_out_at": "2026-10-03T09:00:00+00:00"})
    assert nights == 2
