"""Indexes required by the durable Exely reservation lifecycle."""

import logging

import pymongo.errors
from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class ExelyReservationLifecycleMigration(Migration):
    version = "V010"
    description = "Add Exely reservation version, current identity, and lifecycle indexes"

    async def up(self, db) -> None:
        await db.exely_reservation_versions.create_indexes(
            [
                IndexModel(
                    [("version_identity", ASCENDING)],
                    unique=True,
                    name="idx_exely_version_identity_unique",
                ),
                IndexModel(
                    [
                        ("tenant_id", ASCENDING),
                        ("processing_state", ASCENDING),
                        ("ack_state", ASCENDING),
                    ],
                    name="idx_exely_version_lifecycle",
                ),
            ]
        )
        await db.exely_reservations.create_indexes(
            [
                IndexModel(
                    [
                        ("tenant_id", ASCENDING),
                        ("property_id", ASCENDING),
                        ("external_id", ASCENDING),
                    ],
                    unique=True,
                    partialFilterExpression={"property_id": {"$type": "string"}},
                    name="idx_exely_current_identity_unique",
                ),
                IndexModel(
                    [("tenant_id", ASCENDING), ("pms_status", ASCENDING), ("delivery_state", ASCENDING)],
                    name="idx_exely_current_lifecycle",
                ),
            ]
        )

    async def down(self, db) -> None:
        indexes = (
            (db.exely_reservation_versions, "idx_exely_version_identity_unique"),
            (db.exely_reservation_versions, "idx_exely_version_lifecycle"),
            (db.exely_reservations, "idx_exely_current_identity_unique"),
            (db.exely_reservations, "idx_exely_current_lifecycle"),
        )
        for collection, index_name in indexes:
            try:
                await collection.drop_index(index_name)
            except pymongo.errors.OperationFailure as exc:
                if exc.code != 27:
                    raise
                logger.warning("Exely lifecycle index was already absent")


MIGRATION = ExelyReservationLifecycleMigration()
