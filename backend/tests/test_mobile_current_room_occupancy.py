from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.mobile_router import hub
from domains.pms.room_occupancy import current_room_occupancy, load_current_room_occupancy


def test_five_overdue_checked_in_rooms_of_seventeen_are_29_point_4_percent():
    rooms = [{"id": f"r{i}", "room_number": str(i), "status": "available"} for i in range(17)]
    bookings = [{"room_id": f"r{i}", "status": "checked_in", "check_out": "2026-09-28"} for i in range(5)]
    assert current_room_occupancy(rooms, bookings) == {
        "occupied_rooms": 5,
        "total_rooms": 17,
        "occupancy_pct": 29.4,
        "occupancy_basis": "current_room_state",
    }


def test_counts_distinct_physical_rooms_not_bookings_people_or_forecast():
    rooms = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    bookings = [
        {"room_id": "a", "status": "checked_in", "adults": 4},
        {"room_id": "a", "status": "checked_in"},
        {"room_id": "b", "status": "confirmed"},
        {"room_id": "c", "status": "checked_out"},
        {"room_id": "other-tenant-room", "status": "checked_in"},
        {"status": "checked_in"},
    ]
    assert current_room_occupancy(rooms, bookings)["occupied_rooms"] == 1


def test_matches_rooms_screen_block_priority_housekeeping_and_assignment_fallbacks():
    rooms = [
        {"id": "a", "status": "occupied", "housekeeping_status": "dirty"},
        {"id": "b", "status": "available", "current_booking_id": "b1"},
        {"id": "c", "status": "available", "room_number": "103"},
        {"id": "d", "status": "occupied", "hk_status": "out_of_order"},
        {"id": "e", "status": "maintenance"},
        {"id": "f", "status": "dirty"},
    ]
    bookings = [{"room_number": " 103 ", "status": "checked_in"}, {"room_id": "e", "status": "checked_in"}]
    result = current_room_occupancy(rooms, bookings)
    assert result["occupied_rooms"] == 3
    assert result["occupancy_pct"] == 50
    assert current_room_occupancy([], [])["occupancy_pct"] == 0


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, limit):
        assert limit is None  # No arbitrary 500/1000 row truncation.
        return self.rows


class Collection:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def find(self, query, projection):
        self.queries.append(query)
        return Cursor(self.rows)


@pytest.mark.asyncio
async def test_loader_scopes_both_queries_and_active_non_virtual_inventory():
    database = SimpleNamespace(
        rooms=Collection([{"id": "r1"}]),
        bookings=Collection([{"room_id": "r1", "status": "checked_in"}]),
    )
    result = await load_current_room_occupancy(database, "tenant-a")
    assert result["occupancy_pct"] == 100
    query = database.rooms.queries[0]
    assert query["tenant_id"] == "tenant-a"
    assert {"$or": [{"is_virtual": False}, {"is_virtual": {"$exists": False}}]} in query["$and"]
    assert {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]} in query["$and"]
    assert database.bookings.queries == [{"tenant_id": "tenant-a", "status": "checked_in"}]


@pytest.mark.asyncio
async def test_executive_digest_serializes_the_current_room_snapshot(monkeypatch):
    user = SimpleNamespace(id="u1", tenant_id="tenant-a", name="Demo", username="demo")
    monkeypatch.setattr(hub, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(hub, "_collect_my_tasks", AsyncMock(return_value=[]))
    monkeypatch.setattr(hub, "_can", lambda user, op: op == "view_executive_reports")
    monkeypatch.setattr(hub, "_can_procurement", lambda user: False)
    counter = SimpleNamespace(count_documents=AsyncMock(return_value=0))
    database = SimpleNamespace(
        notifications=counter,
        alerts=counter,
        bookings=counter,
        maintenance_tasks=counter,
        tasks=counter,
        tenants=SimpleNamespace(find_one=AsyncMock(return_value={"property_name": "Demo"})),
    )
    monkeypatch.setattr(hub, "db", database)
    snapshot = {"occupied_rooms": 5, "total_rooms": 17, "occupancy_pct": 29.4, "occupancy_basis": "current_room_state"}
    loader = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(hub, "load_current_room_occupancy", loader)
    result = await hub.get_today_digest(credentials=None)
    assert all(result[key] == value for key, value in snapshot.items())
    loader.assert_awaited_once_with(database, "tenant-a")
