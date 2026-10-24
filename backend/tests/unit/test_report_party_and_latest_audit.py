from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.pms_core.daily_reconciliation import latest_night_audit
from modules.pms_core.stay_night_metrics import reservation_party_counts


def test_people_are_declared_party_not_rooms_or_duplicate_guest_profile_rows():
    rows = [{"id": "family", "adults": 2, "children": 2},
            {"id": "family", "adults": 2, "children": 2},
            {"id": "couple", "adults": 2, "children": 0}]
    assert reservation_party_counts(rows) == {"adults": 4, "children": 2, "total": 6,
        "known_total": 6, "unknown_booking_count": 0, "basis": "reservation_party"}


@pytest.mark.parametrize("invalid", [None, -1, True, "2", 1.5])
def test_incomplete_or_invalid_party_is_unknown_not_an_invented_zero(invalid):
    result = reservation_party_counts([{"id": "one", "adults": 2, "children": 0},
                                       {"id": "unknown", "adults": invalid, "children": 0}])
    assert result["total"] is None and result["known_total"] == 2
    assert result["unknown_booking_count"] == 1


@pytest.mark.asyncio
async def test_current_run_is_tenant_scoped_and_preferred_over_stale_legacy_log():
    db = SimpleNamespace(night_audit_runs=SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "oct23", "business_date": "2026-10-23", "status": "completed", "started_at": "2026-10-24T10:00:00Z"})),
        night_audit_logs=SimpleNamespace(find_one=AsyncMock()))
    result = await latest_night_audit(db, "hotel")
    assert result["audit_date"] == "2026-10-23" and result["source"] == "night_audit_runs"
    assert result["status"] == "completed"
    assert db.night_audit_runs.find_one.call_args.args[0] == {"tenant_id": "hotel", "dry_run": {"$ne": True}}
    db.night_audit_logs.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_property_remains_supported_without_fabricating_an_audit():
    db = SimpleNamespace(night_audit_runs=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        night_audit_logs=SimpleNamespace(find_one=AsyncMock(return_value={"audit_date": "2026-04-22", "status": "partial"})))
    assert (await latest_night_audit(db, "hotel"))["source"] == "night_audit_logs"
    assert db.night_audit_logs.find_one.call_args.args[0] == {"tenant_id": "hotel"}
    db.night_audit_logs.find_one.return_value = None
    assert await latest_night_audit(db, "hotel") is None
