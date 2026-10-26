"""Actual LOCAL Mongo transactions, canonical folio debt and audit rows."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.spa import router as spa
from domains.spa.folio import amounts
from modules.pms_core.receivable_reporting import folio_snapshots
from shared_kernel import audit_helper
from tests.test_pos_final_consistency_replica import db  # noqa: F401


def user():
    return SimpleNamespace(id='manager', tenant_id='t', name='Ayşe Kaya', role='admin', is_super_admin=False)


@pytest_asyncio.fixture
async def wired(db, monkeypatch):  # noqa: F811
    for name in ('spa_locks', 'spa_appointments', 'folio_charges', 'folio_postings', 'folios', 'bookings',
                 'payments', 'audit_logs', 'audit_chain_state'):
        await db.create_collection(name)
    await db.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-10-25'}})
    await db.bookings.insert_one({'id': 'b', 'tenant_id': 't', 'status': 'checked_in', 'currency': 'TRY'})
    await db.folios.insert_one({'id': 'actual-folio', 'booking_id': 'b', 'tenant_id': 't', 'status': 'open', 'currency': 'TRY', 'balance': 0})
    await db.spa_appointments.insert_one({'id': 'a', 'tenant_id': 't', 'status': 'scheduled', 'reservation_id': 'b',
        'charge_to_room': True, 'price': 1500, 'tax_rate': .2, 'currency': 'TRY', 'service_name': 'İsveç Masajı',
        'notes': 'Misafir talebi; oda hesabına aktarım'})
    monkeypatch.setattr(spa, 'get_system_db', lambda: db)
    monkeypatch.setattr(audit_helper, 'db', db)
    monkeypatch.setattr('core.audit_chain._system_db', lambda: db)
    monkeypatch.setattr(spa, '_publish_posting', AsyncMock())
    return db


async def complete():
    return await spa.change_status('a', spa.StatusUpdate(status='completed'), current_user=user())


async def test_completion_is_actual_receivable_with_known_vat_and_real_folio_identity(wired):
    assert (await complete())['status'] == 'completed'
    charge = await wired.folio_charges.find_one({'tenant_id': 't'})
    assert charge['booking_id'] == 'b' and charge['folio_id'] == 'actual-folio'
    assert charge['amount'] == 1250 and charge['vat_amount'] == 250 and charge['total'] == 1500
    assert charge['tax_breakdown'] == {'vat': 250} and charge['tax_amount'] == 0
    assert charge['business_date'] == '2026-10-25' and charge['charge_category'] == 'spa'
    folio = await wired.folios.find_one({'id': 'actual-folio'})
    snap = (await folio_snapshots(wired, 't', [folio], fallback_currency='TRY'))['actual-folio']
    assert folio['balance'] == snap['balance_by_currency']['TRY'] == 1500
    posting = await wired.folio_postings.find_one({'tenant_id': 't'})
    assert posting['folio_charge_id'] == charge['id'] and posting['folio_id'] == folio['id']
    audit = await wired.audit_logs.find_one({'action': 'spa_charge_posted'})
    assert audit['actor_id'] == 'manager' and audit['entity_id'] == 'b' and audit.get('record_hash')
    assert audit['metadata']['total'] == 1500 and audit['metadata']['currency'] == 'TRY'
    assert audit['metadata']['reason'] == 'Misafir talebi; oda hesabına aktarım'


async def test_concurrent_completion_and_source_replay_cannot_double_debt(wired):
    results = await asyncio.gather(complete(), complete(), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert all(isinstance(result, dict) or isinstance(result, HTTPException) and result.status_code == 409 for result in results)
    appt = await wired.spa_appointments.find_one({'id': 'a'})
    assert (await spa._post_to_folio('t', appt, actor_id='manager', actor_name='Ayşe Kaya'))['replayed']
    assert await wired.folio_charges.count_documents({}) == await wired.folio_postings.count_documents({}) == 1
    assert await wired.audit_logs.count_documents({'action': 'spa_charge_posted'}) == 1
    altered = deepcopy(appt)
    altered['price'] = 1600
    with pytest.raises(HTTPException) as error:
        await spa._post_to_folio('t', altered, actor_id='manager', actor_name='Ayşe Kaya')
    assert error.value.status_code == 409


@pytest.mark.parametrize('change,code', [({'status': 'checked_out'}, 409), ({'tenant_id': 'other'}, 404), ({'currency': 'EUR'}, 409)])
async def test_invalid_reservation_cannot_be_charged_or_completed(wired, change, code):
    await wired.bookings.update_one({'id': 'b'}, {'$set': change})
    with pytest.raises(HTTPException) as error:
        await complete()
    assert error.value.status_code == code
    assert not await wired.folio_charges.count_documents({}) and not await wired.folio_postings.count_documents({})
    assert (await wired.spa_appointments.find_one({'id': 'a'}))['status'] == 'scheduled'


async def test_full_comp_keeps_original_price_without_creating_guest_debt(wired):
    await wired.bookings.update_one({'id': 'b'}, {'$set': {'is_complimentary': True, 'complimentary_scope': 'full'}})
    await complete()
    charge = await wired.folio_charges.find_one({})
    assert charge['total'] == charge['amount'] == charge['vat_amount'] == 0
    assert charge['complimentary_original_amount'] == 1500 and charge['tax_breakdown'] == {'vat': 0}
    assert (await wired.folios.find_one({}))['balance'] == 0


async def test_posting_or_audit_failure_rolls_back_charge_and_completion(wired, monkeypatch):
    from domains.spa import folio

    monkeypatch.setattr(folio, 'audit_log', AsyncMock(side_effect=RuntimeError('audit write unavailable')))
    with pytest.raises(RuntimeError, match='audit write'):
        await complete()
    assert not await wired.folio_charges.count_documents({}) and not await wired.folio_postings.count_documents({})
    assert (await wired.folios.find_one({}))['balance'] == 0
    assert (await wired.spa_appointments.find_one({}))['status'] == 'scheduled'


async def test_multiple_folio_windows_require_explicit_selection(wired):
    await wired.folios.insert_one({'id': 'company-folio', 'booking_id': 'b', 'tenant_id': 't', 'status': 'open', 'currency': 'TRY'})
    with pytest.raises(HTTPException) as error:
        await complete()
    assert error.value.status_code == 409
    await wired.spa_appointments.update_one({'id': 'a'}, {'$set': {'folio_id': 'actual-folio'}})
    await complete()
    assert (await wired.folio_charges.find_one({}))['folio_id'] == 'actual-folio'


def test_missing_vat_is_not_fabricated_as_tax_free():
    with pytest.raises(HTTPException) as error:
        amounts({'price': 1500})
    assert error.value.status_code == 409
