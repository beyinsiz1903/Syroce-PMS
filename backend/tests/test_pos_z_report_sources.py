from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.pos_router import pos_core


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return [dict(row) for row in self.rows[:limit]]


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, _projection):
        self.queries.append(query)
        return _Cursor(self.rows)


@pytest.mark.asyncio
async def test_z_report_merges_waiter_orders_and_legacy_transactions(monkeypatch):
    orders = _Collection(
        [
            {
                "id": "order-1",
                "business_date": "2026-09-03",
                "status": "completed",
                "payment_method": "cash",
                "total_amount": 132,
                "tax_amount": 12,
                "order_items": [{"category": "food", "total_price": 120}],
                "created_at": "2026-09-08T18:30:00+00:00",
            },
            {
                "id": "void-1",
                "business_date": "2026-09-03",
                "status": "cancelled",
                "payment_method": "cash",
                "total_amount": 20,
                "tax_amount": 2,
                "created_at": "2026-09-08T18:20:00+00:00",
            },
            {
                "id": "open-1",
                "business_date": "2026-09-03",
                "status": "pending",
                "payment_method": None,
                "total_amount": 75,
                "tax_amount": 7,
                "created_at": "2026-09-08T18:25:00+00:00",
            },
        ]
    )
    menu_transactions = _Collection(
        [
            {
                "id": "order-1",
                "transaction_date": "2026-09-03",
                "status": "completed",
                "total_amount": 132,
                "tax_amount": 12,
            }
        ]
    )
    legacy_transactions = _Collection(
        [
            {
                "id": "legacy-1",
                "transaction_date": "2026-09-03",
                "status": "completed",
                "payment_method": "card",
                "total_amount": 50,
                "tax_amount": 9,
                "items": [{"category": "beverage", "price": 25, "quantity": 2}],
                "created_at": "2026-09-08T18:10:00+00:00",
            }
        ]
    )
    fake_db = SimpleNamespace(
        pos_orders=orders,
        pos_menu_transactions=menu_transactions,
        transactions=legacy_transactions,
        tenant_settings=SimpleNamespace(
            find_one=AsyncMock(return_value={"business_date": "2026-09-03"})
        ),
    )
    monkeypatch.setattr(pos_core, "db", fake_db)

    report = await pos_core.get_z_report(
        date=None,
        outlet_id=None,
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )

    assert report["report_date"] == "2026-09-03"
    assert report["gross_sales"] == 182
    assert report["net_sales"] == 182
    assert report["tax_total"] == 21
    assert report["transaction_count"] == 2
    assert report["void_count"] == 1
    assert report["refunds"] == 20
    assert report["payment_methods"] == {"cash": 132, "card": 50}
    assert report["category_sales"] == {"food": 120, "beverage": 50}
    assert orders.queries[0]["business_date"] == "2026-09-03"
    assert menu_transactions.queries[0]["transaction_date"] == "2026-09-03"
    assert legacy_transactions.queries[0]["transaction_date"] == "2026-09-03"

    voids = await pos_core.get_void_transactions(
        date="2026-09-03",
        start_date=None,
        end_date=None,
        outlet_id=None,
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )
    assert voids["count"] == 1
    assert voids["void_transactions"][0]["id"] == "void-1"


@pytest.mark.asyncio
async def test_daily_summary_uses_selected_date_outlet_and_excludes_voids(monkeypatch):
    query = AsyncMock(
        return_value=[
            {
                "id": "paid-1",
                "status": "completed",
                "total_amount": 120.50,
                "order_items": [
                    {"item_name": "Türk Kahvesi", "quantity": 2, "unit_price": 30},
                    {"item_name": "Tost", "quantity": 1, "total_price": 60.50},
                ],
            },
            {
                "id": "paid-2",
                "status": "closed",
                "total_amount": 79.50,
                "items": [
                    {"name": "Türk Kahvesi", "quantity": 1, "price": 30},
                    {"name": "Çay", "quantity": 1, "total": 49.50},
                ],
            },
            {"id": "void-1", "status": "cancelled", "total_amount": 50},
            {"id": "open-1", "status": "pending", "total_amount": 80},
        ]
    )
    monkeypatch.setattr(pos_core, "_query_pos_transactions", query)

    result = await pos_core.get_pos_daily_summary(
        date="2026-09-27",
        outlet_id="outlet-a",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )

    query.assert_awaited_once_with(
        "tenant-a",
        limit=5000,
        outlet_id="outlet-a",
        date="2026-09-27",
    )
    assert result == {
        "date": "2026-09-27",
        "outlet_id": "outlet-a",
        "total_sales": 200.0,
        "transaction_count": 2,
        "average_transaction": 100.0,
        "top_items": [
            {"name": "Türk Kahvesi", "quantity": 3, "revenue": 90.0},
            {"name": "Tost", "quantity": 1, "revenue": 60.5},
            {"name": "Çay", "quantity": 1, "revenue": 49.5},
        ],
    }
