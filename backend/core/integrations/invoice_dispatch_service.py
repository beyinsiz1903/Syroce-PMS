import uuid
from datetime import UTC, datetime

from core.integrations.dispatch import generate_idempotency_key
from core.integrations.errors import IntegrationNotFoundError, IntegrationValidationError
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState, PrepareDispatchResult


class InvoiceDispatchService:

    @staticmethod
    async def prepare_dispatch(
        *,
        tenant_id: str,
        invoice_id: str,
        provider: InvoiceProvider,
        document_kind: InvoiceDocumentKind
    ) -> PrepareDispatchResult:
        if document_kind != InvoiceDocumentKind.E_INVOICE:
            raise IntegrationValidationError(
                f"Unsupported document kind: {document_kind}",
            )

        db = get_db_for_tenant(tenant_id)
        invoice = await db.invoices.find_one({"id": invoice_id, "tenant_id": tenant_id})

        if not invoice:
            raise IntegrationNotFoundError(
                "Invoice not found",
            )

        if invoice.get("invoice_type") != "SATIS":
            raise IntegrationValidationError(
                "Only SATIS invoices are supported for dispatch.",
            )

        idempotency_key = generate_idempotency_key(tenant_id, invoice_id, provider, document_kind)
        new_uuid = uuid.uuid4()
        now = datetime.now(UTC)

        sync_model = InvoiceSync(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            provider=provider,
            document_kind=document_kind,
            idempotency_key=idempotency_key,
            request_uuid=str(new_uuid),
            state=InvoiceSyncState.PREPARED,
            prepared_at=now,
            created_at=now,
            updated_at=now,
        )

        persisted_model, created = await InvoiceSyncRepository.create_prepared(tenant_id, sync_model)

        return PrepareDispatchResult(
            dispatch_id=persisted_model.id,
            request_uuid=uuid.UUID(persisted_model.request_uuid),
            idempotency_key=persisted_model.idempotency_key,
            created=created
        )
