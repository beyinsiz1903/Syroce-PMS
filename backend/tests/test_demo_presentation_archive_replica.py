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


async def linked_direct_guest(db, *, embedded=None, tenant=None):
    bid = '438a48d7-8f67-4bd6-b0f6-ee0dfe2cbf21'
    await db.bookings.update_one({'id': bid}, {'$set': {'guest_id': 'direct-guest'}, '$unset': {'guest_name': ''}})
    if embedded is not None:
        await db.bookings.update_one({'id': bid}, {'$set': {'guest_name': embedded}})
    await db.guests.insert_one({'tenant_id': tenant or archive.TENANT, 'id': 'direct-guest', 'name': archive.SOURCES[bid]})
    return bid


async def test_direct_booking_without_embedded_name_uses_scoped_link_and_preserves_raw_booking(seeded):
    bid = await linked_direct_guest(seeded)
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert not reviewed['blocked'] and len(reviewed['eligible']) == 7
    public = next(row for row in archive.public_plan(reviewed)['eligible'] if row['id'] == bid)
    assert public['guest_name'] == archive.SOURCES[bid]
    body = await request(seeded)
    await archive.apply(seeded, actor(), body)
    receipt = await seeded.demo_presentation_archives.find_one({})
    evidence = next(row for row in receipt['before_images'] if row['booking']['id'] == bid)
    assert 'guest_name' not in evidence['booking']
    assert evidence['verified_identity']['linked_guest'] == {'id': 'direct-guest', 'name': archive.SOURCES[bid]}
    assert (await seeded.guests.find_one({'id': 'direct-guest'}))['name'] == archive.SOURCES[bid]


@pytest.mark.parametrize('change', ['foreign_profile', 'missing_profile', 'contradictory_cache'])
async def test_guest_identity_fallback_never_accepts_foreign_missing_or_contradictory_source(seeded, change):
    bid = await linked_direct_guest(seeded, embedded='Başka Misafir' if change == 'contradictory_cache' else None,
        tenant='foreign-hotel' if change == 'foreign_profile' else None)
    if change == 'missing_profile':
        await seeded.guests.delete_many({})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert any(row['id'] == bid and 'source_identity_changed' in row['reasons'] for row in reviewed['blocked'])
    assert not await seeded.demo_presentation_archives.count_documents({})
    assert (await seeded.bookings.find_one({'id': bid}))['status'] == 'confirmed'


async def test_linked_guest_rename_after_preview_invalidates_source_hash_before_any_archive(seeded):
    await linked_direct_guest(seeded)
    body = await request(seeded)
    await seeded.guests.update_one({'id': 'direct-guest'}, {'$set': {'name': 'Farklı Misafir'}})
    with pytest.raises(HTTPException) as error:
        await archive.apply(seeded, actor(), body)
    assert error.value.status_code == 409
    assert await seeded.bookings.count_documents({'status': 'confirmed'}) == 7
    assert not await seeded.demo_presentation_archives.count_documents({})


async def original_queue_orphan(database, bid):
    await database.bookings.update_one({'id': bid}, {'$set': archive.REVIEWED_SYNTHETIC_ORPHANS[bid]})


@pytest.mark.parametrize('bid', list(archive.REVIEWED_SYNTHETIC_ORPHANS))
async def test_only_reviewed_original_queue_orphan_can_archive_without_creating_a_guest(seeded, bid):
    await original_queue_orphan(seeded, bid)
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert not reviewed['blocked']
    evidence = next(row for row in reviewed['eligible'] if row['booking']['id'] == bid)
    assert evidence['verified_identity']['basis'] == 'reviewed_legacy_synthetic_orphan'
    await archive.apply(seeded, actor(), await request(seeded, [bid]))
    assert not await seeded.guests.count_documents({})
    assert await seeded.rooms.count_documents({'id': 'QT2ED0', 'status': 'occupied'}) == 1
    log = await seeded.audit_logs.find_one({'entity_id': bid})
    assert log['metadata']['identity_basis'] == 'reviewed_legacy_synthetic_orphan'
    assert log['record_hash'] and log['actor_id'] == actor().id and log['metadata']['reason']


@pytest.mark.parametrize('bid', list(archive.REVIEWED_SYNTHETIC_ORPHANS))
@pytest.mark.parametrize('field', ['guest_id', 'created_at', 'guest_name'])
async def test_queue_orphan_manifest_cannot_accept_reassigned_or_changed_source(seeded, bid, field):
    await original_queue_orphan(seeded, bid)
    body = await request(seeded, [bid])
    await seeded.bookings.update_one({'id': bid}, {'$set': {field: 'changed-source'}})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert any(row['id'] == bid and 'source_identity_changed' in row['reasons'] for row in reviewed['blocked'])
    with pytest.raises(HTTPException) as error:
        await archive.apply(seeded, actor(), body)
    assert error.value.status_code == 409
    assert not await seeded.demo_presentation_archives.count_documents({})


@pytest.mark.parametrize('bid', list(archive.REVIEWED_SYNTHETIC_ORPHANS))
async def test_reviewed_orphan_never_overrides_an_existing_conflicting_profile(seeded, bid):
    await original_queue_orphan(seeded, bid)
    await seeded.guests.insert_one({'tenant_id': archive.TENANT,
        'id': archive.REVIEWED_SYNTHETIC_ORPHANS[bid]['guest_id'], 'name': 'Gerçek Misafir'})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert any(row['id'] == bid and 'source_identity_changed' in row['reasons'] for row in reviewed['blocked'])


async def test_all_seven_actual_source_shapes_archive_once_and_preserve_each_identity_basis(seeded):
    for bid in archive.REVIEWED_SYNTHETIC_ORPHANS:
        await original_queue_orphan(seeded, bid)
    await linked_direct_guest(seeded)
    for bid, name in archive.SOURCES.items():
        if bid in archive.REVIEWED_SYNTHETIC_ORPHANS or bid == '438a48d7-8f67-4bd6-b0f6-ee0dfe2cbf21':
            continue
        await seeded.bookings.update_one({'id': bid}, {'$set': {'guest_id': 'profile-' + bid}})
        await seeded.guests.insert_one({'tenant_id': archive.TENANT, 'id': 'profile-' + bid, 'name': name})
    body = await request(seeded)
    result = await archive.apply(seeded, actor(), body)
    assert len(result['archived_ids']) == 7
    receipt = await seeded.demo_presentation_archives.find_one({})
    assert len(receipt['before_images']) == 7
    assert sum(row['verified_identity']['basis'] == 'reviewed_legacy_synthetic_orphan' for row in receipt['before_images']) == 2
    assert (await archive.apply(seeded, actor(), body))['replayed']
    assert await seeded.audit_logs.count_documents({'action': 'demo_reservation_archived'}) == 7
    assert await seeded.guests.count_documents({}) == 5


@pytest.mark.parametrize('bid', list(archive.REVIEWED_SYNTHETIC_ORPHANS))
async def test_reviewed_original_orphan_still_rejects_even_zero_valued_financial_source(seeded, bid):
    await original_queue_orphan(seeded, bid)
    await seeded.folio_charges.insert_one({'tenant_id': archive.TENANT, 'booking_id': bid, 'amount': 0})
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert any(row['id'] == bid and row['reasons'] == ['financial_or_service_sources_exist'] for row in reviewed['blocked'])
    with pytest.raises(HTTPException) as error:
        await archive.apply(seeded, actor(), await request(seeded, [bid]))
    assert error.value.status_code == 409
    assert not await seeded.demo_presentation_archives.count_documents({})


async def test_eligible_subset_can_archive_without_touching_two_blocked_sources(seeded):
    blocked = set(archive.REVIEWED_SYNTHETIC_ORPHANS)
    for bid in blocked:
        await seeded.bookings.update_one({'id': bid}, {'$set': {'guest_id': 'not-reviewed-profile'}})
    body = await request(seeded)
    assert set(body.booking_ids) == set(archive.SOURCES) - blocked
    result = await archive.apply(seeded, actor(), body)
    assert len(result['archived_ids']) == 5
    assert await seeded.bookings.count_documents({'id': {'$in': list(blocked)}, 'status': 'confirmed'}) == 2
    reviewed = await archive.plan(seeded, archive.TENANT)
    assert not reviewed['eligible'] and len(reviewed['blocked']) == 2 and len(reviewed['already_archived']) == 5
    assert await seeded.rooms.count_documents({'id': 'QT2ED0', 'status': 'occupied'}) == 1
    assert await seeded.audit_logs.count_documents({'action': 'demo_reservation_archived'}) == 5
