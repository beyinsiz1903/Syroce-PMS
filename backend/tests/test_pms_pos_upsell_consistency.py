from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    orders = _PosOrders([{"outlet_name": "Restoran", "total_amount": 125, "currency": "TRY"}])
    monkeypatch.setattr(pos_inventory, "db", SimpleNamespace(pos_orders=orders))

    async def _user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    monkeypatch.setattr(pos_inventory, "get_current_user", _user)
    result = await pos_inventory.get_outlet_sales_breakdown("2026-09-24", "2026-09-24", object())

    assert result["total_sales"] == 125
    assert orders.query["status"] == {"$nin": ["cancelled", "voided"]}
    assert orders.query["$or"][0] == {"business_date": {"$gte": "2026-09-24", "$lt": "2026-09-25"}}
    assert orders.query["$or"][1]["created_at"]["$lt"] == "2026-09-25"


@pytest.mark.asyncio
async def test_pos_does_not_sum_currencies_or_invent_legacy_currency(monkeypatch):
    orders = _PosOrders([{"total_amount": 100, "currency": "USD"}, {"total_amount": 200, "currency": "TRY"}, {"total_amount": 30}])
    monkeypatch.setattr(pos_inventory, "db", SimpleNamespace(pos_orders=orders))
    monkeypatch.setattr(pos_inventory, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t")))
    result = await pos_inventory.get_outlet_sales_breakdown("2026-10-26", "2026-10-26", object())
    assert result["total_sales"] is None
    assert result["total_sales_by_currency"] == {"USD": 100, "TRY": 200, "UNKNOWN": 30}
    assert result["orders_by_currency"] == {"USD": 1, "TRY": 1, "UNKNOWN": 1}
    assert result["outlets"]["Bilinmeyen"]["avg_ticket"] is None


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
async def test_accepted_upsell_delegates_to_atomic_source_handoff(monkeypatch):
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

    handoff = AsyncMock(return_value={"status": "accepted", "folio_charge_id": "canonical"})
    monkeypatch.setattr("core.guest_service_folio.accept_upsell", handoff)
    user = SimpleNamespace(id="manager", role="admin", tenant_id="tenant-1", email="resepsiyon@example.com", is_super_admin=False)
    result = await upsell.update_upsell_offer("offer-1", "accepted", user, None)

    assert result["status"] == "accepted"
    handoff.assert_awaited_once_with(fake_db, "tenant-1", "offer-1", "manager")
    assert charges.inserted is None and offers.updated is None
