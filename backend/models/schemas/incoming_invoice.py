from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from models.schemas.invoice_sync import InvoiceProvider
from models.schemas.invoicing import TaxDetail


class IncomingInvoiceProfile(StrEnum):
    BASIC = "TEMELFATURA"
    COMMERCIAL = "TICARIFATURA"


class IncomingInvoiceAnswerStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ANSWERED_AUTOMATICALLY = "DOCUMENT_ANSWERED_AUTOMATICALLY"
    UNKNOWN = "UNKNOWN"


class IncomingInvoiceProviderStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    WAITING = "WAITING"
    SUCCEED = "SUCCEED"
    ERROR = "ERROR"


class IncomingTaxDetail(TaxDetail):
    is_deduction: bool = False


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
    provider_status: IncomingInvoiceProviderStatus = IncomingInvoiceProviderStatus.UNKNOWN
    provider_gib_code: str | None = None
    issue_date: datetime
    issue_date_timezone_assumed: bool = False
    received_at: datetime

    payable_amount: Decimal | None = None
    currency: str | None = None
    exchange_rate: Decimal | None = None

    created_at: datetime
    updated_at: datetime
    version: int = 1


class IncomingInvoiceLine(BaseModel):
    id: str
    tenant_id: str
    incoming_invoice_id: str

    provider_line_id: str | None = None
    line_number: int

    name: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal

    discount_amount: Decimal
    line_extension_amount: Decimal

    kdv_rate: Decimal
    kdv_amount: Decimal
    other_taxes: list[IncomingTaxDetail] = Field(default_factory=list)

    currency: str
    active: bool = True
    created_at: datetime
    updated_at: datetime
    version: int = 1
