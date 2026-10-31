"""Manager output must use the same actual-night cohort as official reports."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from modules.pms_core.manager_daily_operations import manager_daily_operations
from modules.pms_core.stay_night_metrics import load_stay_night_metrics
from routers.reports_pkg import standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.fixture(autouse=True)
async def data(ledger_db, monkeypatch):
    monkeypatch.setattr(standard_reports, "db", ledger_db)
    monkeypatch.setattr(standard_reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-26"}))
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": room, "room_number": room} for room in ("r1", "r2", "r3")])
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "virtual", "room_number": "virtual", "is_virtual": True})
    await ledger_db.room_blocks.insert_one({"tenant_id": "A", "room_id": "r3", "start_date": "2026-10-26", "end_date": "2026-10-27", "status": "active", "allow_sell": False})
    base = {"tenant_id": "A", "check_in": "2026-10-25", "check_out": "2026-10-28", "currency": "TRY", "total_amount": 300}
    await ledger_db.bookings.insert_many([
        {**base, "id": "actual", "room_id": "r1", "status": "checked_in", "guest_nationality": "TR", "vip": True},
        {**base, "id": "planned", "room_id": "r2", "status": "confirmed"},
        {**base, "id": "late", "room_id": "r2", "status": "checked_in", "checked_in_business_date": "2026-10-27"},
        {**base, "id": "left", "room_id": "r2", "status": "checked_out", "checked_out_business_date": "2026-10-26"},
        {**base, "id": "virtual", "room_id": "virtual", "status": "checked_in"},
        {**base, "id": "foreign", "tenant_id": "B", "room_id": "r1", "status": "checked_in"},
        {**base, "id": "cancel", "check_in": "2026-11-20", "check_out": "2026-11-22", "status": "cancelled", "cancelled_at": "2026-10-26T12:00:00Z"},
    ])


async def test_manager_metrics_match_canonical_occupancy_and_same_cohort_breakdowns(ledger_db):
    result = await standard_reports.get_manager_daily_operations(date_str="2026-10-26", current_user=SimpleNamespace(tenant_id="A"))
    canonical = (await load_stay_night_metrics(ledger_db, "A", date(2026, 10, 26), date(2026, 10, 26), actual_only=True))[0]
    assert result["occupiedRooms"] == canonical["occupied_rooms"] == 1
    assert result["occupancy"] == canonical["occupancy_rate"] == 50
    assert (result["totalRooms"], result["availableRooms"], result["oooRooms"], result["emptyRooms"]) == (3, 2, 1, 1)
    assert result["nationality"] == {"TR": 1} and sum(result["losDistribution"].values()) == result["inhouseReservations"] == 1
    assert result["vipGuests"] == result["cancellations"] == 1
    assert not {"guest_name", "guest_id", "email"}.intersection(result)


async def test_completed_audit_evidence_recovers_lagging_checkin_timestamp(ledger_db):
    await ledger_db.bookings.update_one({"id": "actual"}, {"$set": {"checked_in_at": "2026-10-27T04:00:00Z"}})
    assert (await manager_daily_operations(ledger_db, "A", date(2026, 10, 26)))["occupiedRooms"] == 0
    await ledger_db.night_audit_runs.insert_one({"tenant_id": "A", "id": "run", "business_date": "2026-10-25", "status": "completed"})
    await ledger_db.night_audit_run_items.insert_one({"tenant_id": "A", "run_id": "run", "booking_id": "actual", "posting_date": "2026-10-25", "posting_type": "room_charge", "status": "posted"})
    assert (await manager_daily_operations(ledger_db, "A", date(2026, 10, 26)))["occupiedRooms"] == 1


@pytest.mark.parametrize("value", ["", "2026-10-26oops", "2026-02-30"])
async def test_invalid_date_is_rejected_not_truncated(ledger_db, value):
    with pytest.raises(HTTPException) as error:
        await standard_reports.get_manager_daily_operations(date_str=value, current_user=SimpleNamespace(tenant_id="A"))
    assert error.value.status_code == 422
