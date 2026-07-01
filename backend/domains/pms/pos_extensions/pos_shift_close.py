"""POS Shift Close — vardiya aç/kapa + nakit mutabakat.

Mevcut z-report endpoint'i bozulmaz. Bu modül kasiyer-bazlı vardiya
(open → expected sum from pos_transactions → counted cash → variance)
ekler. Aynı kasiyer için aynı outlet'te aktif vardiya unique compound
guard ile engellenir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import ensure_compound_unique

router = APIRouter(prefix="/api/pos/ext/shifts", tags=["pos-ext-shifts"])


async def _ensure_shift_indexes() -> None:
    # Atomic open-shift guard at DB level — only one row may exist with
    # status='open' for the same (tenant, outlet, cashier). When a shift is
    # closed the partial filter no longer matches, allowing a new open shift.
    await ensure_compound_unique(
        db.pos_shifts,
        keys=[("tenant_id", 1), ("outlet_id", 1), ("cashier_id", 1)],
        partial_filter={"status": "open"},
        name="pos_shifts_open_unique",
    )


class ShiftOpen(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outlet_id: str = Field(min_length=1)
    opening_cash: float = Field(default=0, ge=0)
    cashier_id: str | None = None  # default = current_user.id
    note: str | None = None


class CashCount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    denomination: float = Field(gt=0)
    count: int = Field(ge=0)


class ShiftClose(BaseModel):
    model_config = ConfigDict(extra="ignore")
    counted_cash_total: float | None = Field(default=None, ge=0)
    counted_breakdown: list[CashCount] | None = None
    notes: str | None = None
    blind: bool = False  # blind = kasiyer expected_cash görmeden sayar


def _now() -> datetime:
    return datetime.now(UTC)


async def _expected_cash_for_shift(tenant_id: str, shift: dict) -> dict:
    """Sum pos_transactions cash payments closed during the shift window for this cashier."""
    q: dict = {
        "tenant_id": tenant_id,
        "outlet_id": shift["outlet_id"],
        "payment_method": "cash",
        "status": {"$in": ["completed", "closed"]},
        "closed_at": {"$gte": shift["opened_at"]},
    }
    if shift.get("cashier_id"):
        q["cashier_id"] = shift["cashier_id"]
    rows = await db.pos_transactions.find(q, {"_id": 0, "amount_paid": 1, "grand_total": 1, "total": 1}).to_list(2000)
    cash_sum = 0.0
    for r in rows:
        v = r.get("amount_paid") or r.get("grand_total") or r.get("total") or 0
        try:
            cash_sum += float(v)
        except Exception:
            pass
    return {"cash_sales": round(cash_sum, 2), "tx_count": len(rows)}


@router.post("/open")
async def open_shift(body: ShiftOpen, current_user: User = Depends(get_current_user)):
    await _ensure_shift_indexes()
    cashier = body.cashier_id or current_user.id
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "outlet_id": body.outlet_id,
        "cashier_id": cashier,
        "opening_cash": float(body.opening_cash),
        "status": "open",
        "opened_at": _now(),
        "opened_by": current_user.id,
        "note": body.note,
    }
    try:
        await db.pos_shifts.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.pos_shifts.find_one(
            {
                "tenant_id": current_user.tenant_id,
                "outlet_id": body.outlet_id,
                "cashier_id": cashier,
                "status": "open",
            },
            {"_id": 0, "id": 1},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Open shift already exists: {(existing or {}).get('id', 'unknown')}",
        )
    doc.pop("_id", None)
    return {"success": True, "shift": doc}


@router.get("/open")
async def get_open_shift(
    outlet_id: str = Query(..., min_length=1),
    cashier_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    q = {
        "tenant_id": current_user.tenant_id,
        "outlet_id": outlet_id,
        "status": "open",
    }
    if cashier_id:
        q["cashier_id"] = cashier_id
    rows = await db.pos_shifts.find(q, {"_id": 0}).to_list(20)
    return {"open_shifts": rows, "count": len(rows)}


@router.post("/{shift_id}/close")
async def close_shift(shift_id: str, body: ShiftClose, current_user: User = Depends(get_current_user)):
    shift = await db.pos_shifts.find_one({"id": shift_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    if shift.get("status") != "open":
        # Idempotent close
        return {"success": True, "shift": shift, "idempotent": True}

    # Compute counted total from breakdown if given.
    counted = body.counted_cash_total
    breakdown_total: float | None = None
    if body.counted_breakdown:
        breakdown_total = round(sum(c.denomination * c.count for c in body.counted_breakdown), 2)
        if counted is None:
            counted = breakdown_total
    if counted is None:
        raise HTTPException(status_code=400, detail="counted_cash_total veya counted_breakdown gerekli")

    sales = await _expected_cash_for_shift(current_user.tenant_id, shift)
    expected_total = round(float(shift.get("opening_cash", 0)) + sales["cash_sales"], 2)
    variance = round(float(counted) - expected_total, 2)

    update = {
        "status": "closed",
        "closed_at": _now(),
        "closed_by": current_user.id,
        "counted_cash_total": float(counted),
        "expected_cash_total": expected_total,
        "cash_sales": sales["cash_sales"],
        "tx_count": sales["tx_count"],
        "variance": variance,
        "blind": bool(body.blind),
        "notes": body.notes,
    }
    if breakdown_total is not None:
        update["counted_breakdown_total"] = breakdown_total

    await db.pos_shifts.update_one({"id": shift_id, "tenant_id": current_user.tenant_id}, {"$set": update})

    if body.counted_breakdown:
        await db.pos_shift_cash_counts.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "shift_id": shift_id,
                "breakdown": [c.model_dump() for c in body.counted_breakdown],
                "total": breakdown_total,
                "created_at": _now(),
                "created_by": current_user.id,
            }
        )

    closed = {**shift, **update}
    closed.pop("_id", None)
    return {"success": True, "shift": closed}


@router.get("")
async def list_shifts(
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    outlet_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if outlet_id:
        q["outlet_id"] = outlet_id
    rows = await db.pos_shifts.find(q, {"_id": 0}).sort("opened_at", -1).to_list(limit)
    return {"shifts": rows, "count": len(rows)}


@router.get("/{shift_id}")
async def get_shift(shift_id: str, current_user: User = Depends(get_current_user)):
    shift = await db.pos_shifts.find_one({"id": shift_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    breakdowns = await db.pos_shift_cash_counts.find({"tenant_id": current_user.tenant_id, "shift_id": shift_id}, {"_id": 0}).sort("created_at", -1).to_list(10)
    return {"shift": shift, "cash_counts": breakdowns}
