"""LOCAL-only stock, role, tenant, outage and concurrency acceptance matrix."""
# Ruff: imported pytest fixtures are intentionally reused as test arguments.
# ruff: noqa: F811
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from core.security import get_current_user
from domains.pms import minibar_consumption as consumption
from domains.pms import minibar_router as router
from domains.pms import minibar_stock as stock
from models.enums import UserRole
from tests.test_minibar_atomic_replica import user, wired  # noqa: F401
from tests.test_pos_final_consistency_replica import db  # noqa: F401


async def link(database, quantity=20):
    await database.inventory_items.insert_one({'tenant_id': 't', 'id': 'warehouse-water', 'name': 'Maden Suyu',
        'quantity': quantity, 'unit': 'adet', 'unit_cost': 20})
    await database.minibar_items.update_one({'id': 'water'}, {'$set': {
        'inventory_product_id': 'warehouse-water', 'inventory_source': 'accounting'}})


def water(key='water', room_id='room', quantity=1):
    return router.ConsumeIn(room_id=room_id, idempotency_key=key, note='Misafir minibar tüketimi',
        lines=[router.ConsumeLine(item_id='water', quantity=quantity)])


async def test_central_stock_and_movement_are_atomic_and_replay_does_not_deplete_twice(wired):
    await link(wired)
    result = await router.consume(water(quantity=3), user())
    assert result['stock_complete'] and result['stock'][0]['status'] == 'depleted'
    assert (await wired.inventory_items.find_one({'id': 'warehouse-water'}))['quantity'] == 17
    movement = await wired.stock_movements.find_one({})
    assert movement['quantity'] == 3 and movement['movement_type'] == 'out'
    assert movement['total_cost'] == 60 and movement['business_date'] == '2026-10-25'
    assert not await wired.inventory_movements.count_documents({})
    again = await router.consume(water(quantity=3), user())
    assert again['idempotent'] and again['stock_complete']
    assert await wired.stock_movements.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({'action': 'minibar_stock_depleted'}) == 1


async def test_twenty_simultaneous_identical_requests_make_one_charge_and_stock_movement(wired):
    await link(wired)
    # Prebuild protection indexes; the test stresses actual source/stock work.
    await router._ensure_minibar_charge_index()
    await router._ensure_minibar_consumption_index()
    await stock.ensure_stock_indexes(wired)
    await wired.minibar_locks.create_index([('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)
    results = await asyncio.gather(*(router.consume(water('concurrent'), user()) for _ in range(20)))
    assert all(r['posted_to_folio'] for r in results)
    assert await wired.minibar_consumptions.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == await wired.stock_movements.count_documents({}) == 1
    assert (await wired.inventory_items.find_one({'id': 'warehouse-water'}))['quantity'] == 19


async def test_two_rooms_race_for_last_unit_never_go_negative(wired):
    await link(wired, quantity=1)
    await wired.rooms.insert_one({'tenant_id': 't', 'id': 'room2', 'room_number': '103'})
    await wired.bookings.insert_one({'tenant_id': 't', 'id': 'b2', 'room_id': 'room2', 'currency': 'TRY', 'status': 'checked_in'})
    await wired.folios.insert_one({'tenant_id': 't', 'id': 'f2', 'booking_id': 'b2', 'folio_type': 'guest', 'currency': 'TRY', 'status': 'open'})
    results = await asyncio.gather(router.consume(water('one'), user()), router.consume(water('two', 'room2'), user()))
    assert {r['stock'][0]['status'] for r in results} == {'depleted', 'insufficient_stock'}
    assert (await wired.inventory_items.find_one({'id': 'warehouse-water'}))['quantity'] == 0
    assert await wired.stock_movements.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == 2  # physical consumption is still billed, shortage remains visible


async def test_outage_after_financial_commit_is_durable_and_retry_only_repairs_stock(wired, monkeypatch):
    await link(wired)
    original = stock.run_stock
    monkeypatch.setattr(consumption, 'run_stock', AsyncMock(side_effect=ConnectionError('stock worker unavailable')))
    result = await router.consume(water(), user())
    assert result['posted_to_folio'] and result['stock'][0]['status'] == 'pending_retry'
    assert (await wired.inventory_items.find_one({}))['quantity'] == 20
    assert (await wired.minibar_consumptions.find_one({}))['stock_jobs'][0]['status'] == 'pending'
    before = await wired.folio_charges.find({}).to_list(None)
    monkeypatch.setattr(consumption, 'run_stock', original)
    replay = await router.consume(water(), user())
    assert replay['idempotent'] and replay['stock_complete']
    assert await wired.folio_charges.find({}).to_list(None) == before
    assert (await wired.inventory_items.find_one({}))['quantity'] == 19


async def test_lost_stock_success_response_cannot_double_deplete(wired, monkeypatch):
    await link(wired)
    original = stock.run_stock
    async def lost_ack(*args, **kwargs):
        await original(*args, **kwargs)
        raise ConnectionError('success response lost')
    monkeypatch.setattr(consumption, 'run_stock', lost_ack)
    first = await router.consume(water(), user())
    assert first['stock'][0]['status'] == 'pending_retry'
    monkeypatch.setattr(consumption, 'run_stock', original)
    await router.consume(water(), user())
    assert (await wired.inventory_items.find_one({}))['quantity'] == 19
    assert await wired.stock_movements.count_documents({}) == 1


@pytest.mark.parametrize('failure', ['movement', 'audit'])
async def test_stock_mid_transaction_failure_rolls_back_quantity_movement_and_job(wired, monkeypatch, failure):
    await link(wired)
    old_insert = type(wired.stock_movements).insert_one
    old_audit = stock.audit_log
    async def fail_movement(collection, *args, **kwargs):
        if collection.name == 'stock_movements':
            raise RuntimeError('injected movement outage')
        return await old_insert(collection, *args, **kwargs)
    if failure == 'movement':
        monkeypatch.setattr(type(wired.stock_movements), 'insert_one', fail_movement)
    else:
        monkeypatch.setattr(stock, 'audit_log', AsyncMock(side_effect=RuntimeError('sealed stock audit unavailable')))
    result = await router.consume(water(), user())
    assert result['stock'][0]['status'] == 'pending_retry'
    assert (await wired.inventory_items.find_one({}))['quantity'] == 20
    assert not await wired.stock_movements.count_documents({})
    assert (await wired.minibar_consumptions.find_one({}))['stock_jobs'][0]['status'] == 'pending'
    monkeypatch.setattr(type(wired.stock_movements), 'insert_one', old_insert)
    monkeypatch.setattr(stock, 'audit_log', old_audit)
    retry = await router.retry_stock(result['consumption']['id'], router.StockRetryIn(reason='Bağlantı yeniden sağlandı'), user())
    assert retry['stock_complete'] and await wired.stock_movements.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == 1


async def test_restock_then_retry_uses_original_frozen_link_not_changed_catalog(wired):
    await link(wired, quantity=0)
    result = await router.consume(water(), user())
    await wired.inventory_items.insert_one({'id': 'different-product', 'tenant_id': 't', 'quantity': 99})
    await router.update_item('water', router.MinibarItemUpdate(inventory_product_id='different-product', inventory_source='accounting'), user())
    await wired.inventory_items.update_one({'id': 'warehouse-water'}, {'$set': {'quantity': 10}})
    retry = await router.retry_stock(result['consumption']['id'], router.StockRetryIn(reason='Stok girişi tamamlandı'), user())
    assert retry['stock_complete']
    assert (await wired.inventory_items.find_one({'id': 'warehouse-water'}))['quantity'] == 9
    assert (await wired.inventory_items.find_one({'id': 'different-product'}))['quantity'] == 99


@pytest.mark.parametrize('code', ['TRY', 'USD', 'EUR'])
@pytest.mark.parametrize('full_comp', [False, True])
async def test_stock_is_physical_not_dependent_on_currency_or_comp_price(wired, code, full_comp):
    await link(wired)
    await wired.bookings.update_one({'id': 'b'}, {'$set': {'currency': code, 'is_complimentary': full_comp, 'complimentary_scope': 'full'}})
    await wired.folios.update_one({'id': 'f'}, {'$set': {'currency': code}})
    await wired.minibar_items.update_one({'id': 'water'}, {'$set': {'currency': code}})
    result = await router.consume(water(), user())
    assert result['consumption']['total'] == (0 if full_comp else 60)
    assert result['stock_complete'] and (await wired.inventory_items.find_one({}))['quantity'] == 19


async def test_reconcile_old_untracked_lines_is_explicit_current_day_not_a_financial_rewrite(wired):
    first = await router.consume(water(), user())
    query = {'id': first['consumption']['id']}
    await wired.minibar_consumptions.update_one(query, {'$unset': {'stock_jobs': ''}})  # pre-upgrade source
    before = await wired.minibar_consumptions.find_one(query)
    charges = await wired.folio_charges.find({}).to_list(None)
    await link(wired)
    await wired.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-26'}})
    request = router.StockReconcileIn(reason='Eski yapay tüketim için bugünkü stok mutabakatı', bindings=[
        router.StockBinding(line_no=0, inventory_product_id='warehouse-water')])
    result = await router.reconcile_stock(before['id'], request, user())
    assert result['bindings_changed'] == 1 and result['stock'][0]['status'] == 'depleted'
    after = await wired.minibar_consumptions.find_one(query)
    assert {k:v for k,v in after.items() if k != 'stock_jobs'} == before
    assert await wired.folio_charges.find({}).to_list(None) == charges
    movement = await wired.stock_movements.find_one({})
    assert movement['business_date'] == '2026-10-26' and movement['consumption_business_date'] == '2026-10-25'
    replay = await router.reconcile_stock(before['id'], request, user())
    assert replay['bindings_changed'] == 0 and await wired.stock_movements.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({'action': 'minibar_stock_linked'}) == 1


async def test_old_linked_source_without_movement_is_not_automatically_depleted_again(wired):
    await link(wired)
    first = await router.consume(water(), user())
    # Simulate the dangerous old gap: quantity was changed, movement absent.
    await wired.minibar_consumptions.update_one({'id': first['consumption']['id']}, {'$unset': {'stock_jobs': ''}})
    await wired.stock_movements.delete_many({})
    before = (await wired.inventory_items.find_one({}))['quantity']
    result = await router.retry_stock(first['consumption']['id'], router.StockRetryIn(reason='Eski kayıt kontrolü'), user())
    assert not result['stock_complete'] and result['stock'][0]['status'] == 'legacy_untracked'
    assert (await wired.inventory_items.find_one({}))['quantity'] == before
    with pytest.raises(HTTPException) as error:
        await router.reconcile_stock(first['consumption']['id'], router.StockReconcileIn(reason='Kaynak mutabakatı', bindings=[
            router.StockBinding(line_no=0, inventory_product_id='warehouse-water')]), user())
    assert error.value.status_code == 409


@pytest.mark.parametrize('role', list(UserRole))
async def test_consumption_role_matrix(wired, role):
    actor = user(); actor.role = role
    if role.value in router._CONSUME_ROLES:
        assert (await router.consume(water(), actor))['posted_to_folio']
    else:
        with pytest.raises(HTTPException) as error:
            await router.consume(water(), actor)
        assert error.value.status_code == 403
        assert not await wired.minibar_consumptions.count_documents({})


@pytest.mark.parametrize('role', list(UserRole))
async def test_catalog_and_stock_retry_role_matrix(wired, role):
    actor = user(); actor.role = role
    data = router.MinibarItemIn(name='Portakal Suyu', price=60, currency='TRY', tax_rate=.1)
    if role.value in router._CATALOG_ROLES:
        assert (await router.create_item(data, actor))['item']['name'] == 'Portakal Suyu'
        assert await wired.audit_logs.count_documents({'action': 'minibar_catalog_created'}) == 1
    else:
        with pytest.raises(HTTPException) as error:
            await router.create_item(data, actor)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await router.retry_stock('unknown', router.StockRetryIn(reason='Yetki kontrolü'), actor)
        assert error.value.status_code == 403


@pytest.mark.parametrize('role', list(UserRole))
async def test_read_role_matrix(wired, role):
    actor = user(); actor.role = role
    if role.value in router._READ_ROLES:
        assert len((await router.list_items(False, actor))['items']) == 2
    else:
        with pytest.raises(HTTPException) as error:
            await router.list_items(False, actor)
        assert error.value.status_code == 403


async def test_cross_tenant_stock_link_retry_and_reconcile_fail_closed_over_http(wired):
    await link(wired)
    made = await router.consume(water(), user())
    app = FastAPI(); app.include_router(router.router)
    other = SimpleNamespace(tenant_id='other', id='other-admin', role='admin', is_super_admin=False)
    app.dependency_overrides[get_current_user] = lambda: other
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
        retry = await client.post(f"/api/minibar/consumptions/{made['consumption']['id']}/retry-stock", json={'reason': 'Diğer tesis kontrolü'})
        assert retry.status_code == 404
        link_result = await client.post('/api/minibar/items', json={'name': 'Yabancı ürün', 'price': 1,
            'inventory_product_id': 'warehouse-water', 'inventory_source': 'accounting'})
        assert link_result.status_code == 404
        listing = await client.get('/api/minibar/inventory-products')
        assert listing.json()['items'] == []
    assert (await wired.inventory_items.find_one({}))['quantity'] == 19


async def test_foreign_or_inactive_link_and_ambiguous_legacy_id_are_rejected(wired):
    await wired.inventory_items.insert_one({'tenant_id': 'other', 'id': 'foreign-product', 'quantity': 99})
    with pytest.raises(HTTPException) as error:
        await router.update_item('water', router.MinibarItemUpdate(inventory_product_id='foreign-product'), user())
    assert error.value.status_code == 404
    await link(wired)
    await wired.inventory.insert_one({'tenant_id': 't', 'id': 'warehouse-water', 'quantity': 10})
    with pytest.raises(HTTPException) as error:
        await stock.validate_link(wired, 't', 'warehouse-water')
    assert error.value.status_code == 409
    await wired.inventory_items.update_one({'id': 'warehouse-water'}, {'$set': {'active': False}})
    with pytest.raises(HTTPException) as error:
        await stock.validate_link(wired, 't', 'warehouse-water', 'accounting')
    assert error.value.status_code == 409


async def test_catalog_audit_failure_does_not_leave_an_unlogged_link(wired, monkeypatch):
    await link(wired)
    before = await wired.minibar_items.find_one({'id': 'water'})
    monkeypatch.setattr(router, 'audit_log', AsyncMock(side_effect=RuntimeError('catalog audit unavailable')))
    with pytest.raises(RuntimeError):
        await router.update_item('water', router.MinibarItemUpdate(name='İsim değişikliği'), user())
    assert await wired.minibar_items.find_one({'id': 'water'}) == before


@pytest.mark.parametrize('changes', [{'tax_rate': None}, {'currency': 'USD'}, {'price': float('nan')}, {'active': False}])
async def test_invalid_property_catalog_never_depletes_stock_or_creates_debt(wired, changes):
    await link(wired)
    await wired.minibar_items.update_one({'id': 'water'}, {'$set': changes})
    with pytest.raises(HTTPException):
        await router.consume(water(), user())
    assert not await wired.minibar_consumptions.count_documents({})
    assert not await wired.folio_charges.count_documents({}) and not await wired.stock_movements.count_documents({})
    assert (await wired.inventory_items.find_one({}))['quantity'] == 20


async def test_audited_warehouse_opening_is_visible_in_central_inventory_and_replays_once(wired):
    data = router.StockProductIn(request_id=uuid4(), name='Maden Suyu 200 ml', unit='adet', quantity=100,
        unit_cost=20, currency='TRY', sku='DEMO-WATER', reason='Yapay sunum stoğu açılışı, gerçek tedarikçi faturası değildir')
    made = await router.create_stock_product(data, user())
    assert not made['replayed'] and made['item']['quantity'] == 100
    assert await wired.inventory_items.count_documents({}) == 1 and await wired.stock_movements.count_documents({'movement_type': 'in'}) == 1
    assert await wired.audit_logs.count_documents({'action': 'minibar_inventory_opened'}) == 1
    replay = await router.create_stock_product(data, user())
    assert replay['replayed'] and replay['item']['id'] == made['item']['id']
    assert await wired.stock_movements.count_documents({}) == 1
    # A changed quantity must not reuse an opening request identity.
    with pytest.raises(HTTPException) as error:
        await router.create_stock_product(data.model_copy(update={'quantity': 101}), user())
    assert error.value.status_code == 409


async def test_warehouse_opening_audit_outage_leaves_no_product_or_movement(wired, monkeypatch):
    monkeypatch.setattr(stock, 'audit_log', AsyncMock(side_effect=RuntimeError('opening audit unavailable')))
    data = router.StockProductIn(request_id=uuid4(), name='Maden Suyu', unit='adet', quantity=100,
        unit_cost=20, currency='TRY', reason='Sunum stok açılışı')
    with pytest.raises(RuntimeError):
        await router.create_stock_product(data, user())
    assert not await wired.inventory_items.count_documents({}) and not await wired.stock_movements.count_documents({})


async def test_missing_completed_movement_is_never_redepleted_or_reported_as_verified(wired):
    await link(wired)
    first = await router.consume(water(), user())
    await wired.stock_movements.delete_many({})
    result = await router.consume(water(), user())
    assert result['idempotent'] and not result['stock_complete'] and result['stock'][0]['status'] == 'pending_retry'
    assert (await wired.inventory_items.find_one({}))['quantity'] == 19
    assert not await wired.stock_movements.count_documents({})
    assert first['consumption']['id'] == result['consumption']['id']


@pytest.mark.parametrize('role', list(UserRole))
@pytest.mark.parametrize('currency', ['TRY', 'USD', 'EUR'])
@pytest.mark.parametrize('full_comp', [False, True])
@pytest.mark.parametrize('folio_open', [False, True])
@pytest.mark.parametrize('available', [0, 2])
async def test_combined_role_property_currency_comp_folio_and_stock_matrix(wired, role, currency, full_comp, folio_open, available):
    """312 actual replica cases, not independent capability booleans."""
    await link(wired, quantity=available)
    await wired.bookings.update_one({'id': 'b'}, {'$set': {'currency': currency,
        'is_complimentary': full_comp, 'complimentary_scope': 'full' if full_comp else None}})
    await wired.folios.update_one({'id': 'f'}, {'$set': {'currency': currency, 'status': 'open' if folio_open else 'closed'}})
    await wired.minibar_items.update_one({'id': 'water'}, {'$set': {'currency': currency}})
    actor = user(); actor.role = role
    if role.value not in router._CONSUME_ROLES:
        with pytest.raises(HTTPException) as error:
            await router.consume(water('combined-matrix'), actor)
        assert error.value.status_code == 403
        for collection in ('minibar_consumptions', 'folio_charges', 'minibar_late_charges', 'stock_movements', 'audit_logs'):
            assert await wired[collection].count_documents({}) == 0
        return
    result = await router.consume(water('combined-matrix'), actor)
    assert result['posted_to_folio'] is folio_open
    assert result['consumption']['total'] == (0 if full_comp else 60)
    assert result['stock_complete'] is bool(available)
    assert result['stock'][0]['status'] == ('depleted' if available else 'insufficient_stock')
    assert (await wired.inventory_items.find_one({'id': 'warehouse-water'}))['quantity'] == max(available - 1, 0)
    assert await wired.folio_charges.count_documents({}) == int(folio_open)
    assert await wired.minibar_late_charges.count_documents({}) == int(not folio_open)
    replay = await router.consume(water('combined-matrix'), actor)
    assert replay['idempotent']
    assert await wired.minibar_consumptions.count_documents({}) == 1
    assert await wired.stock_movements.count_documents({}) == int(bool(available))
