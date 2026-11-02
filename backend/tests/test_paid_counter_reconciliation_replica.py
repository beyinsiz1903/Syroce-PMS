"""Sealed historical counter reconciliation; disposable loopback DB only."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI

from core.security import get_current_user
from routers.finance import folio
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def closed(acceptance, monkeypatch):
    a = acceptance
    monkeypatch.setattr(folio, 'db', a.db)
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'status': 'checked_out', 'paid_amount': 0}})
    await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'status': 'closed'}})
    await a.db.payments.insert_one({'tenant_id': 'qa', 'id': 'receipt', 'booking_id': 'synthetic-stay',
        'folio_id': 'synthetic-folio', 'currency': 'USD', 'amount': 120, 'method': 'cash', 'status': 'paid'})
    app = FastAPI()
    app.include_router(folio.router, prefix='/api')
    app.dependency_overrides[get_current_user] = lambda: a.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-counter-acceptance') as api:
        yield a, api


PATH = '/api/folio/booking/synthetic-stay/'


async def plan(api):
    result = await api.get(PATH + 'paid-counter-preview')
    assert result.status_code == 200, result.text
    return result.json()


async def apply(api, snapshot):
    return await api.post(PATH + 'reconcile-paid-counter', json={
        'source_revision': snapshot['source_revision'], 'reason': 'Yalnız yerel geçmiş sayaç mutabakatı'})


async def test_preview_apply_reload_and_duplicate_do_not_create_money(closed):
    a, api = closed
    before = await a.db.payments.find({}, {'_id': 0}).to_list(None)
    snapshot = await plan(api)
    assert snapshot['eligible'] and snapshot['ledger_paid_amount'] == 120
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0
    result = await apply(api, snapshot)
    assert result.status_code == 200 and result.json()['applied']
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 120
    assert (await apply(api, snapshot)).status_code == 409
    assert not (await apply(api, await plan(api))).json()['applied']
    assert await a.db.payments.find({}, {'_id': 0}).to_list(None) == before
    assert await a.db.cashier_shifts.count_documents({}) == 0
    assert await a.db.audit_logs.count_documents({'operation_name': 'payment_counter_reconciled'}) == 1


@pytest.mark.parametrize('change,blocker', [
    ({'paid_amount': 150}, 'unexplained_existing_credit'),
    ({'migration_financial_snapshot': {'paid': 25}}, 'imported_opening_credit_requires_review'),
    ({'currency': 'EUR'}, 'mixed_or_unknown_currency'),
    ({'status': 'checked_in'}, 'active_financial_workflow_requires_review'),
])
async def test_unknown_credit_import_currency_or_live_workflow_are_not_rewritten(closed, change, blocker):
    a, api = closed
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': change})
    before = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    snapshot = await plan(api)
    assert not snapshot['eligible'] and blocker in snapshot['blockers']
    assert (await apply(api, snapshot)).status_code == 409
    assert await a.db.bookings.find_one({'id': 'synthetic-stay'}) == before


async def test_voided_failed_and_refund_rows_have_the_correct_net_counter(closed):
    a, api = closed
    await a.db.payments.insert_many([
        {'tenant_id': 'qa', 'id': 'void', 'booking_id': 'synthetic-stay', 'amount': 999, 'voided': True},
        {'tenant_id': 'qa', 'id': 'decline', 'booking_id': 'synthetic-stay', 'amount': 999, 'status': 'failed'},
        {'tenant_id': 'qa', 'id': 'refund', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
            'currency': 'USD', 'amount': 20, 'method': 'cash', 'payment_type': 'refund', 'status': 'paid'},
        {'tenant_id': 'foreign', 'id': 'cross', 'booking_id': 'synthetic-stay', 'currency': 'USD', 'amount': 999, 'method': 'cash'},
    ])
    snapshot = await plan(api)
    assert snapshot['eligible'] and snapshot['ledger_paid_amount'] == 100
    assert (await apply(api, snapshot)).status_code == 200


async def test_source_change_invalidates_the_preview(closed):
    a, api = closed
    snapshot = await plan(api)
    await a.db.payments.update_one({'id': 'receipt'}, {'$set': {'amount': 125}})
    assert (await apply(api, snapshot)).status_code == 409
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0


@pytest.mark.parametrize('change,blocker', [({'folio_id': 'other-stay-folio'}, 'ambiguous_payment_owner'),
    ({'amount': -10}, 'invalid_payment_amount')])
async def test_unknown_folio_and_negative_receipt_are_not_repaired(closed, change, blocker):
    a, api = closed
    await a.db.payments.update_one({'id': 'receipt'}, {'$set': change})
    snapshot = await plan(api)
    assert not snapshot['eligible'] and blocker in snapshot['blockers']
    assert (await apply(api, snapshot)).status_code == 409


async def test_audit_failure_rolls_back_the_counter(closed, monkeypatch):
    from core import audit_chain

    a, api = closed
    snapshot = await plan(api)

    async def fail(*args, **kwargs):
        raise RuntimeError('Explicit local audit failure')

    monkeypatch.setattr(audit_chain, 'append_audit_log', fail)
    with pytest.raises(RuntimeError, match='audit failure'):
        await apply(api, snapshot)
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0


async def test_nonfinance_role_and_foreign_tenant_cannot_reconcile(closed):
    a, api = closed
    snapshot = await plan(api)
    a.user.role = 'housekeeping'
    assert (await api.get(PATH + 'paid-counter-preview')).status_code == 403
    assert (await apply(api, snapshot)).status_code == 403
    a.user.role = 'admin'
    a.user.tenant_id = 'foreign'
    assert (await api.get(PATH + 'paid-counter-preview')).status_code == 404


async def test_concurrent_preview_applies_allow_only_one_counter_change(closed):
    a, api = closed
    snapshot = await plan(api)
    results = await asyncio.gather(*(apply(api, snapshot) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 120
    assert await a.db.audit_logs.count_documents({'operation_name': 'payment_counter_reconciled'}) == 1


@pytest.fixture
async def sealed_confirmed(closed):
    a, api = closed
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {
        'status': 'confirmed', 'check_in': '2027-01-20', 'check_out': '2027-01-22', 'total_amount': 100}})
    await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'amount': 120, 'total': 120}})
    await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'balance': 0}})
    await a.db.folios.insert_one({'tenant_id': 'qa', 'id': 'empty-closed-folio', 'booking_id': 'synthetic-stay',
                                'status': 'closed', 'currency': 'USD', 'balance': 0})
    return a, api


async def review_plan(api):
    response = await api.get(PATH + 'paid-counter-preview?review_closed_folios=true')
    assert response.status_code == 200, response.text
    return response.json()


async def review_apply(api, snapshot):
    return await api.post(PATH + 'reconcile-paid-counter', json={
        'source_revision': snapshot['source_revision'], 'reason': 'Kapalı ve dengeli folyoların açık incelemeli sayaç mutabakatı',
        'review_closed_folios': True})


async def test_reviewed_sealed_folios_repair_without_fake_checkout_or_new_money(sealed_confirmed):
    a, api = sealed_confirmed
    old_plan = await plan(api)
    assert not old_plan['eligible'] and old_plan['blockers'] == ['active_financial_workflow_requires_review']
    assert (await apply(api, old_plan)).status_code == 409  # default guard is intact
    before = {name: await a.db[name].find({}, {'_id': 0}).to_list(None)
              for name in ('bookings', 'folios', 'payments', 'folio_charges', 'rooms', 'cashier_shifts', 'outbox_events')}
    snapshot = await review_plan(api)
    assert snapshot['eligible'] and snapshot['review_closed_folios'] and snapshot['ledger_paid_amount'] == 120
    assert snapshot['source_revision'] != old_plan['source_revision']
    assert (await review_apply(api, old_plan)).status_code == 409  # ordinary preview cannot authorize the reviewed mode
    response = await review_apply(api, snapshot)
    assert response.status_code == 200 and response.json()['applied']
    after = await a.db.bookings.find_one({'id': 'synthetic-stay'}, {'_id': 0})
    assert after == {**before['bookings'][0], 'paid_amount': 120}
    assert after['status'] == 'confirmed'
    for name in before.keys() - {'bookings'}:
        assert await a.db[name].find({}, {'_id': 0}).to_list(None) == before[name]
    assert (await review_apply(api, snapshot)).status_code == 409
    assert not (await review_apply(api, await review_plan(api))).json()['applied']
    audit = await a.db.audit_logs.find({'operation_name': 'payment_counter_reconciled'}).to_list(None)
    assert len(audit) == 1


@pytest.mark.parametrize('kind,blocker', [
    ('open_folio', 'active_financial_workflow_requires_review'),
    ('checked_in', 'active_financial_workflow_requires_review'),
    ('stored_balance', 'closed_folio_stored_balance_not_zero'),
    ('charge_changed', 'closed_folio_ledger_not_balanced'),
    ('opening_credit', 'imported_opening_credit_requires_review'),
    ('unknown_payment_owner', 'ambiguous_payment_owner'),
    ('unbound_extra', 'ambiguous_charge_owner'),
    ('foreign_charge_owner', 'ambiguous_charge_owner'),
    ('pending_provider', 'unresolved_provider_payment_requires_review'),
    ('unknown_provider', 'unresolved_provider_payment_requires_review'),
    ('mixed_charge_currency', 'mixed_or_unknown_currency'),
    ('subcent_charge', 'invalid_charge_amount'),
    ('missing_folio_identity', 'missing_or_duplicate_folio_identity'),
    ('duplicate_folio_identity', 'missing_or_duplicate_folio_identity'),
    ('missing_charge_identity', 'missing_or_duplicate_charge_identity'),
    ('duplicate_charge_identity', 'missing_or_duplicate_charge_identity'),
    ('missing_extra_identity', 'missing_or_duplicate_charge_identity'),
    ('duplicate_extra_identity', 'missing_or_duplicate_charge_identity'),
    ('duplicate_provider_transaction', 'duplicate_payment_transaction_requires_review'),
])
async def test_review_does_not_bypass_an_open_uncertain_or_inconsistent_ledger(sealed_confirmed, kind, blocker):
    a, api = sealed_confirmed
    if kind == 'open_folio':
        await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'status': 'open'}})
    elif kind == 'checked_in':
        await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'status': 'checked_in'}})
    elif kind == 'stored_balance':
        await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'balance': 5}})
    elif kind == 'charge_changed':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'amount': 121, 'total': 121}})
    elif kind == 'opening_credit':
        await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'opening_balance': 10}})
    elif kind == 'unknown_payment_owner':
        await a.db.payments.update_one({'id': 'receipt'}, {'$unset': {'folio_id': ''}})
    elif kind == 'unbound_extra':
        await a.db.extra_charges.insert_one({'tenant_id': 'qa', 'id': 'unbound', 'booking_id': 'synthetic-stay', 'amount': 1})
    elif kind == 'foreign_charge_owner':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'booking_id': 'other-stay'}})
    elif kind in {'pending_provider', 'unknown_provider'}:
        await a.db.payment_intents.insert_one({'tenant_id': 'qa', 'id': 'provider-intent', 'booking_id': 'synthetic-stay',
                                              'status': 'pending' if kind == 'pending_provider' else 'unknown'})
    elif kind == 'mixed_charge_currency':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'currency': 'TRY'}})
    elif kind == 'subcent_charge':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'amount': 120.001, 'total': 120.001}})
    elif kind == 'missing_folio_identity':
        await a.db.folios.insert_one({'tenant_id': 'qa', 'booking_id': 'synthetic-stay', 'status': 'closed', 'balance': 0})
    elif kind == 'duplicate_folio_identity':
        await a.db.folios.insert_one({'tenant_id': 'qa', 'id': 'synthetic-folio', 'booking_id': 'synthetic-stay', 'status': 'closed', 'balance': 0})
    elif kind == 'missing_charge_identity':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$unset': {'id': ''}})
    elif kind == 'duplicate_charge_identity':
        duplicate = await a.db.folio_charges.find_one({'id': 'synthetic-room-charge'}, {'_id': 0})
        await a.db.folio_charges.insert_one(duplicate)
    elif kind == 'missing_extra_identity':
        await a.db.extra_charges.insert_one({'tenant_id': 'qa', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio', 'total': 0})
    elif kind == 'duplicate_provider_transaction':
        await a.db.payments.update_one({'id': 'receipt'}, {'$set': {'amount': 60, 'provider_ref': 'same-provider-transaction'}})
        duplicate = await a.db.payments.find_one({'id': 'receipt'}, {'_id': 0})
        await a.db.payments.insert_one({**duplicate, 'id': 'retry-created-row'})
        # Reports deduplicate the PSP transaction: the ledger is balanced at
        # 60, not the raw two-row sum of 120. Never repair to that doubled sum.
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'amount': 60, 'total': 60}})
    else:
        row = {'tenant_id': 'qa', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio', 'total': 0, 'id': 'duplicate-extra'}
        await a.db.extra_charges.insert_many([dict(row), dict(row)])
    before = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    snapshot = await review_plan(api)
    assert not snapshot['eligible'] and blocker in snapshot['blockers']
    assert (await review_apply(api, snapshot)).status_code == 409
    assert await a.db.bookings.find_one({'id': 'synthetic-stay'}) == before
    assert await a.db.audit_logs.count_documents({'operation_name': 'payment_counter_reconciled'}) == 0


@pytest.mark.parametrize('source', ['charge', 'extra', 'intent', 'folio'])
async def test_review_freezes_all_sealing_sources_not_only_payments(sealed_confirmed, source):
    a, api = sealed_confirmed
    snapshot = await review_plan(api)
    assert snapshot['eligible']
    if source == 'charge':
        await a.db.folio_charges.update_one({'id': 'synthetic-room-charge'}, {'$set': {'description': 'Changed reviewed source'}})
    elif source == 'extra':
        await a.db.extra_charges.insert_one({'tenant_id': 'qa', 'id': 'new-voided', 'booking_id': 'synthetic-stay', 'voided': True})
    elif source == 'intent':
        await a.db.payment_intents.insert_one({'tenant_id': 'qa', 'id': 'new-terminal', 'booking_id': 'synthetic-stay', 'status': 'failed'})
    else:
        await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'updated_at': '2026-11-02T12:00:00Z'}})
    assert (await review_apply(api, snapshot)).status_code == 409
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0


async def test_review_remains_tenant_rbac_and_transaction_audit_bound(sealed_confirmed, monkeypatch):
    from core import audit_chain

    a, api = sealed_confirmed
    snapshot = await review_plan(api)
    a.user.role = 'housekeeping'
    assert (await api.get(PATH + 'paid-counter-preview?review_closed_folios=true')).status_code == 403
    assert (await review_apply(api, snapshot)).status_code == 403
    a.user.role = 'admin'
    a.user.tenant_id = 'other-tenant'
    assert (await review_apply(api, snapshot)).status_code == 404
    a.user.tenant_id = 'qa'

    async def audit_failure(*args, **kwargs):
        raise RuntimeError('review audit failure')

    monkeypatch.setattr(audit_chain, 'append_audit_log', audit_failure)
    with pytest.raises(RuntimeError, match='review audit failure'):
        await review_apply(api, snapshot)
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0


async def test_review_concurrent_applies_have_one_counter_change_and_one_audit(sealed_confirmed):
    a, api = sealed_confirmed
    snapshot = await review_plan(api)
    results = await asyncio.gather(*(review_apply(api, snapshot) for _ in range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 120
    assert await a.db.audit_logs.count_documents({'operation_name': 'payment_counter_reconciled'}) == 1


@pytest.mark.parametrize('value', [False, 'true', 1, None])
async def test_review_requires_a_literal_explicit_true_flag(sealed_confirmed, value):
    _a, api = sealed_confirmed
    snapshot = await review_plan(api)
    response = await api.post(PATH + 'reconcile-paid-counter', json={
        'source_revision': snapshot['source_revision'], 'reason': 'Explicit reviewed test', 'review_closed_folios': value})
    assert response.status_code == 422
