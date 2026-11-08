"""Standalone SPA acceptance: isolated local replica only, never live money."""
import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.spa import finance
from domains.spa import router as spa
from modules.pms_core.reporting_ledger import posted_revenue_rows
from tests.test_spa_real_folio_replica import db, user, wired  # noqa: F401


@pytest.fixture
async def external(wired):  # noqa: F811
    await wired.create_collection('extra_charges')
    await wired.spa_appointments.update_one({'id': 'a'}, {
        '$unset': {'reservation_id': '', 'folio_id': ''},
        '$set': {'charge_to_room': False, 'guest_name': 'Aslı Bayraktar',
                 'starts_at': '2026-10-25T12:30:00+00:00'},
    })
    return wired


async def test_external_completion_posts_spa_receivable_without_room_or_payment(external):
    await spa.change_status('a', spa.StatusUpdate(status='completed'), current_user=user())
    charge = await external.extra_charges.find_one({'source_spa_appointment_id': 'a'})
    assert charge is not None, 'Completed nonresident SPA needs a real independent revenue source'
    assert (charge['amount'], charge['vat_amount'], charge['total']) == (1250, 250, 1500)
    assert charge['charge_category'] == 'spa' and charge['business_date'] == '2026-10-25'
    assert not charge.get('booking_id') and not charge.get('folio_id')
    assert await external.folio_charges.count_documents({}) == 0
    assert await external.payments.count_documents({}) == 0
    assert (await external.folios.find_one({'id': 'actual-folio'}))['balance'] == 0
    rows = await posted_revenue_rows('t', date(2026, 10, 25), date(2026, 10, 25), database=external)
    assert len(rows) == 1 and rows[0]['total'] == 1500 and rows[0]['charge_category'] == 'spa'


async def test_external_source_is_in_spa_summary_not_unposted_catalog_value(external):
    await spa.change_status('a', spa.StatusUpdate(status='completed'), current_user=user())
    summary = await spa.daily_summary('2026-10-25', user())
    assert summary['revenue_by_currency'] == {'TRY': 1500}
    assert summary['unposted_appointments'] == 0 and summary['revenue_complete']


def test_external_manual_receipts_have_tenant_scoped_normal_routes():
    paths = {route.path for route in spa.router.routes}
    assert '/api/spa/appointments/{appt_id}/settlements' in paths


@pytest.fixture
async def financial(external, monkeypatch):
    monkeypatch.setattr(finance, 'get_system_db', lambda: external)
    for name in ('cashier_shifts', 'cash_flow', 'bank_accounts', 'gl_accounts', 'gl_journal_entries'):
        await external.create_collection(name)
    await external.gl_accounts.insert_many([{'tenant_id': 't', 'code': code, 'name': code, 'active': True, 'type': 'asset'}
        for code in ('100', '102', '108', '120')])
    await external.gl_operational_mappings.insert_one({'tenant_id': 't', 'enabled': True})
    await external.cashier_shifts.insert_one({'_id': 'shift', 'tenant_id': 't', 'status': 'open',
        'business_date': '2026-10-25', 'cash_in': 0, 'cash_out': 0, 'transactions': []})
    await spa.change_status('a', spa.StatusUpdate(status='completed'), user())
    return external


def request(**extra):
    return finance.SettlementIn(**{'request_id': 'spa-receipt-001', 'amount': 100, 'method': 'cash',
        'reference': 'SPA-001', 'reason': 'Synthetic local manual receipt', **extra})


async def test_cash_partial_refund_receipt_gl_and_cashier_are_not_room_money(financial, monkeypatch):
    first = await finance.record_settlement('a', request(), user())
    assert (await finance.record_settlement('a', request(), user()))['replayed']
    for i, amount in enumerate((30, 70)):
        await finance.record_settlement('a', request(request_id=f'spa-refund-{i}', kind='refund', amount=amount,
            original_payment_id=first['payment']['id']), user())
    result = await finance.list_settlements('a', user())
    assert result['totals'] == {'service_total': 1500, 'collected': 100, 'refunded': 100, 'net_collected': 0, 'outstanding': 1500}
    assert len(result['payments']) == 3 and all(p['receipt_number'].startswith('SPA-') for p in result['payments'])
    assert await financial.payments.count_documents({}) == await financial.cash_flow.count_documents({}) == await financial.gl_journal_entries.count_documents({}) == 3
    assert not await financial.payments.count_documents({'$or': [{'folio_id': {'$exists': True}}, {'booking_id': {'$exists': True}}]})
    assert (await financial.folios.find_one({}))['balance'] == 0
    shift = await financial.cashier_shifts.find_one({})
    assert shift['cash_in'] == shift['cash_out'] == 100 and len(shift['transactions']) == 3 and not shift['spa_pending_ids']
    from domains.pms import cashier_service
    monkeypatch.setattr(cashier_service, 'db', financial)
    assert await cashier_service.reconcile_open_shift_payments('t') == 0
    assert all(j['total_debit_minor'] == j['total_credit_minor'] for j in await financial.gl_journal_entries.find({}).to_list(None))


async def test_lost_gl_response_recovers_once_and_blocks_other_request_and_cashier_close(financial, monkeypatch):
    actual = finance.post_journal_entry
    async def lost(*args, **kwargs):
        await actual(*args, **kwargs)
        raise TimeoutError('lost durable GL reply')
    monkeypatch.setattr(finance, 'post_journal_entry', lost)
    with pytest.raises(TimeoutError):
        await finance.record_settlement('a', request(), user())
    assert await financial.gl_journal_entries.count_documents({}) == 1 and not await financial.payments.count_documents({})
    assert (await finance.list_settlements('a', user()))['pending']['request']['request_id'] == 'spa-receipt-001'
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(request_id='spa-other-001'), user())
    assert error.value.status_code == 409
    from domains.pms import cashier_router, cashier_service
    monkeypatch.setattr(cashier_router, 'db', financial)
    monkeypatch.setattr(cashier_service, 'db', financial)
    with pytest.raises(HTTPException) as error:
        await cashier_router.close_shift({'counted_amount': 0}, user())
    assert error.value.status_code == 409
    monkeypatch.setattr(finance, 'post_journal_entry', actual)
    await finance.record_settlement('a', request(), user())
    assert await financial.gl_journal_entries.count_documents({}) == await financial.payments.count_documents({}) == 1


async def test_parallel_collections_cannot_overcollect(financial):
    results = await asyncio.gather(*[finance.record_settlement('a', request(request_id=f'parallel-{i}', amount=1000), user()) for i in range(2)], return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
    assert await financial.payments.count_documents({}) == 1


@pytest.mark.parametrize('changes,code', [({'method': 'bank_transfer', 'bank_account_id': 'other-tenant'}, 422),
    ({'exchange_rate': 2}, 422), ({'amount': 1501}, 409), ({'amount': .001}, 422)])
async def test_invalid_money_never_claims_or_posts(financial, changes, code):
    await financial.bank_accounts.insert_one({'id': 'other-tenant', 'tenant_id': 'other', 'currency': 'TRY'})
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(**changes), user())
    assert error.value.status_code == code
    assert not await financial.payments.count_documents({}) and not await financial.gl_journal_entries.count_documents({})
    assert not (await financial.spa_appointments.find_one({'id': 'a'})).get('finance_pending')


async def test_missing_cash_shift_or_legacy_completed_cannot_receive(financial):
    await financial.cashier_shifts.update_one({}, {'$set': {'status': 'closed'}})
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(), user())
    assert error.value.status_code == 409
    await financial.spa_appointments.update_one({'id': 'a'}, {'$unset': {'external_charge_id': ''}})
    with pytest.raises(HTTPException) as error:
        await finance.list_settlements('a', user())
    assert error.value.status_code == 409


async def test_unknown_vat_rolls_back_external_completion(external):
    await external.spa_appointments.update_one({'id': 'a'}, {'$unset': {'tax_rate': ''}})
    with pytest.raises(HTTPException) as error:
        await spa.change_status('a', spa.StatusUpdate(status='completed'), user())
    assert error.value.status_code == 409
    assert (await external.spa_appointments.find_one({'id': 'a'}))['status'] == 'scheduled'
    assert not await external.extra_charges.count_documents({})


async def test_new_appointment_requires_explicit_service_vat_before_source_creation(external, monkeypatch):
    monkeypatch.setattr(spa, '_ensure_indexes', AsyncMock())
    await external.spa_services.insert_one({'tenant_id': 't', 'id': 'service', 'price': 100, 'name': 'Bakım', 'duration_minutes': 60})
    with pytest.raises(HTTPException) as error:
        await spa.create_appointment(spa.AppointmentIn(service_id='service', starts_at='2026-11-08T12:00:00Z', guest_name='Selin Kaya'), user())
    assert error.value.status_code == 409
    assert await external.spa_appointments.count_documents({}) == 1


async def test_request_key_payload_change_and_excess_refund_are_rejected(financial):
    first = (await finance.record_settlement('a', request(), user()))['payment']
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(amount=101), user())
    assert error.value.status_code == 409


async def test_generic_folio_void_cannot_orphan_spa_cash_and_gl(financial, monkeypatch):
    from domains.pms.misc import payments_folio
    first = (await finance.record_settlement('a', request(), user()))['payment']
    monkeypatch.setattr(payments_folio, 'db', financial)
    with pytest.raises(HTTPException) as error:
        await payments_folio.void_payment(first['id'], current_user=user())
    assert error.value.status_code == 409
    assert not (await financial.payments.find_one({'id': first['id']}))['voided']
    assert (await financial.cashier_shifts.find_one({}))['cash_in'] == 100
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(request_id='refund-excess-001', kind='refund', amount=101,
            original_payment_id=first['id']), user())
    assert error.value.status_code == 409


async def test_tenant_and_staff_cannot_read_or_write(financial):
    outsider = user()
    outsider.tenant_id = 'other'
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(), outsider)
    assert error.value.status_code == 404
    staff = user()
    staff.role = 'housekeeping'
    with pytest.raises(HTTPException) as error:
        await finance.list_settlements('a', staff)
    assert error.value.status_code == 403


async def test_audit_failure_rolls_back_financial_rows_then_same_gl_recovers(financial, monkeypatch):
    actual = finance.audit_log
    monkeypatch.setattr(finance, 'audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError):
        await finance.record_settlement('a', request(), user())
    assert not await financial.payments.count_documents({}) and not await financial.cash_flow.count_documents({})
    assert (await financial.cashier_shifts.find_one({}))['cash_in'] == 0
    monkeypatch.setattr(finance, 'audit_log', actual)
    await finance.record_settlement('a', request(), user())
    assert await financial.gl_journal_entries.count_documents({}) == await financial.payments.count_documents({}) == 1


async def test_night_audit_accrues_external_sale_once_not_already_posted_receipt(financial):
    from core.integrations import operational_gl_bridge as bridge
    from core.integrations.operational_gl_valuation import daily_sources
    await financial.gl_accounts.insert_many([{'tenant_id': 't', 'code': c, 'name': c, 'active': True, 'type': 'revenue' if c == '600' else 'liability'} for c in ('600', '391')])
    await finance.record_settlement('a', request(amount=1500), user())
    # A generic extra charge must not suddenly acquire this new SPA GL path.
    await financial.extra_charges.insert_one({'id': 'unrelated', 'tenant_id': 't', 'business_date': '2026-10-25', 'total': 999, 'currency': 'TRY'})
    result = await bridge.post_night_audit_daily_to_gl(financial, 't', '2026-10-25', run_id='audit')
    assert result['status'] == 'posted'
    entry = await financial.gl_journal_entries.find_one({'source': 'night_audit'})
    values = {r['account_code']: (r['debit'], r['credit']) for r in entry['lines']}
    assert values == {'120': (1500, 0), '600': (0, 1250), '391': (0, 250)}
    assert await financial.gl_journal_entries.count_documents({}) == 2
    charges, payments, _ = await daily_sources(financial, 't', '2026-10-25')
    assert len(charges) == 1 and charges[0]['source'] == 'spa_external' and not payments


async def test_foreign_bank_collection_requires_source_valuation_and_refunds_original_rate(financial):
    from core.integrations.operational_gl_valuation import normalized_valuation, build_plan
    from core.integrations.operational_gl_bridge import DEFAULT_MAPPING
    from shared_kernel.gl_posting import post_journal_entry
    await financial.spa_appointments.update_one({'id': 'a'}, {'$set': {'currency': 'EUR'}})
    await financial.extra_charges.update_one({'source_spa_appointment_id': 'a'}, {'$set': {'currency': 'EUR'}})
    await financial.bank_accounts.insert_one({'tenant_id': 't', 'id': 'bank', 'currency': 'EUR', 'balance': 0})
    await financial.gl_accounts.insert_many([{'tenant_id': 't', 'code': c, 'name': c, 'active': True, 'type': 'revenue' if c == '600' else 'liability'} for c in ('600', '391')])
    args = {'method': 'bank_transfer', 'bank_account_id': 'bank', 'exchange_rate': 40}
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(**args), user())
    assert error.value.status_code == 409 and not await financial.payments.count_documents({})
    charge = await financial.extra_charges.find_one({'source_spa_appointment_id': 'a'})
    plan = build_plan([charge], [], {**DEFAULT_MAPPING, 'enabled': True}, normalized_valuation('2026-10-25',
        {'base_currency': 'TRY', 'business_date': '2026-10-25', 'reference': 'Synthetic fixed valuation only', 'rates_to_try': {'EUR': 40}}))
    entry = await post_journal_entry(financial, 't', date='2026-10-25', memo='Synthetic source valuation', lines=plan['lines'],
        source='night_audit', source_ref='valued', actor='manager', idempotency_key='valued-source', source_manifest=plan['manifest'])
    await financial.night_audit_runs.insert_one({'tenant_id': 't', 'id': 'valued', 'business_date': '2026-10-25', 'gl_valued_entry_id': entry['id']})
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement('a', request(**{**args, 'exchange_rate': 41}), user())
    assert error.value.status_code == 409
    first = (await finance.record_settlement('a', request(**args), user()))['payment']
    await finance.record_settlement('a', request(request_id='foreign-refund-001', kind='refund', amount=25,
        original_payment_id=first['id'], **{**args, 'exchange_rate': None}), user())
    assert (await financial.bank_accounts.find_one({'id': 'bank'}))['balance'] == 75
    assert sum(p['reporting_amount'] for p in await financial.payments.find({}).to_list(None)) == 3000
    assert await financial.folio_charges.count_documents({}) == 0
