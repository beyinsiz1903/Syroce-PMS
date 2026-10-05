from types import SimpleNamespace

import pytest

from routers.departments import dashboards


class _Cursor:
    async def to_list(self, _limit):
        return [{"charge_category": "room", "total": 1250.0}]


class _Charges:
    def __init__(self):
        self.query = None

    def find(self, query):
        self.query = query
        return _Cursor()


@pytest.mark.asyncio
async def test_department_revenue_uses_business_day_and_charge_category(monkeypatch):
    charges = _Charges()
    monkeypatch.setattr(dashboards, "db", SimpleNamespace(folio_charges=charges))

    async def business_day(_db, _tenant_id):
        return {"business_date": "2026-10-02"}

    monkeypatch.setattr(dashboards, "ensure_business_date_initialized", business_day)
    result = await dashboards.get_revenue_by_department(
        current_user=SimpleNamespace(tenant_id="tenant-1")
    )

    assert charges.query["voided"] == {"$ne": True}
    assert charges.query["date"]["$gte"] == "2026-10-02T00:00:00+00:00"
    assert result["departments"][0]["key"] == "rooms"
    assert result["total_revenue"] == 1250.0
