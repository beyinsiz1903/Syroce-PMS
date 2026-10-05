from types import SimpleNamespace

import pytest

from domains.pms.dashboard_router import dashboard_core


class _Cursor:
    def __init__(self):
        self.limit = "unset"

    async def to_list(self, limit):
        self.limit = limit
        return []


class _Collection:
    def __init__(self):
        self.query = None
        self.cursor = _Cursor()

    def find(self, query):
        self.query = query
        return self.cursor


@pytest.mark.asyncio
async def test_revenue_expense_chart_has_complete_non_void_ledger_scope(monkeypatch):
    charges = _Collection()
    expenses = _Collection()
    monkeypatch.setattr(
        dashboard_core,
        "db",
        SimpleNamespace(folio_charges=charges, expenses=expenses),
    )

    await dashboard_core.get_revenue_expense_chart(
        period="30days", current_user=SimpleNamespace(tenant_id="tenant-1")
    )

    assert charges.query["voided"] == {"$ne": True}
    assert "$lt" in charges.query["date"]
    assert charges.cursor.limit is None
    assert expenses.cursor.limit is None
