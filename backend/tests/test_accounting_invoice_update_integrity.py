from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.finance import accounting


@pytest.mark.asyncio
async def test_invoice_update_rejects_financial_and_tenant_tampering(monkeypatch):
    monkeypatch.setattr(accounting, "db", SimpleNamespace())

    with pytest.raises(HTTPException) as exc:
        await accounting.update_accounting_invoice(
            "invoice-a",
            {"tenant_id": "other-tenant", "total": 1, "currency": "EUR"},
            current_user=SimpleNamespace(tenant_id="tenant-a"),
            _perm=None,
        )

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_invoice_update_accepts_valid_status_and_stamps_payment_date(monkeypatch):
    invoice = {
        "id": "invoice-a",
        "tenant_id": "tenant-a",
        "invoice_number": "INV-1",
        "status": "paid",
        "total": 120,
        "currency": "TRY",
    }
    invoices = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(return_value=invoice),
    )
    cash_flow = SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(accounting_invoices=invoices, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    result = await accounting.update_accounting_invoice(
        "invoice-a",
        {"status": "paid"},
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _perm=None,
    )

    patch = invoices.update_one.await_args.args[1]["$set"]
    assert patch["status"] == "paid"
    assert patch["payment_date"]
    assert result == invoice
    assert cash_flow.update_one.await_args.kwargs["upsert"] is True
    cash_flow.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_unpaid_invoice_update_removes_legacy_cash_flow_income(monkeypatch):
    invoice = {"id": "invoice-a", "tenant_id": "tenant-a", "status": "pending"}
    invoices = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(return_value=invoice),
    )
    cash_flow = SimpleNamespace(update_one=AsyncMock(), delete_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(accounting_invoices=invoices, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    await accounting.update_accounting_invoice(
        "invoice-a",
        {"status": "pending"},
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _perm=None,
    )

    cash_flow.update_one.assert_not_awaited()
    cash_flow.delete_one.assert_awaited_once_with(
        {"tenant_id": "tenant-a", "reference_type": "invoice", "reference_id": "invoice-a"}
    )
