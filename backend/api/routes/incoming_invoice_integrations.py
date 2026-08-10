"""API Routes for Incoming Invoices Lifecycle Operations."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from core.helpers import require_admin
from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncService
from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.invoice_return_service import ReturnQuantityRequest
from core.integrations.nilvera.config import is_nilvera_incoming_answer_enabled
from core.integrations.nilvera.errors import NilveraApiError
from models.schemas import User
from models.schemas.incoming_invoice import (
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceLine,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
    IncomingTaxDetail,
)
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
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
    answer: Literal["APPROVE", "REJECT"]
    note: str | None = Field(default=None, max_length=1000)
    request_uuid: uuid.UUID

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_answer(cls, value):
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_note(self):
        if self.note is not None:
            self.note = self.note.strip() or None
        if self.answer == "REJECT" and self.note is None:
            raise ValueError("A note is required when rejecting an invoice")
        if self.answer == "APPROVE" and self.note is not None:
            raise ValueError("A note is not allowed when approving an invoice")
        return self


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


class IncomingInvoiceResponse(BaseModel):
    id: str
    provider_uuid: str
    invoice_number: str
    sender_vkn_tckn: str
    sender_title: str
    profile: IncomingInvoiceProfile
    answer_status: IncomingInvoiceAnswerStatus
    provider_status: IncomingInvoiceProviderStatus
    provider_gib_code: str | None
    issue_date: datetime
    issue_date_timezone_assumed: bool
    received_at: datetime
    payable_amount: Decimal | None
    currency: str | None
    updated_at: datetime


class IncomingInvoiceListResponse(BaseModel):
    items: list[IncomingInvoiceResponse]
    total: int
    offset: int
    limit: int


class IncomingInvoiceLineResponse(BaseModel):
    id: str
    provider_line_id: str | None
    line_number: int
    name: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    discount_amount: Decimal
    line_extension_amount: Decimal
    kdv_rate: Decimal
    kdv_amount: Decimal
    other_taxes: list[IncomingTaxDetail]
    currency: str


class IncomingInvoiceDetailResponse(IncomingInvoiceResponse):
    lines: list[IncomingInvoiceLineResponse]


class IncomingInvoiceSyncRequest(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date is not None and self.start_date.tzinfo is None:
            raise ValueError("start_date must be timezone-aware")
        if self.end_date is not None and self.end_date.tzinfo is None:
            raise ValueError("end_date must be timezone-aware")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("start_date cannot be after end_date")
            if self.end_date - self.start_date > timedelta(days=31):
                raise ValueError("Date range cannot exceed 31 days")
        return self


class IncomingInvoiceSyncResponse(BaseModel):
    invoices_seen: int = Field(ge=0)
    invoices_created: int = Field(ge=0)
    invoices_changed: int = Field(ge=0)
    lines_created: int = Field(ge=0)
    lines_changed: int = Field(ge=0)
    lines_deactivated: int = Field(ge=0)
    unknown_invoices: int = Field(ge=0)
    pending_invoices: int = Field(ge=0)
    provider_error_invoices: int = Field(ge=0)


def _invoice_response(invoice) -> IncomingInvoiceResponse:
    return IncomingInvoiceResponse(
        id=invoice.id,
        provider_uuid=invoice.provider_uuid,
        invoice_number=invoice.invoice_number,
        sender_vkn_tckn=invoice.sender_vkn_tckn,
        sender_title=invoice.sender_title,
        profile=invoice.profile,
        answer_status=invoice.answer_status,
        provider_status=invoice.provider_status,
        provider_gib_code=invoice.provider_gib_code,
        issue_date=invoice.issue_date,
        issue_date_timezone_assumed=invoice.issue_date_timezone_assumed,
        received_at=invoice.received_at,
        payable_amount=invoice.payable_amount,
        currency=invoice.currency,
        updated_at=invoice.updated_at,
    )


def _line_response(line: IncomingInvoiceLine) -> IncomingInvoiceLineResponse:
    return IncomingInvoiceLineResponse(
        id=line.id,
        provider_line_id=line.provider_line_id,
        line_number=line.line_number,
        name=line.name,
        quantity=line.quantity,
        unit_code=line.unit_code,
        unit_price=line.unit_price,
        discount_amount=line.discount_amount,
        line_extension_amount=line.line_extension_amount,
        kdv_rate=line.kdv_rate,
        kdv_amount=line.kdv_amount,
        other_taxes=line.other_taxes,
        currency=line.currency,
    )


@router.get("", response_model=IncomingInvoiceListResponse)
async def list_incoming_invoices(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    profile: IncomingInvoiceProfile | None = None,
    answer_status: IncomingInvoiceAnswerStatus | None = None,
    provider_status: IncomingInvoiceProviderStatus | None = None,
    user: User = Depends(require_admin),
) -> IncomingInvoiceListResponse:
    invoices, total = await IncomingInvoiceRepository.list_invoices(
        user.tenant_id,
        offset=offset,
        limit=limit,
        profile=profile,
        answer_status=answer_status,
        provider_status=provider_status,
    )
    return IncomingInvoiceListResponse(
        items=[_invoice_response(invoice) for invoice in invoices],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/sync", response_model=IncomingInvoiceSyncResponse)
async def sync_incoming_invoices(
    payload: IncomingInvoiceSyncRequest,
    user: User = Depends(require_admin),
) -> IncomingInvoiceSyncResponse:
    end_date = payload.end_date or datetime.now(UTC)
    start_date = payload.start_date or end_date - timedelta(days=31)
    if start_date > end_date or end_date - start_date > timedelta(days=31):
        raise HTTPException(status_code=422, detail="Invalid incoming invoice sync date range")
    try:
        result = await IncomingInvoiceSyncService.sync_tenant(
            user.tenant_id,
            start_date,
            end_date,
        )
    except NilveraApiError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.safe_code, "detail": exc.safe_user_message},
        ) from None
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NILVERA_INCOMING_SYNC_UNAVAILABLE",
                "detail": "Incoming invoice synchronization is unavailable.",
            },
        ) from None
    return IncomingInvoiceSyncResponse(**result.__dict__)


@router.get("/{invoice_id}", response_model=IncomingInvoiceDetailResponse)
async def get_incoming_invoice(
    invoice_id: str,
    user: User = Depends(require_admin),
) -> IncomingInvoiceDetailResponse:
    invoice = await IncomingInvoiceRepository.get_by_id(user.tenant_id, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = await IncomingInvoiceRepository.list_lines(user.tenant_id, invoice.id)
    return IncomingInvoiceDetailResponse(
        **_invoice_response(invoice).model_dump(),
        lines=[_line_response(line) for line in lines],
    )


@router.post("/{invoice_id}/answer", response_model=InvoiceLifecycleResponse)
async def answer_incoming_invoice(
    invoice_id: str,
    request: IncomingInvoiceAnswerRequest,
    user: User = Depends(require_admin),
) -> InvoiceLifecycleResponse:
    if not is_nilvera_incoming_answer_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NILVERA_INCOMING_ANSWER_DISABLED",
                "detail": "Incoming invoice answers are disabled.",
            },
        )

    tenant_id = user.tenant_id
    invoice = await IncomingInvoiceRepository.get_by_id(tenant_id, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    action_type = InvoiceLifecycleActionType.ACCEPT_INCOMING if request.answer == "APPROVE" else InvoiceLifecycleActionType.REJECT_INCOMING
    request_uuid = str(request.request_uuid)
    idempotency_key = f"{tenant_id}:{invoice_id}:{action_type.value}:{request_uuid}"
    fingerprint_data = json.dumps(
        {
            "action_type": action_type.value,
            "note": request.note,
            "source_invoice_id": invoice_id,
            "tenant_id": tenant_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    request_fingerprint = hashlib.sha256(fingerprint_data.encode("utf-8")).hexdigest()

    existing_action = await InvoiceLifecycleRepository.get_by_idempotency_key(tenant_id, idempotency_key)
    if existing_action:
        if existing_action.request_fingerprint != request_fingerprint:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: request_uuid used with different payload.")
        return _map_to_response(existing_action)

    if invoice.profile == IncomingInvoiceProfile.BASIC:
        raise HTTPException(status_code=400, detail="Cannot approve or reject a BASIC (TEMELFATURA) invoice.")
    if invoice.answer_status != IncomingInvoiceAnswerStatus.PENDING:
        raise HTTPException(status_code=409, detail="INVOICE_ANSWER_STATE_NOT_PENDING")
    if invoice.provider_status != IncomingInvoiceProviderStatus.SUCCEED:
        raise HTTPException(status_code=409, detail="INVOICE_PROVIDER_STATUS_NOT_READY")

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
        request_uuid=request_uuid,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        answer_guard_key=invoice_id,
        reason=request.note,
        requested_by=str(user.id),
        requested_at=datetime.now(UTC),
    )

    created = await InvoiceLifecycleRepository.create_action(action)
    if created == ActionCreationResult.IDEMPOTENCY_CONFLICT:
        concurrent_action = await InvoiceLifecycleRepository.get_by_idempotency_key(tenant_id, idempotency_key)
        if concurrent_action and concurrent_action.request_fingerprint == request_fingerprint:
            return _map_to_response(concurrent_action)
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: request_uuid used with different payload.")
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

    # 4. Fail-Closed Option A: Provider Contract Not Verified
    # Do not create allocation or action yet.
    raise HTTPException(status_code=503, detail={"code": "PROVIDER_CONTRACT_NOT_VERIFIED", "detail": "CreateReturn provider contract is not verified."})
