"""Repository for managing invoice_sync status polling and reconciliation."""

from datetime import UTC, datetime

from pymongo import ReturnDocument

from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState


class InvoiceStatusRepository:
    """Repository for managing invoice_sync status polling securely."""

    @staticmethod
    async def claim_status_lease(
        tenant_id: str,
        dispatch_id: str,
        worker_id: str,
        lease_duration_sec: int,
    ) -> InvoiceSync | None:
        """
        Atomically claims a record for status polling.
        Only records in SUBMITTED state and NOT requiring reconciliation can be claimed.
        """
        db = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)
        expires_at = datetime.fromtimestamp(now.timestamp() + lease_duration_sec, tz=UTC)

        result = await db.invoice_sync.find_one_and_update(
            {
                "id": dispatch_id,
                "tenant_id": tenant_id,
                "state": InvoiceSyncState.SUBMITTED.value,
                "reconciliation_required": {"$ne": True},
                "$or": [
                    {"status_lease_owner": None},
                    {"status_lease_expires_at": {"$lte": now}}
                ]
            },
            {
                "$set": {
                    "status_lease_owner": worker_id,
                    "status_lease_expires_at": expires_at,
                    "updated_at": now
                },
                "$inc": {"version": 1}
            },
            return_document=ReturnDocument.AFTER
        )
        if not result:
            return None
        return InvoiceSync.model_validate(result)

    @staticmethod
    async def update_status_poll_result(
        tenant_id: str,
        dispatch_id: str,
        worker_id: str,
        update_fields: dict,
    ) -> bool:
        """
        Atomically updates the polling result if the worker still holds the lease.
        Also clears the lease.
        """
        db = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)

        updates = update_fields.copy()
        updates["status_lease_owner"] = None
        updates["status_lease_expires_at"] = None
        updates["updated_at"] = now

        result = await db.invoice_sync.update_one(
            {
                "id": dispatch_id,
                "tenant_id": tenant_id,
                "status_lease_owner": worker_id,
                "status_lease_expires_at": {"$gt": now}
            },
            {
                "$set": updates,
                "$inc": {"version": 1}
            }
        )
        return result.modified_count > 0

    @staticmethod
    async def reconcile_status(
        tenant_id: str,
        dispatch_id: str,
        target_state: InvoiceSyncState,
        note: str,
        actor: str,
    ) -> bool:
        """
        Atomically applies manual reconciliation logic.
        Updates state, clears reconciliation flag, sets note and actor.
        """
        db = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)

        result = await db.invoice_sync.update_one(
            {
                "id": dispatch_id,
                "tenant_id": tenant_id,
            },
            {
                "$set": {
                    "state": target_state.value,
                    "reconciliation_required": False,
                    "reconciled_at": now,
                    "reconciled_by": actor,
                    "reconciliation_note": note,
                    "updated_at": now,
                    # Clear leases to be safe
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "status_lease_owner": None,
                    "status_lease_expires_at": None,
                },
                "$inc": {"version": 1}
            }
        )
        return result.modified_count > 0
