from types import SimpleNamespace

import pytest

from domains.guest.experience_router import upsell
from domains.revenue.analytics_router import pos_inventory


class _AsyncRows:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _PosOrders:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def find(self, query):
        self.query = query
        return _AsyncRows(self.rows)


@pytest.mark.asyncio
async def test_pos_sales_uses_business_date_and_excludes_cancelled(monkeypatch):
    orders = _PosOrders([{"outlet_name": "Restoran", "total_amount": 125}])
    monkeypatch.setattr(pos_inventory, "db", SimpleNamespace(pos_orders=orders))

    async def _user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    monkeypatch.setattr(pos_inventory, "get_current_user", _user)
    result = await pos_inventory.get_outlet_sales_breakdown("2026-09-24", "2026-09-24", object())

    assert result["total_sales"] == 125
    assert orders.query["status"] == {"$nin": ["cancelled", "voided"]}
    assert orders.query["$or"][0] == {"business_date": {"$gte": "2026-09-24", "$lt": "2026-09-25"}}
    assert orders.query["$or"][1]["created_at"]["$lt"] == "2026-09-25"


class _Collection:
    def __init__(self, find_one_result=None):
        self.find_one_result = find_one_result
        self.inserted = None
        self.updated = None

    async def find_one(self, *_args, **_kwargs):
        return self.find_one_result

    async def insert_one(self, row):
        self.inserted = row

    async def update_one(self, query, update):
        self.updated = (query, update)


@pytest.mark.asyncio
async def test_accepted_upsell_posts_complete_charge_to_open_folio(monkeypatch):
    offers = _Collection({
        "id": "offer-1",
        "tenant_id": "tenant-1",
        "booking_id": "booking-1",
        "status": "pending",
        "price": 240,
        "target_item": "Geç çıkış",
    })
    charges = _Collection(None)
    folios = _Collection({"id": "folio-1"})
    fake_db = SimpleNamespace(upsell_offers=offers, folio_charges=charges, folios=folios)
    monkeypatch.setattr(upsell, "db", fake_db)

    async def _stamp(_db, _tenant_id, row):
        row["business_date"] = "2026-09-24"

    async def _balance(_folio_id, _tenant_id):
        return 240

    monkeypatch.setattr(upsell, "stamp_open_business_date", _stamp)
    monkeypatch.setattr(upsell, "calculate_folio_balance", _balance)
    monkeypatch.setattr(upsell, "invalidate_financial_report_caches", lambda _tenant_id: None)

    user = SimpleNamespace(tenant_id="tenant-1", email="resepsiyon@example.com")
    result = await upsell.update_upsell_offer("offer-1", "accepted", user, None)

    assert result["status"] == "accepted"
    assert charges.inserted["folio_id"] == "folio-1"
    assert charges.inserted["charge_category"] == "other"
    assert charges.inserted["total"] == 240
    assert charges.inserted["voided"] is False
    assert folios.updated[1]["$set"]["balance"] == 240
    assert offers.updated[0] == {"id": "offer-1", "tenant_id": "tenant-1"}
