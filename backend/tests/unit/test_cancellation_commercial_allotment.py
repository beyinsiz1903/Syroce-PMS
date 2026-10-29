"""Cancellation releases occupancy, never rewrites a saved sales ceiling.

Only in-memory collections and mocked lock/outbox functions; no live provider
or MongoDB connection is used. Exercise the same state machine as the UI.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from domains.channel_manager.calendar_inventory import exely_publishable_availability
from modules.pms_core import reservation_state_machine as state

pytestmark = pytest.mark.exely_failure_stress


def matches(row, query):
    for key, wanted in query.items():
        actual = row.get(key)
        if not isinstance(wanted, dict):
            if actual != wanted:
                return False
            continue
        for op, value in wanted.items():
            if op == '$exists':
                ok = (key in row) == value
            elif op == '$ne':
                ok = actual != value
            elif op == '$in':
                ok = actual in value
            elif op == '$lt':
                ok = actual < value
            elif op == '$gt':
                ok = actual > value
            elif op == '$gte':
                ok = actual >= value
            else:
                raise AssertionError(f'Unsupported isolated query operator: {op}')
            if not ok:
                return False
    return True


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.update_one = AsyncMock(side_effect=self._update)
        self.update_many = AsyncMock(side_effect=self._update)
        self.insert_one = AsyncMock()

    def find(self, query, _projection):
        rows = [deepcopy(row) for row in self.rows if matches(row, query)]
        return SimpleNamespace(to_list=AsyncMock(return_value=rows))

    async def find_one(self, query, _projection):
        return next((deepcopy(row) for row in self.rows if matches(row, query)), None)

    async def _update(self, query, change):
        for row in self.rows:
            if matches(row, query):
                row.update(change.get('$set', {}))
                for key, amount in change.get('$inc', {}).items():
                    row[key] = row.get(key, 0) + amount


@pytest.fixture
def scenario(monkeypatch):
    def make(cap, booking_status='confirmed', assigned=True):
        owner = {'tenant_id': 'demo-test', 'pms_room_type': 'Standard',
                 'exely_room_code': 'panel-std', 'exely_rate_plan_code': 'base',
                 'sync_availability': True}
        calendar = [
            {'tenant_id': 'demo-test', 'room_type_code': 'panel-std',
             'rate_plan_code': plan, 'date': day, 'availability': amount, 'rate': 100,
             'stop_sell': False, 'min_los': 1}
            for plan, amount in [('base', cap), ('other-plan', 0)]
            for day in ('2026-11-09', '2026-11-10', '2026-11-11')
        ]
        calendar.append({**calendar[1], 'tenant_id': 'foreign-test'})
        booking = {'tenant_id': 'demo-test', 'id': 'synthetic-booking',
                   'room_id': 'std-0' if assigned else None, 'room_type': 'Standard',
                   'guest_name': 'Synthetic QA', 'room_number': '101' if assigned else '',
                   'status': booking_status, 'check_in': '2026-11-10T14:00:00+03:00',
                   'check_out': '2026-11-11T12:00:00+03:00', 'correlation_id': 'qa-cancel',
                   'total_amount': 100, 'currency': 'USD', 'paid_amount': 0}
        fake = SimpleNamespace(
            rooms=Collection([{'id': f'std-{i}', 'tenant_id': 'demo-test',
                              'room_type': 'Standard', 'room_number': str(101 + i),
                              'status': 'clean'} for i in range(8)]),
            bookings=Collection(), exely_room_mappings=Collection([owner]),
            rate_calendar=Collection(calendar), notifications=Collection(),
            pms_audit_trail=Collection(), guests=Collection(),
        )
        monkeypatch.setattr(state, 'db', fake)
        release = AsyncMock()
        enqueue = AsyncMock()
        monkeypatch.setattr('core.atomic_booking.release_booking_nights', release)
        monkeypatch.setattr('core.outbox_service.enqueue_outbox_event', enqueue)
        return fake, booking, owner, release, enqueue
    return make


async def published(fake, owner, physical):
    return (await exely_publishable_availability(fake, 'demo-test', 'Standard', owner,
                                               {'2026-11-10': physical}))['2026-11-10']


@pytest.mark.asyncio
@pytest.mark.parametrize('cap', [0, 5, 8])
@pytest.mark.parametrize('booking_status', ['pending', 'confirmed', 'guaranteed'])
async def test_ui_cancel_returns_to_original_allotment_without_editing_any_calendar(scenario, cap, booking_status):
    fake, booking, owner, release, enqueue = scenario(cap, booking_status)
    original_calendar = deepcopy(fake.rate_calendar.rows)
    assert await published(fake, owner, 8) == cap
    fake.bookings.rows.append(deepcopy(booking))
    assert await published(fake, owner, 7) == max(cap - 1, 0)

    result = await state.ReservationStateMachine().handle_cancellation(
        'demo-test', booking, 'operator-test', 'Synthetic approved ARI test cleanup')

    restored = await published(fake, owner, 8)
    assert restored == cap, f'Saved ceiling {cap} must be restored, not raised to {restored}'
    assert fake.rate_calendar.rows == original_calendar
    fake.rate_calendar.update_many.assert_not_awaited()
    assert result['success'] and fake.bookings.rows[0]['status'] == 'cancelled'
    assert fake.bookings.rows[0]['total_amount'] == 100 and fake.bookings.rows[0]['paid_amount'] == 0
    release.assert_awaited_once_with('demo-test', 'synthetic-booking',
        reason='cancelled:Synthetic approved ARI test cleanup', correlation_id='qa-cancel')
    fake.notifications.insert_one.assert_awaited_once()
    fake.pms_audit_trail.insert_one.assert_awaited_once()
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_stale_cancel_calls_cannot_increment_the_sales_ceiling(scenario):
    fake, booking, owner, _release, _enqueue = scenario(5)
    fake.bookings.rows.append(deepcopy(booking))
    original = deepcopy(fake.rate_calendar.rows)
    machine = state.ReservationStateMachine()
    # This is not a claim of end-to-end cancellation idempotency. Even a stale
    # caller must not mutate the commercial ceiling or unrelated rate plans.
    for _ in range(2):
        await machine.handle_cancellation('demo-test', booking, 'operator-test', 'Synthetic QA')
    assert await published(fake, owner, 8) == 5
    assert fake.rate_calendar.rows == original


@pytest.mark.asyncio
async def test_unassigned_cancellation_still_releases_locks_and_keeps_the_ceiling(scenario):
    fake, booking, owner, release, enqueue = scenario(5, assigned=False)
    fake.bookings.rows.append(deepcopy(booking))
    assert await published(fake, owner, 8) == 4
    await state.ReservationStateMachine().handle_cancellation('demo-test', booking, 'operator-test')
    assert await published(fake, owner, 8) == 5
    fake.rate_calendar.update_many.assert_not_awaited()
    release.assert_awaited_once()
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('booking_status', ['pending', 'confirmed', 'guaranteed'])
async def test_normal_ui_cancel_http_route_keeps_cap_and_requests_auto_sync(scenario, monkeypatch, booking_status):
    import asyncio

    from core.security import get_current_user
    from routers import pms_hardening as api

    fake, booking, owner, release, enqueue = scenario(5, booking_status)
    fake.bookings.rows.append(deepcopy(booking))
    original = deepcopy(fake.rate_calendar.rows)
    monkeypatch.setattr(api, 'db', fake)
    monkeypatch.setattr(api, 'rsm', state.ReservationStateMachine())
    enforce = MagicMock()
    monkeypatch.setattr(api, 'perm_svc', SimpleNamespace(enforce_user_permission=enforce))
    notify = AsyncMock()
    sync = AsyncMock()
    monkeypatch.setattr('core.agency_notify.on_pms_status_change', notify)
    monkeypatch.setattr('domains.channel_manager.availability_auto_sync.sync_availability_after_booking', sync)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        tenant_id='demo-test', id='operator-test', name='Synthetic Operator')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated.test') as client:
        response = await client.post('/api/pms-core/cancel',
            json={'booking_id': 'synthetic-booking', 'reason': 'Synthetic approved ARI test cleanup'})
    await asyncio.sleep(0)  # Let the route's mocked automatic-sync task finish.
    assert response.status_code == 200 and response.json()['success'] is True
    assert fake.rate_calendar.rows == original
    assert await published(fake, owner, 8) == 5
    enforce.assert_called_once()
    assert enforce.call_args.args[1] == 'cancel_booking'
    sync.assert_awaited_once_with(tenant_id='demo-test', room_id='std-0',
        check_in=booking['check_in'], check_out=booking['check_out'])
    release.assert_awaited_once()
    enqueue.assert_awaited_once()
    notify.assert_awaited_once()
