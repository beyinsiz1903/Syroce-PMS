"""Presentation defects reproduced against isolated LOCAL MongoDB, never live data."""
import asyncio
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from common.context import OperationContext
from core import pos_folio_consumer, tenant_db
from domains.pms.pos_fnb.analytics import snapshot
from domains.pms.pos_fnb.check_split import preview
from domains.pms.pos_fnb.folio_lines import checkout_lines
from domains.pms.pos_fnb.guest_qr import table_token
from domains.pms.pos_fnb.report_adapters import report
from domains.pms.pos_fnb.reservation_store import create
from domains.pms.pos_fnb_router import guest_menu, reservations
from modules.pms_core.reporting_ledger import posted_revenue_rows
from modules.pms_core.revenue_report import build_revenue_report
from tests.test_pos_final_consistency_replica import db, service  # noqa: F401

DAY = '2026-10-25'


def ctx():
    return OperationContext(tenant_id='t', actor_id='manager', actor_role='admin')


def sale(oid='cash', total=110, category='beverage', method='cash'):
    return {'tenant_id': 't', 'id': 'tx-' + oid, 'order_id': oid, 'outlet_id': 'bar',
        'status': 'completed', 'currency': 'EUR', 'transaction_date': DAY, 'created_at': '2026-10-26T10:00:00Z',
        'amount': total, 'total_amount': total, 'tax_amount': round(total / 11, 2), 'payment_method': method,
        'order_items': [{'item_id': 'tea', 'item_name': 'Çay', 'category': category, 'quantity': 1,
                        'total': round(total / 1.1, 2), 'unit_price': round(total / 1.1, 2), 'tax_rate': .1}]}


@pytest.mark.parametrize('discount,service_amount', [(0, 0), (33, 5), (330, 0)])
def test_folio_lines_conserve_net_vat_gross_and_discount(discount, service_amount):
    row = sale(total=330)
    row['order_items'] = [dict(row['order_items'][0]), {**row['order_items'][0], 'item_id': 'cake', 'category': 'dessert', 'total': 200}]
    row['order_items'][0]['total'] = 100
    row.update(amount=330 - discount + service_amount, tax_amount=round(30 * (330 - discount) / 330, 2),
               discount_amount=discount, service_charge_amount=service_amount)
    lines = checkout_lines(row)
    assert sum(Decimal(str(r['total'])) for r in lines) == Decimal(str(row['amount']))
    assert sum(Decimal(str(r['vat_amount'])) for r in lines) == Decimal(str(row['tax_amount']))
    assert all(Decimal(str(r['amount'])) + Decimal(str(r['vat_amount'])) == Decimal(str(r['total'])) for r in lines)
    assert all(r['tax_amount'] == 0 and r['subtotal'] - r['discount_amount'] == pytest.approx(r['amount']) for r in lines)
    assert {r['charge_category'] for r in lines} >= {'beverage', 'dessert'}


async def menu_and_booking(db, currency='EUR'):
    await db.pos_outlets.insert_one({'tenant_id': 't', 'id': 'bar'})
    await db.pos_menu_items.insert_one({'tenant_id': 't', 'id': 'tea', 'outlet_id': 'bar', 'name': 'Çay', 'price': 100, 'tax_rate': .1, 'category': 'beverage'})
    await db.bookings.insert_one({'tenant_id': 't', 'id': 'booking', 'status': 'checked_in', 'currency': currency})
    await db.folios.insert_one({'tenant_id': 't', 'id': 'folio', 'booking_id': 'booking', 'folio_type': 'guest', 'status': 'open', 'currency': currency})


async def test_room_currency_mismatch_never_creates_payment_or_outbox(service, db):
    await menu_and_booking(db, 'USD')
    made = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    result = await service.close_order(ctx(), made.data['order_id'], 'room_charge', post_to_folio=True, booking_id='booking')
    assert not result.ok and result.code == 'FOLIO_CURRENCY_MISMATCH'
    assert await db.pos_transactions.count_documents({}) == 0
    assert await db.outbox_events.count_documents({}) == 0


async def test_room_lines_are_posted_once_with_known_vat_and_reversed_together(service, db, monkeypatch):
    await menu_and_booking(db)
    made = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}, {'item_id': 'tea', 'quantity': 2}])
    oid = made.data['order_id']
    result = await service.close_order(ctx(), oid, 'room_charge', post_to_folio=True, booking_id='booking')
    assert result.ok
    event = await db.outbox_events.find_one({'event_type': 'pos.charge.posted.v1'})
    assert len(event['payload']['charges']) == 2
    assert sum(row['amount'] for row in event['payload']['charges']) == 300
    assert sum(row['vat_amount'] for row in event['payload']['charges']) == 30
    monkeypatch.setattr(pos_folio_consumer, 'get_system_db', lambda: db)
    for _ in range(2):
        assert (await pos_folio_consumer.handle_ic_pos_event(event))[0]
    assert await db.folio_charges.count_documents({}) == 2
    assert (await db.folios.find_one({'id': 'folio'}))['balance'] == 330
    assert (await service.refund_order(ctx(), oid, None, 'Misafir talebi', 'refund-all')).ok
    reversal = await db.outbox_events.find_one({'event_type': 'pos.charge.reversed.v1'})
    assert (await pos_folio_consumer.handle_ic_pos_event(reversal))[0]
    assert (await db.folios.find_one({'id': 'folio'}))['balance'] == 0


async def test_legacy_pos_folio_view_uses_exact_sale_evidence_without_rewriting(db):
    txn = sale('room', 220, method='room_charge')
    await db.pos_transactions.insert_one(dict(txn))
    original = {'tenant_id': 't', 'id': 'legacy-charge', 'source_pos_order_id': 'room', 'currency': 'EUR',
        'business_date': DAY, 'charge_category': 'food', 'amount': 220, 'total': 220, 'tax_amount': 20}
    await db.folio_charges.insert_one(deepcopy(original))
    rows = await posted_revenue_rows('t', date.fromisoformat(DAY), date.fromisoformat(DAY), database=db)
    result = build_revenue_report(rows, date.fromisoformat(DAY), date.fromisoformat(DAY))
    assert result['reconciliation']['issue_count'] == 0
    assert result['totals']['total'] == 220 and result['totals']['net'] == 200 and result['totals']['vat'] == 20
    assert result['rows'][0]['category'] == 'beverage'
    stored = await db.folio_charges.find_one({'id': 'legacy-charge'}, {'_id': 0})
    assert stored == original
    await db.pos_transactions.update_one({'id': txn['id']}, {'$set': {'tax_amount': 19}})
    rows = await posted_revenue_rows('t', date.fromisoformat(DAY), date.fromisoformat(DAY), database=db)
    assert build_revenue_report(rows, date.fromisoformat(DAY), date.fromisoformat(DAY))['reconciliation']['issue_count'] == 1


async def seed_reports(db):
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': DAY}})
    cash, room = sale(), sale('room', 220, category='food', method='room_charge')
    refund = {'tenant_id': 't', 'id': 'refund', 'order_id': 'cash', 'original_transaction_id': cash['id'],
        'transaction_date': DAY, 'created_at': '2026-10-26T11:00:00Z', 'status': 'refunded', 'payment_type': 'refund', 'payment_method': 'cash', 'total_amount': -110}
    await db.pos_transactions.insert_many([deepcopy(cash), deepcopy(room), refund])
    await db.pos_menu_transactions.insert_one({**cash, 'id': 'mirror'})
    await db.pos_transactions.insert_one({**cash, 'tenant_id': 'other', 'id': 'foreign-tenant', 'order_id': 'other'})
    await db.folio_charges.insert_one({'tenant_id': 't', 'id': 'room-charge', 'business_date': DAY, 'source_pos_order_id': 'room',
        'currency': 'EUR', 'charge_category': 'food', 'amount': 220, 'total': 220, 'tax_amount': 20})
    await db.pos_menu_items.insert_one({'tenant_id': 't', 'id': 'tea', 'cost': 20})


@pytest.mark.parametrize('kind,key', [('sales', 'summary'), ('dashboard', 'summary'), ('performance', None),
    ('breakdown', 'summary'), ('mobile', 'orders'), ('engineering', 'totals'), ('chart', 'summary')])
async def test_reports_share_business_day_source_dedupe_room_and_refund(db, kind, key):
    await seed_reports(db)
    result = await report(db, 't', kind, DAY, DAY)
    body = result[key] if key else result
    field = 'total_sales' if kind == 'sales' else 'revenue' if kind == 'engineering' else 'total_revenue'
    assert body[field] == 220
    assert result['period']['start_date'] == result['period']['end_date'] == DAY
    if kind == 'performance':
        assert sum(row['quantity_sold'] for row in body['top_performers']) == 1
    if kind == 'sales':
        assert body['food_sales'] == 220 and body['beverage_sales'] == 0


async def test_invalid_report_range_is_rejected(db):
    with pytest.raises(HTTPException):
        await snapshot(db, 't', '2026-10-26', DAY)


async def test_two_currency_pos_revenue_is_not_added(db):
    await db.pos_transactions.insert_many([sale(), {**sale('usd'), 'currency': 'USD'}])
    result = await snapshot(db, 't', DAY, DAY)
    assert result['total_revenue'] is None
    assert set(result['totals_by_currency']) == {'EUR', 'USD'}
    for kind in ('sales', 'dashboard', 'chart', 'mobile', 'breakdown', 'performance', 'engineering'):
        view = await report(db, 't', kind, DAY, DAY)
        assert view['requires_currency_selection']
        assert view['summary']['total_revenue'] is None
        assert view['menu_items'] == [] and view['chart_data'] == []


async def test_registered_reports_use_canonical_snapshot_and_business_date(db, monkeypatch):
    from domains.pms import marketplace_router
    from domains.pms.pos_fnb_router import fnb_reports, pos_core as fnb_core
    from domains.pms.pos_router import pos_core
    await seed_reports(db)
    await db.pos_outlets.insert_one({'tenant_id': 't', 'id': 'bar', 'outlet_name': 'Teras Restoran'})
    user = SimpleNamespace(tenant_id='t', id='manager', role='admin')
    for module in (marketplace_router, fnb_reports, fnb_core, pos_core):
        monkeypatch.setattr(module, 'db', db)
        monkeypatch.setattr(module, 'get_current_user', AsyncMock(return_value=user))
    # Endpoint default must follow PMS day, not the computer's current date.
    engineering = await fnb_core.get_menu_engineering(current_user=user)
    assert engineering['period']['end_date'] == DAY
    assert engineering['totals']['revenue'] == 220
    sales = await fnb_reports.get_fnb_sales_report(DAY, DAY, None)
    assert sales['summary']['total_sales'] == 220
    mobile = await marketplace_router.get_fnb_daily_summary_mobile(DAY, None)
    assert mobile['orders']['total_revenue'] == 220
    assert mobile['orders']['by_outlet'] == {'bar': {'count': 2, 'revenue': 220}}
    assert mobile['stock_consumption']['total_cost'] is None
    breakdown = await marketplace_router.get_menu_sales_breakdown(None, DAY, DAY, user)
    assert breakdown['summary']['total_revenue'] == 220
    assert breakdown['by_outlet'] == [{'outlet_id': 'bar', 'outlet_name': 'Teras Restoran', 'revenue': 220}]
    outlets = await marketplace_router.get_outlets(user)
    assert outlets['outlets'][0]['today_transactions'] == 2
    summary = await pos_core.get_pos_daily_summary(DAY, None, user)
    assert summary['total_sales'] == 220
    assert sum(item['quantity'] for item in summary['top_items']) == 1
    await db.pos_orders.insert_one({'id': 'voided', 'tenant_id': 't', 'business_date': DAY, 'status': 'voided', 'total_amount': 100, 'grand_total': 110})
    voids = await pos_core.get_void_report(DAY, DAY, None)
    z = await pos_core.get_z_report(DAY, None, user)
    assert voids['total_voided_amount'] == z['void_amount'] == 110


async def test_public_qr_works_with_strict_proxy_and_restores_scope(db, service, monkeypatch):
    await menu_and_booking(db)
    table = {'tenant_id': 't', 'outlet_id': 'bar', 'id': 'table', 'table_number': '1', 'status': 'available'}
    await db.table_layouts.insert_one(dict(table))
    monkeypatch.setattr(tenant_db, 'STRICT_TENANT_MODE', True)
    proxy = tenant_db.TenantAwareDBProxy(db)
    monkeypatch.setattr(guest_menu, 'db', proxy)
    monkeypatch.setattr(guest_menu, 'require_tenant_module', AsyncMock())
    monkeypatch.setattr(guest_menu, 'get_tenant_currency', AsyncMock(return_value=('EUR', '€')))
    monkeypatch.setattr(guest_menu, 'PosFnbServiceV2', lambda: service)
    app = FastAPI(); app.include_router(guest_menu.router)
    body = {'table_id': 'table', 'table_token': table_token('t', 'bar', table), 'guest_name': 'Elif Aydın',
            'idempotency_key': 'guest-strict-1', 'items': [{'item_id': 'tea', 'quantity': 1}], 'expected_total': 110}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        made = await client.post('/api/public/fnb/t/bar/order', json=body)
        assert made.status_code == 200, made.text
        repeated = await client.post('/api/public/fnb/t/bar/order', json=body)
        assert repeated.status_code == 200 and repeated.json()['idempotent']
        rejected = await client.post('/api/public/fnb/t/bar/order', json={**body, 'table_token': 'forged'})
        assert rejected.status_code == 403
    assert tenant_db.get_current_tenant_id() is None
    assert await db.pos_orders.count_documents({}) == 1
    assert await db.pos_transactions.count_documents({}) == 0


async def test_reservation_slot_is_atomic_and_table_is_tenant_scoped(db):
    await menu_and_booking(db)
    await db.table_layouts.insert_one({'tenant_id': 't', 'outlet_id': 'bar', 'id': 'table', 'table_number': '1'})
    body = dict(outlet_id='bar', table_id='table', guest_name='Zeynep Kaya', pax=2, res_date=DAY, res_time='19:00')
    results = await asyncio.gather(*(create(db, 't', 'manager', **body) for _ in range(2)), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 1
    assert any(isinstance(row, HTTPException) and row.status_code == 409 for row in results)
    assert await db.pos_table_reservations.count_documents({}) == 1
    with pytest.raises(HTTPException) as error:
        await create(db, 'other', 'manager', **body)
    assert error.value.status_code == 404
    assert all(route.path.startswith('/api/pos/reservations') for route in reservations.router.routes)


def test_split_preview_preserves_paid_source_and_cent_residue():
    original = sale(); original['total_amount'] = 100
    before = deepcopy(original)
    result = preview(original, 'equal', 3)
    assert [row['amount'] for row in result['splits']] == [33.34, 33.33, 33.33]
    assert result['preview_only'] and original == before
    for type_, count, details in [('equal', 0, None), ('custom', 2, {'1': -1, '2': 101}),
                                  ('custom', 2, {'1': 99}), ('by_item', 2, {'1': [0], '2': [0]})]:
        with pytest.raises(HTTPException):
            preview(original, type_, count, details)


async def test_mixed_and_zero_comp_reconcile_without_false_journal_blockers(db, monkeypatch):
    from core.integrations.operational_gl_bridge import DEFAULT_MAPPING, post_direct_pos_to_gl
    from domains.accounting import gl_router
    await db.gl_operational_mappings.insert_one({'tenant_id': 't', **DEFAULT_MAPPING, 'enabled': True})
    await db.gl_accounts.insert_many([{'tenant_id': 't', 'code': code, 'active': True, 'name': code} for code in ('100', '108', '600', '391')])
    mixed = {**sale('mixed', 814, method='mixed'), 'currency': 'TRY', 'payment_breakdown': [{'method': 'cash', 'amount': 407}, {'method': 'card', 'amount': 407}]}
    comp = {**sale('comp', 0), 'currency': 'TRY'}
    await db.pos_transactions.insert_many([deepcopy(mixed), deepcopy(comp)])
    entry = await post_direct_pos_to_gl(db, 't', transaction=mixed, order={}, posted_to_folio=False, actor='manager')
    assert entry['entry']['total_debit'] == 814
    assert (await post_direct_pos_to_gl(db, 't', transaction=comp, order={}, posted_to_folio=False, actor='manager'))['reason'] == 'no_activity'
    monkeypatch.setattr(gl_router, 'db', db)
    result = await gl_router.operational_reconciliation(DAY, SimpleNamespace(tenant_id='t', role='admin'))
    assert result['healthy'], result['blockers']
    assert result['pos']['total'] == result['pos']['gl_total'] == 814
    following = await gl_router.operational_reconciliation('2026-10-26', SimpleNamespace(tenant_id='t', role='admin'))
    assert following['pos']['direct_count'] == 0  # created_at is not a second accounting day
    # A real tender mismatch must still block; do not merely remove warnings.
    await db.pos_transactions.update_one({'id': mixed['id']}, {'$set': {'payment_breakdown.0.amount': 406}})
    result = await gl_router.operational_reconciliation(DAY, SimpleNamespace(tenant_id='t', role='admin'))
    assert any(row['code'] == 'pos_gl_variance' for row in result['blockers'])


async def test_foreign_tender_is_preserved_on_sealed_cash_line(db):
    from core.integrations.operational_gl_bridge import DEFAULT_MAPPING, post_direct_pos_to_gl
    await db.gl_operational_mappings.insert_one({'tenant_id': 't', **DEFAULT_MAPPING, 'enabled': True})
    await db.gl_accounts.insert_many([{'tenant_id': 't', 'code': code, 'active': True, 'name': code} for code in ('100', '600', '391')])
    txn = {**sale('eur', 451), 'currency': 'TRY', 'checkout_quote': {'currency_code': 'EUR', 'base_currency': 'TRY', 'amount_foreign': 8.2, 'rate_used': 55}}
    await db.pos_transactions.insert_one(deepcopy(txn))
    result = await post_direct_pos_to_gl(db, 't', transaction=txn, order={}, posted_to_folio=False, actor='manager')
    cash = next(row for row in result['entry']['lines'] if row['account_code'] == '100')
    assert cash['currency'] == 'EUR' and cash['foreign_amount'] == 8.2 and cash['exchange_rate'] == '55.000000'


async def test_expected_stock_shortage_remains_recoverable_without_error_log(service, db, caplog):
    await menu_and_booking(db)
    await db.ingredients.insert_one({'tenant_id': 't', 'id': 'ingredient', 'current_stock': 0})
    await db.recipes.insert_one({'tenant_id': 't', 'id': 'recipe', 'menu_item_id': 'tea', 'ingredients': [{'ingredient_id': 'ingredient', 'quantity': 1}]})
    made = await service.create_order(ctx(), 'bar', items=[{'item_id': 'tea', 'quantity': 1}])
    result = await service.close_order(ctx(), made.data['order_id'], 'cash')
    assert result.ok
    row = await db.pos_orders.find_one({'id': made.data['order_id']})
    assert row['stock_consumption_status'] == 'failed'
    assert any('awaits operator action' in record.message for record in caplog.records)
    assert not any(record.levelname == 'ERROR' and 'stock' in record.message.lower() for record in caplog.records)
