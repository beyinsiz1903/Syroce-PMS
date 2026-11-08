from datetime import datetime
from types import SimpleNamespace

from domains.pms.frontdesk_service import FrontdeskService
from modules.pms_core.operational_snapshot_service import build_operational_snapshot


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)

    async def __aiter__(self):
        for row in self.rows:
            yield row


class _Rooms:
    def __init__(self):
        self.pipeline = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return _Cursor([
            {"_id": "available", "count": 2, "room_ids": ["r1", "r2"]},
            {"_id": "occupied", "count": 1, "room_ids": ["r3"]},
        ])


class _Bookings:
    def find(self, query, projection):
        assert query["tenant_id"] == "tenant-a"
        assert set(query["status"]["$in"]) == {"confirmed", "guaranteed", "checked_in"}
        return _Cursor([
            {"id": "b1", "room_id": "r1", "status": "checked_in", "check_in": "2026-10-02", "check_out": "2026-10-05"},
            {"id": "b2", "room_id": "r2", "status": "confirmed", "check_in": "2026-10-03", "check_out": "2026-10-04"},
            {"id": "b3", "room_id": None, "status": "guaranteed", "check_in": "2026-10-03", "check_out": "2026-10-05"},
            {"id": "b4", "room_id": "virtual-room", "status": "checked_in", "check_in": "2026-10-03", "check_out": "2026-10-05"},
            {"id": "b5", "room_id": "r3", "status": "confirmed", "check_in": "2026-10-01", "check_out": "2026-10-03"},
        ])


class _DB:
    def __init__(self):
        self.rooms = _Rooms()
        self.bookings = _Bookings()


async def test_snapshot_uses_business_day_active_inventory_and_distinct_rooms():
    database = _DB()
    snapshot = await build_operational_snapshot("tenant-a", business_date="2026-10-03", database=database)

    room_match = database.rooms.pipeline[0]["$match"]
    assert room_match["tenant_id"] == "tenant-a"
    assert {"$or": [{"is_virtual": False}, {"is_virtual": {"$exists": False}}]} in room_match["$and"]
    assert {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]} in room_match["$and"]
    assert snapshot["business_date"] == "2026-10-03"
    assert snapshot["total_rooms"] == 3
    assert snapshot["occupied_rooms"] == 3  # r1 + r2 + one truly unassigned stay; virtual assignment excluded
    assert snapshot["in_house_stays"] == 1
    assert snapshot["total_guests"] == 3
    assert snapshot["out_of_scope_assigned_stays"] == 1
    assert snapshot["today_checkins"] == 3
    assert snapshot["today_checkouts"] == 1
    assert snapshot["inventory_scope"] == "active_non_virtual_rooms"
    assert snapshot["snapshot_id"]
    assert "frontdesk_arrivals" not in snapshot


async def test_frontdesk_uses_open_day_for_counts_and_late_movements():
    class TenantSettings:
        async def find_one(self, query, _projection):
            assert query == {"tenant_id": "tenant-a"}
            return {"business_date": "2026-10-03"}

    class Bookings(_Bookings):
        def find(self, query, projection):
            rows = super().find(query, projection).rows
            rows[2]["check_in"] = datetime(2026, 10, 3)
            return _Cursor(rows + [
                {"id": "late", "status": "checked_in", "check_out": "2026-10-02T11:00:00Z"},
                {"id": "future", "status": "confirmed", "check_in": "2026-10-04", "check_out": "2026-10-06"},
                {"id": "hold", "status": "confirmed", "check_in": "2026-10-02", "source": {"kind": "ota_unmatched_hold"}},
                {"id": "invalid", "status": "confirmed", "check_in": "invalid"},
            ])

    class Rooms(_Rooms):
        def find(self, query, _projection):
            assert query["tenant_id"] == "tenant-a"
            return _Cursor([{"id": "r2", "room_number": "202"}])

    service = FrontdeskService()
    service._db = SimpleNamespace(rooms=Rooms(), bookings=Bookings(), tenant_settings=TenantSettings())
    result = await service.get_business_day_movements(SimpleNamespace(tenant_id="tenant-a"))

    assert result.data["business_date"] == "2026-10-03"
    assert result.data["today_checkins"] == 3
    assert result.data["today_checkouts"] == 1
    assert result.data["in_house_stays"] == 1
    assert result.data["available_rooms"] == 0
    assert [row["id"] for row in result.data["arrivals"]] == ["b2", "b3", "b5"]
    assert result.data["arrivals"][0]["room_number"] == "202"
    assert [row["id"] for row in result.data["departures"]] == ["late"]
