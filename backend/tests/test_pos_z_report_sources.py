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
