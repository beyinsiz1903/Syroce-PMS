import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import agency_completion as queue
from routers import marketplace_b2b as api


class Bookings:
    def __init__(self, row):
        self.row = row

    async def find_one_and_update(self, query, update, **kwargs):
        state = self.row['agency_completion']
        now = datetime.now(UTC)
        assert query['$or'][1]['agency_completion.status'] == 'processing'
        eligible = (state['status'] in ['pending', 'retry', 'waiting'] and state['available_at'] <= now) or (state['status'] == 'processing' and state['lease_until'] < now)
        if not eligible:
            return None
        self.apply(update)
        return deepcopy(self.row)

    def apply(self, update):
        state = self.row['agency_completion']
        for key, value in update.get('$set', {}).items():
            state[key.split('.')[-1]] = value
        for key in update.get('$unset', {}):
            state.pop(key.split('.')[-1], None)
        for key, value in update.get('$addToSet', {}).items():
            if value not in state['done']:
                state['done'].append(value)

    async def update_one(self, query, update):
        assert query['tenant_id'] == 'hotel'
        if query.get('agency_completion.owner') != self.row['agency_completion'].get('owner'):
            return SimpleNamespace(matched_count=0)
        self.apply(update)
        return SimpleNamespace(matched_count=1)


def database():
    row = {'id': 'booking', 'tenant_id': 'hotel', 'agency_id': 'agency',
           'agency_completion': queue.pending_completion('marketplace')}
    return SimpleNamespace(bookings=Bookings(row), outbox_events=SimpleNamespace(find_one=AsyncMock(return_value={'status': 'processed'})))


@pytest.mark.asyncio
async def test_concurrent_workers_claim_once_and_finish(monkeypatch):
    db = database()
    perform = AsyncMock()
    monkeypatch.setattr(queue, 'perform_step', perform)
    assert sorted(await asyncio.gather(queue.process_one(db), queue.process_one(db))) == [False, True]
    assert db.bookings.row['agency_completion']['status'] == 'complete'
    assert perform.await_count == 7


@pytest.mark.asyncio
async def test_failure_resumes_missing_steps_and_redacts_error(monkeypatch):
    db = database()
    performed = []
    async def perform(database, booking, step):
        performed.append(step)
        if step == 'folio':
            raise RuntimeError('secret token must never reach admin')
    monkeypatch.setattr(queue, 'perform_step', perform)
    await queue.process_one(db)
    state = db.bookings.row['agency_completion']
    assert 'ledger' in state['done'] and 'inventory' in state['done'] and 'folio' not in state['done']
    assert state['status'] == 'retry'
    assert state['last_error'] == 'folio:RuntimeError'
    state['available_at'] = datetime.now(UTC) - timedelta(seconds=1)
    success = AsyncMock()
    monkeypatch.setattr(queue, 'perform_step', success)
    await queue.process_one(db)
    assert state['status'] == 'complete'
    assert 'ledger' not in [call.args[2] for call in success.await_args_list]
    assert success.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('channel_status', ['retry', 'failed', 'processed'])
async def test_channel_manager_outcome_never_blocks_the_agency_sale(monkeypatch, channel_status):
    db = database()
    state = db.bookings.row['agency_completion']
    state.update(status='processing', owner='dead-worker', lease_until=datetime.now(UTC) - timedelta(seconds=1))
    monkeypatch.setattr(queue, 'perform_step', AsyncMock())
    db.outbox_events.find_one.return_value = {'status': channel_status}
    await queue.process_one(db)
    assert state['status'] == 'complete'
    assert state['channel_delivery'] == channel_status


@pytest.mark.asyncio
async def test_missing_inventory_event_is_still_repaired(monkeypatch):
    db = database()
    monkeypatch.setattr(queue, 'perform_step', AsyncMock())
    db.outbox_events.find_one.return_value = None
    await queue.process_one(db)
    state = db.bookings.row['agency_completion']
    assert state['status'] == 'retry' and state['last_error'].startswith('inventory_delivery:')


@pytest.mark.asyncio
async def test_local_writes_have_stable_upsert_identity():
    collection = SimpleNamespace(update_one=AsyncMock())
    db = SimpleNamespace(folios=collection, marketplace_bookings=collection, notifications=collection, pms_audit_trail=collection)
    row = {'id': 'booking', 'tenant_id': 'hotel', 'agency_id': 'agency', 'guest_id': 'guest',
           'check_in': '2027-01-01', 'check_out': '2027-01-02', 'total_amount': 100, 'currency': 'EUR'}
    for step in ['folio', 'ledger', 'notification', 'audit']:
        await queue.perform_step(db, row, step)
        await queue.perform_step(db, row, step)
        calls = collection.update_one.await_args_list[-2:]
        assert calls[0].args[0] == calls[1].args[0] == {'_id': queue.stable_id('booking', step)}
        assert calls[0].kwargs['upsert'] and '$setOnInsert' in calls[0].args[1]


def test_public_summary_never_exposes_internal_state_or_credentials():
    result = queue.public_booking({'id': 'b', 'agency_request_hash': 'secret', 'guest_phone': 'private',
                                   'agency_completion': {'status': 'retry', 'owner': 'secret'}})
    assert result['integration_status'] == 'retry'
    assert 'agency_completion' not in result and 'agency_request_hash' not in result and 'guest_phone' not in result


@pytest.mark.asyncio
async def test_admin_retry_cannot_steal_processing_work(monkeypatch):
    db = SimpleNamespace(bookings=SimpleNamespace(find_one=AsyncMock(return_value=None)), outbox_events=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(api, 'get_system_db', lambda: db)
    with pytest.raises(HTTPException) as error:
        await api.admin_retry_integration('b', True)
    assert error.value.status_code == 409
    db.outbox_events.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_retry_requeues_failed_delivery_without_new_booking(monkeypatch):
    db = SimpleNamespace(bookings=SimpleNamespace(find_one=AsyncMock(return_value={'id': 'b', 'tenant_id': 't'}),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))), outbox_events=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(api, 'get_system_db', lambda: db)
    result = await api.admin_retry_integration('b', True)
    assert result['integration_status'] == 'pending'
    assert db.outbox_events.update_one.call_args.args[0]['status'] == 'failed'
    assert db.outbox_events.update_one.call_args.args[0]['tenant_id'] == 't'


def test_admin_endpoints_require_superadmin():
    routes = [route for route in api.router.routes if '/admin/integrations' in route.path]
    assert len(routes) == 2
    for route in routes:
        assert api._require_system_admin in [dep.call for dep in route.dependant.dependencies]


@pytest.mark.asyncio
async def test_booking_visible_to_own_agency_before_ledger_exists(monkeypatch):
    row = {'id': 'b', 'agency_id': 'a', 'tenant_id': 't', 'created_at': '2027-01-01',
           'agency_completion': queue.pending_completion('marketplace'), 'agency_request_hash': 'private'}
    captured = []
    class Cursor:
        def __init__(self, rows): self.rows = rows
        def sort(self, *args): return self
        def limit(self, *args): return self
        async def to_list(self, *args): return self.rows
    def canonical(query, projection):
        captured.append(query)
        return Cursor([row] if query['agency_id'] == 'a' else [])
    db = SimpleNamespace(marketplace_bookings=SimpleNamespace(find=lambda *args: Cursor([])),
                         bookings=SimpleNamespace(find=canonical))
    monkeypatch.setattr(api, 'get_system_db', lambda: db)
    own = await api.agency_list_reservations(None, None, None, None, 100, {'agency_id': 'a'})
    other = await api.agency_list_reservations(None, None, None, None, 100, {'agency_id': 'other'})
    assert own['reservations'][0]['integration_status'] == 'pending'
    assert 'agency_request_hash' not in own['reservations'][0]
    assert other['reservations'] == []
    assert captured[0]['agency_completion.kind'] == 'marketplace'


@pytest.mark.asyncio
async def test_successful_webhook_not_resent_after_crash(monkeypatch):
    from core import tenant_db
    from routers import webhook_retry_service
    collection = SimpleNamespace(find_one=AsyncMock(return_value={'status': 'succeeded'}))
    monkeypatch.setattr(tenant_db, 'get_system_db', lambda: SimpleNamespace(webhook_deliveries=collection))
    result = await webhook_retry_service.deliver_webhook_with_retry({}, 'reservation.created', {}, delivery_id='stable')
    assert result['status'] == 'succeeded'
    collection.find_one.assert_awaited_once_with({'id': 'stable'})
