"""Bulk group collections conserve cents and commit folios/cashier together, LOCAL DB only."""
import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from domains.pms import cashier_service
from routers.hotel_services_pkg import group_folio as route
from routers.hotel_services_pkg._common import GroupBulkPaymentRequest
from tests import test_group_payment_contract as fixtures

db = fixtures.db


async def setup(database, monkeypatch):
    actor = await fixtures.setup_payment(database, monkeypatch)
    await database.folios.insert_one({'id': 'f1', 'tenant_id': 't', 'booking_id': 'b1', 'status': 'open', 'currency': 'TRY'})
    await database.cashier_shifts.insert_one({'id': 'shift', 'tenant_id': 't', 'status': 'open', 'business_date': '2026-11-12', 'cash_in': 0, 'transactions': []})
    await database.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-11-12'}})
    return actor


@pytest.mark.asyncio
@pytest.mark.parametrize('distribution', ['equal', 'proportional', 'balance_only'])
async def test_bulk_posts_exact_amount_owned_folios_and_cashier_once(db, monkeypatch, distribution):
    actor = await setup(db, monkeypatch)
    data = GroupBulkPaymentRequest(group_id='g', total_amount=100.01, reference='bulk-1', distribution=distribution)
    first = await route.record_group_bulk_payment(data, actor, None)
    repeated = await route.record_group_bulk_payment(data, actor, None)
    assert first['total_distributed'] == 100.01
    assert repeated['idempotent'] is True
    rows = await db.payments.find({'tenant_id': 't'}).to_list(None)
    assert round(sum(p['amount'] for p in rows), 2) == 100.01
    assert all(p.get('folio_id') in {'f1', 'f'} and p.get('business_date') == '2026-11-12' for p in rows)
    shift = await db.cashier_shifts.find_one({'id': 'shift'})
    assert round(shift['cash_in'], 2) == 100.01 and len(shift['transactions']) == len(rows)
    assert {x['ref_id'] for x in shift['transactions']} == {p['id'] for p in rows}
    assert round(sum(r['balance'] for r in await route._load_group_booking_rows('t', ['b1', 'b2'])), 2) == 5034.99
    with pytest.raises(HTTPException) as error:
        await route.record_group_bulk_payment(data.model_copy(update={'total_amount': 100}), actor, None)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_later_cashier_failure_rolls_back_all_member_payments(db, monkeypatch):
    actor = await setup(db, monkeypatch)
    original = cashier_service.record_cash_transaction
    calls = 0
    async def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HTTPException(409, 'simulated cashier failure')
        return await original(**kwargs)
    monkeypatch.setattr(cashier_service, 'record_cash_transaction', fail_second)
    with pytest.raises(HTTPException):
        await route.record_group_bulk_payment(GroupBulkPaymentRequest(group_id='g', total_amount=100, reference='rollback'), actor, None)
    assert await db.payments.count_documents({}) == 0
    assert (await db.cashier_shifts.find_one({'id': 'shift'}))['transactions'] == []
    assert await db.group_bulk_payment_operations.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['no-shift', 'stale-shift', 'missing-shift-day', 'ambiguous', 'closed', 'mixed', 'fx', 'overpayment', 'missing-member'])
async def test_invalid_bulk_targets_leave_no_partial_writes(db, monkeypatch, invalid):
    actor = await setup(db, monkeypatch)
    if invalid == 'no-shift':
        await db.cashier_shifts.update_one({'id': 'shift'}, {'$set': {'status': 'closed'}})
    elif invalid == 'stale-shift':
        await db.cashier_shifts.update_one({'id': 'shift'}, {'$set': {'business_date': '2026-11-11'}})
    elif invalid == 'missing-shift-day':
        await db.cashier_shifts.update_one({'id': 'shift'}, {'$unset': {'business_date': ''}})
    elif invalid == 'ambiguous':
        await db.folios.insert_one({'id': 'f-other', 'tenant_id': 't', 'booking_id': 'b2', 'status': 'open', 'currency': 'TRY'})
    elif invalid == 'closed':
        await db.folios.update_one({'id': 'f'}, {'$set': {'status': 'closed'}})
    elif invalid in {'mixed', 'fx'}:
        await db.bookings.update_many({'tenant_id': 't', **({'id': 'b2'} if invalid == 'mixed' else {})}, {'$set': {'currency': 'EUR'}})
        await db.folios.update_many({'tenant_id': 't'}, {'$set': {'currency': 'EUR'}})
        await db.extra_charges.update_many({}, {'$set': {'currency': 'EUR'}})
    elif invalid == 'missing-member':
        await db.bookings.delete_one({'id': 'b2'})
    data = GroupBulkPaymentRequest(group_id='g', total_amount=6000 if invalid == 'overpayment' else 100, reference='invalid')
    with pytest.raises(HTTPException) as error:
        await route.record_group_bulk_payment(data, actor, None)
    assert error.value.status_code in {404, 409, 422}
    assert await db.payments.count_documents({}) == 0
    assert (await db.cashier_shifts.find_one({'id': 'shift'}))['transactions'] == []


@pytest.mark.asyncio
async def test_concurrent_same_reference_is_one_collection(db, monkeypatch):
    actor = await setup(db, monkeypatch)
    data = GroupBulkPaymentRequest(group_id='g', total_amount=100, reference='concurrent')
    results = await asyncio.gather(*(route.record_group_bulk_payment(data, actor, None) for _ in range(2)))
    assert sum(bool(x.get('idempotent')) for x in results) == 1
    assert (await db.cashier_shifts.find_one({'id': 'shift'}))['cash_in'] == 100


@pytest.mark.parametrize('changes', [{'total_amount': 0}, {'total_amount': -1}, {'total_amount': float('nan')}, {'total_amount': float('inf')}, {'distribution': 'unknown'}, {'reference': ' '}])
def test_invalid_bulk_request(changes):
    with pytest.raises(ValidationError):
        GroupBulkPaymentRequest(**{'group_id': 'g', 'total_amount': 100, 'reference': 'bulk', **changes})


@pytest.mark.parametrize('distribution,expected', [('equal', [.01, 1.99]), ('proportional', [0, 2]), ('balance_only', [.01, 1.99])])
def test_distribution_never_overpays_small_debt(distribution, expected):
    from modules.pms_core.group_bulk_collection import allocate_collection
    assert allocate_collection(2, [.01, 100], distribution) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['card', 'credit_card', 'bank_transfer', 'online'])
async def test_non_cash_bulk_has_exactly_one_shift_row_per_payment(db, monkeypatch, method):
    actor = await setup(db, monkeypatch)
    await route.record_group_bulk_payment(GroupBulkPaymentRequest(group_id='g', total_amount=100, reference='method', method=method), actor, None)
    shift = await db.cashier_shifts.find_one({'id': 'shift'})
    assert shift['cash_in'] == 0 and len(shift['transactions']) == 2
    assert all(row['method'] == method for row in shift['transactions'])


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['agency', 'city_ledger', 'security_deposit_application', 'comp'])
async def test_non_collection_method_never_becomes_bulk_cash(db, monkeypatch, method):
    actor = await setup(db, monkeypatch)
    with pytest.raises(HTTPException) as error:
        await route.record_group_bulk_payment(GroupBulkPaymentRequest(group_id='g', total_amount=100, reference='invalid-method', method=method), actor, None)
    assert error.value.status_code == 422
    assert await db.payments.count_documents({}) == 0
