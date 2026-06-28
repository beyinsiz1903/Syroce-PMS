# Accounting Endpoints to be integrated into server.py
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v94 DW

api_router = APIRouter(prefix="/api")

# These endpoints will be added to server.py

# ============= SUPPLIER MANAGEMENT =============


@api_router.post("/accounting/suppliers")
async def create_supplier(
    name: str,
    tax_office: str | None = None,
    tax_number: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    category: str = "general",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    from accounting_models import Supplier

    supplier = Supplier(tenant_id=current_user.tenant_id, name=name, tax_office=tax_office, tax_number=tax_number, email=email, phone=phone, address=address, category=category)
    supplier_dict = supplier.model_dump()
    supplier_dict["created_at"] = supplier_dict["created_at"].isoformat()
    await db.suppliers.insert_one(supplier_dict)
    return supplier


@api_router.get("/accounting/suppliers")
async def get_suppliers(current_user: User = Depends(get_current_user)):
    suppliers = await db.suppliers.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return suppliers


@api_router.put("/accounting/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.suppliers.update_one({"id": supplier_id, "tenant_id": current_user.tenant_id}, {"$set": updates})
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    return supplier


# ============= BANK ACCOUNTS =============


@api_router.post("/accounting/bank-accounts")
async def create_bank_account(
    name: str,
    bank_name: str,
    account_number: str,
    iban: str | None = None,
    currency: str = "USD",
    balance: float = 0.0,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    from accounting_models import BankAccount

    bank_account = BankAccount(tenant_id=current_user.tenant_id, name=name, bank_name=bank_name, account_number=account_number, iban=iban, currency=currency, balance=balance)
    account_dict = bank_account.model_dump()
    account_dict["created_at"] = account_dict["created_at"].isoformat()
    await db.bank_accounts.insert_one(account_dict)
    return bank_account


@api_router.get("/accounting/bank-accounts")
async def get_bank_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.bank_accounts.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return accounts


@api_router.put("/accounting/bank-accounts/{account_id}")
async def update_bank_account(
    account_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.bank_accounts.update_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"$set": updates})
    account = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    return account


# ============= EXPENSE MANAGEMENT =============


@api_router.post("/accounting/expenses")
async def create_expense(
    category: str,
    description: str,
    amount: float,
    vat_rate: float,
    date: str,
    supplier_id: str | None = None,
    payment_method: str | None = None,
    receipt_url: str | None = None,
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    from accounting_models import Expense

    count = await db.expenses.count_documents({"tenant_id": current_user.tenant_id})
    expense_number = f"EXP-{count + 1:05d}"

    vat_amount = amount * (vat_rate / 100)
    total_amount = amount + vat_amount

    expense = Expense(
        tenant_id=current_user.tenant_id,
        expense_number=expense_number,
        supplier_id=supplier_id,
        category=category,
        description=description,
        amount=amount,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_amount=total_amount,
        date=datetime.fromisoformat(date),
        payment_method=payment_method,
        receipt_url=receipt_url,
        notes=notes,
        created_by=current_user.name,
    )

    expense_dict = expense.model_dump()
    expense_dict["date"] = expense_dict["date"].isoformat()
    expense_dict["created_at"] = expense_dict["created_at"].isoformat()
    await db.expenses.insert_one(expense_dict)

    # Update supplier balance if applicable
    if supplier_id:
        await db.suppliers.update_one({"id": supplier_id}, {"$inc": {"account_balance": total_amount}})

    # Create cash flow entry
    from accounting_models import CashFlow

    cash_flow = CashFlow(
        tenant_id=current_user.tenant_id,
        transaction_type="expense",
        category=category,
        amount=total_amount,
        description=description,
        reference_id=expense.id,
        reference_type="expense",
        date=datetime.fromisoformat(date),
        created_by=current_user.name,
    )
    cf_dict = cash_flow.model_dump()
    cf_dict["date"] = cf_dict["date"].isoformat()
    cf_dict["created_at"] = cf_dict["created_at"].isoformat()
    await db.cash_flow.insert_one(cf_dict)

    return expense


@api_router.get("/accounting/expenses")
async def get_expenses(start_date: str | None = None, end_date: str | None = None, category: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    if category:
        query["category"] = category

    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return expenses


@api_router.put("/accounting/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    await db.expenses.update_one({"id": expense_id, "tenant_id": current_user.tenant_id}, {"$set": updates})
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    return expense


# ============= INVENTORY MANAGEMENT =============


@api_router.post("/accounting/inventory")
async def create_inventory_item(
    name: str,
    category: str,
    unit: str,
    quantity: float = 0.0,
    unit_cost: float = 0.0,
    reorder_level: float = 0.0,
    sku: str | None = None,
    supplier_id: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    is_consumable: bool = True,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    if quantity < 0:
        raise HTTPException(status_code=422, detail="quantity must be >= 0")
    if unit_cost < 0:
        raise HTTPException(status_code=422, detail="unit_cost must be >= 0")
    if reorder_level < 0:
        raise HTTPException(status_code=422, detail="reorder_level must be >= 0")
    from accounting_models import InventoryItem

    item = InventoryItem(
        tenant_id=current_user.tenant_id,
        name=name,
        sku=sku,
        category=category,
        unit=unit,
        quantity=quantity,
        unit_cost=unit_cost,
        reorder_level=reorder_level,
        supplier_id=supplier_id,
        location=location,
        notes=notes,
        is_consumable=is_consumable,
    )
    item_dict = item.model_dump()
    item_dict["created_at"] = item_dict["created_at"].isoformat()
    await db.inventory_items.insert_one(item_dict)
    return item


@api_router.patch("/accounting/inventory/{item_id}")
async def update_inventory_item(
    item_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    """Belirli alanları güncelle (örn. is_consumable, reorder_level, unit_cost, notes)."""
    allowed = {"is_consumable", "reorder_level", "unit_cost", "notes", "location", "supplier_id", "category", "name", "sku", "unit"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    if "is_consumable" in updates:
        updates["is_consumable"] = bool(updates["is_consumable"])
    res = await db.inventory_items.update_one(
        {"id": item_id, "tenant_id": current_user.tenant_id},
        {"$set": updates},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"ok": True, "updated": updates}


@api_router.get("/accounting/inventory")
async def get_inventory(current_user: User = Depends(get_current_user)):
    items = await db.inventory_items.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)

    # Get low stock items
    low_stock = [item for item in items if item["quantity"] <= item["reorder_level"]]

    return {"items": items, "low_stock_count": len(low_stock), "total_value": sum(item["quantity"] * item["unit_cost"] for item in items)}


@api_router.post("/accounting/inventory/movement")
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
    from accounting_models import StockMovement

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

    return movement


# ============= SETUP KITS (Oda Hazırlık Standardı) =============


@api_router.get("/accounting/setup-kits")
async def list_setup_kits(current_user: User = Depends(get_current_user)):
    kits = await db.setup_kits.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": kits}


@api_router.post("/accounting/setup-kits")
async def create_setup_kit(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    name = (payload.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Kit adı en az 2 karakter olmalı")
    lines = payload.get("lines") or []
    if not lines:
        raise HTTPException(status_code=400, detail="En az bir kalem ekleyin")

    clean_lines = []
    for ln in lines:
        item_id = ln.get("item_id")
        qty = float(ln.get("quantity") or 0)
        if not item_id or qty <= 0:
            continue
        clean_lines.append(
            {
                "item_id": item_id,
                "item_name": ln.get("item_name") or "",
                "unit": ln.get("unit") or "adet",
                "quantity": qty,
            }
        )
    if not clean_lines:
        raise HTTPException(status_code=400, detail="Geçerli kalem yok")

    kit = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "name": name,
        "description": (payload.get("description") or "").strip(),
        "category": payload.get("category") or "room_setup",
        "lines": clean_lines,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.setup_kits.insert_one(dict(kit))
    kit.pop("_id", None)
    return kit


@api_router.delete("/accounting/setup-kits/{kit_id}")
async def delete_setup_kit(
    kit_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    r = await db.setup_kits.delete_one({"id": kit_id, "tenant_id": current_user.tenant_id})
    if not r.deleted_count:
        raise HTTPException(status_code=404, detail="Kit bulunamadı")
    return {"ok": True}


@api_router.post("/accounting/setup-kits/{kit_id}/apply")
async def apply_setup_kit(
    kit_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v94 DW
):
    import math

    try:
        multiplier = float(payload.get("multiplier") or 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Çarpan geçersiz")
    if not math.isfinite(multiplier) or multiplier <= 0 or multiplier > 10000:
        raise HTTPException(status_code=400, detail="Çarpan 0 ile 10000 arasında olmalı")

    reference = payload.get("reference") or "room_setup"
    notes = payload.get("notes") or ""
    tenant_id = current_user.tenant_id

    kit = await db.setup_kits.find_one({"id": kit_id, "tenant_id": tenant_id}, {"_id": 0})
    if not kit:
        raise HTTPException(status_code=404, detail="Kit bulunamadı")

    # Önceden yeterlilik kontrolü (kullanıcıya hızlı geri bildirim)
    shortages = []
    needs = []  # tüketilecek (stoktan düşecek) kalemler
    reusables = []  # çok kullanımlık — sadece hatırlatma
    for ln in kit["lines"]:
        try:
            line_qty = float(ln.get("quantity") or 0)
        except (TypeError, ValueError):
            line_qty = 0
        if not math.isfinite(line_qty) or line_qty <= 0:
            shortages.append({"item_name": ln.get("item_name", "?"), "reason": "Geçersiz miktar"})
            continue
        needed = line_qty * multiplier
        item = await db.inventory_items.find_one({"id": ln["item_id"], "tenant_id": tenant_id}, {"_id": 0})
        if not item:
            shortages.append({"item_name": ln.get("item_name", "?"), "reason": "Ürün bulunamadı"})
            continue
        # Çok kullanımlık (havlu, nevresim vb.) — stoktan düşmez
        if item.get("is_consumable", True) is False:
            reusables.append(
                {
                    "item_name": ln["item_name"],
                    "quantity": needed,
                    "unit": ln.get("unit"),
                }
            )
            continue
        if (item.get("quantity") or 0) < needed:
            shortages.append(
                {
                    "item_name": ln["item_name"],
                    "needed": needed,
                    "available": item.get("quantity") or 0,
                    "unit": ln.get("unit"),
                }
            )
        else:
            needs.append((ln, needed))
    if shortages:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Yetersiz stok",
                "shortages": shortages,
            },
        )

    # Atomik koşullu decrement — her satır için tenant filtresi + quantity yeterli koşulu.
    # Başarısız olursa şimdiye kadar uygulananları telafi et (compensating reversals).
    applied = []
    rollback_log = []  # [(item_id, qty_to_restore, movement_id_to_delete), ...]
    try:
        for ln, deducted in needs:
            res = await db.inventory_items.update_one(
                {
                    "id": ln["item_id"],
                    "tenant_id": tenant_id,
                    "quantity": {"$gte": deducted},
                },
                {"$inc": {"quantity": -deducted}},
            )
            if res.modified_count != 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Stok yarışı tespit edildi, tekrar deneyin",
                        "item_name": ln["item_name"],
                    },
                )
            movement_id = str(uuid.uuid4())
            movement = {
                "id": movement_id,
                "tenant_id": tenant_id,
                "item_id": ln["item_id"],
                "movement_type": "out",
                "quantity": deducted,
                "unit_cost": 0.0,
                "reference": reference,
                "notes": notes or f"{kit['name']} × {multiplier:g}",
                "created_by": current_user.name,
                "created_at": datetime.now(UTC).isoformat(),
                "kit_id": kit_id,
            }
            await db.stock_movements.insert_one(dict(movement))
            rollback_log.append((ln["item_id"], deducted, movement_id))
            applied.append(
                {
                    "item_name": ln["item_name"],
                    "deducted": deducted,
                    "unit": ln.get("unit"),
                }
            )
    except Exception as e:
        # Telafi: uygulanmış satırları geri al (best-effort)
        for item_id, qty, mv_id in rollback_log:
            try:
                await db.inventory_items.update_one(
                    {"id": item_id, "tenant_id": tenant_id},
                    {"$inc": {"quantity": qty}},
                )
                await db.stock_movements.delete_one({"id": mv_id, "tenant_id": tenant_id})
            except Exception:
                pass
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Kit uygulanamadı, geri alındı")

    return {
        "ok": True,
        "kit_name": kit["name"],
        "multiplier": multiplier,
        "applied": applied,
        "reusables": reusables,
    }


# ============= ADVANCED INVOICING =============


@api_router.post("/accounting/invoices")
async def create_accounting_invoice(
    invoice_type: str,
    customer_name: str,
    customer_email: str | None = None,
    customer_tax_office: str | None = None,
    customer_tax_number: str | None = None,
    customer_address: str | None = None,
    items: list[dict[str, Any]] = [],
    due_date: str = None,
    booking_id: str | None = None,
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    from accounting_models import AccountingInvoice, AccountingInvoiceItem

    count = await db.accounting_invoices.count_documents({"tenant_id": current_user.tenant_id})
    invoice_number = f"INV-{datetime.now().year}-{count + 1:05d}"

    invoice_items = []
    subtotal = 0.0
    total_vat = 0.0
    vat_withholding = 0.0
    total_additional_taxes = 0.0

    for item_data in items:
        item = AccountingInvoiceItem(**item_data)
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
        invoice_type=invoice_type,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_tax_office=customer_tax_office,
        customer_tax_number=customer_tax_number,
        customer_address=customer_address,
        items=invoice_items,
        subtotal=subtotal,
        total_vat=total_vat,
        vat_withholding=vat_withholding,
        total_additional_taxes=total_additional_taxes,
        total=total,
        due_date=datetime.fromisoformat(due_date),
        booking_id=booking_id,
        created_by=current_user.name,
    )

    invoice_dict = invoice.model_dump()
    invoice_dict["issue_date"] = invoice_dict["issue_date"].isoformat()
    invoice_dict["due_date"] = invoice_dict["due_date"].isoformat()
    invoice_dict["created_at"] = invoice_dict["created_at"].isoformat()
    await db.accounting_invoices.insert_one(invoice_dict)

    # Create cash flow entry
    from accounting_models import CashFlow

    cash_flow = CashFlow(
        tenant_id=current_user.tenant_id,
        transaction_type="income",
        category="room_revenue" if booking_id else "other_services",
        amount=total,
        description=f"Invoice {invoice_number}",
        reference_id=invoice.id,
        reference_type="invoice",
        date=datetime.now(UTC),
        created_by=current_user.name,
    )
    cf_dict = cash_flow.model_dump()
    cf_dict["date"] = cf_dict["date"].isoformat()
    cf_dict["created_at"] = cf_dict["created_at"].isoformat()
    await db.cash_flow.insert_one(cf_dict)

    return invoice


@api_router.get("/accounting/invoices")
async def get_accounting_invoices(
    start_date: str | None = None, end_date: str | None = None, invoice_type: str | None = None, status: str | None = None, current_user: User = Depends(get_current_user)
):
    query = {"tenant_id": current_user.tenant_id}
    if start_date and end_date:
        query["issue_date"] = {"$gte": start_date, "$lte": end_date}
    if invoice_type:
        query["invoice_type"] = invoice_type
    if status:
        query["status"] = status

    invoices = await db.accounting_invoices.find(query, {"_id": 0}).sort("issue_date", -1).to_list(1000)
    return invoices


@api_router.put("/accounting/invoices/{invoice_id}")
async def update_accounting_invoice(
    invoice_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v94 DW
):
    if "status" in updates and updates["status"] == "paid" and "payment_date" not in updates:
        updates["payment_date"] = datetime.now(UTC).isoformat()

    tenant_filter = {"id": invoice_id, "tenant_id": current_user.tenant_id}
    upd = await db.accounting_invoices.update_one(tenant_filter, {"$set": updates})
    if upd.matched_count == 0:
        raise HTTPException(status_code=404, detail="Accounting invoice not found")
    invoice = await db.accounting_invoices.find_one(tenant_filter, {"_id": 0})
    return invoice


# ============= CASH FLOW =============


@api_router.get("/accounting/cash-flow")
async def get_cash_flow(start_date: str | None = None, end_date: str | None = None, transaction_type: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    if transaction_type:
        query["transaction_type"] = transaction_type

    flows = await db.cash_flow.find(query, {"_id": 0}).sort("date", -1).to_list(1000)

    total_income = sum(f["amount"] for f in flows if f["transaction_type"] == "income")
    total_expense = sum(f["amount"] for f in flows if f["transaction_type"] == "expense")
    net_cash_flow = total_income - total_expense

    return {"transactions": flows, "total_income": total_income, "total_expense": total_expense, "net_cash_flow": net_cash_flow}


# ============= FINANCIAL REPORTS =============


@api_router.get("/accounting/reports/profit-loss")
async def get_profit_loss_report(start_date: str, end_date: str, current_user: User = Depends(get_current_user)):
    # Get all income
    invoices = await db.accounting_invoices.find({"tenant_id": current_user.tenant_id, "status": "paid", "issue_date": {"$gte": start_date, "$lte": end_date}}, {"_id": 0}).to_list(1000)

    # Get all expenses
    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": start_date, "$lte": end_date}}, {"_id": 0}).to_list(1000)

    total_revenue = sum(inv["total"] for inv in invoices)
    total_expenses = sum(exp["total_amount"] for exp in expenses)
    gross_profit = total_revenue - total_expenses
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    # Revenue breakdown
    revenue_by_category = {}
    for inv in invoices:
        for item in inv["items"]:
            desc = item["description"]
            revenue_by_category[desc] = revenue_by_category.get(desc, 0) + item["total"]

    # Expense breakdown
    expense_by_category = {}
    for exp in expenses:
        cat = exp["category"]
        expense_by_category[cat] = expense_by_category.get(cat, 0) + exp["total_amount"]

    return {
        "period": {"start": start_date, "end": end_date},
        "total_revenue": round(total_revenue, 2),
        "total_expenses": round(total_expenses, 2),
        "gross_profit": round(gross_profit, 2),
        "profit_margin": round(profit_margin, 2),
        "revenue_breakdown": revenue_by_category,
        "expense_breakdown": expense_by_category,
    }


@api_router.get("/accounting/reports/vat-report")
async def get_vat_report(start_date: str, end_date: str, current_user: User = Depends(get_current_user)):
    # Sales VAT (collected)
    invoices = await db.accounting_invoices.find({"tenant_id": current_user.tenant_id, "issue_date": {"$gte": start_date, "$lte": end_date}}, {"_id": 0}).to_list(1000)

    sales_vat = sum(inv["total_vat"] for inv in invoices)

    # Purchase VAT (paid)
    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": start_date, "$lte": end_date}}, {"_id": 0}).to_list(1000)

    purchase_vat = sum(exp["vat_amount"] for exp in expenses)

    vat_payable = sales_vat - purchase_vat

    return {"period": {"start": start_date, "end": end_date}, "sales_vat": round(sales_vat, 2), "purchase_vat": round(purchase_vat, 2), "vat_payable": round(vat_payable, 2)}


@api_router.get("/accounting/reports/balance-sheet")
async def get_balance_sheet(current_user: User = Depends(get_current_user)):
    # Assets
    bank_accounts = await db.bank_accounts.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    total_cash = sum(acc["balance"] for acc in bank_accounts)

    inventory = await db.inventory_items.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    total_inventory = sum(item["quantity"] * item["unit_cost"] for item in inventory)

    # Receivables (unpaid invoices)
    receivables = await db.accounting_invoices.find({"tenant_id": current_user.tenant_id, "status": {"$in": ["pending", "partial"]}}, {"_id": 0}).to_list(1000)
    total_receivables = sum(inv["total"] for inv in receivables)

    total_assets = total_cash + total_inventory + total_receivables

    # Liabilities
    payables = await db.expenses.find({"tenant_id": current_user.tenant_id, "payment_status": "pending"}, {"_id": 0}).to_list(1000)
    total_payables = sum(exp["total_amount"] for exp in payables)

    # Equity
    total_equity = total_assets - total_payables

    return {
        "assets": {"cash": round(total_cash, 2), "inventory": round(total_inventory, 2), "receivables": round(total_receivables, 2), "total": round(total_assets, 2)},
        "liabilities": {"payables": round(total_payables, 2), "total": round(total_payables, 2)},
        "equity": {"total": round(total_equity, 2)},
    }


@api_router.get("/accounting/dashboard")
async def get_accounting_dashboard(current_user: User = Depends(get_current_user)):
    # Get current month data
    today = datetime.now(UTC)
    month_start = today.replace(day=1, hour=0, minute=0, second=0).isoformat()
    month_end = today.isoformat()

    invoices = await db.accounting_invoices.find({"tenant_id": current_user.tenant_id, "issue_date": {"$gte": month_start, "$lte": month_end}}, {"_id": 0}).to_list(1000)

    expenses = await db.expenses.find({"tenant_id": current_user.tenant_id, "date": {"$gte": month_start, "$lte": month_end}}, {"_id": 0}).to_list(1000)

    total_income = sum(inv["total"] for inv in invoices if inv["status"] == "paid")
    total_expenses = sum(exp["total_amount"] for exp in expenses)
    pending_invoices = len([inv for inv in invoices if inv["status"] == "pending"])
    overdue_invoices = len([inv for inv in invoices if inv["status"] == "overdue"])

    # Get bank balances
    bank_accounts = await db.bank_accounts.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    total_bank_balance = sum(acc["balance"] for acc in bank_accounts)

    return {
        "monthly_income": round(total_income, 2),
        "monthly_expenses": round(total_expenses, 2),
        "net_income": round(total_income - total_expenses, 2),
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
        "total_bank_balance": round(total_bank_balance, 2),
    }
