import logging

from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)

class InvoiceSyncWorkerIndexMigration(Migration):
    version = "V003"
    description = "Add worker polling index for invoice_sync collection"

    async def up(self, db) -> None:
        logger.info("Running V003 migration: adding worker index to invoice_sync")
        collection = db.invoice_sync

        index_model = IndexModel(
            [("state", ASCENDING), ("next_retry_at", ASCENDING), ("lease_expires_at", ASCENDING)],
            name="ix_invoice_sync_worker_poll",
            background=True
        )
        await collection.create_indexes([index_model])
        logger.info("Created worker index ix_invoice_sync_worker_poll")

    async def down(self, db) -> None:
        logger.info("Reverting V003 migration: removing worker index from invoice_sync")
        collection = db.invoice_sync
        try:
            await collection.drop_index("ix_invoice_sync_worker_poll")
            logger.info("Dropped worker index ix_invoice_sync_worker_poll")
        except Exception as e:
            logger.warning("Failed to drop worker index, might not exist: %s", e)

MIGRATION = InvoiceSyncWorkerIndexMigration()
