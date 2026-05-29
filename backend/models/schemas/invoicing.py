"""Auto-split from schemas.py — domain: invoicing."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.enums import (
    InvoiceStatus,
)


# Invoice Models
class InvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class InvoiceCreate(BaseModel):
    booking_id: str | None = None
    customer_name: str
    customer_email: str
    # F8 § 98 (Wave 3): Turkish e-Fatura/e-Arşiv customer identity. VKN (10
    # digits, corporate) or TCKN (11 digits, individual). Optional so existing
    # callers keep working; when supplied it must be a valid length/digit string
    # so downstream e-invoice integrations don't emit malformed identifiers.
    customer_tax_id: str | None = None
    customer_tax_office: str | None = None
    items: list[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    due_date: str
    notes: str | None = None

    @field_validator("customer_tax_id")
    @classmethod
    def _validate_tax_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return None
        if not v.isdigit() or len(v) not in (10, 11):
            raise ValueError(
                "customer_tax_id must be 10 digits (VKN) or 11 digits (TCKN)"
            )
        return v

class Invoice(BaseModel):
    # v95 Bug fix: legacy DB rows from earlier seed/booking flows may lack
    # several "required" fields (customer_name/email/items/subtotal/tax/due_date).
    # Make them optional with safe defaults so list/get endpoints don't 500;
    # new invoices created via /invoices POST still get full data via InvoiceCreate.
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    booking_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    items: list[InvoiceItem] = Field(default_factory=list)
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issue_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_date: datetime | None = None
    notes: str | None = None
    # Legacy fields (alias so list endpoint can also surface old billing_* rows)
    billing_name: str | None = None
    billing_tax_id: str | None = None
    item_count: int | None = None
    created_at: str | None = None
    created_by: str | None = None


