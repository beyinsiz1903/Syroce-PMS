import pytest
import os
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2
from common.context import OperationContext
from core.atomic_checkin_checkout import CheckOutError
from datetime import datetime, UTC

def create_db_mock():
    db_mock = MagicMock()
    
    booking = {
        "id": "b1",
        "tenant_id": "t1",
        "status": "checked_in",
        "room_id": "r1"
    }
    col_mock = MagicMock()
    col_mock.find_one = AsyncMock(return_value=booking)
    col_mock.insert_one = AsyncMock()
    db_mock.__getitem__.return_value = col_mock
    
    # Defaults
    db_mock.bookings.find_one = AsyncMock(return_value=booking)
    booking_update_res = MagicMock()
    booking_update_res.matched_count = 1
    db_mock.bookings.update_one = AsyncMock(return_value=booking_update_res)
    
    room_update_res = MagicMock()
    room_update_res.matched_count = 1
    db_mock.rooms.update_one = AsyncMock(return_value=room_update_res)
    
    folio_cursor = MagicMock()
    folio_cursor.to_list = AsyncMock(return_value=[])
    db_mock.folios.find.return_value = folio_cursor
    
    keycards_cursor = MagicMock()
    keycards_cursor.to_list = AsyncMock(return_value=[])
    db_mock.keycards.find.return_value = keycards_cursor
    
    db_mock.housekeeping_tasks.insert_one = AsyncMock()
    db_mock.housekeeping_tasks.find_one = AsyncMock(return_value=None)
    
    mock_delete_many = AsyncMock()
    mock_delete_many.return_value.deleted_count = 2
    db_mock.room_night_locks.delete_many = mock_delete_many
    
    # Mock transaction wrapper
    session_mock = AsyncMock()
    async def mock_with_transaction(func, **kwargs):
        return await func(session_mock)
    session_mock.with_transaction = mock_with_transaction
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session_mock
    db_mock.client.start_session.return_value = session_context
    
    return db_mock, booking, session_mock

@pytest.fixture
def service_and_mocks():
    db_mock, booking, session_mock = create_db_mock()
    service = FrontdeskServiceV2()
    service._db = db_mock
    service._acquire_lock = AsyncMock(return_value=True)
    service._release_lock = AsyncMock()
    ctx = OperationContext(tenant_id="t1", actor_id="user1", actor_role="admin")
    
    with patch.dict(os.environ, {"MONGO_DISABLE_TRANSACTIONS": "1"}):
        yield service, db_mock, ctx, session_mock

@pytest.mark.asyncio
async def test_rnl_release_on_checkout(service_and_mocks):
    service, db_mock, ctx, session_mock = service_and_mocks
    
    res = await service.checkout(ctx, "b1", force=True, reason="test")
    assert res.ok is True
    
    db_mock.room_night_locks.delete_many.assert_called_once_with(
        {"booking_id": "b1", "tenant_id": "t1"}, session=None
    )
    db_mock.bookings.update_one.assert_called_once()
    assert db_mock.rooms.update_one.call_count == 1
    assert db_mock.housekeeping_tasks.insert_one.call_count == 1

@pytest.mark.asyncio
async def test_booking_update_matched_count_0(service_and_mocks):
    service, db_mock, ctx, session_mock = service_and_mocks
    
    booking_update_res = MagicMock()
    booking_update_res.matched_count = 0
    db_mock.bookings.update_one = AsyncMock(return_value=booking_update_res)
    
    with pytest.raises(CheckOutError, match="Booking disappeared"):
        await service.checkout(ctx, "b1", force=True, reason="test")

@pytest.mark.asyncio
async def test_room_update_matched_count_0(service_and_mocks):
    service, db_mock, ctx, session_mock = service_and_mocks
    
    room_update_res = MagicMock()
    room_update_res.matched_count = 0
    db_mock.rooms.update_one = AsyncMock(return_value=room_update_res)
    
    with pytest.raises(CheckOutError, match="Room disappeared"):
        await service.checkout(ctx, "b1", force=True, reason="test")

@pytest.mark.asyncio
async def test_hk_insert_exception(service_and_mocks):
    service, db_mock, ctx, session_mock = service_and_mocks
    
    db_mock.housekeeping_tasks.insert_one = AsyncMock(side_effect=Exception("DB Error"))
    
    with pytest.raises(Exception, match="DB Error"):
        await service.checkout(ctx, "b1", force=True, reason="test")

@pytest.mark.asyncio
async def test_second_checkout_deduplicates_hk(service_and_mocks):
    service, db_mock, ctx, session_mock = service_and_mocks
    
    # Simulate existing HK task
    db_mock.housekeeping_tasks.find_one = AsyncMock(return_value={"id": "existing-task-id"})
    
    res = await service.checkout(ctx, "b1", force=True, reason="test")
    assert res.ok is True
    
    # HK task insert should NOT be called
    db_mock.housekeeping_tasks.insert_one.assert_not_called()
    db_mock.housekeeping_tasks.find_one.assert_called_once_with(
        {
            "tenant_id": "t1",
            "booking_id": "b1",
            "task_type": "checkout_cleaning",
            "status": {"$nin": ["cancelled"]},
        },
        {"_id": 0, "id": 1},
        session=None
    )
