"""Room list status fields must survive database and cached read paths."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import cache_warmer
from core.pagination import PaginationParams
from routers import pms_rooms


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, field, direction):
        self.rows.sort(key=lambda row: row.get(field, ''), reverse=direction == -1)
        return self

    def skip(self, offset):
        self.rows = self.rows[offset:]
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, length=None):
        return [dict(row) for row in self.rows[:length]]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)

        return iterate()


@pytest.mark.asyncio
async def test_database_room_list_projects_independent_status_fields(monkeypatch):
    room = {"id": "room-1", "room_number": "101", "status": "occupied", "room_status": "clean", "housekeeping_status": "clean", "hk_status": "clean"}
    collection = SimpleNamespace(find=MagicMock(return_value=Cursor([room])))
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(rooms=collection))

    result = await pms_rooms.get_rooms(p=PaginationParams(limit=20, offset=0), current_user=SimpleNamespace(tenant_id="tenant-1"))

    query, projection = collection.find.call_args.args
    assert query["tenant_id"] == "tenant-1"
    for field in ("status", "room_status", "housekeeping_status", "hk_status"):
        assert projection[field] == 1
        assert result[0][field] == room[field]
    assert "guest_name" not in projection
    assert "current_booking_id" not in projection


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["redis", "warmer"])
async def test_cached_read_refreshes_real_status_and_does_not_mutate_snapshot(monkeypatch, source):
    import redis_cache

    snapshots = _inventory(100)
    snapshot = snapshots[0]
    snapshot.update({"status": "inspected", "hk_status": "clean"})
    current = [dict(room) for room in snapshots]
    current[0].update({"status": "maintenance", "housekeeping_status": "maintenance", "hk_status": "maintenance"})
    collection = SimpleNamespace(find=MagicMock(side_effect=lambda *_args: Cursor(current)))
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(rooms=collection))
    monkeypatch.setattr(redis_cache, "redis_cache", SimpleNamespace(get=lambda _key: snapshots if source == "redis" else None))
    monkeypatch.setattr(cache_warmer, "cache_warmer", SimpleNamespace(get_cached=lambda _key, **_kwargs: snapshots))

    result = await pms_rooms.get_rooms(p=PaginationParams(limit=100, offset=0), current_user=SimpleNamespace(tenant_id="tenant-1"))

    assert result[0]["status"] == "maintenance"
    assert result[0]["housekeeping_status"] == "maintenance"
    assert snapshot["status"] == "inspected"
    assert snapshot["hk_status"] == "clean"
    query, projection = collection.find.call_args.args
    assert query == {
        "tenant_id": "tenant-1", "id": {"$in": [room["id"] for room in snapshots]},
        "$and": [
            {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
            {"$or": [{"is_virtual": False}, {"is_virtual": {"$exists": False}}]},
        ],
    }
    assert "guest_name" not in projection


@pytest.mark.asyncio
async def test_cached_room_missing_from_fresh_tenant_read_is_not_returned(monkeypatch):
    collection = SimpleNamespace(find=MagicMock(return_value=Cursor([])))
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(rooms=collection))

    result = await pms_rooms._enrich_rooms_with_housekeeping("tenant-1", [{"id": "deleted-room", "status": "inspected"}], refresh_status=True)

    assert result == []


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", ["cleaning", "inspection", "maintenance"])
async def test_housekeeping_metadata_uses_actual_task_when_occupancy_status_is_unchanged(monkeypatch, task_type):
    started = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    task = {"id": "task-1", "room_id": "room-1", "status": "in_progress", "started_at": started, "assigned_to": "Ayşe", "task_type": task_type}
    tasks = SimpleNamespace(find=MagicMock(return_value=Cursor([task])))
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(housekeeping_tasks=tasks))

    result = await pms_rooms._enrich_rooms_with_housekeeping("tenant-1", [{"id": "room-1", "status": "occupied", "housekeeping_status": "cleaning"}])

    assert result[0]["status"] == "occupied"
    assert result[0]["housekeeping"]["assigned_to_name"] == "Ayşe"
    assert result[0]["housekeeping"]["started_at"] == started
    assert result[0]["housekeeping"]["task_type"] == task_type
    assert 14 <= result[0]["housekeeping"]["elapsed_minutes"] <= 16
    assert tasks.find.call_args.args[0]["tenant_id"] == "tenant-1"


@pytest.mark.asyncio
async def test_existing_room_cleaning_timestamp_is_used_without_an_open_task(monkeypatch):
    started = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    tasks = SimpleNamespace(find=MagicMock(return_value=Cursor([])))
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(housekeeping_tasks=tasks))

    result = await pms_rooms._enrich_rooms_with_housekeeping("tenant-1", [{"id": "room-1", "status": "occupied", "housekeeping_status": "cleaning", "cleaning_started_at": started}])

    assert result[0]["housekeeping"]["started_at"] == started
    assert 9 <= result[0]["housekeeping"]["elapsed_minutes"] <= 11
    assert result[0]["housekeeping"]["assigned_to_name"] is None


@pytest.mark.asyncio
async def test_prewarmed_snapshot_retains_operational_status_fields():
    room = {"id": "room-1", "tenant_id": "tenant-1", "status": "occupied", "room_status": "clean", "housekeeping_status": "clean", "hk_status": "clean"}
    collection = SimpleNamespace(count_documents=AsyncMock(return_value=1), find=MagicMock(return_value=Cursor([room])))
    warmer = cache_warmer.CacheWarmer(SimpleNamespace(rooms=collection))

    await warmer.warm_rooms_cache("tenant-1")

    projection = collection.find.call_args.args[1]
    for field in ("status", "room_status", "housekeeping_status", "hk_status"):
        assert projection[field] == 1
        assert warmer.cache["rooms:tenant-1"]["data"][0][field] == room[field]


@pytest.mark.asyncio
@pytest.mark.parametrize("currency", ["USD", "EUR", None])
async def test_inhouse_room_card_source_preserves_currency_without_conversion(currency):
    from domains.pms.frontdesk_service import FrontdeskService

    booking = {"id": "booking-1", "room_id": "room-1", "status": "checked_in", "balance": 125}
    if currency is not None:
        booking["currency"] = currency
    rooms = SimpleNamespace(find=MagicMock(return_value=Cursor([{"id": "room-1", "room_number": "201", "status": "occupied"}])))
    bookings = SimpleNamespace(find=MagicMock(return_value=Cursor([booking])))
    service = FrontdeskService.__new__(FrontdeskService)
    service._db = SimpleNamespace(bookings=bookings, rooms=rooms)

    result = await service.get_unified_inhouse(SimpleNamespace(tenant_id="tenant-1"))

    stay = result.data["in_house"][0]
    assert stay["balance"] == 125
    assert stay.get("currency") == currency
    assert stay["room_number"] == "201"
    assert bookings.find.call_args.args[0]["tenant_id"] == "tenant-1"


def _room_collection(rows):
    def find(query, _projection):
        selected = [row for row in rows if row.get("tenant_id") == query.get("tenant_id")]
        if "$and" in query:
            assert query["$and"] == [
                {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
                {"$or": [{"is_virtual": False}, {"is_virtual": {"$exists": False}}]},
            ]
            selected = [row for row in selected if row.get("is_active", True) is True and row.get("is_virtual", False) is False]
        if "id" in query:
            selected = [row for row in selected if row["id"] in query["id"]["$in"]]
        return Cursor(selected)

    return SimpleNamespace(find=MagicMock(side_effect=find))


def _inventory(count):
    return [{"_id": index, "id": f"room-{index:04}", "tenant_id": "tenant-1", "room_number": str(index + 100), "status": "available"} for index in range(count)]


@pytest.mark.asyncio
async def test_room_warmer_is_complete_tenant_scoped_active_nonvirtual_and_sorted():
    rows = list(reversed(_inventory(151))) + [
        {"_id": -1, "id": "other-tenant", "tenant_id": "tenant-2", "room_number": "901"},
        {"_id": -2, "id": "inactive", "tenant_id": "tenant-1", "room_number": "902", "is_active": False},
        {"_id": -3, "id": "virtual", "tenant_id": "tenant-1", "room_number": "903", "is_virtual": True},
    ]
    collection = _room_collection(rows)
    warmer = cache_warmer.CacheWarmer(SimpleNamespace(rooms=collection))

    await warmer.warm_rooms_cache("tenant-1")

    result = warmer.get_cached("rooms:tenant-1", require_complete=True)
    assert len(result) == 151
    assert [room["_id"] for room in result] == list(range(151))
    assert "rooms:tenant-2" not in warmer.cache
    assert collection.find.call_args.args[0]["tenant_id"] == "tenant-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2000, 2001])
async def test_room_cache_bound_is_proven_before_caching(count):
    warmer = cache_warmer.CacheWarmer(SimpleNamespace(rooms=_room_collection(_inventory(count))))
    warmer.cache["rooms:tenant-1"] = {"data": ["old partial"]}

    await warmer.warm_rooms_cache("tenant-1")

    if count > 2000:
        assert "rooms:tenant-1" not in warmer.cache
    else:
        assert len(warmer.get_cached("rooms:tenant-1", require_complete=True)) == count


def test_room_read_rejects_legacy_partial_cache_without_completeness_marker():
    warmer = cache_warmer.CacheWarmer(SimpleNamespace())
    warmer.cache["rooms:tenant-1"] = {"data": _inventory(100), "expires_at": datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=20)}
    assert len(warmer.get_cached("rooms:tenant-1")) == 100
    assert warmer.get_cached("rooms:tenant-1", require_complete=True) is None


@pytest.mark.asyncio
async def test_warm_first_page_and_database_following_pages_preserve_all_rooms(monkeypatch):
    import redis_cache

    rows = list(reversed(_inventory(551)))
    database = SimpleNamespace(rooms=_room_collection(rows))
    warmer = cache_warmer.CacheWarmer(database)
    await warmer.warm_rooms_cache("tenant-1")
    monkeypatch.setattr(cache_warmer, "cache_warmer", warmer)
    monkeypatch.setattr(redis_cache, "redis_cache", None)
    monkeypatch.setattr(pms_rooms, "db", database)

    pages = [await pms_rooms.get_rooms(p=PaginationParams(limit=200, offset=offset), current_user=SimpleNamespace(tenant_id="tenant-1")) for offset in [0, 200, 400]]

    assert [len(page) for page in pages] == [200, 200, 151]
    assert [room["id"] for page in pages for room in page] == [room["id"] for room in _inventory(551)]


@pytest.mark.asyncio
async def test_deleted_cached_room_falls_back_to_a_full_database_page(monkeypatch):
    import redis_cache

    original = _inventory(251)
    rows = list(original)
    database = SimpleNamespace(rooms=_room_collection(rows))
    warmer = cache_warmer.CacheWarmer(database)
    await warmer.warm_rooms_cache("tenant-1")
    rows.pop(0)
    monkeypatch.setattr(cache_warmer, "cache_warmer", warmer)
    monkeypatch.setattr(redis_cache, "redis_cache", None)
    monkeypatch.setattr(pms_rooms, "db", database)

    page = await pms_rooms.get_rooms(p=PaginationParams(limit=200, offset=0), current_user=SimpleNamespace(tenant_id="tenant-1"))

    assert len(page) == 200
    assert page[0]["id"] == original[1]["id"]
    assert page[-1]["id"] == original[200]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [("is_active", False), ("is_virtual", True)])
async def test_cached_room_membership_change_does_not_shorten_the_first_page(monkeypatch, field, value):
    import redis_cache

    rows = _inventory(251)
    database = SimpleNamespace(rooms=_room_collection(rows))
    warmer = cache_warmer.CacheWarmer(database)
    await warmer.warm_rooms_cache("tenant-1")
    rows[0][field] = value
    monkeypatch.setattr(cache_warmer, "cache_warmer", warmer)
    monkeypatch.setattr(redis_cache, "redis_cache", None)
    monkeypatch.setattr(pms_rooms, "db", database)

    page = await pms_rooms.get_rooms(p=PaginationParams(limit=200, offset=0), current_user=SimpleNamespace(tenant_id="tenant-1"))

    assert len(page) == 200
    assert page[0]["id"] == "room-0001"
    assert page[-1]["id"] == "room-0200"
    assert "rooms:tenant-1" not in warmer.cache


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["redis", "warmer"])
async def test_short_cached_page_cannot_hide_appended_rooms(monkeypatch, source):
    import redis_cache

    rows = _inventory(151)
    snapshots = [dict(room) for room in rows]
    database = SimpleNamespace(rooms=_room_collection(rows))
    warmer = cache_warmer.CacheWarmer(database)
    await warmer.warm_rooms_cache("tenant-1")
    rows.extend(_inventory(251)[151:])
    monkeypatch.setattr(cache_warmer, "cache_warmer", warmer if source == "warmer" else None)
    monkeypatch.setattr(redis_cache, "redis_cache", SimpleNamespace(get=lambda _key: snapshots, set=MagicMock()) if source == "redis" else None)
    monkeypatch.setattr(pms_rooms, "db", database)

    pages = [await pms_rooms.get_rooms(p=PaginationParams(limit=200, offset=offset), current_user=SimpleNamespace(tenant_id="tenant-1")) for offset in [0, 200]]

    assert [len(page) for page in pages] == [200, 51]
    assert [room["id"] for page in pages for room in page] == [room["id"] for room in _inventory(251)]


@pytest.mark.asyncio
@pytest.mark.parametrize("currency", ["USD", "EUR"])
async def test_default_booking_cache_preserves_reservation_currency(currency):
    booking = {"id": "booking-1", "tenant_id": "tenant-1", "currency": currency, "total_amount": 125}
    collection = SimpleNamespace(count_documents=AsyncMock(return_value=1), find=MagicMock(return_value=Cursor([booking])))
    warmer = cache_warmer.CacheWarmer(SimpleNamespace(bookings=collection))

    await warmer.warm_bookings_cache("tenant-1")

    assert collection.find.call_args.args[1]["currency"] == 1
    assert warmer.cache["bookings:tenant-1"]["data"][0]["currency"] == currency
    assert warmer.cache["bookings:tenant-1"]["data"][0]["total_amount"] == 125
