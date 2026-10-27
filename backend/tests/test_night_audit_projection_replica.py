"""Night posting must atomically refresh the same projection as departments."""
from unittest.mock import AsyncMock

import pytest

from core import booking_payment_state, night_audit_hardened as audit
from tests.test_pos_final_consistency_replica import db  # noqa: F401


async def seed(db, monkeypatch):
    monkeypatch.setattr(audit, 'db', db)
    monkeypatch.setattr(audit, 'client', db.client)
    for name in ('night_audit_run_items', 'pms_audit_trail', 'folios', 'bookings', 'folio_charges'):
        if name not in await db.list_collection_names():
            await db.create_collection(name)
    await db.bookings.insert_one({'id': 'b', 'tenant_id': 't', 'status': 'checked_in', 'currency': 'TRY',
        'total_amount': 200, 'balance': 150, 'payment_status': 'partial'})
    await db.folios.insert_one({'id': 'f', 'tenant_id': 't', 'booking_id': 'b', 'status': 'open', 'balance': -50})
    await db.payments.insert_one({'id': 'p', 'tenant_id': 't', 'folio_id': 'f', 'booking_id': 'b', 'amount': 50, 'method': 'cash'})
    item = {'id': 'i', 'tenant_id': 't', 'run_id': 'r', 'booking_id': 'b', 'folio_id': 'f',
        'status': 'pending', 'posting_type': 'room_charge', 'posting_date': '2026-10-18', 'amount': 90, 'tax_amount': 10,
        'tax_breakdown': {'vat': 10}, 'total': 100, 'currency': 'TRY'}
    await db.night_audit_run_items.insert_one(dict(item))
    return item


@pytest.mark.asyncio
async def test_room_post_updates_balance_projection_in_same_transaction(db, monkeypatch):
    item = await seed(db, monkeypatch)
    assert await audit._post_room_charge_item('t', item, 'r')
    row = await db.bookings.find_one({'id': 'b'})
    assert row['balance'] == 50 and row['collected_amount'] == 50 and row['payment_status'] == 'partial'
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == 50
    assert not await audit._post_room_charge_item('t', item, 'r')
    assert await db.folio_charges.count_documents({}) == 1


@pytest.mark.asyncio
async def test_projection_failure_cannot_leave_acknowledged_room_debt(db, monkeypatch):
    item = await seed(db, monkeypatch)
    monkeypatch.setattr(booking_payment_state, 'refresh_booking_payment_state', AsyncMock(side_effect=RuntimeError('projection unavailable')))
    assert not await audit._post_room_charge_item('t', item, 'r')
    assert await db.folio_charges.count_documents({}) == 0
    assert (await db.folios.find_one({'id': 'f'}))['balance'] == -50
    assert (await db.night_audit_run_items.find_one({'id': 'i'}))['status'] == 'failed'


@pytest.mark.asyncio
async def test_mixed_currency_simulation_never_returns_nominal_money_sum(db):
    from tests.test_night_audit_hardening import BD, PROPERTY, TENANT, _call_engine, _seed_booking
    await _call_engine('ensure_night_audit_indexes', db.client, db)
    await _seed_booking(db, room_rate=1000)
    foreign = await _seed_booking(db, room_rate=100)
    await db.bookings.update_one({'id': foreign['booking_id']}, {'$set': {'currency': 'EUR'}})
    await db.tenant_settings.insert_one({'tenant_id': TENANT, 'business_date': BD})
    result = await _call_engine('start_night_audit', db.client, db, TENANT, PROPERTY, BD, 'manual', {'id': 'tester'}, dry_run=True)
    assert result['success'] and result['projected_total_by_currency'] == {'TRY': 1000, 'EUR': 100}
    assert result['projected_total'] is result['total_room_revenue'] is result['total_tax_amount'] is None
    assert await db.folio_charges.count_documents({'tenant_id': TENANT}) == 0
