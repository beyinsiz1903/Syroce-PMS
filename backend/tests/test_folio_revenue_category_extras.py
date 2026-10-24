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


class _DB(SimpleNamespace):
    def __init__(self, **values):
        super().__init__(**{key: _Collection([]) for key in ("pos_transactions", "pos_menu_transactions", "transactions", "rooms", "room_types", "folios", "bookings")}, **values)


@pytest.mark.asyncio
async def test_category_report_includes_reservation_card_food_and_beverage(monkeypatch):
    fake_db = _DB(
        folio_charges=_Collection(
            [
                {
                    "tenant_id": "tenant-1",
                    "business_date": "2026-09-23",
                    "charge_category": "room",
                    "amount": 1000,
                    "total": 1000,
                    "currency": "TRY",
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
                    "currency": "EUR",
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
        pos_orders=_Collection([]),
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
    assert rows["beverage"]["subtotal"] is None
    assert rows["beverage"]["net"] is None  # missing tax evidence is not zero tax
    assert rows["beverage"]["total"] == 200
    assert result["totals"]["total"] is None  # never add EUR and TRY
    assert rows["room"]["by_currency"]["TRY"]["total"] == 1000
    assert rows["beverage"]["by_currency"]["EUR"]["total"] == 200
    assert {code: values["total"] for code, values in result["totals_by_currency"].items()} == {"TRY": 1000, "EUR": 200}
    assert result["reconciliation"]["tax_unknown_count"] == 2


@pytest.mark.asyncio
async def test_category_report_includes_direct_pos_once_and_deduplicates_posted_order(monkeypatch):
    fake_db = _DB(
        folio_charges=_Collection(
            [
                {
                    "tenant_id": "tenant-1",
                    "business_date": "2026-09-23",
                    "charge_category": "fnb",
                    "amount": 250,
                    "total": 250,
                    "currency": "TRY",
                    "source_pos_order_id": "posted-order",
                }
            ]
        ),
        extra_charges=_Collection([]),
        pos_orders=_Collection(
            [
                {
                    "tenant_id": "tenant-1",
                    "id": "posted-order",
                    "business_date": "2026-09-23",
                    "total_amount": 250,
                    "currency": "TRY",
                    "status": "paid",
                },
                {
                    "tenant_id": "tenant-1",
                    "id": "direct-order",
                    "business_date": "2026-09-23",
                    "total_amount": 400,
                    "currency": "TRY",
                    "status": "paid",
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

    fnb = next(row for row in result["rows"] if row["category"] == "fnb")
    assert fnb["count"] == 2
    assert fnb["total"] == 650
    assert result["totals_by_currency"]["TRY"]["total"] == 650
