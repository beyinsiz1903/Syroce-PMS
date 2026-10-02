from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb_router import fnb_reports


class _Cursor:
    async def to_list(self, _limit):
        return []


class _Collection:
    def __init__(self):
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        return _Cursor()


@pytest.mark.asyncio
async def test_fnb_dashboard_defaults_to_open_business_day(monkeypatch):
    charges = _Collection()
    orders = _Collection()
    monkeypatch.setattr(fnb_reports, "db", SimpleNamespace(folio_charges=charges, pos_orders=orders))

    async def current_user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    async def business_day(_db, tenant_id):
        assert tenant_id == "tenant-1"
        return {"business_date": "2026-10-02"}

    monkeypatch.setattr(fnb_reports, "get_current_user", current_user)
    monkeypatch.setattr(fnb_reports, "ensure_business_date_initialized", business_day)

    result = await fnb_reports.get_fnb_dashboard(credentials=None)

    assert result["date"] == "2026-10-02"
    assert charges.queries[0]["date"]["$gte"] == "2026-10-02T00:00:00"
