import logging

import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from bootstrap.migrations.base import Migration

logger = logging.getLogger(__name__)


class IncomingInvoiceAnswerAtomicityMigration(Migration):
    version = "V006"
    description = "Add atomic answer guard key index for incoming invoices"

    async def up(self, db: AsyncIOMotorDatabase) -> None:
        logger.info(f"Applying migration {self.version}: {self.description}")

        index = IndexModel(
            [("tenant_id", ASCENDING), ("answer_guard_key", ASCENDING)],
            unique=True,
            name="idx_lifecycle_actions_tenant_answer_guard_unique",
            partialFilterExpression={
                "answer_guard_key": {"$type": "string"},
            },
        )
        try:
            await db.invoice_lifecycle_actions.create_indexes([index])
            logger.info("Successfully created partial unique index on tenant_id + answer_guard_key.")
        except pymongo.errors.OperationFailure as e:
            logger.error(f"Failed to create index in V006: {e}")
            raise

    async def down(self, db: AsyncIOMotorDatabase) -> None:
        logger.info(f"Rolling back migration {self.version}")
        try:
            await db.invoice_lifecycle_actions.drop_index("idx_lifecycle_actions_tenant_answer_guard_unique")
            logger.info("Successfully dropped unique index on tenant_id + answer_guard_key.")
        except pymongo.errors.OperationFailure as e:
            # Code 27 is IndexNotFound
            if e.code == 27:
                logger.warning("Index idx_lifecycle_actions_tenant_answer_guard_unique not found. Skipping drop.")
            else:
                logger.error(f"Failed to drop index in V006: {e}")
                raise

MIGRATION = IncomingInvoiceAnswerAtomicityMigration()
