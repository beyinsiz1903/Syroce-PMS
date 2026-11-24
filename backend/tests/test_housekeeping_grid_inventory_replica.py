"""Active physical inventory and actual guest parity; disposable LOCAL Mongo."""
from types import SimpleNamespace

import pytest

from routers.hotel_services_pkg import housekeeping_settings as hk
from tests.test_pos_final_consistency_replica import db as db


@pytest.fixture
async def board(db, monkeypatch):
    monkeypatch.setattr(hk, 'db', db)
    monkeypatch.setattr(hk, '_ensure_hotel_context', lambda *_: None)
    await db.rooms.insert_many([
        {'id': 'occupied', 'tenant_id': 't', 'room_number': '101', 'housekeeping_status': 'clean', 'current_booking_id': 'current'},
        {'id': 'vacant', 'tenant_id': 't', 'room_number': '102', 'hk_status': 'dirty'},
        {'id': 'virtual', 'tenant_id': 't', 'room_number': 'V-STD', 'is_virtual': True, 'housekeeping_status': 'clean'},
        {'id': 'inactive', 'tenant_id': 't', 'room_number': 'TST814', 'is_active': False, 'housekeeping_status': 'clean'},
        {'id': 'foreign', 'tenant_id': 'other', 'room_number': '103', 'housekeeping_status': 'clean'},
    ])
    await db.bookings.insert_many([
        {'id': 'future', 'tenant_id': 't', 'room_id': 'occupied', 'status': 'confirmed', 'guest_name': 'Gelecek Misafir'},
        {'id': 'current', 'tenant_id': 't', 'room_id': 'occupied', 'status': 'checked_in', 'guest_name': 'İçerideki Misafir'},
        {'id': 'future2', 'tenant_id': 't', 'room_id': 'vacant', 'status': 'confirmed', 'guest_name': 'Gelecek Misafir 2'},
    ])
    return SimpleNamespace(tenant_id='t')


@pytest.mark.asyncio
async def test_room_grid_excludes_virtual_inactive_foreign_and_future_guests(db, board):
    result = await hk.get_housekeeping_rooms(current_user=board)
    assert result['total'] == 2
    assert [room['id'] for room in result['rooms']] == ['occupied', 'vacant']
    assert result['summary'] == {'clean': 1, 'dirty': 1}
    assert result['rooms'][0]['current_booking']['guest_name'] == 'İçerideki Misafir'
    assert result['rooms'][1]['current_booking'] is None


@pytest.mark.asyncio
async def test_status_filter_preserves_full_inventory_summary(db, board):
    result = await hk.get_housekeeping_rooms(status_filter='dirty', current_user=board)
    assert [room['id'] for room in result['rooms']] == ['vacant']
    assert result['summary'] == {'clean': 1, 'dirty': 1}
    assert result['total'] == 1
    assert result['inventory_total'] == 2


@pytest.mark.asyncio
async def test_multiple_inhouse_candidates_do_not_pick_an_arbitrary_guest(db, board):
    await db.bookings.insert_many([
        {'id': 'one', 'tenant_id': 't', 'room_id': 'vacant', 'status': 'checked_in', 'guest_name': 'Bir'},
        {'id': 'two', 'tenant_id': 't', 'room_id': 'vacant', 'status': 'in_house', 'guest_name': 'İki'},
    ])
    result = await hk.get_housekeeping_rooms(current_user=board)
    vacant = next(room for room in result['rooms'] if room['id'] == 'vacant')
    assert vacant['current_booking'] is None
    assert vacant['booking_conflict'] is True


@pytest.mark.asyncio
async def test_known_owner_wins_over_stale_inhouse_record(db, board):
    await db.bookings.insert_one({'id': 'stale', 'tenant_id': 't', 'room_id': 'occupied', 'status': 'checked_in', 'guest_name': 'Eski Misafir'})
    result = await hk.get_housekeeping_rooms(current_user=board)
    room = next(room for room in result['rooms'] if room['id'] == 'occupied')
    assert room['current_booking']['id'] == 'current'
    assert room['booking_conflict'] is False


@pytest.mark.asyncio
async def test_stale_owner_does_not_attach_another_guest_or_change_room(db, board):
    await db.rooms.update_one({'id': 'occupied'}, {'$set': {'current_booking_id': 'missing'}})
    before = await db.rooms.find_one({'id': 'occupied'})
    result = await hk.get_housekeeping_rooms(current_user=board)
    room = next(room for room in result['rooms'] if room['id'] == 'occupied')
    assert room['current_booking'] is None and room['booking_conflict'] is True
    assert await db.rooms.find_one({'id': 'occupied'}) == before
