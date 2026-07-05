"""Procurement / Satınalma — Suppliers, PR, PO, GRN.

Opera/Protel S&C ve Türk PMS rakipleri seviyesinde satınalma:
* Tedarikçi master (vendor master)
* Satınalma Talebi (PR) — departman talebi, onay akışı
* Satınalma Siparişi (PO) — PR'den veya direkt; tedarikçiye gönderim
* Mal Kabul Notu (GRN) — kısmi teslimat; kabulle stok güncellemesi
* 3-yönlü mutabakat hazırlığı (PO ↔ GRN ↔ Invoice)

Auto-numbering: SUP-YYYY-####, PR-YYYY-####, PO-YYYY-####, GRN-YYYY-####
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from cache_manager import cache as _cache
from cache_manager import cached as _cached
from core.audit import log_audit_event
from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
)
from core.security import get_current_user
from core.spa_mice_authz import require_procurement
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import (  # v76 Bug DL
    RolePermissionService,
    require_op,
)

router = APIRouter(prefix="/api/procurement", tags=["procurement"])

_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_system_db()
    try:
        await db.proc_suppliers.create_index([("tenant_id", 1), ("active", 1), ("name", 1)], name="proc_sup_name")
        await db.proc_suppliers.create_index([("tenant_id", 1), ("code", 1)], unique=True, sparse=True, name="proc_sup_code")
        await db.proc_purchase_requests.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="proc_pr_status")
        await db.proc_purchase_requests.create_index([("tenant_id", 1), ("pr_no", 1)], unique=True, name="proc_pr_no")
        await db.proc_purchase_orders.create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="proc_po_status")
        await db.proc_purchase_orders.create_index([("tenant_id", 1), ("po_no", 1)], unique=True, name="proc_po_no")
        await db.proc_purchase_orders.create_index([("tenant_id", 1), ("supplier_id", 1)], name="proc_po_supplier")
        await db.proc_goods_receipts.create_index([("tenant_id", 1), ("po_id", 1), ("received_at", -1)], name="proc_grn_po")
        await db.proc_goods_receipts.create_index([("tenant_id", 1), ("grn_no", 1)], unique=True, name="proc_grn_no")
        await db.proc_counters.create_index([("tenant_id", 1), ("kind", 1)], unique=True, name="proc_counter_uniq")
    except Exception:
        pass
    _indexes_ready = True


async def _next_no(tenant_id: str, kind: str, prefix: str) -> str:
    """Atomic per-tenant counter: PRE-YYYY-####."""
    db = get_system_db()
    year = datetime.now(UTC).year
    res = await db.proc_counters.find_one_and_update(
        {"tenant_id": tenant_id, "kind": kind, "year": year}, {"$inc": {"seq": 1}, "$setOnInsert": {"tenant_id": tenant_id, "kind": kind, "year": year}}, upsert=True, return_document=True
    )
    seq = res.get("seq", 1) if res else 1
    return f"{prefix}-{year}-{seq:04d}"


def _strip_id(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─── Suppliers ─────────────────────────────────────────────────


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=40)
    tax_no: str | None = Field(default=None, max_length=40)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    credit_limit: float | None = Field(default=None, ge=0, le=1e12)
    categories: list[str] = Field(default_factory=list)
    notes: str | None = None
    active: bool = True


@router.post("/suppliers")
async def create_supplier(
    body: SupplierIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    await _ensure_indexes()
    db = get_system_db()
    doc = body.model_dump()
    doc.update(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": current_user.username,
        }
    )
    try:
        await db.proc_suppliers.insert_one(doc)
    except Exception as exc:
        if "duplicate" in str(exc).lower():
            raise HTTPException(409, "Bu kod ile tedarikçi zaten var")
        raise
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action="create",
        entity_type="proc_supplier",
        entity_id=doc["id"],
        details=f"Tedarikçi: {doc['name']}",
        before_value=None,
        after_value=doc,
        db=db,
    )
    _invalidate_suppliers_cache(current_user.tenant_id)
    return _strip_id(doc)


def _invalidate_suppliers_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "proc_suppliers")


@router.get("/suppliers")
@_cached(ttl=120, key_prefix="proc_suppliers")
async def list_suppliers(
    active_only: bool = True,
    q: str | None = None,
    with_commitment: bool = False,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v76 Bug DL: vendor cost data
):
    await _ensure_indexes()
    db = get_system_db()
    query: dict = {"tenant_id": current_user.tenant_id}
    if active_only:
        query["active"] = True
    if q:
        import re as _re

        query["name"] = {"$regex": _re.escape(q.replace("\x00", "")), "$options": "i"}
    items = await db.proc_suppliers.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    if with_commitment and items:
        # Per-supplier open PO commitment (matches credit-limit enforcement
        # window in create PO: status in {sent, partially_received}). Single
        # aggregation round-trip; map onto supplier rows for headroom UI.
        pipeline = [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "status": {"$in": ["sent", "partially_received"]},
                }
            },
            {
                "$group": {
                    "_id": "$supplier_id",
                    "total": {"$sum": "$grand_total"},
                }
            },
        ]
        totals: dict[str, float] = {}
        async for doc in db.proc_purchase_orders.aggregate(pipeline):
            sid = doc.get("_id")
            if sid:
                totals[sid] = float(doc.get("total", 0) or 0)
        for s in items:
            s["open_commitment"] = round(totals.get(s.get("id"), 0.0), 2)
    return {"items": items, "count": len(items)}


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    body: SupplierIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    db = get_system_db()
    before = await db.proc_suppliers.find_one({"id": supplier_id, "tenant_id": current_user.tenant_id})
    if not before:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    patch = body.model_dump()
    patch["updated_at"] = datetime.now(UTC).isoformat()
    patch["updated_by"] = current_user.username
    await db.proc_suppliers.update_one({"id": supplier_id, "tenant_id": current_user.tenant_id}, {"$set": patch})
    after = await db.proc_suppliers.find_one({"id": supplier_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action="update",
        entity_type="proc_supplier",
        entity_id=supplier_id,
        details=f"Tedarikçi güncellendi: {after.get('name')}",
        before_value=_strip_id(before),
        after_value=after,
        db=db,
    )
    _invalidate_suppliers_cache(current_user.tenant_id)
    return after


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(
    supplier_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    db = get_system_db()
    in_use = await db.proc_purchase_orders.find_one({"tenant_id": current_user.tenant_id, "supplier_id": supplier_id, "status": {"$nin": ["cancelled", "closed"]}})
    if in_use:
        raise HTTPException(409, "Tedarikçi açık siparişlerde kullanılıyor; önce pasif yapın")
    res = await db.proc_suppliers.delete_one({"id": supplier_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action="delete",
        entity_type="proc_supplier",
        entity_id=supplier_id,
        details="Tedarikçi silindi",
        before_value=None,
        after_value=None,
        db=db,
    )
    _invalidate_suppliers_cache(current_user.tenant_id)
    return {"ok": True}


# ─── Purchase Request (PR) ─────────────────────────────────────


class PRLine(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    sku: str | None = None
    inventory_item_id: str | None = None  # housekeeping_inventory linkage
    quantity: float = Field(gt=0)
    unit: str = "adet"
    est_unit_cost: float = Field(ge=0, default=0)
    notes: str | None = None


class PRIn(BaseModel):
    department: str = Field(min_length=2, max_length=80)
    requester: str | None = None
    needed_by: date | None = None
    notes: str | None = None
    lines: list[PRLine] = Field(min_length=1)


def _pr_total(lines: list[dict]) -> float:
    return round(sum((line.get("quantity", 0) * line.get("est_unit_cost", 0)) for line in lines), 2)


@router.post("/purchase-requests")
async def create_purchase_request(
    body: PRIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    await _ensure_indexes()
    db = get_system_db()
    pr_no = await _next_no(current_user.tenant_id, "pr", "PR")
    payload = body.model_dump(mode="json")
    payload["lines_total"] = _pr_total(payload["lines"])
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "pr_no": pr_no,
        "status": "draft",
        "requester": payload.get("requester") or current_user.username,
        "department": payload["department"],
        "needed_by": payload.get("needed_by"),
        "notes": payload.get("notes"),
        "lines": payload["lines"],
        "lines_total": payload["lines_total"],
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    await db.proc_purchase_requests.insert_one(doc)
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action="create",
        entity_type="proc_pr",
        entity_id=doc["id"],
        details=f"PR {pr_no} ({payload['department']})",
        before_value=None,
        after_value=_strip_id(dict(doc)),
        db=db,
    )
    return _strip_id(doc)


@router.get("/purchase-requests")
async def list_prs(
    status: str | None = None,
    department: str | None = None,
    current_user: User = Depends(get_current_user),
):
    db = get_system_db()
    query: dict = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    if department:
        query["department"] = department
    items = await db.proc_purchase_requests.find(query, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"items": items, "count": len(items)}


@router.get("/purchase-requests/{pr_id}")
async def get_pr(pr_id: str, current_user: User = Depends(get_current_user)):
    db = get_system_db()
    doc = await db.proc_purchase_requests.find_one({"id": pr_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "PR bulunamadı")
    return doc


class PRStatusIn(BaseModel):
    status: Literal["submitted", "approved", "rejected", "cancelled"]
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_for_reject(cls, v, info):
        if info.data.get("status") in ("rejected", "cancelled"):
            if not v or len(v.strip()) < 5:
                raise ValueError("Red/iptal nedeni en az 5 karakter olmalı")
        return v


@router.post("/purchase-requests/{pr_id}/status")
async def change_pr_status(
    pr_id: str,
    body: PRStatusIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    db = get_system_db()
    before = await db.proc_purchase_requests.find_one({"id": pr_id, "tenant_id": current_user.tenant_id})
    if not before:
        raise HTTPException(404, "PR bulunamadı")
    cur = before.get("status", "draft")
    allowed = {
        "draft": {"submitted", "cancelled"},
        "submitted": {"approved", "rejected", "cancelled"},
        "approved": {"cancelled"},
        "rejected": set(),
        "cancelled": set(),
        "converted": set(),
    }
    if body.status not in allowed.get(cur, set()):
        raise HTTPException(409, f"Geçersiz durum geçişi: {cur} → {body.status}")
    patch: dict = {
        "status": body.status,
        "status_changed_at": datetime.now(UTC).isoformat(),
        "status_changed_by": current_user.username,
    }
    if body.reason:
        patch["status_reason"] = body.reason
    if body.status == "approved":
        patch["approved_at"] = patch["status_changed_at"]
        patch["approved_by"] = current_user.username
    await db.proc_purchase_requests.update_one({"id": pr_id, "tenant_id": current_user.tenant_id}, {"$set": patch})
    after = await db.proc_purchase_requests.find_one({"id": pr_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action=f"status:{body.status}",
        entity_type="proc_pr",
        entity_id=pr_id,
        details=f"PR {after.get('pr_no')} → {body.status}",
        before_value=_strip_id(before),
        after_value=after,
        db=db,
    )
    return after


# ─── Purchase Order (PO) ───────────────────────────────────────


class POLine(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    sku: str | None = None
    inventory_item_id: str | None = None
    quantity: float = Field(gt=0)
    unit: str = "adet"
    unit_cost: float = Field(ge=0)
    notes: str | None = None


class POIn(BaseModel):
    supplier_id: str
    source_pr_id: str | None = None
    expected_delivery: date | None = None
    currency: str = Field(default="TRY", max_length=3)
    tax_rate: float = Field(default=20.0, ge=0, le=100)
    notes: str | None = None
    lines: list[POLine] = Field(min_length=1)
    override_credit_limit: bool = False


async def _supplier_open_po_total(tenant_id: str, supplier_id: str) -> float:
    """Sum grand_total of open POs (draft / sent / partially_received)."""
    db = get_system_db()
    pipeline = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "supplier_id": supplier_id,
                "status": {"$in": ["draft", "sent", "partially_received"]},
            }
        },
        {"$group": {"_id": None, "total": {"$sum": "$grand_total"}}},
    ]
    open_total = 0.0
    async for row in db.proc_purchase_orders.aggregate(pipeline):
        open_total = float(row.get("total", 0) or 0)
    return round(open_total, 2)


def _po_compute(lines: list[dict], tax_rate: float) -> dict:
    subtotal = round(sum(line["quantity"] * line["unit_cost"] for line in lines), 2)
    tax = round(subtotal * tax_rate / 100.0, 2)
    return {"subtotal": subtotal, "tax_total": tax, "grand_total": round(subtotal + tax, 2)}


@router.post("/purchase-orders")
async def create_purchase_order(
    body: POIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    await _ensure_indexes()
    db = get_system_db()
    sup = await db.proc_suppliers.find_one({"id": body.supplier_id, "tenant_id": current_user.tenant_id})
    if not sup:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    if not sup.get("active", True):
        raise HTTPException(409, "Tedarikçi pasif")
    if body.source_pr_id:
        pr = await db.proc_purchase_requests.find_one({"id": body.source_pr_id, "tenant_id": current_user.tenant_id})
        if not pr:
            raise HTTPException(404, "Kaynak PR bulunamadı")
        if pr.get("status") != "approved":
            raise HTTPException(409, "Sadece onaylı PR'den PO oluşturulur")
    payload = body.model_dump(mode="json")
    lines = payload["lines"]
    for line in lines:
        line["received_qty"] = 0.0
        line["line_total"] = round(line["quantity"] * line["unit_cost"], 2)
    totals = _po_compute(lines, payload["tax_rate"])

    # Credit-limit enforcement: sum open PO grand_totals for this supplier
    # (draft + sent + partially_received) and reject if the new PO would
    # push the running commitment past supplier.credit_limit. Users with
    # `manage_credit_limit` permission may opt-in to bypass via
    # `override_credit_limit=true` on the request body.
    credit_limit = sup.get("credit_limit")
    if credit_limit is not None and credit_limit >= 0:
        override = bool(body.override_credit_limit)
        override_allowed = override and RolePermissionService().check_permission(
            current_user.role,
            "manage_credit_limit",
            granted_permissions=getattr(current_user, "granted_permissions", None),
        )
        if override and not override_allowed:
            raise HTTPException(403, "Kredi limiti aşımı override için 'manage_credit_limit' yetkisi gerekli")
        if not override_allowed:
            open_total = await _supplier_open_po_total(current_user.tenant_id, body.supplier_id)
            projected = round(open_total + totals["grand_total"], 2)
            if projected > float(credit_limit) + 1e-6:
                raise HTTPException(409, f"Tedarikçi kredi limiti aşıldı: açık {open_total:.2f} + yeni {totals['grand_total']:.2f} = {projected:.2f} > limit {float(credit_limit):.2f}")

    po_no = await _next_no(current_user.tenant_id, "po", "PO")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "po_no": po_no,
        "status": "draft",
        "supplier_id": body.supplier_id,
        "supplier_name": sup.get("name"),
        "supplier_payment_terms_days": sup.get("payment_terms_days", 30),
        "source_pr_id": body.source_pr_id,
        "expected_delivery": payload.get("expected_delivery"),
        "currency": payload["currency"],
        "tax_rate": payload["tax_rate"],
        "lines": lines,
        **totals,
        "notes": payload.get("notes"),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    await db.proc_purchase_orders.insert_one(doc)
    if body.source_pr_id:
        await db.proc_purchase_requests.update_one(
            {"id": body.source_pr_id, "tenant_id": current_user.tenant_id},
            {"$set": {"status": "converted", "converted_to_po_id": doc["id"], "converted_to_po_no": po_no, "converted_at": doc["created_at"]}},
        )
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action="create",
        entity_type="proc_po",
        entity_id=doc["id"],
        details=f"PO {po_no} → {sup.get('name')} ({totals['grand_total']} {body.currency})",
        before_value=None,
        after_value=_strip_id(dict(doc)),
        db=db,
    )
    return _strip_id(doc)


@router.get("/purchase-orders")
async def list_pos(
    status: str | None = None,
    supplier_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    db = get_system_db()
    query: dict = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    if supplier_id:
        query["supplier_id"] = supplier_id
    items = await db.proc_purchase_orders.find(query, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"items": items, "count": len(items)}


@router.get("/purchase-orders/{po_id}")
async def get_po(po_id: str, current_user: User = Depends(get_current_user)):
    db = get_system_db()
    doc = await db.proc_purchase_orders.find_one({"id": po_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "PO bulunamadı")
    grns = await db.proc_goods_receipts.find({"tenant_id": current_user.tenant_id, "po_id": po_id}, {"_id": 0}).sort("received_at", -1).to_list(100)
    doc["grns"] = grns
    return doc


@router.get("/credit-utilisation")
async def credit_utilisation_report(
    include_unlimited: bool = False,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Portfolio view of supplier credit exposure for finance (Task #79).

    Returns every active supplier with the same open-PO commitment used
    by the create-PO guard (``draft / sent / partially_received``).
    Rows are sorted by ``used_pct`` descending so suppliers nearest /
    over their limit appear first; suppliers without a credit_limit
    (only returned when ``include_unlimited=true``) sort last.

    Status badges:
      * ``ok``       — used_pct < 80 (or no limit set, no open commitment)
      * ``warning``  — used_pct >= 80 and <= 100
      * ``exceeded`` — open_total > limit
      * ``no_limit`` — supplier has no credit_limit configured
    """
    db = get_system_db()
    sup_query: dict = {
        "tenant_id": current_user.tenant_id,
        "active": True,
    }
    if not include_unlimited:
        sup_query["credit_limit"] = {"$gt": 0}
    suppliers = await db.proc_suppliers.find(
        sup_query,
        {"_id": 0, "id": 1, "name": 1, "code": 1, "credit_limit": 1},
    ).to_list(2000)

    pipeline = [
        {
            "$match": {
                "tenant_id": current_user.tenant_id,
                "status": {"$in": ["draft", "sent", "partially_received"]},
            }
        },
        {"$group": {"_id": "$supplier_id", "total": {"$sum": "$grand_total"}}},
    ]
    totals: dict[str, float] = {}
    async for row in db.proc_purchase_orders.aggregate(pipeline):
        sid = row.get("_id")
        if sid:
            totals[sid] = float(row.get("total", 0) or 0)

    rows: list[dict] = []
    for s in suppliers:
        sid = s.get("id")
        limit = s.get("credit_limit")
        open_total = round(totals.get(sid, 0.0), 2)
        used_pct: float | None = None
        headroom: float | None = None
        status = "no_limit"
        if limit is not None and float(limit) > 0:
            used_pct = round(open_total / float(limit) * 100.0, 2)
            headroom = round(float(limit) - open_total, 2)
            if open_total > float(limit) + 1e-6:
                status = "exceeded"
            elif used_pct >= 80.0:
                status = "warning"
            else:
                status = "ok"
        elif limit is not None and float(limit) == 0:
            headroom = 0.0
            used_pct = 0.0
            status = "exceeded" if open_total > 0 else "ok"
        rows.append(
            {
                "supplier_id": sid,
                "supplier_name": s.get("name"),
                "supplier_code": s.get("code"),
                "limit": float(limit) if limit is not None else None,
                "open_total": open_total,
                "headroom": headroom,
                "used_pct": used_pct,
                "status": status,
            }
        )

    rows.sort(
        key=lambda r: (
            r["used_pct"] is None,
            -(r["used_pct"] or 0.0),
            (r["supplier_name"] or "").lower(),
        )
    )
    return {"items": rows, "count": len(rows)}


@router.get("/suppliers/{supplier_id}/credit-utilisation")
async def supplier_credit_utilisation(
    supplier_id: str,
    projected_amount: float = 0.0,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Return supplier credit headroom so the PO form can warn buyers
    before the create endpoint hard-rejects (HTTP 409) at >100%.

    Response fields:
      limit             — supplier.credit_limit (None if unset)
      open_total        — sum of open PO grand_totals
                          (draft / sent / partially_received)
      projected_amount  — echoed back (0 if not provided)
      projected_total   — open_total + projected_amount
      headroom          — limit - projected_total (None if no limit)
      used_pct          — projected_total / limit * 100 (None if no limit)
      warning           — True when used_pct >= 80
      exceeded          — True when projected_total > limit
    """
    db = get_system_db()
    sup = await db.proc_suppliers.find_one({"id": supplier_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "credit_limit": 1, "name": 1})
    if not sup:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    limit = sup.get("credit_limit")
    open_total = await _supplier_open_po_total(current_user.tenant_id, supplier_id)
    projected_amount = max(0.0, float(projected_amount or 0))
    projected_total = round(open_total + projected_amount, 2)
    used_pct: float | None = None
    headroom: float | None = None
    warning = False
    exceeded = False
    if limit is not None and float(limit) > 0:
        used_pct = round(projected_total / float(limit) * 100.0, 2)
        headroom = round(float(limit) - projected_total, 2)
        warning = used_pct >= 80.0
        exceeded = projected_total > float(limit) + 1e-6
    elif limit is not None and float(limit) == 0:
        headroom = 0.0
        used_pct = 0.0
        exceeded = projected_total > 0
        warning = exceeded
    return {
        "supplier_id": supplier_id,
        "supplier_name": sup.get("name"),
        "limit": float(limit) if limit is not None else None,
        "open_total": open_total,
        "projected_amount": round(projected_amount, 2),
        "projected_total": projected_total,
        "headroom": headroom,
        "used_pct": used_pct,
        "warning": warning,
        "exceeded": exceeded,
    }


class POStatusIn(BaseModel):
    status: Literal["sent", "cancelled", "closed"]
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_for_cancel(cls, v, info):
        if info.data.get("status") == "cancelled":
            if not v or len(v.strip()) < 5:
                raise ValueError("İptal nedeni en az 5 karakter olmalı")
        return v


@router.post("/purchase-orders/{po_id}/status")
async def change_po_status(
    po_id: str,
    body: POStatusIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    db = get_system_db()
    before = await db.proc_purchase_orders.find_one({"id": po_id, "tenant_id": current_user.tenant_id})
    if not before:
        raise HTTPException(404, "PO bulunamadı")
    cur = before.get("status", "draft")
    allowed = {
        "draft": {"sent", "cancelled"},
        "sent": {"cancelled"},
        "partially_received": {"cancelled"},
        "received": {"closed"},
    }
    if body.status not in allowed.get(cur, set()):
        raise HTTPException(409, f"Geçersiz durum geçişi: {cur} → {body.status}")
    patch = {
        "status": body.status,
        "status_changed_at": datetime.now(UTC).isoformat(),
        "status_changed_by": current_user.username,
    }
    if body.reason:
        patch["status_reason"] = body.reason
    if body.status == "sent":
        patch["sent_at"] = patch["status_changed_at"]
    await db.proc_purchase_orders.update_one({"id": po_id, "tenant_id": current_user.tenant_id}, {"$set": patch})
    after = await db.proc_purchase_orders.find_one({"id": po_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.username,
        action=f"status:{body.status}",
        entity_type="proc_po",
        entity_id=po_id,
        details=f"PO {after.get('po_no')} → {body.status}",
        before_value=_strip_id(before),
        after_value=after,
        db=db,
    )
    return after


# ─── Goods Receipt Note (GRN) ──────────────────────────────────


class GRNLine(BaseModel):
    po_line_idx: int = Field(ge=0)
    received_qty: float = Field(gt=0)
    qc_status: Literal["accepted", "rejected", "partial"] = "accepted"
    notes: str | None = None


class GRNIn(BaseModel):
    received_at: datetime | None = None
    notes: str | None = None
    lines: list[GRNLine] = Field(min_length=1)


async def _grn_apply(db, tenant_id: str, po_id: str, body: GRNIn, username: str, session=None) -> tuple[dict, str, dict]:
    """Read-validate-write the PO+GRN within a single (optionally
    transactional) session. Returns (grn_doc, new_status, stock_increments).
    """
    po = await db.proc_purchase_orders.find_one({"id": po_id, "tenant_id": tenant_id}, session=session)
    if not po:
        raise HTTPException(404, "PO bulunamadı")
    if po.get("status") not in ("sent", "partially_received"):
        raise HTTPException(409, "Mal kabul yalnızca gönderilmiş veya kısmi alınmış POlar için")
    po_lines = list(po.get("lines") or [])
    new_received = [float(line.get("received_qty", 0)) for line in po_lines]
    grn_lines_out: list[dict] = []
    stock_increments: dict[str, float] = {}
    for grn_line in body.lines:
        if grn_line.po_line_idx >= len(po_lines):
            raise HTTPException(422, f"Geçersiz po_line_idx={grn_line.po_line_idx}")
        po_line = po_lines[grn_line.po_line_idx]
        ordered = float(po_line.get("quantity", 0))
        already = new_received[grn_line.po_line_idx]
        if grn_line.qc_status != "rejected":
            new_total = already + grn_line.received_qty
            if new_total > ordered + 1e-6:
                raise HTTPException(422, f"{po_line.get('item_name')}: kabul ({new_total}) sipariş miktarını ({ordered}) aşıyor")
            new_received[grn_line.po_line_idx] = new_total
            inv_id = po_line.get("inventory_item_id")
            if inv_id:
                stock_increments[inv_id] = stock_increments.get(inv_id, 0.0) + grn_line.received_qty
        grn_lines_out.append(
            {
                "po_line_idx": grn_line.po_line_idx,
                "item_name": po_line.get("item_name"),
                "sku": po_line.get("sku"),
                "inventory_item_id": po_line.get("inventory_item_id"),
                "received_qty": grn_line.received_qty,
                "qc_status": grn_line.qc_status,
                "notes": grn_line.notes,
            }
        )

    grn_no = await _next_no(tenant_id, "grn", "GRN")
    received_at = (body.received_at or datetime.now(UTC)).isoformat()
    grn_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "grn_no": grn_no,
        "po_id": po_id,
        "po_no": po.get("po_no"),
        "supplier_id": po.get("supplier_id"),
        "supplier_name": po.get("supplier_name"),
        "received_at": received_at,
        "received_by": username,
        "notes": body.notes,
        "lines": grn_lines_out,
        "created_at": datetime.now(UTC).isoformat(),
    }
    for idx, qty in enumerate(new_received):
        po_lines[idx]["received_qty"] = qty
    fully = all(line["received_qty"] >= line["quantity"] - 1e-6 for line in po_lines)
    any_recv = any(line["received_qty"] > 0 for line in po_lines)
    new_status = "received" if fully else ("partially_received" if any_recv else po.get("status"))
    # Inside a Mongo transaction, snapshot isolation + automatic
    # write-conflict detection guarantees mutual exclusion: if two
    # concurrent GRN transactions both read the same PO and try to
    # write, one of them is aborted with WriteConflict (code 112).
    # The outer handler converts that to a 409. So a plain id+tenant
    # filter is sufficient — no CAS needed.
    res = await db.proc_purchase_orders.update_one({"id": po_id, "tenant_id": tenant_id}, {"$set": {"lines": po_lines, "status": new_status, "last_received_at": received_at}}, session=session)
    if not res.matched_count:
        raise HTTPException(404, "PO güncellenemedi")
    await db.proc_goods_receipts.insert_one(grn_doc, session=session)
    return grn_doc, new_status, stock_increments


@router.post("/purchase-orders/{po_id}/grn")
async def create_grn(
    po_id: str,
    body: GRNIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    require_procurement(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # Run in a transaction when replica set is available so
    # concurrent GRNs against the same PO line cannot interleave
    # the read-modify-write cycle (architect: CRITICAL).
    grn_doc: dict
    new_status: str
    stock_increments: dict
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                grn_doc, new_status, stock_increments = await _grn_apply(db, tenant_id, po_id, body, current_user.username, session=session)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Mongo write-conflict (code 112) under concurrent GRNs
        # against same PO → return 409 so client can retry.
        code = getattr(exc, "code", None)
        if code == 112 or "WriteConflict" in str(exc):
            raise HTTPException(409, "PO eş zamanlı güncellendi; lütfen tekrar deneyin")
        if not is_replica_set_unavailable(exc):
            raise
        if not standalone_fallback_allowed():
            raise HTTPException(status_code=503, detail=("Mal kabul atomik garanti sağlayamıyor (Mongo replica set gerekli)."))
        # Dev opt-in: best-effort non-tx fallback.
        grn_doc, new_status, stock_increments = await _grn_apply(db, tenant_id, po_id, body, current_user.username)

    # Stock effect on housekeeping_inventory (if linked) — outside the
    # transaction since housekeeping_inventory is a separate domain
    # collection; per-doc $inc is itself atomic.
    for inv_id, qty in stock_increments.items():
        await db.housekeeping_inventory.update_one({"id": inv_id, "tenant_id": tenant_id}, {"$inc": {"current_stock": qty}, "$set": {"last_restock_date": datetime.now(UTC)}})

    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.username,
        action="create",
        entity_type="proc_grn",
        entity_id=grn_doc["id"],
        details=(f"{grn_doc.get('grn_no')} ← PO {grn_doc.get('po_no')} ({len(grn_doc.get('lines') or [])} kalem)"),
        before_value=None,
        after_value=_strip_id(dict(grn_doc)),
        db=db,
    )
    return {
        "grn": _strip_id(grn_doc),
        "po_status": new_status,
        "stock_updated": stock_increments,
    }


@router.get("/purchase-orders/{po_id}/grns")
async def list_grns(po_id: str, current_user: User = Depends(get_current_user)):
    db = get_system_db()
    items = await db.proc_goods_receipts.find({"tenant_id": current_user.tenant_id, "po_id": po_id}, {"_id": 0}).sort("received_at", -1).to_list(200)
    return {"items": items, "count": len(items)}


# ─── Dashboard summary ─────────────────────────────────────────


@router.get("/summary")
async def procurement_summary(
    current_user: User = Depends(get_current_user),
):
    # Perf: önceden 5 ardışık count_documents + cursor taraması ~1.2s
    # alıyordu (Atlas RTT × 6). asyncio.gather ile paralelize + commitment
    # için aggregation $sum (cursor + Python toplama yerine tek round-trip
    # MongoDB tarafında) → tek yavaş round-trip kadar bekleniyor (~270ms).
    import asyncio

    db = get_system_db()
    tid = current_user.tenant_id

    async def _commitment_sum() -> float:
        pipeline = [
            {
                "$match": {
                    "tenant_id": tid,
                    "status": {"$in": ["sent", "partially_received"]},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$grand_total"}}},
        ]
        cursor = db.proc_purchase_orders.aggregate(pipeline)
        async for doc in cursor:
            return float(doc.get("total", 0) or 0)
        return 0.0

    pr_pending, pr_approved, po_open, po_received, suppliers, commitment = await asyncio.gather(
        db.proc_purchase_requests.count_documents({"tenant_id": tid, "status": {"$in": ["draft", "submitted"]}}),
        db.proc_purchase_requests.count_documents({"tenant_id": tid, "status": "approved"}),
        db.proc_purchase_orders.count_documents({"tenant_id": tid, "status": {"$in": ["draft", "sent", "partially_received"]}}),
        db.proc_purchase_orders.count_documents({"tenant_id": tid, "status": "received"}),
        db.proc_suppliers.count_documents({"tenant_id": tid, "active": True}),
        _commitment_sum(),
    )
    return {
        "suppliers_active": suppliers,
        "pr_pending": pr_pending,
        "pr_approved": pr_approved,
        "po_open": po_open,
        "po_received": po_received,
        "open_commitment_value": round(commitment, 2),
    }

# ─────────────────────────────────────────────────────────────────────
# Fatura / Satın Alma Muhasebeleştirme
# ─────────────────────────────────────────────────────────────────────
@router.post("/post-invoice-to-gl")
async def post_invoice_to_gl(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Sisteme girilen tedarikçi faturasını Genel Muhasebe Mizanına işler.
    153 Ticari Mallar (Borç) - 320 Satıcılar (Alacak)
    """
    require_op(current_user, ["proc_read"]) # using read as placeholder or could be proc_write
    
    amount = float(payload.get("amount", 0))
    supplier_name = payload.get("supplier_name", "Bilinmeyen Tedarikçi")
    invoice_no = payload.get("invoice_no", "FAT-000")
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Fatura tutarı 0'dan büyük olmalıdır.")
        
    try:
        from routers.finance.general_ledger import mock_db as gl_db
        import uuid
        from datetime import datetime
        
        journal_entry = {
            "id": str(uuid.uuid4()),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "type": "Alış Faturası",
            "description": f"Tedarikçi Faturası: {supplier_name} ({invoice_no})",
            "total": amount,
            "timestamp": datetime.utcnow().isoformat(),
            "lines": [
                {
                    "account_code": "153",
                    "debit": amount,
                    "credit": 0.0,
                    "description": "Ticari Mallar Girişi"
                },
                {
                    "account_code": "320",
                    "debit": 0.0,
                    "credit": amount,
                    "description": f"Satıcılar: {supplier_name}"
                }
            ]
        }
        gl_db["journals"].append(journal_entry)
        return {"status": "success", "message": f"{amount} TL tutarındaki fatura başarıyla muhasebeleştirildi (153/320)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
