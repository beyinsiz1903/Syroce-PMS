from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_currency
from routers.finance import accounting


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.limits = []

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows


class _Collection:
    def __init__(self, cursor):
        self.cursor = cursor

    def find(self, *_args, **_kwargs):
        return self.cursor


@pytest.mark.asyncio
async def test_financial_summaries_never_silently_cap_source_rows(monkeypatch):
    invoice_cursor = _Cursor([])
    expense_cursor = _Cursor([])
    bank_cursor = _Cursor([])
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(
            accounting_invoices=_Collection(invoice_cursor),
            expenses=_Collection(expense_cursor),
            bank_accounts=_Collection(bank_cursor),
        ),
    )
    currency = AsyncMock(return_value=("TRY", "₺"))
    monkeypatch.setattr(accounting, "get_tenant_currency", currency)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", currency)
    user = SimpleNamespace(tenant_id="tenant-a")

    await accounting.get_profit_loss_report("2026-10-01", "2026-10-02", current_user=user, _perm=None)
    await accounting.get_vat_report("2026-10-01", "2026-10-02", current_user=user)
    await accounting.get_accounting_dashboard(current_user=user, _perm=None)

    assert invoice_cursor.limits == [None, None, None]
    assert expense_cursor.limits == [None, None, None]
    assert bank_cursor.limits == [None]
