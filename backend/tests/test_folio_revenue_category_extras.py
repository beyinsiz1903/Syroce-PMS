import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-tests")

from routers.finance import folio as folio_router


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection):
        return _Cursor(
            row
            for row in self.rows
            if row.get("tenant_id") == query["tenant_id"] and row.get("voided") is not True
        )


@pytest.mark.asyncio
async def test_category_report_includes_reservation_card_food_and_beverage(monkeypatch):
    fake_db = SimpleNamespace(
        folio_charges=_Collection(
            [
                {
                    "tenant_id": "tenant-1",
                    "business_date": "2026-09-23",
                    "charge_category": "room",
                    "amount": 1000,
                    "total": 1000,
                }
            ]
        ),
        extra_charges=_Collection(
            [
                {
                    "tenant_id": "tenant-1",
                    "business_date": "2026-09-23",
                    "category": "beverage",
                    "charge_amount": 100,
                    "quantity": 2,
                    "total": 200,
                },
                {
                    "tenant_id": "tenant-1",
                    "business_date": "2026-09-23",
                    "category": "food",
                    "charge_amount": 50,
                    "total": 50,
                    "voided": True,
                },
            ]
        ),
    )
    monkeypatch.setattr(folio_router, "db", fake_db)

    result = await folio_router.revenue_by_category.__wrapped__(
        date_from="2026-09-23",
        date_to="2026-09-23",
        current_user=SimpleNamespace(tenant_id="tenant-1"),
        _perm=None,
    )

    rows = {row["category"]: row for row in result["rows"]}
    assert rows["room"]["total"] == 1000
    assert rows["beverage"]["count"] == 1
    assert rows["beverage"]["subtotal"] == 200
    assert rows["beverage"]["net"] == 200
    assert rows["beverage"]["total"] == 200
    assert result["totals"]["total"] == 1200
