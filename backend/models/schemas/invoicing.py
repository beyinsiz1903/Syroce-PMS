"""Auto-split from schemas.py — domain: invoicing."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.enums import (
    InvoiceStatus,
)


# Invoice Models
class TaxDetail(BaseModel):
    tax_code: str
    tax_name: str
    rate: Decimal
    taxable_amount: Decimal
    amount: Decimal
    exemption_code: str | None = None
    exemption_reason: str | None = None

    @field_validator("tax_code", "tax_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Must not be empty")
        return v

    @field_validator("rate", "taxable_amount", "amount")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_exemption(self) -> "TaxDetail":
        _validate_scale(self.taxable_amount, 2, "taxable_amount")
        _validate_scale(self.amount, 2, "amount")
        _validate_scale(self.rate, 2, "rate")

        if self.exemption_code is not None:
            self.exemption_code = self.exemption_code.strip() or None
        if self.exemption_reason is not None:
            self.exemption_reason = self.exemption_reason.strip() or None

        has_code = bool(self.exemption_code)
        has_reason = bool(self.exemption_reason)
        if has_code != has_reason:
            raise ValueError("exemption_code and exemption_reason must both be provided together or neither")
        return self


class InvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

    # E-document financial snapshot fields (Additive, Nullable)
    unit_code: str | None = None
    tax_quantity: Decimal | None = None
    tax_unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    line_extension_amount: Decimal | None = None
    kdv_rate: Decimal | None = None
    kdv_amount: Decimal | None = None
    other_taxes: list[TaxDetail] | None = None


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

    # E-document buyer details
    buyer_tax_number: str | None = None
    buyer_legal_name: str | None = None
    buyer_address: str | None = None
    buyer_city: str | None = None
    buyer_country_code: str | None = None
    buyer_country_name: str | None = None
    buyer_tax_office: str | None = None
    buyer_alias: str | None = None
    buyer_type: Literal["BUSINESS", "INDIVIDUAL_CONSUMER"] | None = None

    # E-document document-level snapshot fields
    document_kind: Literal["E_INVOICE", "E_ARCHIVE"] | None = None
    invoice_type: Literal["SATIS", "IADE", "TEVKIFAT"] | None = None
    profile: Literal["TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"] | None = None
    series: str | None = None
    currency: str | None = None
    exchange_rate: Decimal | None = None
    discount_total: Decimal | None = None
    line_extension_total: Decimal | None = None
    kdv_total: Decimal | None = None
    other_tax_total: Decimal | None = None
    payable_total: Decimal | None = None
    tax_data_complete: bool = False

    @field_validator("customer_tax_id")
    @classmethod
    def _validate_tax_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return None
        if not v.isdigit() or len(v) not in (10, 11):
            raise ValueError("customer_tax_id must be 10 digits (VKN) or 11 digits (TCKN)")
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

    # E-document buyer details
    buyer_tax_number: str | None = None
    buyer_legal_name: str | None = None
    buyer_address: str | None = None
    buyer_city: str | None = None
    buyer_country_code: str | None = None
    buyer_country_name: str | None = None
    buyer_tax_office: str | None = None
    buyer_alias: str | None = None
    buyer_type: Literal["BUSINESS", "INDIVIDUAL_CONSUMER"] | None = None

    # E-document document-level snapshot fields
    document_kind: Literal["E_INVOICE", "E_ARCHIVE"] | None = None
    invoice_type: Literal["SATIS", "IADE", "TEVKIFAT"] | None = None
    profile: Literal["TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"] | None = None
    series: str | None = None
    currency: str | None = None
    exchange_rate: Decimal | None = None
    discount_total: Decimal | None = None
    line_extension_total: Decimal | None = None
    kdv_total: Decimal | None = None
    other_tax_total: Decimal | None = None
    payable_total: Decimal | None = None
    tax_data_complete: bool = False


def _validate_scale(val: Decimal, max_decimals: int, name: str) -> None:
    if not val.is_finite():
        raise ValueError(f"{name} must be a finite number (not NaN or Infinity)")
    normalized = val.normalize()
    exp = normalized.as_tuple().exponent
    if isinstance(exp, int) and exp < 0 and abs(exp) > max_decimals:
        raise ValueError(f"{name} exceeds maximum allowed decimals of {max_decimals}")


def validate_invoice_tax_snapshot(invoice: Invoice | InvoiceCreate) -> bool:
    """
    Validates the tax snapshot of an invoice according to strict e-document rules.
    Raises ValueError with detailed error messages if validation fails.
    Returns True if valid.
    """
    # Check document-level fields
    for field in ["line_extension_total", "kdv_total", "other_tax_total", "payable_total"]:
        val = getattr(invoice, field)
        if val is None:
            raise ValueError(f"Missing required snapshot field: {field}")
        _validate_scale(val, 2, field)
        if val < 0:
            raise ValueError(f"{field} cannot be negative")

    if invoice.discount_total is not None:
        _validate_scale(invoice.discount_total, 2, "discount_total")
        if invoice.discount_total < 0:
            raise ValueError("discount_total cannot be negative")

    # Math
    if not invoice.items:
        raise ValueError("Invoice must have at least one item")

    calc_line_ext = Decimal('0')
    calc_kdv = Decimal('0')
    calc_other_tax = Decimal('0')

    for idx, item in enumerate(invoice.items):
        prefix = f"Item {idx}"

        if item.unit_code is None or not item.unit_code.strip():
            raise ValueError(f"{prefix} missing unit_code")

        if item.tax_quantity is None:
            raise ValueError(f"{prefix} missing tax_quantity")
        _validate_scale(item.tax_quantity, 4, f"{prefix} tax_quantity")
        if item.tax_quantity <= 0:
            raise ValueError(f"{prefix} tax_quantity must be > 0")

        if item.tax_unit_price is None:
            raise ValueError(f"{prefix} missing tax_unit_price")
        _validate_scale(item.tax_unit_price, 6, f"{prefix} tax_unit_price")
        if item.tax_unit_price < 0:
            raise ValueError(f"{prefix} tax_unit_price cannot be negative")

        if item.discount_amount is None:
            raise ValueError(f"{prefix} missing discount_amount")
        _validate_scale(item.discount_amount, 2, f"{prefix} discount_amount")
        if item.discount_amount < 0:
            raise ValueError(f"{prefix} discount_amount cannot be negative")

        if item.line_extension_amount is None:
            raise ValueError(f"{prefix} missing line_extension_amount")
        _validate_scale(item.line_extension_amount, 2, f"{prefix} line_extension_amount")
        if item.line_extension_amount < 0:
            raise ValueError(f"{prefix} line_extension_amount cannot be negative")

        if item.kdv_rate is None:
            raise ValueError(f"{prefix} missing kdv_rate")
        _validate_scale(item.kdv_rate, 2, f"{prefix} kdv_rate")
        if item.kdv_rate < 0:
            raise ValueError(f"{prefix} kdv_rate cannot be negative")

        if item.kdv_amount is None:
            raise ValueError(f"{prefix} missing kdv_amount")
        _validate_scale(item.kdv_amount, 2, f"{prefix} kdv_amount")
        if item.kdv_amount < 0:
            raise ValueError(f"{prefix} kdv_amount cannot be negative")

        gross = item.tax_quantity * item.tax_unit_price
        if item.discount_amount > gross:
            raise ValueError(f"{prefix} discount_amount cannot exceed gross_line_amount")

        expected_line_ext = gross - item.discount_amount
        if item.line_extension_amount != expected_line_ext:
            raise ValueError(f"{prefix} line_extension_amount mismatch. Expected {expected_line_ext}, got {item.line_extension_amount}")

        calc_line_ext += item.line_extension_amount
        calc_kdv += item.kdv_amount

        if item.other_taxes:
            for ot in item.other_taxes:
                _validate_scale(ot.amount, 2, f"{prefix} other tax amount")
                calc_other_tax += ot.amount

    if invoice.line_extension_total != calc_line_ext:
        raise ValueError(f"line_extension_total mismatch. Expected {calc_line_ext}, got {invoice.line_extension_total}")

    if invoice.kdv_total != calc_kdv:
        raise ValueError(f"kdv_total mismatch. Expected {calc_kdv}, got {invoice.kdv_total}")

    if invoice.other_tax_total != calc_other_tax:
        raise ValueError(f"other_tax_total mismatch. Expected {calc_other_tax}, got {invoice.other_tax_total}")

    expected_payable = calc_line_ext + calc_kdv + calc_other_tax
    if invoice.payable_total != expected_payable:
        raise ValueError(f"payable_total mismatch. Expected {expected_payable}, got {invoice.payable_total}")

    return True
