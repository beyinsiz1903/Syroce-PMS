from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from modules.pms_core.stay_night_metrics import booking_occupies_night, with_checkin_business_date_evidence


def collection(rows):
    return SimpleNamespace(find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=rows))))


def stay(**changes):
    return {"id": "stay", "status": "checked_in", "check_in": "2026-10-18", "check_out": "2026-10-26",
            "checked_in_at": "2026-10-24T10:00:00Z", **changes}


@pytest.mark.asyncio
async def test_completed_audit_presence_recovers_inside_stay_wall_clock_without_rewriting_it():
    items = [{"booking_id": "stay", "run_id": "run18", "posting_date": "2026-10-18"},
             {"booking_id": "stay", "run_id": "run19", "posting_date": "2026-10-19"}]
    db = SimpleNamespace(night_audit_run_items=collection(items), night_audit_runs=collection([
        {"id": "run18", "business_date": "2026-10-18"}, {"id": "run19", "business_date": "2026-10-19"}]))
    original = stay()
    before = deepcopy(original)
    [result] = await with_checkin_business_date_evidence(db, "hotel", [original])
    assert result["checked_in_business_date"] == "2026-10-18"
    assert original == before and result["checked_in_at"] == original["checked_in_at"]
    assert booking_occupies_night(result, date(2026, 10, 18), actual_only=True)
    assert not booking_occupies_night(original, date(2026, 10, 18), actual_only=True)
    query = db.night_audit_run_items.find.call_args.args[0]
    assert query["tenant_id"] == "hotel" and query["booking_id"] == {"$in": ["stay"]}
    assert query["posting_type"] == "room_charge"
    assert db.night_audit_runs.find.call_args.args[0]["status"] == {"$in": ["completed", "completed_with_exceptions"]}


@pytest.mark.asyncio
async def test_dry_failed_or_wrong_day_run_cannot_prove_occupancy_or_hide_real_late_arrival():
    db = SimpleNamespace(night_audit_run_items=collection([
        {"booking_id": "stay", "run_id": "dry", "posting_date": "2026-10-18"},
        {"booking_id": "stay", "run_id": "wrong-day", "posting_date": "2026-10-19"}]),
        night_audit_runs=collection([{"id": "wrong-day", "business_date": "2026-10-20"}]))
    original = stay()
    assert await with_checkin_business_date_evidence(db, "hotel", [original]) == [original]
    assert not booking_occupies_night(original, date(2026, 10, 18), actual_only=True)


@pytest.mark.asyncio
async def test_explicit_business_day_and_simple_stays_need_no_evidence_queries():
    rows = [stay(checked_in_business_date="2026-10-20"), stay(checked_in_at="2026-10-18T12:00:00Z"),
            stay(checked_in_at="2026-11-01T12:00:00Z")]
    assert await with_checkin_business_date_evidence(SimpleNamespace(), "hotel", rows) is rows
