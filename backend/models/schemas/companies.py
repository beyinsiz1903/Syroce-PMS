"""Auto-split from schemas.py — domain: companies."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.enums import (
    CancellationPolicyType,
    CompanyStatus,
    ContractedRateType,
    DepartmentType,
    MarketSegment,
    PaymentMethod,
    RateType,
    RiskLevel,
)


# Company Models
class CompanyCreate(BaseModel):
    name: str
    corporate_code: str | None = None
    tax_number: str | None = None
    billing_address: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contracted_rate: ContractedRateType | None = None
    default_rate_type: RateType | None = None
    default_market_segment: MarketSegment | None = None
    default_cancellation_policy: CancellationPolicyType | None = None
    room_nights_commitment: int | None = None

    payment_terms: str | None = None
    status: CompanyStatus = CompanyStatus.PENDING


class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    corporate_code: str | None = None
    tax_number: str | None = None
    billing_address: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contracted_rate: ContractedRateType | None = None
    default_rate_type: RateType | None = None
    default_market_segment: MarketSegment | None = None
    default_cancellation_policy: CancellationPolicyType | None = None
    payment_terms: str | None = None
    status: CompanyStatus = CompanyStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Finance Mobile Models - Bank Accounts & Credit Limits
class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    bank_name: str  # Garanti BBVA, İş Bankası, etc.
    account_number: str
    iban: str
    currency: str = "TRY"
    current_balance: float = 0.0
    available_balance: float = 0.0
    account_type: str = "checking"  # checking, savings, etc.
    is_active: bool = True
    api_enabled: bool = False  # Future: Open Banking API integration
    api_credentials: dict[str, Any] | None = None  # API keys/tokens
    last_sync: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreditLimit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    company_id: str  # Link to Company model
    company_name: str | None = None
    credit_limit: float = 0.0
    monthly_limit: float | None = None
    current_debt: float = 0.0
    available_credit: float = 0.0
    payment_terms_days: int = 30  # Net 30, Net 60, etc.
    risk_level: RiskLevel = RiskLevel.NORMAL
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    expense_number: str
    date: datetime
    amount: float
    category: str  # Personnel, Utilities, Maintenance, etc.
    department: DepartmentType
    vendor: str | None = None
    description: str
    payment_method: PaymentMethod
    paid: bool = False
    approved_by: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CashFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_type: str  # inflow, outflow
    amount: float
    currency: str = "TRY"
    date: datetime
    category: str
    reference_id: str | None = None  # Link to payment, expense, etc.
    reference_type: str | None = None  # payment, expense, invoice, etc.
    bank_account_id: str | None = None
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CityLedgerTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    account_id: str
    transaction_type: str  # charge, payment
    amount: float
    description: str
    reference_number: str | None = None
    posted_by: str
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
