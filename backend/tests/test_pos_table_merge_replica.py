"""Real transactional table-merge acceptance; uses an explicit local replica set."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from domains.pms.pos_fnb import table_merge
from domains.pms.pos_fnb.analytics import snapshot
from tests.test_pos_final_consistency_replica import ctx, menu
from tests.test_pos_final_consistency_replica import db as db
from tests.test_pos_final_consistency_replica import service as service


async def checks(database, svc):
    await menu(database)
    await database.table_layouts.insert_many([
        {"id": f"table-{i}", "tenant_id": "t", "outlet_id": "bar", "table_number": str(i), "status": "available"}
        for i in (1, 2)
    ])
    ids = []
    for i in (1, 2):
        result = await svc.create_order(ctx(), "bar", str(i), [
            {"item_id": "tea", "quantity": i, "special_instructions": f"Masa {i} notu"},
        ])
        assert result.ok
        ids.append(result.data["order_id"])
    return ids


@pytest.mark.asyncio
async def test_merge_preserves_each_line_kitchen_history_and_exactly_one_later_sale(db, service, monkeypatch):
    source, target = await checks(db, service)
    before = {row["id"]: row async for row in db.pos_orders.find({})}
    source_kitchen = await db.kitchen_orders.find_one({"order_id": source})
    await db.kitchen_orders.update_one({"id": source_kitchen["id"]}, {"$set": {"status": "ready"}})
    await db.kitchen_orders.insert_one({"id": "served-history", "tenant_id": "t", "order_id": source, "status": "served"})
    enqueue_count = service._enqueue_kot.await_count

    result = await service.merge_order_tables(ctx(), source, target)
    assert result.ok and result.data["grand_total"] == 330
    merged = await db.pos_orders.find_one({"id": target})
    assert [row["line_id"] for row in merged["order_items"]] == [
        before[target]["order_items"][0]["line_id"], before[source]["order_items"][0]["line_id"],
    ]
    assert merged["order_items"][0] == before[target]["order_items"][0]
    assert merged["order_items"][1] == {**before[source]["order_items"][0], "merged_from_order_id": source}
    assert (await db.pos_orders.find_one({"id": source}))["status"] == "merged"
    assert (await db.table_layouts.find_one({"table_number": "1"}))["current_order_id"] is None
    assert (await db.table_layouts.find_one({"table_number": "2"}))["current_order_id"] == target
    moved = await db.kitchen_orders.find_one({"id": source_kitchen["id"]})
    assert moved["order_id"] == target and moved["status"] == "ready" and moved["table_number"] == "2"
    assert moved["merged_from_order_id"] == source
    assert (await db.kitchen_orders.find_one({"id": "served-history"}))["order_id"] == source
    assert service._enqueue_kot.await_count == enqueue_count
    assert await db.pos_transactions.count_documents({}) == await db.outbox_events.count_documents({}) == 0

    replay = await service.merge_order_tables(ctx(), source, target)
    assert replay.ok and replay.data["idempotent"]
    assert len((await db.pos_orders.find_one({"id": target}))["order_items"]) == 2
    assert not (await service.close_order(ctx(), source, "cash")).ok
    assert not (await service.void_order(ctx(), source, "Kaynak adisyon")).ok
    assert not (await service.add_order_items(ctx(), source, [{"item_id": "tea", "quantity": 1}])).ok
    monkeypatch.setattr("core.integrations.operational_gl_bridge.post_direct_pos_to_gl", AsyncMock())
    paid = await service.close_order(ctx(), target, "cash")
    assert paid.ok
    sale = await db.pos_transactions.find_one({"order_id": target})
    assert sale["total_amount"] == 330 and len(sale["order_items"]) == 2
    assert await db.pos_transactions.count_documents({}) == 1
    report = await snapshot(db, "t", "2026-10-18", "2026-10-18", "bar")
    assert report["sale_count"] == 1 and report["total_revenue"] == 330
    assert sum(line["quantity"] for line in report["lines"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"currency": "USD"}, {"outlet_id": "another"}, {"business_date": "2026-10-17"},
    {"payment_status": "partially_paid"}, {"status": "closed"}, {"booking_id": "guest"},
    {"order_type": "room_service"}, {"discount_amount": 5}, {"tip_amount": 10},
    {"stock_consumption_status": "consumed"}, {"grand_total": 1},
])
async def test_ineligible_checks_never_change_source_target_tables_or_kitchen(db, service, changes):
    source, target = await checks(db, service)
    await db.pos_orders.update_one({"id": target}, {"$set": changes})
    before = {name: await db[name].find({}).to_list(None) for name in ("pos_orders", "table_layouts", "kitchen_orders")}
    with pytest.raises(HTTPException) as rejected:
        await service.merge_order_tables(ctx(), source, target)
    assert rejected.value.status_code == 409
    for name, rows in before.items():
        assert await db[name].find({}).to_list(None) == rows


@pytest.mark.asyncio
async def test_merge_does_not_take_a_cross_tenant_target_or_an_already_settled_check(db, service):
    source, target = await checks(db, service)
    await db.pos_orders.update_one({"id": target}, {"$set": {"tenant_id": "elsewhere"}})
    with pytest.raises(HTTPException) as rejected:
        await service.merge_order_tables(ctx(), source, target)
    assert rejected.value.status_code == 404
    await db.pos_orders.update_one({"id": target}, {"$set": {"tenant_id": "t"}})
    await db.pos_transactions.insert_one({"tenant_id": "t", "order_id": target, "amount": 10, "status": "completed"})
    with pytest.raises(HTTPException) as rejected:
        await service.merge_order_tables(ctx(), source, target)
    assert rejected.value.status_code == 409
    assert (await db.pos_orders.find_one({"id": source}))["status"] == "pending"


@pytest.mark.asyncio
async def test_kitchen_write_failure_rolls_back_all_merge_writes(db, service, monkeypatch):
    source, target = await checks(db, service)
    original = type(db.kitchen_orders).update_many

    async def fail_kitchen(self, *args, **kwargs):
        if self.name == "kitchen_orders":
            raise RuntimeError("kitchen unavailable")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(type(db.kitchen_orders), "update_many", fail_kitchen)
    with pytest.raises(RuntimeError, match="kitchen unavailable"):
        await service.merge_order_tables(ctx(), source, target)
    assert (await db.pos_orders.find_one({"id": source}))["status"] == "pending"
    assert (await db.pos_orders.find_one({"id": target}))["grand_total"] == 220
    assert (await db.table_layouts.find_one({"table_number": "1"}))["status"] == "occupied"
    assert await db.kitchen_orders.count_documents({"order_id": source}) == 1


@pytest.mark.asyncio
async def test_parallel_merge_retry_does_not_duplicate_lines(db, service):
    source, target = await checks(db, service)
    results = await asyncio.gather(*[service.merge_order_tables(ctx(), source, target) for _ in range(2)])
    assert all(result.ok for result in results)
    assert sum(bool(result.data["idempotent"]) for result in results) == 1
    row = await db.pos_orders.find_one({"id": target})
    assert row["grand_total"] == 330 and len(row["order_items"]) == len(row["merged_checks"]) + 1 == 2


@pytest.mark.asyncio
async def test_source_payment_racing_merge_never_collects_the_source_twice(db, service, monkeypatch):
    source, target = await checks(db, service)
    monkeypatch.setattr("core.integrations.operational_gl_bridge.post_direct_pos_to_gl", AsyncMock())
    await asyncio.gather(service.merge_order_tables(ctx(), source, target), service.close_order(ctx(), source, "cash"), return_exceptions=True)
    source_row = await db.pos_orders.find_one({"id": source})
    target_row = await db.pos_orders.find_one({"id": target})
    if source_row["status"] == "merged":
        assert target_row["grand_total"] == 330
        assert await db.pos_transactions.count_documents({"order_id": source}) == 0
    else:
        assert source_row["status"] == "closed" and target_row["grand_total"] == 220
        assert await db.pos_transactions.count_documents({"order_id": source}) == 1


@pytest.mark.asyncio
async def test_merge_never_falls_back_to_nontransactional_writes(monkeypatch):
    async def standalone(**kwargs):
        raise OperationFailure("Transaction numbers are only allowed on a replica set")

    monkeypatch.setattr(table_merge, "with_resource_locks", standalone)
    with pytest.raises(HTTPException) as rejected:
        await table_merge.merge_open_checks(type("Database", (), {"client": None})(), "t", "u", "a", "b")
    assert rejected.value.status_code == 503
