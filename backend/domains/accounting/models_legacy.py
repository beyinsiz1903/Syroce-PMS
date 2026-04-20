import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
    tax_office: str | None = None
    tax_number: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    account_balance: float = 0.0
    category: str = "general"
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    bank_name: str
    account_number: str
    iban: str | None = None
    currency: str = "USD"
    balance: float = 0.0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    expense_number: str
    supplier_id: str | None = None
    category: ExpenseCategory
    description: str
    amount: float
    vat_rate: float = 18.0
    vat_amount: float = 0.0
    total_amount: float
    date: datetime
    payment_status: PaymentStatus = PaymentStatus.PENDING
    payment_method: str | None = None
    receipt_url: str | None = None
    notes: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    sku: str | None = None
    category: str
    unit: str
    quantity: float = 0.0
    unit_cost: float = 0.0
    reorder_level: float = 0.0
    supplier_id: str | None = None
    location: str | None = None
    notes: str | None = None
    is_consumable: bool = True  # False = çok kullanımlık (havlu, nevresim vb.) — stoktan düşmez
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class StockMovement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_id: str
    movement_type: str  # in, out, adjustment
    quantity: float
    unit_cost: float
    reference: str | None = None
    notes: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class AdditionalTax(BaseModel):
    tax_type: AdditionalTaxType
    tax_name: str  # Display name
    rate: float | None = None  # For percentage-based taxes
    amount: float | None = None  # For fixed amount taxes
    is_percentage: bool = True
    withholding_rate: str | None = None  # For withholding taxes (e.g., "7/10")
    calculated_amount: float = 0.0

class AccountingInvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    vat_rate: float
    vat_amount: float
    total: float
    additional_taxes: list[AdditionalTax] | None = []

class AccountingInvoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    invoice_type: InvoiceType
    customer_name: str
    customer_email: str | None = None
    customer_tax_office: str | None = None
    customer_tax_number: str | None = None
    customer_address: str | None = None
    items: list[AccountingInvoiceItem]
    subtotal: float
    total_vat: float
    vat_withholding: float = 0.0  # Tevkifat on VAT
    total_additional_taxes: float = 0.0  # Other additional taxes (ÖTV, etc.)
    total: float
    status: PaymentStatus = PaymentStatus.PENDING
    issue_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_date: datetime
    payment_date: datetime | None = None
    notes: str | None = None
    booking_id: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CashFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_type: TransactionType
    category: str
    amount: float
    description: str
    bank_account_id: str | None = None
    reference_id: str | None = None
    reference_type: str | None = None  # invoice, expense, booking
    date: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
