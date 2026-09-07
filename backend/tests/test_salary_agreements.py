from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError
from test_gl_sequence_index_mongo import mongo_uri  # noqa: F401

import domains.hr.router as hr
from domains.hr.salary import MIN_BASE, SalaryAgreement, calculate, from_gross, tariff


def agreement(**changes):
    data = {
        "unit": "monthly",
        "basis": "gross",
        "amount": "33030",
        "period_month": "2026-01",
        "opening_tax_base": 0,
        "opening_exemption_base": 0,
        "minimum_wage_exemption": True,
        "insurance_days": 30,
        "paid_hours": 225,
        "source_note": "QA opening payroll",
        "standard_4a_confirmed": True,
    }
    data.update(changes)
    return SalaryAgreement(**data)


def test_official_minimum_wage_reference():
    r = calculate(agreement())
    assert r["net_salary"] == D("28075.50")
    assert r["sgk_employee"] == D("4624.20")
    assert r["unemployment"] == D("330.30")
    assert r["income_tax"] == r["stamp_tax"] == 0


@pytest.mark.parametrize("base,tax", [(190000, 28500), (400000, 70500), (1500000, 367500), (5300000, 1697500), (5300100, 1697540)])
def test_official_wage_brackets(base, tax):
    assert tariff(D(base)) == D(tax)


@pytest.mark.parametrize("opening", [0, 185000, 390000, 1490000, 5290000, 6000000])
@pytest.mark.parametrize("gross", [33030, 50000, 297270, 500000, 1234567.89])
def test_net_gross_roundtrip(opening, gross):
    a = agreement(period_month="2026-09", opening_tax_base=opening, opening_exemption_base=MIN_BASE * 8, amount=gross)
    forward = calculate(a)
    reverse = calculate(a.model_copy(update={"basis": "net", "amount": forward["net_salary"]}))
    assert abs(reverse["net_salary"] - forward["net_salary"]) <= D(".01")
    assert abs(reverse["gross_pay"] - D(str(gross))) <= D(".04")


def test_sgk_ceiling_and_exemption_not_prorated():
    r = calculate(agreement(amount=500000))
    assert r["tax_calculation"]["premium_base"] == 297270
    assert r["sgk_employee"] == D("41617.80")
    partial = calculate(agreement(amount=33030, insurance_days=15))
    assert partial["gross_pay"] == 16515
    assert partial["net_salary"] == D("14037.75")


def test_cumulative_tax_changes_net():
    a = agreement(amount=50000, period_month="2026-09")
    assert calculate(a)["net_salary"] > calculate(a.model_copy(update={"opening_tax_base": D(600000)}))["net_salary"]


@pytest.mark.parametrize(
    "changes",
    [
        {"opening_tax_base": None},
        {"opening_tax_base": ""},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"opening_tax_base": -1},
        {"standard_4a_confirmed": False},
        {"period_month": "2027-01"},
        {"opening_tax_base": 1},
        {"opening_exemption_base": 1},
        {"insurance_days": 0},
    ],
)
def test_invalid_context_rejected(changes):
    with pytest.raises(ValidationError):
        agreement(**changes)


def test_hourly_and_monthly_equivalence():
    assert calculate(agreement(amount=50000)) == calculate(agreement(unit="hourly", amount=250, paid_hours=200))


def test_exemption_disabled():
    r = calculate(agreement(minimum_wage_exemption=False))
    assert r["income_tax"] == D("4211.33")
    assert r["stamp_tax"] == D("250.70")


@pytest.mark.asyncio
async def test_monthly_salary_without_attendance_and_tenant_scope(monkeypatch):
    a = agreement(amount=50000)

    async def staff_rows():
        yield {"id": "staff", "tenant_id": "qa", "name": "QA", "salary_agreement": a.model_dump(), "active": True}

    find = Mock(side_effect=lambda *args: staff_rows())
    monkeypatch.setattr(hr, "db", SimpleNamespace(staff_members=SimpleNamespace(find=find)))
    monkeypatch.setattr(hr, "_build_payroll", AsyncMock(return_value=("2026-01", [])))
    monkeypatch.setattr(hr, "_payroll_collect_overtime", AsyncMock(return_value={}))
    monkeypatch.setattr(hr, "_payroll_collect_leaves", AsyncMock(return_value={}))
    monkeypatch.setattr(hr, "_get_payroll_tax_rates", AsyncMock(return_value=hr.TR_PAYROLL_TAX_RATES_DEFAULT))
    _, rows, summary = await hr._build_payroll_v2("qa", "2026-01")
    assert find.call_args.args[0]["tenant_id"] == "qa"
    assert summary["staff_count"] == 1
    assert rows[0]["gross_pay"] == 50000
    assert rows[0]["net_salary"] == float(calculate(a)["net_salary"])
    assert rows[0]["calculation_mode"] == "statutory_2026"
    hr._build_payroll.return_value = ("2026-02", [])
    with pytest.raises(HTTPException, match="2026-02"):
        await hr._build_payroll_v2("qa", "2026-02")


def test_new_fields_masked_for_unrelated_user(monkeypatch):
    monkeypatch.setattr(hr, "_user_has_hr_op", lambda *args: False)
    user = SimpleNamespace(id="unrelated", email="other@example.test", role="front_desk")
    masked = hr._mask_hr_pii({"id": "staff", "salary_agreement": agreement().model_dump(), "tax_calculation": from_gross(33030, agreement())["tax_calculation"]}, user)
    assert masked["salary_agreement"] is None
    assert masked["tax_calculation"] is None


@pytest.fixture
def salary_db(monkeypatch, mongo_uri):  # noqa: F811
    client = AsyncIOMotorClient(mongo_uri)
    database = client.salary_agreement_qa
    monkeypatch.setattr(hr, "db", database)
    monkeypatch.setattr(hr, "_audit", AsyncMock())
    yield database
    client.close()


@pytest.mark.asyncio
async def test_real_mongo_update_preview_extra_tax_and_snapshot(salary_db):
    from domains.hr.salary import json_values
    user = SimpleNamespace(id="operator", tenant_id="qa", role="super_admin")
    a = agreement(amount=50000)
    await salary_db.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "name": "QA", "active": True})
    locked = {"id": "old", "tenant_id": "qa", "status": "locked", "rows": [{"gross_pay": 10}]}
    await salary_db.payroll_runs.insert_one(dict(locked))
    await hr.update_staff_member("staff", hr.StaffUpdatePayload(salary_agreement=a), user)
    saved = await salary_db.staff_members.find_one({"id": "staff"})
    assert saved["salary_agreement"] == json_values(a.model_dump())
    audit = hr._audit.call_args.kwargs
    assert "salary_agreement" not in audit["before"] and "salary_agreement" not in audit["after"]
    await salary_db.overtime_requests.insert_one({"tenant_id": "qa", "staff_id": "staff", "status": "approved", "work_date": "2026-01-10", "hours": 3})
    await salary_db.staff_members.insert_one({"id": "foreign", "tenant_id": "other", "name": "NOT IN QA", "salary_agreement": json_values(a.model_dump())})
    _, rows, _ = await hr._build_payroll_v2("qa", "2026-01", [{"staff_id": "staff", "kind": "bonus", "amount": 1000}])
    assert len(rows) == 1 and rows[0]["staff_id"] == "staff"
    assert rows[0]["gross_pay"] == 52000  # 50000 / 225 * 3 * 1.5 + 1000
    assert rows[0]["income_tax"] == float(from_gross(52000, a)["income_tax"])
    assert await salary_db.payroll_runs.find_one({"id": "old"}, {"_id": 0}) == locked


@pytest.mark.asyncio
async def test_invalid_context_cannot_overwrite_agreement(salary_db):
    from domains.hr.salary import json_values
    a = agreement(amount=50000)
    await salary_db.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "salary_agreement": json_values(a.model_dump())})
    user = SimpleNamespace(id="operator", tenant_id="qa", role="super_admin")
    with pytest.raises(HTTPException):
        await hr.update_staff_member("staff", hr.StaffUpdatePayload(salary_agreement=agreement(amount=10)), user)
    assert (await salary_db.staff_members.find_one({"id": "staff"}))["salary_agreement"]["amount"] == 50000


@pytest.mark.asyncio
async def test_hourly_overtime_cannot_be_paid_twice(salary_db):
    from domains.hr.salary import json_values
    a = agreement(unit="hourly", amount=250, paid_hours=200)
    await salary_db.staff_members.insert_one({"id": "staff", "tenant_id": "qa", "name": "QA", "salary_agreement": json_values(a.model_dump())})
    await salary_db.attendance_records.insert_one({"tenant_id": "qa", "staff_id": "staff", "date": "2026-01-10", "total_hours": 203})
    await salary_db.overtime_requests.insert_one({"tenant_id": "qa", "staff_id": "staff", "status": "approved", "work_date": "2026-01-10", "hours": 3})
    _, rows, _ = await hr._build_payroll_v2("qa", "2026-01")
    assert rows[0]["gross_pay"] == 51125
    await salary_db.staff_members.update_one({"id": "staff"}, {"$set": {"salary_agreement.paid_hours": 203}})
    with pytest.raises(HTTPException, match="iki kez"):
        await hr._build_payroll_v2("qa", "2026-01")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["front_desk", "housekeeping", "supervisor"])
async def test_exports_deny_roles_without_payroll_permission(monkeypatch, role):
    monkeypatch.setattr(hr, "_user_has_hr_op", lambda *args: False)
    user = SimpleNamespace(id="other", tenant_id="qa", role=role)
    for export in (hr.export_payroll, hr.export_payroll_csv_stream):
        with pytest.raises(HTTPException) as exc:
            await export(month="2026-01", current_user=user)
        assert exc.value.status_code == 403
