from types import SimpleNamespace

import pytest

from domains.pms.dashboard_router import dashboard_core


class _Cursor:
    async def to_list(self, _limit):
        return []


class _Collection:
    def __init__(self):
        self.query = None

    def find(self, query):
        self.query = query
        return _Cursor()


@pytest.mark.asyncio
async def test_monthly_profitability_uses_non_void_bounded_ledger_window(monkeypatch):
    charges = _Collection()
    expenses = _Collection()
    monkeypatch.setattr(
        dashboard_core,
        "db",
        SimpleNamespace(folio_charges=charges, expenses=expenses),
    )

    await dashboard_core.get_monthly_profitability(
        months=1, current_user=SimpleNamespace(tenant_id="tenant-1")
    )

    assert charges.query["voided"] == {"$ne": True}
    assert "$gte" in charges.query["date"] and "$lt" in charges.query["date"]
    assert charges.query["date"] == expenses.query["date"]
