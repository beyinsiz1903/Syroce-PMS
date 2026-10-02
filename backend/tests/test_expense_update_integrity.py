from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.finance import accounting


@pytest.mark.asyncio
async def test_expense_update_recalculates_vat_and_total(monkeypatch):
    existing = {
        "id": "expense-a",
        "tenant_id": "tenant-a",
        "supplier_id": "supplier-a",
        "amount": 100,
        "vat_rate": 20,
        "total_amount": 120,
        "currency": "TRY",
        "payment_status": "paid",
    }
    expenses = SimpleNamespace(
        find_one=AsyncMock(side_effect=[existing, {**existing, "amount": 200, "vat_rate": 10, "vat_amount": 20, "total_amount": 220}]),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    cash_flow = SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock())
    suppliers = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(expenses=expenses, cash_flow=cash_flow, suppliers=suppliers))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))

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
    cash_flow.delete_one.assert_not_awaited()
    assert suppliers.update_one.await_args.args == (
        {"id": "supplier-a", "tenant_id": "tenant-a"},
        {"$inc": {"account_balance_by_currency.TRY": 100.0, "account_balance": 100.0}},
    )


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


@pytest.mark.asyncio
async def test_unpaid_expense_update_removes_legacy_cash_flow(monkeypatch):
    existing = {
        "id": "expense-a",
        "tenant_id": "tenant-a",
        "amount": 100,
        "vat_rate": 20,
        "total_amount": 120,
        "currency": "TRY",
        "payment_status": "pending",
    }
    expenses = SimpleNamespace(
        find_one=AsyncMock(side_effect=[existing, {**existing, "description": "Düzeltilmiş açıklama"}]),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    cash_flow = SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(expenses=expenses, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    await accounting.update_expense(
        "expense-a",
        {"description": "Düzeltilmiş açıklama"},
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _perm=None,
    )

    cash_flow.update_one.assert_not_awaited()
    cash_flow.delete_one.assert_awaited_once_with(
        {"tenant_id": "tenant-a", "reference_type": "expense", "reference_id": "expense-a"}
    )
