"""Indexes required by Exely reservation claims and duplicate fencing."""

import logging

import pymongo.errors
from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


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
        await db.exely_raw_events.create_indexes(
            [
                IndexModel(
                    [("tenant_id", ASCENDING), ("provider_event_id", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"provider_event_id": {"$type": "string"}},
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
