from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_lifecycle import InvoiceLifecycleAction, InvoiceLifecycleActionState


class InvoiceLifecycleRepository:
    """Repository for managing invoice lifecycle actions."""

    @staticmethod
    async def create_action(action: InvoiceLifecycleAction) -> bool:
        """
        Creates a new lifecycle action. Returns True if successfully inserted,
        False if an action with the same idempotency key already exists.
        """
        db: AsyncIOMotorDatabase = get_db_for_tenant(action.tenant_id)
        doc = action.model_dump(by_alias=True)
        try:
            await db.invoice_lifecycle_actions.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    @staticmethod
    async def get_by_id(tenant_id: str, action_id: str) -> InvoiceLifecycleAction | None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        doc = await db.invoice_lifecycle_actions.find_one({"id": action_id, "tenant_id": tenant_id})
        if not doc:
            return None
        return InvoiceLifecycleAction.model_validate(doc)

    @staticmethod
    async def get_by_idempotency_key(tenant_id: str, idempotency_key: str) -> InvoiceLifecycleAction | None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        doc = await db.invoice_lifecycle_actions.find_one({"idempotency_key": idempotency_key, "tenant_id": tenant_id})
        if not doc:
            return None
        return InvoiceLifecycleAction.model_validate(doc)

    @staticmethod
    async def has_active_action_for_invoice(tenant_id: str, invoice_id: str) -> bool:
        from models.schemas.invoice_lifecycle import InvoiceLifecycleActionType
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        count = await db.invoice_lifecycle_actions.count_documents({
            "tenant_id": tenant_id,
            "source_invoice_id": invoice_id,
            "action_type": {"$in": [InvoiceLifecycleActionType.ACCEPT_INCOMING.value, InvoiceLifecycleActionType.REJECT_INCOMING.value]},
            "state": {"$in": [
                InvoiceLifecycleActionState.REQUESTED.value,
                InvoiceLifecycleActionState.PROCESSING.value,
                InvoiceLifecycleActionState.RETRY_SCHEDULED.value,
                InvoiceLifecycleActionState.SUCCEEDED.value,
                InvoiceLifecycleActionState.RECONCILIATION_REQUIRED.value
            ]}
        })
        return count > 0

    @staticmethod
    async def claim_action_lease(tenant_id: str, action_id: str, worker_id: str, lease_duration_sec: int) -> InvoiceLifecycleAction | None:
        """
        Atomically claims a lifecycle action for processing.
        """
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)
        from datetime import timedelta
        expires_at = now + timedelta(seconds=lease_duration_sec) if lease_duration_sec > 0 else now

        doc = await db.invoice_lifecycle_actions.find_one_and_update(
            {
                "id": action_id,
                "tenant_id": tenant_id,
                "$or": [
                    {"lifecycle_lease_owner": None},
                    {"lifecycle_lease_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "lifecycle_lease_owner": worker_id,
                    "lifecycle_lease_expires_at": expires_at,
                    "state": InvoiceLifecycleActionState.PROCESSING.value,
                }
            },
            return_document=True,
        )
        if not doc:
            return None
        return InvoiceLifecycleAction.model_validate(doc)

    @staticmethod
    async def update_action_result(tenant_id: str, action_id: str, worker_id: str, update_fields: dict) -> bool:
        """
        Updates the result of a processed action and releases the lease.
        Only succeeds if the worker still owns the lease.
        """
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)

        # Clean the lease
        update_fields["lifecycle_lease_owner"] = None
        update_fields["lifecycle_lease_expires_at"] = None

        result = await db.invoice_lifecycle_actions.update_one({"id": action_id, "tenant_id": tenant_id, "lifecycle_lease_owner": worker_id}, {"$set": update_fields})
        return result.modified_count > 0
