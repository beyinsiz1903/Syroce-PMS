"""Follow-up to the PR1484 live receipt acceptance; loopback DB only."""
import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from core.security import get_current_user
from domains.pms import cashier_service
from routers.finance import folio
from tests.test_folio_write_contract_replica import call, receipt
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('initial', [0, None, 'missing', 5])
async def test_new_receipt_updates_the_legacy_booking_counter_once_without_overwriting_prior_credit(acceptance, monkeypatch, initial):
    a = acceptance
    if initial == 'missing':
        await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$unset': {'paid_amount': ''}})
    else:
        await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'paid_amount': initial}})
    first = await call(a, monkeypatch, receipt(), 'counter-once')
    assert first.status_code == 200, first.text
    replay = await call(a, monkeypatch, receipt(), 'counter-once')
    assert replay.status_code == 200 and replay.json()['id'] == first.json()['id']
    changed = await call(a, monkeypatch, receipt(amount=20), 'counter-once')
    assert changed.status_code == 409
    booking = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    assert booking['paid_amount'] == (5 if initial == 5 else 0) + 10
    assert booking['collected_amount'] == 10 and booking['balance'] == 550
    assert await a.db.payments.count_documents({}) == 1


async def test_concurrent_different_receipts_do_not_lose_a_booking_counter_increment(acceptance, monkeypatch):
    a = acceptance
    results = await asyncio.gather(call(a, monkeypatch, receipt(), 'parallel-a'),
        call(a, monkeypatch, receipt(amount=20), 'parallel-b'))
    assert all(r.status_code == 200 for r in results)
    assert await a.db.payments.count_documents({}) == 2
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 30


async def test_shift_race_rollback_does_not_credit_the_booking_counter(acceptance, monkeypatch):
    a = acceptance
    await a.db.cashier_shifts.insert_one({'tenant_id': 'qa', 'id': 'race-shift', 'status': 'open',
        'opened_at': datetime.now(UTC).isoformat(), 'transactions': [], 'cash_in': 0, 'cash_out': 0})

    async def closed_in_between(**kwargs):
        raise HTTPException(409, 'Vardiya işlem sırasında kapandı')

    monkeypatch.setattr(cashier_service, 'record_cash_transaction', closed_in_between)
    response = await call(a, monkeypatch, receipt(method='cash'), 'counter-race')
    assert response.status_code == 409
    assert await a.db.payments.count_documents({}) == 0
    booking = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    assert booking['paid_amount'] == booking['collected_amount'] == 0


async def test_foreign_receipt_void_uses_the_original_try_snapshot_and_reverses_counter(acceptance, monkeypatch):
    from core import database

    a = acceptance
    monkeypatch.setattr(database, 'db', a.db)
    await a.db.cashier_shifts.insert_one({'tenant_id': 'qa', 'id': 'refund-shift', 'status': 'open',
        'opened_at': datetime.now(UTC).isoformat(), 'transactions': [], 'cash_in': 0, 'cash_out': 0})
    first = await call(a, monkeypatch, receipt(method='cash'), 'counter-refund')
    assert first.status_code == 200
    payment = first.json()
    app = FastAPI()
    app.include_router(folio.router, prefix='/api')
    app.dependency_overrides[get_current_user] = lambda: a.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-acceptance') as api:
        response = await api.post(f"/api/folio/synthetic-folio/payment/{payment['id']}/void", json={'reason': 'Yalnız yerel sentetik iade kabulü'})
        duplicate = await api.post(f"/api/folio/synthetic-folio/payment/{payment['id']}/void", json={'reason': 'Aynı iadenin tekrarı'})
    assert response.status_code == 200, response.text
    assert duplicate.status_code == 400
    booking = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    assert booking['paid_amount'] == booking['collected_amount'] == 0 and booking['balance'] == 560
    shift = await a.db.cashier_shifts.find_one({'id': 'refund-shift'})
    assert shift['cash_in'] == shift['cash_out'] == 350
    assert len(shift['transactions']) == 2
    returned = next(t for t in shift['transactions'] if t['direction'] == 'out')
    assert (returned['amount'], returned['original_amount'], returned['currency'], returned['fx_rate']) == (350, 10, 'USD', 35)
    assert await a.db.audit_logs.count_documents({'action': 'folio_payment_voided'}) == 1


async def test_counter_does_not_invent_conversion_for_a_different_ledger_currency(acceptance, monkeypatch):
    a = acceptance
    monkeypatch.setattr(folio, 'db', a.db)
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'paid_amount': 25}})
    await folio._increment_booking_paid_amount('qa', 'synthetic-stay', 10, 'EUR')
    reversed_amount = await folio._decrement_booking_paid_amount('qa', 'synthetic-stay', 10, currency='EUR')
    assert reversed_amount == 0
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 25


async def test_legacy_foreign_void_without_try_evidence_rejects_before_mutation(acceptance, monkeypatch):
    a = acceptance
    monkeypatch.setattr(folio, 'db', a.db)
    legacy = {'tenant_id': 'qa', 'id': 'legacy-foreign', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
        'amount': 10, 'currency': 'USD', 'method': 'card', 'payment_type': 'interim', 'status': 'paid', 'voided': False}
    await a.db.payments.insert_one(dict(legacy))
    app = FastAPI()
    app.include_router(folio.router, prefix='/api')
    app.dependency_overrides[get_current_user] = lambda: a.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-acceptance') as api:
        response = await api.post('/api/folio/synthetic-folio/payment/legacy-foreign/void', json={'reason': 'Eksik kur kanıtı kabulü'})
    assert response.status_code == 422
    assert await a.db.payments.find_one({'id': 'legacy-foreign'}, {'_id': 0}) == legacy
    assert await a.db.cashier_shifts.count_documents({}) == 0
    assert (await a.db.bookings.find_one({'id': 'synthetic-stay'}))['paid_amount'] == 0
