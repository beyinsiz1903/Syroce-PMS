"""Automatic Exely stock must not reopen a deliberately smaller sales allotment.

All databases and provider queues are fakes; these tests cannot publish stock.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domains.channel_manager import availability_auto_sync as auto
from domains.channel_manager import unified_rate_manager_router as grid
from domains.channel_manager.calendar_inventory import exely_publishable_availability

pytestmark = pytest.mark.exely_failure_stress


def collection(rows):
    def find(query, projection):
        def matches(row):
            for key, expected in query.items():
                actual = row.get(key)
                if not isinstance(expected, dict):
                    if actual != expected:
                        return False
                    continue
                for op, value in expected.items():
                    if op == '$ne' and actual == value:
                        return False
                    if op == '$in' and actual not in value:
                        return False
                    if op == '$lt' and not actual < value:
                        return False
                    if op == '$gt' and not actual > value:
                        return False
                    if op == '$gte' and not actual >= value:
                        return False
                    if op == '$lte' and not actual <= value:
                        return False
            return True

        include = any(value for key, value in projection.items() if key != '_id')
        result = [{key: value for key, value in row.items()
                   if (projection.get(key) if include else projection.get(key, 1))}
                  for row in rows if matches(row)]
        return SimpleNamespace(to_list=AsyncMock(return_value=result))
    return SimpleNamespace(find=MagicMock(side_effect=find))


def database(calendar, bookings=(), mappings=None):
    owner = {
        'tenant_id': 'test', 'pms_room_type': 'Standard',
        'exely_room_code': 'panel-std', 'exely_rate_plan_code': 'panel-bar',
        'pms_api_room_code': 'wire-std', 'pms_api_rate_plan_code': 'wire-bar',
        'sync_availability': True,
    }
    return SimpleNamespace(
        exely_connections=SimpleNamespace(find_one=AsyncMock(return_value={'hotel_code': 'test-property'})),
        exely_room_mappings=collection(mappings if mappings is not None else [owner]),
        rate_calendar=collection(calendar), bookings=collection(bookings),
        rooms=collection([
            *[{'id': f'std-{i}', 'tenant_id': 'test', 'room_type': 'Standard'} for i in range(8)],
            {'id': 'deluxe-1', 'tenant_id': 'test', 'room_type': 'Deluxe'},
            {'id': 'lowercase', 'tenant_id': 'test', 'room_type': 'standard'},
            {'id': 'holder', 'tenant_id': 'test', 'room_type': 'Standard', 'is_virtual': True},
            {'id': 'inactive', 'tenant_id': 'test', 'room_type': 'Standard', 'is_active': False},
            {'id': 'foreign', 'tenant_id': 'other', 'room_type': 'Standard'},
        ]),
    )


def calendar_row(day='2026-11-10', value=5, **overrides):
    return {'tenant_id': 'test', 'room_type_code': 'panel-std',
            'rate_plan_code': 'panel-bar', 'date': day, 'availability': value, **overrides}


def booking(**overrides):
    return {'tenant_id': 'test', 'room_id': 'std-0', 'room_type': 'Standard',
            'status': 'confirmed', 'check_in': '2026-11-10', 'check_out': '2026-11-11', **overrides}


@pytest.fixture
def enqueue(monkeypatch):
    queue = AsyncMock(return_value={'accepted': True})
    monkeypatch.setattr('domains.channel_manager.providers.exely.ari_publish.enqueue_exely_ari_update', queue)
    return queue


@pytest.mark.asyncio
@pytest.mark.parametrize('cap,bookings,canonical,expected', [
    (5, [], 8, 5),
    (5, [booking()], 7, 4),
    (5, [booking(status='cancelled')], 8, 5),
    (5, [booking(room_id=None)], 8, 4),
    (5, [], 0, 0),
    (0, [], 8, 0),
    (None, [booking()], 6, 6),
    (5, [booking(room_id='lowercase', room_type='standard')], 8, 5),
    (5, [booking(room_id='deluxe-1')], 8, 5),
    (None, [], 8, 8),
    (10, [booking()], 7, 7),
    (0, [booking()], 7, 0),
    (1, [booking(), booking(room_id='std-1')], 6, 0),
])
async def test_automatic_value_respects_commercial_and_physical_limits(monkeypatch, enqueue, cap, bookings, canonical, expected):
    fake = database([] if cap is None else [calendar_row(value=cap)], bookings)
    monkeypatch.setattr(auto, 'db', fake)
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': canonical})
    assert result == {'configured': True, 'queued_operations': 1, 'errors': []}
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs['availability'] == expected
    assert enqueue.await_args.kwargs['room_type_code'] == 'wire-std'
    assert enqueue.await_args.kwargs['rate_plan_code'] == 'wire-bar'


@pytest.mark.asyncio
async def test_day_specific_caps_group_only_equal_results_and_ignore_alias_other_tenant_and_plan(monkeypatch, enqueue):
    fake = database([
        calendar_row(value=5), calendar_row('2026-11-11', 7), calendar_row('2026-11-12', 8),
        calendar_row(value=1, tenant_id='other'),
        calendar_row(value=0, rate_plan_code='non-owner'),
        calendar_row(value=0, room_type_code='wire-std'),
    ])
    monkeypatch.setattr(auto, 'db', fake)
    result = await auto._push_to_exely('test', 'Standard', {
        '2026-11-10': 8, '2026-11-11': 8, '2026-11-12': 8,
    })
    assert result['errors'] == [] and result['queued_operations'] == 3
    assert [(c.kwargs['start_date'], c.kwargs['end_date'], c.kwargs['availability'])
            for c in enqueue.await_args_list] == [
                ('2026-11-10', '2026-11-10', 5), ('2026-11-11', '2026-11-11', 7),
                ('2026-11-12', '2026-11-12', 8),
            ]


@pytest.mark.asyncio
async def test_create_cancel_cycle_restores_allotment_not_physical_capacity(monkeypatch, enqueue):
    for bookings, canonical, expected in [([], 8, 5), ([booking()], 7, 4), ([booking(status='cancelled')], 8, 5)]:
        monkeypatch.setattr(auto, 'db', database([calendar_row()], bookings))
        result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': canonical})
        assert not result['errors']
        assert enqueue.await_args.kwargs['availability'] == expected
    assert enqueue.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_cap', [-1, True, 1.5, '5'])
async def test_invalid_cap_stops_before_any_day_is_queued(monkeypatch, enqueue, bad_cap):
    monkeypatch.setattr(auto, 'db', database([calendar_row(), calendar_row('2026-11-11', bad_cap)]))
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8, '2026-11-11': 8})
    assert result['queued_operations'] == 0 and result['errors']
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_owner_calendar_row_is_not_arbitrarily_selected(monkeypatch, enqueue):
    monkeypatch.setattr(auto, 'db', database([calendar_row(value=5), calendar_row(value=8)]))
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8})
    assert result['queued_operations'] == 0 and result['errors']
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_calendar_read_failure_does_not_fall_back_to_physical_stock(monkeypatch, enqueue):
    fake = database([])
    fake.rate_calendar.find.side_effect = TimeoutError('synthetic offline read failure')
    monkeypatch.setattr(auto, 'db', fake)
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8})
    assert result['queued_operations'] == 0 and result['errors'] == ['TimeoutError']
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_connection_or_no_owner_does_not_even_read_calendar(monkeypatch, enqueue):
    fake = database([])
    fake.exely_connections.find_one.return_value = None
    monkeypatch.setattr(auto, 'db', fake)
    assert not (await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8}))['configured']
    fake.exely_connections.find_one.return_value = {'hotel_code': 'test-property'}
    fake.exely_room_mappings = collection([])
    assert (await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8}))['errors'] == ['exely_room_mapping_missing']
    fake.rate_calendar.find.assert_not_called()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_cap_booking_is_subtracted_once_with_checkout_exclusive_and_final_night(monkeypatch, enqueue):
    fake = database([calendar_row(), calendar_row('2026-11-11')], [
        booking(check_in='2026-11-10T14:00:00', check_out='2026-11-11T12:00:00'),
        booking(room_id=None, check_in='2026-11-11T14:00:00', check_out='2026-11-12T12:00:00'),
        booking(tenant_id='other'), booking(status='archived_demo'), booking(status='no_show'),
        booking(room_id=None, room_type='unknown'),
    ])
    monkeypatch.setattr(auto, 'db', fake)
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': 7, '2026-11-11': 8})
    assert not result['errors'] and result['queued_operations'] == 1
    kwargs = enqueue.await_args.kwargs
    assert (kwargs['start_date'], kwargs['end_date'], kwargs['availability']) == ('2026-11-10', '2026-11-11', 4)
    assert fake.bookings.find.call_args.args[0] == {
        'tenant_id': 'test', 'status': {'$in': ['pending', 'confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lt': '2026-11-12'}, 'check_out': {'$gt': '2026-11-10'},
    }
    assert fake.rate_calendar.find.call_args.args[0] == {
        'tenant_id': 'test', 'room_type_code': 'panel-std', 'rate_plan_code': 'panel-bar',
        'date': {'$in': ['2026-11-10', '2026-11-11']},
    }


@pytest.mark.asyncio
async def test_sparse_dates_do_not_publish_untouched_night(monkeypatch, enqueue):
    fake = database([calendar_row(), calendar_row('2026-11-11'), calendar_row('2026-11-12')])
    monkeypatch.setattr(auto, 'db', fake)
    await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8, '2026-11-12': 8})
    assert [(c.kwargs['start_date'], c.kwargs['end_date']) for c in enqueue.await_args_list] == [
        ('2026-11-10', '2026-11-10'), ('2026-11-12', '2026-11-12')]


@pytest.mark.asyncio
async def test_shared_projection_matches_normal_grid_but_cannot_exceed_locks(monkeypatch):
    fake = database([calendar_row()], [booking(room_id=None)])
    fake.pricing_settings = collection([])
    monkeypatch.setattr(grid, 'db', fake)
    rendered = await grid._build_exely_grid('test', {'currency': 'USD'}, '2026-11-10', '2026-11-10')
    day = rendered['grid'][0]['dates'][0]
    assert (day['base_availability'], day['sold'], day['availability']) == (5, 1, 4)
    owner = (await fake.exely_room_mappings.find({'tenant_id': 'test'}, {'_id': 0}).to_list(10))[0]
    assert await exely_publishable_availability(fake, 'test', 'Standard', owner, {'2026-11-10': 8}) == {'2026-11-10': 4}
    assert await exely_publishable_availability(fake, 'test', 'Standard', owner, {'2026-11-10': 2}) == {'2026-11-10': 2}


@pytest.mark.asyncio
@pytest.mark.parametrize('canonical', [-1, True, 1.5, '8'])
async def test_invalid_physical_source_is_not_coerced(canonical):
    fake = database([])
    with pytest.raises(ValueError, match='Invalid canonical'):
        await exely_publishable_availability(fake, 'test', 'Standard', {}, {'2026-11-10': canonical})
    fake.rooms.find.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('limited_source', ['rooms', 'bookings'])
async def test_truncated_projection_never_publishes(monkeypatch, enqueue, limited_source):
    fake = database([calendar_row()])
    rows = ([{'id': f'room-{i}', 'room_type': 'Standard'} for i in range(500)]
            if limited_source == 'rooms' else [booking()] * 10000)
    getattr(fake, limited_source).find = MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    monkeypatch.setattr(auto, 'db', fake)
    result = await auto._push_to_exely('test', 'Standard', {'2026-11-10': 8})
    assert result['queued_operations'] == 0 and result['errors']
    enqueue.assert_not_awaited()
