import uuid
from datetime import UTC, datetime

from core.integrations.dispatch import generate_idempotency_key
from core.integrations.errors import IntegrationNotFoundError, IntegrationValidationError
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraApiError, NilveraServerError, NilveraTimeoutError
from core.integrations.nilvera.mapper import NilveraInvoiceMapper, SellerSnapshot
from core.integrations.nilvera.provisioner import get_nilvera_tenant_config
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import (
    DispatchErrorCategory,
    InvoiceDocumentKind,
    InvoiceProvider,
    InvoiceSync,
    InvoiceSyncState,
    PrepareDispatchResult,
)
from models.schemas.invoicing import Invoice


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

    @staticmethod
    async def execute_dispatch(tenant_id: str, dispatch_id: str, worker_id: str | None = None) -> bool:
        """Executes the HTTP dispatch for a sync record that is currently in SENDING state.

        Returns True if successful, False if it failed.
        State transitions (SUBMITTED, RETRYABLE_ERROR, PERMANENT_ERROR) are handled internally.
        """
        db = get_db_for_tenant(tenant_id)

        # 1. Fetch the sync record
        sync_doc = await db.invoice_sync.find_one({"id": dispatch_id, "tenant_id": tenant_id})
        if not sync_doc:
            raise IntegrationNotFoundError(f"Invoice sync record {dispatch_id} not found")

        sync_model = InvoiceSync(**sync_doc)
        if sync_model.state != InvoiceSyncState.SENDING:
            raise IntegrationValidationError(f"Expected state SENDING, got {sync_model.state}")

        async def _transition(target_state: InvoiceSyncState, update_fields: dict, inc_fields: dict | None = None) -> bool:
            success = await InvoiceSyncRepository.transition_state(
                tenant_id,
                dispatch_id,
                current_state=InvoiceSyncState.SENDING,
                target_state=target_state,
                update_fields=update_fields,
                inc_fields=inc_fields,
                expected_version=sync_model.version if worker_id else None,
                lease_owner_id=worker_id
            )
            if success and worker_id:
                sync_model.version += 1
            return success

        # 2. Fetch the Nilvera config
        nilvera_cfg = await get_nilvera_tenant_config(tenant_id, decrypt_api_key=True)
        if not nilvera_cfg.get("enabled") or not nilvera_cfg.get("api_key"):
            from datetime import timedelta
            await _transition(
                target_state=InvoiceSyncState.RETRYABLE_ERROR,
                update_fields={
                    "last_error_message": "Nilvera integration is not enabled or API key is missing. Check tenant_settings.",
                    "last_error_category": DispatchErrorCategory.AUTHENTICATION,
                    "last_error_retryable": True,
                    "next_retry_at": datetime.now(UTC) + timedelta(hours=12),
                }
            )
            return False

        api_key = nilvera_cfg["api_key"]

        # 3. Fetch the invoice
        invoice_doc = await db.invoices.find_one({"id": sync_model.invoice_id, "tenant_id": tenant_id})
        if not invoice_doc:
            await _transition(
                target_state=InvoiceSyncState.PERMANENT_ERROR,
                update_fields={
                    "last_error_message": "Source invoice not found in database",
                    "last_error_category": DispatchErrorCategory.NOT_FOUND,
                    "last_error_retryable": False,
                }
            )
            return False

        invoice = Invoice(**invoice_doc)

        seller_info = nilvera_cfg.get("seller", {})
        if not seller_info.get("vkn") or not seller_info.get("name") or not seller_info.get("tax_office") or not seller_info.get("address") or not seller_info.get("city") or not seller_info.get("country"):
            await _transition(
                target_state=InvoiceSyncState.PERMANENT_ERROR,
                update_fields={
                    "last_error_message": "Tenant company info (VKN, Name, Tax Office, Address, City, Country) is incomplete. Cannot dispatch.",
                    "last_error_category": DispatchErrorCategory.VALIDATION,
                    "last_error_retryable": False,
                }
            )
            return False

        seller = SellerSnapshot(
            tax_number=seller_info["vkn"],
            name=seller_info["name"],
            tax_office=seller_info["tax_office"],
            country=seller_info["country"],
            city=seller_info["city"],
            address=seller_info["address"],
        )

        customer_alias = getattr(invoice, "buyer_alias", None)
        if sync_model.document_kind == InvoiceDocumentKind.E_INVOICE and not customer_alias:
            await _transition(
                target_state=InvoiceSyncState.PERMANENT_ERROR,
                update_fields={
                    "last_error_message": "Customer alias is required for E-Invoice but missing from invoice snapshot.",
                    "last_error_category": DispatchErrorCategory.VALIDATION,
                    "last_error_retryable": False,
                }
            )
            return False

        try:
            payload = NilveraInvoiceMapper.map_to_nilvera(
                invoice=invoice,
                seller=seller,
                customer_alias=customer_alias,
                request_uuid=uuid.UUID(sync_model.request_uuid)
            )
        except Exception as e:
            await _transition(
                target_state=InvoiceSyncState.PERMANENT_ERROR,
                update_fields={
                    "last_error_message": f"Mapping error: {str(e)[:500]}",
                    "last_error_category": DispatchErrorCategory.VALIDATION,
                    "last_error_retryable": False,
                }
            )
            return False

        # Increment attempt_count before external API call
        sync_model.attempt_count += 1

        lease_ok = await _transition(
            target_state=InvoiceSyncState.SENDING,
            update_fields={},
            inc_fields={"attempt_count": 1}
        )
        if worker_id and not lease_ok:
            return False

        # 6. HTTP POST
        try:
            async with NilveraHttpClient(api_key=api_key) as client:
                payload_dict = payload.model_dump(by_alias=True, exclude_none=True)

                from core.integrations.nilvera.config import NilveraEndpoints
                response_data = await client.post(
                    NilveraEndpoints.SEND_INVOICE_MODEL,
                    json=payload_dict,
                    correlation_id=sync_model.request_uuid,
                    retryable=False
                )

                if not isinstance(response_data, dict):
                     raise NilveraApiError(
                         message="Invalid provider response type: expected object",
                         http_status=200,
                         provider_code="INVALID_RESPONSE_TYPE",
                         retryable=False
                     )

                provider_doc_id = response_data.get("UUID")

                if not provider_doc_id:
                     raise NilveraApiError(
                         message="Provider returned a successful response without a document UUID",
                         http_status=200,
                         provider_code="MISSING_UUID",
                         retryable=False
                     )

                await _transition(
                    target_state=InvoiceSyncState.SUBMITTED,
                    update_fields={
                        "provider_document_id": str(provider_doc_id),
                        "submitted_at": datetime.now(UTC),
                        "last_error_message": None,
                        "last_error_category": None,
                    }
                )
                return True

        except NilveraApiError as e:
            error_msg = getattr(e, "sanitized_detail", None) or getattr(e, "sanitized_description", None) or e.message
            provider_code = getattr(e, "provider_code", None)

            update_fields = {
                "last_error_message": str(error_msg)[:500],
                "last_error_code": provider_code,
                "last_error_retryable": False,
            }

            target_state = InvoiceSyncState.PERMANENT_ERROR

            if e.http_status in (401, 403):
                target_state = InvoiceSyncState.CONFIGURATION_ERROR
                update_fields["last_error_category"] = DispatchErrorCategory.AUTHENTICATION
            elif e.http_status == 409:
                if provider_code in ("1001", "1004", "1005", "1015"):
                    target_state = InvoiceSyncState.RECONCILIATION_REQUIRED
                    update_fields["reconciliation_required"] = True
                    update_fields["reconciliation_reason"] = f"DUPLICATE_{provider_code}"
                elif provider_code in ("1000", "1002"):
                    target_state = InvoiceSyncState.PERMANENT_ERROR
                    update_fields["last_error_category"] = DispatchErrorCategory.BUSINESS_RULE
                else:
                    target_state = InvoiceSyncState.RECONCILIATION_REQUIRED
                    update_fields["reconciliation_required"] = True
                    update_fields["reconciliation_reason"] = f"UNKNOWN_409_{provider_code or 'NOCODE'}"
            elif e.http_status in (429, 502, 503, 504) or (e.http_status is not None and e.http_status >= 500) or isinstance(e, (NilveraTimeoutError, NilveraServerError)):
                target_state = InvoiceSyncState.RECONCILIATION_REQUIRED
                update_fields["reconciliation_required"] = True
                update_fields["reconciliation_reason"] = f"AMBIGUOUS_{e.http_status or 'TIMEOUT'}"
            else:
                target_state = InvoiceSyncState.PERMANENT_ERROR
                update_fields["last_error_category"] = DispatchErrorCategory.VALIDATION

            if provider_code in ("INVALID_RESPONSE_TYPE", "MISSING_UUID"):
                update_fields["last_error_category"] = DispatchErrorCategory.INVALID_PROVIDER_RESPONSE

            await _transition(
                target_state=target_state,
                update_fields=update_fields
            )
            return False
        except Exception as e:
            # Fallback for unexpected errors (Network, parsing, etc)
            await _transition(
                target_state=InvoiceSyncState.RECONCILIATION_REQUIRED,
                update_fields={
                    "last_error_message": f"Unexpected error: {str(e)[:500]}",
                    "last_error_category": DispatchErrorCategory.UNKNOWN,
                    "last_error_retryable": False,
                    "reconciliation_required": True,
                    "reconciliation_reason": "UNEXPECTED_EXCEPTION",
                }
            )
            return False
