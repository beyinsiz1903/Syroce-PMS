from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bootstrap.migrations.versions.v011_exely_reservation_fencing import (
    ExelyReservationFencingMigration,
)
from domains.channel_manager.providers import common_ingest
from domains.channel_manager.providers.event_fence import raw_event_fence_key


class _AsyncGroups:
    def __init__(self, groups):
        self._groups = iter(groups)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._groups)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _RawEvents:
    def __init__(self, groups):
        self._groups = groups
        self.bulk_write = AsyncMock()
        self.create_indexes = AsyncMock()

    def aggregate(self, pipeline, **kwargs):
        assert pipeline[0]["$match"]["tenant_id"] == {"$type": "string"}
        assert kwargs == {"allowDiskUse": True}
        return _AsyncGroups(self._groups)


def test_raw_event_fence_key_is_deterministic_and_tenant_scoped() -> None:
    first = raw_event_fence_key("tenant-a", "event")

    assert first == raw_event_fence_key("tenant-a", "event")
    assert first != raw_event_fence_key("tenant-b", "event")
    assert len(first) == 64
    assert "tenant-a" not in first
    assert "event" not in first


@pytest.mark.asyncio
async def test_migration_preserves_duplicates_and_fences_one_canonical_row() -> None:
    raw_events = _RawEvents(
        [
            {
                "_id": {"tenant_id": "tenant-a", "provider_event_id": "event-a"},
                "canonical_id": "first-document",
            },
            {
                "_id": {"tenant_id": "tenant-a", "provider_event_id": "event-b"},
                "canonical_id": "second-document",
            },
        ]
    )
    database = SimpleNamespace(
        exely_reservation_versions=SimpleNamespace(create_indexes=AsyncMock()),
        exely_raw_events=raw_events,
        bookings=SimpleNamespace(create_indexes=AsyncMock()),
    )

    await ExelyReservationFencingMigration().up(database)

    raw_events.bulk_write.assert_awaited_once()
    operations = raw_events.bulk_write.await_args.args[0]
    assert len(operations) == 2
    assert operations[0]._filter == {"_id": "first-document"}
    assert operations[0]._doc == {"$set": {"dedup_fence_key": raw_event_fence_key("tenant-a", "event-a")}}
    assert operations[1]._filter == {"_id": "second-document"}
    assert not hasattr(raw_events, "delete_many")

    index = raw_events.create_indexes.await_args.args[0][0].document
    assert index == {
        "key": {"dedup_fence_key": 1},
        "unique": True,
        "partialFilterExpression": {"dedup_fence_key": {"$type": "string"}},
        "name": "idx_exely_raw_event_unique",
    }


@pytest.mark.asyncio
async def test_new_exely_raw_event_carries_same_fence_key(monkeypatch) -> None:
    raw_events = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(common_ingest, "_col", lambda _provider, _key: raw_events)

    await common_ingest.store_raw_event(
        "exely",
        "tenant-a",
        "reservation",
        "external",
        "direct",
        {"safe": "metadata"},
        provider_event_id="event-a",
    )

    stored = raw_events.insert_one.await_args.args[0]
    assert stored["dedup_fence_key"] == raw_event_fence_key("tenant-a", "event-a")
    assert "payload" not in stored


@pytest.mark.asyncio
async def test_non_exely_raw_event_does_not_receive_exely_fence(monkeypatch) -> None:
    raw_events = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(common_ingest, "_col", lambda _provider, _key: raw_events)

    await common_ingest.store_raw_event(
        "hotelrunner",
        "tenant-a",
        "reservation",
        "external",
        "direct",
        {"safe": "metadata"},
        provider_event_id="event-a",
    )

    stored = raw_events.insert_one.await_args.args[0]
    assert "dedup_fence_key" not in stored
