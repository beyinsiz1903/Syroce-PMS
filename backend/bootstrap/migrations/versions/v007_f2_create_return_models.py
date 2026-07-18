import logging

import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class F2CreateReturnModelsMigration(Migration):
    version = "V007"
    description = "Add indexes for F2 incoming invoice lines, return balances, and allocations"

    async def up(self, db: AsyncIOMotorDatabase) -> None:
        logger.info(f"Applying migration {self.version}: {self.description}")

        # 1. Indexes for incoming_invoice_lines
        lines_indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("incoming_invoice_id", ASCENDING), ("line_number", ASCENDING)],
                unique=True,
                name="idx_incoming_lines_tenant_invoice_line_num",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("provider_line_id", ASCENDING)],
                name="idx_incoming_lines_tenant_provider_line",
            ),
        ]

        try:
            await db.incoming_invoice_lines.create_indexes(lines_indexes)
            logger.info("Successfully created indexes on incoming_invoice_lines.")
        except pymongo.errors.OperationFailure as e:
            logger.error(f"Failed to create indexes for incoming_invoice_lines in V007: {e}")
            raise

        # 2. Indexes for invoice_return_balances
        balance_indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("source_incoming_invoice_id", ASCENDING), ("source_line_id", ASCENDING)],
                unique=True,
                name="idx_return_balances_tenant_invoice_line_unique",
            )
        ]

        try:
            await db.invoice_return_balances.create_indexes(balance_indexes)
            logger.info("Successfully created unique index on invoice_return_balances.")
        except pymongo.errors.OperationFailure as e:
            logger.error(f"Failed to create indexes for invoice_return_balances in V007: {e}")
            raise

        # 3. Indexes for invoice_return_allocations
        allocation_indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("source_incoming_invoice_id", ASCENDING), ("source_line_id", ASCENDING)],
                name="idx_return_allocations_tenant_invoice_line",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("return_action_id", ASCENDING)],
                name="idx_return_allocations_tenant_action",
            ),
        ]

        try:
            await db.invoice_return_allocations.create_indexes(allocation_indexes)
            logger.info("Successfully created indexes on invoice_return_allocations.")
        except pymongo.errors.OperationFailure as e:
            logger.error(f"Failed to create indexes for invoice_return_allocations in V007: {e}")
            raise

    async def down(self, db: AsyncIOMotorDatabase) -> None:
        logger.info(f"Rolling back migration {self.version}")

        collections_and_indexes = [
            ("incoming_invoice_lines", ["idx_incoming_lines_tenant_invoice_line_num", "idx_incoming_lines_tenant_provider_line"]),
            ("invoice_return_balances", ["idx_return_balances_tenant_invoice_line_unique"]),
            ("invoice_return_allocations", ["idx_return_allocations_tenant_invoice_line", "idx_return_allocations_tenant_action"]),
        ]

        for coll_name, index_names in collections_and_indexes:
            collection = db[coll_name]
            for idx_name in index_names:
                try:
                    await collection.drop_index(idx_name)
                    logger.info(f"Successfully dropped index {idx_name} on {coll_name}.")
                except pymongo.errors.OperationFailure as e:
                    if e.code == 27:  # IndexNotFound
                        logger.warning(f"Index {idx_name} not found on {coll_name}. Skipping drop.")
                    else:
                        logger.error(f"Failed to drop index {idx_name} on {coll_name} in V007: {e}")
                        raise

MIGRATION = F2CreateReturnModelsMigration()
