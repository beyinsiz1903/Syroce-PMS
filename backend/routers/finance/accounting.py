"""Auto-split from finance.py — section: accounting."""

import asyncio
import logging
import math
import re as _re
import uuid
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.sanitize import sanitize_plaintext
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from domains.accounting.models_legacy import AccountingInvoice, AccountingInvoiceItem, AdditionalTax
from models.enums import PaymentStatus
from models.schemas import (
    CashFlow,
    ConvertCurrencyRequest,
    CreateCurrencyRateRequest,
    CreateMultiCurrencyInvoiceRequest,
    GenerateInvoiceFromFolioRequest,
    User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from modules.pms_core.role_permission_service import require_op
from shared_kernel.invoice_guards import ensure_booking_invoiceable, is_status_invoiceable

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter()
security = HTTPBearer()
folio_balance_read_service = FolioBalanceReadService()
open_folio_service = OpenFolioService()
logger = logging.getLogger(__name__)

ACCOMMODATION_VAT_RATE = 10.0
FOOD_SERVICE_VAT_RATE = 10.0
GENERAL_VAT_RATE = 20.0
SUPPORTED_ACCOUNTING_CURRENCIES = {"TRY", "EUR", "USD", "GBP"}


def _accounting_currency(value: object, fallback: str = "TRY") -> str:
    code = str(value or fallback).strip().upper()
    if code == "TL":
        code = "TRY"
    if code not in SUPPORTED_ACCOUNTING_CURRENCIES:
        raise ValueError(f"Unsupported currency: {code}")
    return code


def _report_date_bounds(start_date: str, end_date: str) -> tuple[str, str]:
    """Return inclusive ISO-day bounds for records persisted as ISO strings.

    A bare end date sorts *before* every timestamp on that day (for example,
    ``2026-10-02`` precedes ``2026-10-02T10:00:00``).  Reports must therefore
    query through the last representable instant of the requested final day.
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Tarih YYYY-MM-DD formatında olmalıdır.") from exc
    if end < start:
        raise HTTPException(status_code=422, detail="Bitiş tarihi başlangıç tarihinden önce olamaz.")
    return f"{start.isoformat()}T00:00:00", f"{end.isoformat()}T23:59:59.999999"


def _invoice_currency_terms(
    requested_currency: object,
    requested_exchange_rate: object,
    tenant_currency: str,
) -> tuple[str, float]:
    """Resolve one invoice currency without silently inventing an FX rate."""
    base_currency = _accounting_currency(tenant_currency)
    currency = _accounting_currency(requested_currency, base_currency)
    if currency == base_currency:
        return currency, 1.0
    try:
        exchange_rate = float(requested_exchange_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{currency} fatura için 1 {currency} = kaç {base_currency} olduğu girilmelidir"
        ) from exc
    if not math.isfinite(exchange_rate) or exchange_rate <= 0:
        raise ValueError("Fatura döviz kuru sıfırdan büyük olmalıdır")
    return currency, exchange_rate


def _currency_totals(records, amount_field: str, fallback_currency: str, predicate=None) -> dict[str, float]:
    totals: dict[str, float] = {}
    for record in records:
        if predicate is not None and not predicate(record):
            continue
        currency = _accounting_currency(record.get("currency"), fallback_currency)
        totals[currency] = totals.get(currency, 0) + float(record.get(amount_field, 0) or 0)
    return {currency: round(amount, 2) for currency, amount in totals.items()}


def _charge_vat_rate(charge: dict[str, Any], accommodation_vat_rate: float = ACCOMMODATION_VAT_RATE) -> float:
    """Resolve VAT without treating accommodation tax as VAT.

    Turkish PMS folios can contain both VAT and the separate accommodation
    tax. Room ``tax_rate`` is therefore a combined informational rate and must
    not be copied into a fiscal invoice's VAT field.
    """
    category = str(charge.get("charge_category") or "other").lower()
    if category == "city_tax" or charge.get("konaklama_vergisi"):
        return 0.0
    if category == "room":
        return float(accommodation_vat_rate)

    explicit = charge.get("vat_rate")
    if explicit is not None:
        return float(explicit)

    if category in {"food", "food_beverage", "beverage", "minibar"}:
        text = f"{charge.get('description', '')} {charge.get('subcategory', '')}".lower()
        alcoholic_markers = ("alkol", "alcohol", "wine", "şarap", "sarap", "bira", "beer", "viski", "whisky")
        return GENERAL_VAT_RATE if any(marker in text for marker in alcoholic_markers) else FOOD_SERVICE_VAT_RATE
    return float(charge.get("tax_rate") or GENERAL_VAT_RATE)


def folio_charge_to_invoice_items(
    charge: dict[str, Any],
    accommodation_vat_rate: float = ACCOMMODATION_VAT_RATE,
) -> list[dict[str, Any]]:
    """Convert one folio charge to fiscal lines while preserving its total."""
    category = str(charge.get("charge_category") or "other").lower()
    description = charge.get("description") or "Otel hizmeti"
    amount = round(float(charge.get("amount") or charge.get("unit_price") or 0.0), 2)
    vat_rate = _charge_vat_rate(charge, accommodation_vat_rate)
    item = {
        "description": description,
        "category": category,
        "quantity": 1,
        "unit_price": amount,
        "vat_rate": vat_rate,
        "total": round(amount * (1 + vat_rate / 100.0), 2),
    }
    if category != "room":
        return [item]

    breakdown = charge.get("tax_breakdown") or {}
    accommodation_tax = round(float(breakdown.get("accommodation_tax") or 0.0), 2)
    if accommodation_tax <= 0:
        recorded_total = round(float(charge.get("total") or 0.0), 2)
        accommodation_tax = max(round(recorded_total - item["total"], 2), 0.0)
    if accommodation_tax <= 0:
        return [item]

    return [
        item,
        {
            "description": "Konaklama Vergisi",
            "category": "city_tax",
            "tax_type": "accommodation_tax",
            "quantity": 1,
            "unit_price": accommodation_tax,
            "vat_rate": 0.0,
            "total": accommodation_tax,
        },
    ]


class InvoiceType(str, Enum):
    SALES = "sales"  # Satış faturası
    PURCHASE = "purchase"  # Alış faturası
    PROFORMA = "proforma"  # Proforma
    E_INVOICE = "e_invoice"  # E-Fatura
    E_ARCHIVE = "e_archive"  # E-Arşiv


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
    account_balance_by_currency: dict[str, float] = Field(default_factory=dict)
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
    vat_rate: float = 20.0
    vat_amount: float = 0.0
    total_amount: float
    currency: str = "TRY"
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
    currency: str = "TRY"
    reorder_level: float = 0.0
    supplier_id: str | None = None
    location: str | None = None
    notes: str | None = None
    is_consumable: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StockMovement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_id: str
    movement_type: str  # in, out, adjustment, transfer_out, transfer_in
    quantity: float
    unit_cost: float
    reference: str | None = None
    notes: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Task #20 — warehouse transfer: both legs share the same transfer_id
    # so reconciliation can pair source decrement and destination increment.
    transfer_id: str | None = None
    counterpart_item_id: str | None = None


class StockTransferRequest(BaseModel):
    source_item_id: str
    destination_item_id: str
    quantity: float = Field(gt=0)
    unit_cost: float = Field(default=0.0, ge=0)
    reference: str | None = None
    notes: str | None = None
    # Task #75 — unit-mismatch guard. When the source and destination
    # inventory rows use different units of measure (e.g. kg vs adet),
    # the caller MUST pass an explicit conversion factor so the server
    # knows how many destination units one source unit corresponds to.
    # Destination receives `quantity * conversion_factor`. If units match
    # this field is ignored.
    conversion_factor: float | None = Field(default=None, gt=0)


class StockTransferLine(BaseModel):
    source_item_id: str
    destination_item_id: str
    quantity: float = Field(gt=0)
    unit_cost: float = Field(default=0.0, ge=0)


class BulkStockTransferRequest(BaseModel):
    lines: list[StockTransferLine] = Field(min_length=1, max_length=100)
    reference: str | None = None
    notes: str | None = None


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    tax_office: str | None = None
    tax_number: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    category: str = "general"


class BankAccountCreateRequest(BaseModel):
    name: str
    bank_name: str
    account_number: str
    iban: str | None = None
    currency: str = "USD"
    balance: float = 0.0


class ExpenseCreateRequest(BaseModel):
    category: str
    description: str
    amount: float
    vat_rate: float
    date: str
    supplier_id: str | None = None
    payment_method: str | None = None
    receipt_url: str | None = None
    notes: str | None = None
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value):
        return _accounting_currency(value) if value else None


class InventoryItemCreateRequest(BaseModel):
    name: str
    category: str
    unit: str
    quantity: float = Field(default=0.0, ge=0)
    unit_cost: float = Field(default=0.0, ge=0)
    reorder_level: float = Field(default=0.0, ge=0)
    sku: str | None = None
    supplier_id: str | None = None
    location: str | None = None
    notes: str | None = None
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value):
        return _accounting_currency(value) if value else None


def _norm(v):
    """Treat empty / 'none' sentinels coming from select inputs as null."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in ("", "none"):
        return None
    return v


def _invalidate_accounting_caches(tenant_id: str, *prefixes: str) -> None:
    """Cache invalidation must never turn an already persisted record into a 500."""
    if not cache:
        return
    try:
        for prefix in prefixes:
            cache.invalidate_tenant_cache(tenant_id, prefix)
    except Exception:
        logger.warning("Accounting cache invalidation failed", exc_info=True)


@router.post("/accounting/suppliers")
async def create_supplier(
    payload: SupplierCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    supplier = Supplier(
        tenant_id=current_user.tenant_id,
        name=sanitize_plaintext(payload.name, max_length=200),
        tax_office=sanitize_plaintext(payload.tax_office, max_length=200) if payload.tax_office else None,
        tax_number=sanitize_plaintext(payload.tax_number, max_length=50) if payload.tax_number else None,
        email=payload.email,
        phone=payload.phone,
        address=sanitize_plaintext(payload.address, max_length=500) if payload.address else None,
        category=payload.category or "general",
    )
    supplier_dict = supplier.model_dump(mode="json")
    await db.suppliers.insert_one(supplier_dict)
    persisted = await db.suppliers.find_one({"id": supplier.id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not persisted:
        raise HTTPException(status_code=500, detail="Tedarikçi kaydı doğrulanamadı")
    return persisted


@router.get("/accounting/suppliers")
async def get_suppliers(current_user: User = Depends(get_current_user)):
    suppliers = await db.suppliers.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return suppliers


@router.put("/accounting/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    editable_fields = {
        "name", "tax_office", "tax_number", "email", "phone", "address", "category", "notes",
    }
    if not updates or set(updates) - editable_fields:
        raise HTTPException(status_code=422, detail="Tedarikçinin korunan alanları değiştirilemez")
    patch = dict(updates)
    for field, max_length in (("name", 200), ("tax_office", 200), ("tax_number", 50), ("address", 500), ("notes", 1000)):
        if field in patch:
            patch[field] = sanitize_plaintext(str(patch[field]), max_length=max_length) if patch[field] else None
    result = await db.suppliers.update_one(
        {"id": supplier_id, "tenant_id": current_user.tenant_id},
        {"$set": patch},
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=404, detail="Tedarikçi bulunamadı")
    supplier = await db.suppliers.find_one({"id": supplier_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    return supplier


@router.post("/accounting/bank-accounts")
async def create_bank_account(
    payload: BankAccountCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    bank_account = BankAccount(
        tenant_id=current_user.tenant_id,
        name=sanitize_plaintext(payload.name, max_length=200),
        bank_name=sanitize_plaintext(payload.bank_name, max_length=200),
        account_number=sanitize_plaintext(payload.account_number, max_length=80),
        iban=sanitize_plaintext(payload.iban, max_length=50) if payload.iban else None,
        currency=(payload.currency or "USD").upper(),
        balance=payload.balance,
    )
    account_dict = bank_account.model_dump()
    account_dict["created_at"] = account_dict["created_at"].isoformat()
    await db.bank_accounts.insert_one(account_dict)
    _invalidate_accounting_caches(current_user.tenant_id, "accounting_dashboard", "report_balance_sheet")
    return bank_account


@router.get("/accounting/bank-accounts")
async def get_bank_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.bank_accounts.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return accounts


@router.put("/accounting/bank-accounts/{account_id}")
async def update_bank_account(
    account_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    # Balances and currency are accounting facts.  They must only be changed
    # by reconciled bank movements, never through a generic profile edit.
    editable_fields = {"name", "bank_name", "account_number", "iban", "is_active"}
    if not updates or set(updates) - editable_fields:
        raise HTTPException(status_code=422, detail="Banka hesabının korunan mali alanları değiştirilemez")
    patch = dict(updates)
    for field, max_length in (("name", 200), ("bank_name", 200), ("account_number", 80), ("iban", 50)):
        if field in patch:
            patch[field] = sanitize_plaintext(str(patch[field]), max_length=max_length) if patch[field] else None
    if "is_active" in patch and not isinstance(patch["is_active"], bool):
        raise HTTPException(status_code=422, detail="Hesap durumu doğru/yanlış olmalıdır")
    result = await db.bank_accounts.update_one(
        {"id": account_id, "tenant_id": current_user.tenant_id},
        {"$set": patch},
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=404, detail="Banka hesabı bulunamadı")
    account = await db.bank_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    _invalidate_accounting_caches(current_user.tenant_id, "accounting_dashboard", "report_balance_sheet")
    return account


@router.post("/accounting/expenses")
async def create_expense(
    payload: ExpenseCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    currency = _accounting_currency(payload.currency, tenant_currency)
    count = await db.expenses.count_documents({"tenant_id": current_user.tenant_id})
    expense_number = f"EXP-{count + 1:05d}"

    vat_amount = payload.amount * (payload.vat_rate / 100)
    total_amount = payload.amount + vat_amount

    supplier_id = _norm(payload.supplier_id)

    expense = Expense(
        tenant_id=current_user.tenant_id,
        expense_number=expense_number,
        supplier_id=supplier_id,
        category=payload.category,
        description=sanitize_plaintext(payload.description, max_length=500),
        amount=payload.amount,
        vat_rate=payload.vat_rate,
        vat_amount=vat_amount,
        total_amount=total_amount,
        currency=currency,
        date=datetime.fromisoformat(payload.date),
        payment_method=_norm(payload.payment_method),
        receipt_url=_norm(payload.receipt_url),
        notes=sanitize_plaintext(payload.notes, max_length=1000) if payload.notes else None,
        created_by=current_user.name,
    )

    expense_dict = expense.model_dump(mode="json")
    await db.expenses.insert_one(expense_dict)

    if supplier_id:
        supplier = await db.suppliers.find_one(
            {"id": supplier_id, "tenant_id": current_user.tenant_id},
            {"_id": 0, "account_balance": 1, "account_balance_by_currency": 1},
        )
        if supplier and not supplier.get("account_balance_by_currency") and float(supplier.get("account_balance", 0) or 0) != 0:
            await db.suppliers.update_one(
                {"id": supplier_id, "tenant_id": current_user.tenant_id},
                {"$set": {f"account_balance_by_currency.{tenant_currency}": float(supplier["account_balance"])}},
            )
        balance_updates = {f"account_balance_by_currency.{currency}": total_amount}
        # Preserve the legacy scalar only for the hotel's accounting currency;
        # foreign nominal amounts must never be added to it.
        if currency == tenant_currency:
            balance_updates["account_balance"] = total_amount
        await db.suppliers.update_one(
            {"id": supplier_id, "tenant_id": current_user.tenant_id},
            {"$inc": balance_updates},
        )

    # An expense is an accrual until it is paid.  Recording it in cash flow at
    # creation would overstate cash outflows and make AP look like a payment.
    if expense.payment_status == PaymentStatus.PAID:
        cash_flow = CashFlow(
            tenant_id=current_user.tenant_id,
            transaction_type="expense",
            category=payload.category,
            amount=total_amount,
            currency=currency,
            description=expense.description,
            reference_id=expense.id,
            reference_type="expense",
            date=datetime.fromisoformat(payload.date),
            created_by=current_user.name,
        )
        cf_dict = cash_flow.model_dump()
        cf_dict["date"] = cf_dict["date"].isoformat()
        cf_dict["created_at"] = cf_dict["created_at"].isoformat()
        await db.cash_flow.insert_one(cf_dict)

    _invalidate_accounting_caches(
        current_user.tenant_id,
        "accounting_dashboard",
        "report_profit_loss",
        "report_balance_sheet",
    )

    return expense


@router.get("/accounting/expenses")
async def get_expenses(start_date: str | None = None, end_date: str | None = None, category: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    if category:
        query["category"] = category

    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return expenses


@router.put("/accounting/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    editable_fields = {
        "supplier_id",
        "category",
        "description",
        "amount",
        "vat_rate",
        "date",
        "payment_status",
        "payment_method",
        "receipt_url",
        "notes",
        "currency",
    }
    unsupported_fields = set(updates) - editable_fields
    if unsupported_fields:
        raise HTTPException(status_code=422, detail="Giderin korunan alanları değiştirilemez")

    current = await db.expenses.find_one(
        {"id": expense_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not current:
        raise HTTPException(status_code=404, detail="Gider bulunamadı")

    patch = dict(updates)
    if "supplier_id" in patch:
        patch["supplier_id"] = _norm(patch["supplier_id"])
    if "payment_status" in patch:
        try:
            patch["payment_status"] = PaymentStatus(str(patch["payment_status"]).lower()).value
        except ValueError as exc:
            allowed = ", ".join(status.value for status in PaymentStatus)
            raise HTTPException(status_code=422, detail=f"Geçersiz ödeme durumu. Geçerli değerler: {allowed}") from exc
    if "category" in patch:
        try:
            patch["category"] = ExpenseCategory(str(patch["category"]).lower()).value
        except ValueError as exc:
            allowed = ", ".join(category.value for category in ExpenseCategory)
            raise HTTPException(status_code=422, detail=f"Geçersiz gider kategorisi. Geçerli değerler: {allowed}") from exc
    if "date" in patch:
        try:
            patch["date"] = datetime.fromisoformat(str(patch["date"])).isoformat()
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Gider tarihi geçerli ISO tarih formatında olmalıdır") from exc
    if "description" in patch:
        patch["description"] = sanitize_plaintext(str(patch["description"]), max_length=500)
    if "notes" in patch:
        patch["notes"] = sanitize_plaintext(str(patch["notes"]), max_length=1000) if patch["notes"] else None
    if "currency" in patch:
        try:
            patch["currency"] = _accounting_currency(patch["currency"], current.get("currency") or "TRY")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "amount" in patch or "vat_rate" in patch:
        try:
            amount = float(patch.get("amount", current.get("amount", 0)))
            vat_rate = float(patch.get("vat_rate", current.get("vat_rate", 0)))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Tutar ve KDV oranı sayısal olmalıdır") from exc
        if not math.isfinite(amount) or amount < 0 or not math.isfinite(vat_rate) or not 0 <= vat_rate <= 100:
            raise HTTPException(status_code=422, detail="Tutar negatif olamaz; KDV oranı 0 ile 100 arasında olmalıdır")
        patch.update(
            {
                "amount": round(amount, 2),
                "vat_rate": round(vat_rate, 2),
                "vat_amount": round(amount * vat_rate / 100, 2),
                "total_amount": round(amount * (1 + vat_rate / 100), 2),
            }
        )

    result = await db.expenses.update_one(
        {"id": expense_id, "tenant_id": current_user.tenant_id},
        {"$set": patch},
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=404, detail="Gider bulunamadı")
    expense = await db.expenses.find_one({"id": expense_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    expense_for_cash_flow = {**current, **patch}
    old_supplier_id = _norm(current.get("supplier_id"))
    new_supplier_id = _norm(expense_for_cash_flow.get("supplier_id"))
    old_currency = _accounting_currency(current.get("currency"), "TRY")
    new_currency = _accounting_currency(expense_for_cash_flow.get("currency"), old_currency)
    old_total = float(current.get("total_amount") or 0)
    new_total = float(expense_for_cash_flow.get("total_amount") or 0)
    if old_supplier_id or new_supplier_id:
        tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)

        async def apply_supplier_delta(supplier_id: str | None, currency: str, amount: float) -> None:
            if not supplier_id or not amount:
                return
            increments = {f"account_balance_by_currency.{currency}": round(amount, 2)}
            if currency == tenant_currency:
                increments["account_balance"] = round(amount, 2)
            await db.suppliers.update_one(
                {"id": supplier_id, "tenant_id": current_user.tenant_id},
                {"$inc": increments},
            )

        if old_supplier_id == new_supplier_id and old_currency == new_currency:
            await apply_supplier_delta(new_supplier_id, new_currency, new_total - old_total)
        else:
            await apply_supplier_delta(old_supplier_id, old_currency, -old_total)
            await apply_supplier_delta(new_supplier_id, new_currency, new_total)

    cash_flow_filter = {
        "tenant_id": current_user.tenant_id,
        "reference_type": "expense",
        "reference_id": expense_id,
    }
    cash_flow_patch = {
        "transaction_type": "expense",
        "category": expense_for_cash_flow.get("category"),
        "amount": float(expense_for_cash_flow.get("total_amount") or 0),
        "currency": expense_for_cash_flow.get("currency") or "TRY",
        "description": expense_for_cash_flow.get("description"),
        "date": expense_for_cash_flow.get("date"),
    }
    payment_status = expense_for_cash_flow.get("payment_status", PaymentStatus.PENDING)
    if isinstance(payment_status, PaymentStatus):
        payment_status = payment_status.value
    payment_status = str(payment_status).lower()
    if payment_status == PaymentStatus.PAID.value:
        await db.cash_flow.update_one(
            cash_flow_filter,
            {
                "$set": cash_flow_patch,
                "$setOnInsert": {
                    "tenant_id": current_user.tenant_id,
                    "reference_type": "expense",
                    "reference_id": expense_id,
                    "created_by": getattr(current_user, "name", None),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            },
            upsert=True,
        )
    else:
        # Remove entries written by older versions while the expense is unpaid,
        # partial, or refunded; these are AP states, not cash movements.
        await db.cash_flow.delete_one(cash_flow_filter)
    _invalidate_accounting_caches(
        current_user.tenant_id,
        "accounting_dashboard",
        "report_profit_loss",
        "report_balance_sheet",
    )
    return expense


@router.post("/accounting/inventory")
async def create_inventory_item(
    payload: InventoryItemCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    currency = _accounting_currency(payload.currency, tenant_currency)
    item = InventoryItem(
        tenant_id=current_user.tenant_id,
        name=sanitize_plaintext(payload.name, max_length=200),
        sku=sanitize_plaintext(payload.sku, max_length=80) if payload.sku else None,
        category=payload.category,
        unit=payload.unit,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        currency=currency,
        reorder_level=payload.reorder_level,
        supplier_id=_norm(payload.supplier_id),
        location=sanitize_plaintext(payload.location, max_length=200) if payload.location else None,
        notes=sanitize_plaintext(payload.notes, max_length=1000) if payload.notes else None,
    )
    item_dict = item.model_dump()
    item_dict["created_at"] = item_dict["created_at"].isoformat()
    await db.inventory_items.insert_one(item_dict)
    _invalidate_accounting_caches(current_user.tenant_id, "report_balance_sheet")
    return item


@router.get("/accounting/inventory")
async def get_inventory(current_user: User = Depends(get_current_user)):
    items = await db.inventory_items.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    valued_items = [
        {**item, "inventory_value": float(item.get("quantity", 0) or 0) * float(item.get("unit_cost", 0) or 0)}
        for item in items
    ]
    total_value_by_currency = _currency_totals(valued_items, "inventory_value", tenant_currency)

    # Get low stock items
    low_stock = [item for item in items if item["quantity"] <= item["reorder_level"]]

    return {
        "items": items,
        "low_stock_count": len(low_stock),
        "total_value": round(total_value_by_currency.get(tenant_currency, 0), 2),
        "total_value_by_currency": {code: round(value, 2) for code, value in total_value_by_currency.items()},
        "currency": tenant_currency,
    }


@router.post("/accounting/inventory/movement")
async def create_stock_movement(
    item_id: str,
    movement_type: str,
    quantity: float,
    unit_cost: float,
    reference: str | None = None,
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    # Task #209 — Negative stock guard (P0 financial integrity).
    # Atomic conditional update prevents qty < 0; tenant-scoped filter
    # blocks cross-tenant IDOR; movement record only persisted after
    # update succeeds (no orphan movements on reject).
    if movement_type not in ("in", "out", "adjustment"):
        raise HTTPException(
            status_code=422,
            detail="movement_type must be one of: in, out, adjustment",
        )
    if not isinstance(quantity, (int, float)) or quantity != quantity:  # NaN check
        raise HTTPException(status_code=422, detail="quantity must be a number")
    if movement_type in ("in", "out") and quantity <= 0:
        raise HTTPException(
            status_code=422,
            detail="quantity must be > 0 for in/out movements",
        )
    if movement_type == "adjustment" and quantity < 0:
        raise HTTPException(
            status_code=422,
            detail="adjustment quantity must be >= 0",
        )

    tenant_filter = {"id": item_id, "tenant_id": current_user.tenant_id}
    owned = await db.inventory_items.find_one(tenant_filter, {"_id": 0, "id": 1, "quantity": 1})
    if not owned:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    if movement_type == "in":
        await db.inventory_items.update_one(tenant_filter, {"$inc": {"quantity": quantity}})
    elif movement_type == "out":
        # Atomic guard: only decrement if current quantity >= requested.
        # modified_count == 0 means insufficient stock — reject with 409.
        guard_filter = dict(tenant_filter)
        guard_filter["quantity"] = {"$gte": quantity}
        result = await db.inventory_items.update_one(guard_filter, {"$inc": {"quantity": -quantity}})
        if result.modified_count == 0:
            current_qty = float(owned.get("quantity") or 0)
            raise HTTPException(
                status_code=409,
                detail=(f"Insufficient stock: requested={quantity}, available={current_qty}"),
            )
    else:  # adjustment — quantity already validated >= 0 above
        await db.inventory_items.update_one(tenant_filter, {"$set": {"quantity": quantity}})

    movement = StockMovement(
        tenant_id=current_user.tenant_id, item_id=item_id, movement_type=movement_type, quantity=quantity, unit_cost=unit_cost, reference=reference, notes=notes, created_by=current_user.name
    )
    movement_dict = movement.model_dump()
    movement_dict["created_at"] = movement_dict["created_at"].isoformat()
    await db.stock_movements.insert_one(movement_dict)

    _invalidate_accounting_caches(current_user.tenant_id, "report_balance_sheet")

    return movement


@router.post("/accounting/inventory/transfer")
async def transfer_stock_between_warehouses(
    payload: StockTransferRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    # Task #20 — Warehouse-to-warehouse atomic transfer.
    # Each inventory item row represents stock at a specific location/warehouse
    # (InventoryItem.location). Transfer decrements the source row and
    # increments the destination row atomically using a compensating-$inc
    # pattern: the source decrement is guarded by `quantity >= requested`
    # so insufficient stock fails fast with 409. If the destination
    # increment fails (e.g. dest deleted mid-flight) the source decrement
    # is reversed and the operation reported as a 409/500. Both legs share
    # a `transfer_id` so reconciliation can pair them.
    if payload.source_item_id == payload.destination_item_id:
        raise HTTPException(
            status_code=422,
            detail="source_item_id and destination_item_id must differ",
        )
    quantity = float(payload.quantity)
    if quantity != quantity or quantity <= 0:  # NaN or non-positive
        raise HTTPException(status_code=422, detail="quantity must be > 0")

    src_filter = {"id": payload.source_item_id, "tenant_id": current_user.tenant_id}
    dst_filter = {"id": payload.destination_item_id, "tenant_id": current_user.tenant_id}

    src = await db.inventory_items.find_one(src_filter, {"_id": 0, "id": 1, "quantity": 1, "location": 1, "unit": 1})
    if not src:
        raise HTTPException(status_code=404, detail="Source inventory item not found")
    dst = await db.inventory_items.find_one(dst_filter, {"_id": 0, "id": 1, "quantity": 1, "location": 1, "unit": 1})
    if not dst:
        raise HTTPException(status_code=404, detail="Destination inventory item not found")

    # Task #75 — unit-mismatch guard. A bare quantity transfer across
    # different units of measure (e.g. kg → adet) silently corrupts stock
    # levels. Reject unless the caller supplies an explicit conversion
    # factor. When units match we ignore any supplied factor so legacy
    # callers (no factor) keep working unchanged.
    src_unit = (src.get("unit") or "").strip()
    dst_unit = (dst.get("unit") or "").strip()
    if src_unit and dst_unit and src_unit != dst_unit:
        if payload.conversion_factor is None:
            raise HTTPException(
                status_code=422,
                detail=(f"Unit mismatch: source is '{src_unit}' but destination is '{dst_unit}'. Supply an explicit conversion_factor (destination units per source unit) to proceed."),
            )
        factor = float(payload.conversion_factor)
    else:
        factor = 1.0
    dst_quantity = quantity * factor

    # Atomic source decrement with insufficient-stock guard.
    guard_src = dict(src_filter)
    guard_src["quantity"] = {"$gte": quantity}
    dec = await db.inventory_items.update_one(guard_src, {"$inc": {"quantity": -quantity}})
    if dec.modified_count == 0:
        current_qty = float(src.get("quantity") or 0)
        raise HTTPException(
            status_code=409,
            detail=(f"Insufficient stock at source: requested={quantity}, available={current_qty}"),
        )

    # Destination increment. If it fails for any reason, reverse the source
    # decrement so no stock is destroyed.
    try:
        inc = await db.inventory_items.update_one(dst_filter, {"$inc": {"quantity": dst_quantity}})
        if inc.matched_count == 0:
            # Destination disappeared between read and write — compensate.
            await db.inventory_items.update_one(src_filter, {"$inc": {"quantity": quantity}})
            raise HTTPException(
                status_code=409,
                detail="Destination inventory item disappeared during transfer",
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Compensate source on any unexpected failure.
        try:
            await db.inventory_items.update_one(src_filter, {"$inc": {"quantity": quantity}})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Transfer failed: {exc}") from exc

    transfer_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    out_leg = StockMovement(
        tenant_id=current_user.tenant_id,
        item_id=payload.source_item_id,
        movement_type="transfer_out",
        quantity=quantity,
        unit_cost=payload.unit_cost,
        reference=payload.reference,
        notes=payload.notes,
        created_by=current_user.name,
        transfer_id=transfer_id,
        counterpart_item_id=payload.destination_item_id,
    )
    in_leg = StockMovement(
        tenant_id=current_user.tenant_id,
        item_id=payload.destination_item_id,
        movement_type="transfer_in",
        quantity=dst_quantity,
        unit_cost=payload.unit_cost,
        reference=payload.reference,
        notes=payload.notes,
        created_by=current_user.name,
        transfer_id=transfer_id,
        counterpart_item_id=payload.source_item_id,
    )
    out_dict = out_leg.model_dump()
    in_dict = in_leg.model_dump()
    out_dict["created_at"] = now_iso
    in_dict["created_at"] = now_iso
    # Insert both audit legs; if audit insert fails we still keep the
    # successful stock movement (better than reversing real inventory)
    # but log via HTTP 500 so caller can alert.
    try:
        await db.stock_movements.insert_many([out_dict, in_dict])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Transfer completed but audit write failed: {exc}",
        ) from exc

    return {
        "transfer_id": transfer_id,
        "source_item_id": payload.source_item_id,
        "destination_item_id": payload.destination_item_id,
        "quantity": quantity,
        "destination_quantity": dst_quantity,
        "conversion_factor": factor,
        "unit_cost": payload.unit_cost,
        "legs": [out_leg, in_leg],
    }


@router.post("/accounting/inventory/transfer-bulk")
async def transfer_stock_bulk(
    payload: BulkStockTransferRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    # Task #74 — Multi-line warehouse transfer document.
    # All lines share a single `transfer_id` so finance can reconcile the
    # whole movement as one document. Each line is applied with the same
    # source-guarded $inc pattern as the single-line endpoint. If any line
    # fails mid-flight, every already-applied line is compensated (best
    # effort) so we never destroy or duplicate stock on a partial failure.
    lines = payload.lines
    if not lines:
        raise HTTPException(status_code=422, detail="at least one line required")

    # Per-line structural validation + per-source aggregate so a duplicated
    # source row across lines is validated against the sum, not per-line.
    needed_per_source: dict[str, float] = {}
    for idx, line in enumerate(lines, start=1):
        if line.source_item_id == line.destination_item_id:
            raise HTTPException(
                status_code=422,
                detail=f"line {idx}: source_item_id and destination_item_id must differ",
            )
        q = float(line.quantity)
        if q != q or q <= 0:  # NaN or non-positive
            raise HTTPException(
                status_code=422,
                detail=f"line {idx}: quantity must be > 0",
            )
        needed_per_source[line.source_item_id] = needed_per_source.get(line.source_item_id, 0.0) + q

    # Pre-fetch every involved row so we can short-circuit obvious failures
    # (missing rows, insufficient stock) before mutating anything.
    all_ids = set(needed_per_source.keys())
    all_ids.update(line.destination_item_id for line in lines)
    items: dict[str, dict] = {}
    async for it in db.inventory_items.find(
        {"id": {"$in": list(all_ids)}, "tenant_id": current_user.tenant_id},
        {"_id": 0, "id": 1, "quantity": 1, "location": 1},
    ):
        items[it["id"]] = it

    for idx, line in enumerate(lines, start=1):
        if line.source_item_id not in items:
            raise HTTPException(
                status_code=404,
                detail=f"line {idx}: source inventory item not found",
            )
        if line.destination_item_id not in items:
            raise HTTPException(
                status_code=404,
                detail=f"line {idx}: destination inventory item not found",
            )
    for src_id, needed in needed_per_source.items():
        available = float(items[src_id].get("quantity") or 0)
        if available < needed:
            raise HTTPException(
                status_code=409,
                detail=(f"Insufficient stock for source {src_id}: requested={needed}, available={available}"),
            )

    transfer_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    applied: list[tuple[StockTransferLine, dict, dict]] = []

    async def _rollback():
        # Best-effort compensation: re-increment any source we decremented
        # and re-decrement any destination we incremented. We swallow errors
        # because the original failure has already been raised to the caller.
        for ln, src_f, dst_f in reversed(applied):
            try:
                await db.inventory_items.update_one(src_f, {"$inc": {"quantity": ln.quantity}})
            except Exception:
                pass
            try:
                await db.inventory_items.update_one(dst_f, {"$inc": {"quantity": -ln.quantity}})
            except Exception:
                pass

    for idx, line in enumerate(lines, start=1):
        src_filter = {"id": line.source_item_id, "tenant_id": current_user.tenant_id}
        dst_filter = {"id": line.destination_item_id, "tenant_id": current_user.tenant_id}

        guard_src = dict(src_filter)
        guard_src["quantity"] = {"$gte": line.quantity}
        try:
            dec = await db.inventory_items.update_one(guard_src, {"$inc": {"quantity": -line.quantity}})
        except Exception as exc:
            await _rollback()
            raise HTTPException(
                status_code=500,
                detail=f"line {idx}: transfer failed: {exc}",
            ) from exc
        if dec.modified_count == 0:
            # Either source vanished or concurrent activity drained it.
            await _rollback()
            raise HTTPException(
                status_code=409,
                detail=f"line {idx}: insufficient stock at source (race)",
            )

        try:
            inc = await db.inventory_items.update_one(dst_filter, {"$inc": {"quantity": line.quantity}})
        except Exception as exc:
            # Compensate this line's source decrement, then rollback prior lines.
            try:
                await db.inventory_items.update_one(src_filter, {"$inc": {"quantity": line.quantity}})
            except Exception:
                pass
            await _rollback()
            raise HTTPException(
                status_code=500,
                detail=f"line {idx}: transfer failed: {exc}",
            ) from exc
        if inc.matched_count == 0:
            try:
                await db.inventory_items.update_one(src_filter, {"$inc": {"quantity": line.quantity}})
            except Exception:
                pass
            await _rollback()
            raise HTTPException(
                status_code=409,
                detail=f"line {idx}: destination inventory item disappeared during transfer",
            )

        applied.append((line, src_filter, dst_filter))

    # All lines applied successfully — write paired audit legs sharing the
    # single transfer_id so the reconciliation report groups them together.
    legs_to_insert: list[dict] = []
    leg_models: list[StockMovement] = []
    for line in lines:
        out_leg = StockMovement(
            tenant_id=current_user.tenant_id,
            item_id=line.source_item_id,
            movement_type="transfer_out",
            quantity=line.quantity,
            unit_cost=line.unit_cost,
            reference=payload.reference,
            notes=payload.notes,
            created_by=current_user.name,
            transfer_id=transfer_id,
            counterpart_item_id=line.destination_item_id,
        )
        in_leg = StockMovement(
            tenant_id=current_user.tenant_id,
            item_id=line.destination_item_id,
            movement_type="transfer_in",
            quantity=line.quantity,
            unit_cost=line.unit_cost,
            reference=payload.reference,
            notes=payload.notes,
            created_by=current_user.name,
            transfer_id=transfer_id,
            counterpart_item_id=line.source_item_id,
        )
        for leg in (out_leg, in_leg):
            d = leg.model_dump()
            d["created_at"] = now_iso
            legs_to_insert.append(d)
        leg_models.extend([out_leg, in_leg])

    try:
        await db.stock_movements.insert_many(legs_to_insert)
    except Exception as exc:
        # Stock already moved successfully; surface so caller can alert,
        # but do NOT roll back inventory (better than destroying real stock).
        raise HTTPException(
            status_code=500,
            detail=f"Bulk transfer completed but audit write failed: {exc}",
        ) from exc

    return {
        "transfer_id": transfer_id,
        "reference": payload.reference,
        "line_count": len(lines),
        "lines": [
            {
                "source_item_id": line.source_item_id,
                "destination_item_id": line.destination_item_id,
                "quantity": line.quantity,
                "unit_cost": line.unit_cost,
            }
            for line in lines
        ],
        "legs": leg_models,
    }


@router.get("/accounting/inventory/transfers")
async def get_transfer_history(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    # Task #62 — Transfer history report for finance reconciliation.
    # Each warehouse transfer writes paired stock_movements rows tagged with
    # the same `transfer_id` (transfer_out + transfer_in per line).
    # Task #74 extended this so a single `transfer_id` can carry many lines
    # (multi-item transfer document). Pair every leg by (source, destination)
    # within the transfer so multi-line documents preserve every line; for
    # the legacy single-line case the response still exposes the top-level
    # `source_*`/`destination_*` fields for backwards compatibility.
    # Tenant-scoped at the query level; date filter is inclusive on ISO
    # `created_at` strings (lexicographic compare is safe because all rows
    # are written with `.isoformat()` in UTC).
    if limit < 1:
        limit = 1
    elif limit > 5000:
        limit = 5000

    query: dict[str, Any] = {
        "tenant_id": current_user.tenant_id,
        "movement_type": {"$in": ["transfer_out", "transfer_in"]},
        "transfer_id": {"$ne": None},
    }
    if start_date and end_date:
        query["created_at"] = {"$gte": start_date, "$lte": end_date}
    elif start_date:
        query["created_at"] = {"$gte": start_date}
    elif end_date:
        query["created_at"] = {"$lte": end_date}

    # Pull legs. A multi-line transfer writes 2*N rows per transfer_id, so
    # cap generously (200x) to keep up to `limit` complete documents in the
    # common case (documents typically <=10 lines).
    fetch_cap = max(limit * 4, min(limit * 200, 20000))
    rows = await db.stock_movements.find(query, {"_id": 0}).sort("created_at", -1).to_list(fetch_cap)

    # Resolve item names for readability without an extra round-trip per row.
    item_ids = {r.get("item_id") for r in rows if r.get("item_id")}
    item_ids.update(r.get("counterpart_item_id") for r in rows if r.get("counterpart_item_id"))
    item_ids.discard(None)
    name_by_id: dict[str, str] = {}
    if item_ids:
        items_cursor = db.inventory_items.find(
            {
                "tenant_id": current_user.tenant_id,
                "id": {"$in": list(item_ids)},
            },
            {"_id": 0, "id": 1, "name": 1, "location": 1},
        )
        async for it in items_cursor:
            label = it.get("name") or ""
            loc = it.get("location")
            name_by_id[it["id"]] = f"{label} ({loc})" if loc else label

    # First pass: bucket legs by transfer_id, then within each bucket pair
    # them by (source_item_id, destination_item_id). Quantities for the same
    # pair are summed so a document that legitimately repeats the same line
    # (allowed by the bulk endpoint) collapses to one reconciliation row.
    legs_by_tid: dict[str, list[dict]] = {}
    for row in rows:
        tid = row.get("transfer_id")
        if not tid:
            continue
        legs_by_tid.setdefault(tid, []).append(row)

    grouped: dict[str, dict[str, Any]] = {}
    for tid, legs in legs_by_tid.items():
        # Earliest leg drives the document header so all legs of one
        # document share a single created_at/reference/etc.
        header_leg = min(legs, key=lambda r: r.get("created_at") or "")
        header = {
            "transfer_id": tid,
            "reference": header_leg.get("reference"),
            "notes": header_leg.get("notes"),
            "created_at": header_leg.get("created_at"),
            "created_by": header_leg.get("created_by"),
        }

        # Pair legs into reconciliation lines.
        pair_acc: dict[tuple[str | None, str | None], dict[str, Any]] = {}
        for leg in legs:
            mt = leg.get("movement_type")
            if mt == "transfer_out":
                src = leg.get("item_id")
                dst = leg.get("counterpart_item_id")
            elif mt == "transfer_in":
                dst = leg.get("item_id")
                src = leg.get("counterpart_item_id")
            else:
                continue
            key = (src, dst)
            entry = pair_acc.setdefault(
                key,
                {
                    "source_item_id": src,
                    "source_item_name": name_by_id.get(src),
                    "destination_item_id": dst,
                    "destination_item_name": name_by_id.get(dst),
                    "_out_qty": 0.0,
                    "_in_qty": 0.0,
                    "unit_cost": float(leg.get("unit_cost") or 0),
                },
            )
            q = float(leg.get("quantity") or 0)
            if mt == "transfer_out":
                entry["_out_qty"] += q
            else:
                entry["_in_qty"] += q

        lines_out: list[dict[str, Any]] = []
        total_qty = 0.0
        total_value = 0.0
        for entry in pair_acc.values():
            # The canonical quantity for a line is the out-leg sum (both
            # legs should agree; out leg is what was decremented from the
            # source warehouse).
            qty = entry["_out_qty"] or entry["_in_qty"]
            unit_cost = entry["unit_cost"]
            line = {
                "source_item_id": entry["source_item_id"],
                "source_item_name": entry["source_item_name"],
                "destination_item_id": entry["destination_item_id"],
                "destination_item_name": entry["destination_item_name"],
                "quantity": qty,
                "unit_cost": unit_cost,
            }
            lines_out.append(line)
            total_qty += qty
            total_value += qty * unit_cost

        # Stable line ordering by source/destination for deterministic output.
        lines_out.sort(
            key=lambda ln: (
                ln.get("source_item_name") or "",
                ln.get("destination_item_name") or "",
            )
        )

        # Backwards-compatible single-line summary fields when the document
        # has exactly one line, so existing consumers keep working.
        first = lines_out[0] if lines_out else None
        single = len(lines_out) == 1
        header.update(
            {
                "line_count": len(lines_out),
                "total_quantity": total_qty,
                "total_value": total_value,
                "lines": lines_out,
                "source_item_id": first["source_item_id"] if single else None,
                "source_item_name": first["source_item_name"] if single else None,
                "destination_item_id": first["destination_item_id"] if single else None,
                "destination_item_name": first["destination_item_name"] if single else None,
                "quantity": first["quantity"] if single else total_qty,
                "unit_cost": first["unit_cost"] if single else 0.0,
            }
        )
        grouped[tid] = header

    transfers = sorted(
        grouped.values(),
        key=lambda t: t.get("created_at") or "",
        reverse=True,
    )[:limit]

    return {
        "transfers": transfers,
        "count": len(transfers),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        },
    }


# Block ANY HTML/XML-like tag (`<word`, `</word>`, `<...>`), event handlers,
# javascript: pseudo-URLs. Catches unknown tags too (e.g. `<x>`, `<EVIL>`).
_INVOICE_NAME_BLOCK = _re.compile(
    r"<\s*/?\s*[A-Za-z][\w:-]*"  # opening or closing tag start: <tag, </tag
    r"|on\w+\s*=|javascript:|data:",
    _re.IGNORECASE,
)


def _validate_invoice_customer_name(name: str | None) -> str:
    """Reject empty / unsafe / XML-injection customer names at write time.
    Check the RAW input for HTML/XML tag patterns first (sanitize_plaintext
    silently strips tags, which would otherwise mask injection attempts).
    Then sanitize and verify minimum length."""
    raw = (name or "").strip()
    if _INVOICE_NAME_BLOCK.search(raw):
        raise HTTPException(
            status_code=400,
            detail="Müşteri adı geçersiz karakterler içeriyor (HTML/XML kabul edilmez).",
        )
    cleaned = (sanitize_plaintext(raw, max_length=200) or "").strip()
    if len(cleaned) < 2:
        raise HTTPException(
            status_code=400,
            detail="Müşteri adı en az 2 karakter olmalıdır.",
        )
    return cleaned


# Package C (e-Fatura/e-Arşiv compliance parity): single source of truth for the
# Turkish tax-identity contract, mirroring InvoiceCreate.customer_tax_id. VKN
# (10 digits, corporate) or TCKN (11 digits, individual). Optional so existing
# callers keep working; when supplied it must be digits of length 10/11 so the
# GIB e-invoice path never emits malformed identifiers. Raises ValueError on
# malformed input (pydantic surfaces 422; the raw-dict update path wraps it).
def _normalize_customer_tax_number(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if v == "":
        return None
    if not v.isdigit() or len(v) not in (10, 11):
        raise ValueError("customer_tax_number must be 10 digits (VKN) or 11 digits (TCKN)")
    return v


def _normalize_accounting_invoice_due_date(v: str) -> str:
    """Return a canonical invoice due date before the route parses it."""
    try:
        return date.fromisoformat(v.strip()).isoformat()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("due_date geçerli bir tarih olmalıdır (YYYY-MM-DD)") from exc


class AccountingInvoiceCreateRequest(BaseModel):
    invoice_type: str
    customer_name: str
    customer_email: str | None = None
    customer_tax_office: str | None = None
    customer_tax_number: str | None = None
    customer_address: str | None = None
    # Existing integrations may open an invoice draft before adding its lines.
    # The UI requires a line on final creation, but the API remains backward compatible.
    items: list[dict[str, Any]] = Field(default_factory=list)
    due_date: str
    booking_id: str | None = None
    notes: str | None = None
    currency: str | None = None
    exchange_rate: float | None = Field(default=None, gt=0)

    @field_validator("invoice_type")
    @classmethod
    def _validate_invoice_type(cls, value: str) -> str:
        # ``standard`` was used by older clients for a normal sales invoice.
        # Normalize it at the API boundary so reports never have to guess what
        # an arbitrary document type means.
        normalized = str(value or "").strip().lower().replace("-", "_")
        aliases = {"standard": InvoiceType.SALES.value, "einvoice": InvoiceType.E_INVOICE.value, "earchive": InvoiceType.E_ARCHIVE.value}
        normalized = aliases.get(normalized, normalized)
        try:
            return InvoiceType(normalized).value
        except ValueError as exc:
            allowed = ", ".join(invoice_type.value for invoice_type in InvoiceType)
            raise ValueError(f"invoice_type geçerli bir belge türü olmalıdır: {allowed}") from exc

    @field_validator("customer_tax_number")
    @classmethod
    def _validate_customer_tax_number(cls, v: str | None) -> str | None:
        return _normalize_customer_tax_number(v)

    @field_validator("due_date")
    @classmethod
    def _validate_due_date(cls, v: str) -> str:
        return _normalize_accounting_invoice_due_date(v)

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str | None) -> str | None:
        return _accounting_currency(v) if v else None


@router.post("/accounting/invoices")
async def create_accounting_invoice(
    request: AccountingInvoiceCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    # Models are now imported at the top of the file

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    try:
        invoice_currency, exchange_rate = _invoice_currency_terms(
            request.currency,
            request.exchange_rate,
            tenant_currency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    count = await db.accounting_invoices.count_documents({"tenant_id": current_user.tenant_id})
    invoice_number = f"INV-{datetime.now().year}-{count + 1:05d}"

    invoice_items = []
    subtotal = 0.0
    total_vat = 0.0
    vat_withholding = 0.0
    total_additional_taxes = 0.0

    for item_data in request.items:
        # Handle additional_taxes parsing
        additional_taxes = []
        if "additional_taxes" in item_data and item_data["additional_taxes"]:
            for tax_data in item_data["additional_taxes"]:
                additional_taxes.append(AdditionalTax(**tax_data))

        # Create item with parsed additional taxes
        item_dict = {k: v for k, v in item_data.items() if k != "additional_taxes"}
        item_dict["additional_taxes"] = additional_taxes

        # Financial line amounts are server-owned.  Never accept a client
        # supplied VAT or total: those fields would otherwise allow an invoice
        # whose displayed rate and booked amount disagree.
        try:
            _qty = float(item_dict.get("quantity", 0) or 0)
            _up = float(item_dict.get("unit_price", 0) or 0)
            _vrate = float(item_dict.get("vat_rate", 0) or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="quantity/unit_price/vat_rate sayisal olmali")
        _line_net = round(_qty * _up, 2)
        item_dict["vat_amount"] = round(_line_net * (_vrate / 100.0), 2)
        item_dict["total"] = round(_line_net + item_dict["vat_amount"], 2)

        try:
            item = AccountingInvoiceItem(**item_dict)
        except Exception as ve:
            raise HTTPException(status_code=422, detail=f"Gecersiz fatura kalemi: {ve}")

        invoice_items.append(item)
        subtotal += item.quantity * item.unit_price
        total_vat += item.vat_amount

        # Calculate additional taxes if present
        if item.additional_taxes:
            for tax in item.additional_taxes:
                if tax.tax_type == "withholding":
                    # Withholding tax is deducted from VAT
                    # Calculate based on withholding rate (e.g., "7/10" = 70%)
                    if tax.withholding_rate:
                        rate_parts = tax.withholding_rate.split("/")
                        if len(rate_parts) == 2:
                            rate_percent = (int(rate_parts[0]) / int(rate_parts[1])) * 100
                            withholding_amount = item.vat_amount * (rate_percent / 100)
                            vat_withholding += withholding_amount
                            tax.calculated_amount = withholding_amount
                else:
                    # Other taxes (ÖTV, accommodation, etc.)
                    if tax.is_percentage and tax.rate:
                        tax_amount = (item.quantity * item.unit_price) * (tax.rate / 100)
                        total_additional_taxes += tax_amount
                        tax.calculated_amount = tax_amount
                    elif tax.amount:
                        total_additional_taxes += tax.amount
                        tax.calculated_amount = tax.amount

    total = subtotal + total_vat + total_additional_taxes - vat_withholding

    invoice = AccountingInvoice(
        tenant_id=current_user.tenant_id,
        invoice_number=invoice_number,
        invoice_type=request.invoice_type,
        customer_name=_validate_invoice_customer_name(request.customer_name),
        customer_email=request.customer_email,
        customer_tax_office=sanitize_plaintext(request.customer_tax_office, max_length=120),
        customer_tax_number=sanitize_plaintext(request.customer_tax_number, max_length=20),
        customer_address=sanitize_plaintext(request.customer_address, max_length=500),
        items=invoice_items,
        subtotal=subtotal,
        total_vat=total_vat,
        vat_withholding=vat_withholding,
        total_additional_taxes=total_additional_taxes,
        total=total,
        currency=invoice_currency,
        base_currency=tenant_currency,
        exchange_rate=exchange_rate,
        subtotal_base=round(subtotal * exchange_rate, 2),
        total_vat_base=round(total_vat * exchange_rate, 2),
        total_base=round(total * exchange_rate, 2),
        due_date=datetime.fromisoformat(request.due_date),
        booking_id=request.booking_id,
        notes=request.notes,
        created_by=current_user.name,
    )

    invoice_dict = invoice.model_dump(mode="json")
    await db.accounting_invoices.insert_one(invoice_dict)

    # v95.1 — list cache + dashboard cache invalidasyon
    _invalidate_accounting_caches(
        current_user.tenant_id,
        "accounting_invoices_list",
        "accounting_dashboard",
        "report_profit_loss",
        "report_balance_sheet",
    )

    return invoice


@router.get("/accounting/invoices")
@cached(ttl=300, key_prefix="accounting_invoices_list")  # v95.1 — 5dk cache, write path'leri invalidate eder
async def get_accounting_invoices(
    start_date: str | None = None,
    end_date: str | None = None,
    invoice_type: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v95.1 — diğer finance uçlarıyla tutarlı yetki
):
    query = {"tenant_id": current_user.tenant_id}
    if start_date and end_date:
        query["issue_date"] = {"$gte": start_date, "$lte": end_date}
    if invoice_type:
        query["invoice_type"] = invoice_type
    if status:
        query["status"] = status

    invoices = await db.accounting_invoices.find(query, {"_id": 0}).sort("issue_date", -1).to_list(1000)
    # Render-time scrub for legacy rows that contain XML/HTML fragments
    # (e.g. test seeds from earlier security probes). Persisted on next write.
    for inv in invoices:
        for f in ("customer_name", "customer_tax_office", "customer_address"):
            if f in inv and isinstance(inv[f], str):
                inv[f] = sanitize_plaintext(inv[f], max_length=500)
    return invoices


@router.put("/accounting/invoices/{invoice_id}")
async def update_accounting_invoice(
    invoice_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    editable_fields = {
        "status",
        "payment_date",
        "customer_name",
        "customer_email",
        "customer_tax_office",
        "customer_tax_number",
        "customer_address",
        "due_date",
        "notes",
    }
    if set(updates) - editable_fields:
        raise HTTPException(status_code=422, detail="Faturanın mali ve tesis alanları değiştirilemez")
    if "status" in updates:
        try:
            updates["status"] = PaymentStatus(str(updates["status"])).value
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Geçersiz fatura durumu") from exc
    if "status" in updates and updates["status"] == "paid" and "payment_date" not in updates:
        updates["payment_date"] = datetime.now(UTC).isoformat()

    if "due_date" in updates:
        try:
            updates["due_date"] = _normalize_accounting_invoice_due_date(str(updates["due_date"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    for f in ("customer_name", "customer_tax_office", "customer_address", "customer_tax_number"):
        if f in updates and isinstance(updates[f], str):
            updates[f] = sanitize_plaintext(updates[f], max_length=500)

    # Package C compliance parity: the create model validates customer_tax_number
    # via pydantic, but this update path takes a raw dict, so enforce the same
    # VKN/TCKN contract here to prevent post-create malformed writes.
    if "customer_tax_number" in updates:
        try:
            updates["customer_tax_number"] = _normalize_customer_tax_number(updates["customer_tax_number"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    tenant_filter = {"id": invoice_id, "tenant_id": current_user.tenant_id}
    upd = await db.accounting_invoices.update_one(tenant_filter, {"$set": updates})
    if upd.matched_count == 0:
        raise HTTPException(status_code=404, detail="Accounting invoice not found")
    invoice = await db.accounting_invoices.find_one(tenant_filter, {"_id": 0})
    cash_flow_filter = {
        "tenant_id": current_user.tenant_id,
        "reference_type": "invoice",
        "reference_id": invoice_id,
    }
    if invoice and invoice.get("status") == PaymentStatus.PAID.value:
        await db.cash_flow.update_one(
            cash_flow_filter,
            {
                "$set": {
                    "transaction_type": "income",
                    "category": "room_revenue" if invoice.get("booking_id") else "other_services",
                    "amount": float(invoice.get("total") or 0),
                    "currency": invoice.get("currency") or "TRY",
                    "description": f"Invoice {invoice.get('invoice_number') or invoice_id}",
                    "date": invoice.get("payment_date") or datetime.now(UTC).isoformat(),
                },
                "$setOnInsert": {
                    **cash_flow_filter,
                    "created_by": getattr(current_user, "name", None),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            },
            upsert=True,
        )
    else:
        await db.cash_flow.delete_one(cash_flow_filter)

    _invalidate_accounting_caches(
        current_user.tenant_id,
        "accounting_invoices_list",
        "accounting_dashboard",
        "report_profit_loss",
        "report_balance_sheet",
    )

    # Render-time scrub for legacy XML/HTML residues from old test seeds.
    if invoice:
        for f in ("customer_name", "customer_tax_office", "customer_address"):
            if f in invoice and isinstance(invoice[f], str):
                invoice[f] = sanitize_plaintext(invoice[f], max_length=500)

    return invoice


@router.get("/accounting/cash-flow")
async def get_cash_flow(start_date: str | None = None, end_date: str | None = None, transaction_type: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if start_date or end_date:
        if not start_date or not end_date:
            raise HTTPException(status_code=422, detail="Başlangıç ve bitiş tarihi birlikte verilmelidir.")
        start_bound, end_bound = _report_date_bounds(start_date, end_date)
        query["date"] = {"$gte": start_bound, "$lte": end_bound}
    if transaction_type:
        query["transaction_type"] = transaction_type

    flows = await db.cash_flow.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    income_by_currency: dict[str, float] = {}
    expense_by_currency: dict[str, float] = {}
    for flow in flows:
        currency = _accounting_currency(flow.get("currency"), tenant_currency)
        flow["currency"] = currency
        amount = float(flow.get("amount", 0) or 0)
        target = income_by_currency if flow.get("transaction_type") == "income" else expense_by_currency
        target[currency] = target.get(currency, 0) + amount

    currencies = set(income_by_currency) | set(expense_by_currency)
    net_by_currency = {
        code: round(income_by_currency.get(code, 0) - expense_by_currency.get(code, 0), 2)
        for code in currencies
    }
    income_by_currency = {code: round(value, 2) for code, value in income_by_currency.items()}
    expense_by_currency = {code: round(value, 2) for code, value in expense_by_currency.items()}

    return {
        "transactions": flows,
        # Legacy scalars now describe only the tenant currency, not an invalid
        # sum of unrelated nominal currencies.
        "total_income": income_by_currency.get(tenant_currency, 0),
        "total_expense": expense_by_currency.get(tenant_currency, 0),
        "net_cash_flow": net_by_currency.get(tenant_currency, 0),
        "total_income_by_currency": income_by_currency,
        "total_expense_by_currency": expense_by_currency,
        "net_cash_flow_by_currency": net_by_currency,
        "currency": tenant_currency,
    }


@router.get("/accounting/reports/profit-loss")
@cached(ttl=900, key_prefix="report_profit_loss")  # Cache for 15 min
async def get_profit_loss_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):
    # Tur 3: defaults — last 30 days when params omitted
    from datetime import date as _d
    from datetime import timedelta as _td

    if not start_date:
        start_date = (_d.today() - _td(days=30)).isoformat()
    if not end_date:
        end_date = _d.today().isoformat()
    start_bound, end_bound = _report_date_bounds(start_date, end_date)
    # Only paid sales documents are realised revenue in this cash-basis view.
    # A paid purchase or proforma must never become hotel income.
    invoices = await db.accounting_invoices.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": "paid",
            "invoice_type": {"$nin": [InvoiceType.PROFORMA.value, InvoiceType.PURCHASE.value]},
            "issue_date": {"$gte": start_bound, "$lte": end_bound},
        },
        {"_id": 0},
    ).to_list(None)

    # Get all expenses
    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": start_bound, "$lte": end_bound}}, {"_id": 0}).to_list(None)

    from core.tenant_currency import get_tenant_currency

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)

    def _currency_totals(records, amount_field):
        totals: dict[str, float] = {}
        for record in records:
            code = str(record.get("currency") or tenant_currency).upper()
            totals[code] = totals.get(code, 0) + float(record.get(amount_field, 0) or 0)
        return {code: round(amount, 2) for code, amount in sorted(totals.items())}

    total_revenue_by_currency = _currency_totals(invoices, "total")
    total_expenses_by_currency = _currency_totals(expenses, "total_amount")
    gross_profit_by_currency = {
        code: round(total_revenue_by_currency.get(code, 0) - total_expenses_by_currency.get(code, 0), 2)
        for code in sorted(set(total_revenue_by_currency) | set(total_expenses_by_currency))
    }
    profit_margin_by_currency = {
        code: round((gross_profit_by_currency[code] / revenue * 100), 2) if revenue > 0 else 0
        for code, revenue in total_revenue_by_currency.items()
    }

    report_currencies = set(total_revenue_by_currency) | set(total_expenses_by_currency)
    mixed_currency = len(report_currencies) > 1
    if mixed_currency:
        total_revenue = total_expenses = gross_profit = profit_margin = None
    else:
        only_currency = next(iter(report_currencies), tenant_currency)
        total_revenue = total_revenue_by_currency.get(only_currency, 0)
        total_expenses = total_expenses_by_currency.get(only_currency, 0)
        gross_profit = round(total_revenue - total_expenses, 2)
        profit_margin = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0

    # Revenue breakdown
    revenue_by_category = {}
    revenue_by_category_currency: dict[str, dict[str, float]] = {}
    for inv in invoices:
        for item in inv["items"]:
            desc = item["description"]
            revenue_by_category[desc] = revenue_by_category.get(desc, 0) + item["total"]
            code = str(inv.get("currency") or tenant_currency).upper()
            category_totals = revenue_by_category_currency.setdefault(desc, {})
            category_totals[code] = round(category_totals.get(code, 0) + float(item.get("total", 0) or 0), 2)

    # Expense breakdown
    expense_by_category = {}
    expense_by_category_currency: dict[str, dict[str, float]] = {}
    for exp in expenses:
        cat = exp["category"]
        expense_by_category[cat] = expense_by_category.get(cat, 0) + exp["total_amount"]
        code = str(exp.get("currency") or tenant_currency).upper()
        category_totals = expense_by_category_currency.setdefault(cat, {})
        category_totals[code] = round(category_totals.get(code, 0) + float(exp.get("total_amount", 0) or 0), 2)

    return {
        "period": {"start": start_date, "end": end_date},
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "gross_profit": gross_profit,
        "profit_margin": profit_margin,
        "revenue_breakdown": revenue_by_category,
        "expense_breakdown": expense_by_category,
        "total_revenue_by_currency": total_revenue_by_currency,
        "total_expenses_by_currency": total_expenses_by_currency,
        "gross_profit_by_currency": gross_profit_by_currency,
        "profit_margin_by_currency": profit_margin_by_currency,
        "revenue_breakdown_by_currency": revenue_by_category_currency,
        "expense_breakdown_by_currency": expense_by_category_currency,
        "mixed_currency": mixed_currency,
    }


@router.get("/accounting/reports/vat-report")
async def get_vat_report(start_date: str | None = None, end_date: str | None = None, current_user: User = Depends(get_current_user)):
    # Tur 3: defaults — last 30 days when params omitted
    from datetime import date as _d
    from datetime import timedelta as _td

    if not start_date:
        start_date = (_d.today() - _td(days=30)).isoformat()
    if not end_date:
        end_date = _d.today().isoformat()
    start_bound, end_bound = _report_date_bounds(start_date, end_date)
    # Sales VAT (collected)
    # Proforma and purchase invoices are not output VAT.  A proforma is only
    # an offer, while a purchase invoice belongs to input VAT through AP.
    invoices = await db.accounting_invoices.find(
        {
            "tenant_id": current_user.tenant_id,
            "invoice_type": {"$nin": [InvoiceType.PROFORMA.value, InvoiceType.PURCHASE.value]},
            "issue_date": {"$gte": start_bound, "$lte": end_bound},
        },
        {"_id": 0},
    ).to_list(None)

    from core.tenant_currency import get_tenant_currency

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)

    def _vat_totals(records, field):
        totals: dict[str, float] = {}
        for record in records:
            code = str(record.get("currency") or tenant_currency).upper()
            totals[code] = totals.get(code, 0) + float(record.get(field, 0) or 0)
        return {code: round(amount, 2) for code, amount in sorted(totals.items())}

    # Purchase VAT (paid)
    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": start_bound, "$lte": end_bound}}, {"_id": 0}).to_list(None)

    sales_vat_by_currency = _vat_totals(invoices, "total_vat")
    purchase_vat_by_currency = _vat_totals(expenses, "vat_amount")
    vat_payable_by_currency = {
        code: round(sales_vat_by_currency.get(code, 0) - purchase_vat_by_currency.get(code, 0), 2)
        for code in sorted(set(sales_vat_by_currency) | set(purchase_vat_by_currency))
    }
    report_currencies = set(sales_vat_by_currency) | set(purchase_vat_by_currency)
    mixed_currency = len(report_currencies) > 1
    if mixed_currency:
        sales_vat = purchase_vat = vat_payable = None
    else:
        only_currency = next(iter(report_currencies), tenant_currency)
        sales_vat = sales_vat_by_currency.get(only_currency, 0)
        purchase_vat = purchase_vat_by_currency.get(only_currency, 0)
        vat_payable = round(sales_vat - purchase_vat, 2)

    return {
        "period": {"start": start_date, "end": end_date},
        "sales_vat": sales_vat,
        "purchase_vat": purchase_vat,
        "vat_payable": vat_payable,
        "sales_vat_by_currency": sales_vat_by_currency,
        "purchase_vat_by_currency": purchase_vat_by_currency,
        "vat_payable_by_currency": vat_payable_by_currency,
        "mixed_currency": mixed_currency,
    }


@router.get("/accounting/reports/balance-sheet")
@cached(ttl=300, key_prefix="report_balance_sheet")  # Cache for 5 minutes
async def get_balance_sheet(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):
    tenant_id = current_user.tenant_id
    from core.tenant_currency import get_tenant_currency

    tenant_currency, _ = await get_tenant_currency(tenant_id)

    async def _group_currency(collection, match, amount_expression):
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"$toUpper": {"$ifNull": ["$currency", tenant_currency]}},
                    "total": {"$sum": amount_expression},
                }
            },
        ]
        rows = await collection.aggregate(pipeline).to_list(100)
        return {str(row.get("_id") or tenant_currency).upper(): round(float(row.get("total") or 0), 2) for row in rows}

    async def _sum_cash():
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": None, "total": {"$sum": "$balance"}}},
        ]
        cur = db.bank_accounts.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]["total"] if docs else 0

    async def _sum_inventory():
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": {
                            "$multiply": [
                                {"$ifNull": ["$quantity", 0]},
                                {"$ifNull": ["$unit_cost", 0]},
                            ]
                        }
                    },
                }
            },
        ]
        cur = db.inventory_items.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]["total"] if docs else 0

    async def _sum_receivables():
        pipeline = [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "status": {"$in": ["pending", "partial"]},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]
        cur = db.accounting_invoices.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]["total"] if docs else 0

    async def _sum_payables():
        pipeline = [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "payment_status": "pending",
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}},
        ]
        cur = db.expenses.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]["total"] if docs else 0

    total_cash, total_inventory, total_receivables, total_payables = await asyncio.gather(_sum_cash(), _sum_inventory(), _sum_receivables(), _sum_payables())

    cash_by_currency, receivables_by_currency = await asyncio.gather(
        _group_currency(db.bank_accounts, {"tenant_id": tenant_id}, {"$ifNull": ["$balance", 0]}),
        _group_currency(
            db.accounting_invoices,
            {"tenant_id": tenant_id, "status": {"$in": ["pending", "partial"]}},
            {"$ifNull": ["$total", 0]},
        ),
    )
    inventory_by_currency = {tenant_currency: round(total_inventory, 2)} if total_inventory else {}
    payables_by_currency = {tenant_currency: round(total_payables, 2)} if total_payables else {}
    asset_codes = set(cash_by_currency) | set(inventory_by_currency) | set(receivables_by_currency)
    total_assets_by_currency = {
        code: round(cash_by_currency.get(code, 0) + inventory_by_currency.get(code, 0) + receivables_by_currency.get(code, 0), 2)
        for code in sorted(asset_codes)
    }
    equity_codes = asset_codes | set(payables_by_currency)
    total_equity_by_currency = {
        code: round(total_assets_by_currency.get(code, 0) - payables_by_currency.get(code, 0), 2)
        for code in sorted(equity_codes)
    }

    total_assets = total_cash + total_inventory + total_receivables

    # Equity
    total_equity = total_assets - total_payables

    return {
        "assets": {
            "cash": round(total_cash, 2),
            "inventory": round(total_inventory, 2),
            "receivables": round(total_receivables, 2),
            "total": round(total_assets, 2),
            "cash_by_currency": cash_by_currency,
            "inventory_by_currency": inventory_by_currency,
            "receivables_by_currency": receivables_by_currency,
            "total_by_currency": total_assets_by_currency,
        },
        "liabilities": {
            "payables": round(total_payables, 2),
            "total": round(total_payables, 2),
            "payables_by_currency": payables_by_currency,
            "total_by_currency": payables_by_currency,
        },
        "equity": {"total": round(total_equity, 2), "total_by_currency": total_equity_by_currency},
    }


@router.get("/accounting/dashboard")
@cached(ttl=600, key_prefix="accounting_dashboard")  # Cache for 10 minutes
async def get_accounting_dashboard(
    current_user=Depends(get_current_user),  # v68 Bug DE: tenant-scoped cache key
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):

    # Get current month data
    today = datetime.now(UTC)
    month_start = today.replace(day=1, hour=0, minute=0, second=0).isoformat()
    month_end = today.isoformat()

    # Keep dashboard income/receivable figures aligned with the report ledger:
    # purchase and proforma documents are never hotel sales.
    invoices = await db.accounting_invoices.find(
        {
            "tenant_id": current_user.tenant_id,
            "invoice_type": {"$nin": [InvoiceType.PROFORMA.value, InvoiceType.PURCHASE.value]},
            "issue_date": {"$gte": month_start, "$lte": month_end},
        },
        {"_id": 0},
    ).to_list(None)

    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": month_start, "$lte": month_end}}, {"_id": 0}).to_list(None)

    # Never combine nominal amounts from different currencies.  Keep the legacy
    # scalar fields for older clients, and expose currency-safe breakdowns for
    # current clients.
    cur_code, cur_symbol = await get_tenant_currency(current_user.tenant_id)

    collected_by_currency = _currency_totals(invoices, "total", cur_code, lambda inv: inv.get("status") == "paid")
    accrued_by_currency = _currency_totals(invoices, "total", cur_code)
    pending_by_currency = _currency_totals(invoices, "total", cur_code, lambda inv: inv.get("status") in ("pending", "partial"))
    overdue_by_currency = _currency_totals(invoices, "total", cur_code, lambda inv: inv.get("status") == "overdue")
    expenses_by_currency = _currency_totals(expenses, "total_amount", cur_code)

    collected_income = collected_by_currency.get(cur_code, 0)
    accrued_revenue = accrued_by_currency.get(cur_code, 0)
    pending_amount = pending_by_currency.get(cur_code, 0)
    overdue_amount = overdue_by_currency.get(cur_code, 0)
    total_expenses = expenses_by_currency.get(cur_code, 0)
    net_income_by_currency = {
        code: round(collected_by_currency.get(code, 0) - expenses_by_currency.get(code, 0), 2)
        for code in set(collected_by_currency) | set(expenses_by_currency)
    }
    pending_invoices = len([inv for inv in invoices if inv.get("status") == "pending"])
    overdue_invoices = len([inv for inv in invoices if inv.get("status") == "overdue"])

    # Get bank balances
    bank_accounts = await db.bank_accounts.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(None)
    bank_balance_by_currency = _currency_totals(bank_accounts, "balance", cur_code)
    total_bank_balance = bank_balance_by_currency.get(cur_code, 0)

    return {
        # Backward-compat field (paid invoices only).
        "monthly_income": round(collected_income, 2),
        # New explicit fields:
        "collected_income": round(collected_income, 2),
        "accrued_revenue": round(accrued_revenue, 2),
        "pending_amount": round(pending_amount, 2),
        "overdue_amount": round(overdue_amount, 2),
        "monthly_expenses": round(total_expenses, 2),
        "net_income": round(collected_income - total_expenses, 2),
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
        "total_bank_balance": round(total_bank_balance, 2),
        "collected_income_by_currency": collected_by_currency,
        "accrued_revenue_by_currency": accrued_by_currency,
        "pending_amount_by_currency": pending_by_currency,
        "overdue_amount_by_currency": overdue_by_currency,
        "monthly_expenses_by_currency": expenses_by_currency,
        "net_income_by_currency": net_income_by_currency,
        "bank_balance_by_currency": bank_balance_by_currency,
        "currency": cur_code,
        "currency_symbol": cur_symbol,
    }


@router.get("/accounting/currencies")
async def get_currencies(current_user: User = Depends(get_current_user)):
    """Get all supported currencies"""
    currencies = [
        {"code": "TRY", "name": "Turkish Lira", "symbol": "₺"},
        {"code": "USD", "name": "US Dollar", "symbol": "$"},
        {"code": "EUR", "name": "Euro", "symbol": "€"},
        {"code": "GBP", "name": "British Pound", "symbol": "£"},
    ]
    return {"currencies": currencies}


@router.post("/accounting/currency-rates")
async def create_currency_rate(
    request: CreateCurrencyRateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Create or update currency exchange rate"""
    rate = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "from_currency": request.from_currency,
        "to_currency": request.to_currency,
        "rate": request.rate,
        "effective_date": request.effective_date,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    rate_copy = rate.copy()
    await db.currency_rates.insert_one(rate_copy)
    return rate


@router.get("/accounting/currency-rates")
async def get_currency_rates(from_currency: str = None, to_currency: str = None, date: str = None, current_user: User = Depends(get_current_user)):
    """Get currency exchange rates"""
    query = {"tenant_id": current_user.tenant_id}

    if from_currency:
        query["from_currency"] = from_currency
    if to_currency:
        query["to_currency"] = to_currency
    if date:
        query["effective_date"] = {"$lte": date}

    rates = await db.currency_rates.find(query, {"_id": 0}).sort("effective_date", -1).to_list(100)

    return {"rates": rates, "count": len(rates)}


@router.post("/accounting/convert-currency")
async def convert_currency(
    request: ConvertCurrencyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Convert amount between currencies"""
    # If same currency, no conversion needed
    if request.from_currency == request.to_currency:
        return {"amount": request.amount, "from_currency": request.from_currency, "to_currency": request.to_currency, "rate": 1.0, "converted_amount": request.amount}

    # Get exchange rate
    query = {"tenant_id": current_user.tenant_id, "from_currency": request.from_currency, "to_currency": request.to_currency}

    if request.date:
        query["effective_date"] = {"$lte": request.date}

    rate_record = await db.currency_rates.find_one(query, {"_id": 0}, sort=[("effective_date", -1)])

    if not rate_record:
        # Try reverse rate
        reverse_query = {"tenant_id": current_user.tenant_id, "from_currency": request.to_currency, "to_currency": request.from_currency}
        if request.date:
            reverse_query["effective_date"] = {"$lte": request.date}

        reverse_rate = await db.currency_rates.find_one(reverse_query, {"_id": 0}, sort=[("effective_date", -1)])

        if reverse_rate:
            rate = 1.0 / reverse_rate["rate"]
        else:
            # Default rates if not found
            default_rates = {("TRY", "USD"): 0.037, ("TRY", "EUR"): 0.034, ("USD", "TRY"): 27.0, ("EUR", "TRY"): 29.5, ("USD", "EUR"): 0.92, ("EUR", "USD"): 1.09}
            rate = default_rates.get((request.from_currency, request.to_currency), 1.0)
    else:
        rate = rate_record["rate"]

    converted_amount = request.amount * rate

    return {
        "amount": request.amount,
        "from_currency": request.from_currency,
        "to_currency": request.to_currency,
        "rate": round(rate, 4),
        "converted_amount": round(converted_amount, 2),
        "date": request.date or datetime.now(UTC).date().isoformat(),
    }


@router.post("/accounting/invoices/multi-currency")
async def create_multi_currency_invoice(
    request: CreateMultiCurrencyInvoiceRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Create invoice in any currency with auto-conversion to TRY"""
    # Calculate totals in invoice currency
    subtotal = sum(item.get("quantity", 0) * item.get("unit_price", 0) for item in request.items)

    # Calculate VAT
    total_vat = 0
    for item in request.items:
        item_total = item.get("quantity", 0) * item.get("unit_price", 0)
        vat_rate = item.get("vat_rate", GENERAL_VAT_RATE) / 100
        item["vat_amount"] = round(item_total * vat_rate, 2)
        total_vat += item["vat_amount"]

    total = subtotal + total_vat

    # Convert to TRY if needed
    if request.currency != "TRY":
        if request.exchange_rate:
            rate = request.exchange_rate
        else:
            # Get current rate
            conversion = await convert_currency(ConvertCurrencyRequest(amount=1.0, from_currency=request.currency, to_currency="TRY"), current_user)
            rate = conversion["rate"]

        subtotal_try = subtotal * rate
        total_vat_try = total_vat * rate
        total_try = total * rate
    else:
        rate = 1.0
        subtotal_try = subtotal
        total_vat_try = total_vat
        total_try = total

    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    invoice = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "invoice_number": invoice_number,
        "customer_name": _validate_invoice_customer_name(request.customer_name),
        "customer_email": request.customer_email,
        "customer_address": sanitize_plaintext(request.customer_address, max_length=500),
        "items": request.items,
        "currency": request.currency,
        "exchange_rate": rate,
        "subtotal": round(subtotal, 2),
        "total_vat": round(total_vat, 2),
        "total": round(total, 2),
        "subtotal_try": round(subtotal_try, 2),
        "total_vat_try": round(total_vat_try, 2),
        "total_try": round(total_try, 2),
        "payment_terms": request.payment_terms,
        "notes": request.notes,
        "issue_date": datetime.now(UTC).date().isoformat(),
        "due_date": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    invoice_copy = invoice.copy()
    await db.accounting_invoices.insert_one(invoice_copy)

    return invoice


@router.post("/accounting/invoices/from-folio")
async def generate_invoice_from_folio(
    request: GenerateInvoiceFromFolioRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Generate accounting invoice from PMS folio"""
    # Get folio
    folio = await db.folios.find_one({"id": request.folio_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Get folio charges
    charges = await db.folio_charges.find({"folio_id": request.folio_id, "tenant_id": current_user.tenant_id, "voided": False}, {"_id": 0}).to_list(1000)

    # Get booking info. Folios reference their booking via folio.booking_id;
    # the booking document is NOT linked back with a folio_id at check-in /
    # walk-in, so a reverse {'folio_id': ...} lookup never matches and the
    # invoice silently loses the customer (falls back to "Guest") and the
    # booking_id. Resolve via the folio's own booking_id instead.
    booking = None
    folio_booking_id = folio.get("booking_id")
    if folio_booking_id:
        booking = await db.bookings.find_one({"id": folio_booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    # Fiscal-document guard: refuse to mint a sales invoice for a CANCELLED
    # reservation (no stay happened -> the cut would later need a credit note to
    # unwind). The no-show penalty / checked-out invoicing stays allowed, and a
    # missing booking (manual/legacy folio) is not blocked. Booking is read
    # fresh just above, so this is a true last-second check.
    if booking is not None and not is_status_invoiceable(booking.get("status")):
        raise HTTPException(
            status_code=409,
            detail="Rezervasyon iptal edilmiş; fatura/e-Fatura kesilemez",
        )

    # Convert charges to invoice items
    hotel_settings = await db.hotel_settings.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "default_accommodation_vat_rate": 1},
    ) or {}
    accommodation_vat_rate = float(
        hotel_settings.get("default_accommodation_vat_rate", ACCOMMODATION_VAT_RATE)
    )
    invoice_items = []
    for charge in charges:
        invoice_items.extend(folio_charge_to_invoice_items(charge, accommodation_vat_rate))

    # Resolve customer info. Walk-in / check-in store the guest's name on the
    # GUEST document (booking carries only guest_id), so fall back through
    # booking -> guest -> folio. Without the guest lookup the validator receives
    # an empty name and raises 400, which would break invoicing for every
    # walk-in folio.
    guest = None
    guest_id = (booking.get("guest_id") if booking else None) or folio.get("guest_id")
    if guest_id:
        from security.encrypted_lookup import decrypt_guest_doc

        guest = decrypt_guest_doc(await db.guests.find_one({"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}))

    raw_customer_name = (booking.get("guest_name") if booking else None) or (guest.get("name") if guest else None) or folio.get("guest_name") or "Guest"
    # Apply same validator as manual create — guest_name from booking/folio could
    # have been seeded with HTML/XML payloads in older data; reject those here.
    customer_name = _validate_invoice_customer_name(raw_customer_name)
    customer_email = (booking.get("guest_email") if booking else None) or (guest.get("email") if guest else None) or folio.get("guest_email") or ""

    # Create invoice
    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Calculate totals
    subtotal = sum(item["unit_price"] * item["quantity"] for item in invoice_items)
    total_vat = sum(item["unit_price"] * item["quantity"] * (item["vat_rate"] / 100) for item in invoice_items)

    # Currency conversion if needed
    if request.invoice_currency != "TRY":
        conversion = await convert_currency(ConvertCurrencyRequest(amount=subtotal + total_vat, from_currency="TRY", to_currency=request.invoice_currency), current_user)
        exchange_rate = conversion["rate"]
        total_foreign = conversion["converted_amount"]
    else:
        exchange_rate = 1.0
        total_foreign = subtotal + total_vat

    invoice = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "invoice_number": invoice_number,
        "folio_id": request.folio_id,
        "booking_id": booking["id"] if booking else None,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_address": booking.get("guest_address", "") if booking else "",
        "items": invoice_items,
        "currency": request.invoice_currency,
        "exchange_rate": exchange_rate,
        "subtotal": round(subtotal, 2),
        "total_vat": round(total_vat, 2),
        "total": round(subtotal + total_vat, 2),
        "total_foreign_currency": round(total_foreign, 2),
        "payment_terms": "Due on checkout",
        "issue_date": datetime.now(UTC).date().isoformat(),
        "due_date": datetime.now(UTC).date().isoformat(),
        "status": "pending",
        "source": "pms_folio",
        # invoice_type drives the e-Fatura sweep query (sales invoices only).
        "invoice_type": "sales",
        # When e-Fatura is requested we QUEUE a real cut: the
        # process_pending_efaturas_task picks up 'pending' sales invoices,
        # builds the UBL-TR document and transmits it to the configured
        # provider. No fake document/UUID is written here.
        "efatura_status": "pending" if request.include_efatura else None,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    invoice_copy = invoice.copy()
    await db.accounting_invoices.insert_one(invoice_copy)

    # Update folio with invoice reference
    await db.folios.update_one({"id": request.folio_id}, {"$set": {"invoice_id": invoice["id"], "invoice_number": invoice_number}})

    # E-Fatura: the invoice is persisted with efatura_status='pending' above so
    # the process_pending_efaturas_task sweep performs the REAL cut against the
    # configured provider (build UBL-TR -> transmit -> store official ETTN). No
    # mock document/UUID is generated inline anymore: a fake "generated" here
    # would silently hide the absence of a real fiscal document.

    # v95.1 parity — folio-sourced invoices must invalidate the same caches as
    # the manual create/update paths, otherwise a freshly generated invoice is
    # missing from GET /accounting/invoices (5dk cache) for tenants whose list
    # was already warmed.
    if cache:
        cache.invalidate_tenant_cache(current_user.tenant_id, "accounting_invoices_list")
        try:
            cache.delete_pattern(f"cache:{current_user.tenant_id}:accounting_dashboard:*")
        except Exception:
            pass

    return {"invoice": invoice, "message": "Invoice generated from folio successfully", "efatura_generated": request.include_efatura}


@router.get("/accounting/invoices/{invoice_id}/efatura-status")
async def get_invoice_efatura_status(invoice_id: str, current_user: User = Depends(get_current_user)):
    """Get E-Fatura status for accounting invoice"""
    invoice = await db.accounting_invoices.find_one({"id": invoice_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get E-Fatura record
    efatura = await db.efatura_records.find_one({"invoice_id": invoice_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    # The accounting invoice itself carries the live lifecycle state set by the
    # process_pending_efaturas_task sweep (pending -> generated | error). Surface
    # it even before/without an efatura_records mirror so the accounting screen
    # can show queued and failed states, not only successfully cut documents.
    inv_status = invoice.get("efatura_status")

    if not efatura:
        return {
            "invoice_id": invoice_id,
            "invoice_number": invoice.get("invoice_number"),
            "efatura_status": inv_status or "not_generated",
            "efatura_error": invoice.get("efatura_last_error"),
            "efatura_attempts": invoice.get("efatura_attempts", 0),
            "message": (
                "E-Fatura kuyruga alindi, XML uretimi bekleniyor"
                if inv_status == "pending"
                else "E-Fatura XML hazir, indirilebilir"
                if inv_status == "xml_ready"
                else "E-Fatura harici olarak bildirildi"
                if inv_status == "reported_externally"
                else "E-Fatura XML uretimi basarisiz oldu"
                if inv_status == "error"
                else "E-Fatura has not been generated for this invoice"
            ),
        }

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice.get("invoice_number"),
        "efatura_uuid": efatura.get("efatura_uuid"),
        "efatura_status": inv_status or efatura.get("status"),
        "official_number": efatura.get("official_number") or invoice.get("efatura_official_number"),
        "provider": efatura.get("provider") or invoice.get("efatura_provider"),
        "efatura_error": invoice.get("efatura_last_error"),
        "efatura_attempts": invoice.get("efatura_attempts", 0),
        "generated_at": efatura.get("generated_at"),
        "sent_at": efatura.get("sent_at"),
        "gib_response": efatura.get("gib_response"),
    }


@router.post("/accounting/invoices/{invoice_id}/generate-efatura")
async def generate_efatura_for_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Generate E-Fatura for existing accounting invoice"""
    invoice = await db.accounting_invoices.find_one({"id": invoice_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check if E-Fatura already exists
    existing_efatura = await db.efatura_records.find_one({"invoice_id": invoice_id, "tenant_id": current_user.tenant_id})

    if existing_efatura:
        return {"message": "E-Fatura already exists for this invoice", "efatura_uuid": existing_efatura.get("efatura_uuid"), "status": existing_efatura.get("status")}

    # Last-second guard: do not cut a NEW e-Fatura against a reservation that has
    # since been cancelled. An already-existing record (handled above) is
    # returned as is — it cannot be un-cut; only a fresh cut is blocked here.
    await ensure_booking_invoiceable(db, current_user.tenant_id, invoice.get("booking_id"))

    # Generate a flawless UBL-TR document and persist it. There is NO automatic
    # transmission to an integrator/GIB; the accountant downloads the XML and
    # files it themselves. Fail-closed: with no supplier identity we refuse
    # instead of writing a fake "generated" document. The helper escapes every
    # user-controlled field (customer name, charge descriptions) before it
    # reaches the UBL-TR tree.
    from core import efatura_provider as ep

    if not ep.is_configured():
        raise HTTPException(
            status_code=503,
            detail="E-Fatura tedarikci kimligi (VKN) yapilandirilmamis (fail-closed)",
        )
    cfg = ep.provider_config()
    ettn = invoice.get("efatura_ettn") or str(uuid.uuid4())
    profile = ep.document_profile(invoice)
    try:
        efatura_xml = ep.build_ubl_tr_document(
            invoice,
            supplier_vkn=cfg["supplier_vkn"],
            supplier_name=cfg["supplier_name"],
            ettn=ettn,
            profile=profile,
        )
    except Exception as e:  # noqa: BLE001 - bad invoice data -> error, no fake doc
        attempts = int(invoice.get("efatura_attempts") or 0) + 1
        await db.accounting_invoices.update_one(
            {"id": invoice_id, "tenant_id": current_user.tenant_id},
            {
                "$set": {
                    "efatura_status": "error",
                    "efatura_attempts": attempts,
                    "efatura_ettn": ettn,
                    "efatura_last_error": str(e)[:500],
                }
            },
        )
        raise HTTPException(
            status_code=422,
            detail="E-Fatura XML uretilemedi (gecersiz fatura verisi)",
        ) from e

    now_iso = datetime.now(UTC).isoformat()
    efatura_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "invoice_id": invoice_id,
        "invoice_number": invoice.get("invoice_number"),
        "efatura_uuid": ettn,
        "ettn": ettn,
        "profile": profile,
        "provider": cfg["provider"],
        "xml_content": efatura_xml,
        "status": "xml_ready",
        "error": None,
        "generated_at": now_iso,
    }

    efatura_copy = efatura_record.copy()
    await db.efatura_records.insert_one(efatura_copy)

    # Update invoice with E-Fatura reference
    await db.accounting_invoices.update_one(
        {"id": invoice_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "efatura_uuid": ettn,
                "efatura_ettn": ettn,
                "efatura_provider": cfg["provider"],
                "efatura_profile": profile,
                "efatura_status": "xml_ready",
                "efatura_generated_at": now_iso,
                "efatura_last_error": None,
            }
        },
    )

    return {"message": "E-Fatura XML uretildi", "efatura_uuid": ettn, "efatura_status": "xml_ready", "invoice_number": invoice.get("invoice_number")}


@router.get("/efatura/invoices")
async def get_efatura_invoices(current_user: User = Depends(get_current_user)):
    invoices = await db.invoices.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)

    # Add efatura status to each invoice
    for invoice in invoices:
        invoice["efatura_status"] = invoice.get("efatura_status", "pending")

    return {"invoices": invoices}


@router.get("/efatura/settings")
async def get_efatura_settings(current_user: User = Depends(get_current_user)):
    settings = await db.efatura_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0})
    return settings or {"vkn": "1234567890", "enabled": True, "auto_send": False, "last_sync": None}


@router.get("/accounting/invoices/{invoice_id}/efatura-xml")
async def download_efatura_xml(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Download the generated UBL-TR XML for an invoice.

    Tenant-scoped (cross-tenant IDOR safe). Returns the raw XML document as an
    ``application/xml`` attachment so the accountant can file it through their
    own program. The download filename is sanitised against HTTP header
    injection.
    """
    efatura = await db.efatura_records.find_one(
        {"invoice_id": invoice_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not efatura or not efatura.get("xml_content"):
        raise HTTPException(status_code=404, detail="E-Fatura XML bulunamadi")

    from core import efatura_provider as ep

    filename = ep.safe_xml_filename(
        efatura.get("invoice_number") or invoice_id,
        efatura.get("customer_name"),
    )
    return Response(
        content=efatura["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/accounting/invoices/{invoice_id}/report-efatura-external")
async def report_efatura_external(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Mark an e-Fatura as reported externally (filed via the accountant's own
    program). Only allowed once the document is ``xml_ready``; deliberately
    refuses otherwise so the lifecycle stays honest."""
    invoice = await db.accounting_invoices.find_one(
        {"id": invoice_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.get("efatura_status") != "xml_ready":
        raise HTTPException(
            status_code=409,
            detail="Yalnizca 'XML Hazir' durumundaki fatura harici bildirilebilir",
        )

    now_iso = datetime.now(UTC).isoformat()
    await db.accounting_invoices.update_one(
        {"id": invoice_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "efatura_status": "reported_externally",
                "efatura_reported_at": now_iso,
            }
        },
    )
    await db.efatura_records.update_one(
        {"invoice_id": invoice_id, "tenant_id": current_user.tenant_id},
        {"$set": {"status": "reported_externally", "reported_at": now_iso}},
    )

    return {
        "message": "E-Fatura harici olarak bildirildi",
        "efatura_status": "reported_externally",
        "invoice_number": invoice.get("invoice_number"),
    }


@router.post("/accounting/send-statement")
async def send_statement_email(
    company_id: str,
    email: str | None = None,
    include_details: bool = True,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """
    Send account statement to company with one click
    - Outstanding balance
    - Invoice details
    - Payment reminder
    """
    company = await db.companies.find_one({"id": company_id, "tenant_id": current_user.tenant_id})

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get all open folios for company
    folios = []
    total_balance = 0
    async for folio in db.folios.find({"company_id": company_id, "tenant_id": current_user.tenant_id, "status": "open"}):
        balance = folio.get("balance", 0)
        total_balance += balance
        folios.append({"folio_number": folio.get("folio_number"), "booking_id": folio.get("booking_id"), "balance": balance, "created_at": folio.get("created_at")})

    recipient_email = email or company.get("contact_email")

    if not recipient_email:
        raise HTTPException(status_code=400, detail="No email address provided")

    # Create statement document
    statement = {
        "company_name": company.get("name"),
        "statement_date": datetime.now(UTC).isoformat(),
        "total_outstanding": round(total_balance, 2),
        "folios": folios,
        "payment_terms": company.get("payment_terms", "Net 30"),
        "contact_person": company.get("contact_person"),
    }

    # In production, send actual email via SMTP or email service
    # For now, simulate email sending

    return {"success": True, "message": f"Statement sent to {recipient_email}", "statement": statement, "note": "In production, integrate with SendGrid, AWS SES, or SMTP server"}
