from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.finance import accounting


@pytest.mark.asyncio
async def test_expense_update_recalculates_vat_and_total(monkeypatch):
    existing = {"id": "expense-a", "tenant_id": "tenant-a", "amount": 100, "vat_rate": 20, "currency": "TRY"}
    expenses = SimpleNamespace(
        find_one=AsyncMock(side_effect=[existing, {**existing, "amount": 200, "vat_rate": 10, "vat_amount": 20, "total_amount": 220}]),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    cash_flow = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(expenses=expenses, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    result = await accounting.update_expense(
        "expense-a",
        {"amount": 200, "vat_rate": 10},
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _perm=None,
    )

    assert result["total_amount"] == 220
    assert expenses.update_one.await_args.args[1]["$set"] == {
        "amount": 200.0,
        "vat_rate": 10.0,
        "vat_amount": 20.0,
        "total_amount": 220.0,
    }
    assert cash_flow.update_one.await_args.args[1]["$set"] == {
        "transaction_type": "expense",
        "category": None,
        "amount": 220.0,
        "currency": "TRY",
        "description": None,
        "date": None,
    }
    assert cash_flow.update_one.await_args.kwargs["upsert"] is True


@pytest.mark.asyncio
async def test_expense_update_rejects_tenant_or_total_tampering(monkeypatch):
    monkeypatch.setattr(accounting, "db", SimpleNamespace())

    with pytest.raises(HTTPException) as exc:
        await accounting.update_expense(
            "expense-a",
            {"tenant_id": "other-tenant", "total_amount": 1},
            current_user=SimpleNamespace(tenant_id="tenant-a"),
            _perm=None,
        )

    assert exc.value.status_code == 422
