import logging

import pymongo.errors
from pymongo import ASCENDING, DESCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class IncomingInvoiceSyncMigration(Migration):
    version = "V009"
    description = "Add incoming invoice read and periodic sync indexes"

    async def up(self, db) -> None:
        await db.incoming_invoices.create_index(
            [("tenant_id", ASCENDING), ("issue_date", DESCENDING), ("id", ASCENDING)],
            name="idx_incoming_invoices_tenant_issue_date",
        )
        await db.incoming_invoice_sync_state.create_indexes(
            [
                IndexModel(
                    [("tenant_id", ASCENDING), ("provider", ASCENDING)],
                    unique=True,
                    name="idx_incoming_sync_state_tenant_provider_unique",
                ),
                IndexModel(
                    [
                        ("tenant_id", ASCENDING),
                        ("provider", ASCENDING),
                        ("next_sync_at", ASCENDING),
                        ("lease_expires_at", ASCENDING),
                    ],
                    name="idx_incoming_sync_state_due",
                ),
            ]
        )

    async def down(self, db) -> None:
        indexes = (
            (db.incoming_invoices, "idx_incoming_invoices_tenant_issue_date"),
            (
                db.incoming_invoice_sync_state,
                "idx_incoming_sync_state_tenant_provider_unique",
            ),
            (db.incoming_invoice_sync_state, "idx_incoming_sync_state_due"),
        )
        for collection, index_name in indexes:
            try:
                await collection.drop_index(index_name)
            except pymongo.errors.OperationFailure as exc:
                if exc.code != 27:
                    raise
                logger.warning("Incoming invoice sync index was already absent")


MIGRATION = IncomingInvoiceSyncMigration()
