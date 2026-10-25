"""Room board must reconcile to physical inventory, never virtual folio rooms."""
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers import housekeeping


async def board(monkeypatch, rows):
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=rows))
    rooms = SimpleNamespace(find=Mock(return_value=cursor))
    monkeypatch.setattr(housekeeping, "db", SimpleNamespace(rooms=rooms))
    result = await inspect.unwrap(housekeeping.get_room_status_board)(current_user=SimpleNamespace(tenant_id="inventory-tenant"))
    rooms.find.assert_called_once_with({"tenant_id": "inventory-tenant"}, {"_id": 0})
    cursor.to_list.assert_awaited_once_with(None)
    return result


@pytest.mark.asyncio
async def test_room_board_excludes_virtual_and_inactive_rooms(monkeypatch):
    rows = [
        {"id": "a", "status": "available", "is_active": True},
        {"id": "b", "status": "occupied"},
        {"id": "c", "status": "dirty", "is_virtual": False},
        {"id": "paymaster", "status": "available", "is_virtual": True},
        {"id": "closed", "status": "dirty", "is_active": False},
    ]
    result = await board(monkeypatch, rows)
    assert [r["id"] for r in result["rooms"]] == ["a", "b", "c"]
    assert result["inventory_basis"] == "active_physical_rooms"
    assert result["total_rooms"] == sum(result["status_counts"].values()) == 3


@pytest.mark.asyncio
async def test_unknown_room_status_remains_visible_not_a_server_error(monkeypatch):
    result = await board(monkeypatch, [
        {"id": "missing"}, {"id": "blank", "status": " "},
        {"id": "other", "status": "out_of_service"}, {"id": "casing", "status": " OCCUPIED "},
    ])
    assert result["status_counts"]["unknown"] == 2
    assert result["status_counts"]["out_of_service"] == 1
    assert result["status_counts"]["occupied"] == 1
    assert result["total_rooms"] == sum(result["status_counts"].values()) == 4


@pytest.mark.asyncio
async def test_large_room_inventory_is_not_silently_truncated(monkeypatch):
    result = await board(monkeypatch, [{"id": str(i), "status": "available"} for i in range(1003)])
    assert result["total_rooms"] == result["status_counts"]["available"] == 1003


@pytest.mark.asyncio
async def test_empty_physical_inventory_is_a_real_zero(monkeypatch):
    result = await board(monkeypatch, [{"id": "virtual", "is_virtual": True, "status": "available"}])
    assert result["total_rooms"] == 0 and result["rooms"] == []
    assert sum(result["status_counts"].values()) == 0
