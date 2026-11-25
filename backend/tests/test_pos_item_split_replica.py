"""Local replica-set acceptance for item check partition and rollback."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from domains.pms.pos_fnb.item_split import split_items
from tests.test_pos_final_consistency_replica import ctx, menu
from tests.test_pos_final_consistency_replica import db as db
from tests.test_pos_final_consistency_replica import service as service


async def setup(db, service):
    await menu(db)
    await db.table_layouts.insert_many([{'tenant_id': 't', 'id': f'table-{i}', 'outlet_id': 'bar', 'table_number': str(i), 'status': 'available'} for i in (1, 2, 3)])
    result = await service.create_order(ctx(), 'bar', '1', [{'item_id': 'tea', 'quantity': 3}])
    assert result.ok
    order = await db.pos_orders.find_one({'id': result.data['order_id']})
    return order, order['order_items'][0]['line_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['pending', 'preparing', 'ready', 'served'])
async def test_partial_units_keep_money_tax_kitchen_and_retry_exactly_once(db, service, monkeypatch, status):
    source, line = await setup(db, service)
    await db.kitchen_orders.update_many({}, {'$set': {'status': status}})
    kot_calls = service._enqueue_kot.await_count
    result = await split_items(db, 't', 'operator', source['id'], '2', {line: 1}, 'request-split-001')
    assert result['source_total'] == 220 and result['target_total'] == 110
    orders = await db.pos_orders.find({}).to_list(None)
    assert len(orders) == 2 and sum(o['tax_amount'] for o in orders) == 30
    assert sum(o['grand_total'] for o in orders) == source['grand_total'] == 330
    assert sum(o['order_items'][0]['quantity'] for o in orders) == 3
    tickets = await db.kitchen_orders.find({}).to_list(None)
    assert len(tickets) == 2 and sum(t['quantity'] for t in tickets) == 3
    assert {t['status'] for t in tickets} == {status}
    assert all(t['ordered_at'] == tickets[0]['ordered_at'] for t in tickets)
    assert service._enqueue_kot.await_count == kot_calls
    replay = await split_items(db, 't', 'operator', source['id'], '2', {line: 1}, 'request-split-001')
    assert replay['idempotent'] and replay['target_order_id'] == result['target_order_id']
    assert await db.pos_orders.count_documents({}) == 2
    assert await db.pos_transactions.count_documents({}) == await db.outbox_events.count_documents({}) == 0
    monkeypatch.setattr('core.integrations.operational_gl_bridge.post_direct_pos_to_gl', AsyncMock())
    for order in orders:
        paid = await service.close_order(ctx(), order['id'], 'cash')
        assert paid.ok
    sales = await db.pos_transactions.find({'status': 'completed'}).to_list(None)
    assert len(sales) == 2 and sum(s['total_amount'] for s in sales) == 330


@pytest.mark.asyncio
@pytest.mark.parametrize('quantities', ['empty', 'unknown', 'too_many', 'all', 'zero', 'fraction', 'bool'])
async def test_invalid_partition_leaves_orders_tables_kitchen_unchanged(db, service, quantities):
    source, line = await setup(db, service)
    values = {'empty': {}, 'unknown': {'missing': 1}, 'too_many': {line: 4}, 'all': {line: 3}, 'zero': {line: 0}, 'fraction': {line: 1.5}, 'bool': {line: True}}[quantities]
    before = {name: await db[name].find({}).to_list(None) for name in ('pos_orders', 'table_layouts', 'kitchen_orders')}
    with pytest.raises(HTTPException):
        await split_items(db, 't', 'u', source['id'], '2', values, 'invalid-split-001')
    for name, rows in before.items():
        assert await db[name].find({}).to_list(None) == rows


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'payment_status': 'paid'}, {'status': 'closed'}, {'booking_id': 'b'}, {'business_date': '2026-10-17'}, {'discount_amount': 1}, {'stock_consumption_status': 'consumed'}, {'grand_total': 1}])
async def test_unsafe_order_is_rejected(db, service, changes):
    source, line = await setup(db, service)
    await db.pos_orders.update_one({'id': source['id']}, {'$set': changes})
    with pytest.raises(HTTPException):
        await split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'unsafe-split-001')
    assert await db.pos_orders.count_documents({}) == 1
    assert (await db.table_layouts.find_one({'table_number': '2'}))['status'] == 'available'


@pytest.mark.asyncio
async def test_tenant_busy_target_and_kitchen_mismatch_rejected(db, service):
    source, line = await setup(db, service)
    with pytest.raises(HTTPException) as rejected:
        await split_items(db, 'other', 'u', source['id'], '2', {line: 1}, 'tenant-split-001')
    assert rejected.value.status_code == 404
    await db.table_layouts.update_one({'table_number': '2'}, {'$set': {'status': 'dirty'}})
    with pytest.raises(HTTPException):
        await split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'dirty-split-001')
    await db.table_layouts.update_one({'table_number': '2'}, {'$set': {'status': 'available'}})
    await db.kitchen_orders.update_many({}, {'$set': {'quantity': 99}})
    with pytest.raises(HTTPException):
        await split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'kitchen-split-001')
    assert await db.pos_orders.count_documents({}) == 1


@pytest.mark.asyncio
async def test_duplicate_parallel_request_creates_one_target_and_changed_retry_rejects(db, service):
    source, line = await setup(db, service)
    results = await asyncio.gather(*[split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'parallel-split-001') for _ in range(2)])
    assert results[0]['target_order_id'] == results[1]['target_order_id']
    assert await db.pos_orders.count_documents({}) == 2
    with pytest.raises(HTTPException):
        await split_items(db, 't', 'u', source['id'], '3', {line: 1}, 'parallel-split-001')


@pytest.mark.asyncio
async def test_failure_after_order_insert_rolls_back_every_collection(db, service, monkeypatch):
    source, line = await setup(db, service)
    before = {n: deepcopy(await db[n].find({}).to_list(None)) for n in ('pos_orders', 'table_layouts', 'kitchen_orders', 'pos_order_item_batches')}
    real = type(db.kitchen_orders).update_one

    async def fail(self, *args, **kwargs):
        if self.name == 'kitchen_orders':
            raise OperationFailure('synthetic write failure')
        return await real(self, *args, **kwargs)

    monkeypatch.setattr(type(db.kitchen_orders), 'update_one', fail)
    with pytest.raises(OperationFailure):
        await split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'rollback-split-001')
    for name, rows in before.items():
        assert await db[name].find({}).to_list(None) == rows


@pytest.mark.asyncio
async def test_whole_line_move_preserves_identity_and_can_merge_back_without_duplicate_kitchen(db, service):
    source, line = await setup(db, service)
    added = await service.add_order_items(ctx(), source['id'], [{'item_id': 'tea', 'quantity': 1}])
    assert added.ok
    result = await split_items(db, 't', 'u', source['id'], '2', {line: 3}, 'whole-line-split-001')
    target = await db.pos_orders.find_one({'id': result['target_order_id']})
    assert target['order_items'][0]['line_id'] == line
    assert await db.kitchen_orders.count_documents({}) == 2
    merged = await service.merge_order_tables(ctx(), result['target_order_id'], source['id'])
    assert merged.ok and merged.data['grand_total'] == 440
    assert sum(r['quantity'] for r in (await db.pos_orders.find_one({'id': source['id']}))['order_items']) == 4
    assert await db.kitchen_orders.count_documents({}) == 2


@pytest.mark.asyncio
async def test_separate_requests_competing_for_same_empty_table_only_one_claims_it(db, service):
    source, line = await setup(db, service)
    other = await service.create_order(ctx(), 'bar', '3', [{'item_id': 'tea', 'quantity': 2}])
    other_order = await db.pos_orders.find_one({'id': other.data['order_id']})
    results = await asyncio.gather(
        split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'race-table-split-001'),
        split_items(db, 't', 'u', other_order['id'], '2', {other_order['order_items'][0]['line_id']: 1}, 'race-table-split-002'),
        return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, HTTPException) for r in results) == 1
    orders = await db.pos_orders.find({}).to_list(None)
    assert len(orders) == 3 and sum(o['grand_total'] for o in orders) == 550
    assert sum([t['quantity'] async for t in db.kitchen_orders.find({})]) == 5


@pytest.mark.asyncio
async def test_partial_split_then_void_both_preserves_cancelled_kitchen_without_sale(db, service):
    source, line = await setup(db, service)
    result = await split_items(db, 't', 'u', source['id'], '2', {line: 1}, 'void-split-001')
    for order_id in (source['id'], result['target_order_id']):
        assert (await service.void_order(ctx(), order_id, 'Synthetic cancellation after split')).ok
    assert await db.pos_transactions.count_documents({}) == 0
    assert {t['status'] async for t in db.kitchen_orders.find({})} == {'cancelled'}
    assert sum([t['quantity'] async for t in db.kitchen_orders.find({})]) == 3
