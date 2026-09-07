"""Approved overtime must survive attendance-free payroll previews."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import domains.hr.router as hr


@pytest.fixture
def payroll_data(monkeypatch):
    base = AsyncMock(return_value=("2026-09", []))
    overtime = AsyncMock(return_value={"qa": {"hours": 1.5, "requests": 1}})
    staff = AsyncMock(return_value={"id": "qa", "name": "QA", "hourly_rate": 200, "department": "test"})
    monkeypatch.setattr(hr, "_build_payroll", base)
    monkeypatch.setattr(hr, "_payroll_collect_overtime", overtime)
    monkeypatch.setattr(hr, "_verify_staff_in_tenant", staff)
    monkeypatch.setattr(hr, "_payroll_collect_leaves", AsyncMock(return_value={}))
    monkeypatch.setattr(hr, "_get_payroll_tax_rates", AsyncMock(return_value=hr.TR_PAYROLL_TAX_RATES_DEFAULT))
    # Any accidental persistence access must fail, not modify locked snapshots.
    monkeypatch.setattr(hr, "db", SimpleNamespace())
    return base, overtime, staff


@pytest.mark.asyncio
async def test_overtime_only_staff_gets_paid_without_attendance(payroll_data):
    month, rows, summary = await hr._build_payroll_v2("tenant-qa", "2026-09")
    assert month == "2026-09"
    assert len(rows) == 1
    row = rows[0]
    assert row["staff_name"] == "QA"
    assert row["gross_pay"] == 450  # 1.5h * 200 * 1.5
    assert row["attendance_hours"] == 0
    assert row["approved_overtime_hours"] == row["overtime_hours"] == row["total_hours"] == 1.5
    assert row["net_salary"] == 321.70
    assert summary["total_gross"] == 450
    payroll_data[2].assert_awaited_once_with("qa", "tenant-qa")
    assert next(item for item in row["line_items"] if item["kind"] == "overtime_approved")["amount"] == 450
    assert payroll_data[0].return_value[1] == []


@pytest.mark.asyncio
async def test_existing_attendance_row_not_duplicated_or_mutated(payroll_data):
    base, _, staff = payroll_data
    rows = hr._compute_payroll_for_month(
        [{"staff_id": "qa", "total_hours": 200}],
        {"qa": {"hourly_rate": 200, "monthly_hours": 195}}, "2026-09",
    )
    original = deepcopy(rows)
    base.return_value = ("2026-09", rows)
    _, result, _ = await hr._build_payroll_v2("tenant-qa", "2026-09")
    assert len(result) == 1
    assert result[0]["gross_pay"] == original[0]["gross_pay"] + 450
    assert result[0]["overtime_hours"] == 6.5
    assert result[0]["total_hours"] == 201.5
    assert rows == original
    staff.assert_not_awaited()


@pytest.mark.asyncio
async def test_orphan_staff_fails_closed_instead_of_silent_underpayment(payroll_data):
    payroll_data[2].return_value = None
    with pytest.raises(HTTPException) as exc:
        await hr._build_payroll_v2("tenant-qa", "2026-09")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_no_attendance_and_no_approved_overtime_stays_empty(payroll_data):
    payroll_data[1].return_value = {}
    _, rows, summary = await hr._build_payroll_v2("tenant-qa", "2026-09")
    assert rows == []
    assert summary["staff_count"] == summary["total_gross"] == 0
    payroll_data[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_collector_is_tenant_month_and_approval_scoped(monkeypatch):
    async def records():
        yield {"staff_id": "qa", "hours": 1}
        yield {"staff_id": "qa", "hours": 0.5}
    find = Mock(return_value=records())
    monkeypatch.setattr(hr, "db", SimpleNamespace(overtime_requests=SimpleNamespace(find=find)))
    assert await hr._payroll_collect_overtime("tenant-qa", "2026-09") == {"qa": {"hours": 1.5, "requests": 2}}
    assert find.call_args.args[0] == {
        "tenant_id": "tenant-qa", "status": "approved",
        "work_date": {"$gte": "2026-09-01", "$lte": "2026-09-30"},
    }
