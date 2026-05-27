"""Auto-split from finance.py — section: accounting."""
import asyncio
import re as _re
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.sanitize import sanitize_plaintext
from core.security import get_current_user
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


class SupplierCreateRequest(BaseModel):
    name: str
    tax_office: str | None = None
    tax_number: str | None = None
    email: str | None = None
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


def _norm(v):
    """Treat empty / 'none' sentinels coming from select inputs as null."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in ('', 'none'):
        return None
    return v


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
    supplier_dict = supplier.model_dump()
    supplier_dict['created_at'] = supplier_dict['created_at'].isoformat()
    await db.suppliers.insert_one(supplier_dict)
    return supplier



@router.get("/accounting/suppliers")
async def get_suppliers(current_user: User = Depends(get_current_user)):
    suppliers = await db.suppliers.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return suppliers



@router.put("/accounting/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.suppliers.update_one({'id': supplier_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    supplier = await db.suppliers.find_one({'id': supplier_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
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
    account_dict['created_at'] = account_dict['created_at'].isoformat()
    await db.bank_accounts.insert_one(account_dict)
    return bank_account



@router.get("/accounting/bank-accounts")
async def get_bank_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.bank_accounts.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return accounts



@router.put("/accounting/bank-accounts/{account_id}")
async def update_bank_account(account_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.bank_accounts.update_one({'id': account_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    account = await db.bank_accounts.find_one({'id': account_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    return account


@router.post("/accounting/expenses")
async def create_expense(
    payload: ExpenseCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    count = await db.expenses.count_documents({'tenant_id': current_user.tenant_id})
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
        date=datetime.fromisoformat(payload.date),
        payment_method=_norm(payload.payment_method),
        receipt_url=_norm(payload.receipt_url),
        notes=sanitize_plaintext(payload.notes, max_length=1000) if payload.notes else None,
        created_by=current_user.name,
    )

    expense_dict = expense.model_dump()
    expense_dict['date'] = expense_dict['date'].isoformat()
    expense_dict['created_at'] = expense_dict['created_at'].isoformat()
    await db.expenses.insert_one(expense_dict)

    if supplier_id:
        await db.suppliers.update_one(
            {'id': supplier_id, 'tenant_id': current_user.tenant_id},
            {'$inc': {'account_balance': total_amount}},
        )

    cash_flow = CashFlow(
        tenant_id=current_user.tenant_id,
        transaction_type='expense',
        category=payload.category,
        amount=total_amount,
        description=expense.description,
        reference_id=expense.id,
        reference_type='expense',
        date=datetime.fromisoformat(payload.date),
        created_by=current_user.name,
    )
    cf_dict = cash_flow.model_dump()
    cf_dict['date'] = cf_dict['date'].isoformat()
    cf_dict['created_at'] = cf_dict['created_at'].isoformat()
    await db.cash_flow.insert_one(cf_dict)

    return expense



@router.get("/accounting/expenses")
async def get_expenses(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if start_date and end_date:
        query['date'] = {'$gte': start_date, '$lte': end_date}
    if category:
        query['category'] = category

    expenses = await db.expenses.find(query, {'_id': 0}).sort('date', -1).to_list(1000)
    return expenses



@router.put("/accounting/expenses/{expense_id}")
async def update_expense(expense_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.expenses.update_one({'id': expense_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    expense = await db.expenses.find_one({'id': expense_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    return expense


@router.post("/accounting/inventory")
async def create_inventory_item(
    payload: InventoryItemCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    item = InventoryItem(
        tenant_id=current_user.tenant_id,
        name=sanitize_plaintext(payload.name, max_length=200),
        sku=sanitize_plaintext(payload.sku, max_length=80) if payload.sku else None,
        category=payload.category,
        unit=payload.unit,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        reorder_level=payload.reorder_level,
        supplier_id=_norm(payload.supplier_id),
        location=sanitize_plaintext(payload.location, max_length=200) if payload.location else None,
        notes=sanitize_plaintext(payload.notes, max_length=1000) if payload.notes else None,
    )
    item_dict = item.model_dump()
    item_dict['created_at'] = item_dict['created_at'].isoformat()
    await db.inventory_items.insert_one(item_dict)
    return item



@router.get("/accounting/inventory")
async def get_inventory(current_user: User = Depends(get_current_user)):
    items = await db.inventory_items.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)

    # Get low stock items
    low_stock = [item for item in items if item['quantity'] <= item['reorder_level']]

    return {
        'items': items,
        'low_stock_count': len(low_stock),
        'total_value': sum(item['quantity'] * item['unit_cost'] for item in items)
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
    if movement_type not in ('in', 'out', 'adjustment'):
        raise HTTPException(
            status_code=422,
            detail="movement_type must be one of: in, out, adjustment",
        )
    if not isinstance(quantity, (int, float)) or quantity != quantity:  # NaN check
        raise HTTPException(status_code=422, detail="quantity must be a number")
    if movement_type in ('in', 'out') and quantity <= 0:
        raise HTTPException(
            status_code=422,
            detail="quantity must be > 0 for in/out movements",
        )
    if movement_type == 'adjustment' and quantity < 0:
        raise HTTPException(
            status_code=422,
            detail="adjustment quantity must be >= 0",
        )

    tenant_filter = {'id': item_id, 'tenant_id': current_user.tenant_id}
    owned = await db.inventory_items.find_one(
        tenant_filter, {'_id': 0, 'id': 1, 'quantity': 1}
    )
    if not owned:
        raise HTTPException(status_code=404, detail='Inventory item not found')

    if movement_type == 'in':
        await db.inventory_items.update_one(tenant_filter, {'$inc': {'quantity': quantity}})
    elif movement_type == 'out':
        # Atomic guard: only decrement if current quantity >= requested.
        # modified_count == 0 means insufficient stock — reject with 409.
        guard_filter = dict(tenant_filter)
        guard_filter['quantity'] = {'$gte': quantity}
        result = await db.inventory_items.update_one(
            guard_filter, {'$inc': {'quantity': -quantity}}
        )
        if result.modified_count == 0:
            current_qty = float(owned.get('quantity') or 0)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Insufficient stock: requested={quantity}, "
                    f"available={current_qty}"
                ),
            )
    else:  # adjustment — quantity already validated >= 0 above
        await db.inventory_items.update_one(tenant_filter, {'$set': {'quantity': quantity}})

    movement = StockMovement(
        tenant_id=current_user.tenant_id,
        item_id=item_id,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        reference=reference,
        notes=notes,
        created_by=current_user.name
    )
    movement_dict = movement.model_dump()
    movement_dict['created_at'] = movement_dict['created_at'].isoformat()
    await db.stock_movements.insert_one(movement_dict)

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

    src_filter = {'id': payload.source_item_id, 'tenant_id': current_user.tenant_id}
    dst_filter = {'id': payload.destination_item_id, 'tenant_id': current_user.tenant_id}

    src = await db.inventory_items.find_one(
        src_filter, {'_id': 0, 'id': 1, 'quantity': 1, 'location': 1}
    )
    if not src:
        raise HTTPException(status_code=404, detail='Source inventory item not found')
    dst = await db.inventory_items.find_one(
        dst_filter, {'_id': 0, 'id': 1, 'quantity': 1, 'location': 1}
    )
    if not dst:
        raise HTTPException(status_code=404, detail='Destination inventory item not found')

    # Atomic source decrement with insufficient-stock guard.
    guard_src = dict(src_filter)
    guard_src['quantity'] = {'$gte': quantity}
    dec = await db.inventory_items.update_one(guard_src, {'$inc': {'quantity': -quantity}})
    if dec.modified_count == 0:
        current_qty = float(src.get('quantity') or 0)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient stock at source: requested={quantity}, "
                f"available={current_qty}"
            ),
        )

    # Destination increment. If it fails for any reason, reverse the source
    # decrement so no stock is destroyed.
    try:
        inc = await db.inventory_items.update_one(dst_filter, {'$inc': {'quantity': quantity}})
        if inc.matched_count == 0:
            # Destination disappeared between read and write — compensate.
            await db.inventory_items.update_one(src_filter, {'$inc': {'quantity': quantity}})
            raise HTTPException(
                status_code=409,
                detail='Destination inventory item disappeared during transfer',
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Compensate source on any unexpected failure.
        try:
            await db.inventory_items.update_one(src_filter, {'$inc': {'quantity': quantity}})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f'Transfer failed: {exc}') from exc

    transfer_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    out_leg = StockMovement(
        tenant_id=current_user.tenant_id,
        item_id=payload.source_item_id,
        movement_type='transfer_out',
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
        movement_type='transfer_in',
        quantity=quantity,
        unit_cost=payload.unit_cost,
        reference=payload.reference,
        notes=payload.notes,
        created_by=current_user.name,
        transfer_id=transfer_id,
        counterpart_item_id=payload.source_item_id,
    )
    out_dict = out_leg.model_dump()
    in_dict = in_leg.model_dump()
    out_dict['created_at'] = now_iso
    in_dict['created_at'] = now_iso
    # Insert both audit legs; if audit insert fails we still keep the
    # successful stock movement (better than reversing real inventory)
    # but log via HTTP 500 so caller can alert.
    try:
        await db.stock_movements.insert_many([out_dict, in_dict])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Transfer completed but audit write failed: {exc}',
        ) from exc

    return {
        'transfer_id': transfer_id,
        'source_item_id': payload.source_item_id,
        'destination_item_id': payload.destination_item_id,
        'quantity': quantity,
        'unit_cost': payload.unit_cost,
        'legs': [out_leg, in_leg],
    }


# Block ANY HTML/XML-like tag (`<word`, `</word>`, `<...>`), event handlers,
# javascript: pseudo-URLs. Catches unknown tags too (e.g. `<x>`, `<EVIL>`).
_INVOICE_NAME_BLOCK = _re.compile(
    r"<\s*/?\s*[A-Za-z][\w:-]*"      # opening or closing tag start: <tag, </tag
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


class AccountingInvoiceCreateRequest(BaseModel):
    invoice_type: str
    customer_name: str
    customer_email: str | None = None
    customer_tax_office: str | None = None
    customer_tax_number: str | None = None
    customer_address: str | None = None
    items: list[dict[str, Any]] = []
    due_date: str
    booking_id: str | None = None
    notes: str | None = None


@router.post("/accounting/invoices")
async def create_accounting_invoice(
    request: AccountingInvoiceCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    # Models are now imported at the top of the file

    count = await db.accounting_invoices.count_documents({'tenant_id': current_user.tenant_id})
    invoice_number = f"INV-{datetime.now().year}-{count + 1:05d}"

    invoice_items = []
    subtotal = 0.0
    total_vat = 0.0
    vat_withholding = 0.0
    total_additional_taxes = 0.0

    for item_data in request.items:
        # Handle additional_taxes parsing
        additional_taxes = []
        if 'additional_taxes' in item_data and item_data['additional_taxes']:
            for tax_data in item_data['additional_taxes']:
                additional_taxes.append(AdditionalTax(**tax_data))

        # Create item with parsed additional taxes
        item_dict = {k: v for k, v in item_data.items() if k != 'additional_taxes'}
        item_dict['additional_taxes'] = additional_taxes

        # Auto-compute vat_amount/total if client did not send (avoid 5xx)
        try:
            _qty = float(item_dict.get('quantity', 0) or 0)
            _up = float(item_dict.get('unit_price', 0) or 0)
            _vrate = float(item_dict.get('vat_rate', 0) or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="quantity/unit_price/vat_rate sayisal olmali")
        _line_net = _qty * _up
        if 'vat_amount' not in item_dict or item_dict.get('vat_amount') in (None, ""):
            item_dict['vat_amount'] = round(_line_net * (_vrate / 100.0), 2)
        try:
            _vat_amount_num = float(item_dict.get('vat_amount', 0) or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="vat_amount sayisal olmali")
        if 'total' not in item_dict or item_dict.get('total') in (None, ""):
            item_dict['total'] = round(_line_net + _vat_amount_num, 2)
        else:
            try:
                item_dict['total'] = float(item_dict['total'])
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="total sayisal olmali")

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
                if tax.tax_type == 'withholding':
                    # Withholding tax is deducted from VAT
                    # Calculate based on withholding rate (e.g., "7/10" = 70%)
                    if tax.withholding_rate:
                        rate_parts = tax.withholding_rate.split('/')
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
        due_date=datetime.fromisoformat(request.due_date),
        booking_id=request.booking_id,
        notes=request.notes,
        created_by=current_user.name
    )

    invoice_dict = invoice.model_dump()
    invoice_dict['issue_date'] = invoice_dict['issue_date'].isoformat()
    invoice_dict['due_date'] = invoice_dict['due_date'].isoformat()
    invoice_dict['created_at'] = invoice_dict['created_at'].isoformat()
    await db.accounting_invoices.insert_one(invoice_dict)

    # Create cash flow entry
    # CashFlow model imported at top
    cash_flow = CashFlow(
        tenant_id=current_user.tenant_id,
        transaction_type='income',
        category='room_revenue' if request.booking_id else 'other_services',
        amount=total,
        description=f"Invoice {invoice_number}",
        reference_id=invoice.id,
        reference_type='invoice',
        date=datetime.now(UTC),
        created_by=current_user.name
    )
    cf_dict = cash_flow.model_dump()
    cf_dict['date'] = cf_dict['date'].isoformat()
    cf_dict['created_at'] = cf_dict['created_at'].isoformat()
    await db.cash_flow.insert_one(cf_dict)

    # v95.1 — list cache + dashboard cache invalidasyon
    if cache:
        cache.invalidate_tenant_cache(current_user.tenant_id, "accounting_invoices_list")
        try:
            cache.delete_pattern(f"cache:{current_user.tenant_id}:accounting_dashboard:*")
        except Exception:
            pass

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
    query = {'tenant_id': current_user.tenant_id}
    if start_date and end_date:
        query['issue_date'] = {'$gte': start_date, '$lte': end_date}
    if invoice_type:
        query['invoice_type'] = invoice_type
    if status:
        query['status'] = status

    invoices = await db.accounting_invoices.find(query, {'_id': 0}).sort('issue_date', -1).to_list(1000)
    # Render-time scrub for legacy rows that contain XML/HTML fragments
    # (e.g. test seeds from earlier security probes). Persisted on next write.
    for inv in invoices:
        for f in ('customer_name', 'customer_tax_office', 'customer_address'):
            if f in inv and isinstance(inv[f], str):
                inv[f] = sanitize_plaintext(inv[f], max_length=500)
    return invoices



@router.put("/accounting/invoices/{invoice_id}")
async def update_accounting_invoice(invoice_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    if 'status' in updates and updates['status'] == 'paid' and 'payment_date' not in updates:
        updates['payment_date'] = datetime.now(UTC).isoformat()

    for f in ('customer_name', 'customer_tax_office', 'customer_address', 'customer_tax_number'):
        if f in updates and isinstance(updates[f], str):
            updates[f] = sanitize_plaintext(updates[f], max_length=500)

    tenant_filter = {'id': invoice_id, 'tenant_id': current_user.tenant_id}
    upd = await db.accounting_invoices.update_one(tenant_filter, {'$set': updates})
    if upd.matched_count == 0:
        raise HTTPException(status_code=404, detail="Accounting invoice not found")
    invoice = await db.accounting_invoices.find_one(tenant_filter, {'_id': 0})

    # Drop the dashboard + invoices list cache so the UI reflects the change.
    # cached() builds keys as "cache:{tenant_id}:{key_prefix}:{hash}".
    try:
        from cache_manager import cache as _cache
        if _cache:
            _cache.invalidate_tenant_cache(current_user.tenant_id, "accounting_invoices_list")
            _cache.delete_pattern(f"cache:{current_user.tenant_id}:accounting_dashboard:*")
    except Exception:
        pass

    # Render-time scrub for legacy XML/HTML residues from old test seeds.
    if invoice:
        for f in ('customer_name', 'customer_tax_office', 'customer_address'):
            if f in invoice and isinstance(invoice[f], str):
                invoice[f] = sanitize_plaintext(invoice[f], max_length=500)

    return invoice


@router.get("/accounting/cash-flow")
async def get_cash_flow(
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if start_date and end_date:
        query['date'] = {'$gte': start_date, '$lte': end_date}
    if transaction_type:
        query['transaction_type'] = transaction_type

    flows = await db.cash_flow.find(query, {'_id': 0}).sort('date', -1).to_list(1000)

    total_income = sum(f['amount'] for f in flows if f['transaction_type'] == 'income')
    total_expense = sum(f['amount'] for f in flows if f['transaction_type'] == 'expense')
    net_cash_flow = total_income - total_expense

    return {
        'transactions': flows,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_cash_flow': net_cash_flow
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
    # Get all income
    invoices = await db.accounting_invoices.find({
        'tenant_id': current_user.tenant_id,
        'status': 'paid',
        'issue_date': {'$gte': start_date, '$lte': end_date}
    }, {'_id': 0}).to_list(1000)

    # Get all expenses
    expenses = await db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_date, '$lte': end_date}
    }, {'_id': 0}).to_list(1000)

    total_revenue = sum(inv['total'] for inv in invoices)
    total_expenses = sum(exp['total_amount'] for exp in expenses)
    gross_profit = total_revenue - total_expenses
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    # Revenue breakdown
    revenue_by_category = {}
    for inv in invoices:
        for item in inv['items']:
            desc = item['description']
            revenue_by_category[desc] = revenue_by_category.get(desc, 0) + item['total']

    # Expense breakdown
    expense_by_category = {}
    for exp in expenses:
        cat = exp['category']
        expense_by_category[cat] = expense_by_category.get(cat, 0) + exp['total_amount']

    return {
        'period': {'start': start_date, 'end': end_date},
        'total_revenue': round(total_revenue, 2),
        'total_expenses': round(total_expenses, 2),
        'gross_profit': round(gross_profit, 2),
        'profit_margin': round(profit_margin, 2),
        'revenue_breakdown': revenue_by_category,
        'expense_breakdown': expense_by_category
    }



@router.get("/accounting/reports/vat-report")
async def get_vat_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    # Tur 3: defaults — last 30 days when params omitted
    from datetime import date as _d
    from datetime import timedelta as _td
    if not start_date:
        start_date = (_d.today() - _td(days=30)).isoformat()
    if not end_date:
        end_date = _d.today().isoformat()
    # Sales VAT (collected)
    invoices = await db.accounting_invoices.find({
        'tenant_id': current_user.tenant_id,
        'issue_date': {'$gte': start_date, '$lte': end_date}
    }, {'_id': 0}).to_list(1000)

    sales_vat = sum(inv['total_vat'] for inv in invoices)

    # Purchase VAT (paid)
    expenses = await db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_date, '$lte': end_date}
    }, {'_id': 0}).to_list(1000)

    purchase_vat = sum(exp['vat_amount'] for exp in expenses)

    vat_payable = sales_vat - purchase_vat

    return {
        'period': {'start': start_date, 'end': end_date},
        'sales_vat': round(sales_vat, 2),
        'purchase_vat': round(purchase_vat, 2),
        'vat_payable': round(vat_payable, 2)
    }



@router.get("/accounting/reports/balance-sheet")
@cached(ttl=300, key_prefix="report_balance_sheet")  # Cache for 5 minutes
async def get_balance_sheet(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):
    tenant_id = current_user.tenant_id

    async def _sum_cash():
        pipeline = [
            {'$match': {'tenant_id': tenant_id}},
            {'$group': {'_id': None, 'total': {'$sum': '$balance'}}},
        ]
        cur = db.bank_accounts.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]['total'] if docs else 0

    async def _sum_inventory():
        pipeline = [
            {'$match': {'tenant_id': tenant_id}},
            {'$group': {'_id': None, 'total': {
                '$sum': {'$multiply': [
                    {'$ifNull': ['$quantity', 0]},
                    {'$ifNull': ['$unit_cost', 0]},
                ]}
            }}},
        ]
        cur = db.inventory_items.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]['total'] if docs else 0

    async def _sum_receivables():
        pipeline = [
            {'$match': {
                'tenant_id': tenant_id,
                'status': {'$in': ['pending', 'partial']},
            }},
            {'$group': {'_id': None, 'total': {'$sum': '$total'}}},
        ]
        cur = db.accounting_invoices.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]['total'] if docs else 0

    async def _sum_payables():
        pipeline = [
            {'$match': {
                'tenant_id': tenant_id,
                'payment_status': 'pending',
            }},
            {'$group': {'_id': None, 'total': {'$sum': '$total_amount'}}},
        ]
        cur = db.expenses.aggregate(pipeline)
        docs = await cur.to_list(1)
        return docs[0]['total'] if docs else 0

    total_cash, total_inventory, total_receivables, total_payables = await asyncio.gather(
        _sum_cash(), _sum_inventory(), _sum_receivables(), _sum_payables()
    )

    total_assets = total_cash + total_inventory + total_receivables

    # Equity
    total_equity = total_assets - total_payables

    return {
        'assets': {
            'cash': round(total_cash, 2),
            'inventory': round(total_inventory, 2),
            'receivables': round(total_receivables, 2),
            'total': round(total_assets, 2)
        },
        'liabilities': {
            'payables': round(total_payables, 2),
            'total': round(total_payables, 2)
        },
        'equity': {
            'total': round(total_equity, 2)
        }
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

    invoices = await db.accounting_invoices.find({
        'tenant_id': current_user.tenant_id,
        'issue_date': {'$gte': month_start, '$lte': month_end}
    }, {'_id': 0}).to_list(1000)

    expenses = await db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': month_start, '$lte': month_end}
    }, {'_id': 0}).to_list(1000)

    collected_income = sum(inv.get('total', 0) for inv in invoices if inv.get('status') == 'paid')
    accrued_revenue = sum(inv.get('total', 0) for inv in invoices)
    pending_amount = sum(inv.get('total', 0) for inv in invoices if inv.get('status') in ('pending', 'partial'))
    overdue_amount = sum(inv.get('total', 0) for inv in invoices if inv.get('status') == 'overdue')
    total_expenses = sum(exp.get('amount', 0) for exp in expenses)
    pending_invoices = len([inv for inv in invoices if inv.get('status') == 'pending'])
    overdue_invoices = len([inv for inv in invoices if inv.get('status') == 'overdue'])

    # Get bank balances
    bank_accounts = await db.bank_accounts.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    total_bank_balance = sum(acc['balance'] for acc in bank_accounts)

    # Tenant currency for display.
    from core.tenant_currency import get_tenant_currency
    cur_code, cur_symbol = await get_tenant_currency(current_user.tenant_id)

    return {
        # Backward-compat field (paid invoices only).
        'monthly_income': round(collected_income, 2),
        # New explicit fields:
        'collected_income': round(collected_income, 2),
        'accrued_revenue': round(accrued_revenue, 2),
        'pending_amount': round(pending_amount, 2),
        'overdue_amount': round(overdue_amount, 2),
        'monthly_expenses': round(total_expenses, 2),
        'net_income': round(collected_income - total_expenses, 2),
        'pending_invoices': pending_invoices,
        'overdue_invoices': overdue_invoices,
        'total_bank_balance': round(total_bank_balance, 2),
        'currency': cur_code,
        'currency_symbol': cur_symbol,
    }



@router.get("/accounting/currencies")
async def get_currencies(current_user: User = Depends(get_current_user)):
    """Get all supported currencies"""
    currencies = [
        {'code': 'TRY', 'name': 'Turkish Lira', 'symbol': '₺'},
        {'code': 'USD', 'name': 'US Dollar', 'symbol': '$'},
        {'code': 'EUR', 'name': 'Euro', 'symbol': '€'},
        {'code': 'GBP', 'name': 'British Pound', 'symbol': '£'}
    ]
    return {'currencies': currencies}


@router.post("/accounting/currency-rates")
async def create_currency_rate(
    request: CreateCurrencyRateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Create or update currency exchange rate"""
    rate = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'from_currency': request.from_currency,
        'to_currency': request.to_currency,
        'rate': request.rate,
        'effective_date': request.effective_date,
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    rate_copy = rate.copy()
    await db.currency_rates.insert_one(rate_copy)
    return rate


@router.get("/accounting/currency-rates")
async def get_currency_rates(
    from_currency: str = None,
    to_currency: str = None,
    date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get currency exchange rates"""
    query = {'tenant_id': current_user.tenant_id}

    if from_currency:
        query['from_currency'] = from_currency
    if to_currency:
        query['to_currency'] = to_currency
    if date:
        query['effective_date'] = {'$lte': date}

    rates = await db.currency_rates.find(
        query,
        {'_id': 0}
    ).sort('effective_date', -1).to_list(100)

    return {'rates': rates, 'count': len(rates)}


@router.post("/accounting/convert-currency")
async def convert_currency(
    request: ConvertCurrencyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Convert amount between currencies"""
    # If same currency, no conversion needed
    if request.from_currency == request.to_currency:
        return {
            'amount': request.amount,
            'from_currency': request.from_currency,
            'to_currency': request.to_currency,
            'rate': 1.0,
            'converted_amount': request.amount
        }

    # Get exchange rate
    query = {
        'tenant_id': current_user.tenant_id,
        'from_currency': request.from_currency,
        'to_currency': request.to_currency
    }

    if request.date:
        query['effective_date'] = {'$lte': request.date}

    rate_record = await db.currency_rates.find_one(
        query,
        {'_id': 0},
        sort=[('effective_date', -1)]
    )

    if not rate_record:
        # Try reverse rate
        reverse_query = {
            'tenant_id': current_user.tenant_id,
            'from_currency': request.to_currency,
            'to_currency': request.from_currency
        }
        if request.date:
            reverse_query['effective_date'] = {'$lte': request.date}

        reverse_rate = await db.currency_rates.find_one(
            reverse_query,
            {'_id': 0},
            sort=[('effective_date', -1)]
        )

        if reverse_rate:
            rate = 1.0 / reverse_rate['rate']
        else:
            # Default rates if not found
            default_rates = {
                ('TRY', 'USD'): 0.037,
                ('TRY', 'EUR'): 0.034,
                ('USD', 'TRY'): 27.0,
                ('EUR', 'TRY'): 29.5,
                ('USD', 'EUR'): 0.92,
                ('EUR', 'USD'): 1.09
            }
            rate = default_rates.get((request.from_currency, request.to_currency), 1.0)
    else:
        rate = rate_record['rate']

    converted_amount = request.amount * rate

    return {
        'amount': request.amount,
        'from_currency': request.from_currency,
        'to_currency': request.to_currency,
        'rate': round(rate, 4),
        'converted_amount': round(converted_amount, 2),
        'date': request.date or datetime.now(UTC).date().isoformat()
    }


@router.post("/accounting/invoices/multi-currency")
async def create_multi_currency_invoice(
    request: CreateMultiCurrencyInvoiceRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Create invoice in any currency with auto-conversion to TRY"""
    # Calculate totals in invoice currency
    subtotal = sum(item.get('quantity', 0) * item.get('unit_price', 0) for item in request.items)

    # Calculate VAT
    total_vat = 0
    for item in request.items:
        item_total = item.get('quantity', 0) * item.get('unit_price', 0)
        vat_rate = item.get('vat_rate', 18) / 100
        item['vat_amount'] = round(item_total * vat_rate, 2)
        total_vat += item['vat_amount']

    total = subtotal + total_vat

    # Convert to TRY if needed
    if request.currency != 'TRY':
        if request.exchange_rate:
            rate = request.exchange_rate
        else:
            # Get current rate
            conversion = await convert_currency(
                ConvertCurrencyRequest(
                    amount=1.0,
                    from_currency=request.currency,
                    to_currency='TRY'
                ),
                current_user
            )
            rate = conversion['rate']

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
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'invoice_number': invoice_number,
        'customer_name': _validate_invoice_customer_name(request.customer_name),
        'customer_email': request.customer_email,
        'customer_address': sanitize_plaintext(request.customer_address, max_length=500),
        'items': request.items,
        'currency': request.currency,
        'exchange_rate': rate,
        'subtotal': round(subtotal, 2),
        'total_vat': round(total_vat, 2),
        'total': round(total, 2),
        'subtotal_try': round(subtotal_try, 2),
        'total_vat_try': round(total_vat_try, 2),
        'total_try': round(total_try, 2),
        'payment_terms': request.payment_terms,
        'notes': request.notes,
        'issue_date': datetime.now(UTC).date().isoformat(),
        'due_date': (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
        'status': 'pending',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
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
    folio = await db.folios.find_one({
        'id': request.folio_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Get folio charges
    charges = await db.folio_charges.find({
        'folio_id': request.folio_id,
        'tenant_id': current_user.tenant_id,
        'voided': False
    }, {'_id': 0}).to_list(1000)

    # Get booking info
    booking = await db.bookings.find_one({
        'folio_id': request.folio_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Convert charges to invoice items
    invoice_items = []
    for charge in charges:
        item = {
            'description': charge.get('description', 'Hotel Charge'),
            'quantity': 1,
            'unit_price': charge.get('amount', 0),
            'vat_rate': charge.get('vat_rate', 18),
            'total': charge.get('total', 0)
        }
        invoice_items.append(item)

    # Get customer info from booking or folio
    raw_customer_name = booking.get('guest_name') if booking else folio.get('guest_name', 'Guest')
    # Apply same validator as manual create — guest_name from booking/folio could
    # have been seeded with HTML/XML payloads in older data; reject those here.
    customer_name = _validate_invoice_customer_name(raw_customer_name)
    customer_email = booking.get('guest_email') if booking else folio.get('guest_email', '')

    # Create invoice
    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Calculate totals
    subtotal = sum(item['unit_price'] * item['quantity'] for item in invoice_items)
    total_vat = sum(item['unit_price'] * item['quantity'] * (item['vat_rate'] / 100) for item in invoice_items)

    # Currency conversion if needed
    if request.invoice_currency != 'TRY':
        conversion = await convert_currency(
            ConvertCurrencyRequest(
                amount=subtotal + total_vat,
                from_currency='TRY',
                to_currency=request.invoice_currency
            ),
            current_user
        )
        exchange_rate = conversion['rate']
        total_foreign = conversion['converted_amount']
    else:
        exchange_rate = 1.0
        total_foreign = subtotal + total_vat

    invoice = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'invoice_number': invoice_number,
        'folio_id': request.folio_id,
        'booking_id': booking['id'] if booking else None,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_address': booking.get('guest_address', '') if booking else '',
        'items': invoice_items,
        'currency': request.invoice_currency,
        'exchange_rate': exchange_rate,
        'subtotal': round(subtotal, 2),
        'total_vat': round(total_vat, 2),
        'total': round(subtotal + total_vat, 2),
        'total_foreign_currency': round(total_foreign, 2),
        'payment_terms': 'Due on checkout',
        'issue_date': datetime.now(UTC).date().isoformat(),
        'due_date': datetime.now(UTC).date().isoformat(),
        'status': 'pending',
        'source': 'pms_folio',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    invoice_copy = invoice.copy()
    await db.accounting_invoices.insert_one(invoice_copy)

    # Update folio with invoice reference
    await db.folios.update_one(
        {'id': request.folio_id},
        {'$set': {'invoice_id': invoice['id'], 'invoice_number': invoice_number}}
    )

    # Generate E-Fatura if requested
    if request.include_efatura:
        # Bug AP (April 2026): every interpolation goes through xml.sax.saxutils
        # so user-controlled fields can't break out of their elements/attributes
        # and inject arbitrary UBL nodes (which would corrupt the GİB submission
        # or, worse, smuggle alternate billing data past tax controls).
        from xml.sax.saxutils import escape as _xe
        from xml.sax.saxutils import quoteattr as _qa
        efatura_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <ID>{_xe(str(invoice_number))}</ID>
    <IssueDate>{_xe(str(invoice['issue_date']))}</IssueDate>
    <InvoiceTypeCode>SATIS</InvoiceTypeCode>
    <DocumentCurrencyCode>{_xe(str(request.invoice_currency))}</DocumentCurrencyCode>
    <LineCountNumeric>{len(invoice_items)}</LineCountNumeric>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID={_qa(str(request.invoice_currency))}>{_xe(str(invoice['subtotal']))}</TaxExclusiveAmount>
        <TaxInclusiveAmount currencyID={_qa(str(request.invoice_currency))}>{_xe(str(invoice['total']))}</TaxInclusiveAmount>
    </LegalMonetaryTotal>
</Invoice>"""

        efatura_record = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'invoice_id': invoice['id'],
            'invoice_number': invoice_number,
            'efatura_uuid': str(uuid.uuid4()),
            'xml_content': efatura_xml,
            'status': 'generated',
            'generated_at': datetime.now(UTC).isoformat()
        }

        efatura_copy = efatura_record.copy()
        await db.efatura_records.insert_one(efatura_copy)

        invoice['efatura_uuid'] = efatura_record['efatura_uuid']
        invoice['efatura_status'] = 'generated'

    return {
        'invoice': invoice,
        'message': 'Invoice generated from folio successfully',
        'efatura_generated': request.include_efatura
    }



@router.get("/accounting/invoices/{invoice_id}/efatura-status")
async def get_invoice_efatura_status(
    invoice_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get E-Fatura status for accounting invoice"""
    invoice = await db.accounting_invoices.find_one({
        'id': invoice_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get E-Fatura record
    efatura = await db.efatura_records.find_one({
        'invoice_id': invoice_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not efatura:
        return {
            'invoice_id': invoice_id,
            'invoice_number': invoice.get('invoice_number'),
            'efatura_status': 'not_generated',
            'message': 'E-Fatura has not been generated for this invoice'
        }

    return {
        'invoice_id': invoice_id,
        'invoice_number': invoice.get('invoice_number'),
        'efatura_uuid': efatura.get('efatura_uuid'),
        'efatura_status': efatura.get('status'),
        'generated_at': efatura.get('generated_at'),
        'sent_at': efatura.get('sent_at'),
        'gib_response': efatura.get('gib_response')
    }


@router.post("/accounting/invoices/{invoice_id}/generate-efatura")
async def generate_efatura_for_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Generate E-Fatura for existing accounting invoice"""
    invoice = await db.accounting_invoices.find_one({
        'id': invoice_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check if E-Fatura already exists
    existing_efatura = await db.efatura_records.find_one({
        'invoice_id': invoice_id,
        'tenant_id': current_user.tenant_id
    })

    if existing_efatura:
        return {
            'message': 'E-Fatura already exists for this invoice',
            'efatura_uuid': existing_efatura.get('efatura_uuid'),
            'status': existing_efatura.get('status')
        }

    # Generate E-Fatura XML — Bug AP: customer_name (and every other field)
    # comes from user input. xml.sax.saxutils.escape neutralizes `<`, `>`, `&`;
    # quoteattr handles attribute values including embedded quotes. Without
    # this, customer_name=`</Name>...<EVIL>...</EVIL><Name>x` smuggles arbitrary
    # nodes into the UBL tree.
    from xml.sax.saxutils import escape as _xe
    from xml.sax.saxutils import quoteattr as _qa
    currency = invoice.get('currency', 'TRY')
    efatura_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <ID>{_xe(str(invoice.get('invoice_number') or ''))}</ID>
    <IssueDate>{_xe(str(invoice.get('issue_date') or ''))}</IssueDate>
    <InvoiceTypeCode>SATIS</InvoiceTypeCode>
    <DocumentCurrencyCode>{_xe(str(currency))}</DocumentCurrencyCode>
    <LineCountNumeric>{len(invoice.get('items', []))}</LineCountNumeric>
    <AccountingSupplierParty>
        <Party>
            <PartyName>
                <Name>Hotel Name</Name>
            </PartyName>
        </Party>
    </AccountingSupplierParty>
    <AccountingCustomerParty>
        <Party>
            <PartyName>
                <Name>{_xe(str(invoice.get('customer_name') or 'N/A'))}</Name>
            </PartyName>
        </Party>
    </AccountingCustomerParty>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID={_qa(str(currency))}>{_xe(str(invoice.get('subtotal', 0)))}</TaxExclusiveAmount>
        <TaxInclusiveAmount currencyID={_qa(str(currency))}>{_xe(str(invoice.get('total', 0)))}</TaxInclusiveAmount>
    </LegalMonetaryTotal>
</Invoice>"""

    efatura_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'invoice_id': invoice_id,
        'invoice_number': invoice.get('invoice_number'),
        'efatura_uuid': str(uuid.uuid4()),
        'xml_content': efatura_xml,
        'status': 'generated',
        'generated_at': datetime.now(UTC).isoformat()
    }

    efatura_copy = efatura_record.copy()
    await db.efatura_records.insert_one(efatura_copy)

    # Update invoice with E-Fatura reference
    await db.accounting_invoices.update_one(
        {'id': invoice_id},
        {
            '$set': {
                'efatura_uuid': efatura_record['efatura_uuid'],
                'efatura_status': 'generated'
            }
        }
    )

    return {
        'message': 'E-Fatura generated successfully',
        'efatura_uuid': efatura_record['efatura_uuid'],
        'invoice_number': invoice.get('invoice_number')
    }



@router.get("/efatura/invoices")
async def get_efatura_invoices(current_user: User = Depends(get_current_user)):
    invoices = await db.invoices.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('created_at', -1).limit(50).to_list(50)

    # Add efatura status to each invoice
    for invoice in invoices:
        invoice['efatura_status'] = invoice.get('efatura_status', 'pending')

    return {'invoices': invoices}


@router.get("/efatura/settings")
async def get_efatura_settings(current_user: User = Depends(get_current_user)):
    settings = await db.efatura_settings.find_one({'tenant_id': current_user.tenant_id}, {'_id': 0})
    return settings or {'vkn': '1234567890', 'enabled': True, 'auto_send': False, 'last_sync': None}


@router.post("/efatura/send/{invoice_id}")
async def send_efatura(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    # Tenant-scoped update; prevents cross-tenant IDOR via guessed invoice_id.
    result = await db.invoices.update_one(
        {'id': invoice_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'efatura_status': 'sent',
            'efatura_sent_at': datetime.now(UTC).isoformat()
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return {'message': 'E-Fatura sent successfully'}


@router.post("/efatura/generate/{invoice_id}")
async def generate_efatura(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Generate E-Fatura XML for GIB"""
    invoice = await db.accounting_invoices.find_one(
        {'id': invoice_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Generate E-Fatura XML (simplified) — XML injection guard with escape
    from xml.sax.saxutils import escape as _xml_escape
    _inv_no = _xml_escape(str(invoice.get('invoice_number', '')))
    _inv_date = _xml_escape(str(invoice.get('invoice_date', '')))
    _line_count = int(len(invoice.get('items', [])))
    try:
        _subtotal = float(invoice.get('subtotal', 0) or 0)
        _grand = float(invoice.get('grand_total', 0) or 0)
    except (TypeError, ValueError):
        _subtotal, _grand = 0.0, 0.0
    efatura_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <ID>{_inv_no}</ID>
    <IssueDate>{_inv_date}</IssueDate>
    <InvoiceTypeCode>SATIS</InvoiceTypeCode>
    <LineCountNumeric>{_line_count}</LineCountNumeric>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount>{_subtotal:.2f}</TaxExclusiveAmount>
        <TaxInclusiveAmount>{_grand:.2f}</TaxInclusiveAmount>
    </LegalMonetaryTotal>
</Invoice>"""

    # Save E-Fatura record
    efatura_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'invoice_id': invoice_id,
        'invoice_number': invoice['invoice_number'],
        'efatura_uuid': str(uuid.uuid4()),
        'xml_content': efatura_xml,
        'status': 'generated',
        'generated_at': datetime.now(UTC).isoformat()
    }

    efatura_copy = efatura_record.copy()
    await db.efatura_records.insert_one(efatura_copy)

    # Update invoice status
    await db.accounting_invoices.update_one(
        {'id': invoice_id},
        {'$set': {'efatura_status': 'generated', 'efatura_uuid': efatura_record['efatura_uuid']}}
    )

    return {
        'message': 'E-Fatura generated successfully',
        'efatura_uuid': efatura_record['efatura_uuid'],
        'xml_content': efatura_xml
    }


@router.post("/efatura/send-to-gib/{invoice_id}")
async def send_efatura_to_gib(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    """Send E-Fatura to GIB (Turkish Revenue Administration)"""
    efatura = await db.efatura_records.find_one(
        {'invoice_id': invoice_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )

    if not efatura:
        raise HTTPException(status_code=404, detail="E-Fatura not found")

    # Mock GIB integration (in production, use actual GIB API)
    gib_response = {
        'status': 'success',
        'gib_id': str(uuid.uuid4()),
        'timestamp': datetime.now(UTC).isoformat()
    }

    # Update E-Fatura status
    await db.efatura_records.update_one(
        {'id': efatura['id']},
        {
            '$set': {
                'status': 'sent_to_gib',
                'gib_response': gib_response,
                'sent_at': datetime.now(UTC).isoformat()
            }
        }
    )

    await db.accounting_invoices.update_one(
        {'id': invoice_id},
        {'$set': {'efatura_status': 'sent', 'efatura_sent_at': datetime.now(UTC).isoformat()}}
    )

    return {'message': 'E-Fatura sent to GIB successfully', 'gib_response': gib_response}


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
    company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    })

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get all open folios for company
    folios = []
    total_balance = 0
    async for folio in db.folios.find({
        'company_id': company_id,
        'tenant_id': current_user.tenant_id,
        'status': 'open'
    }):
        balance = folio.get('balance', 0)
        total_balance += balance
        folios.append({
            'folio_number': folio.get('folio_number'),
            'booking_id': folio.get('booking_id'),
            'balance': balance,
            'created_at': folio.get('created_at')
        })

    recipient_email = email or company.get('contact_email')

    if not recipient_email:
        raise HTTPException(status_code=400, detail="No email address provided")

    # Create statement document
    statement = {
        'company_name': company.get('name'),
        'statement_date': datetime.now(UTC).isoformat(),
        'total_outstanding': round(total_balance, 2),
        'folios': folios,
        'payment_terms': company.get('payment_terms', 'Net 30'),
        'contact_person': company.get('contact_person')
    }

    # In production, send actual email via SMTP or email service
    # For now, simulate email sending

    return {
        'success': True,
        'message': f'Statement sent to {recipient_email}',
        'statement': statement,
        'note': 'In production, integrate with SendGrid, AWS SES, or SMTP server'
    }





