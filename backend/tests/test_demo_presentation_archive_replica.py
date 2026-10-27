"""Only an explicitly selected LOCAL replica set; no live hotel mutations."""
# Ruff: the imported pytest fixture is intentionally reused as an argument.
# ruff: noqa: F811
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from modules.pms_core import demo_presentation_archive as archive
from routers.reservation_detail import DemoPresentationArchiveIn
from shared_kernel import audit_helper
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest_asyncio.fixture
async def seeded(db, monkeypatch):  # noqa: F811
    for collection in ('bookings', 'folios', 'room_night_locks', 'audit_logs', 'audit_chain_state', 'minibar_locks'):
        await db.create_collection(collection)
    await db.tenants.insert_one({'id': archive.TENANT, 'hotel_id': '100001', 'property_name': 'Syroce Demo Hotel'})
    await db.tenant_settings.insert_one({'tenant_id': archive.TENANT, 'business_date': '2026-10-26'})
    await db.exely_connections.insert_one({'tenant_id': archive.TENANT, 'is_active': True, 'hotel_code': '501694',
        'mode': 'sandbox', 'ari_write_enabled': False, 'auto_sync_reservations': False})
    await db.cm_connectors.insert_one({'tenant_id': archive.TENANT, 'status': 'paused'})
    for number, (bid, name) in enumerate(archive.SOURCES.items()):
        await db.bookings.insert_one({'id': bid, 'tenant_id': archive.TENANT, 'guest_name': name,
            'check_in': '2027-11-13T14:00:00', 'check_out': '2027-11-15T12:00:00', 'status': 'confirmed',
            'room_id': 'QT2ED0' if number == 1 else None, 'allocation_source': 'pending_assignment', 'total_amount': 100})
        await db.room_night_locks.insert_one({'tenant_id': archive.TENANT, 'booking_id': bid, 'room_id': 'QT2ED0', 'night_date': '2027-11-13'})
    await db.rooms.insert_one({'id': 'QT2ED0', 'tenant_id': archive.TENANT, 'status': 'occupied'})
    monkeypatch.setattr(audit_helper, 'db', db)
    monkeypatch.setattr('core.audit_chain._system_db', lambda: db)
    return db


def actor():
    return SimpleNamespace(tenant_id=archive.TENANT, id='demo-manager', role='admin')


async def request(db, ids=None):
    reviewed = await archive.plan(db, archive.TENANT)
    return DemoPresentationArchiveIn(request_id=uuid4(), source_fingerprint=reviewed['source_fingerprint'],
        booking_ids=ids or [row['booking']['id'] for row in reviewed['eligible']],
        reason='Açık onaylı sunum temizliği; yalnız eski yapay rezervasyonlar arşivlenir',
        confirmation='ARCHIVE_REVIEWED_SYNTHETIC_DEMO_100001_ONLY')


async def test_archive_preserves_evidence_room_and_finance_with_one_replay(seeded):
    body = await request(seeded)
    result = await archive.apply(seeded, actor(), body)
    assert len(result['archived_ids']) == 7 and not result['provider_cancelled']
    assert await seeded.bookings.count_documents({'status': 'archived_demo'}) == 7
    assert await seeded.rooms.count_documents({'id': 'QT2ED0', 'status': 'occupied'}) == 1
    assert await seeded.room_night_locks.count_documents({}) == 0
    receipt = await seeded.demo_presentation_archives.find_one({})
    assert len(receipt['before_images']) == 7 and all(row['room_night_locks'] for row in receipt['before_images'])
    replay = await archive.apply(seeded, actor(), body)
    assert replay['replayed'] and await seeded.demo_presentation_archives.count_documents({}) == 1
    assert await seeded.audit_logs.count_documents({'action': 'demo_reservation_archived'}) == 7
    assert (await seeded.tenant_settings.find_one({'tenant_id': archive.TENANT}))['business_date'] == '2026-10-26'


@pytest.mark.parametrize('collection', [*archive.FINANCIAL, 'spa_appointments', 'minibar_consumptions', 'pos_orders'])
async def test_any_existing_financial_or_service_source_blocks_archive(seeded, collection):
    bid = next(iter(archive.SOURCES))
    await seeded[collection].insert_one({'tenant_id': archive.TENANT, 'booking_id': bid, 'amount': 0})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert reviewed['blocked'][0]['id'] == bid and 'financial_or_service_sources_exist' in reviewed['blocked'][0]['reasons']
    body = await request(seeded, [bid])
    with pytest.raises(HTTPException) as error:
        await archive.apply(seeded, actor(), body)
    assert error.value.status_code == 409
    assert (await seeded.bookings.find_one({'id': bid}))['status'] == 'confirmed'


async def test_unlinked_folio_payment_is_detected_even_without_booking_id(seeded):
    bid = next(iter(archive.SOURCES))
    await seeded.folios.insert_one({'id': 'f', 'tenant_id': archive.TENANT, 'booking_id': bid, 'status': 'open', 'balance': 0})
    await seeded.payments.insert_one({'tenant_id': archive.TENANT, 'folio_id': 'f', 'amount': 100})
    assert (await archive.plan(seeded, archive.TENANT))['blocked'][0]['source_counts']['payments'] == 1


async def test_audit_outage_rolls_back_archive_receipt_and_lock_release(seeded, monkeypatch):
    body = await request(seeded)
    monkeypatch.setattr(archive, 'audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError):
        await archive.apply(seeded, actor(), body)
    assert await seeded.bookings.count_documents({'status': 'confirmed'}) == 7
    assert await seeded.room_night_locks.count_documents({}) == 7
    assert await seeded.demo_presentation_archives.count_documents({}) == 0


async def test_concurrent_archive_replays_once(seeded):
    body = await request(seeded)
    results = await asyncio.gather(archive.apply(seeded, actor(), body), archive.apply(seeded, actor(), body))
    assert sorted(result['replayed'] for result in results) == [False, True]
    assert await seeded.audit_logs.count_documents({}) == 7


async def test_changed_sources_require_a_new_review(seeded):
    body = await request(seeded)
    await seeded.bookings.update_one({'id': body.booking_ids[0]}, {'$set': {'total_amount': 123}})
    with pytest.raises(HTTPException) as error:
        await archive.apply(seeded, actor(), body)
    assert error.value.status_code == 409


@pytest.mark.parametrize('change', ['hotel', 'tenant', 'provider', 'connector'])
async def test_scope_and_outbound_channel_guards(seeded, change):
    tid = archive.TENANT
    if change == 'hotel':
        await seeded.tenants.update_one({'id': tid}, {'$set': {'hotel_id': 'other-hotel'}})
    elif change == 'tenant':
        tid = 'another-tenant'
    elif change == 'provider':
        await seeded.exely_connections.update_one({'tenant_id': tid}, {'$set': {'auto_sync_reservations': True}})
    else:
        await seeded.cm_connectors.update_one({'tenant_id': tid}, {'$set': {'status': 'active'}})
    with pytest.raises(HTTPException) as error:
        await archive.plan(seeded, tid)
    assert error.value.status_code in {404, 409}
    assert await seeded.bookings.count_documents({'status': 'confirmed'}) == 7


async def test_real_guest_or_inhouse_booking_never_becomes_a_demo_archive(seeded):
    bid = next(iter(archive.SOURCES))
    await seeded.bookings.update_one({'id': bid}, {'$set': {'guest_name': 'Gerçek Misafir', 'status': 'checked_in'}})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert {'source_identity_changed', 'not_a_future_unarrived_reservation'}.issubset(reviewed['blocked'][0]['reasons'])
