"""POS Loyalty — POS akışı için puan kazan/harca motoru.

Mevcut `loyalty_*` koleksiyonlarına dokunmaz; POS'a özel hesap defteri
(`loyalty_pos_accounts` + `loyalty_pos_ledger`) tutar. Race condition guard'ı:
redeem `find_one_and_update` ile balance >= points koşulu altında atomik
azaltır. Earn idempotency_key ile çift-yazımdan korunur.
"""
from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import idempotent_insert

router = APIRouter(prefix="/api/pos/ext/loyalty", tags=["pos-ext-loyalty"])


class LoyaltySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    earn_points_per_unit: float = Field(default=1.0, ge=0)  # 1 TL → N puan
    redeem_value_per_point: float = Field(default=0.1, ge=0)  # 1 puan → Z TL
    min_redeem_points: int = Field(default=10, ge=1)
    active: bool = True


class EarnRequest(BaseModel):
    guest_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    order_id: str | None = None
    idempotency_key: str | None = None


class RedeemRequest(BaseModel):
    guest_id: str = Field(min_length=1)
    points: int = Field(gt=0)
    order_id: str | None = None
    idempotency_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def _get_settings(tenant_id: str) -> dict:
    doc = await db.loyalty_pos_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return {
            "tenant_id": tenant_id,
            "earn_points_per_unit": 1.0,
            "redeem_value_per_point": 0.1,
            "min_redeem_points": 10,
            "active": True,
        }
    return doc


@router.put("/settings")
async def update_settings(body: LoyaltySettings, current_user: User = Depends(get_current_user)):
    doc = body.model_dump()
    doc.update({"tenant_id": current_user.tenant_id, "updated_at": _now(), "updated_by": current_user.id})
    await db.loyalty_pos_settings.update_one(
        {"tenant_id": current_user.tenant_id}, {"$set": doc}, upsert=True
    )
    doc.pop("_id", None)
    return {"success": True, "settings": doc}


@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_user)):
    return await _get_settings(current_user.tenant_id)


@router.get("/balance")
async def balance(
    guest_id: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    acc = await db.loyalty_pos_accounts.find_one(
        {"tenant_id": current_user.tenant_id, "guest_id": guest_id}, {"_id": 0}
    )
    return {
        "guest_id": guest_id,
        "balance": int(acc["balance"]) if acc else 0,
        "lifetime_earned": int(acc.get("lifetime_earned", 0)) if acc else 0,
        "lifetime_redeemed": int(acc.get("lifetime_redeemed", 0)) if acc else 0,
    }


@router.post("/earn")
async def earn(body: EarnRequest, current_user: User = Depends(get_current_user)):
    settings = await _get_settings(current_user.tenant_id)
    if not settings.get("active", True):
        raise HTTPException(status_code=400, detail="Loyalty programı aktif değil")
    rate = float(settings.get("earn_points_per_unit") or 0)
    points = int(math.floor(body.amount * rate))
    if points <= 0:
        return {"success": True, "entry": None, "points_earned": 0, "note": "Below earn threshold"}

    entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_id": body.guest_id,
        "kind": "earn",
        "points": points,
        "amount": float(body.amount),
        "order_id": body.order_id,
        "idempotency_key": body.idempotency_key,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.loyalty_pos_ledger, current_user.tenant_id, body.idempotency_key, entry
    )
    if not replayed:
        # Only increment the account balance when the ledger row is freshly created.
        await db.loyalty_pos_accounts.update_one(
            {"tenant_id": current_user.tenant_id, "guest_id": body.guest_id},
            {
                "$inc": {"balance": points, "lifetime_earned": points},
                "$setOnInsert": {"created_at": _now()},
                "$set": {"updated_at": _now()},
            },
            upsert=True,
        )
    return {"success": True, "entry": saved, "points_earned": points, "idempotent": replayed}


@router.post("/redeem")
async def redeem(body: RedeemRequest, current_user: User = Depends(get_current_user)):
    if body.idempotency_key:
        prior = await db.loyalty_pos_ledger.find_one(
            {"tenant_id": current_user.tenant_id, "idempotency_key": body.idempotency_key, "kind": "redeem"},
            {"_id": 0},
        )
        if prior:
            new_bal_doc = await db.loyalty_pos_accounts.find_one(
                {"tenant_id": current_user.tenant_id, "guest_id": body.guest_id},
                {"_id": 0, "balance": 1},
            )
            return {
                "success": True, "entry": prior, "idempotent": True,
                "points_redeemed": -int(prior.get("points", 0)),
                "discount_value": float(prior.get("discount_value", 0)),
                "new_balance": int((new_bal_doc or {}).get("balance", 0)),
            }

    settings = await _get_settings(current_user.tenant_id)
    if not settings.get("active", True):
        raise HTTPException(status_code=400, detail="Loyalty programı aktif değil")
    if body.points < int(settings.get("min_redeem_points", 1)):
        raise HTTPException(status_code=400, detail=f"Min {settings['min_redeem_points']} puan harcanabilir")

    # Atomic balance check + decrement.
    updated = await db.loyalty_pos_accounts.find_one_and_update(
        {
            "tenant_id": current_user.tenant_id,
            "guest_id": body.guest_id,
            "balance": {"$gte": body.points},
        },
        {
            "$inc": {"balance": -body.points, "lifetime_redeemed": body.points},
            "$set": {"updated_at": _now()},
        },
        projection={"_id": 0},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Yetersiz puan bakiyesi")

    discount_value = round(body.points * float(settings.get("redeem_value_per_point") or 0), 2)
    entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_id": body.guest_id,
        "kind": "redeem",
        "points": -int(body.points),
        "discount_value": discount_value,
        "order_id": body.order_id,
        "idempotency_key": body.idempotency_key,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.loyalty_pos_ledger, current_user.tenant_id, body.idempotency_key, entry
    )
    if replayed:
        # The atomic decrement above already happened on this duplicate request —
        # roll it back so the account stays consistent with the single ledger row.
        await db.loyalty_pos_accounts.update_one(
            {"tenant_id": current_user.tenant_id, "guest_id": body.guest_id},
            {
                "$inc": {"balance": int(body.points), "lifetime_redeemed": -int(body.points)},
                "$set": {"updated_at": _now()},
            },
        )
        bal_doc = await db.loyalty_pos_accounts.find_one(
            {"tenant_id": current_user.tenant_id, "guest_id": body.guest_id},
            {"_id": 0, "balance": 1},
        )
        new_bal = int((bal_doc or {}).get("balance", 0))
    else:
        new_bal = int(updated["balance"])
    return {
        "success": True,
        "entry": saved,
        "points_redeemed": int(body.points),
        "discount_value": discount_value,
        "new_balance": new_bal,
        "idempotent": replayed,
    }


@router.get("/ledger")
async def ledger(
    guest_id: str = Query(..., min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    rows = await db.loyalty_pos_ledger.find(
        {"tenant_id": current_user.tenant_id, "guest_id": guest_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"entries": rows, "count": len(rows)}


@router.delete("/account")
async def purge_account(
    guest_id: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    """Remove account + ledger rows for a guest. Used by stress cleanup; staff-only via auth."""
    acc = await db.loyalty_pos_accounts.delete_one(
        {"tenant_id": current_user.tenant_id, "guest_id": guest_id}
    )
    led = await db.loyalty_pos_ledger.delete_many(
        {"tenant_id": current_user.tenant_id, "guest_id": guest_id}
    )
    if acc.deleted_count == 0 and led.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No loyalty data for guest")
    return {"success": True, "account_deleted": acc.deleted_count, "ledger_deleted": led.deleted_count}
