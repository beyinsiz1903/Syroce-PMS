"""Real source unique indexes + transactions + transfer/replay/refund chain."""
from copy import deepcopy
from uuid import uuid4

import pytest
import pytest_asyncio

from core import pos_folio_consumer as consumer
from core.booking_atomicity import with_resource_locks
from core.outbox_service import POS_CHARGE_POSTED, POS_CHARGE_REVERSED
from modules.pms_core.service_charge_split import split_service_charge
from routers.reservation_detail import ChargeSplit
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def audit_context(db, monkeypatch):
    from shared_kernel import audit_helper
    for name in ('audit_logs', 'audit_chain_state'):
        await db.create_collection(name)
    monkeypatch.setattr(audit_helper, 'db', db)
    monkeypatch.setattr('core.audit_chain._system_db', lambda: db)


async def seed(database, source_field, index_name):
    for name in ('bookings', 'folios', 'folio_charges', 'folio_operations', 'payments', 'extra_charges', 'invoices'):
        await database.create_collection(name)
    await database.bookings.insert_many([{'tenant_id': 't', 'id': bid, 'status': 'checked_in', 'currency': 'TRY'} for bid in ('b1', 'b2')])
    await database.folios.insert_many([{'tenant_id': 't', 'id': fid, 'booking_id': bid, 'status': 'open', 'folio_type': 'guest', 'currency': 'TRY', 'balance': total}
        for fid, bid, total in [('f1', 'b1', 120), ('f2', 'b2', 0)]])
    await database.folio_charges.create_index([('tenant_id', 1), (source_field, 1), ('line_no', 1)],
        unique=True, name=index_name, partialFilterExpression={source_field: {'$type': 'string'}})
    charge = {'tenant_id': 't', 'id': 'meal', 'booking_id': 'b1', 'folio_id': 'f1', 'currency': 'TRY',
        'charge_category': 'food', 'charge_type': 'service', 'amount': 100, 'subtotal': 100, 'discount_amount': 0,
        'vat_amount': 20, 'tax_amount': 0, 'tax_breakdown': {'vat': 20}, 'total': 120,
        'quantity': 1, 'business_date': '2026-10-25', 'voided': False, source_field: 'origin', 'line_no': 0}
    await database.folio_charges.insert_one(deepcopy(charge))
    return charge


async def transfer(database, amount=48, operation=None):
    operation = operation or uuid4()
    body = ChargeSplit(charge_id='meal', target_booking_id='b2', split_amount=amount,
        reason='Misafirlerin birlikte kullandığı hizmetin paylaşılması', request_id=operation)
    async def commit(session):
        return await split_service_charge(database, 't', 'Ayşe Kaya', 'b1', body, operation, session=session, actor_id='manager')
    return await with_resource_locks(client=database.client, db=database, tenant_id='t', locks_collection='folio_locks',
        resources=[('booking', 'b1'), ('booking', 'b2')], callback=commit)


@pytest.mark.parametrize('field,index', [('source_minibar_log_id', 'ux_folio_charges_minibar_source'),
    ('source_pos_order_id', 'ux_folio_charges_pos_source'), ('source_laundry_order_id', 'ux_folio_charges_laundry_source'),
    ('source_transport_booking_id', 'ux_folio_charges_transport_source')])
async def test_real_source_indexes_allow_multiple_transfers_without_losing_source_or_tax(db, field, index):
    await seed(db, field, index)
    operation = uuid4()
    first = await transfer(db, operation=operation)
    assert first['new_charge']['line_no'] == 'split:' + str(operation)
    assert first['new_charge']['source_line_no'] == 0 and first['new_charge'][field] == 'origin'
    assert (await transfer(db, operation=operation))['replayed']
    await transfer(db, amount=12)
    rows = await db.folio_charges.find({}).to_list(None)
    assert len(rows) == 3 and len({r['line_no'] for r in rows}) == 3
    assert sum(r['total'] for r in rows) == 120 and sum(r['vat_amount'] for r in rows) == 20
    assert (await db.folios.find_one({'id': 'f1'}))['balance'] == 60
    assert (await db.folios.find_one({'id': 'f2'}))['balance'] == 60
    assert await db.folio_operations.count_documents({}) == 2
    logs = await db.audit_logs.find({}).to_list(None)
    assert len(logs) == 4 and all(row.get('record_hash') and row['actor_id'] == 'manager' for row in logs)
    assert {row['action'] for row in logs} == {'charge_split', 'charge_received'}


async def test_missing_transfer_audit_rolls_back_both_rooms_and_financial_operation(db, monkeypatch):
    from unittest.mock import AsyncMock

    await seed(db, 'source_minibar_log_id', 'ux_folio_charges_minibar_source')
    monkeypatch.setattr('modules.pms_core.service_charge_split.audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await transfer(db)
    assert await db.folio_charges.count_documents({}) == 1
    assert (await db.folio_charges.find_one({'id': 'meal'}))['total'] == 120
    assert (await db.folios.find_one({'id': 'f1'}))['balance'] == 120
    assert (await db.folios.find_one({'id': 'f2'}))['balance'] == 0
    assert not await db.folio_operations.count_documents({})


async def test_pos_redelivery_after_transfer_is_proven_and_refund_refreshes_both_rooms(db, monkeypatch):
    original = await seed(db, 'source_pos_order_id', 'ux_folio_charges_pos_source')
    monkeypatch.setattr(consumer, 'get_system_db', lambda: db)
    await transfer(db)
    await transfer(db, amount=12)
    event = {'tenant_id': 't', 'event_type': POS_CHARGE_POSTED,
        'payload': {'folio_id': 'f1', 'booking_id': 'b1', 'source_pos_order_id': 'origin', 'charges': [original]}}
    assert (await consumer.handle_ic_pos_event(deepcopy(event)))[0]
    assert await db.folio_charges.count_documents({}) == 3
    assert (await db.folios.find_one({'id': 'f2'}))['balance'] == 60
    # An altered source event cannot hide behind a legitimate transfer.
    altered = deepcopy(event)
    altered['payload']['charges'][0]['total'] = 121
    assert not (await consumer.handle_ic_pos_event(altered))[0]
    # A missing/corrupted target part is not proof of a harmless duplicate.
    await db.folio_charges.update_one({'split_from_charge_id': 'meal'}, {'$set': {'total': 49}})
    assert not (await consumer.handle_ic_pos_event(deepcopy(event)))[0]
    await db.folio_charges.update_one({'split_from_charge_id': 'meal'}, {'$set': {'total': 48}})
    reversal = {'tenant_id': 't', 'entity_id': 'origin', 'event_type': POS_CHARGE_REVERSED,
        'payload': {'folio_id': 'f1', 'source_pos_order_id': 'origin', 'reason': 'Tam iade'}}
    await db.outbox_events.insert_one(deepcopy(reversal))
    assert (await consumer.handle_ic_pos_event(reversal))[0]
    assert (await db.folios.find_one({'id': 'f1'}))['balance'] == 0
    assert (await db.folios.find_one({'id': 'f2'}))['balance'] == 0
    assert not await db.folio_charges.count_documents({'voided': {'$ne': True}})
    assert (await consumer.handle_ic_pos_event(event))[0]
    assert not await db.folio_charges.count_documents({'voided': {'$ne': True}})
