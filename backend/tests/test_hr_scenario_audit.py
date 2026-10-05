"""Regression coverage for the isolated HR release audit findings.

Persistence uses a disposable localhost MongoDB. Authentication sessions,
browser downloads and actual notification delivery are not simulated passes.
"""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import load_workbook
from test_gl_sequence_index_mongo import mongo_uri  # noqa: F401

import domains.hr.router as hr

USER = SimpleNamespace(id="operator", tenant_id="qa", role="super_admin", granted_permissions=[])


@pytest.fixture
def isolated(monkeypatch, mongo_uri):  # noqa: F811 - imported pytest fixture
    client = AsyncIOMotorClient(mongo_uri)
    db = client.hr_release_audit
    monkeypatch.setattr(hr, "db", db)
    monkeypatch.setattr(hr, "get_motor_database", lambda: db)
    monkeypatch.setattr(hr, "_audit", AsyncMock())
    yield db
    client.close()


async def leave(db, **changes):
    doc = {"id": "leave", "tenant_id": "qa", "staff_id": "staff", "status": "dept_approved",
               "start_date": "2026-09-08", "end_date": "2026-09-09", "total_days": 2,
               "leave_type": "annual", "requested_by": "operator"}
    doc.update(changes)
    await db.leave_requests.insert_one(doc)
    return doc


async def approve():
    return await hr.decide_leave_request("leave", hr.LeaveDecision(decision="approve"), USER)


@pytest.mark.asyncio
async def test_annual_leave_cannot_exceed_balance(isolated):
    await isolated.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "name": "QA"})
    await isolated.leave_balances.insert_one({"tenant_id": "qa", "staff_id": "staff", "year": 2026, "annual_entitlement": 1})
    await leave(isolated)
    with pytest.raises(HTTPException):
        await approve()


@pytest.mark.asyncio
async def test_overlapping_leave_cannot_be_approved(isolated):
    await leave(isolated, id="previous", status="approved")
    await leave(isolated)
    with pytest.raises(HTTPException):
        await approve()


@pytest.mark.asyncio
async def test_year_crossing_leave_balance_counts_only_days_in_year(isolated):
    await isolated.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "name": "QA"})
    await leave(isolated, status="approved", start_date="2026-12-31", end_date="2027-01-02", total_days=3)
    old = await hr.get_leave_balance("staff", 2026, USER)
    new = await hr.get_leave_balance("staff", 2027, USER)
    assert (old["annual"]["used"], new["annual"]["used"]) == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("month,days", [("2026-12", 1), ("2027-01", 2)])
async def test_payroll_leave_month_clipping(isolated, month, days):
    await leave(isolated, status="approved", start_date="2026-12-31", end_date="2027-01-02", total_days=3)
    result = await hr._payroll_collect_leaves("qa", month)
    assert result["staff"]["paid_days"] == days


@pytest.mark.asyncio
async def test_concurrent_leave_approve_reject_has_one_winner(isolated, monkeypatch):
    await leave(isolated)
    results = await asyncio.gather(approve(), hr.decide_leave_request(
        "leave", hr.LeaveDecision(decision="reject", note="QA reject"), USER), return_exceptions=True)
    assert sum(isinstance(r, dict) and r.get("success") is True for r in results) == 1


@pytest.mark.asyncio
async def test_leave_shift_write_failure_is_recoverable_on_retry(isolated, monkeypatch):
    await leave(isolated)
    actual = hr._apply_leave_to_shifts
    attempts = 0
    async def interrupted(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        result = await actual(*args, **kwargs)
        if attempts == 1:
            raise ConnectionError("simulated interruption after shift writes")
        return result
    shifts = AsyncMock(side_effect=interrupted)
    monkeypatch.setattr(hr, "_apply_leave_to_shifts", shifts)
    with pytest.raises(ConnectionError):
        await approve()
    assert (await isolated.leave_requests.find_one({"id": "leave"}))["status"] == "dept_approved"
    assert await isolated.notifications.count_documents({}) == 0
    assert await isolated.shift_schedules.count_documents({}) == 0
    try:
        result = await approve()
    except HTTPException as error:
        pytest.fail(f"Retry cannot recover shift projection: {error.status_code} {error.detail}")
    assert result["success"] and shifts.await_count == 2
    assert await isolated.shift_schedules.count_documents({}) == 2
    assert await isolated.notifications.count_documents({}) == 1
    await approve()  # A lost HTTP response is safely replayable.
    assert await isolated.shift_schedules.count_documents({}) == 2
    assert await isolated.notifications.count_documents({}) == 1


@pytest.mark.asyncio
async def test_two_distinct_leave_requests_share_one_balance(isolated):
    await isolated.leave_balances.insert_one({"tenant_id": "qa", "staff_id": "staff", "year": 2026,
                                               "annual_entitlement": 2})
    await leave(isolated)
    await leave(isolated, id="second", start_date="2026-09-10", end_date="2026-09-11")
    results = await asyncio.gather(*(hr.decide_leave_request(
        rid, hr.LeaveDecision(decision="approve"), USER) for rid in ("leave", "second")), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert await isolated.leave_requests.count_documents({"status": "approved"}) == 1


@pytest.mark.parametrize("value", ["20260908", "2026-09-08T00:00:00", "2026-02-30"])
def test_leave_dates_are_canonical(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        hr.LeaveRequestPayload(staff_id="staff", start_date=value, end_date="2026-09-09")


async def overtime(db, req_id, hours, status="dept_approved", work_date="2026-09-08"):
    await db.overtime_requests.insert_one({"id": req_id, "tenant_id": "qa", "staff_id": "staff",
        "status": status, "hours": hours, "work_date": work_date, "requested_by": "operator"})


@pytest.mark.asyncio
async def test_overtime_sequential_cap_and_year_boundary(isolated):
    await overtime(isolated, "prior", 269, "approved")
    await overtime(isolated, "too-much", 2)
    with pytest.raises(HTTPException) as caught:
        await hr.decide_overtime_request("too-much", hr.OvertimeDecisionPayload(action="approve"), USER)
    assert caught.value.status_code == 400
    await overtime(isolated, "next-year", 2, work_date="2027-01-01")
    result = await hr.decide_overtime_request("next-year", hr.OvertimeDecisionPayload(action="approve"), USER)
    assert result["success"]


@pytest.mark.asyncio
async def test_concurrent_overtime_cannot_exceed_annual_cap(isolated, monkeypatch):
    await overtime(isolated, "prior", 269, "approved")
    await overtime(isolated, "a", 1)
    await overtime(isolated, "b", 1)
    actual = hr._yearly_overtime_hours
    results = await asyncio.gather(*(hr.decide_overtime_request(
        rid, hr.OvertimeDecisionPayload(action="approve"), USER) for rid in ("a", "b")), return_exceptions=True)
    assert sum(isinstance(r, dict) and r.get("success") for r in results) == 1
    assert await actual("qa", "staff", 2026) <= 270


@pytest.mark.asyncio
async def test_notification_recipients_include_active_superadmin_only_in_tenant(isolated):
    await isolated.users.insert_many([
        {"id": "super", "tenant_id": "qa", "role": "super_admin", "is_active": True},
        {"id": "admin", "tenant_id": "qa", "role": "admin", "is_active": True},
        {"id": "inactive", "tenant_id": "qa", "role": "admin", "is_active": False},
        {"id": "other", "tenant_id": "other", "role": "admin", "is_active": True},
    ])
    await hr._notify_hr_managers("qa", kind="leave_request", title="QA", body="QA", ref_id="leave")
    docs = await isolated.notifications.find({}).to_list(None)
    assert {doc["user_id"] for doc in docs} == {"super", "admin"}


@pytest.mark.asyncio
async def test_xlsx_snapshot_numeric_parity_and_formula_safety(isolated):
    row = {"staff_id": "staff", "staff_name": "=1+1", "department": "QA", "total_hours": 1.5,
        "overtime_hours": 1.5, "gross_pay": 315, "sgk_employee": 44.1, "unemployment": 3.15,
        "income_tax": 40.16, "stamp_tax": 2.39, "net_salary": 225.2,
        "line_items": [{"kind": "overtime_approved", "label": "QA", "amount": 315, "note": "=1+1"}]}
    await isolated.payroll_runs.insert_one({"id": "run", "tenant_id": "qa", "period_month": "2026-09",
        "status": "locked", "rows": [row], "summary": {}})
    response = await hr.export_payroll_run_xlsx("run", USER)
    content = b"".join([chunk async for chunk in response.body_iterator])
    workbook = load_workbook(io.BytesIO(content), data_only=False)
    sheet = workbook.worksheets[0]
    assert (sheet["D2"].value, sheet["E2"].value, sheet["J2"].value) == (1.5, 315, 225.2)
    assert sheet["P2"].value == "Yaklaşık hesap"
    assert "kesinleştirme" in sheet["Q2"].value
    assert sheet["A3"].value == "TOPLAM" and sheet["J3"].value == 225.2
    assert sheet.freeze_panes == "A2" and sheet.auto_filter.ref == "A1:Q2"
    assert sheet.column_dimensions["Q"].width > 16
    assert sheet["A2"].data_type != "f", "Staff name became executable XLSX formula"
    assert workbook["Kalemler"]["H2"].data_type != "f"
