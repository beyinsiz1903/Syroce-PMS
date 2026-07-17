import logging

from pymongo import ASCENDING, IndexModel
import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorDatabase

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class IncomingInvoiceLifecycleMigration(Migration):
    version = "V005"
    description = "Add indexes for incoming invoices and lifecycle actions"

    async def up(self, db: AsyncIOMotorDatabase) -> None:
        logger.info("Running V005 migration: adding indexes for incoming invoices")

        # 1. Incoming Invoices Collections and Indexes
        await db.incoming_invoices.create_indexes([
            IndexModel([("id", ASCENDING)], unique=True, name="idx_incoming_invoices_id_unique"),
            IndexModel([("tenant_id", ASCENDING), ("provider_uuid", ASCENDING)], unique=True, name="idx_incoming_invoices_tenant_provider_uuid_unique")
        ])

        # 2. Lifecycle Actions Collections and Indexes
        await db.invoice_lifecycle_actions.create_indexes([
            IndexModel([("tenant_id", ASCENDING), ("idempotency_key", ASCENDING)], unique=True, name="idx_lifecycle_actions_tenant_idemp_key_unique"),
            IndexModel([
                ("state", ASCENDING),
                ("next_attempt_at", ASCENDING),
                ("lifecycle_lease_expires_at", ASCENDING),
            ], name="idx_lifecycle_actions_worker_poll"),
            IndexModel([
                ("tenant_id", ASCENDING),
                ("source_invoice_id", ASCENDING),
                ("requested_at", pymongo.DESCENDING),
            ], name="idx_lifecycle_actions_tenant_source_req_at")
        ])

    async def down(self, db: AsyncIOMotorDatabase) -> None:
        logger.info("Reverting V005 migration: dropping incoming invoice indexes")
        for idx in ["idx_incoming_invoices_id_unique", "idx_incoming_invoices_tenant_provider_uuid_unique"]:
            try:
                await db.incoming_invoices.drop_index(idx)
            except pymongo.errors.OperationFailure:
                pass

        for idx in ["idx_lifecycle_actions_tenant_idemp_key_unique", "idx_lifecycle_actions_worker_poll", "idx_lifecycle_actions_tenant_source_req_at"]:
            try:
                await db.invoice_lifecycle_actions.drop_index(idx)
            except pymongo.errors.OperationFailure:
                pass


MIGRATION = IncomingInvoiceLifecycleMigration()
