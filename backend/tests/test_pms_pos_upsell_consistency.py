from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.guest.experience_router import upsell
from domains.pms.pos_router import pos_core
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
async def test_pos_sales_uses_same_business_period_and_finalized_ledger_as_z(monkeypatch):
    database = SimpleNamespace()
    monkeypatch.setattr(pos_inventory, "db", database)
    query = AsyncMock(return_value=[
        {"outlet_name": "Restoran", "status": "completed", "total_amount": 132, "currency": "TRY"},
        {"outlet_name": "Restoran", "status": "merged", "total_amount": 80, "currency": "TRY"},
        {"outlet_name": "Restoran", "status": "pending", "total_amount": 25, "currency": "TRY"},
    ])
    monkeypatch.setattr(pos_core, "_query_pos_transactions", query)
    monkeypatch.setattr(pos_inventory, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))

    async def _user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    monkeypatch.setattr(pos_inventory, "get_current_user", _user)
    result = await pos_inventory.get_outlet_sales_breakdown("2026-09-24", "2026-09-24", object())

    assert result["total_sales"] == 132
    assert result["orders_by_currency"] == {"TRY": 1}
    query.assert_awaited_once_with("tenant-1", limit=None, start_date="2026-09-24", end_date="2026-09-24", database=database)


@pytest.mark.asyncio
async def test_pos_does_not_sum_currencies_or_invent_legacy_currency(monkeypatch):
    monkeypatch.setattr(pos_inventory, "db", SimpleNamespace())
    monkeypatch.setattr(pos_inventory, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(pos_core, "_query_pos_transactions", AsyncMock(return_value=[
        {"status": "completed", "total_amount": 100, "currency": "USD"},
        {"status": "completed", "total_amount": 200, "currency": "TRY"},
        {"status": "completed", "total_amount": 30},
    ]))
    monkeypatch.setattr(pos_inventory, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t")))
    result = await pos_inventory.get_outlet_sales_breakdown("2026-10-26", "2026-10-26", object())
    assert result["total_sales"] is None
    assert result["total_sales_by_currency"] == {"USD": 100, "TRY": 200, "UNKNOWN": 30}
    assert result["orders_by_currency"] == {"USD": 1, "TRY": 1, "UNKNOWN": 1}
    assert result["outlets"]["Bilinmeyen"]["avg_ticket"] is None


@pytest.mark.asyncio
async def test_pos_summary_refund_reduces_sales_without_becoming_another_order(monkeypatch):
    from domains.pms.pos_fnb import reporting
    rows = [
        {"status": "completed", "total_amount": 110, "tip_amount": 10, "currency": "TRY"},
        {"status": "refunded", "total_amount": -22, "tip_amount": -2, "currency": "TRY"},
    ]
    monkeypatch.setattr(pos_inventory, "db", SimpleNamespace())
    monkeypatch.setattr(pos_inventory, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(pos_inventory, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t")))
    monkeypatch.setattr(pos_core, "_query_pos_transactions", AsyncMock(return_value=rows))
    monkeypatch.setattr(reporting, "enrich_refunds", AsyncMock(return_value=(rows, [])))
    result = await pos_inventory.get_outlet_sales_breakdown("2026-11-10", "2026-11-10", object())
    assert result["total_sales_by_currency"] == {"TRY": 80}
    assert result["orders_by_currency"] == {"TRY": 1}
    assert result["outlets"]["Bilinmeyen"]["orders"] == 1
    assert rows[0]["total_amount"] == 110 and rows[1]["total_amount"] == -22


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
