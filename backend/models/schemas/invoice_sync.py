from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceSyncState(StrEnum):
    PREPARED = "PREPARED"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    CANCELLED = "CANCELLED"


class InvoiceDocumentKind(StrEnum):
    E_INVOICE = "E_INVOICE"


class InvoiceProvider(StrEnum):
    NILVERA = "NILVERA"


class DispatchErrorCategory(StrEnum):
    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DUPLICATE = "DUPLICATE"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    TRANSPORT = "TRANSPORT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    BUSINESS_RULE = "BUSINESS_RULE"
    UNKNOWN = "UNKNOWN"
    INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"


class RetryDecision(BaseModel):
    retryable: bool
    requires_reconciliation: bool = False
    next_retry_at: datetime | None = None
    reason: str | None = None


class PrepareDispatchResult(BaseModel):
    dispatch_id: str
    request_uuid: UUID
    idempotency_key: str
    created: bool


class InvoiceSync(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    tenant_id: str
    invoice_id: str
    provider: InvoiceProvider
    document_kind: InvoiceDocumentKind
    idempotency_key: str
    request_uuid: str

    state: InvoiceSyncState

    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None

    lease_owner: str | None = None
    lease_expires_at: datetime | None = None

    provider_document_id: str | None = None
    provider_status: str | None = None
    provider_status_code: str | None = None
    provider_status_message: str | None = None
    provider_correlation_id: str | None = None

    status_tracking_started_at: datetime | None = None
    last_status_check_at: datetime | None = None
    next_status_check_at: datetime | None = None
    status_check_attempt_count: int = 0

    status_poll_error_code: str | None = None
    status_poll_error_message: str | None = None
    status_poll_retryable: bool | None = None

    reconciliation_required: bool = False
    reconciliation_reason: str | None = None
    reconciled_at: datetime | None = None
    reconciled_by: str | None = None
    reconciliation_note: str | None = None

    reconciliation_started_at: datetime | None = None
    first_not_found_at: datetime | None = None
    last_reconciliation_at: datetime | None = None
    not_found_count: int = 0
    reconciliation_attempt_count: int = 0
    redispatch_count: int = 0
    next_reconciliation_at: datetime | None = None
    last_counted_reconciliation_cycle_id: str | None = None
    current_reconciliation_cycle_id: str | None = None

    status_lease_owner: str | None = None
    status_lease_expires_at: datetime | None = None

    last_error_category: DispatchErrorCategory | None = None
    last_error_code: str | None = None
    last_error_message: str | None = Field(default=None, max_length=512)
    last_error_retryable: bool | None = None

    prepared_at: datetime
    queued_at: datetime | None = None
    sending_at: datetime | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    cancelled_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
    version: int = 1
