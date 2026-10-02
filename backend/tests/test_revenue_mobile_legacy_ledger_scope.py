from types import SimpleNamespace

import pytest

from domains.revenue.pricing_router import revenue_mobile


class _Cursor:
    async def to_list(self, _limit):
        return []


class _Charges:
    def __init__(self):
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        return _Cursor()


@pytest.mark.asyncio
async def test_total_revenue_uses_the_shared_non_void_ledger_scope(monkeypatch):
    charges = _Charges()
    monkeypatch.setattr(revenue_mobile, "db", SimpleNamespace(folio_charges=charges))

    async def current_user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    monkeypatch.setattr(revenue_mobile, "get_current_user", current_user)

    await revenue_mobile.get_total_revenue_mobile(
        start_date="2026-09-01", end_date="2026-09-30", credentials=None
    )

    assert all(query["voided"] == {"$ne": True} for query in charges.queries)
