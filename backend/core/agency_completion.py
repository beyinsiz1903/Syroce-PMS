"""Booking-embedded durable completion queue: no booking/enqueue dual-write gap.

Local writes and outbox IDs are deterministic. Delivery is at-least-once;
remote webhook consumers must honor the stable idempotency key.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument

logger = logging.getLogger(__name__)


def pending_completion(kind):
    return {'kind': kind, 'status': 'pending', 'attempts': 0, 'done': [],
            'available_at': datetime.now(UTC), 'version': 1}


def stable_id(booking_id, step):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'syroce:agency:{booking_id}:{step}'))


def public_booking(booking):
    from security.encrypted_lookup import decrypt_booking_doc
    row = decrypt_booking_doc(dict(booking))
    keys = ('id', 'tenant_id', 'agency_id', 'confirmation_code', 'status', 'room_type', 'room_id',
            'room_number', 'rate_plan_code', 'meal_plan', 'cancellation_policy', 'check_in',
            'check_out', 'total_amount', 'currency', 'guest_name', 'hotel_name', 'created_at',
            'adults', 'children', 'payment_status', 'balance', 'net_to_hotel')
    return {**{key: row.get(key) for key in keys},
            'integration_status': row.get('agency_completion', {}).get('status', 'unknown')}


async def perform_step(database, booking, step):
    tenant = booking['tenant_id']
    bid = booking['id']
    now = datetime.now(UTC).isoformat()
    if step == 'ledger':
        # Snapshot derives only from the canonical committed booking.
        keys = ('id', 'tenant_id', 'agency_id', 'agency_name', 'hotel_name', 'confirmation_code',
                'external_reference', 'guest_name', 'room_id', 'room_type', 'room_number',
                'rate_plan_code', 'meal_plan', 'cancellation_policy', 'total_amount', 'currency',
                'nightly_rates', 'net_to_hotel', 'payment_terms', 'syroce_b2b_fee_pct', 'syroce_b2b_fee_amount')
        doc = {key: booking.get(key) for key in keys}
        doc.update(check_in=booking['check_in'][:10], check_out=booking['check_out'][:10],
                   idempotency_key=booking.get('agency_idempotency_key'),
                   commission_pct=booking.get('agency_commission_rate', 0),
                   commission_amount=booking.get('agency_commission_amount', 0),
                   status=booking.get('status'), payment_status=booking.get('payment_status'),
                   created_at=booking.get('created_at', now))
        await database.marketplace_bookings.update_one({'_id': stable_id(bid, 'ledger')}, {'$setOnInsert': doc}, upsert=True)
    elif step == 'folio':
        from models.schemas import Folio, FolioType
        folio = Folio(id=stable_id(bid, step), tenant_id=tenant, booking_id=bid,
                      folio_number=f'AG-{bid}',
                      guest_id=booking['guest_id'], folio_type=FolioType.GUEST).model_dump(mode='json')
        await database.folios.update_one({'_id': stable_id(bid, step)}, {'$setOnInsert': folio}, upsert=True)
    elif step == 'notification':
        doc = {'id': stable_id(bid, step), 'tenant_id': tenant, 'user_id': None, 'type': 'reservation',
               'title': 'Yeni acente rezervasyonu', 'message': booking.get('confirmation_code', bid),
               'priority': 'high', 'read': False, 'action_url': f'/reservations?booking_id={bid}',
               'metadata': {'booking_id': bid, 'agency_id': booking['agency_id']}, 'created_at': now}
        await database.notifications.update_one({'_id': stable_id(bid, step)}, {'$setOnInsert': doc}, upsert=True)
    elif step == 'inventory':
        from core.outbox_service import BOOKING_CREATED, enqueue_outbox_event
        await enqueue_outbox_event(database, tenant_id=tenant, event_type=BOOKING_CREATED,
                                   entity_type='booking', entity_id=bid, property_id=tenant,
                                   idempotency_key=stable_id(bid, step), correlation_id=bid,
                                   payload={'booking_id': bid, 'guest_id': booking['guest_id'],
                                            'room_id': booking['room_id'], 'check_in': booking['check_in'],
                                            'check_out': booking['check_out'], 'status': booking['status'],
                                            'property_id': tenant, 'source_channel': 'agency', 'origin': 'agency'})
    elif step == 'realtime':
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio
        await sio.emit('booking_created', {'booking': public_booking(booking)},
                       room=tenant_broadcast_room(tenant))
    elif step == 'audit':
        await database.pms_audit_trail.update_one({'_id': stable_id(bid, step)}, {'$setOnInsert': {
            'id': stable_id(bid, step), 'tenant_id': tenant, 'entity_id': bid,
            'entity_type': 'booking', 'action': 'agency_booking_created',
            'agency_id': booking['agency_id'], 'created_at': now,
            'timestamp': now, 'performed_by': booking.get('agency_user_id', 'agency_completion_worker'),
            'details': {'agency_id': booking['agency_id'], 'room_id': booking.get('room_id')},
        }}, upsert=True)
    elif step == 'webhooks':
        from routers.webhook_retry_service import deliver_webhook_with_retry
        event = 'marketplace.reservation.created' if booking['agency_completion']['kind'] == 'marketplace' else 'reservation.created'
        hooks = await database.agency_webhooks.find({'tenant_id': tenant, 'agency_id': booking['agency_id'],
                                                     'is_active': True, 'events': event}, {'_id': 0}).to_list(None)
        for hook in hooks:
            result = await deliver_webhook_with_retry(hook, event,
                {'reservation_id': bid, 'confirmation_code': booking.get('confirmation_code'),
                 'check_in': booking['check_in'], 'check_out': booking['check_out'],
                 'total_amount': booking['total_amount'], 'currency': booking.get('currency')},
                delivery_id=stable_id(bid, f"webhook:{hook['id']}"))
            if result.get('status') != 'succeeded':
                raise RuntimeError('webhook_delivery_failed')


async def process_one(database):
    now = datetime.now(UTC)
    owner = str(uuid.uuid4())
    booking = await database.bookings.find_one_and_update({
        '$or': [
            {'agency_completion.status': {'$in': ['pending', 'retry', 'waiting']}, 'agency_completion.available_at': {'$lte': now}},
            {'agency_completion.status': 'processing', 'agency_completion.lease_until': {'$lt': now}},
        ],
    }, {'$set': {'agency_completion.status': 'processing', 'agency_completion.owner': owner,
                 'agency_completion.lease_until': now + timedelta(minutes=2)}},
        sort=[('agency_completion.available_at', 1)], return_document=ReturnDocument.AFTER)
    if not booking:
        return False
    from security.encrypted_lookup import decrypt_booking_doc
    booking = decrypt_booking_doc(booking)
    state = booking['agency_completion']
    query = {'id': booking['id'], 'tenant_id': booking['tenant_id'], 'agency_completion.owner': owner}
    steps = (['ledger'] if state['kind'] == 'marketplace' else []) + ['folio', 'notification', 'inventory', 'audit', 'realtime', 'webhooks']
    step = 'delivery'
    try:
        failures = []
        for step in steps:
            if step in state.get('done', []):
                continue
            # Bound execution below the lease interval. A stopped process can
            # safely be retried because durable effects use stable identifiers.
            from core.tenant_db import tenant_context
            succeeded = False
            try:
                with tenant_context(booking['tenant_id']):
                    await asyncio.wait_for(perform_step(database, booking, step), timeout=45)
                succeeded = True
            except Exception as exc:
                failures.append((step, exc))
            progress = {'$set': {'agency_completion.lease_until': datetime.now(UTC) + timedelta(minutes=2)}}
            if succeeded:
                progress['$addToSet'] = {'agency_completion.done': step}
            result = await database.bookings.update_one(query, progress)
            if not result.matched_count:
                return True
        if failures:
            step, error = failures[0]
            raise error
        step = 'inventory_delivery'
        delivery = await database.outbox_events.find_one({'idempotency_key': stable_id(booking['id'], 'inventory')})
        if not delivery:
            raise RuntimeError('inventory_event_missing')
        # The agency sale is complete once Syroce PMS holds the booking, folio,
        # ledger, notification and audit records and the inventory event is
        # queued. Delivery to a third-party channel manager (Exely,
        # HotelRunner, ...) is the hotel's channel integration: its outcome is
        # recorded for operators but never holds the agency's reservation in
        # "waiting" or turns it into "failed".
        await database.bookings.update_one(query, {'$set': {
            'agency_completion.status': 'complete',
            'agency_completion.channel_delivery': delivery.get('status') or 'pending',
            'agency_completion.available_at': datetime.now(UTC) + timedelta(seconds=30),
            'agency_completion.last_error': None, 'agency_completion.updated_at': datetime.now(UTC),
        }, '$unset': {'agency_completion.owner': '', 'agency_completion.lease_until': ''}})
    except Exception as exc:
        attempts = int(state.get('attempts', 0)) + 1
        await database.bookings.update_one(query, {'$set': {
            'agency_completion.status': 'failed' if attempts >= 8 else 'retry',
            'agency_completion.attempts': attempts,
            'agency_completion.last_error': f'{step}:{type(exc).__name__}',
            'agency_completion.available_at': datetime.now(UTC) + timedelta(seconds=min(30 * 2**attempts, 3600)),
            'agency_completion.updated_at': datetime.now(UTC),
        }, '$unset': {'agency_completion.owner': '', 'agency_completion.lease_until': ''}})
    return True


class CompletionWorker:
    def __init__(self):
        self.task = None

    async def start(self):
        from core.tenant_db import get_system_db
        # Required for crash/replay safety: unlike the generic best-effort
        # index bootstrap, do not silently run without the dedup constraint.
        await get_system_db().outbox_events.create_index(
            [('idempotency_key', 1)], name='idx_outbox_idempotency', unique=True,
            partialFilterExpression={'idempotency_key': {'$type': 'string'}})
        await get_system_db().bookings.create_index([('agency_completion.status', 1), ('agency_completion.available_at', 1)])
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run(), name='agency-booking-completion')

    async def run(self):
        from core.tenant_db import get_system_db
        while True:
            try:
                worked = await process_one(get_system_db())
                await asyncio.sleep(0.1 if worked else 5)
            except Exception:
                logger.error('Agency completion worker unavailable; persisted queue retained')
                await asyncio.sleep(5)

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None


worker = CompletionWorker()
