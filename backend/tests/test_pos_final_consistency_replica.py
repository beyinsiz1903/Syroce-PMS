"""Restaurant acceptance regressions; use only an explicitly selected LOCAL replica set."""
import asyncio
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from common import audit_hook
from common.context import OperationContext
from core import pos_folio_consumer
from core.outbox_service import POS_CHARGE_POSTED, POS_CHARGE_REVERSED
from domains.pms import pos_fnb_router_v2
from domains.pms.pos_extensions import pos_barcode, pos_fiscal, pos_happy_hour, pos_print_spool
from domains.pms.pos_fnb import pos_fnb_service_v2 as service_module
from domains.pms.pos_fnb.guest_qr import table_token, verify_table_token
from domains.pms.pos_fnb.order_pricing import allocate_parts, reprice_order
from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2
from domains.pms.pos_fnb.receipts import receipt_payload
from domains.pms.pos_fnb_router import guest_menu
from domains.pms.pos_fnb_router import pos_core as table_router
from domains.pms.pos_router import pos_core


@pytest_asyncio.fixture
async def db():
    uri = os.getenv('POS_TEST_MONGO_URI')
    assert uri and urlparse(uri).hostname in {'127.0.0.1', 'localhost'}, 'Explicit LOCAL replica set required'
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    database = client['pos_acceptance_' + uuid.uuid4().hex]
    # Mongo transactions cannot implicitly create a missing collection.
    for name in ('pos_orders', 'pos_transactions', 'pos_order_item_voids', 'kitchen_orders',
                 'pos_order_item_batches', 'outbox_events', 'folio_locks', 'pos_refund_locks',
                 'pos_table_locks', 'stock_consumptions', 'pos_guest_requests'):
        await database.create_collection(name)
    await database.hotel_settings.insert_one({'tenant_id': 't', 'currency': 'EUR', 'timezone': 'Europe/Istanbul'})
    # Fixtures below book sales on this operating day. Calendar time must not
    # silently move a generated refund to a different report after midnight.
    await database.tenant_settings.insert_one({'tenant_id': 't', 'business_date': '2026-10-18'})
    yield database
    await client.drop_database(database.name)
    client.close()


@pytest_asyncio.fixture
async def service(db, monkeypatch):
    service = PosFnbServiceV2()
    service._db = db
    service._enqueue_kot = AsyncMock()
    service._broadcast_kitchen_queue = AsyncMock()
    monkeypatch.setattr(audit_hook, '_write_audit', AsyncMock())
    monkeypatch.setattr('core.integrations.operational_gl_bridge.post_direct_pos_refund_to_gl', AsyncMock())
    return service


def ctx():
    return OperationContext(tenant_id='t', actor_id='manager', actor_role='admin')


async def menu(db, *, price=100, tax=.1):
    await db.pos_outlets.insert_one({'id': 'bar', 'tenant_id': 't', 'is_active': True})
    await db.pos_menu_items.insert_one({'id': 'tea', 'tenant_id': 't', 'outlet_id': 'bar',
        'item_name': 'Çay', 'unit_price': price, 'tax_rate': tax, 'available': True, 'category': 'drinks'})


@pytest.mark.asyncio
async def test_real_decorators_allow_positional_reason_and_reprice_every_line_change(service, db):
    await menu(db)
    created = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    oid = created.data['order_id']
    result = await service.apply_order_adjustment(ctx(), oid, 'discount', 'percentage', 10, 'Misafir indirimi')
    assert result.ok and result.data['grand_total'] == 99
    assert (await service.add_order_items(ctx(), oid, [{'item_id': 'tea', 'quantity': 1}], 'append-1')).ok
    assert (await db.pos_orders.find_one({'id': oid}))['grand_total'] == 198
    result = await service.apply_order_adjustment(ctx(), oid, 'service_charge', 'fixed', 5, 'Servis')
    assert result.ok and result.data['grand_total'] == 203
    result = await service.void_order_item(ctx(), oid, 0, 'Yanlış ürün')
    assert result.ok and result.data['grand_total'] == 104
    assert (await db.kitchen_orders.find_one({'order_id': oid, 'status': 'cancelled'})) is not None
    assert await db.pos_order_item_voids.count_documents({}) == 1
    recorded = [call.args[1]['override_reason'] for call in audit_hook._write_audit.await_args_list]
    assert 'Yanlış ürün' in recorded and 'Servis' in recorded
    blank = await service.void_order_item(ctx(), oid, 0, '  ')
    assert not blank.ok and blank.code == 'REASON_REQUIRED'


def test_removing_last_line_does_not_restore_old_subtotal():
    assert reprice_order({'order_items': [{'total': 100, 'tax_rate': .1}], 'total_amount': 100}, [])['grand_total'] == 0


@pytest.mark.asyncio
async def test_line_void_failure_rolls_back_order_and_kitchen(service, db, monkeypatch):
    await menu(db)
    result = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}, {'item_id': 'tea', 'quantity': 1}])
    oid = result.data['order_id']
    original = await db.pos_orders.find_one({'id': oid})
    async def fail(*args, **kwargs):
        raise RuntimeError('audit insert unavailable')
    monkeypatch.setattr(type(db.pos_order_item_voids), 'insert_one', fail)
    with pytest.raises(RuntimeError):
        await service.void_order_item(ctx(), oid, 0, 'Yanlış')
    assert (await db.pos_orders.find_one({'id': oid}))['grand_total'] == original['grand_total']
    assert (await db.kitchen_orders.find_one({'order_id': oid}))['status'] == 'pending'


async def paid(db, *, amount=110, method='cash', breakdown=None, oid='paid'):
    await db.pos_orders.insert_one({'tenant_id': 't', 'id': oid, 'outlet_id': 'bar', 'status': 'closed', 'payment_status': 'paid'})
    await db.pos_transactions.insert_one({'tenant_id': 't', 'id': 'sale-' + oid, 'order_id': oid, 'outlet_id': 'bar',
        'status': 'completed', 'total_amount': amount, 'tax_amount': 10 if amount == 110 else 0,
        'payment_method': method, 'payment_breakdown': breakdown,
        'transaction_date': '2026-10-18', 'currency': 'EUR',
        'order_items': [{'item_name': 'Çay', 'category': 'drinks', 'total': 100, 'quantity': 1, 'unit_price': 100}]})


@pytest.mark.asyncio
async def test_concurrent_refund_retry_credits_only_once_and_rejects_changed_request(service, db):
    await paid(db)
    results = await asyncio.gather(*(service.refund_order(ctx(), 'paid', 55, 'Misafir talebi', 'same-refund') for _ in range(2)))
    assert all(result.ok for result in results)
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 1
    assert (await db.pos_transactions.find_one({'id': 'sale-paid'}))['refunded_amount'] == 55
    with pytest.raises(HTTPException) as exc:
        await service.refund_order(ctx(), 'paid', 10, 'Misafir talebi', 'same-refund')
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_penny_refunds_exhaust_each_original_tender_without_over_refunding(service, db):
    await paid(db, amount=.03, method='mixed', breakdown=[{'method': 'cash', 'amount': .02}, {'method': 'card', 'amount': .01}])
    for index in range(3):
        assert (await service.refund_order(ctx(), 'paid', .01, 'İade', f'penny-{index}')).ok
    refunds = await db.pos_transactions.find({'payment_type': 'refund'}).to_list(None)
    for method, expected in (('cash', -.02), ('card', -.01)):
        assert round(sum(part['amount'] for row in refunds for part in row['payment_breakdown'] if part['method'] == method), 2) == expected
    assert (await db.pos_orders.find_one({'id': 'paid'}))['payment_status'] == 'refunded'


@pytest.mark.asyncio
async def test_room_refund_outbox_failure_rolls_back_all_financial_writes(service, db, monkeypatch):
    await paid(db, method='room_charge')
    await db.pos_transactions.update_one({'id': 'sale-paid'}, {'$set': {'folio_id': 'folio'}})
    monkeypatch.setattr(service_module, 'enqueue_outbox_event', AsyncMock(side_effect=RuntimeError('injected enqueue failure')))
    with pytest.raises(RuntimeError):
        await service.refund_order(ctx(), 'paid', None, 'İade', 'room-refund')
    assert await db.pos_transactions.count_documents({'payment_type': 'refund'}) == 0
    assert not (await db.pos_transactions.find_one({'id': 'sale-paid'})).get('refunded_amount')
    assert (await db.pos_orders.find_one({'id': 'paid'}))['payment_status'] == 'paid'


@pytest.mark.asyncio
async def test_room_refund_before_delayed_post_never_resurrects_folio_debt(service, db, monkeypatch):
    await paid(db, method='room_charge')
    await db.pos_transactions.update_one({'id': 'sale-paid'}, {'$set': {'folio_id': 'folio'}})
    await db.folios.insert_one({'tenant_id': 't', 'id': 'folio', 'status': 'open', 'balance': 0})
    assert (await service.refund_order(ctx(), 'paid', None, 'İade', 'room-refund')).ok
    monkeypatch.setattr(pos_folio_consumer, 'get_system_db', lambda: db)
    assert await db.outbox_events.count_documents({'event_type': POS_CHARGE_REVERSED}) == 1
    event = {'event_type': POS_CHARGE_POSTED, 'tenant_id': 't', 'payload': {'folio_id': 'folio',
        'source_pos_order_id': 'paid', 'charges': [{'tenant_id': 't', 'folio_id': 'folio', 'source_pos_order_id': 'paid', 'line_no': 0, 'total': 110}]}}
    assert (await pos_folio_consumer.handle_ic_pos_event(event))[0]
    assert await db.folio_charges.count_documents({'voided': {'$ne': True}}) == 0
    assert (await db.folios.find_one({'id': 'folio'}))['balance'] == 0


@pytest.mark.asyncio
async def test_full_refund_clears_z_tax_categories_and_preserves_receipt_snapshot(service, db, monkeypatch):
    await paid(db)
    assert (await service.refund_order(ctx(), 'paid', 55, 'İade', 'r1')).ok
    assert (await service.refund_order(ctx(), 'paid', 55, 'İade', 'r2')).ok
    refunds = await db.pos_transactions.find({'payment_type': 'refund'}).to_list(None)
    assert {row['transaction_date'] for row in refunds} == {'2026-10-18'}
    monkeypatch.setattr(pos_core, 'db', db)
    report = await pos_core.get_z_report('2026-10-18', None, SimpleNamespace(tenant_id='t'))
    assert report['net_sales'] == 0 and report['tax_total'] == 0
    assert report['category_sales']['drinks'] == 0
    assert report['currency'] == 'EUR' and report['gross_sales'] == 110 and report['refunds'] == 110
    receipt = await receipt_payload(db, 't', 'paid')
    assert receipt['total'] == 110 and receipt['refunded_amount'] == 110 and receipt['currency'] == 'EUR'
    assert receipt['items'][0]['name'] == 'Çay' and 'Mali belge değildir' in receipt['footer']
    with pytest.raises(HTTPException):
        await receipt_payload(db, 'other', 'paid')


@pytest.mark.asyncio
async def test_legacy_refund_on_later_day_hydrates_only_reversal_for_that_day(db, monkeypatch):
    await paid(db)
    await db.pos_transactions.insert_many([
        {'tenant_id': 't', 'id': 'r1', 'original_transaction_id': 'sale-paid', 'order_id': 'paid', 'payment_type': 'refund',
         'status': 'refunded', 'total_amount': -55, 'transaction_date': '2026-10-18', 'created_at': '2026-10-18T10:00:00'},
        {'tenant_id': 't', 'id': 'r2', 'original_transaction_id': 'sale-paid', 'order_id': 'paid', 'payment_type': 'refund',
         'status': 'refunded', 'total_amount': -55, 'transaction_date': '2026-10-19', 'created_at': '2026-10-19T10:00:00'}])
    monkeypatch.setattr(pos_core, 'db', db)
    report = await pos_core.get_z_report('2026-10-19', None, SimpleNamespace(tenant_id='t'))
    assert report['net_sales'] == -55 and report['tax_total'] == -5
    assert report['category_sales']['drinks'] == -50
    assert 'tax_amount' not in await db.pos_transactions.find_one({'id': 'r2'})  # read-only enrichment


@pytest_asyncio.fixture
async def guest(db, service, monkeypatch):
    # Freeze only the request bucket, near the real MongoDB clock. A fixed
    # historical instant makes expires_at already expired to its TTL monitor.
    frozen_now = datetime.now(UTC)
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now.astimezone(tz) if tz else frozen_now.replace(tzinfo=None)
    monkeypatch.setattr(guest_menu, 'datetime', FixedClock)
    await menu(db)
    await db.table_layouts.insert_one({'tenant_id': 't', 'outlet_id': 'bar', 'id': 'table', 'table_number': '1', 'status': 'available'})
    monkeypatch.setattr(guest_menu, 'db', db)
    monkeypatch.setattr(guest_menu, 'require_tenant_module', AsyncMock())
    monkeypatch.setattr(guest_menu, 'get_tenant_currency', AsyncMock(return_value=('EUR', '€')))
    monkeypatch.setattr(guest_menu, 'PosFnbServiceV2', lambda: service)
    app = FastAPI()
    app.include_router(guest_menu.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield client


def guest_body(key='guest-order-1'):
    return {'table_id': 'table', 'table_token': table_token('t', 'bar', {'id': 'table'}),
            'idempotency_key': key, 'items': [{'item_id': 'tea', 'quantity': 1}], 'expected_total': 110}


@pytest.mark.asyncio
async def test_public_qr_menu_order_kitchen_append_and_parallel_retry(guest, db):
    url = '/api/public/fnb/t/bar'
    result = await guest.get(url + '/menu')
    assert result.status_code == 200 and result.json()['categories'][0]['items'][0]['currency'] == 'EUR'
    results = await asyncio.gather(*(guest.post(url + '/order', json=guest_body()) for _ in range(4)))
    assert all(result.status_code == 200 for result in results), [result.text for result in results]
    assert await db.pos_orders.count_documents({}) == 1
    assert await db.pos_order_item_batches.count_documents({}) == 0
    assert await db.kitchen_orders.count_documents({}) == 1
    order = await db.pos_orders.find_one({})
    assert order['grand_total'] == 110 and order['source'] == 'guest_qr'
    assert (await guest.post(url + '/order', json=guest_body('guest-order-2'))).status_code == 200
    assert (await db.pos_orders.find_one({}))['grand_total'] == 220
    assert await db.kitchen_orders.count_documents({}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('change,status', [({'table_token': 'fake'}, 403), ({'expected_total': 1}, 409),
    ({'items': [{'item_id': 'tea', 'quantity': -1}]}, 422), ({'table_id': 'foreign'}, 404)])
async def test_guest_bad_requests_never_create_orders(guest, db, change, status):
    result = await guest.post('/api/public/fnb/t/bar/order', json={**guest_body(), **change})
    assert result.status_code == status
    assert await db.pos_orders.count_documents({}) == 0


@pytest.mark.asyncio
async def test_guest_cannot_bypass_license_or_checkout(guest, db, monkeypatch):
    monkeypatch.setattr(guest_menu, 'require_tenant_module', AsyncMock(side_effect=HTTPException(403, 'Lisans yok')))
    assert (await guest.get('/api/public/fnb/t/bar/menu')).status_code == 403
    assert (await guest.post('/api/public/fnb/t/bar/order', json=guest_body())).status_code == 403
    assert (await guest.post('/api/pos/v2/orders/private/close', json={})).status_code == 404
    assert await db.pos_orders.count_documents({}) == 0


def test_signed_table_tokens_reject_other_table_and_rotation():
    token = table_token('t', 'bar', {'id': 'a'})
    for tenant, outlet, table in [('other', 'bar', {'id': 'a'}), ('t', 'other', {'id': 'a'}),
                                 ('t', 'bar', {'id': 'b'}), ('t', 'bar', {'id': 'a', 'qr_version': 2})]:
        with pytest.raises(HTTPException):
            verify_table_token(token, tenant, outlet, table)


@pytest.mark.asyncio
async def test_happy_hour_uses_hotel_time_and_previous_day_for_overnight_tail(db):
    instant = datetime(2026, 10, 18, 22, 0, tzinfo=UTC)  # Monday 01:00 in Istanbul
    local = await pos_happy_hour.hotel_local_time(db, 't', instant)
    rule = {'start_time': '22:00', 'end_time': '02:00', 'days_of_week': [6], 'active': True}
    assert local.hour == 1 and local.weekday() == 0
    assert pos_happy_hour._rule_matches(rule, local, 'bar', {})
    assert not pos_happy_hour._rule_matches({**rule, 'days_of_week': [0]}, local, 'bar', {})


def test_minor_unit_allocation_conserves_capacity_for_every_small_split():
    for a in range(1, 12):
        for b in range(1, 12):
            remaining = [a / 100, b / 100]
            for _ in range(a + b):
                shares = allocate_parts(remaining, .01)
                assert round(sum(shares), 2) == .01
                remaining = [round(cap - share, 2) for cap, share in zip(remaining, shares)]
                assert all(cap >= 0 for cap in remaining)
            assert remaining == [0, 0]


@pytest.mark.asyncio
async def test_fiscal_readiness_never_claims_simulator_is_certified(monkeypatch):
    monkeypatch.setenv('ENVIRONMENT', 'production')
    monkeypatch.delenv('ALLOW_POS_FISCAL_SIMULATOR', raising=False)
    monkeypatch.delenv('POS_FISCAL_DRIVER', raising=False)
    result = await pos_fiscal.readiness(SimpleNamespace(tenant_id='t'))
    assert not result['certified'] and not result['can_simulate']


@pytest.mark.asyncio
async def test_barcode_binds_existing_tenant_product(db, monkeypatch):
    await menu(db)
    monkeypatch.setattr(pos_barcode, 'db', db)
    with pytest.raises(HTTPException):
        await pos_barcode.lookup('404', outlet_id='bar', current_user=SimpleNamespace(tenant_id='t', id='u'))
    await pos_barcode.upsert_mapping(pos_barcode.BarcodeMap(barcode='1234', menu_item_id='tea'), SimpleNamespace(tenant_id='t', id='u'))
    result = await pos_barcode.lookup('1234', outlet_id='bar', current_user=SimpleNamespace(tenant_id='t', id='u'))
    assert result['item']['id'] == 'tea'
    with pytest.raises(HTTPException) as exc:
        await pos_barcode.lookup('1234', outlet_id='other', current_user=SimpleNamespace(tenant_id='t', id='u'))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_many_small_refunds_do_not_leave_a_floating_point_penny(service, db):
    await paid(db, amount=.3)
    for index in range(30):
        result = await service.refund_order(ctx(), 'paid', .01, 'İade', f'small-{index}')
        assert result.ok, (index, result.error)
    assert (await db.pos_transactions.find_one({'id': 'sale-paid'}))['refunded_amount'] == .3
    assert (await db.pos_orders.find_one({'id': 'paid'}))['payment_status'] == 'refunded'


@pytest.mark.asyncio
async def test_transfer_failure_rolls_back_target_order_and_source_table(service, db, monkeypatch):
    await menu(db)
    await db.table_layouts.insert_many([{'id': str(i), 'tenant_id': 't', 'outlet_id': 'bar', 'table_number': str(i), 'status': 'available'} for i in (1, 2)])
    created = await service.create_order(ctx(), 'bar', '1', [{'item_id': 'tea', 'quantity': 1}])
    original = type(db.kitchen_orders).update_many
    async def fail_kitchen(self, *args, **kwargs):
        if self.name == 'kitchen_orders':
            raise RuntimeError('kitchen update unavailable')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(type(db.kitchen_orders), 'update_many', fail_kitchen)
    with pytest.raises(RuntimeError):
        await service.transfer_order_table(ctx(), created.data['order_id'], '2')
    assert (await db.pos_orders.find_one({}))['table_number'] == '1'
    assert (await db.table_layouts.find_one({'table_number': '1'}))['status'] == 'occupied'
    assert (await db.table_layouts.find_one({'table_number': '2'}))['status'] == 'available'


@pytest.mark.asyncio
async def test_void_and_payment_race_cannot_leave_a_paid_void_order(service, db, monkeypatch):
    await menu(db)
    monkeypatch.setattr('core.integrations.operational_gl_bridge.post_direct_pos_to_gl', AsyncMock())
    created = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    oid = created.data['order_id']
    await asyncio.gather(service.void_order(ctx(), oid, 'İptal'), service.close_order(ctx(), oid, idempotency_key='pay-once'))
    order = await db.pos_orders.find_one({'id': oid})
    count = await db.pos_transactions.count_documents({'status': 'completed'})
    assert (order['status'], count) in {('voided', 0), ('closed', 1)}
    if count:
        assert order['payment_status'] == 'paid'


@pytest.mark.asyncio
async def test_reversal_committed_during_post_is_reconciled_after_insert(db, monkeypatch):
    monkeypatch.setattr(pos_folio_consumer, 'get_system_db', lambda: db)
    await db.folios.insert_one({'tenant_id': 't', 'id': 'folio', 'status': 'open', 'balance': 0})
    original = type(db.folio_charges).insert_one
    async def interleave(self, doc, *args, **kwargs):
        if self.name == 'folio_charges':
            reverse = {'tenant_id': 't', 'entity_id': 'o', 'event_type': POS_CHARGE_REVERSED,
                       'payload': {'source_pos_order_id': 'o', 'folio_id': 'folio'}}
            await db.outbox_events.insert_one(reverse)
            await pos_folio_consumer.handle_ic_pos_event(reverse)
        return await original(self, doc, *args, **kwargs)
    monkeypatch.setattr(type(db.folio_charges), 'insert_one', interleave)
    event = {'tenant_id': 't', 'event_type': POS_CHARGE_POSTED, 'payload': {'folio_id': 'folio', 'source_pos_order_id': 'o',
        'charges': [{'tenant_id': 't', 'folio_id': 'folio', 'source_pos_order_id': 'o', 'line_no': 0, 'total': 110}]}}
    assert (await pos_folio_consumer.handle_ic_pos_event(event))[0]
    assert (await db.folios.find_one({'id': 'folio'}))['balance'] == 0
    assert (await db.folio_charges.find_one({}))['voided'] is True


@pytest.mark.asyncio
async def test_parallel_print_dispatch_has_only_one_side_effect_and_no_automatic_uncertain_retry(db, monkeypatch):
    monkeypatch.setattr(pos_print_spool, 'db', db)
    dispatch = AsyncMock(return_value={'ok': False, 'reason': 'uncertain write'})
    monkeypatch.setattr(pos_print_spool, '_dispatch', dispatch)
    await db.print_jobs.insert_one({'tenant_id': 't', 'id': 'print', 'status': 'pending', 'rendered_bytes': b'x'})
    await asyncio.gather(*(pos_print_spool.dispatch_job('print', SimpleNamespace(tenant_id='t')) for _ in range(5)))
    assert dispatch.await_count == 1
    assert (await db.print_jobs.find_one({}))['status'] == 'failed'
    result = await pos_print_spool.dispatch_job('print', SimpleNamespace(tenant_id='t'))
    assert not result['success'] and dispatch.await_count == 1


@pytest.mark.asyncio
async def test_guest_rate_limit_cannot_be_bypassed_by_retrying_a_rejected_intent(guest, db):
    # Succeed with 10 distinct requests, then reject the 11th on every retry.
    for index in range(10):
        result = await guest.post('/api/public/fnb/t/bar/order', json=guest_body(f'guest-limit-{index}'))
        assert result.status_code == 200, result.text
        if index == 0:
            limiter = await db.pos_guest_limits.find_one({})
            assert limiter['expires_at'].replace(tzinfo=UTC) > datetime.now(UTC)
    for _ in range(2):
        result = await guest.post('/api/public/fnb/t/bar/order', json=guest_body('guest-limit-eleven'))
        assert result.status_code == 429
    assert (await db.pos_orders.find_one({}))['grand_total'] == 1100


@pytest.mark.asyncio
async def test_table_bill_uses_tax_discount_and_service_total_not_subtotal(service, db, monkeypatch):
    await menu(db)
    await db.table_layouts.insert_one({'id': 'table', 'tenant_id': 't', 'outlet_id': 'bar', 'table_number': '1', 'status': 'available'})
    created = await service.create_order(ctx(), 'bar', '1', [{'item_id': 'tea', 'quantity': 1}])
    await service.apply_order_adjustment(ctx(), created.data['order_id'], 'discount', 'percentage', 10, 'Misafir indirimi')
    monkeypatch.setattr(table_router, 'db', db)
    result = await table_router.get_table_layout('bar', SimpleNamespace(tenant_id='t', id='manager'))
    assert result['tables'][0]['current_bill'] == 99  # subtotal=100 is not the payable bill


@pytest.mark.asyncio
async def test_operations_does_not_truncate_counts_or_call_legacy_unknown_prices_zero(db, monkeypatch):
    monkeypatch.setattr('core.database.db', db)
    await db.pos_orders.insert_many([{'id': str(index), 'tenant_id': 't', 'status': 'pending',
        'payment_status': 'unpaid', 'grand_total': 10, 'currency': 'EUR'} for index in range(501)])
    await db.kitchen_orders.insert_many([{'tenant_id': 't', 'status': 'pending'} for _ in range(1001)])
    result = await pos_fnb_router_v2.pos_operations_summary(None, SimpleNamespace(tenant_id='t'))
    assert result['open_check_count'] == 501 and result['open_check_total'] == 5010
    assert result['kitchen_open_count'] == 1001
    await db.pos_orders.insert_one({'id': 'legacy', 'tenant_id': 't', 'status': 'pending', 'total_amount': 50})
    result = await pos_fnb_router_v2.pos_operations_summary(None, SimpleNamespace(tenant_id='t'))
    assert result['pricing_unverified_count'] == 1 and result['open_check_total'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('amount', [None, 'invalid', -1, float('inf')])
async def test_malformed_old_order_cannot_close_as_zero_or_negative(service, db, amount):
    await db.pos_orders.insert_one({'tenant_id': 't', 'id': 'old', 'status': 'pending', 'payment_status': 'unpaid', 'grand_total': amount})
    result = await service.close_order(ctx(), 'old')
    assert not result.ok and result.code == 'ORDER_PRICING_INVALID'
    assert await db.pos_transactions.count_documents({}) == 0
