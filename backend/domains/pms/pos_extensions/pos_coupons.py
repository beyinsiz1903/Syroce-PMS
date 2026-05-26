"""POS Coupons — kupon kodu motoru (validate + atomic redeem).

Çift-harcama guard'ı: redeem `findOneAndUpdate` ile `used_count < max_uses`
condition'ı altında atomik increment yapar (race condition'da iki redeem'in
ikisi de geçemez). Redeem log'u `pos_coupon_redemptions` tablosuna yazılır.
Mevcut indirim akışı bozulmaz — bu router order'a YAZMAZ, sadece
"discount_value" döner; frontend close_order'a manuel ekler.
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

from ._idem import ensure_compound_unique, idempotent_insert

router = APIRouter(prefix="/api/pos/ext/coupons", tags=["pos-ext-coupons"])


async def _ensure_coupon_indexes() -> None:
    await ensure_compound_unique(
        db.pos_coupons,
        keys=[("tenant_id", 1), ("code", 1)],
        name="pos_coupons_tenant_code_unique",
    )


class CouponCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(min_length=3, max_length=40)
    discount_type: str = Field(default="percent", pattern="^(percent|amount)$")
    discount_value: float = Field(gt=0)
    min_amount: float = Field(default=0, ge=0)
    valid_from: str | None = None  # ISO
    valid_to: str | None = None    # ISO
    max_uses: int = Field(default=1, ge=1)
    active: bool = True
    note: str | None = None


class ValidateRequest(BaseModel):
    code: str
    amount: float = Field(ge=0)


class RedeemRequest(BaseModel):
    code: str
    amount: float = Field(ge=0)
    order_id: str | None = None
    idempotency_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid iso timestamp '{s}'")


def _compute_discount(coupon: dict, amount: float) -> float:
    if coupon["discount_type"] == "percent":
        pct = max(0.0, min(100.0, float(coupon["discount_value"])))
        return round(amount * pct / 100.0, 2)
    return min(amount, round(float(coupon["discount_value"]), 2))


def _check_validity(coupon: dict, amount: float, now: datetime) -> tuple[bool, str | None]:
    if not coupon.get("active", True):
        return False, "Coupon inactive"
    if amount < float(coupon.get("min_amount", 0) or 0):
        return False, f"Order below minimum amount ({coupon.get('min_amount')})"
    vf = coupon.get("valid_from")
    vt = coupon.get("valid_to")
    if vf:
        d = vf if isinstance(vf, datetime) else _parse_iso(vf)
        if d and now < d:
            return False, "Coupon not yet valid"
    if vt:
        d = vt if isinstance(vt, datetime) else _parse_iso(vt)
        if d and now > d:
            return False, "Coupon expired"
    if int(coupon.get("used_count", 0)) >= int(coupon.get("max_uses", 1)):
        return False, "Coupon usage limit reached"
    return True, None


@router.post("")
async def create_coupon(body: CouponCreate, current_user: User = Depends(get_current_user)):
    await _ensure_coupon_indexes()
    code = body.code.strip().upper()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "code": code,
        "discount_type": body.discount_type,
        "discount_value": float(body.discount_value),
        "min_amount": float(body.min_amount),
        "valid_from": _parse_iso(body.valid_from),
        "valid_to": _parse_iso(body.valid_to),
        "max_uses": int(body.max_uses),
        "used_count": 0,
        "active": bool(body.active),
        "note": body.note,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    try:
        await db.pos_coupons.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Coupon code already exists")
    doc.pop("_id", None)
    return {"success": True, "coupon": doc}


@router.get("")
async def list_coupons(
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if active_only:
        q["active"] = True
    rows = await db.pos_coupons.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"coupons": rows, "count": len(rows)}


@router.delete("/{coupon_id}")
async def delete_coupon(coupon_id: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_coupons.delete_one(
        {"id": coupon_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return {"success": True, "deleted": coupon_id}


@router.post("/validate")
async def validate(body: ValidateRequest, current_user: User = Depends(get_current_user)):
    code = body.code.strip().upper()
    coupon = await db.pos_coupons.find_one(
        {"tenant_id": current_user.tenant_id, "code": code}, {"_id": 0}
    )
    if not coupon:
        return {"valid": False, "reason": "Unknown code"}
    ok, reason = _check_validity(coupon, body.amount, _now())
    if not ok:
        return {"valid": False, "reason": reason, "coupon": {"code": code}}
    discount = _compute_discount(coupon, body.amount)
    return {
        "valid": True,
        "code": code,
        "discount_type": coupon["discount_type"],
        "discount_value": coupon["discount_value"],
        "discount_amount": discount,
        "remaining_uses": int(coupon["max_uses"]) - int(coupon.get("used_count", 0)),
    }


@router.post("/redeem")
async def redeem(body: RedeemRequest, current_user: User = Depends(get_current_user)):
    code = body.code.strip().upper()

    # Idempotency replay — atomic DB-level guard.
    if body.idempotency_key:
        prior = await db.pos_coupon_redemptions.find_one(
            {"tenant_id": current_user.tenant_id, "idempotency_key": body.idempotency_key},
            {"_id": 0},
        )
        if prior:
            return {"success": True, "redemption": prior, "idempotent": True}

    coupon = await db.pos_coupons.find_one(
        {"tenant_id": current_user.tenant_id, "code": code}, {"_id": 0}
    )
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    ok, reason = _check_validity(coupon, body.amount, _now())
    if not ok:
        raise HTTPException(status_code=400, detail=reason or "Coupon invalid")

    # Atomic increment under conditions — protects against race-condition double-spend.
    updated = await db.pos_coupons.find_one_and_update(
        {
            "tenant_id": current_user.tenant_id,
            "code": code,
            "active": True,
            "$expr": {"$lt": ["$used_count", "$max_uses"]},
        },
        {"$inc": {"used_count": 1}, "$set": {"last_redeemed_at": _now()}},
        projection={"_id": 0},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Coupon usage limit reached (race)")

    discount = _compute_discount(coupon, body.amount)
    redemption = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "coupon_id": coupon["id"],
        "code": code,
        "order_id": body.order_id,
        "amount": float(body.amount),
        "discount_amount": discount,
        "idempotency_key": body.idempotency_key,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.pos_coupon_redemptions, current_user.tenant_id, body.idempotency_key, redemption
    )
    if replayed:
        # The counter was already incremented for the same key on a concurrent
        # call — roll back this redundant increment to keep used_count accurate.
        await db.pos_coupons.update_one(
            {"tenant_id": current_user.tenant_id, "code": code, "used_count": {"$gt": 0}},
            {"$inc": {"used_count": -1}},
        )
    return {"success": True, "redemption": saved, "discount_amount": discount, "idempotent": replayed}


@router.get("/redemptions")
async def list_redemptions(
    code: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if code:
        q["code"] = code.strip().upper()
    if order_id:
        q["order_id"] = order_id
    rows = await db.pos_coupon_redemptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"redemptions": rows, "count": len(rows)}
