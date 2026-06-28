"""Loyalty puan kazanım servisi (cross-domain).

Konaklama (checkout) sonrası loyalty üyesine puan vermek için kullanılan
servis. PMS domain'i (frontdesk checkout) ve Guest domain'i (loyalty
router) tarafından paylaşıldığı için domain dışında — shared_kernel'de
yaşar. Bu sayede `domains/pms` modülleri `domains/guest` modüllerinden
import yapmadan loyalty entegrasyonunu kullanabilir (cross-domain
coupling kuralı ihlali olmaz).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.tenant_db import get_system_db

# Konaklama → puan dönüşüm oranı. MVP için sabit; ileride tier veya
# tenant config'inden okunabilir. 10 TL harcama = 1 baz puan; tier
# earn_multiplier ile çarpılır.
LOYALTY_POINTS_PER_CURRENCY_UNIT = 0.1

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
        await db.loyalty_members.create_index([("tenant_id", 1), ("guest_id", 1)], unique=True, name="loyalty_member_guest")
        await db.loyalty_rewards.create_index([("tenant_id", 1), ("active", 1)])
        await db.loyalty_transactions.create_index([("tenant_id", 1), ("guest_id", 1), ("created_at", -1)])
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


async def _resolve_tier(db, tenant_id: str, points: int) -> dict | None:
    cur = db.loyalty_tiers.find({"tenant_id": tenant_id, "min_points": {"$lte": points}}).sort("min_points", -1)
    async for t in cur:
        return t
    return None


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
    member = await db.loyalty_members.find_one({"tenant_id": tenant_id, "guest_id": guest_id})
    if not member:
        return None
    tier = None
    if member.get("tier_id"):
        tier = await db.loyalty_tiers.find_one({"tenant_id": tenant_id, "id": member["tier_id"]})
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
        await db.loyalty_members.update_one({"tenant_id": tenant_id, "guest_id": guest_id}, {"$set": update})
    except Exception:
        await db.loyalty_transactions.delete_one({"id": tx_doc["id"]})
        raise
    return {
        "awarded": awarded,
        "balance": new_balance,
        "tier": update.get("tier_name"),
        "booking_id": booking_id,
    }
