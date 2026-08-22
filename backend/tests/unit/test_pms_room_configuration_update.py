from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.schemas import User
from routers import pms_rooms


@pytest.fixture
def admin_user() -> User:
    return User(
        id="admin-1",
        tenant_id="tenant-1",
        email="admin@example.com",
        name="Admin",
        role="admin",
    )


@pytest.mark.asyncio
async def test_update_room_accepts_custom_type_capacity_view_price_and_twin_bed(admin_user):
    updated_room = {
        "id": "room-207",
        "tenant_id": "tenant-1",
        "room_number": "207",
        "room_type": "Ağaç Ev",
        "floor": 2,
        "capacity": 2,
        "base_price": 3250.5,
        "view": "Orman",
        "bed_type": "twin",
    }
    rooms = MagicMock()
    rooms.find_one = AsyncMock(side_effect=[None, updated_room])
    rooms.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    fake_db = SimpleNamespace(rooms=rooms)

    with (
        patch.object(pms_rooms, "db", fake_db),
        patch.object(pms_rooms, "_invalidate_room_list_caches") as invalidate,
    ):
        result = await pms_rooms.update_room(
            "room-207",
            {
                "room_number": " 207 ",
                "room_type": " Ağaç Ev ",
                "floor": "2",
                "capacity": "2",
                "base_price": 3250.5,
                "view": " Orman ",
                "bed_type": " twin ",
            },
            current_user=admin_user,
            _perm=None,
        )

    assert result == updated_room
    rooms.update_one.assert_awaited_once_with(
        {"id": "room-207", "tenant_id": "tenant-1"},
        {
            "$set": {
                "room_number": "207",
                "room_type": "Ağaç Ev",
                "floor": 2,
                "capacity": 2,
                "base_price": 3250.5,
                "view": "Orman",
                "bed_type": "twin",
            }
        },
    )
    invalidate.assert_called_once_with("tenant-1")


@pytest.mark.asyncio
async def test_update_room_rejects_capacity_below_one(admin_user):
    rooms = MagicMock()
    rooms.update_one = AsyncMock()

    with patch.object(pms_rooms, "db", SimpleNamespace(rooms=rooms)):
        with pytest.raises(HTTPException) as exc_info:
            await pms_rooms.update_room(
                "room-207",
                {"capacity": 0},
                current_user=admin_user,
                _perm=None,
            )

    assert exc_info.value.status_code == 422
    rooms.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_room_rejects_duplicate_number_within_tenant(admin_user):
    rooms = MagicMock()
    rooms.find_one = AsyncMock(return_value={"id": "another-room"})
    rooms.update_one = AsyncMock()

    with patch.object(pms_rooms, "db", SimpleNamespace(rooms=rooms)):
        with pytest.raises(HTTPException) as exc_info:
            await pms_rooms.update_room(
                "room-207",
                {"room_number": "208"},
                current_user=admin_user,
                _perm=None,
            )

    assert exc_info.value.status_code == 409
    rooms.update_one.assert_not_awaited()

