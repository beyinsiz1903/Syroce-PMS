"""API Routes for Incoming Invoices Lifecycle Operations."""

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from core.helpers import require_admin
from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.invoice_return_service import ReturnQuantityRequest, process_return_request
from models.schemas import User
from models.schemas.incoming_invoice import IncomingInvoiceProfile
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)

router = APIRouter(
    prefix="/api/integrations/incoming-invoices",
    tags=["Integrations", "Incoming Invoices"],
)


class IncomingInvoiceAnswerRequest(BaseModel):
    answer: str  # "APPROVE" or "REJECT"
    note: str | None = None
    request_uuid: str


class InvoiceLifecycleResponse(BaseModel):
    action_id: str
    source_invoice_id: str
    action_type: str
    state: str
    reason: str | None = None
    reconciliation_required: bool = False
    reconciliation_reason: str | None = None
    requested_at: datetime
    succeeded_at: datetime | None = None


@router.post("/{invoice_id}/answer", response_model=InvoiceLifecycleResponse)
async def answer_incoming_invoice(
    invoice_id: str,
    request: IncomingInvoiceAnswerRequest,
    user: User = Depends(require_admin),
) -> InvoiceLifecycleResponse:
    tenant_id = user.tenant_id
    invoice = await IncomingInvoiceRepository.get_by_id(tenant_id, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.profile == IncomingInvoiceProfile.BASIC:
        raise HTTPException(status_code=400, detail="Cannot approve or reject a BASIC (TEMELFATURA) invoice.")

    answer_upper = request.answer.upper()
    if answer_upper not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="Answer must be APPROVE or REJECT.")

    if answer_upper == "REJECT" and not request.note:
        raise HTTPException(status_code=400, detail="A note is required when rejecting an invoice.")

    action_type = InvoiceLifecycleActionType.ACCEPT_INCOMING if answer_upper == "APPROVE" else InvoiceLifecycleActionType.REJECT_INCOMING

    idempotency_key = f"{tenant_id}:{invoice_id}:{action_type.value}:{request.request_uuid}"
    fingerprint_raw = f"{tenant_id}:{invoice_id}:{action_type.value}:{answer_upper}:{request.note or ''}"
    request_fingerprint = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()

    existing_action = await InvoiceLifecycleRepository.get_by_idempotency_key(tenant_id, idempotency_key)
    if existing_action:
        if existing_action.request_fingerprint != request_fingerprint:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: request_uuid used with different payload.")
        return _map_to_response(existing_action)

    # Make sure we don't already have an action for this invoice that has been processed or is processing.
    has_active = await InvoiceLifecycleRepository.has_active_action_for_invoice(tenant_id, invoice_id)
    if has_active:
        raise HTTPException(status_code=409, detail="INVOICE_ALREADY_ANSWERED")

    action_id = str(uuid.uuid4())
    action = InvoiceLifecycleAction(
        id=action_id,
        tenant_id=tenant_id,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id=invoice_id,
        source_provider_uuid=invoice.provider_uuid,
        action_type=action_type,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid=request.request_uuid,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        answer_guard_key=invoice_id,
        reason=request.note,
        requested_by=str(user.id),
        requested_at=datetime.now(UTC),
    )

    created = await InvoiceLifecycleRepository.create_action(action)
    from models.schemas.invoice_lifecycle import ActionCreationResult
    if created == ActionCreationResult.IDEMPOTENCY_CONFLICT:
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: Concurrent creation detected.")
    if created == ActionCreationResult.GUARD_CONFLICT:
        raise HTTPException(status_code=409, detail="INVOICE_ALREADY_ANSWERED: An answer is already being processed for this invoice.")

    return _map_to_response(action)


@router.get("/{invoice_id}/lifecycle", response_model=list[InvoiceLifecycleResponse])
async def get_invoice_lifecycle(invoice_id: str, user: User = Depends(require_admin)) -> list[InvoiceLifecycleResponse]:
    tenant_id = user.tenant_id
    from core.tenant_db import get_db_for_tenant

    db = get_db_for_tenant(tenant_id)
    cursor = db.invoice_lifecycle_actions.find({"tenant_id": tenant_id, "source_invoice_id": invoice_id}).sort("requested_at", -1)
    docs = await cursor.to_list(length=100)

    return [_map_to_response(InvoiceLifecycleAction.model_validate(doc)) for doc in docs]


def _map_to_response(action: InvoiceLifecycleAction) -> InvoiceLifecycleResponse:
    return InvoiceLifecycleResponse(
        action_id=action.id,
        source_invoice_id=action.source_invoice_id,
        action_type=action.action_type.value,
        state=action.state.value,
        reason=action.reason,
        reconciliation_required=action.reconciliation_required,
        reconciliation_reason=action.reconciliation_reason,
        requested_at=action.requested_at,
        succeeded_at=action.completed_at,
    )


class IncomingInvoiceReturnRequest(BaseModel):
    return_type: Literal["FULL", "PARTIAL"]
    lines: list[ReturnQuantityRequest] | None = None
    request_uuid: str


class IncomingInvoiceReturnResponse(BaseModel):
    return_action_id: str | None = None
    source_invoice_id: str
    return_type: str
    allocated_lines_count: int


@router.post("/{invoice_id}/return", response_model=IncomingInvoiceReturnResponse)
async def create_incoming_invoice_return(
    request: Request,
    invoice_id: str,
    payload: IncomingInvoiceReturnRequest,
    x_idempotency_key: str = Header(..., min_length=1),
    user: User = Depends(require_admin),
) -> IncomingInvoiceReturnResponse:
    tenant_id = user.tenant_id

    # 1. Validate UUID format for invoice_id
    try:
        uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid invoice_id format")

    try:
        uuid.UUID(payload.request_uuid)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid request_uuid format")

    # 2. Check incoming invoice existence and tenant match
    invoice = await IncomingInvoiceRepository.get_by_id(tenant_id, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # 3. Payload validation
    if payload.return_type == "PARTIAL":
        if not payload.lines or len(payload.lines) == 0:
            raise HTTPException(status_code=422, detail="PARTIAL return requires lines")

        line_ids = set()
        for line in payload.lines:
            if line.quantity <= Decimal("0"):
                raise HTTPException(status_code=422, detail="Return quantity must be greater than 0")
            if line.source_line_id in line_ids:
                raise HTTPException(status_code=422, detail="Duplicate source_line_id in payload")
            line_ids.add(line.source_line_id)

        # Optional: Validate lines belong to invoice (can be handled by service too, but good to check here)

    # 4. Idempotency Check
    # Normalize payload for fingerprint (simplified)
    lines_str = ""
    if payload.lines:
        sorted_lines = sorted(payload.lines, key=lambda x: x.source_line_id)
        lines_str = ",".join([f"{l.source_line_id}:{l.quantity}" for l in sorted_lines])

    fingerprint_raw = f"{tenant_id}:{invoice_id}:{payload.return_type}:{lines_str}:{payload.request_uuid}"
    request_fingerprint = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()

    # Check if action already exists for this idempotency key
    idemp_key = f"{tenant_id}:return:{x_idempotency_key}"
    existing_action = await InvoiceLifecycleRepository.get_by_idempotency_key(tenant_id, idemp_key)
    if existing_action:
        if existing_action.request_fingerprint != request_fingerprint:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: Key used with different payload")
        # Return existing result
        return IncomingInvoiceReturnResponse(
            return_action_id=existing_action.id,
            source_invoice_id=existing_action.source_invoice_id,
            return_type=payload.return_type,
            allocated_lines_count=0  # Simplified for mock replay
        )

    # 5. Fail-Closed Option A: Provider Contract Not Verified
    # Do not create allocation or action yet.
    raise HTTPException(
        status_code=503,
        detail={
            "code": "PROVIDER_CONTRACT_NOT_VERIFIED",
            "detail": "CreateReturn provider contract is not verified."
        }
    )

    # --- Unreachable code below (Reserved for when contract is verified) ---
    action_id = str(uuid.uuid4())

    try:
        allocations = await process_return_request(
            tenant_id=tenant_id,
            incoming_invoice_id=invoice_id,
            action_id=action_id,
            return_type=payload.return_type,
            partial_requests=payload.lines
        )
    except Exception as e:
        from core.integrations.invoice_return_repository import CASFailedError, PreconditionFailedError
        from core.integrations.invoice_return_service import ReturnValidationError

        if isinstance(e, ReturnValidationError):
            raise HTTPException(status_code=400, detail=str(e))
        elif isinstance(e, CASFailedError):
            raise HTTPException(status_code=409, detail=f"CAS Conflict: {str(e)}")
        elif isinstance(e, PreconditionFailedError):
            raise HTTPException(status_code=412, detail=f"Precondition Failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error processing return")

    return IncomingInvoiceReturnResponse(
        return_action_id=action_id,
        source_invoice_id=invoice_id,
        return_type=payload.return_type,
        allocated_lines_count=len(allocations)
    )
