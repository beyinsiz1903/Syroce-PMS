"""Real LOCAL Mongo: POS source/reversal refreshes every reservation cache."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from core import booking_payment_state as state
from core import pos_folio_consumer as consumer
from core.outbox_service import POS_CHARGE_POSTED, POS_CHARGE_REVERSED
from tests.test_pos_final_consistency_replica import db  # noqa: F401


async def seed(db, monkeypatch):
    monkeypatch.setattr(consumer, 'get_system_db', lambda: db)
    # Unposted future room price is still part of reservation debt. A second
    # folio window is included too: never copy one negative folio to booking.
    await db.bookings.insert_many([
        {'tenant_id': 't', 'id': bid, 'status': 'checked_in', 'currency': 'TRY',
         'total_amount': 1000, 'balance': 0, 'payment_status': 'paid'} for bid in ('b1', 'b2')])
    await db.bookings.insert_one({'tenant_id': 'other', 'id': 'b2', 'balance': 999})
    await db.folios.insert_many([
        {'tenant_id': 't', 'id': fid, 'booking_id': bid, 'status': 'open', 'currency': 'TRY', 'balance': -1000}
        for fid, bid in (('f1', 'b1'), ('f2', 'b2'), ('separate-window', 'b1'))])
    await db.folio_charges.insert_one({'tenant_id': 't', 'id': 'window-extra', 'booking_id': 'b1',
        'folio_id': 'separate-window', 'total': 60, 'charge_category': 'spa', 'voided': False})
    await db.payments.insert_many([
        {'tenant_id': 't', 'id': fid, 'booking_id': bid, 'folio_id': fid, 'amount': amount, 'method': 'cash', 'voided': False}
        for fid, bid, amount in (('f1', 'b1', 1000), ('f2', 'b2', 1000), ('separate-window', 'b1', 60))])
    line = {'tenant_id': 't', 'id': 'meal', 'booking_id': 'b1', 'folio_id': 'f1',
        'charge_category': 'food', 'amount': 100, 'vat_amount': 20, 'total': 120, 'currency': 'TRY',
        'source_pos_order_id': 'o', 'line_no': 0, 'voided': False}
    return {'tenant_id': 't', 'event_type': POS_CHARGE_POSTED,
        'payload': {'folio_id': 'f1', 'source_pos_order_id': 'o', 'charges': [line]}}


async def split_rows(db):
    await db.folio_charges.update_one({'id': 'meal'}, {'$set': {'amount': 25, 'vat_amount': 5, 'total': 30}})
    await db.folio_charges.insert_many([
        {'tenant_id': 't', 'id': cid, 'booking_id': 'b2', 'folio_id': 'f2',
         'amount': amount / 1.2, 'vat_amount': amount / 6, 'total': amount, 'currency': 'TRY',
         'source_pos_order_id': 'o', 'source_line_no': 0, 'line_no': 'split:' + cid, 'voided': False}
        for cid, amount in (('part1', 60), ('part2', 30))])
    # Simulate the legitimate split endpoint's projection before refund.
    for bid in ('b1', 'b2'):
        await state.refresh_booking_payment_state(db, 't', bid, strict=True)


async def test_post_and_refund_keep_both_reservations_in_sync_with_multiple_windows(db, monkeypatch):
    event = await seed(db, monkeypatch)
    assert (await consumer.handle_ic_pos_event(deepcopy(event)))[0]
    b1 = await db.bookings.find_one({'tenant_id': 't', 'id': 'b1'})
    assert b1['balance'] == 120 and b1['payment_status'] == 'partial' and b1['collected_amount'] == 1060
    assert (await db.folios.find_one({'id': 'f1'}))['balance'] == -880
    await split_rows(db)
    reversal = {'tenant_id': 't', 'event_type': POS_CHARGE_REVERSED,
        'payload': {'folio_id': 'f1', 'source_pos_order_id': 'o'}}
    for _ in range(2):
        assert (await consumer.handle_ic_pos_event(deepcopy(reversal)))[0]
        for bid in ('b1', 'b2'):
            booking = await db.bookings.find_one({'tenant_id': 't', 'id': bid})
            assert booking['balance'] == 0 and booking['payment_status'] == 'paid'
    assert (await db.bookings.find_one({'tenant_id': 'other', 'id': 'b2'}))['balance'] == 999
    assert await db.folio_charges.count_documents({'source_pos_order_id': 'o'}) == 3
    assert not await db.folio_charges.count_documents({'source_pos_order_id': 'o', 'voided': {'$ne': True}})


@pytest.mark.parametrize('kind', ['post', 'refund'])
async def test_projection_failure_is_retryable_and_replay_repairs_without_double_debt(db, monkeypatch, kind):
    event = await seed(db, monkeypatch)
    if kind == 'refund':
        assert (await consumer.handle_ic_pos_event(event))[0]
        await split_rows(db)
        event = {'tenant_id': 't', 'event_type': POS_CHARGE_REVERSED,
            'payload': {'folio_id': 'f1', 'source_pos_order_id': 'o'}}
    original = state.refresh_booking_payment_state
    monkeypatch.setattr(state, 'refresh_booking_payment_state', AsyncMock(side_effect=RuntimeError('projection unavailable')))
    ok, message = await consumer.handle_ic_pos_event(deepcopy(event))
    assert not ok and message.startswith('retryable:')
    monkeypatch.setattr(state, 'refresh_booking_payment_state', original)
    assert (await consumer.handle_ic_pos_event(deepcopy(event)))[0]
    expected = 120 if kind == 'post' else 0
    assert (await db.bookings.find_one({'tenant_id': 't', 'id': 'b1'}))['balance'] == expected
    assert await db.folio_charges.count_documents({'source_pos_order_id': 'o'}) == (1 if kind == 'post' else 3)
    if kind == 'refund':
        assert (await db.bookings.find_one({'tenant_id': 't', 'id': 'b2'}))['balance'] == 0
