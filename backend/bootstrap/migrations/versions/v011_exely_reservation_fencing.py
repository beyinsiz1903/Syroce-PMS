"""Indexes required by Exely reservation claims and duplicate fencing."""

import logging

import pymongo.errors
from pymongo import ASCENDING, IndexModel, UpdateOne

from bootstrap.migrations.base import Migration
from domains.channel_manager.providers.event_fence import raw_event_fence_key

logger = logging.getLogger(__name__)

RAW_EVENT_BACKFILL_BATCH_SIZE = 500


async def _backfill_raw_event_fences(collection) -> int:
    """Fence one canonical row per legacy identity without deleting duplicates."""
    cursor = collection.aggregate(
        [
            {
                "$match": {
                    "tenant_id": {"$type": "string"},
                    "provider_event_id": {"$type": "string"},
                }
            },
            {"$sort": {"_id": 1}},
            {
                "$group": {
                    "_id": {
                        "tenant_id": "$tenant_id",
                        "provider_event_id": "$provider_event_id",
                    },
                    "canonical_id": {"$first": "$_id"},
                }
            },
        ],
        allowDiskUse=True,
    )
    operations: list[UpdateOne] = []
    updated = 0

    async def flush() -> None:
        nonlocal updated
        if not operations:
            return
        batch = operations.copy()
        operations.clear()
        await collection.bulk_write(batch, ordered=False)
        updated += len(batch)

    async for group in cursor:
        identity = group.get("_id") or {}
        tenant_id = identity.get("tenant_id")
        provider_event_id = identity.get("provider_event_id")
        canonical_id = group.get("canonical_id")
        if not isinstance(tenant_id, str) or not isinstance(provider_event_id, str) or canonical_id is None:
            continue
        operations.append(
            UpdateOne(
                {"_id": canonical_id},
                {"$set": {"dedup_fence_key": raw_event_fence_key(tenant_id, provider_event_id)}},
            )
        )
        if len(operations) >= RAW_EVENT_BACKFILL_BATCH_SIZE:
            await flush()
    await flush()
    return updated


class ExelyReservationFencingMigration(Migration):
    version = "V011"
    description = "Add Exely event, RoomStay, and processing-lease indexes"

    async def up(self, db) -> None:
        await db.exely_reservation_versions.create_indexes(
            [
                IndexModel(
                    [
                        ("tenant_id", ASCENDING),
                        ("provider", ASCENDING),
                        ("property_id", ASCENDING),
                        ("provider_reservation_id", ASCENDING),
                        ("provider_version_key", ASCENDING),
                    ],
                    unique=True,
                    partialFilterExpression={"property_id": {"$type": "string"}},
                    name="idx_exely_provider_version_unique",
                ),
                IndexModel(
                    [
                        ("processing_state", ASCENDING),
                        ("processing_lease_expires_at", ASCENDING),
                    ],
                    name="idx_exely_processing_lease",
                ),
            ]
        )
        fenced_events = await _backfill_raw_event_fences(db.exely_raw_events)
        logger.info("Exely raw-event fencing backfill completed count=%d", fenced_events)
        await db.exely_raw_events.create_indexes(
            [
                IndexModel(
                    [("dedup_fence_key", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"dedup_fence_key": {"$type": "string"}},
                    name="idx_exely_raw_event_unique",
                )
            ]
        )
        await db.bookings.create_indexes(
            [
                IndexModel(
                    [
                        ("tenant_id", ASCENDING),
                        ("property_id", ASCENDING),
                        ("provider_group_reservation_id", ASCENDING),
                        ("provider_room_stay_slot", ASCENDING),
                    ],
                    unique=True,
                    partialFilterExpression={
                        "source.provider": "exely",
                        "provider_room_stay_slot": {"$type": "int"},
                    },
                    name="idx_exely_room_stay_booking_unique",
                )
            ]
        )

    async def down(self, db) -> None:
        indexes = (
            (db.exely_reservation_versions, "idx_exely_provider_version_unique"),
            (db.exely_reservation_versions, "idx_exely_processing_lease"),
            (db.exely_raw_events, "idx_exely_raw_event_unique"),
            (db.bookings, "idx_exely_room_stay_booking_unique"),
        )
        for collection, index_name in indexes:
            try:
                await collection.drop_index(index_name)
            except pymongo.errors.OperationFailure as exc:
                if exc.code != 27:
                    raise
                logger.warning("Exely fencing index was already absent")


MIGRATION = ExelyReservationFencingMigration()
