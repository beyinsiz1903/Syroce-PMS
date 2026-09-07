from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_salary_agreements import agreement, mongo_uri, salary_db  # noqa: F401

import domains.hr.router as hr
from domains.accounting.payroll_lines import detailed_payroll_lines
from domains.hr.salary import from_gross

MAPPING = {"wage_expense_code": "770", "employer_expense_code": "770.02", "net_payable_code": "335",
           "withholding_payable_code": "360", "sgk_payable_code": "361", "advance_receivable_code": "196",
           "other_deductions_code": "369"}


def sample():
    a = agreement(period_month="2026-10", amount=50000, opening_tax_base=390000, opening_exemption_base="252679.50")
    row = from_gross(53000, a)
    row.update(calculation_mode="statutory_2026", net_salary=Decimal("38550.03"),
               line_items=[{"kind": "bonus", "amount": 2000}, {"kind": "advance", "amount": 500}])
    return {"summary": {"accounting_version": 2, "total_gross": 53000, "total_net": "38550.03"}, "rows": [row]}


def test_independent_reference_and_separate_posting():
    run = sample()
    row = run["rows"][0]
    assert row["sgk_employer"] == Decimal("11527.50")
    assert row["unemployment_employer"] == 1060
    assert row["income_tax"] == Decimal("5848.40")
    assert row["stamp_tax"] == Decimal("151.57")
    lines = detailed_payroll_lines(run, MAPPING)
    assert {x["account_code"]: x.get("credit", x.get("debit")) for x in lines} == {
        "770": 53000, "770.02": 12587.50, "335": 38550.03,
        "360": 5999.97, "361": 20537.50, "196": 500,
    }
    assert round(sum(x.get("credit", 0) for x in lines), 2) == round(sum(x.get("debit", 0) for x in lines), 2) == 65587.50


def test_employer_premiums_ceiling_and_partial_days():
    assert from_gross(500000, agreement())["sgk_employer"] == Decimal("64656.23")
    partial = from_gross(20000, agreement(insurance_days=15))
    assert partial["employer_contributions"] == 4750
    assert partial["employer_cost"] == 24750


@pytest.mark.parametrize("key", ["sgk_payable_code", "employer_expense_code", "advance_receivable_code"])
def test_missing_mapping_fail_closed(key):
    mapping = dict(MAPPING); mapping.pop(key)
    with pytest.raises(HTTPException, match=key):
        detailed_payroll_lines(sample(), mapping)


def test_same_tax_and_sgk_mapping_rejected():
    with pytest.raises(HTTPException):
        detailed_payroll_lines(sample(), {**MAPPING, "sgk_payable_code": "360"})


@pytest.mark.parametrize("field,value", [("net_salary", 0), ("sgk_employer", None), ("gross_pay", float('nan')), ("employer_cost", 0)])
def test_snapshot_mismatch_or_missing_values_rejected(field, value):
    run = sample(); run["rows"][0][field] = value
    with pytest.raises(HTTPException):
        detailed_payroll_lines(run, MAPPING)


@pytest.mark.parametrize("value", [-1, 0, float('nan'), float('inf')])
def test_invalid_extras_rejected(value):
    with pytest.raises(ValidationError):
        hr.PayrollExtraLine(staff_id="qa", kind="advance", amount=value)


@pytest.mark.asyncio
async def test_real_mongo_extras_recompute_revision_and_lock(salary_db):  # noqa: F811
    from domains.hr.salary import json_values
    user = SimpleNamespace(id="operator", tenant_id="qa", role="super_admin")
    a = agreement(period_month="2026-10", amount=50000, opening_tax_base=390000, opening_exemption_base="252679.50")
    await salary_db.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "name": "QA", "active": True, "salary_agreement": json_values(a.model_dump())})
    await salary_db.overtime_requests.insert_one({"tenant_id": "qa", "staff_id": "staff", "status": "approved", "work_date": "2026-10-05", "hours": 3})
    parent = {"id": "parent", "tenant_id": "qa", "status": "locked", "rows": [{"gross_pay": 10}]}
    await salary_db.payroll_runs.insert_one(deepcopy(parent))
    await salary_db.payroll_runs.insert_one({"id": "revision", "parent_run_id": "parent", "tenant_id": "qa", "status": "draft", "period_month": "2026-10", "updated_at": "v1"})
    payload = hr.PayrollExtrasUpdatePayload(expected_updated_at="v1", extras=[
        {"staff_id": "staff", "kind": "bonus", "amount": 2000, "note": "QA prim"},
        {"staff_id": "staff", "kind": "advance", "amount": 500, "note": "QA avans"},
    ])
    await hr.update_payroll_extras("revision", payload, user)
    updated = await salary_db.payroll_runs.find_one({"id": "revision"})
    assert updated["summary"]["total_gross"] == 53000
    assert updated["summary"]["total_net"] == 38550.03
    assert updated["summary"]["total_employer_cost"] == 65587.50
    assert updated["summary"]["accounting_version"] == 2
    import csv
    import io

    from openpyxl import load_workbook
    response = await hr.export_payroll_run_csv("revision", user)
    csv_text = "".join([chunk async for chunk in response.body_iterator])
    exported = list(csv.DictReader(io.StringIO(csv_text)))[0]
    assert Decimal(exported["net_salary"]) == Decimal("38550.03")
    assert Decimal(exported["extra_deductions"]) == 500
    assert Decimal(exported["employer_cost"]) == Decimal("65587.50")
    response = await hr.export_payroll_run_xlsx("revision", user)
    content = b"".join([chunk async for chunk in response.body_iterator])
    sheet = load_workbook(io.BytesIO(content)).worksheets[0]
    assert sheet["J2"].value == 38550.03
    assert sheet["L2"].value == 11527.5 and sheet["O2"].value == 65587.5
    assert await salary_db.payroll_runs.find_one({"id": "parent"}, {"_id": 0}) == parent
    with pytest.raises(HTTPException, match="başka bir oturum"):
        await hr.update_payroll_extras("revision", payload, user)
    payload.expected_updated_at = updated["updated_at"]
    await salary_db.payroll_runs.update_one({"id": "revision"}, {"$set": {"status": "locked"}})
    with pytest.raises(HTTPException, match="Yalnızca taslak"):
        await hr.update_payroll_extras("revision", payload, user)


@pytest.mark.asyncio
async def test_foreign_extra_staff_not_silently_dropped(salary_db):  # noqa: F811
    with pytest.raises(HTTPException, match="Ek kalem personeli"):
        await hr._build_payroll_v2("qa", "2026-10", [{"staff_id": "foreign", "kind": "bonus", "amount": 100}])


@pytest.mark.asyncio
async def test_extras_endpoint_rbac_and_tenant_scope(monkeypatch):
    collection = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    monkeypatch.setattr(hr, "db", SimpleNamespace(payroll_runs=collection))
    monkeypatch.setattr(hr, "_user_has_hr_op", lambda *args: False)
    payload = hr.PayrollExtrasUpdatePayload(expected_updated_at="v1", extras=[])
    with pytest.raises(HTTPException) as err:
        await hr.update_payroll_extras("run", payload, SimpleNamespace(id="u", role="front_desk", tenant_id="qa"))
    assert err.value.status_code == 403
    collection.find_one.assert_not_awaited()
    with pytest.raises(HTTPException) as err:
        await hr.update_payroll_extras("foreign-run", payload, SimpleNamespace(id="u", role="finance", tenant_id="qa"))
    assert err.value.status_code == 404
    assert collection.find_one.call_args.args[0] == {"id": "foreign-run", "tenant_id": "qa"}
    collection.update_one.assert_not_awaited()
