"""Minibar financial tests against an explicitly selected LOCAL replica set."""
import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.pms import minibar_router as router
from shared_kernel import audit_helper
from tests.test_pos_final_consistency_replica import db  # noqa: F401


def user():
    return SimpleNamespace(tenant_id='t', id='manager', name='Mehmet Kaya', role='admin', is_super_admin=False)


def payload(key='consume', quantity=1):
    return router.ConsumeIn(room_id='room', idempotency_key=key, note='Oda misafiri tüketimi',
        lines=[router.ConsumeLine(item_id='water', quantity=quantity), router.ConsumeLine(item_id='chocolate', quantity=1)])


@pytest_asyncio.fixture
async def wired(db, monkeypatch):  # noqa: F811
    for name in ('minibar_items', 'minibar_consumptions', 'minibar_late_charges', 'minibar_locks',
                 'folios', 'folio_charges', 'bookings', 'rooms', 'payments', 'audit_logs', 'audit_chain_state'):
        await db.create_collection(name)
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-25'}})
    await db.bookings.insert_one({'id': 'b', 'tenant_id': 't', 'room_id': 'room', 'status': 'checked_in', 'currency': 'TRY'})
    await db.rooms.insert_one({'id': 'room', 'tenant_id': 't', 'room_number': '102'})
    await db.folios.insert_one({'id': 'f', 'tenant_id': 't', 'booking_id': 'b', 'currency': 'TRY', 'folio_type': 'guest', 'status': 'open', 'balance': 0})
    await db.minibar_items.insert_many([
        {'id': 'water', 'tenant_id': 't', 'name': 'Maden Suyu', 'price': 60, 'tax_rate': .2, 'currency': 'TRY', 'active': True},
        {'id': 'chocolate', 'tenant_id': 't', 'name': 'Çikolata', 'price': 110, 'tax_rate': .1, 'currency': 'TRY', 'active': True}])
    monkeypatch.setattr(router, 'db', db)
    monkeypatch.setattr(audit_helper, 'db', db)
    monkeypatch.setattr('core.audit_chain._system_db', lambda: db)
    return db


async def test_vat_currency_receivable_and_sealed_log_conserve_each_line(wired):
    result = await router.consume(payload(), user())
    assert result['posted_to_folio'] and result['consumption']['total'] == 170
    rows = await wired.folio_charges.find({}).sort('line_no', 1).to_list(None)
    assert [(r['amount'], r['vat_amount'], r['total']) for r in rows] == [(50, 10, 60), (100, 10, 110)]
    assert all(r['currency'] == 'TRY' and r['business_date'] == '2026-10-25' and r['tax_amount'] == 0 for r in rows)
    assert (await wired.folios.find_one({}))['balance'] == 170
    booking = await wired.bookings.find_one({'id': 'b'})
    assert booking['balance'] == 170 and booking['payment_status'] == 'pending'
    log = await wired.audit_logs.find_one({'action': 'minibar_consumed'})
    assert log['record_hash'] and log['actor_id'] == 'manager' and log['entity_id'] == 'b'
    assert log['metadata']['amount'] == 170 and log['metadata']['reason'] == 'Oda misafiri tüketimi'


async def test_replay_cannot_change_amount_or_create_double_consumption(wired):
    results = await asyncio.gather(router.consume(payload(), user()), router.consume(payload(), user()))
    assert any(r.get('idempotent') for r in results)
    assert await wired.minibar_consumptions.count_documents({}) == 1
    assert await wired.folio_charges.count_documents({}) == 2
    assert await wired.audit_logs.count_documents({}) == 1
    with pytest.raises(HTTPException) as error:
        await router.consume(payload(quantity=2), user())
    assert error.value.status_code == 409


async def test_replay_repairs_old_projection_without_replaying_consumption_or_audit(wired):
    await router.consume(payload(), user())
    await wired.bookings.update_one({'id': 'b'}, {'$set': {'balance': 9999, 'payment_status': 'paid'}})
    replay = await router.consume(payload(), user())
    booking = await wired.bookings.find_one({'id': 'b'})
    assert replay['idempotent'] and booking['balance'] == 170 and booking['payment_status'] == 'pending'
    assert await wired.folio_charges.count_documents({}) == 2
    assert await wired.minibar_consumptions.count_documents({}) == await wired.audit_logs.count_documents({}) == 1


async def test_legacy_broad_unique_index_does_not_silently_lose_second_product(wired):
    await wired.folio_charges.create_index([('tenant_id', 1), ('booking_id', 1), ('business_date', 1), ('charge_type', 1)],
        unique=True, name='legacy_broad', partialFilterExpression={'voided': False})
    with pytest.raises(HTTPException) as error:
        await router.consume(payload(), user())
    assert error.value.status_code == 409
    assert await wired.folio_charges.count_documents({}) == await wired.minibar_consumptions.count_documents({}) == 0
    assert (await wired.folios.find_one({}))['balance'] == 0
    assert not await wired.audit_logs.count_documents({})


@pytest.mark.parametrize('changes', [{'currency': 'USD'}, {'tax_rate': None}, {'active': False}])
async def test_invalid_catalog_never_creates_partial_debt(wired, changes):
    await wired.minibar_items.update_one({'id': 'chocolate'}, {'$set': changes})
    with pytest.raises(HTTPException) as error:
        await router.consume(payload(), user())
    assert error.value.status_code in {400, 409}
    assert not await wired.folio_charges.count_documents({}) and not await wired.minibar_consumptions.count_documents({})


async def test_full_comp_records_consumption_but_not_guest_debt(wired):
    await wired.bookings.update_one({'id': 'b'}, {'$set': {'is_complimentary': True, 'complimentary_scope': 'full'}})
    result = await router.consume(payload(), user())
    assert result['consumption']['total'] == 0
    rows = await wired.folio_charges.find({}).to_list(None)
    assert sum(row['total'] for row in rows) == 0 and sum(row['complimentary_original_amount'] for row in rows) == 170
    assert all(row['tax_breakdown'] == {'vat': 0} for row in rows)


async def test_missing_open_folio_is_visible_late_charge_not_false_posting(wired):
    await wired.folios.update_one({'id': 'f'}, {'$set': {'status': 'closed'}})
    result = await router.consume(payload(), user())
    assert not result['posted_to_folio'] and result['consumption']['status'] == 'late_charge'
    assert not await wired.folio_charges.count_documents({})
    assert (await wired.minibar_late_charges.find_one({}))['status'] == 'pending_review'


async def test_audit_failure_rolls_back_consumption_and_all_debt(wired, monkeypatch):
    from unittest.mock import AsyncMock

    from domains.pms import minibar_consumption
    monkeypatch.setattr(minibar_consumption, 'audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await router.consume(payload(), user())
    assert not await wired.folio_charges.count_documents({}) and not await wired.minibar_consumptions.count_documents({})
    assert (await wired.folios.find_one({}))['balance'] == 0


async def test_reservation_projection_failure_rolls_back_consumption(wired, monkeypatch):
    from unittest.mock import AsyncMock

    from domains.pms import minibar_consumption
    monkeypatch.setattr(minibar_consumption, 'refresh_booking_payment_state', AsyncMock(side_effect=RuntimeError('projection unavailable')))
    with pytest.raises(RuntimeError, match='projection unavailable'):
        await router.consume(payload(), user())
    assert not await wired.folio_charges.count_documents({}) and not await wired.minibar_consumptions.count_documents({})
    assert (await wired.folios.find_one({}))['balance'] == 0
