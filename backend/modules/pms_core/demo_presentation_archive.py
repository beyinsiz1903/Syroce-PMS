"""Reviewed, reversible local archive of seven known synthetic demo bookings.

Not a guest deletion, provider cancellation, no-show, or a financial cleanup.
Any financial/service source blocks archival. Full before-images are retained.
"""
import json
from datetime import UTC, date, datetime
from hashlib import sha256

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks
from shared_kernel.audit_helper import audit_log

TENANT = '5bad4a34-6ee3-4566-9053-741b7375a9cf'
POLICY = 'synthetic-presentation-archive-20261027-v1'
SOURCES = {
    'queue-test-94d3ffd931': 'Queue Tester',
    'queue-test-b403202216': 'Queue Tester',
    '05cc2a5f-b4ac-5e25-81a2-7aa3e2c72382': 'CertMapping SyntheticTest',
    '4a4bf51e-82c7-5972-aefe-90b4525e0012': 'TestChildAgeSix SyroceQAOctober',
    '81ee0d74-bccb-5112-b275-61767f6e1eec': 'Syroce Deluxe QA Certification',
    'bd6dd709-d7e7-50f7-bd13-0e3de7756525': 'Syroce QA Certification',
    '438a48d7-8f67-4bd6-b0f6-ee0dfe2cbf21': 'Exely Certification Test',
}
FINANCIAL = ('payments', 'folio_charges', 'extra_charges', 'deposits', 'security_funds', 'invoices',
             'cari_transactions', 'city_ledger_transactions', 'billing_settlements')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


async def guard(db, tid, session=None):
    if tid != TENANT:
        raise HTTPException(404, 'Demo arşiv kapsamı bulunamadı')
    tenant = await db.tenants.find_one({'id': tid}, session=session)
    if not tenant or str(tenant.get('hotel_id')) != '100001' or tenant.get('property_name') != 'Syroce Demo Hotel':
        raise HTTPException(409, 'Demo tesis kimliği doğrulanamadı')
    settings = await db.tenant_settings.find_one({'tenant_id': tid}, session=session)
    try:
        day = date.fromisoformat(str((settings or {}).get('business_date'))).isoformat()
    except ValueError:
        raise HTTPException(409, 'Demo iş günü doğrulanamadı') from None
    runner = await db.hotelrunner_connections.find_one({'tenant_id': tid, 'is_active': True}, session=session)
    exely = await db.exely_connections.find({'tenant_id': tid, 'is_active': True}, session=session).to_list(None)
    if runner or any(row.get('ari_write_enabled') or row.get('auto_sync_reservations') or row.get('mode') != 'sandbox'
                     or str(row.get('hotel_code')) != '501694' for row in exely):
        raise HTTPException(409, 'Demo dış kanal gönderimleri kapalı ve TEST bağlantısı sandbox olmalı')
    connectors = await db.cm_connectors.find({'tenant_id': tid}, session=session).to_list(None)
    if any(row.get('status') not in {'paused', 'disconnected', 'inactive'} for row in connectors):
        raise HTTPException(409, 'Demo kanal bağlantıları duraklatılmış olmalı')
    return day


async def plan(db, tid, session=None):
    day = await guard(db, tid, session)
    rows = await db.bookings.find({'tenant_id': tid, 'id': {'$in': list(SOURCES)}}, {'_id': 0}, session=session).to_list(None)
    eligible, blocked, archived = [], [], []
    for booking in sorted(rows, key=lambda row: row['id']):
        bid = booking['id']
        if booking.get('status') == 'archived_demo' and (booking.get('presentation_archive') or {}).get('policy_id') == POLICY:
            archived.append(bid)
            continue
        reasons = []
        if booking.get('guest_name') != SOURCES[bid]:
            reasons.append('source_identity_changed')
        if booking.get('status') not in {'confirmed', 'pending', 'guaranteed'}:
            reasons.append('not_a_future_unarrived_reservation')
        try:
            arrival = date.fromisoformat(str(booking.get('check_in', ''))[:10]).isoformat()
            departure = date.fromisoformat(str(booking.get('check_out', ''))[:10]).isoformat()
            valid_dates = arrival > day and departure > arrival
        except ValueError:
            valid_dates = False
        if not valid_dates or any(booking.get(k) for k in ('checked_in_at', 'checked_out_at', 'actual_check_in', 'actual_check_out')):
            reasons.append('stay_started_or_date_due')
        folios = await db.folios.find({'tenant_id': tid, 'booking_id': bid}, {'_id': 0}, session=session).to_list(None)
        fid = [f['id'] for f in folios if f.get('id')]
        scope = {'tenant_id': tid, '$or': [{'booking_id': bid}, {'reservation_id': bid}, {'folio_id': {'$in': fid}}]}
        counts = {collection: await db[collection].count_documents(scope, session=session) for collection in FINANCIAL}
        for collection in ('spa_appointments', 'minibar_consumptions', 'pos_orders'):
            counts[collection] = await db[collection].count_documents({'tenant_id': tid,
                '$or': [{'booking_id': bid}, {'reservation_id': bid}]}, session=session)
        if any(counts.values()) or any(float(f.get('balance') or 0) != 0 for f in folios):
            reasons.append('financial_or_service_sources_exist')
        if reasons:
            blocked.append({'id': bid, 'reasons': reasons, 'source_counts': counts})
            continue
        locks = await db.room_night_locks.find({'tenant_id': tid, 'booking_id': bid}, {'_id': 0}, session=session).to_list(None)
        eligible.append({'booking': booking, 'empty_folios': folios, 'room_night_locks': locks})
    result = {'policy_id': POLICY, 'business_date': day, 'eligible': eligible, 'blocked': blocked,
        'already_archived': archived, 'missing_known_ids': sorted(set(SOURCES) - {b['id'] for b in rows})}
    result['source_fingerprint'] = digest(result)
    return result


def public_plan(result):
    return {**result, 'eligible': [{'id': row['booking']['id'], 'guest_name': row['booking']['guest_name'],
        'check_in': row['booking']['check_in'], 'lock_count': len(row['room_night_locks']),
        'empty_folio_count': len(row['empty_folios'])} for row in result['eligible']]}


async def apply(db, user, data):
    tid, actor = user.tenant_id, user.id
    await guard(db, tid)
    # Force collections/index creation outside a transaction on fresh installs.
    await db.demo_presentation_archives.create_index([('tenant_id', 1), ('request_id', 1)], unique=True)
    await db.minibar_locks.create_index([('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)
    request = data.model_dump(mode='json')
    if not set(request['booking_ids']).issubset(SOURCES) or len(set(request['booking_ids'])) != len(request['booking_ids']):
        raise HTTPException(422, 'Yalnız incelenmiş yapay rezervasyon kimlikleri arşivlenebilir')

    async def commit(session):
        prior = await db.demo_presentation_archives.find_one({'tenant_id': tid, 'request_id': str(data.request_id)}, {'_id': 0}, session=session)
        if prior:
            if prior['request_hash'] != digest(request):
                raise HTTPException(409, 'Arşiv istek anahtarı başka içerikle kullanılmış')
            return {**prior['result'], 'replayed': True}
        reviewed = await plan(db, tid, session)
        if reviewed['source_fingerprint'] != data.source_fingerprint:
            raise HTTPException(409, 'Arşiv kaynakları değişti; önizlemeyi yeniden inceleyin')
        selected = [row for row in reviewed['eligible'] if row['booking']['id'] in data.booking_ids]
        if len(selected) != len(data.booking_ids):
            raise HTTPException(409, 'Mali/hizmet kaynağı olan veya değişmiş rezervasyon arşivlenemez')
        now = datetime.now(UTC).isoformat()
        result = {'archived_ids': sorted(data.booking_ids), 'replayed': False, 'business_date': reviewed['business_date'],
            'provider_cancelled': False, 'physical_rooms_deleted': False, 'financial_sources_changed': False}
        receipt = {'tenant_id': tid, 'request_id': str(data.request_id), 'policy_id': POLICY,
            'request_hash': digest(request), 'before_images': selected, 'reason': data.reason, 'actor_id': actor,
            'created_at': now, 'result': result}
        await db.demo_presentation_archives.insert_one(receipt, session=session)
        for row in selected:
            booking = row['booking']; bid = booking['id']
            await db.bookings.update_one({'tenant_id': tid, 'id': bid}, {'$set': {
                'status': 'archived_demo', 'allocation_source': 'archived_demo_cleanup',
                'updated_at': now, 'updated_by': actor, 'presentation_archive': {'policy_id': POLICY,
                    'request_id': str(data.request_id), 'reason': data.reason, 'archived_at': now, 'archived_by': actor}}}, session=session)
            for folio in row['empty_folios']:
                await db.folios.update_one({'tenant_id': tid, 'id': folio['id']}, {'$set': {
                    'status': 'closed', 'closed_at': now, 'closure_reason': data.reason}}, session=session)
            await db.room_night_locks.delete_many({'tenant_id': tid, 'booking_id': bid}, session=session)
            await audit_log(actor_id=actor, tenant_id=tid, entity_type='reservation', entity_id=bid,
                action='demo_reservation_archived', metadata={'reason': data.reason, 'policy_id': POLICY,
                    'request_id': str(data.request_id), 'before_hash': digest(row), 'released_lock_count': len(row['room_night_locks']),
                    'provider_cancelled': False, 'financial_sources_changed': False}, session=session, require_chain=True)
        return result

    return await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection='minibar_locks',
        resources=[('demo_archive', tid), *[('booking', bid) for bid in sorted(data.booking_ids)]], callback=commit)
