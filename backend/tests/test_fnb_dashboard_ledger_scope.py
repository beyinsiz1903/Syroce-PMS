from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb_router import fnb_reports


class _Cursor:
    def __init__(self, rows, limits):
        self.rows = rows
        self.limits = limits

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows


class _Collection:
    def __init__(self):
        self.queries = []
        self.limits = []

    def find(self, query):
        self.queries.append(query)
        return _Cursor([], self.limits)


@pytest.mark.asyncio
async def test_fnb_dashboard_uses_non_overlapping_non_void_ledger_scope(monkeypatch):
    charges = _Collection()
    orders = _Collection()
    monkeypatch.setattr(fnb_reports, "db", SimpleNamespace(folio_charges=charges, pos_orders=orders))

    async def current_user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    monkeypatch.setattr(fnb_reports, "get_current_user", current_user)

    await fnb_reports.get_fnb_dashboard(date="2026-10-02", credentials=None)

    current, previous = charges.queries
    assert current["voided"] == {"$ne": True}
    assert current["date"]["$lt"] == "2026-10-03T00:00:00"
    assert previous["date"]["$lt"] == "2026-10-02T00:00:00"
    assert orders.queries[0]["created_at"]["$lt"] == "2026-10-03T00:00:00"
    assert charges.limits == [None, None]
    assert orders.limits == [None]
