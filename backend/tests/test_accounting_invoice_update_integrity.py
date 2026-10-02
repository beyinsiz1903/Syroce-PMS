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
    invoice = {"id": "invoice-a", "tenant_id": "tenant-a", "status": "paid"}
    invoices = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(return_value=invoice),
    )
    monkeypatch.setattr(accounting, "db", SimpleNamespace(accounting_invoices=invoices))
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
