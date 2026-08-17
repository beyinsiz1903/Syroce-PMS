from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import enterprise_router


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


class _TransactionCollection:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None

    def find(self, query):
        self.last_query = query
        return _Cursor(self.rows)


def test_pos_closure_summary_uses_finalized_transactions_and_deduplicates_sources():
    summary = enterprise_router._summarize_pos_closure_transactions(
        [
            {"id": "cash-1", "status": "completed", "total_amount": "125.50", "payment_method": "cash", "_closure_source": "pos_transactions"},
            {"id": "cash-1", "status": "completed", "total_amount": "125.50", "payment_method": "cash", "_closure_source": "pos_menu_transactions"},
            {"id": "card-1", "status": "paid", "amount": 74.5, "payment_method": "credit_card", "_closure_source": "pos_transactions"},
            {"id": "room-1", "status": "settled", "total_amount": 20, "payment_method": "room_charge", "_closure_source": "pos_menu_transactions"},
            {"id": "open-1", "status": "open", "total_amount": 999, "payment_method": "cash", "_closure_source": "pos_transactions"},
        ]
    )

    assert summary == {
        "total_sales": 220.0,
        "cash_sales": 125.5,
        "card_sales": 74.5,
        "other_sales": 20.0,
        "transaction_count": 3,
    }


@pytest.mark.parametrize("value", ["NaN", "Infinity", -1, "not-money"])
def test_pos_closure_rejects_invalid_monetary_values(value):
    with pytest.raises(ValueError, match="INVALID_POS_MONETARY_VALUE"):
        enterprise_router._summarize_pos_closure_transactions([{"id": "bad", "status": "completed", "total_amount": value}])


@pytest.mark.asyncio
async def test_pos_closure_without_finalized_transactions_fails_closed(monkeypatch):
    closures = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock())
    fake_db = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"business_date": "2026-08-17"})),
        pos_transactions=_TransactionCollection([]),
        pos_menu_transactions=_TransactionCollection([]),
        pos_closures=closures,
    )
    monkeypatch.setattr(enterprise_router, "db", fake_db)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-a")

    with pytest.raises(HTTPException) as exc:
        await enterprise_router.create_pos_closure(current_user=user, _perm=True)

    assert exc.value.status_code == 409
    closures.insert_one.assert_not_awaited()


def test_pos_closure_rejects_transactions_without_durable_identity():
    with pytest.raises(ValueError, match="MISSING_POS_TRANSACTION_ID"):
        enterprise_router._summarize_pos_closure_transactions([{"status": "completed", "total_amount": 10, "payment_method": "cash"}])


@pytest.mark.asyncio
async def test_pos_closure_persists_real_totals_once_and_replays(monkeypatch):
    stored = None

    async def insert_one(document):
        nonlocal stored
        stored = dict(document)

    async def find_one(query, _projection=None):
        if stored and query.get("closure_date") == stored["closure_date"]:
            return {key: value for key, value in stored.items() if key != "_id"}
        return None

    closures = SimpleNamespace(find_one=AsyncMock(side_effect=find_one), insert_one=AsyncMock(side_effect=insert_one))
    fake_db = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"business_date": "2026-08-17"})),
        pos_transactions=_TransactionCollection([{"id": "txn-1", "status": "completed", "total_amount": "300.25", "payment_method": "card"}]),
        pos_menu_transactions=_TransactionCollection([{"id": "txn-2", "status": "completed", "total_amount": "99.75", "payment_method": "cash"}]),
        pos_closures=closures,
    )
    monkeypatch.setattr(enterprise_router, "db", fake_db)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-a")

    first = await enterprise_router.create_pos_closure(current_user=user, _perm=True)
    replay = await enterprise_router.create_pos_closure(current_user=user, _perm=True)

    assert first["total_sales"] == 400.0
    assert first["transaction_count"] == 2
    assert first["replayed"] is False
    assert replay["id"] == first["id"]
    assert replay["replayed"] is True
    closures.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_pos_closure_does_not_accept_legacy_fixed_total_as_replay(monkeypatch):
    closures = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "legacy",
                "tenant_id": "tenant-a",
                "closure_date": "2026-08-17",
                "total_sales": 5420.5,
            }
        ),
        insert_one=AsyncMock(),
    )
    fake_db = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"business_date": "2026-08-17"})),
        pos_closures=closures,
    )
    monkeypatch.setattr(enterprise_router, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        await enterprise_router.create_pos_closure(
            current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"),
            _perm=True,
        )

    assert exc.value.status_code == 409
    closures.insert_one.assert_not_awaited()
