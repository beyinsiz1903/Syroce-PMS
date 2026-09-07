"""Regression for the empty hire-date error reproduced in live HR validation."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

import domains.hr.router as hr


@pytest.mark.parametrize("value", [None, "", " ", "\t"])
def test_blank_date_is_unspecified(value):
    assert hr.StaffUpdatePayload(hire_date=value).hire_date is None


@pytest.mark.parametrize("value", ["2026-09", "07/09/2026", "bad-date"])
def test_malformed_nonempty_date_remains_rejected(value):
    with pytest.raises(ValidationError):
        hr.StaffUpdatePayload(hire_date=value)


def test_iso_date_preserved():
    assert hr.StaffUpdatePayload(hire_date="2026-09-07").hire_date == "2026-09-07"


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_date", [None, "2026-01-01"])
async def test_salary_edit_with_blank_date_keeps_existing_date(monkeypatch, existing_date):
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "qa", "hire_date": existing_date}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(hr, "db", SimpleNamespace(staff_members=collection))
    monkeypatch.setattr(hr, "_audit", AsyncMock())
    payload = hr.StaffUpdatePayload(hire_date="", salary_agreement={
        "unit": "monthly", "basis": "gross", "amount": "50000",
        "period_month": "2026-09", "opening_tax_base": "180000",
        "opening_exemption_base": "180000", "insurance_days": 30,
        "paid_hours": 225, "source_note": "QA synthetic regression",
        "minimum_wage_exemption": True,
        "standard_4a_confirmed": True,
    })
    result = await hr.update_staff_member(
        "qa", payload, SimpleNamespace(id="operator", tenant_id="qa-tenant", role="admin")
    )
    assert result["success"] is True
    query, update = collection.update_one.call_args.args
    assert query == {"id": "qa", "tenant_id": "qa-tenant"}
    assert "hire_date" not in update["$set"]
    assert update["$set"]["salary_agreement"]["amount"] == 50000
