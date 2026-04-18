"""Auto-split from schemas.py — domain: invoicing."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

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
    items: list[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    due_date: str
    notes: str | None = None

class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    booking_id: str | None = None
    customer_name: str
    customer_email: str
    items: list[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issue_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_date: datetime
    notes: str | None = None


