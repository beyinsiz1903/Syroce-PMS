from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.finance import accounting


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "record_name", "record_id", "updates"),
    [
        (accounting.update_supplier, "suppliers", "supplier-a", {"tenant_id": "other-tenant"}),
        (accounting.update_supplier, "suppliers", "supplier-a", {"account_balance": 1}),
        (accounting.update_bank_account, "bank_accounts", "bank-a", {"balance": 1}),
        (accounting.update_bank_account, "bank_accounts", "bank-a", {"currency": "EUR"}),
    ],
)
async def test_master_data_updates_reject_protected_financial_fields(monkeypatch, endpoint, record_name, record_id, updates):
    collection = SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock())
    monkeypatch.setattr(accounting, "db", SimpleNamespace(**{record_name: collection}))

    with pytest.raises(HTTPException) as exc:
        await endpoint(record_id, updates, current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None)

    assert exc.value.status_code == 422
    collection.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplier_update_uses_tenant_scoped_whitelist(monkeypatch):
    suppliers = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(return_value={"id": "supplier-a", "name": "Yeni Tedarikçi"}),
    )
    monkeypatch.setattr(accounting, "db", SimpleNamespace(suppliers=suppliers))

    result = await accounting.update_supplier(
        "supplier-a", {"name": "Yeni Tedarikçi"}, current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None
    )

    assert result["name"] == "Yeni Tedarikçi"
    assert suppliers.update_one.await_args.args == (
        {"id": "supplier-a", "tenant_id": "tenant-a"}, {"$set": {"name": "Yeni Tedarikçi"}}
    )


@pytest.mark.asyncio
async def test_bank_account_update_rejects_missing_record(monkeypatch):
    bank_accounts = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)),
        find_one=AsyncMock(),
    )
    monkeypatch.setattr(accounting, "db", SimpleNamespace(bank_accounts=bank_accounts))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        await accounting.update_bank_account(
            "bank-a", {"is_active": False}, current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None
        )

    assert exc.value.status_code == 404
    bank_accounts.find_one.assert_not_awaited()
