"""Offline regressions: reduce reads without caching booking decisions."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters-long")

from core import room_type_inventory_service as inventory
from modules.observability.distributed_tracing import TracingService
from workers.ari_push_worker import next_poll_delay


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args):
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


def test_idle_poll_is_bounded_and_work_restores_fast_poll():
    delay = 5
    delays = []
    for _ in range(5):
        delay = next_poll_delay(delay, False)
        delays.append(delay)
    assert delays == [10, 20, 30, 30, 30]
    assert next_poll_delay(delay, True) == 5


@pytest.mark.asyncio
async def test_worker_processes_new_work_after_idle(monkeypatch):
    from workers import ari_push_worker as worker
    collection = Mock()
    collection.aggregate.side_effect = [Cursor([]), Cursor([]), Cursor([{"_id": "t1"}])]
    monkeypatch.setattr(worker, "db", {"ari_change_sets": collection})
    push = AsyncMock(return_value={"pushed": 1, "failed": 0})
    monkeypatch.setattr(worker, "push_pending_changes", push)
    monkeypatch.setattr(worker, "get_failure_tracker", lambda: Mock())
    delays = []

    async def sleep(delay):
        delays.append(delay)
        if len(delays) == 3:
            raise asyncio.CancelledError()

    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.ari_push_worker_loop()
    assert delays == [10, 20, 5]
    push.assert_awaited_once_with("t1", limit=20)


@pytest.mark.asyncio
async def test_reconcile_reuses_rooms_but_reads_each_days_locks(monkeypatch):
    rooms = Mock()
    rooms.aggregate.return_value = Cursor([
        {"_id": "standard", "count": 2, "room_ids": ["a", "b"]},
        {"_id": "suite", "count": 1, "room_ids": ["c"]},
    ])
    locks = Mock()
    locks.aggregate.side_effect = [Cursor([
        {"_id": {"room_id": "a", "lock_type": "booking"}, "count": 1}
    ]), Cursor([])]
    stored = Mock()
    stored.find.return_value = Cursor([])
    stored.update_one = AsyncMock()
    monkeypatch.setattr(inventory, "db", SimpleNamespace(
        rooms=rooms, room_night_locks=locks, room_type_inventory=stored,
    ))
    result = await inventory.reconcile_date_range("tenant-a", "2026-09-09", "2026-09-10")
    assert result["dates_processed"] == 2
    assert rooms.aggregate.call_count == 1
    assert locks.aggregate.call_count == 2
    assert stored.find.call_count == 2  # not once per room type
    assert stored.find_one.call_count == 0
    rows = [c.args[1]["$set"] for c in stored.update_one.call_args_list]
    assert [(r["date"], r["room_type"], r["sellable"]) for r in rows] == [
        ("2026-09-09", "standard", 1), ("2026-09-09", "suite", 1),
        ("2026-09-10", "standard", 2), ("2026-09-10", "suite", 1),
    ]
    assert all(r["tenant_id"] == "tenant-a" for r in rows)
    assert locks.aggregate.call_args_list[1].args[0][0]["$match"]["night_date"] == "2026-09-10"
    # A subsequent tenant/run must read its own rooms, never reuse the snapshot.
    locks.aggregate.side_effect = [Cursor([])]
    await inventory.reconcile_date_range("tenant-b", "2026-09-09", "2026-09-09")
    assert rooms.aggregate.call_count == 2
    assert rooms.aggregate.call_args.args[0][0]["$match"]["tenant_id"] == "tenant-b"


@pytest.mark.asyncio
async def test_trace_summary_reads_only_aggregate_fields(monkeypatch):
    from core import database
    collection = Mock()
    collection.find.return_value = Cursor([
        {"trace_id": "one", "request_path": "/test", "duration_ms": 12, "status_code": 200},
    ])
    monkeypatch.setattr(database, "db", SimpleNamespace(observability_traces=collection))
    result = await TracingService().get_trace_summary()
    assert result["total_requests"] == 1
    assert result["endpoints"][0]["avg_ms"] == 12
    projection = collection.find.call_args.args[1]
    assert projection == {"_id": 0, "trace_id": 1, "request_path": 1,
                          "duration_ms": 1, "status_code": 1, "is_slow": 1}
