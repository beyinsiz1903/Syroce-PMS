import logging

from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)

class InvoiceSyncStatusPollIndexMigration(Migration):
    version = "V004"
    description = "Add status worker polling index for invoice_sync collection"

    async def up(self, db) -> None:
        logger.info("Running V004 migration: adding status worker index to invoice_sync")
        collection = db.invoice_sync

        index_model = IndexModel(
            [
                ("state", ASCENDING),
                ("reconciliation_required", ASCENDING),
                ("next_status_check_at", ASCENDING),
                ("status_lease_expires_at", ASCENDING),
            ],
            name="ix_invoice_sync_status_poll",
            background=True
        )
        await collection.create_indexes([index_model])
        logger.info("Created status worker index ix_invoice_sync_status_poll")

    async def down(self, db) -> None:
        logger.info("Reverting V004 migration: removing status worker index from invoice_sync")
        collection = db.invoice_sync
        try:
            await collection.drop_index("ix_invoice_sync_status_poll")
            logger.info("Dropped status worker index ix_invoice_sync_status_poll")
        except Exception as e:
            logger.warning("Failed to drop status worker index, might not exist: %s", e)

MIGRATION = InvoiceSyncStatusPollIndexMigration()
