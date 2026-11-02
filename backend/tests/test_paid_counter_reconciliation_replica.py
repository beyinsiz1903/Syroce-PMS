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
