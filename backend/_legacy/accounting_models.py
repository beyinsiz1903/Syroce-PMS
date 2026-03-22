from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

# ============= ACCOUNTING ENUMS =============

class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"

class ExpenseCategory(str, Enum):
    SALARIES = "salaries"
    UTILITIES = "utilities"
    SUPPLIES = "supplies"
    MAINTENANCE = "maintenance"
    MARKETING = "marketing"
    RENT = "rent"
    INSURANCE = "insurance"
    TAXES = "taxes"
    OTHER = "other"

class IncomeCategory(str, Enum):
    ROOM_REVENUE = "room_revenue"
    FOOD_BEVERAGE = "food_beverage"
    SPA = "spa"
    EVENTS = "events"
    LAUNDRY = "laundry"
    OTHER_SERVICES = "other_services"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"

class InvoiceType(str, Enum):
    SALES = "sales"  # Satış faturası
    PURCHASE = "purchase"  # Alış faturası
    PROFORMA = "proforma"  # Proforma
    E_INVOICE = "e_invoice"  # E-Fatura
    E_ARCHIVE = "e_archive"  # E-Arşiv

class VATRate(str, Enum):
    RATE_1 = "1"
    RATE_8 = "8"
    RATE_10 = "10"
    RATE_18 = "18"
    RATE_20 = "20"
    EXEMPT = "0"

class AdditionalTaxType(str, Enum):
    OTV = "otv"  # Özel Tüketim Vergisi (Special Consumption Tax)
    WITHHOLDING = "withholding"  # Tevkifat (Withholding Tax)
    ACCOMMODATION = "accommodation"  # Konaklama Vergisi (Accommodation Tax)
    SPECIAL_COMMUNICATION = "special_communication"  # ÖİV (Special Communication Tax)

class WithholdingRate(str, Enum):
    ALL = "10/10"  # Tümüne Tevkifat Uygula
    RATE_90 = "9/10"
    RATE_70 = "7/10"
    RATE_50 = "5/10"
    RATE_40 = "4/10"
    RATE_30 = "3/10"
    RATE_20 = "2/10"

# ============= ACCOUNTING MODELS =============

class Supplier(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    tax_office: Optional[str] = None
    tax_number: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    account_balance: float = 0.0
    category: str = "general"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    bank_name: str
    account_number: str
    iban: Optional[str] = None
    currency: str = "USD"
    balance: float = 0.0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    expense_number: str
    supplier_id: Optional[str] = None
    category: ExpenseCategory
    description: str
    amount: float
    vat_rate: float = 18.0
    vat_amount: float = 0.0
    total_amount: float
    date: datetime
    payment_status: PaymentStatus = PaymentStatus.PENDING
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    sku: Optional[str] = None
    category: str
    unit: str
    quantity: float = 0.0
    unit_cost: float = 0.0
    reorder_level: float = 0.0
    supplier_id: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StockMovement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_id: str
    movement_type: str  # in, out, adjustment
    quantity: float
    unit_cost: float
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AdditionalTax(BaseModel):
    tax_type: AdditionalTaxType
    tax_name: str  # Display name
    rate: Optional[float] = None  # For percentage-based taxes
    amount: Optional[float] = None  # For fixed amount taxes
    is_percentage: bool = True
    withholding_rate: Optional[str] = None  # For withholding taxes (e.g., "7/10")
    calculated_amount: float = 0.0

class AccountingInvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    vat_rate: float
    vat_amount: float
    total: float
    additional_taxes: Optional[List[AdditionalTax]] = []

class AccountingInvoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    invoice_type: InvoiceType
    customer_name: str
    customer_email: Optional[str] = None
    customer_tax_office: Optional[str] = None
    customer_tax_number: Optional[str] = None
    customer_address: Optional[str] = None
    items: List[AccountingInvoiceItem]
    subtotal: float
    total_vat: float
    vat_withholding: float = 0.0  # Tevkifat on VAT
    total_additional_taxes: float = 0.0  # Other additional taxes (ÖTV, etc.)
    total: float
    status: PaymentStatus = PaymentStatus.PENDING
    issue_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    payment_date: Optional[datetime] = None
    notes: Optional[str] = None
    booking_id: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CashFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_type: TransactionType
    category: str
    amount: float
    description: str
    bank_account_id: Optional[str] = None
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None  # invoice, expense, booking
    date: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
