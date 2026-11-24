"""Full refund must not leave an unstarted item actionable in KDS; LOCAL only."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import kitchen
from tests.test_pos_final_consistency_replica import ctx, menu
from tests.test_pos_final_consistency_replica import db as db
from tests.test_pos_final_consistency_replica import service as service


@pytest.mark.asyncio
async def test_full_refund_cancels_only_unstarted_tickets_atomically(service, db):
    await menu(db)
    result = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    oid = result.data['order_id']
    await db.kitchen_orders.insert_many([
        {'id': 'ready', 'tenant_id': 't', 'order_id': oid, 'status': 'ready'},
        {'id': 'served', 'tenant_id': 't', 'order_id': oid, 'status': 'served'},
        {'id': 'foreign', 'tenant_id': 'other', 'order_id': oid, 'status': 'pending'},
    ])
    await service.close_order(ctx(), oid, 'cash')
    result = await service.refund_order(ctx(), oid, None, 'Hazırlanmadan vazgeçildi', 'refund-kitchen')
    assert result.ok
    rows = [row async for row in db.kitchen_orders.find({'tenant_id': 't', 'order_id': oid})]
    assert not any(row['status'] == 'pending' for row in rows)
    assert {row['status'] for row in rows} == {'cancelled', 'ready', 'served'}
    assert (await db.kitchen_orders.find_one({'id': 'foreign'}))['status'] == 'pending'
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 1


@pytest.mark.asyncio
async def test_historical_refunded_pending_ticket_is_not_actionable_or_rewritten(db, monkeypatch):
    monkeypatch.setattr(kitchen, 'db', db)
    await db.pos_orders.insert_one({'id': 'old', 'tenant_id': 't', 'payment_status': 'refunded'})
    await db.kitchen_orders.insert_one({'id': 'ticket', 'tenant_id': 't', 'order_id': 'old', 'status': 'pending'})
    assert await kitchen._get_active_kitchen_orders('t') == []
    assert (await db.kitchen_orders.find_one({'id': 'ticket'}))['status'] == 'pending'
    with pytest.raises(HTTPException) as blocked:
        await kitchen.update_kitchen_order_status_v2('ticket', 'preparing', SimpleNamespace(tenant_id='t'))
    assert blocked.value.status_code == 409
    for action in (
        lambda: kitchen.complete_kitchen_order('ticket', SimpleNamespace(tenant_id='t')),
        lambda: kitchen.update_kitchen_order_status('ticket', 'preparing', SimpleNamespace(tenant_id='t')),
    ):
        with pytest.raises(HTTPException) as blocked:
            await action()
        assert blocked.value.status_code == 409


@pytest.mark.asyncio
async def test_partial_refund_keeps_kitchen_work_and_full_refund_warns_for_prepared_food(service, db):
    from domains.pms.pos_fnb.kitchen_refunds import actionable_kitchen_orders
    await menu(db)
    result = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    oid = result.data['order_id']
    await service.close_order(ctx(), oid, 'cash')
    assert (await service.refund_order(ctx(), oid, 10, 'Kısmi bedel iadesi', 'partial')).ok
    ticket = await db.kitchen_orders.find_one({'tenant_id': 't', 'order_id': oid})
    assert ticket['status'] == 'pending'
    await db.kitchen_orders.update_one({'id': ticket['id']}, {'$set': {'status': 'preparing'}})
    assert (await service.refund_order(ctx(), oid, None, 'Kalan bedel iadesi', 'remaining')).ok
    ticket = await db.kitchen_orders.find_one({'id': ticket['id']})
    assert ticket['status'] == 'preparing'
    visible = await actionable_kitchen_orders(db, 't', [ticket])
    assert visible[0]['financial_refund_status'] == 'full'


@pytest.mark.asyncio
async def test_kitchen_failure_rolls_back_refund_and_source_state(service, db, monkeypatch):
    await menu(db)
    oid = (await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])).data['order_id']
    await service.close_order(ctx(), oid, 'cash')
    original = type(db.kitchen_orders).update_many

    async def fail(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if self.name == 'kitchen_orders':
            raise RuntimeError('injected after kitchen cancellation')
        return result

    monkeypatch.setattr(type(db.kitchen_orders), 'update_many', fail)
    with pytest.raises(RuntimeError):
        await service.refund_order(ctx(), oid, None, 'Atomik hata denemesi', 'rollback')
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 0
    assert (await db.pos_orders.find_one({'id': oid}))['payment_status'] == 'paid'
    assert (await db.kitchen_orders.find_one({'order_id': oid}))['status'] == 'pending'
    sale = await db.pos_transactions.find_one({'order_id': oid})
    assert not sale.get('refunded_amount')
