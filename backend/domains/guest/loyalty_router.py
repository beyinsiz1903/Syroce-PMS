"""Loyalty Programı — Tier yönetimi, üye puanları, ödül kataloğu, kazanma/harcama."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

router = APIRouter(prefix="/api/loyalty", tags=["Loyalty Program"])


class LoyaltyTier(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    min_points: int = 0
    earn_multiplier: float = 1.0
    benefits: list[str] = Field(default_factory=list)
    color: str = "#888"


class LoyaltyMember(BaseModel):
    id: str | None = None
    guest_id: str
    tier_id: str | None = None
    tier_name: str | None = None
    points_balance: int = 0
    points_lifetime: int = 0
    enrolled_at: str | None = None


class LoyaltyReward(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    description: str | None = None
    points_cost: int = Field(..., gt=0)
    type: str = Field("discount", pattern="^(discount|free_night|upgrade|amenity|fnb|spa)$")
    value: float | None = None
    active: bool = True
    stock: int | None = None


class EarnBody(BaseModel):
    guest_id: str
    points: int = Field(..., gt=0)
    source: str = "stay"
    reference_id: str | None = None


class RedeemBody(BaseModel):
    guest_id: str
    reward_id: str


# Index oluşturma idempotent ama her checkout'ta 6 create_index çağrısı
# ekstra RTT yaratır. Bu flag ile process başına yalnızca bir kez koşar.
_INDEXES_INITIALIZED = False


async def _ensure_indexes() -> None:
    global _INDEXES_INITIALIZED
    if _INDEXES_INITIALIZED:
        return
    db = get_system_db()
    try:
        await db.loyalty_tiers.create_index([("tenant_id", 1), ("min_points", 1)])
        await db.loyalty_members.create_index(
            [("tenant_id", 1), ("guest_id", 1)], unique=True, name="loyalty_member_guest"
        )
        await db.loyalty_rewards.create_index([("tenant_id", 1), ("active", 1)])
        await db.loyalty_transactions.create_index(
            [("tenant_id", 1), ("guest_id", 1), ("created_at", -1)]
        )
        # Stay-based award için idempotency: aynı booking için iki kez puan
        # verilmesini engelle. partialFilterExpression ile yalnızca
        # source="stay" ve reference_id dolu kayıtlara unique uygulanır.
        await db.loyalty_transactions.create_index(
            [("tenant_id", 1), ("source", 1), ("reference_id", 1)],
            unique=True,
            name="loyalty_tx_stay_unique",
            partialFilterExpression={
                "source": "stay",
                "reference_id": {"$type": "string"},
            },
        )
        _INDEXES_INITIALIZED = True
    except Exception:
        # Index oluşturulamazsa flag set edilmez → bir sonraki çağrıda yeniden denenir.
        pass


# Konaklama → puan dönüşüm oranı. MVP için sabit; ileride tier veya
# tenant config'inden okunabilir. 10 TL harcama = 1 baz puan; tier
# earn_multiplier ile çarpılır.
LOYALTY_POINTS_PER_CURRENCY_UNIT = 0.1


async def award_points_for_stay(
    tenant_id: str,
    guest_id: str | None,
    booking_id: str,
    amount: float,
) -> dict | None:
    """Konaklama (checkout) sonrası loyalty üyesine otomatik puan verir.
    Idempotent: aynı booking için ikinci çağrıda DuplicateKeyError yakalanır
    ve sessizce None döner. Misafir loyalty üyesi değilse veya puanlanacak
    tutar yoksa None döner — caller fail etmemeli.
    """
    if not guest_id or not booking_id or not amount or amount <= 0:
        return None
    await _ensure_indexes()
    db = get_system_db()
    member = await db.loyalty_members.find_one(
        {"tenant_id": tenant_id, "guest_id": guest_id}
    )
    if not member:
        return None
    tier = None
    if member.get("tier_id"):
        tier = await db.loyalty_tiers.find_one(
            {"tenant_id": tenant_id, "id": member["tier_id"]}
        )
    multiplier = float((tier or {}).get("earn_multiplier", 1.0))
    base = round(amount * LOYALTY_POINTS_PER_CURRENCY_UNIT)
    awarded = int(round(base * multiplier))
    if awarded <= 0:
        return None
    new_balance = int(member.get("points_balance", 0)) + awarded
    new_lifetime = int(member.get("points_lifetime", 0)) + awarded
    new_tier = await _resolve_tier(db, tenant_id, new_lifetime)
    update = {"points_balance": new_balance, "points_lifetime": new_lifetime}
    if new_tier:
        update["tier_id"] = new_tier["id"]
        update["tier_name"] = new_tier["name"]
    tx_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "type": "earn",
        "source": "stay",
        "reference_id": booking_id,
        "points": awarded,
        "balance_after": new_balance,
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        await db.loyalty_transactions.insert_one(tx_doc)
    except Exception as exc:  # DuplicateKeyError → bu booking zaten ödüllendirilmiş
        if "duplicate" in str(exc).lower() or "E11000" in str(exc):
            return None
        raise
    # Insert başarılı → member balance güncelle. Update fail olursa tx'i
    # geri al (compensating delete) — aksi halde ledger ile balance
    # arasında tutarsızlık kalır ve idempotency unique kuralı yüzünden
    # retry mümkün olmaz.
    try:
        await db.loyalty_members.update_one(
            {"tenant_id": tenant_id, "guest_id": guest_id}, {"$set": update}
        )
    except Exception:
        await db.loyalty_transactions.delete_one({"id": tx_doc["id"]})
        raise
    return {
        "awarded": awarded,
        "balance": new_balance,
        "tier": update.get("tier_name"),
        "booking_id": booking_id,
    }


# ── Tiers ─────────────────────────────────────────────
@router.get("/tiers", response_model=list[LoyaltyTier])
async def list_tiers(user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    docs = await db.loyalty_tiers.find({"tenant_id": user.tenant_id}).sort("min_points", 1).to_list(50)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/tiers", response_model=LoyaltyTier, status_code=201)
async def create_tier(body: LoyaltyTier, user: User = Depends(get_current_user)):
    db = get_system_db()
    doc = body.model_dump()
    doc["id"] = doc.get("id") or str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.loyalty_tiers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/tiers/{tier_id}", status_code=204)
async def delete_tier(tier_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    res = await db.loyalty_tiers.delete_one({"id": tier_id, "tenant_id": user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Tier bulunamadı")
    return None


# ── Members ───────────────────────────────────────────
async def _resolve_tier(db, tenant_id: str, points: int) -> dict | None:
    cur = db.loyalty_tiers.find({"tenant_id": tenant_id, "min_points": {"$lte": points}}).sort(
        "min_points", -1
    )
    async for t in cur:
        return t
    return None


@router.get("/members", response_model=list[LoyaltyMember])
async def list_members(
    q: str | None = None, limit: int = 100, user: User = Depends(get_current_user)
):
    await _ensure_indexes()
    db = get_system_db()
    query: dict[str, Any] = {"tenant_id": user.tenant_id}
    if q:
        query["guest_id"] = {"$regex": q, "$options": "i"}
    docs = await db.loyalty_members.find(query).sort("points_balance", -1).to_list(limit)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/members/enroll", response_model=LoyaltyMember, status_code=201)
async def enroll_member(body: LoyaltyMember, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    existing = await db.loyalty_members.find_one(
        {"tenant_id": user.tenant_id, "guest_id": body.guest_id}
    )
    if existing:
        existing.pop("_id", None)
        return existing
    tier = await _resolve_tier(db, user.tenant_id, body.points_balance)
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["enrolled_at"] = datetime.now(UTC).isoformat()
    if tier:
        doc["tier_id"] = tier["id"]
        doc["tier_name"] = tier["name"]
    await db.loyalty_members.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/earn")
async def earn_points(body: EarnBody, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    member = await db.loyalty_members.find_one(
        {"tenant_id": user.tenant_id, "guest_id": body.guest_id}
    )
    if not member:
        raise HTTPException(404, "Üye değil — önce kaydedin")
    tier = await db.loyalty_tiers.find_one(
        {"tenant_id": user.tenant_id, "id": member.get("tier_id")}
    ) if member.get("tier_id") else None
    multiplier = (tier or {}).get("earn_multiplier", 1.0)
    awarded = int(round(body.points * multiplier))
    new_balance = member.get("points_balance", 0) + awarded
    new_lifetime = member.get("points_lifetime", 0) + awarded
    new_tier = await _resolve_tier(db, user.tenant_id, new_lifetime)
    update = {
        "points_balance": new_balance,
        "points_lifetime": new_lifetime,
    }
    if new_tier:
        update["tier_id"] = new_tier["id"]
        update["tier_name"] = new_tier["name"]
    await db.loyalty_members.update_one(
        {"tenant_id": user.tenant_id, "guest_id": body.guest_id}, {"$set": update}
    )
    await db.loyalty_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "guest_id": body.guest_id,
        "type": "earn",
        "points": awarded,
        "balance_after": new_balance,
        "source": body.source,
        "reference_id": body.reference_id,
        "created_at": datetime.now(UTC).isoformat(),
    })
    return {"awarded": awarded, "balance": new_balance, "tier": update.get("tier_name")}


# ── Rewards ───────────────────────────────────────────
@router.get("/rewards", response_model=list[LoyaltyReward])
async def list_rewards(active_only: bool = True, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id}
    if active_only:
        q["active"] = True
    docs = await db.loyalty_rewards.find(q).sort("points_cost", 1).to_list(200)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/rewards", response_model=LoyaltyReward, status_code=201)
async def create_reward(body: LoyaltyReward, user: User = Depends(get_current_user)):
    db = get_system_db()
    doc = body.model_dump()
    doc["id"] = doc.get("id") or str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.loyalty_rewards.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/rewards/{reward_id}", status_code=204)
async def delete_reward(reward_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    await db.loyalty_rewards.update_one(
        {"id": reward_id, "tenant_id": user.tenant_id}, {"$set": {"active": False}}
    )
    return None


@router.post("/redeem")
async def redeem_reward(body: RedeemBody, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    reward = await db.loyalty_rewards.find_one(
        {"id": body.reward_id, "tenant_id": user.tenant_id, "active": True}
    )
    if not reward:
        raise HTTPException(404, "Ödül bulunamadı")
    if reward.get("stock") is not None and reward["stock"] <= 0:
        raise HTTPException(400, "Ödül stoğu tükendi")
    member = await db.loyalty_members.find_one(
        {"tenant_id": user.tenant_id, "guest_id": body.guest_id}
    )
    if not member:
        raise HTTPException(404, "Üye bulunamadı")
    if member.get("points_balance", 0) < reward["points_cost"]:
        raise HTTPException(400, "Yetersiz puan")
    new_balance = member["points_balance"] - reward["points_cost"]
    await db.loyalty_members.update_one(
        {"tenant_id": user.tenant_id, "guest_id": body.guest_id},
        {"$set": {"points_balance": new_balance}},
    )
    if reward.get("stock") is not None:
        await db.loyalty_rewards.update_one(
            {"id": body.reward_id, "tenant_id": user.tenant_id}, {"$inc": {"stock": -1}}
        )
    redemption = {
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "guest_id": body.guest_id,
        "reward_id": body.reward_id,
        "reward_name": reward["name"],
        "points_cost": reward["points_cost"],
        "balance_after": new_balance,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.loyalty_redemptions.insert_one(redemption)
    await db.loyalty_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "guest_id": body.guest_id,
        "type": "redeem",
        "points": -reward["points_cost"],
        "balance_after": new_balance,
        "reference_id": body.reward_id,
        "created_at": datetime.now(UTC).isoformat(),
    })
    redemption.pop("_id", None)
    return redemption


@router.get("/transactions/{guest_id}")
async def member_history(
    guest_id: str, limit: int = 100, user: User = Depends(get_current_user)
):
    db = get_system_db()
    docs = await db.loyalty_transactions.find(
        {"tenant_id": user.tenant_id, "guest_id": guest_id}
    ).sort("created_at", -1).to_list(limit)
    for d in docs:
        d.pop("_id", None)
    return docs
