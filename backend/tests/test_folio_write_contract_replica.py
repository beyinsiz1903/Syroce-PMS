"""Real finance handlers/RBAC/ledger/cashier on a disposable loopback replica.

Authentication is injected as in the existing acceptance fixture. No external
providers, credentials or production database is used by this suite.
"""
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from core import helpers
from core.security import get_current_user
from routers.finance import folio
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401

pytestmark = pytest.mark.asyncio


async def call(acceptance, monkeypatch, payload, key, folio_id='synthetic-folio'):
    monkeypatch.setattr(folio, 'db', acceptance.db)
    monkeypatch.setattr(helpers, 'db', acceptance.db)
    monkeypatch.setattr(folio, 'cache', None)
    app = FastAPI()
    app.include_router(folio.router, prefix='/api')
    app.dependency_overrides[get_current_user] = lambda: acceptance.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-acceptance') as api:
        return await api.post(f'/api/folio/{folio_id}/payment', json=payload, headers={'Idempotency-Key': key})


def receipt(**overrides):
    return {'amount': 10, 'currency': 'USD', 'method': 'card', 'payment_type': 'interim',
        'received_to_try_rate': 35, **overrides}


async def test_receipt_replay_and_mismatch_have_exactly_one_ledger_and_cashier_row(acceptance, monkeypatch):
    a = acceptance
    a.user.role = 'front_desk'
    await a.db.cashier_shifts.insert_one({'tenant_id': 'qa', 'id': 'local-shift', 'status': 'open',
        'opened_at': datetime.now(UTC).isoformat(), 'transactions': [], 'cash_in': 0, 'cash_out': 0})
    first = await call(a, monkeypatch, receipt(), 'same-receipt')
    assert first.status_code == 200, first.text
    retry = await call(a, monkeypatch, receipt(), 'same-receipt')
    assert retry.status_code == 200 and retry.json()['id'] == first.json()['id']
    changed = await call(a, monkeypatch, receipt(amount=20), 'same-receipt')
    assert changed.status_code == 409
    assert await a.db.payments.count_documents({}) == 1
    payment = await a.db.payments.find_one({})
    assert (payment['amount'], payment['currency'], payment['reporting_amount'], payment['reporting_currency']) == (10, 'USD', 350, 'TRY')
    shift = await a.db.cashier_shifts.find_one({'id': 'local-shift'})
    assert len(shift['transactions']) == 1
    cash = shift['transactions'][0]
    assert (cash['amount'], cash['original_amount'], cash['currency'], cash['fx_rate']) == (350, 10, 'USD', 35)
    assert cash['business_date'] == payment['business_date'] == '2026-10-26'
    booking = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    assert booking['balance'] == 550 and booking['collected_amount'] == 10 and booking['payment_status'] == 'partial'
    await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': {'status': 'closed'}})
    replay_closed = await call(a, monkeypatch, receipt(), 'same-receipt')
    assert replay_closed.status_code == 200 and replay_closed.json()['id'] == first.json()['id']
    assert (await call(a, monkeypatch, receipt(), 'new-after-close')).status_code == 409
    assert await a.db.payments.count_documents({}) == 1


@pytest.mark.parametrize('override,status', [
    ({'currency': 'TRY'}, 422), ({'payment_type': 'refund'}, 422),
    ({'received_to_try_rate': None}, 422), ({'amount': 0.001}, 422),
])
async def test_invalid_receipts_do_not_mutate_any_money_source(acceptance, monkeypatch, override, status):
    a = acceptance
    before = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    response = await call(a, monkeypatch, receipt(**override), 'invalid-local-receipt')
    assert response.status_code == status, response.text
    assert await a.db.payments.count_documents({}) == 0
    assert await a.db.cashier_shifts.count_documents({}) == 0
    assert await a.db.bookings.find_one({'id': 'synthetic-stay'}) == before


async def test_foreign_tenant_and_housekeeping_role_cannot_post_receipt(acceptance, monkeypatch):
    a = acceptance
    a.user.tenant_id = 'different-tenant'
    assert (await call(a, monkeypatch, receipt(), 'foreign-tenant')).status_code == 404
    a.user.tenant_id = 'qa'
    a.user.role = 'housekeeping'
    assert (await call(a, monkeypatch, receipt(), 'unauthorized-role')).status_code == 403
    assert await a.db.payments.count_documents({}) == 0


async def test_cash_requires_open_shift_without_leaving_payment_or_replay_lock(acceptance, monkeypatch):
    a = acceptance
    response = await call(a, monkeypatch, receipt(method='cash'), 'no-cash-shift')
    assert response.status_code == 409
    assert await a.db.payments.count_documents({}) == 0
    assert await a.db.idempotency_keys.count_documents({'status': {'$in': ['processing', 'completed']}}) == 0
