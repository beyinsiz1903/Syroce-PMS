"""DND must survive the real room read paths, not only a PATCH response."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import cache_warmer
import redis_cache
from core.pagination import PaginationParams
from domains.pms import operations_router as operations
from routers import pms_rooms


class Cursor:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def sort(self, *args):
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length=None):
        return deepcopy(self.rows[:length])

    def __aiter__(self):
        async def values():
            for row in self.rows:
                yield deepcopy(row)
        return values()


def collection(rows):
    def find(query, projection):
        selected = [row for row in rows if row["tenant_id"] == query["tenant_id"]]
        if "id" in query:
            selected = [row for row in selected if row["id"] in query["id"]["$in"]]
        return Cursor([{key: value for key, value in row.items() if projection.get(key) == 1} for row in selected])
    return SimpleNamespace(find=MagicMock(side_effect=find), count_documents=AsyncMock(return_value=len(rows)))


@pytest.mark.asyncio
@pytest.mark.parametrize("search", [None, "QT2"])
async def test_database_and_global_search_read_preserve_dnd_without_history(monkeypatch, search):
    rows = [{"id": "public", "tenant_id": "tenant", "room_number": "QT2ED0", "status": "occupied", "dnd": True, "features_audit": [{"actor_id": "private-history"}]}, {"id": "foreign", "tenant_id": "other", "dnd": False}]
    rooms = collection(rows)
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(rooms=rooms))
    result = await pms_rooms.get_rooms(p=PaginationParams(limit=20, offset=0), search=search, current_user=SimpleNamespace(tenant_id="tenant"))
    assert len(result) == 1 and result[0]["id"] == "public"
    assert result[0]["dnd"] is True
    assert "features_audit" not in result[0]
    assert rooms.find.call_args.args[1]["dnd"] == 1
    if search:
        assert rooms.find.call_args.args[0]["room_number"] == {"$regex": "^QT2", "$options": "i"}


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["redis", "warmer"])
@pytest.mark.parametrize("current_state", [True, False, "absent"])
async def test_cached_reads_refresh_dnd_without_changing_snapshot(monkeypatch, source, current_state):
    snapshots = [{"id": f"room-{i}", "tenant_id": "tenant", "room_number": str(i), "status": "occupied", "dnd": current_state is not True} for i in range(100)]
    current = deepcopy(snapshots)
    if current_state == "absent":
        current[0].pop("dnd")
    else:
        current[0]["dnd"] = current_state
    preserved = deepcopy(snapshots)
    rooms = collection(current)
    monkeypatch.setattr(pms_rooms, "db", SimpleNamespace(rooms=rooms))
    monkeypatch.setattr(redis_cache, "redis_cache", SimpleNamespace(get=lambda key: snapshots if source == "redis" else None))
    monkeypatch.setattr(cache_warmer, "cache_warmer", SimpleNamespace(get_cached=lambda key, **kwargs: snapshots))
    result = await pms_rooms.get_rooms(p=PaginationParams(limit=100, offset=0), current_user=SimpleNamespace(tenant_id="tenant"))
    if current_state == "absent":
        assert "dnd" not in result[0]
    else:
        assert result[0]["dnd"] is current_state
    assert snapshots == preserved
    assert rooms.find.call_args.args[0]["tenant_id"] == "tenant"
    assert rooms.find.call_args.args[1]["dnd"] == 1
    assert "features_audit" not in rooms.find.call_args.args[1]


@pytest.mark.asyncio
async def test_new_warm_snapshot_includes_dnd_but_not_audit_history():
    rooms = collection([{"id": "r", "tenant_id": "tenant", "dnd": True, "status": "occupied", "features_audit": ["private"]}])
    warmer = cache_warmer.CacheWarmer(SimpleNamespace(rooms=rooms))
    await warmer.warm_rooms_cache("tenant")
    result = warmer.get_cached("rooms:tenant", require_complete=True)
    assert result[0]["dnd"] is True
    assert "features_audit" not in result[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["changed", "same", "stale", "lost-race"])
async def test_dnd_cache_invalidation_only_after_durable_change(monkeypatch, case):
    room = {"_id": "storage", "id": "public", "tenant_id": "tenant", "dnd": False}
    rooms = SimpleNamespace(find_one=AsyncMock(return_value=room), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0 if case == "lost-race" else 1)))
    monkeypatch.setattr(operations, "db", SimpleNamespace(rooms=rooms))
    invalidate = MagicMock()
    monkeypatch.setattr(pms_rooms, "_invalidate_room_list_caches", invalidate)
    body = {"dnd": case != "same", "expected_dnd": case == "stale"}
    if case in {"stale", "lost-race"}:
        with pytest.raises(HTTPException) as exc:
            await operations.update_room_features("public", body, current_user=SimpleNamespace(id="operator", tenant_id="tenant"))
        assert exc.value.status_code == 409
    else:
        result = await operations.update_room_features("public", body, current_user=SimpleNamespace(id="operator", tenant_id="tenant"))
        assert result["already_applied"] is (case == "same")
    assert invalidate.call_args_list == ([] if case != "changed" else [(("tenant",), {})])
