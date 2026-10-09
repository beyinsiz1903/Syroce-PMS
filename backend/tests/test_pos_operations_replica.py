"""Real Mongo transaction regressions. Run with POS_TEST_MONGO_URI to a LOCAL replica set."""
import asyncio
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from domains.pms.pos_extensions import pos_shift_close
from domains.pms.pos_fnb.checkout_benefits import quote_checkout
from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2, PosOrderStateChanged
from domains.pms.pos_fnb.stock_recovery import run_stock_job
from domains.pms.pos_router import pos_core


@pytest_asyncio.fixture
async def db():
    uri = os.getenv("POS_TEST_MONGO_URI")
    assert uri, "Set POS_TEST_MONGO_URI to an isolated local replica set; these tests must not silently skip"
    assert urlparse(uri).hostname in {"127.0.0.1", "localhost"}, "Never run against a production database"
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    database = client["pos_test_" + uuid.uuid4().hex]
    for collection in ("pos_orders", "pos_transactions", "kitchen_orders", "pos_order_item_batches",
                       "loyalty_pos_ledger", "pos_coupon_redemptions", "stock_consumptions", "pos_refund_locks"):
        await database.create_collection(collection)
    yield database
    await client.drop_database(database.name)
    client.close()


async def setup_checkout(db, *, order_id="order1", points=10):
    await db.hotel_settings.update_one({"tenant_id": "t1"}, {"$set": {"currency": "TRY"}}, upsert=True)
    await db.guests.update_one({"tenant_id": "t1", "id": "g1"}, {"$set": {"name": "Guest"}}, upsert=True)
    await db.loyalty_pos_accounts.update_one({"tenant_id": "t1", "guest_id": "g1"},
                                            {"$set": {"balance": 100}}, upsert=True)
    await db.pos_coupons.update_one({"tenant_id": "t1", "code": "SAVE"},
                                   {"$set": {"active": True, "discount_type": "percent",
                                             "discount_value": 10, "max_uses": 1, "used_count": 0}}, upsert=True)
    await db.pos_exchange_rates.insert_one({"id": "fx1", "tenant_id": "t1", "currency_code": "USD",
                                           "base_currency": "TRY", "rate_to_base": 40, "valid_at": "2026-10-09"})
    order = {"tenant_id": "t1", "id": order_id, "grand_total": 100, "tax_amount": 10,
             "order_items": [], "status": "pending", "payment_status": "unpaid"}
    await db.pos_orders.insert_one(dict(order))
    options = {"guest_id": "g1", "loyalty_points": points, "coupon_code": "SAVE", "currency_code": "USD"}
    quote = await quote_checkout(db, "t1", order, options)
    txn = {"id": "sale-" + order_id, "tenant_id": "t1", "order_id": order_id, "status": "completed",
           "checkout_quote": quote, "total_amount": quote["payable"], "payment_method": "cash",
           "created_at": "2026-10-09", "processed_by": "u1",
           "order_status_before_payment": "pending", "payment_status_before_payment": "unpaid",
           "order_snapshot": {"grand_total": 100, "order_items": []}}
    service = PosFnbServiceV2()
    service._db = db
    return service, order, txn


@pytest.mark.asyncio
async def test_checkout_coupon_loyalty_fx_and_refund_share_one_sale(db):
    service, order, txn = await setup_checkout(db)
    assert txn["checkout_quote"]["net"] == 89
    assert txn["checkout_quote"]["amount_foreign"] == 2.23
    await service._persist_txn_and_intent("t1", txn, order["id"], None)
    assert await db.pos_transactions.count_documents({}) == 1
    assert (await db.pos_coupons.find_one({}))["used_count"] == 1
    assert (await db.loyalty_pos_accounts.find_one({}))["balance"] == 179
    for index, amount in enumerate([40, 49]):
        await service._persist_refund_and_state(
            tenant_id="t1", order_id=order["id"], sale_id=txn["id"], paid=89, refund_amount=amount,
            refund_doc={"id": f"refund{index}", "tenant_id": "t1", "order_id": order["id"], "created_at": "2026-10-09"},
        )
    assert (await db.loyalty_pos_accounts.find_one({}))["balance"] == 100
    assert (await db.pos_orders.find_one({}))["stock_restore_status"] == "pending"
    assert await db.loyalty_pos_ledger.count_documents({}) == 3


@pytest.mark.asyncio
async def test_checkout_abort_rolls_back_coupon_points_sale(db):
    service, order, txn = await setup_checkout(db)
    txn["order_snapshot"]["grand_total"] = 999
    with pytest.raises(PosOrderStateChanged):
        await service._persist_txn_and_intent("t1", txn, order["id"], None)
    assert await db.pos_transactions.count_documents({}) == 0
    assert await db.loyalty_pos_ledger.count_documents({}) == 0
    assert (await db.loyalty_pos_accounts.find_one({}))["balance"] == 100
    assert (await db.pos_coupons.find_one({}))["used_count"] == 0


@pytest.mark.asyncio
async def test_concurrent_last_coupon_cannot_be_spent_twice(db):
    service, order, txn = await setup_checkout(db)
    second = {**order, "id": "order2"}
    await db.pos_orders.insert_one(dict(second))
    quote = await quote_checkout(db, "t1", second, txn["checkout_quote"])
    txn2 = {**txn, "id": "sale2", "order_id": "order2", "checkout_quote": quote}
    outcomes = await asyncio.gather(service._persist_txn_and_intent("t1", txn, order["id"], None),
                                    service._persist_txn_and_intent("t1", txn2, "order2", None), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in outcomes) == 1
    assert await db.pos_transactions.count_documents({}) == 1
    assert (await db.pos_coupons.find_one({}))["used_count"] == 1


@pytest.mark.asyncio
async def test_changed_fx_quote_is_rejected_without_mutations(db):
    service, order, txn = await setup_checkout(db)
    await db.pos_exchange_rates.update_one({"id": "fx1"}, {"$set": {"rate_to_base": 50}})
    with pytest.raises(HTTPException, match="409"):
        await service._persist_txn_and_intent("t1", txn, order["id"], None)
    assert await db.pos_transactions.count_documents({}) == 0
    with pytest.raises(HTTPException):
        await quote_checkout(db, "other-tenant", order, txn["checkout_quote"])


@pytest.mark.asyncio
async def test_coupon_bson_dates_and_non_try_hotel_currency(db):
    _, order, _ = await setup_checkout(db)
    await db.hotel_settings.update_one({"tenant_id": "t1"}, {"$set": {"currency": "EUR"}})
    await db.pos_coupons.update_one({}, {"$set": {"valid_from": datetime(2020, 1, 1), "valid_to": datetime(2040, 1, 1)}})
    quote = await quote_checkout(db, "t1", order, {"coupon_code": "SAVE"})
    assert quote["base_currency"] == "EUR"
    assert quote["currency_code"] == "EUR"
    assert quote["net"] == 90
    assert quote["fx_rounding_base"] == 0


@pytest.mark.asyncio
async def test_stock_failure_rolls_back_and_durable_retry_is_exactly_once(db):
    await db.pos_orders.insert_one({"id": "o1", "tenant_id": "t1", "payment_status": "paid",
                                    "stock_consumption_status": "pending",
                                    "order_items": [{"item_id": "m1", "quantity": 2}]})
    await db.recipes.insert_one({"tenant_id": "t1", "menu_item_id": "m1", "ingredients": [
        {"ingredient_id": "a", "quantity": 2}, {"ingredient_id": "b", "quantity": 3}]})
    await db.ingredients.insert_many([{"tenant_id": "t1", "id": "a", "current_stock": 10},
                                      {"tenant_id": "t1", "id": "b", "current_stock": 1}])
    with pytest.raises(HTTPException):
        await run_stock_job(db, "t1", "o1", "u1")
    assert (await db.ingredients.find_one({"id": "a"}))["current_stock"] == 10
    assert await db.stock_consumptions.count_documents({}) == 0
    assert (await db.pos_orders.find_one({}))["stock_consumption_status"] == "failed"
    await db.ingredients.update_one({"id": "b"}, {"$set": {"current_stock": 10}})
    await db.recipes.update_one({}, {"$set": {"ingredients": []}})  # Retry uses frozen BOM
    await asyncio.gather(*(run_stock_job(db, "t1", "o1", "u1") for _ in range(2)))
    assert (await db.ingredients.find_one({"id": "a"}))["current_stock"] == 6
    assert (await db.ingredients.find_one({"id": "b"}))["current_stock"] == 4
    assert await db.stock_consumptions.count_documents({}) == 2
    await db.pos_orders.update_one({}, {"$set": {"stock_restore_status": "pending", "payment_status": "refunded"}})
    await db.ingredients.delete_one({"id": "b"})
    with pytest.raises(HTTPException):
        await run_stock_job(db, "t1", "o1", "u1", restore=True)
    assert (await db.ingredients.find_one({"id": "a"}))["current_stock"] == 6
    assert (await db.pos_orders.find_one({}))["stock_restore_status"] == "failed"
    await db.ingredients.insert_one({"tenant_id": "t1", "id": "b", "current_stock": 4})
    await asyncio.gather(*(run_stock_job(db, "t1", "o1", "u1", restore=True) for _ in range(2)))
    assert (await db.ingredients.find_one({"id": "a"}))["current_stock"] == 10
    assert (await db.ingredients.find_one({"id": "b"}))["current_stock"] == 10


@pytest.mark.asyncio
async def test_z_and_daily_reports_include_over_5000_rows_without_legacy_duplicates(db, monkeypatch):
    rows = [{"id": f"tx{i}", "order_id": f"o{i}", "tenant_id": "t1", "transaction_date": "2026-10-09",
             "status": "completed", "payment_method": "cash", "total_amount": 10} for i in range(5007)]
    await db.pos_transactions.insert_many(rows)
    await db.pos_menu_transactions.insert_many([{**row, "id": "legacy" + row["id"]} for row in rows])
    monkeypatch.setattr(pos_core, "db", db)
    user = SimpleNamespace(tenant_id="t1")
    report = await pos_core.get_z_report(date="2026-10-09", outlet_id=None, current_user=user)
    assert report["net_sales"] == 50070
    assert report["transaction_count"] == 5007
    daily = await pos_core.get_pos_daily_summary(date="2026-10-09", outlet_id=None, current_user=user)
    assert daily["total_sales"] == 50070
    await db.pos_transactions.insert_one({
        "id": "refund", "order_id": "o0", "tenant_id": "t1", "transaction_date": "2026-10-09",
        "status": "refunded", "payment_type": "refund", "total_amount": -10, "payment_method": "cash",
    })
    report = await pos_core.get_z_report(date="2026-10-09", outlet_id=None, current_user=user)
    assert report["net_sales"] == 50060
    assert report["refunds"] == 10


@pytest.mark.asyncio
async def test_offline_create_and_append_replays_do_not_duplicate_kitchen_or_order(db):
    service = PosFnbServiceV2()
    service._db = db
    service._enqueue_kot = AsyncMock()
    service._broadcast_kitchen_queue = AsyncMock()
    ctx = SimpleNamespace(tenant_id="t1", actor_id="u1", actor_role="admin", actor_is_super_admin=False)
    await db.pos_menu_items.insert_one({"id": "tea", "tenant_id": "t1", "outlet_id": "bar",
                                        "price": 10, "tax_rate": .1, "available": True})
    create = PosFnbServiceV2.create_order.__wrapped__
    kwargs = {"outlet_id": "bar", "items": [{"item_id": "tea", "quantity": 1}], "idempotency_key": "offline-create"}
    results = await asyncio.gather(*(create(service, ctx, **kwargs) for _ in range(2)))
    assert all(result.ok for result in results)
    assert await db.pos_orders.count_documents({}) == 1
    assert await db.kitchen_orders.count_documents({}) == 1
    order = await db.pos_orders.find_one({})
    append = PosFnbServiceV2.add_order_items.__wrapped__
    await asyncio.gather(*(append(service, ctx, order["id"], [{"item_id": "tea", "quantity": 2}],
                                  idempotency_key="offline-append") for _ in range(2)))
    assert (await db.pos_orders.find_one({}))["grand_total"] == 33
    assert await db.kitchen_orders.count_documents({}) == 2
    assert await db.pos_order_item_batches.count_documents({}) == 1
    with pytest.raises(HTTPException, match="409"):
        await append(service, ctx, order["id"], [{"item_id": "tea", "quantity": 3}],
                     idempotency_key="offline-append")
    with pytest.raises(HTTPException, match="409"):
        await create(service, ctx, **{**kwargs, "outlet_id": "other"})


@pytest.mark.asyncio
async def test_full_refund_before_stock_attempt_never_consumes(db):
    await db.pos_orders.insert_one({"tenant_id": "t1", "id": "o1", "payment_status": "refunded",
                                    "stock_requirements": {"a": 5}, "stock_consumption_status": "pending"})
    await db.ingredients.insert_one({"tenant_id": "t1", "id": "a", "current_stock": 10})
    await run_stock_job(db, "t1", "o1", "u1")
    await run_stock_job(db, "t1", "o1", "u1", restore=True)
    assert (await db.ingredients.find_one({}))["current_stock"] == 10
    assert await db.stock_consumptions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_shift_cash_uses_all_sales_split_parts_and_refunds(db, monkeypatch):
    monkeypatch.setattr(pos_shift_close, "db", db)
    base = {"tenant_id": "t1", "outlet_id": "bar", "processed_by": "u1",
            "created_at": "2026-10-09T10:00:00+00:00", "status": "completed"}
    await db.pos_transactions.insert_many([
        {**base, "total_amount": 10, "payment_method": "cash"} for _ in range(5001)
    ] + [
        {**base, "payment_method": "mixed", "total_amount": 100,
         "payment_breakdown": [{"method": "cash", "amount": 40}, {"method": "card", "amount": 60}]},
        {**base, "payment_method": "cash", "status": "refunded", "total_amount": -10},
        {**base, "tenant_id": "other", "payment_method": "cash", "total_amount": 9999},
    ])
    result = await pos_shift_close._expected_cash_for_shift("t1", {
        "outlet_id": "bar", "cashier_id": "u1", "opened_at": datetime(2026, 10, 9, tzinfo=UTC),
        "closed_at": datetime(2026, 10, 10, tzinfo=UTC),
    })
    assert result == {"cash_sales": 50040, "tx_count": 5003}
