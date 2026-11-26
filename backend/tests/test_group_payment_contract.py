"""Group payments use guest-card ownership and cashier recording (local DB only)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import reservation_detail
from routers.hotel_services_pkg import group_folio as route
from routers.hotel_services_pkg._common import GroupPaymentRequest
from tests import test_group_folio_ledger_replica as group_fixtures

db = group_fixtures.db
seed = group_fixtures.seed


async def setup_payment(database, monkeypatch):
    await seed(database, monkeypatch)
    from core import utils
    from domains.pms import cashier_service
    from routers import webhook_retry_service
    monkeypatch.setattr(reservation_detail, 'db', database)
    monkeypatch.setattr(cashier_service, 'db', database)
    monkeypatch.setattr(utils, 'db', database)
    monkeypatch.setattr(reservation_detail, '_enforce_perm', lambda *_: None)
    monkeypatch.setattr(reservation_detail, '_log_activity', AsyncMock())
    monkeypatch.setattr(webhook_retry_service, 'schedule_emit_reservation_updated', lambda *_args, **_kwargs: None)
    await database.extra_charges.update_many({'booking_id': 'b2', 'tenant_id': 't'}, {'$set': {'folio_id': 'f'}})
    await database.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-11-12'}}, upsert=True)
    return SimpleNamespace(id='operator', tenant_id='t', name='Operator', role='manager', email='operator@example.invalid')


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['cash', 'card', 'bank_transfer', 'online'])
async def test_group_payment_owns_folio_records_cashier_and_replays_once(db, monkeypatch, method):
    actor = await setup_payment(db, monkeypatch)
    await db.cashier_shifts.insert_one({'id': 'shift', 'tenant_id': 't', 'status': 'open', 'business_date': '2026-11-12', 'transactions': [], 'cash_in': 0})
    request = GroupPaymentRequest(group_id='g', booking_id='b2', folio_id='f', amount=25, method=method, reference='group-intent-1')
    first = await route.record_group_payment(request, actor, None)
    repeated = await route.record_group_payment(request, actor, None)
    assert first['payment']['folio_id'] == 'f'
    assert repeated['idempotent'] is True
    assert await db.payments.count_documents({'tenant_id': 't', 'booking_id': 'b2'}) == 1
    shift = await db.cashier_shifts.find_one({'id': 'shift'})
    assert shift['cash_in'] == (25 if method == 'cash' else 0) and len(shift['transactions']) == 1
    assert shift['transactions'][0]['ref_id'] == first['payment']['id']
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 310


@pytest.mark.asyncio
@pytest.mark.parametrize('group_id,booking_id', [('missing', 'b2'), ('g', 'not-member')])
async def test_group_membership_is_required_before_any_payment(db, monkeypatch, group_id, booking_id):
    actor = await setup_payment(db, monkeypatch)
    await db.bookings.insert_one({'id': 'not-member', 'tenant_id': 't', 'total_amount': 50})
    with pytest.raises(HTTPException) as error:
        await route.record_group_payment(GroupPaymentRequest(group_id=group_id, booking_id=booking_id, amount=10), actor, None)
    assert error.value.status_code == 404
    assert await db.payments.count_documents({}) == 0


@pytest.mark.asyncio
async def test_group_payment_without_cashier_shift_has_no_payment_side_effect(db, monkeypatch):
    actor = await setup_payment(db, monkeypatch)
    with pytest.raises(HTTPException) as error:
        await route.record_group_payment(GroupPaymentRequest(group_id='g', booking_id='b2', folio_id='f', amount=25, reference='no-shift'), actor, None)
    assert error.value.status_code == 409
    assert await db.payments.count_documents({}) == 0


@pytest.mark.asyncio
async def test_merged_group_member_cannot_receive_an_independent_payment(db, monkeypatch):
    actor = await setup_payment(db, monkeypatch)
    await db.bookings.update_one({'id': 'b2'}, {'$set': {'folio_merged_to': 'b1'}})
    with pytest.raises(HTTPException) as error:
        await route.record_group_payment(GroupPaymentRequest(group_id='g', booking_id='b2', amount=25), actor, None)
    assert error.value.status_code == 409
    assert await db.payments.count_documents({}) == 0


@pytest.mark.parametrize('amount', [0, -1, float('nan'), float('inf')])
def test_group_payment_rejects_invalid_money(amount):
    with pytest.raises(ValidationError):
        GroupPaymentRequest(group_id='g', booking_id='b', amount=amount)


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['foreign', 'other-booking', 'closed'])
async def test_group_payment_rejects_non_owned_or_closed_folio(db, monkeypatch, target):
    actor = await setup_payment(db, monkeypatch)
    await db.folios.insert_one({'id': target, 'tenant_id': 'other' if target == 'foreign' else 't',
        'booking_id': 'b1' if target == 'other-booking' else 'b2',
        'status': 'closed' if target == 'closed' else 'open', 'currency': 'TRY'})
    with pytest.raises(HTTPException) as error:
        await route.record_group_payment(GroupPaymentRequest(group_id='g', booking_id='b2', folio_id=target,
            amount=25, reference='rejected-target'), actor, None)
    assert error.value.status_code in (404, 409)
    assert await db.payments.count_documents({}) == 0
