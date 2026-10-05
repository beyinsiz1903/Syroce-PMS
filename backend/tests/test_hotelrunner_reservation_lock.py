"""Direct regressions for HotelRunner reservation lease ownership."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager import unified_repository as repo
from domains.channel_manager.ingest import pipeline


class _LockCollection:
    def __init__(self):
        self.doc = {
            "id": "opaque-lineage",
            "lock_holder": None,
            "lock_owner_token": None,
            "lock_expires_at": None,
        }

    async def update_one(self, query, update):
        if not self._matches(query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        self.doc.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)

    def _matches(self, query):
        if query.get("id") != self.doc["id"]:
            return False
        if "lock_owner_token" in query and query["lock_owner_token"] != self.doc.get("lock_owner_token"):
            return False
        if "$or" in query and not any(self._matches_clause(clause) for clause in query["$or"]):
            return False
        expires_query = query.get("lock_expires_at", {})
        if "$gte" in expires_query:
            expires_at = self.doc.get("lock_expires_at")
            return bool(expires_at and expires_at >= expires_query["$gte"])
        return True

    def _matches_clause(self, clause):
        field, expected = next(iter(clause.items()))
        actual = self.doc.get(field)
        if isinstance(expected, dict) and "$lt" in expected:
            return bool(actual and actual < expected["$lt"])
        if isinstance(expected, dict) and "$exists" in expected:
            return (field in self.doc) is expected["$exists"]
        return actual == expected


class _DB:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


@pytest.fixture
def lock_collection(monkeypatch):
    collection = _LockCollection()
    monkeypatch.setattr(pipeline, "db", _DB(collection))
    return collection


@pytest.mark.asyncio
async def test_active_lease_has_unique_owner_and_blocks_second_worker(lock_collection):
    lineage = {"id": "opaque-lineage"}

    first_token = await pipeline._acquire_reservation_lock(lineage)
    second_token = await pipeline._acquire_reservation_lock({"id": "opaque-lineage"})

    assert first_token
    assert first_token != "opaque-lineage"
    assert lock_collection.doc["lock_owner_token"] == first_token
    assert second_token is None


@pytest.mark.asyncio
async def test_expired_lease_is_reacquired_with_new_owner(lock_collection):
    first_token = await pipeline._acquire_reservation_lock({"id": "opaque-lineage"})
    lock_collection.doc["lock_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    second_token = await pipeline._acquire_reservation_lock({"id": "opaque-lineage"})

    assert first_token
    assert second_token
    assert second_token != first_token


@pytest.mark.asyncio
async def test_stale_owner_cannot_extend_or_release_successor_lease(lock_collection):
    stale_token = await pipeline._acquire_reservation_lock({"id": "opaque-lineage"})
    lock_collection.doc["lock_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    current_token = await pipeline._acquire_reservation_lock({"id": "opaque-lineage"})

    assert await pipeline._extend_reservation_lock("opaque-lineage", stale_token) is False
    assert await pipeline._release_reservation_lock("opaque-lineage", stale_token) is False
    assert lock_collection.doc["lock_owner_token"] == current_token
    assert await pipeline._extend_reservation_lock("opaque-lineage", current_token) is True
    assert await pipeline._release_reservation_lock("opaque-lineage", current_token) is True
    assert lock_collection.doc["lock_owner_token"] is None


@pytest.mark.asyncio
async def test_heartbeat_loss_cancels_inflight_mutation(monkeypatch):
    lock_lost = asyncio.Event()
    mutation_started = asyncio.Event()
    mutation_cancelled = asyncio.Event()

    async def mutation():
        mutation_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            mutation_cancelled.set()
            raise

    task = asyncio.create_task(pipeline._run_reservation_mutation(mutation(), lock_lost))
    await mutation_started.wait()
    lock_lost.set()

    with pytest.raises(pipeline.ReservationLockLostError):
        await task
    assert mutation_cancelled.is_set()


@pytest.mark.asyncio
async def test_worker_cancellation_stops_inflight_mutation():
    lock_lost = asyncio.Event()
    mutation_started = asyncio.Event()
    mutation_cancelled = asyncio.Event()

    async def mutation():
        mutation_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            mutation_cancelled.set()
            raise

    task = asyncio.create_task(pipeline._run_reservation_mutation(mutation(), lock_lost))
    await mutation_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert mutation_cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("database unavailable")])
async def test_heartbeat_fails_closed(monkeypatch, failure):
    lock_lost = asyncio.Event()
    extend = AsyncMock(side_effect=failure if failure else None, return_value=False)
    real_sleep = asyncio.sleep

    async def no_wait(_seconds):
        # ``pipeline.asyncio`` is the process-wide asyncio module.  Keep the
        # heartbeat immediate without starving pytest's event loop/timeout
        # machinery while that module attribute is monkeypatched.
        await real_sleep(0)

    monkeypatch.setattr(pipeline, "_extend_reservation_lock", extend)
    monkeypatch.setattr(pipeline.asyncio, "sleep", no_wait)

    await pipeline._reservation_lock_heartbeat("opaque-lineage", "opaque-token", lock_lost)

    assert lock_lost.is_set()
    extend.assert_awaited_once()


@pytest.mark.asyncio
async def test_lineage_update_is_fenced_and_does_not_overwrite_lease(monkeypatch):
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    monkeypatch.setattr(repo, "db", _DB(collection))
    expires = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    doc = {
        "id": "opaque-lineage",
        "tenant_id": "tenant",
        "provider": "hotelrunner",
        "external_reservation_id": "opaque-reservation",
        "version": 3,
        "status": "modified",
        "lock_holder": "ingest-pipeline",
        "lock_owner_token": "opaque-token",
        "lock_acquired_at": "opaque-time",
        "lock_heartbeat_at": "opaque-time",
        "lock_expires_at": expires,
    }

    lineage_id = await repo.update_reservation_lineage_with_lock(doc, "opaque-token")

    assert lineage_id == "opaque-lineage"
    query, update = collection.update_one.await_args.args
    assert query["lock_owner_token"] == "opaque-token"
    assert "$gte" in query["lock_expires_at"]
    assert update["$inc"] == {"version": 1}
    assert not any(key.startswith("lock_") for key in update["$set"])


@pytest.mark.asyncio
async def test_lineage_update_rejects_lost_owner(monkeypatch):
    monkeypatch.setattr(
        repo,
        "update_reservation_lineage_with_lock",
        AsyncMock(return_value=None),
    )

    with pytest.raises(pipeline.ReservationLockLostError):
        await pipeline._update_lineage(
            {"id": "opaque-lineage", "status": "confirmed"},
            {},
            "opaque-hash",
            "pull",
            "details_changed",
            "stale-token",
        )
