import logging

from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)

class InvoiceSyncReconciliationIndexMigration(Migration):
    version = "V008"
    description = "Add reconciliation worker polling indexes with tenant_id for multi-tenancy"

    async def up(self, db) -> None:
        logger.info("Running V008 migration: adding multi-tenant reconciliation indexes to invoice_sync")
        collection = db.invoice_sync

        index_model_1 = IndexModel(
            [
                ("tenant_id", ASCENDING),
                ("state", ASCENDING),
                ("next_reconciliation_at", ASCENDING),
                ("status_lease_expires_at", ASCENDING),
            ],
            name="ix_invoice_sync_reconciliation_poll_tenant",
            background=True,
            partialFilterExpression={"state": "RECONCILIATION_REQUIRED"}
        )

        index_model_2 = IndexModel(
            [
                ("tenant_id", ASCENDING),
                ("state", ASCENDING),
                ("redispatch_count", ASCENDING),
            ],
            name="ix_invoice_sync_redispatch_tenant",
            background=True,
            partialFilterExpression={"state": "SAFE_TO_RETRY"}
        )

        await collection.create_indexes([index_model_1, index_model_2])
        logger.info("Created multi-tenant reconciliation worker indexes")

    async def down(self, db) -> None:
        logger.info("Reverting V008 migration: removing reconciliation worker indexes")
        collection = db.invoice_sync

        try:
            await collection.drop_index("ix_invoice_sync_reconciliation_poll_tenant")
            logger.info("Dropped index ix_invoice_sync_reconciliation_poll_tenant")
        except Exception as e:
            logger.warning("Failed to drop index ix_invoice_sync_reconciliation_poll_tenant: %s", e)

        try:
            await collection.drop_index("ix_invoice_sync_redispatch_tenant")
            logger.info("Dropped index ix_invoice_sync_redispatch_tenant")
        except Exception as e:
            logger.warning("Failed to drop index ix_invoice_sync_redispatch_tenant: %s", e)

MIGRATION = InvoiceSyncReconciliationIndexMigration()
