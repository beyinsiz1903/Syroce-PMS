"""
Accounting / Accounts Payable (AP) — Tedarikçi fatura defteri + ödeme planı
===========================================================================
Tedarikçi (proc_suppliers) faturalarının kaydı, satınalma siparişiyle (proc_
purchase_orders) opsiyonel bağ, vade/aging, kısmi ödeme ve ödeme eşleştirme.

Değişmezler:
  * Tenant-scoped; mutasyonlar muhasebe seviyesi RBAC.
  * paid_amount HER ZAMAN ap_payments toplamından yeniden hesaplanır (ledger
    recalc), asla $inc. Böylece çift sayım imkânsız.
  * Ödeme idempotent (idempotency_key partial-unique; replay → mevcut durum).
  * Fazla/aşan ödeme reddedilir; void faturaya ödeme yapılamaz; ödemesi olan
    fatura void edilemez. Fail-closed.
"""

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import get_current_user
from models.schemas import User
from shared_kernel.pos_idem import ensure_compound_unique

logger = logging.getLogger("domains.accounting.ap")

router = APIRouter(prefix="/api/ap", tags=["Accounting / AP"])

_AP_ROLES = {"super_admin", "admin", "accountant"}
_READ_ROLES = {"super_admin", "admin", "accountant", "supervisor"}
_EPS = 0.005


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _tenant_of(user: User) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant bulunamadı")
    return tid


def _role_of(user: User) -> str:
    role = getattr(user, "role", None)
    return getattr(role, "value", role) or ""


def _require_role(user: User, allowed: set[str]) -> None:
    if getattr(user, "is_super_admin", False):
        return
    if _role_of(user) not in allowed:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")


def _actor_id(user: User) -> str:
    return getattr(user, "id", None) or getattr(user, "user_id", None) or "system"


async def _ensure_payment_idem(tenant_id: str) -> None:
    await ensure_compound_unique(
        db.ap_payments,
        [("tenant_id", 1), ("idempotency_key", 1)],
        partial_filter={"idempotency_key": {"$type": "string"}},
        name="ux_ap_payment_idem",
    )


def _status_for(total: float, paid: float) -> str:
    if paid <= _EPS:
        return "open"
    if paid + _EPS >= total:
        return "paid"
    return "partial"


async def _recalc_invoice(tenant_id: str, invoice_id: str) -> dict:
    """paid_amount'ı ödemelerden yeniden hesaplar, status'u günceller, faturayı döner."""
    inv = await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    if inv.get("status") == "void":
        return inv
    payments = await db.ap_payments.find({"tenant_id": tenant_id, "invoice_id": invoice_id}, {"_id": 0}).to_list(10000)
    paid = round(sum(float(p.get("amount", 0) or 0) for p in payments), 2)
    total = float(inv.get("total_amount", 0) or 0)
    status = _status_for(total, paid)
    await db.ap_invoices.update_one(
        {"tenant_id": tenant_id, "id": invoice_id},
        {
            "$set": {
                "paid_amount": paid,
                "balance": round(total - paid, 2),
                "overpaid": paid > total + _EPS,
                "status": status,
                "updated_at": _now_iso(),
            }
        },
    )
    return await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────────────
class InvoiceIn(BaseModel):
    supplier_id: str = Field(..., min_length=1, max_length=64)
    supplier_name: str | None = Field(None, max_length=200)
    invoice_no: str = Field(..., min_length=1, max_length=80)
    po_id: str | None = Field(None, max_length=64)
    issue_date: str | None = Field(None, max_length=40)
    due_date: str = Field(..., max_length=40)
    currency: str = Field("TRY", min_length=3, max_length=3)
    subtotal: float = Field(..., ge=0)
    tax: float = Field(0, ge=0)
    memo: str | None = Field(None, max_length=500)


class PaymentIn(BaseModel):
    amount: float = Field(..., gt=0)
    paid_at: str | None = Field(None, max_length=40)
    method: str = Field("bank_transfer", max_length=40)
    reference: str | None = Field(None, max_length=120)
    idempotency_key: str | None = Field(None, max_length=120)


# ─────────────────────────────────────────────────────────────────────
# Fatura defteri
# ─────────────────────────────────────────────────────────────────────
@router.get("/invoices")
async def list_invoices(
    supplier_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if supplier_id:
        q["supplier_id"] = supplier_id
    if status:
        q["status"] = status
    rows = await db.ap_invoices.find(q, {"_id": 0}).sort("due_date", 1).to_list(limit)
    return {"invoices": rows}


@router.post("/invoices")
async def create_invoice(payload: InvoiceIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _AP_ROLES)
    tenant_id = _tenant_of(current_user)

    supplier = await db.proc_suppliers.find_one({"tenant_id": tenant_id, "id": payload.supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Tedarikçi bulunamadı")
    if payload.po_id:
        po = await db.proc_purchase_orders.find_one({"tenant_id": tenant_id, "id": payload.po_id}, {"_id": 0})
        if not po:
            raise HTTPException(status_code=404, detail="Satınalma siparişi bulunamadı")

    dup = await db.ap_invoices.find_one(
        {"tenant_id": tenant_id, "supplier_id": payload.supplier_id, "invoice_no": payload.invoice_no},
        {"_id": 0},
    )
    if dup:
        raise HTTPException(status_code=400, detail="Bu tedarikçi için aynı fatura no zaten kayıtlı")

    total = round(float(payload.subtotal) + float(payload.tax), 2)
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "supplier_id": payload.supplier_id,
        "supplier_name": payload.supplier_name or supplier.get("name"),
        "invoice_no": payload.invoice_no.strip(),
        "po_id": payload.po_id,
        "issue_date": payload.issue_date or _today(),
        "due_date": payload.due_date,
        "currency": payload.currency.upper(),
        "subtotal": round(float(payload.subtotal), 2),
        "tax": round(float(payload.tax), 2),
        "total_amount": total,
        "paid_amount": 0.0,
        "balance": total,
        "overpaid": False,
        "status": "open",
        "memo": (payload.memo or "").strip() or None,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.ap_invoices.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"invoice": doc}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    inv = await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    payments = await db.ap_payments.find({"tenant_id": tenant_id, "invoice_id": invoice_id}, {"_id": 0}).to_list(10000)
    return {"invoice": inv, "payments": payments}


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _AP_ROLES)
    tenant_id = _tenant_of(current_user)
    inv = await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    if inv.get("status") == "void":
        return {"invoice": inv}
    payments = await db.ap_payments.find({"tenant_id": tenant_id, "invoice_id": invoice_id}, {"_id": 0}).to_list(1)
    if payments:
        raise HTTPException(status_code=409, detail="Ödemesi olan fatura void edilemez")
    await db.ap_invoices.update_one(
        {"tenant_id": tenant_id, "id": invoice_id},
        {"$set": {"status": "void", "updated_at": _now_iso(), "voided_by": _actor_id(current_user)}},
    )
    inv = await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})
    return {"invoice": inv}


@router.post("/invoices/{invoice_id}/payments")
async def apply_payment(invoice_id: str, payload: PaymentIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _AP_ROLES)
    tenant_id = _tenant_of(current_user)

    inv = await db.ap_invoices.find_one({"tenant_id": tenant_id, "id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    if inv.get("status") == "void":
        raise HTTPException(status_code=409, detail="Void faturaya ödeme yapılamaz")

    total = float(inv.get("total_amount", 0) or 0)
    already = float(inv.get("paid_amount", 0) or 0)
    remaining = round(total - already, 2)
    amount = round(float(payload.amount), 2)
    if amount > remaining + _EPS:
        raise HTTPException(
            status_code=400,
            detail=f"Ödeme kalan bakiyeyi aşıyor (kalan={remaining})",
        )

    idem = (payload.idempotency_key or "").strip() or None
    if idem:
        await _ensure_payment_idem(tenant_id)

    now = _now_iso()
    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "supplier_id": inv.get("supplier_id"),
        "amount": amount,
        "paid_at": payload.paid_at or now,
        "method": payload.method,
        "reference": (payload.reference or "").strip() or None,
        "idempotency_key": idem,
        "created_at": now,
        "created_by": _actor_id(current_user),
    }
    try:
        await db.ap_payments.insert_one(dict(payment))
    except DuplicateKeyError:
        existing = await db.ap_payments.find_one({"tenant_id": tenant_id, "idempotency_key": idem}, {"_id": 0})
        inv = await _recalc_invoice(tenant_id, invoice_id)
        return {"invoice": inv, "payment": existing, "idempotent_replay": True}

    inv = await _recalc_invoice(tenant_id, invoice_id)
    payment.pop("_id", None)
    return {"invoice": inv, "payment": payment}


# ─────────────────────────────────────────────────────────────────────
# Aging
# ─────────────────────────────────────────────────────────────────────
def _days_between(d1: str, d2: str) -> int:
    try:
        a = date.fromisoformat(d1[:10])
        b = date.fromisoformat(d2[:10])
        return (a - b).days
    except (ValueError, TypeError):
        return 0


@router.get("/aging")
async def aging(
    as_of: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    ref = (as_of or _today())[:10]

    invoices = await db.ap_invoices.find({"tenant_id": tenant_id, "status": {"$in": ["open", "partial"]}}, {"_id": 0}).to_list(50000)

    buckets = {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    by_supplier: dict[str, dict] = {}
    total_outstanding = 0.0
    for inv in invoices:
        bal = round(
            float(inv.get("total_amount", 0) or 0) - float(inv.get("paid_amount", 0) or 0),
            2,
        )
        if bal <= _EPS:
            continue
        overdue = _days_between(ref, inv.get("due_date", ref))
        if overdue <= 0:
            bk = "current"
        elif overdue <= 30:
            bk = "d1_30"
        elif overdue <= 60:
            bk = "d31_60"
        elif overdue <= 90:
            bk = "d61_90"
        else:
            bk = "d90_plus"
        buckets[bk] += bal
        total_outstanding += bal
        sid = inv.get("supplier_id")
        srow = by_supplier.setdefault(sid, {"supplier_id": sid, "supplier_name": inv.get("supplier_name"), "outstanding": 0.0, "invoice_count": 0})
        srow["outstanding"] += bal
        srow["invoice_count"] += 1

    for srow in by_supplier.values():
        srow["outstanding"] = round(srow["outstanding"], 2)
    return {
        "as_of": ref,
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "total_outstanding": round(total_outstanding, 2),
        "by_supplier": sorted(by_supplier.values(), key=lambda r: r["outstanding"], reverse=True),
    }
