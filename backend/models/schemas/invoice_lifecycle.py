from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class InvoiceLifecycleDirection(StrEnum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


class InvoiceLifecycleActionType(StrEnum):
    ACCEPT_INCOMING = "ACCEPT_INCOMING"
    REJECT_INCOMING = "REJECT_INCOMING"
    CREATE_RETURN_INVOICE = "CREATE_RETURN_INVOICE"


class InvoiceLifecycleActionState(StrEnum):
    REQUESTED = "REQUESTED"
    PROCESSING = "PROCESSING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FAILED = "FAILED"


class InvoiceLifecycleAction(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    tenant_id: str

    direction: InvoiceLifecycleDirection
    source_invoice_id: str
    source_provider_uuid: str

    action_type: InvoiceLifecycleActionType
    state: InvoiceLifecycleActionState

    request_uuid: str
    idempotency_key: str
    request_fingerprint: str

    reason: str | None = None

    provider_action_id: str | None = None
    generated_invoice_uuid: str | None = None
    generated_invoice_number: str | None = None

    attempt_count: int = 0
    next_attempt_at: datetime | None = None

    reconciliation_required: bool = False
    reconciliation_reason: str | None = None

    lifecycle_lease_owner: str | None = None
    lifecycle_lease_expires_at: datetime | None = None

    requested_by: str
    requested_at: datetime
    completed_at: datetime | None = None
