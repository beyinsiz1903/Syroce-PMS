from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from models.schemas.invoice_sync import InvoiceProvider


class IncomingInvoiceProfile(StrEnum):
    BASIC = "TEMELFATURA"
    COMMERCIAL = "TICARIFATURA"


class IncomingInvoiceAnswerStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ANSWERED_AUTOMATICALLY = "DOCUMENT_ANSWERED_AUTOMATICALLY"
    UNKNOWN = "UNKNOWN"


class IncomingInvoice(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    tenant_id: str
    provider: InvoiceProvider
    provider_uuid: str
    invoice_number: str
    sender_vkn_tckn: str
    sender_title: str
    profile: IncomingInvoiceProfile
    answer_status: IncomingInvoiceAnswerStatus
    issue_date: datetime
    received_at: datetime

    payable_amount: float | None = None
    currency: str | None = None

    created_at: datetime
    updated_at: datetime
    version: int = 1
