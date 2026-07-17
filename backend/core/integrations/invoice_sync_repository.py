from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.integrations.errors import IntegrationConflictError
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceSync, InvoiceSyncState


class InvoiceSyncRepository:
    """Repository for managing invoice_sync documents securely."""

    @staticmethod
    async def find_by_business_key(tenant_id: str, invoice_id: str, provider: str, document_kind: str) -> InvoiceSync | None:
        db = get_db_for_tenant(tenant_id)
        doc = await db.invoice_sync.find_one({
            "tenant_id": tenant_id,
            "invoice_id": invoice_id,
            "provider": provider,
            "document_kind": document_kind
        })
        if not doc:
            return None
        return InvoiceSync.model_validate(doc)

    @staticmethod
    async def create_prepared(tenant_id: str, sync_model: InvoiceSync) -> tuple[InvoiceSync, bool]:
        """
        Attempts to insert the given sync_model.
        Returns (model, True) if inserted.
        If a duplicate exists, fetches the existing document and returns (existing_model, False).
        Raises IntegrationConflictError if the collision is on a different key.
        """
        db = get_db_for_tenant(tenant_id)
        doc_dict = sync_model.model_dump(by_alias=True, exclude_none=True)

        try:
            await db.invoice_sync.insert_one(doc_dict)
            return sync_model, True
        except DuplicateKeyError as exc:
            # Check if it was our primary business key
            existing = await InvoiceSyncRepository.find_by_business_key(
                tenant_id,
                sync_model.invoice_id,
                sync_model.provider.value,
                sync_model.document_kind.value
            )
            if existing:
                return existing, False

            # If we collided on UUID or idempotency key from a different invoice/tenant context
            raise IntegrationConflictError(
                "A conflicting dispatch record already exists with a different business key.",
                provider_code="DUPLICATE_KEY",
            ) from exc

    @staticmethod
    async def compare_and_set_state(
        tenant_id: str,
        dispatch_id: str,
        expected_state: InvoiceSyncState,
        expected_version: int,
        target_state: InvoiceSyncState,
        update_fields: dict
    ) -> InvoiceSync | None:
        """
        Atomically transition the state if expected_state and expected_version match.
        Returns the updated document, or None if the condition was not met (conflict or not found).
        """
        db = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)

        updates = update_fields.copy()
        updates["state"] = target_state.value
        updates["updated_at"] = now

        result = await db.invoice_sync.find_one_and_update(
            {
                "id": dispatch_id,
                "tenant_id": tenant_id,
                "state": expected_state.value,
                "version": expected_version
            },
            {
                "$set": updates,
                "$inc": {"version": 1}
            },
            return_document=ReturnDocument.AFTER
        )
        if not result:
            return None
        return InvoiceSync.model_validate(result)

    @staticmethod
    async def get_by_id(tenant_id: str, dispatch_id: str) -> InvoiceSync | None:
        db = get_db_for_tenant(tenant_id)
        doc = await db.invoice_sync.find_one({"id": dispatch_id, "tenant_id": tenant_id})
        if not doc:
            return None
        return InvoiceSync.model_validate(doc)
