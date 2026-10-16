"""Orphan-tenant cleanup: never a real hotel, nothing deleted, undoable."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import deactivate_orphan_tenant_records as orphan

T = "343281"


def _get(row, key):
    for part in key.split("."):
        row = row.get(part) if isinstance(row, dict) else None
    return row


def _match(row, query):
    for key, cond in query.items():
        if key == "$or":
            if not any(_match(row, sub) for sub in cond):
                return False
            continue
        value = _get(row, key)
        if isinstance(cond, dict) and "$ne" in cond:
            if value == cond["$ne"]:
                return False
        elif value != cond:
            return False
    return True


class _Coll:
    def __init__(self, rows=()):
        self.rows = [copy.deepcopy(r) for r in rows]
        self.before_write = None

    def find(self, query, *_a, **_k):
        rows = [copy.deepcopy(r) for r in self.rows if _match(r, query)]

        class _Cur:
            def __aiter__(self):
                self._it = iter(rows)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _Cur()

    async def find_one(self, query, *_a, **_k):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, query)), None)

    async def count_documents(self, query):
        return sum(1 for r in self.rows if _match(r, query))

    async def update_one(self, query, update):
        if self.before_write:
            hook, self.before_write = self.before_write, None
            hook()
        for row in self.rows:
            if _match(row, query):
                for key, value in copy.deepcopy(update.get("$set", {})).items():
                    target, *path = key.split(".")
                    if path:
                        row.setdefault(target, {})[path[0]] = value
                    else:
                        row[key] = value
                for key in update.get("$unset", {}):
                    row.pop(key, None)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def insert_one(self, doc):
        self.rows.append(doc)


class _Db(SimpleNamespace):
    async def list_collection_names(self):
        return [k for k, v in vars(self).items() if isinstance(v, _Coll)]

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def world(monkeypatch):
    import core.atomic_booking as atomic
    import core.tenant_db as tenant_db

    database = _Db(
        tenants=_Coll([{"id": "uuid-real", "hotel_id": "100001", "property_name": "Real"}]),
        bookings=_Coll([
            {"id": "b1", "tenant_id": T, "status": "confirmed"},
            {"id": "b2", "tenant_id": T, "status": "checked_out"},
            {"id": "b3", "tenant_id": "uuid-real", "status": "confirmed"},
        ]),
        payments=_Coll([{"id": "p1", "tenant_id": T, "amount": 800}]),
        test_data_cleanup_runs=_Coll(),
    )
    monkeypatch.setattr(tenant_db, "get_system_db", lambda: database)
    monkeypatch.setattr(atomic, "release_booking_nights", AsyncMock(return_value=2))
    return database


def _b(world, booking_id):
    return next(r for r in world.bookings.rows if r["id"] == booking_id)


@pytest.mark.asyncio
async def test_refuses_a_real_hotel_by_id_or_hotel_id(world, monkeypatch):
    monkeypatch.setenv("ALLOW_ORPHAN_DEACTIVATION", "true")
    assert await orphan.main(["--tenant-id", "uuid-real", "--apply"]) == 3
    assert await orphan.main(["--tenant-id", "100001", "--apply"]) == 3
    assert _b(world, "b3")["status"] == "confirmed" and world.test_data_cleanup_runs.rows == []


@pytest.mark.asyncio
async def test_dry_run_counts_and_writes_nothing(world):
    assert await orphan.main(["--tenant-id", T]) == 0
    run = world.test_data_cleanup_runs.rows[0]
    assert run["mode"] == "dry_run" and run["found"]["collections"] == {"bookings": 2, "payments": 1}
    assert _b(world, "b1")["status"] == "confirmed"


@pytest.mark.asyncio
async def test_apply_needs_the_switch(world, monkeypatch):
    monkeypatch.delenv("ALLOW_ORPHAN_DEACTIVATION", raising=False)
    assert await orphan.main(["--tenant-id", T, "--apply"]) == 2
    assert _b(world, "b1")["status"] == "confirmed"


@pytest.mark.asyncio
async def test_apply_cancels_open_bookings_only_and_undo_restores(world, monkeypatch):
    monkeypatch.setenv("ALLOW_ORPHAN_DEACTIVATION", "true")
    assert await orphan.main(["--tenant-id", T, "--apply"]) == 0
    applied = world.test_data_cleanup_runs.rows[0]["applied"]
    assert applied == {"marked": 2, "cancelled": 1, "released_nights": 2, "resumed": 0}
    b1, b2 = _b(world, "b1"), _b(world, "b2")
    assert (b1["status"], b1["cancellation_reason"]) == ("cancelled", orphan.CLEANUP_TAG)
    assert b2["status"] == "checked_out" and b2["cleanup"]["tag"] == orphan.CLEANUP_TAG
    assert _b(world, "b3")["status"] == "confirmed"  # other tenant untouched
    assert len(world.payments.rows) == 1  # nothing deleted

    # A second apply does not re-mark already cleaned bookings.
    assert await orphan.main(["--tenant-id", T, "--apply"]) == 0
    assert world.test_data_cleanup_runs.rows[1]["applied"]["marked"] == 0

    run_id = b1["cleanup"]["run_id"]
    assert await orphan.main(["--tenant-id", T, "--undo", run_id]) == 0
    b1, b2 = _b(world, "b1"), _b(world, "b2")
    assert b1["status"] == "confirmed" and "cleanup" not in b1 and "cancellation_reason" not in b1
    assert b2["status"] == "checked_out" and "cleanup" not in b2


@pytest.mark.asyncio
async def test_undo_leaves_a_booking_changed_since(world, monkeypatch):
    monkeypatch.setenv("ALLOW_ORPHAN_DEACTIVATION", "true")
    await orphan.main(["--tenant-id", T, "--apply"])
    run_id = _b(world, "b1")["cleanup"]["run_id"]
    _b(world, "b1")["status"] = "checked_out"  # someone changed it after the run
    result = await orphan.undo_run(world, T, run_id)
    assert result["conflicts"] == ["b1"] and _b(world, "b1")["status"] == "checked_out"


@pytest.mark.asyncio
async def test_booking_changed_between_read_and_write_is_left(world, monkeypatch):
    world.bookings.before_write = lambda: _b(world, "b1").update(status="checked_in")
    result = await orphan.apply_run(world, T, "run-x")
    assert _b(world, "b1")["status"] == "checked_in" and result["cancelled"] == 0


@pytest.mark.asyncio
async def test_interrupted_release_is_finished_by_the_next_run(world, monkeypatch):
    import core.atomic_booking as atomic

    monkeypatch.setenv("ALLOW_ORPHAN_DEACTIVATION", "true")
    monkeypatch.setattr(atomic, "release_booking_nights", AsyncMock(side_effect=RuntimeError("lock store down")))
    with pytest.raises(RuntimeError):
        await orphan.main(["--tenant-id", T, "--apply"])
    b1 = _b(world, "b1")
    assert b1["status"] == "cancelled" and b1["cleanup"]["nights_released"] is False

    release = AsyncMock(return_value=2)
    monkeypatch.setattr(atomic, "release_booking_nights", release)
    assert await orphan.main(["--tenant-id", T, "--apply"]) == 0
    assert release.await_count == 1 and release.await_args.args[1] == "b1"
    assert _b(world, "b1")["cleanup"]["nights_released"] is True
    assert world.test_data_cleanup_runs.rows[-1]["applied"]["resumed"] == 1


@pytest.mark.asyncio
async def test_undo_keeps_a_cancellation_edited_after_the_run(world, monkeypatch):
    monkeypatch.setenv("ALLOW_ORPHAN_DEACTIVATION", "true")
    await orphan.main(["--tenant-id", T, "--apply"])
    b1 = _b(world, "b1")
    run_id = b1["cleanup"]["run_id"]
    b1.update(cancellation_reason="guest_request", cancelled_at="2026-10-20T10:00:00")  # still "cancelled"
    result = await orphan.undo_run(world, T, run_id)
    assert result["conflicts"] == ["b1"]
    b1 = _b(world, "b1")
    assert (b1["status"], b1["cancellation_reason"]) == ("cancelled", "guest_request")
