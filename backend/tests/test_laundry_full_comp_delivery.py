"""Full comp applies to future source-module services, not just manual extras."""
import asyncio

import pytest

from core.laundry_delivery import deliver_laundry
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa:F401
from tests.test_laundry_delivery_acceptance import laundry as laundry  # noqa:F401

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('scope,expected', [('full', 0), ('accommodation', 15), ('fnb', 15), (None, 15)])
async def test_future_laundry_obeys_full_comp_but_other_scopes_stay_paid(acceptance, scope, expected):
    a = acceptance
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'is_complimentary': bool(scope), 'complimentary_scope': scope}})
    await a.db.tenant_settings.update_one({'tenant_id': 'qa'}, {'$set': {'laundry_orders.0.items': [{'name': 'Gömlek', 'quantity': 1, 'total': 15, 'vat_rate': 20}]}})
    from core.laundry_tax import laundry_tax_snapshot
    await a.db.tenant_settings.update_one({'tenant_id': 'qa'}, {'$set': {'laundry_orders.0.tax_snapshot': laundry_tax_snapshot([{'total': 15, 'vat_rate': 20}], 'USD')}})
    first = await deliver_laundry(a.db, 'qa', 'wash', a.user)
    replay = await deliver_laundry(a.db, 'qa', 'wash', a.user)
    charge = await a.db.folio_charges.find_one({'charge_type': 'laundry'})
    ledger = await a.db.folio_ledger.find_one({'id': charge['source_ledger_entry_id']})
    assert first['folio_charge']['amount'] == expected
    assert replay['folio_charge']['replayed']
    assert replay['folio_charge']['is_complimentary'] is (scope == 'full')
    assert charge['total'] == ledger['amount'] == expected
    assert charge['net_amount'] == (0 if scope == 'full' else 12.5)
    assert charge['vat_amount'] == (0 if scope == 'full' else 2.5)
    assert charge['is_complimentary'] is (scope == 'full')
    assert await a.db.folio_charges.count_documents({'charge_type': 'laundry'}) == 1
    assert await a.db.payments.count_documents({}) == 0
    order = (await a.db.tenant_settings.find_one({'tenant_id': 'qa'}))['laundry_orders'][0]
    assert order['status'] == 'delivered' and order['total'] == 15
    if scope == 'full':
        assert charge['complimentary_original_amount'] == 15
        assert ledger['complimentary_original_amount'] == 15
        assert order['folio_financial_total'] == 0 and order['complimentary_original_amount'] == 15


async def test_comp_change_never_reprices_an_existing_delivered_source(acceptance):
    a = acceptance
    first = await deliver_laundry(a.db, 'qa', 'wash', a.user)
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'is_complimentary': True, 'complimentary_scope': 'full'}})
    replay = await deliver_laundry(a.db, 'qa', 'wash', a.user)
    assert first['folio_charge']['amount'] == replay['folio_charge']['amount'] == 15
    charge = await a.db.folio_charges.find_one({'charge_type': 'laundry'})
    assert not charge['is_complimentary'] and charge['total'] == 15


async def test_comp_policy_change_during_delivery_retries_with_current_policy(acceptance, monkeypatch):
    a = acceptance
    read, release = asyncio.Event(), asyncio.Event()
    collection_type = type(a.db.folios)
    original = collection_type.find_one
    paused = False

    async def pause_after_booking_read(self, *args, **kwargs):
        nonlocal paused
        if self.name == 'folios' and kwargs.get('session') is not None and not paused:
            paused = True
            read.set()
            await asyncio.wait_for(release.wait(), 5)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(collection_type, 'find_one', pause_after_booking_read)
    delivery = asyncio.create_task(deliver_laundry(a.db, 'qa', 'wash', a.user))
    await asyncio.wait_for(read.wait(), 5)
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'is_complimentary': True, 'complimentary_scope': 'full'}})
    release.set()
    assert (await delivery)['folio_charge']['amount'] == 0
    assert await a.db.folio_charges.count_documents({'charge_type': 'laundry'}) == 1
