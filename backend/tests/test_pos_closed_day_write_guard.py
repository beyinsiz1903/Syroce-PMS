"""Closed POS source snapshots must survive normal subsequent writer calls."""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb.daily_closure import preview
from tests.test_pos_final_consistency_replica import ctx, menu, paid

pytest_plugins = ("tests.test_pos_final_consistency_replica",)

DAY = "2026-10-18"


async def seal(database, day=DAY, tenant="t"):
    await database.pos_closures.insert_one({"tenant_id": tenant, "closure_date": day,
                                           "calculation_version": "canonical_pos_ledger_v2"})


@pytest.mark.asyncio
async def test_new_order_cannot_be_created_on_sealed_pos_day(service, db):
    await menu(db)
    await seal(db)
    service._enqueue_kot = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    assert error.value.status_code == 409
    assert await db.pos_orders.count_documents({}) == 0
    assert await db.pos_transactions.count_documents({}) == 0
    service._enqueue_kot.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_refund_cannot_change_sealed_pos_day(service, db):
    await paid(db)
    await seal(db)
    with pytest.raises(HTTPException) as error:
        await service.refund_order(ctx(), 'paid', 10, 'Sentetik yerel iade', 'closed-day-refund')
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 0
    assert (await db.pos_orders.find_one({'id': 'paid'}))['payment_status'] == 'paid'


@pytest.mark.asyncio
async def test_prior_day_order_cannot_post_into_new_sealed_day(service, db):
    await menu(db)
    service._enqueue_kot = AsyncMock()
    created = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-19'}})
    await seal(db, '2026-10-19')
    with pytest.raises(HTTPException) as error:
        await service.close_order(ctx(), created.data['order_id'], payment_method='cash')
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({}) == 0
    assert (await db.pos_orders.find_one({'id': created.data['order_id']}))['payment_status'] == 'unpaid'


@pytest.mark.asyncio
async def test_next_open_day_refund_preserves_previous_day_snapshot(service, db):
    await paid(db)
    before = await preview(db, 't', DAY)
    await seal(db)
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-19'}})
    result = await service.refund_order(ctx(), 'paid', 10, 'Ertesi gün yerel iade', 'next-day-refund')
    assert result.ok
    refund = await db.pos_transactions.find_one({'payment_type': 'refund'})
    assert refund['transaction_date'] == '2026-10-19'
    assert (await preview(db, 't', DAY))['preview_hash'] == before['preview_hash']


@pytest.mark.asyncio
async def test_refund_retry_after_closure_does_not_create_another_refund(service, db):
    await paid(db)
    first = await service.refund_order(ctx(), 'paid', 10, 'Yerel iade', 'same-request')
    await seal(db)
    again = await service.refund_order(ctx(), 'paid', 10, 'Yerel iade', 'same-request')
    assert first.ok and again.ok and again.data['idempotent']
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 1


@pytest.mark.asyncio
async def test_other_tenant_closure_cannot_block_current_tenant(service, db):
    await menu(db)
    await seal(db, tenant='other-local-tenant')
    service._enqueue_kot = AsyncMock()
    assert (await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])).ok


@pytest.mark.asyncio
async def test_legacy_tab_cannot_be_opened_on_sealed_day(service, db):
    await seal(db)
    with pytest.raises(HTTPException) as error:
        await service.open_tab(ctx(), outlet_id='bar', table_number='1')
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_tab_cannot_be_settled_on_sealed_day(service, db):
    await db.pos_transactions.insert_one({'tenant_id':'t', 'id':'old-tab', 'status':'open',
                                         'transaction_date':DAY, 'total_amount':10, 'currency':'EUR'})
    await seal(db)
    with pytest.raises(HTTPException) as error:
        await service.close_tab(ctx(), 'old-tab')
    assert error.value.status_code == 409
    assert (await db.pos_transactions.find_one({'id':'old-tab'}))['status'] == 'open'


@pytest.mark.asyncio
async def test_legacy_direct_sale_cannot_bypass_current_pms_day_closure(service, db):
    from domains.pms.pos_fnb.pos_fnb_service import PosFnbService

    await seal(db)
    legacy = PosFnbService()
    legacy._db = db
    with pytest.raises(HTTPException) as error:
        await legacy.create_pos_transaction(ctx(), 10, 'cash')
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_direct_router_cannot_bypass_current_pms_day_closure(db, monkeypatch):
    from domains.pms.pos_fnb_router import pos_core

    monkeypatch.setattr(pos_core, 'db', db)
    await seal(db)
    with pytest.raises(HTTPException) as error:
        await pos_core.create_pos_transaction(pos_core.CreatePOSTransactionRequest(amount=10, payment_method='cash'),
            current_user=SimpleNamespace(tenant_id='t', id='manager'), _perm=True)
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_direct_sale_uses_operating_day_and_currency(db):
    from domains.pms.pos_fnb.pos_fnb_service import PosFnbService

    legacy = PosFnbService()
    legacy._db = db
    assert (await legacy.create_pos_transaction(ctx(), 10, 'cash')).ok
    row = await db.pos_transactions.find_one({})
    assert row['transaction_date'] == row['business_date'] == DAY
    assert row['currency'] == 'EUR' and row['amount'] == 10


@pytest.mark.asyncio
async def test_legacy_open_tab_blocks_normal_daily_closure(service, db, monkeypatch):
    assert (await service.open_tab(ctx(), outlet_id='bar', table_number='1')).ok
    router, request = await closure_setup(db, monkeypatch)
    with pytest.raises(HTTPException) as error:
        await router.create_pos_closure(request, current_user=SimpleNamespace(tenant_id='t', id='manager'), _perm=True)
    assert error.value.status_code == 409
    assert await db.pos_closures.count_documents({}) == 0
    assert (await db.pos_transactions.find_one({}))['status'] == 'open'


@pytest.mark.asyncio
async def test_legacy_tab_settlement_and_retry_on_open_day(service, db):
    opened = await service.open_tab(ctx(), outlet_id='bar', table_number='1', items=[{'name':'Çay', 'price':10}])
    identity = opened.data['transaction_id']
    assert (await service.close_tab(ctx(), identity, 'cash')).ok
    before = await db.pos_transactions.find_one({'id':identity})
    await seal(db)
    assert (await service.close_tab(ctx(), identity, 'cash')).data['idempotent']
    assert (await db.pos_transactions.find_one({'id':identity})) == before


async def closure_setup(database, monkeypatch):
    from core import audit_chain
    from domains.pms import enterprise_router
    from domains.pms.pos_fnb.day_write_guard import prepare_day_lock, touch_day_lock

    monkeypatch.setattr(enterprise_router, 'db', database)
    monkeypatch.setattr(audit_chain, '_system_db', lambda: database)
    for name in ('audit_logs', 'audit_chain_state'):
        await database.create_collection(name)
    await prepare_day_lock(database)
    await touch_day_lock(database, 't', DAY, None)
    source = await preview(database, 't', DAY)
    request = enterprise_router.POSClosureRequest(business_date=date.fromisoformat(DAY),
        expected_preview_hash=source['preview_hash'], reason='Yerel kaynak mutabakatı')
    return enterprise_router, request


@pytest.mark.asyncio
@pytest.mark.parametrize('writer', ['create', 'refund'])
async def test_concurrent_closure_and_writer_have_one_consistent_winner(service, db, monkeypatch, writer):
    if writer == 'create':
        await menu(db)
        service._enqueue_kot = AsyncMock()
        async def write():
            return await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    else:
        await paid(db)
        async def write():
            return await service.refund_order(ctx(), 'paid', 10, 'Yerel eşzamanlı iade', 'concurrent')
    router, request = await closure_setup(db, monkeypatch)
    results = await asyncio.gather(write(), router.create_pos_closure(request,
        current_user=SimpleNamespace(tenant_id='t', id='manager'), _perm=True), return_exceptions=True)
    errors = [value for value in results if isinstance(value, BaseException)]
    assert len(errors) == 1 and isinstance(errors[0], HTTPException) and errors[0].status_code == 409
    closed = await db.pos_closures.count_documents({})
    written = await (db.pos_orders if writer == 'create' else db.pos_transactions).count_documents(
        {} if writer == 'create' else {'payment_type': 'refund'})
    assert closed + written == 1


@pytest.mark.asyncio
async def test_mobile_quick_order_rejected_on_closed_day(db, monkeypatch):
    from domains.pms.mobile_router import pos as mobile
    await menu(db)
    await seal(db)
    monkeypatch.setattr(mobile, "db", db)
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t", username="local")))
    request = mobile.QuickOrderRequest(outlet_id="bar", items=[mobile.QuickOrderItem(item_id="tea", quantity=1)])
    with pytest.raises(HTTPException) as error:
        await mobile.create_quick_order_mobile(request, credentials=None, _perm=None)
    assert error.value.status_code == 409
    assert await db.pos_orders.count_documents({}) == 0


@pytest.mark.asyncio
async def test_mobile_retry_after_closure_returns_original_without_new_write(db, monkeypatch):
    from domains.pms.mobile_router import pos as mobile
    await menu(db)
    monkeypatch.setattr(mobile, "db", db)
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t", username="local")))
    request = mobile.QuickOrderRequest(outlet_id="bar", items=[mobile.QuickOrderItem(item_id="tea", quantity=1)], idempotency_key="local-mobile")
    first = await mobile.create_quick_order_mobile(request, credentials=None, _perm=None)
    await seal(db)
    again = await mobile.create_quick_order_mobile(request, credentials=None, _perm=None)
    assert again["idempotent_replay"] and first["order_id"] == again["order_id"]
    assert await db.pos_orders.count_documents({}) == 1


@pytest.mark.asyncio
async def test_concurrent_mobile_retries_claim_only_one_order_on_a_fresh_day(db, monkeypatch):
    from domains.pms.mobile_router import pos as mobile
    await menu(db)
    monkeypatch.setattr(mobile, "db", db)
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=SimpleNamespace(tenant_id="t", username="local")))
    request = mobile.QuickOrderRequest(outlet_id="bar", items=[mobile.QuickOrderItem(item_id="tea", quantity=1)], idempotency_key="local-concurrent-mobile")
    first, second = await asyncio.gather(
        mobile.create_quick_order_mobile(request, credentials=None, _perm=None),
        mobile.create_quick_order_mobile(request, credentials=None, _perm=None),
    )
    assert first["order_id"] == second["order_id"]
    assert sorted([first["idempotent_replay"], second["idempotent_replay"]]) == [False, True]
    assert await db.pos_orders.count_documents({}) == 1
