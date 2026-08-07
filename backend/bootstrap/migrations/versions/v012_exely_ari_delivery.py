"""Create durable Exely ARI delivery indexes."""

import logging

import pymongo.errors
from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class ExelyARIDeliveryMigration(Migration):
    version = "V012"
    description = "Add unique Exely ARI operation and reconciliation indexes"

    async def up(self, db) -> None:
        await db.exely_ari_deliveries.create_indexes(
            [
                IndexModel(
                    [("operation_identity", ASCENDING)],
                    unique=True,
                    name="uq_exely_ari_operation_identity",
                ),
                IndexModel(
                    [("active_fingerprint", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"active_fingerprint": {"$type": "string"}},
                    name="uq_exely_ari_unconfirmed_fingerprint",
                ),
                IndexModel(
                    [("tenant_id", ASCENDING), ("state", ASCENDING), ("created_at", ASCENDING)],
                    name="ix_exely_ari_reconciliation",
                ),
            ]
        )

    async def down(self, db) -> None:
        for index_name in (
            "ix_exely_ari_reconciliation",
            "uq_exely_ari_unconfirmed_fingerprint",
            "uq_exely_ari_operation_identity",
        ):
            try:
                await db.exely_ari_deliveries.drop_index(index_name)
            except pymongo.errors.OperationFailure as exc:
                if exc.code != 27:
                    raise
                logger.warning("Exely ARI index was already absent")


MIGRATION = ExelyARIDeliveryMigration()
