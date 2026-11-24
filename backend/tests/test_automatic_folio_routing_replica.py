"""Real local transactions: new charges route once; old sources/receipts stay put."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from modules.pms_core.automatic_folio_routing import post_automatic_pos_charges, route_new_charge
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401

pytestmark = pytest.mark.asyncio


async def setup(a, **changes):
    await a.db.folios.insert_one({'id': 'company-window', 'tenant_id': 'qa', 'booking_id': 'synthetic-stay',
        'status': 'open', 'currency': 'USD', 'balance': 0, 'folio_type': 'company'})
    rule = {'id': 'route', 'tenant_id': 'qa', 'source_folio_id': 'synthetic-folio',
        'dest_folio_id': 'company-window', 'active': True, 'apply_to_future': True,
        'charge_codes': ['LAUNDRY'], 'from_date': '2026-10-26', 'to_date': '2026-10-26', **changes}
    await a.db.folio_routing.insert_one(rule)
    return {'id': 'new-charge', 'tenant_id': 'qa', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
        'currency': 'USD', 'charge_category': 'laundry', 'business_date': '2026-10-26', 'total': 15, 'amount': 15, 'voided': False}


async def resolve(a, charge):
    async with await a.db.client.start_session() as session:
        async def commit(s):
            target = await route_new_charge(a.db, 'qa', charge, session=s)
            await a.db.folio_charges.insert_one(dict(charge), session=s)
            return target
        return await session.with_transaction(commit)


@pytest.mark.parametrize('category', ['room', 'food', 'beverage', 'minibar', 'spa', 'laundry', 'parking', 'mice'])
async def test_new_categories_only_route_with_matching_rule(acceptance, category):
    a = acceptance
    charge = await setup(a, charge_codes=[category.upper()])
    charge['charge_category'] = category
    old = await a.db.folio_charges.find_one({'id': 'synthetic-room-charge'})
    await a.db.payments.insert_one({'id': 'cash', 'tenant_id': 'qa', 'folio_id': 'synthetic-folio', 'amount': 100})
    assert (await resolve(a, charge))['id'] == 'company-window'
    result = await a.db.folio_charges.find_one({'id': 'new-charge'})
    assert result['folio_id'] == 'company-window' and result['routing_rule_id'] == 'route'
    assert result['routing_source_folio_id'] == 'synthetic-folio'
    assert await a.db.folio_charges.find_one({'id': 'synthetic-room-charge'}) == old
    assert (await a.db.payments.find_one({'id': 'cash'}))['folio_id'] == 'synthetic-folio'


@pytest.mark.parametrize('changes', [{'apply_to_future': False}, {'active': False}, {'charge_codes': ['SPA']},
    {'from_date': '2026-10-27'}, {'to_date': '2026-10-25'}])
async def test_legacy_or_unmatched_rules_leave_new_charge_on_source(acceptance, changes):
    a = acceptance
    charge = await setup(a, **changes)
    assert await resolve(a, charge) is None
    assert (await a.db.folio_charges.find_one({'id': 'new-charge'}))['folio_id'] == 'synthetic-folio'


@pytest.mark.parametrize('change', [{'status': 'closed'}, {'tenant_id': 'other'}, {'currency': 'TRY'},
    {'booking_id': 'other'}, {'invoice_id': 'invoice'}])
async def test_invalid_destination_rolls_back_without_source_charge(acceptance, change):
    a = acceptance
    charge = await setup(a)
    await a.db.folios.update_one({'id': 'company-window'}, {'$set': change})
    with pytest.raises(HTTPException):
        await resolve(a, charge)
    assert not await a.db.folio_charges.count_documents({'id': 'new-charge'})
    assert 'posting_revision' not in await a.db.folio_routing.find_one({'id': 'route'})


async def test_overlap_and_missing_day_fail_without_financial_writes(acceptance):
    a = acceptance
    charge = await setup(a)
    other = await a.db.folio_routing.find_one({'id': 'route'}, {'_id': 0})
    await a.db.folio_routing.insert_one({**other, 'id': 'overlap'})
    with pytest.raises(HTTPException):
        await resolve(a, charge)
    assert not await a.db.folio_charges.count_documents({'id': 'new-charge'})
    await a.db.folio_routing.delete_one({'id': 'overlap'})
    charge.pop('business_date')
    with pytest.raises(HTTPException):
        await resolve(a, charge)


async def test_pos_routed_replay_after_rule_removal_keeps_one_source_and_balances(acceptance):
    a = acceptance
    charge = await setup(a)
    charge.update(source_pos_order_id='order', line_no=0)
    source = await a.db.folios.find_one({'id': 'synthetic-folio'})
    await post_automatic_pos_charges(a.db, 'qa', source, 'order', [deepcopy(charge)])
    await a.db.folio_routing.update_one({'id': 'route'}, {'$set': {'active': False}})
    await post_automatic_pos_charges(a.db, 'qa', source, 'order', [deepcopy(charge)])
    assert await a.db.folio_charges.count_documents({'source_pos_order_id': 'order'}) == 1
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 15
    assert (await a.db.folios.find_one({'id': 'synthetic-folio'}))['balance'] == 560
    assert await a.db.payments.count_documents({}) == 0


async def test_laundry_routes_source_ledger_and_charge_together_and_replays(acceptance):
    from core.laundry_delivery import deliver_laundry
    a = acceptance
    await setup(a)
    await a.db.tenant_settings.update_one({'tenant_id': 'qa'}, {'$set': {'laundry_orders': [{
        'id': 'wash', 'room_number': 'QA104', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
        'status': 'ready', 'total': 15, 'currency': 'USD', 'folio_charged': False,
        'items': [{'name': 'Shirt', 'quantity': 1}]}]}})
    await deliver_laundry(a.db, 'qa', 'wash', a.user)
    assert (await deliver_laundry(a.db, 'qa', 'wash', a.user))['folio_charge']['replayed']
    charge = await a.db.folio_charges.find_one({'charge_type': 'laundry'})
    ledger = await a.db.folio_ledger.find_one({'idempotency_key': 'laundry:wash'})
    assert charge['folio_id'] == ledger['folio_id'] == 'company-window'
    assert charge['total'] == ledger['amount'] == 15
    assert await a.db.folio_charges.count_documents({'charge_type': 'laundry'}) == 1


async def test_guest_card_extra_routes_without_copying_old_charge(acceptance):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    charge = await setup(a)
    charge.pop('folio_id')
    charge.update(category='laundry', charge_amount=15, charge_name='Laundry')
    result = await insert_booking_extra(a.db, 'qa', charge)
    assert result['folio_id'] == 'company-window'
    assert await a.db.extra_charges.count_documents({}) == 1
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 15
    assert (await a.db.folio_charges.find_one({'id': 'synthetic-room-charge'}))['folio_id'] == 'synthetic-folio'


async def test_spa_completion_routes_projection_and_replay_stays_stable(acceptance, monkeypatch):
    from domains.spa.folio import post_charge
    a = acceptance
    await setup(a, charge_codes=['SPA'])
    monkeypatch.setattr('shared_kernel.audit_helper.db', a.db)
    appt = {'id': 'appointment', 'reservation_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
        'currency': 'USD', 'price': 15, 'tax_rate': .2, 'service_name': 'Massage', 'completed_at': '2026-10-26T10:00:00Z'}
    async with await a.db.client.start_session() as session:
        async def commit(s):
            return await post_charge(a.db, 'qa', appt, a.user.id, a.user.name, session=s)
        first = await session.with_transaction(commit)
        second = await session.with_transaction(commit)
    assert first['charge']['folio_id'] == first['posting']['folio_id'] == 'company-window'
    assert second['replayed']
    assert await a.db.folio_postings.count_documents({}) == 1
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 15


async def test_department_source_replay_keeps_fingerprint_after_route(acceptance):
    from core.department_folio import post_source_charge
    a = acceptance
    await setup(a, charge_codes=['PARKING'])
    source = {'id': 'park', 'kind': 'parking', 'booking_id': 'synthetic-stay', 'folio_id': 'synthetic-folio',
        'currency': 'USD', 'gross': 15, 'tax': 2.5, 'description': 'Parking'}
    async with await a.db.client.start_session() as session:
        async def commit(s):
            return await post_source_charge(a.db, 'qa', source, a.user.id, session=s)
        first = await session.with_transaction(commit)
        second = await session.with_transaction(commit)
    assert first['charge']['folio_id'] == 'company-window'
    assert second['replayed']
    assert await a.db.folio_charges.count_documents({'source_transport_booking_id': 'park'}) == 1
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 15


async def test_guest_card_charge_api_uses_rule_before_first_insert(acceptance):
    a = acceptance
    await setup(a)
    response = await a.api.post('/api/frontdesk/folio/synthetic-stay/charge', json={
        'charge_category': 'laundry', 'description': 'Laundry', 'amount': 15, 'quantity': 1})
    assert response.status_code == 200, response.text
    charge = response.json()
    assert charge['folio_id'] == 'company-window'
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 15
    assert (await a.db.folios.find_one({'id': 'synthetic-folio'}))['balance'] == 560


async def test_unmatched_guest_card_extra_stays_on_unique_routing_source(acceptance):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    charge = await setup(a)
    charge.pop('folio_id')
    charge.update(category='minibar', charge_category='minibar', charge_amount=15)
    result = await insert_booking_extra(a.db, 'qa', charge)
    assert result['folio_id'] == 'synthetic-folio'
    assert (await a.db.folios.find_one({'id': 'synthetic-folio'}))['balance'] == 575
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 0


@pytest.mark.parametrize('other_active_rule', [False, True])
async def test_extra_after_destination_merge_owns_the_only_open_window(acceptance, other_active_rule):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    charge = await setup(a)
    await a.db.folio_routing.update_one({'id': 'route'}, {'$set': {'active': False}})
    await a.db.folios.update_one({'id': 'company-window'}, {'$set': {'status': 'closed'}})
    if other_active_rule:
        await a.db.folio_routing.insert_one({'id': 'elsewhere', 'tenant_id': 'qa', 'source_folio_id': 'unrelated',
            'dest_folio_id': 'unrelated-target', 'active': True, 'apply_to_future': True})
    charge.pop('folio_id')
    charge.update(category='minibar', charge_category='minibar', charge_amount=15)
    result = await insert_booking_extra(a.db, 'qa', charge)
    assert result['folio_id'] == 'synthetic-folio'
    assert await a.db.extra_charges.count_documents({'id': 'new-charge'}) == 1
    assert (await a.db.folios.find_one({'id': 'synthetic-folio'}))['balance'] == 575
    assert (await a.db.folios.find_one({'id': 'company-window'}))['balance'] == 0
    assert 'routing_rule_id' not in result


async def test_extra_cannot_fall_back_to_a_closed_modern_window(acceptance):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    await a.db.folios.update_many({'tenant_id': 'qa'}, {'$set': {'status': 'closed'}})
    with pytest.raises(HTTPException) as error:
        await insert_booking_extra(a.db, 'qa', {'id': 'blocked', 'booking_id': 'synthetic-stay', 'total': 15})
    assert error.value.status_code == 409
    assert await a.db.extra_charges.count_documents({'id': 'blocked'}) == 0


@pytest.mark.parametrize('change', [{'currency': 'TRY'}, {'invoice_id': 'sealed-invoice'}])
async def test_extra_fallback_does_not_bypass_window_guards(acceptance, change):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$set': change})
    with pytest.raises(HTTPException):
        await insert_booking_extra(a.db, 'qa', {'id': 'guarded', 'booking_id': 'synthetic-stay',
            'currency': 'USD', 'total': 15, 'charge_amount': 15})
    assert await a.db.extra_charges.count_documents({'id': 'guarded'}) == 0


async def test_unrouted_extra_with_multiple_open_windows_fails_without_writing(acceptance):
    from modules.pms_core.automatic_folio_routing import insert_booking_extra
    a = acceptance
    charge = await setup(a)
    await a.db.folio_routing.update_one({'id': 'route'}, {'$set': {'active': False}})
    charge.pop('folio_id')
    with pytest.raises(HTTPException) as error:
        await insert_booking_extra(a.db, 'qa', charge)
    assert error.value.status_code == 409
    assert await a.db.extra_charges.count_documents({'id': 'new-charge'}) == 0
