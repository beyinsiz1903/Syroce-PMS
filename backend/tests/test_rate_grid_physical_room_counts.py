"""A channel calendar must never add virtual or inactive rooms to capacity."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domains.channel_manager import hr_rate_manager_router as hr
from domains.channel_manager import rate_manager_router as exely
from domains.channel_manager import unified_rate_manager_router as unified


def collection(rows):
    def find(query, projection):
        def matches(row):
            for key, value in query.items():
                actual = row.get(key)
                if isinstance(value, dict) and '$ne' in value:
                    if actual == value['$ne']:
                        return False
                elif actual != value:
                    return False
            return True

        inclusion = any(value for key, value in projection.items() if key != '_id')
        projected = [
            {key: value for key, value in row.items()
             if (projection.get(key) if inclusion else projection.get(key, 1))}
            for row in rows if matches(row)
        ]
        return SimpleNamespace(to_list=AsyncMock(return_value=projected))

    return SimpleNamespace(find=MagicMock(side_effect=find))


@pytest.fixture
def room_collection():
    return collection([
        {'id': 'physical-legacy', 'tenant_id': 'test', 'room_type': 'Standard', 'status': 'available'},
        {'id': 'physical-active', 'tenant_id': 'test', 'room_type': 'Standard', 'status': 'occupied',
         'is_active': True, 'is_virtual': False},
        {'id': 'virtual', 'tenant_id': 'test', 'room_type': 'Standard', 'status': 'available', 'is_virtual': True},
        {'id': 'inactive', 'tenant_id': 'test', 'room_type': 'Standard', 'status': 'available', 'is_active': False},
        {'id': 'foreign', 'tenant_id': 'other', 'room_type': 'Standard', 'status': 'available'},
    ])


@pytest.mark.asyncio
async def test_unified_capacity_and_room_ids_only_include_active_physical_rooms(monkeypatch, room_collection):
    monkeypatch.setattr(unified, 'db', SimpleNamespace(rooms=room_collection))
    counts, ids = await unified._get_room_counts('test')
    assert counts == {'Standard': {'total': 2, 'available': 1}}
    assert ids == {'Standard': ['physical-legacy', 'physical-active']}
    assert room_collection.find.call_args.args[0] == {
        'tenant_id': 'test', 'is_active': {'$ne': False}, 'is_virtual': {'$ne': True},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['exely', 'hotelrunner'])
@pytest.mark.parametrize('saved_allotment', [False, True])
async def test_legacy_grids_use_the_same_sellable_physical_capacity(monkeypatch, room_collection, provider, saved_allotment):
    room = {'code': 'STD', 'name': 'Standard'}
    plan = {'code': 'BAR', 'name': 'Base'}
    mapping = {'exely_room_code': 'STD', 'hr_inv_code': 'STD', 'pms_room_type': 'Standard'}
    conn = {'room_types': [room], 'rate_plans': [plan], 'currency': 'USD',
            'cached_rooms': [{'inv_code': 'STD', 'name': 'Standard', 'rate_plan_id': 'BAR',
                              'rate_plan_name': 'Base', 'sales_currency': 'USD'}]}
    calendar = [{'tenant_id': 'test', 'room_type_code': 'STD', 'rate_plan_code': 'BAR',
                 'date': '2026-11-10', 'availability': 1}] if saved_allotment else []
    calendar_collection = collection(calendar)
    # Date filtering is irrelevant to the fixture's already in-range rows.
    calendar_collection.find = MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=calendar)))
    fake_db = SimpleNamespace(
        rooms=room_collection, bookings=collection([]),
        exely_room_mappings=collection([{'tenant_id': 'test', **mapping}]),
        hotelrunner_room_mappings=collection([{'tenant_id': 'test', **mapping}]),
        exely_connections=SimpleNamespace(find_one=AsyncMock(return_value=conn)),
        hotelrunner_connections=SimpleNamespace(find_one=AsyncMock(return_value=conn)),
        rate_calendar=calendar_collection, hr_rate_calendar=calendar_collection,
        pricing_settings=collection([]), hr_pricing_settings=collection([]),
    )
    module = exely if provider == 'exely' else hr
    monkeypatch.setattr(module, 'db', fake_db)
    method = module.get_rate_grid if provider == 'exely' else module.get_hr_rate_grid
    result = await method('2026-11-10', '2026-11-11', SimpleNamespace(tenant_id='test'))
    assert len(result['grid']) == 1
    row = result['grid'][0]
    assert row['total_rooms'] == 2
    assert [d['availability'] for d in row['dates']] == ([1, 2] if saved_allotment else [2, 2])
    assert room_collection.find.call_args.args[0] == {
        'tenant_id': 'test', 'is_active': {'$ne': False}, 'is_virtual': {'$ne': True},
    }


@pytest.mark.asyncio
async def test_virtual_only_category_does_not_create_sellable_capacity(monkeypatch):
    rooms = collection([{'id': 'holder-only', 'tenant_id': 'test', 'room_type': 'Holder',
                         'status': 'available', 'is_virtual': True}])
    monkeypatch.setattr(unified, 'db', SimpleNamespace(rooms=rooms))
    assert await unified._get_room_counts('test') == ({}, {})
