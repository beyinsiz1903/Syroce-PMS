import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2
from common.context import OperationContext
from datetime import datetime, UTC

def create_db_mock():
    db_mock = MagicMock()
    
    # Mock bookings
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
    db_mock.bookings.find_one = AsyncMock(return_value=booking)
    db_mock.bookings.update_one = AsyncMock()
    
    # Mock folios
    folio_cursor = MagicMock()
    folio_cursor.to_list = AsyncMock(return_value=[])
    db_mock.folios.find.return_value = folio_cursor
    
    # Mock rooms and hk
    db_mock.rooms.update_one = AsyncMock()
    db_mock.housekeeping_tasks.insert_one = AsyncMock()
    
    # Mock keycards
    keycards_cursor = MagicMock()
    keycards_cursor.to_list = AsyncMock(return_value=[])
    db_mock.keycards.find.return_value = keycards_cursor
    
    return db_mock, booking

@pytest.mark.asyncio
async def test_rnl_release_on_checkout():
    db_mock, _ = create_db_mock()
    
    # Mock room night locks
    mock_delete_many = AsyncMock()
    mock_delete_many.return_value.deleted_count = 2
    db_mock.room_night_locks.delete_many = mock_delete_many
    
    service = FrontdeskServiceV2()
    service._db = db_mock
    service._acquire_lock = AsyncMock(return_value=True)
    service._release_lock = AsyncMock()
    
    ctx = OperationContext(tenant_id="t1", actor_id="user1", actor_role="admin")
    
    res = await service.checkout(ctx, "b1", force=True, reason="test")
    if not res.ok:
        assert False, f"Checkout failed: {res.error} - {getattr(res, 'data', {})}"
    assert res.ok is True
    
    # Verify RNL was called
    mock_delete_many.assert_called_once_with({"booking_id": "b1", "tenant_id": "t1"})
    db_mock.bookings.update_one.assert_called_once()
    assert db_mock.rooms.update_one.call_count == 1

@pytest.mark.asyncio
async def test_rnl_release_failure_prevents_checkout():
    db_mock, _ = create_db_mock()
    
    # Mock RNL failure
    mock_delete_many = AsyncMock(side_effect=Exception("DB Error"))
    db_mock.room_night_locks.delete_many = mock_delete_many
    
    service = FrontdeskServiceV2()
    service._db = db_mock
    service._acquire_lock = AsyncMock(return_value=True)
    service._release_lock = AsyncMock()
    
    ctx = OperationContext(tenant_id="t1", actor_id="user1", actor_role="admin")
    
    with pytest.raises(Exception, match="DB Error"):
        await service.checkout(ctx, "b1", force=True, reason="test")
        
    # Verify bookings.update_one was NOT called because RNL deletion failed first
    db_mock.bookings.update_one.assert_not_called()
