"""Paid-service fee cancellation on disposable LOCAL Mongo; no payment/refund created."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.laundry_tax import laundry_tax_snapshot
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401
from tests.test_laundry_delivery_acceptance import laundry as laundry  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def delivered(acceptance, laundry):  # noqa: F811
    a = acceptance
    for name in ('invoices', 'gl_journal_entries', 'billing_concessions'):
        await a.db.create_collection(name)
    # Immutable VAT-inclusive source price is 15 USD, net12.50/VAT2.50.
    tax = laundry_tax_snapshot([{'total': 15, 'vat_rate': 20}], 'USD')
    await a.db.tenant_settings.update_one({'tenant_id': 'qa', 'laundry_orders.id': 'wash'},
        {'$set': {'laundry_orders.$.tax_snapshot': tax, 'laundry_orders.$.items': [{'name': 'Gömlek', 'quantity': 1, 'total': 15, 'vat_rate': 20}]}})
    response = await a.api.patch('/api/laundry/orders/wash', json={'status': 'delivered'})
    assert response.status_code == 200, response.text
    return response.json()


def intent(**changes):
    return {'request_id': str(uuid4()), 'expected_amount': 15, 'currency': 'USD',
        'reason': 'Sentetik ücret iptali; hizmet teslim kaydı korunacak', **changes}


async def void(a, body):
    return await a.api.post('/api/laundry/orders/wash/void-charge', json=body)


async def test_void_keeps_source_price_and_delivery_and_replays_one_reversal(acceptance):
    a = acceptance
    original = await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'})
    body = intent()
    results = await asyncio.gather(void(a, body), void(a, body))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert sum(not r.json()['replayed'] for r in results) == 1
    result = results[0].json()
    assert result['voided_amount'] == 15 and result['folio_balance'] == 560 and not result['new_payment_or_refund']
    settings = await a.db.tenant_settings.find_one({'tenant_id': 'qa'})
    source = next(r for r in settings['laundry_orders'] if r['id'] == 'wash')
    assert source['status'] == 'delivered' and source['total'] == 15 and source['financial_voided']
    assert source['folio_financial_total'] == 0
    current = await a.db.folio_charges.find_one({'id': original['id']})
    for field in ('id', 'amount', 'total', 'currency', 'tax_snapshot', 'vat_amount', 'business_date'):
        assert current.get(field) == original.get(field)
    assert current['voided']
    entries = await a.db.folio_ledger.find({}).to_list(None)
    assert len(entries) == 2 and sum(e['amount'] for e in entries) == 0
    reversal = next(e for e in entries if e['entry_type'] == 'void')
    assert reversal['net_amount'] == -12.5 and reversal['vat_amount'] == -2.5
    assert await a.db.payments.count_documents({}) == 0
    assert await a.db.audit_logs.count_documents({'action': 'laundry_charge_voided'}) == 1
    assert (await a.api.patch('/api/laundry/orders/wash', json={'status': 'delivered'})).status_code == 409
    assert await a.db.folio_charges.count_documents({'source_laundry_order_id': 'wash'}) == 1


@pytest.mark.parametrize('change', [
    {'expected_amount': 16}, {'currency': 'EUR'}, {'reason': ' '},
])
async def test_changed_source_expectation_or_invalid_reason_does_not_cancel(acceptance, change):
    a = acceptance
    response = await void(a, intent(**change))
    assert response.status_code in {409, 422}, response.text
    assert not (await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'}))['voided']
    assert await a.db.folio_ledger.count_documents({}) == 1


@pytest.mark.parametrize('kind', ['closed_folio', 'checked_out', 'closed_day', 'invoice', 'gl', 'concession', 'paid', 'moved_ledger', 'closed_period'])
async def test_protected_money_and_history_remain_unchanged(acceptance, kind):
    a = acceptance
    charge = await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'})
    if kind == 'closed_folio':
        await a.db.folios.update_one({'id': charge['folio_id']}, {'$set': {'status': 'closed'}})
    elif kind == 'checked_out':
        await a.db.bookings.update_one({'id': charge['booking_id']}, {'$set': {'status': 'checked_out'}})
    elif kind == 'closed_day':
        await a.db.night_audit_runs.insert_one({'tenant_id': 'qa', 'business_date': charge['business_date'], 'status': 'completed'})
    elif kind == 'invoice':
        await a.db.invoices.insert_one({'tenant_id': 'qa', 'booking_id': charge['booking_id'], 'status': 'issued'})
    elif kind == 'gl':
        await a.db.gl_journal_entries.insert_one({'tenant_id': 'qa', 'idempotency_key': 'operational-daily:' + charge['business_date']})
    elif kind == 'concession':
        await a.db.billing_concessions.insert_one({'tenant_id': 'qa', 'folio_id': charge['folio_id'], 'status': 'applied'})
    elif kind == 'paid':
        await a.db.payments.insert_one({'tenant_id': 'qa', 'booking_id': charge['booking_id'], 'folio_id': charge['folio_id'], 'amount': 15, 'currency': 'USD', 'method': 'cash', 'status': 'paid'})
    elif kind == 'closed_period':
        await a.db.gl_periods.insert_one({'tenant_id': 'qa', 'start_date': '2026-10-01', 'end_date': '2026-10-31', 'status': 'closed'})
    else:
        await a.db.folio_ledger.update_one({'id': charge['source_ledger_entry_id']}, {'$set': {'folio_id': 'previous-owner'}})
    before = deepcopy(await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'}))
    response = await void(a, intent())
    assert response.status_code == 409, response.text
    assert await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'}) == before
    assert await a.db.folio_ledger.count_documents({}) == 1


async def test_audit_failure_rolls_back_source_ledger_charge_and_balance(acceptance, monkeypatch):
    from core import laundry_charge_void as service
    a = acceptance
    before = deepcopy(await a.db.tenant_settings.find_one({'tenant_id': 'qa'}))
    monkeypatch.setattr(service, 'append_audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await void(a, intent())
    assert await a.db.tenant_settings.find_one({'tenant_id': 'qa'}) == before
    assert not (await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'}))['voided']
    assert await a.db.folio_ledger.count_documents({}) == 1


async def test_foreign_tenant_and_unauthorized_role_cannot_cancel(acceptance):
    a = acceptance
    a.user.tenant_id = 'other'
    assert (await void(a, intent())).status_code == 404
    a.user.tenant_id = 'qa'
    a.user.role = 'housekeeping'
    assert (await void(a, intent())).status_code == 403
    assert not (await a.db.folio_charges.find_one({'source_laundry_order_id': 'wash'}))['voided']


async def test_changed_retry_cannot_create_a_second_reversal(acceptance):
    a = acceptance
    request = intent()
    assert (await void(a, request)).status_code == 200
    changed = await void(a, {**request, 'reason': 'Başka gerekçe ile ikinci iptal'})
    assert changed.status_code == 409
    assert await a.db.folio_ledger.count_documents({'entry_type': 'void'}) == 1
