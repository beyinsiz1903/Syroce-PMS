"""Local Nilvera credit-pool accounting for Syroce multi-tenant e-document usage.

This module never calls Nilvera. It tracks centrally purchased credit lots, tenant
allocations, local consumption and expiry in the Syroce system database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.tenant_db import get_system_db

MIN_PURCHASE_CREDITS = 100_000
ALLOCATION_STEP = 100
DEFAULT_LOW_BALANCE_THRESHOLD = 10_000
POOL_SETTINGS_ID = "nilvera-credit-pool"


class NilveraCreditPoolError(RuntimeError):
    """Fail-closed local credit-pool error."""


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_step(amount: int, *, minimum: int) -> None:
    if amount < minimum or amount % ALLOCATION_STEP != 0:
        raise NilveraCreditPoolError(f"amount must be >= {minimum} and divisible by {ALLOCATION_STEP}")


async def record_purchase(*, credits: int, purchased_at: datetime | None = None, reference: str | None = None, actor_id: str | None = None) -> dict[str, Any]:
    """Record a real-world Nilvera credit purchase in the local ledger only."""
    _validate_step(credits, minimum=MIN_PURCHASE_CREDITS)
    purchased_at = purchased_at or _now()
    if purchased_at.tzinfo is None:
        raise NilveraCreditPoolError("purchased_at must be timezone-aware")

    db = get_system_db()
    lot_id = str(uuid.uuid4())
    expires_at = purchased_at + timedelta(days=365)
    doc = {
        "id": lot_id,
        "credits": credits,
        "unallocated": credits,
        "purchased_at": purchased_at,
        "expires_at": expires_at,
        "reference": reference,
        "created_at": _now(),
    }
    await db.nilvera_credit_lots.insert_one(doc)
    await _audit(db, event_type="PURCHASE", amount=credits, actor_id=actor_id, source_lot_id=lot_id, reference=reference)
    return _clean(doc)


async def allocate_to_tenant(*, tenant_id: str, credits: int, actor_id: str | None = None, reference: str | None = None) -> dict[str, Any]:
    """Reserve credits from the central pool for one tenant, in 100-credit steps."""
    if not tenant_id or len(tenant_id) > 128:
        raise NilveraCreditPoolError("invalid tenant_id")
    _validate_step(credits, minimum=ALLOCATION_STEP)

    db = get_system_db()
    now = _now()
    source = await db.nilvera_credit_lots.find_one(
        {"expires_at": {"$gt": now}, "unallocated": {"$gte": credits}},
        sort=[("expires_at", 1), ("purchased_at", 1)],
    )
    if not source:
        raise NilveraCreditPoolError("insufficient unallocated active credits")

    result = await db.nilvera_credit_lots.update_one(
        {"_id": source["_id"], "expires_at": {"$gt": now}, "unallocated": {"$gte": credits}},
        {"$inc": {"unallocated": -credits}},
    )
    if result.modified_count != 1:
        raise NilveraCreditPoolError("credit allocation conflict; retry from fresh state")

    allocation_id = str(uuid.uuid4())
    allocation = {
        "id": allocation_id,
        "tenant_id": tenant_id,
        "source_lot_id": source["id"],
        "allocated": credits,
        "remaining": credits,
        "allocated_at": now,
        "expires_at": source["expires_at"],
        "reference": reference,
    }
    try:
        await db.nilvera_tenant_credit_lots.insert_one(allocation)
    except Exception:
        await db.nilvera_credit_lots.update_one({"_id": source["_id"]}, {"$inc": {"unallocated": credits}})
        raise

    await _audit(db, event_type="ALLOCATE", amount=credits, actor_id=actor_id, tenant_id=tenant_id, source_lot_id=source["id"], tenant_lot_id=allocation_id, reference=reference)
    return _clean(allocation)


async def consume_tenant_credits(*, tenant_id: str, credits: int = 1, actor_id: str | None = None, reference: str | None = None) -> dict[str, Any]:
    """Consume active tenant credits locally; intended to be called after proven e-document success."""
    if not tenant_id or len(tenant_id) > 128:
        raise NilveraCreditPoolError("invalid tenant_id")
    if credits < 1:
        raise NilveraCreditPoolError("credits must be positive")

    db = get_system_db()
    now = _now()
    lot = await db.nilvera_tenant_credit_lots.find_one(
        {"tenant_id": tenant_id, "expires_at": {"$gt": now}, "remaining": {"$gte": credits}},
        sort=[("expires_at", 1), ("allocated_at", 1)],
    )
    if not lot:
        raise NilveraCreditPoolError("insufficient active tenant credits")

    result = await db.nilvera_tenant_credit_lots.update_one(
        {"_id": lot["_id"], "tenant_id": tenant_id, "expires_at": {"$gt": now}, "remaining": {"$gte": credits}},
        {"$inc": {"remaining": -credits}},
    )
    if result.modified_count != 1:
        raise NilveraCreditPoolError("credit consumption conflict; retry from fresh state")

    await _audit(db, event_type="CONSUME", amount=credits, actor_id=actor_id, tenant_id=tenant_id, source_lot_id=lot["source_lot_id"], tenant_lot_id=lot["id"], reference=reference)
    return await get_tenant_balance(tenant_id)


async def get_tenant_balance(tenant_id: str) -> dict[str, Any]:
    db = get_system_db()
    now = _now()
    active = await db.nilvera_tenant_credit_lots.find({"tenant_id": tenant_id, "expires_at": {"$gt": now}}).to_list(length=1000)
    expired = await db.nilvera_tenant_credit_lots.find({"tenant_id": tenant_id, "expires_at": {"$lte": now}}).to_list(length=1000)
    allocated = sum(int(x.get("allocated", 0)) for x in active)
    remaining = sum(int(x.get("remaining", 0)) for x in active)
    consumed = allocated - remaining
    expired_unused = sum(int(x.get("remaining", 0)) for x in expired)
    next_expiry = min((x["expires_at"] for x in active if x.get("remaining", 0) > 0), default=None)
    return {
        "tenant_id": tenant_id,
        "allocated_active": allocated,
        "consumed_active": consumed,
        "remaining_active": remaining,
        "expired_unused": expired_unused,
        "next_expiry_at": next_expiry,
        "low_balance": remaining <= ALLOCATION_STEP,
    }


async def get_pool_summary() -> dict[str, Any]:
    db = get_system_db()
    now = _now()
    active_lots = await db.nilvera_credit_lots.find({"expires_at": {"$gt": now}}).to_list(length=1000)
    expired_lots = await db.nilvera_credit_lots.find({"expires_at": {"$lte": now}}).to_list(length=1000)
    settings = await db.nilvera_credit_pool_settings.find_one({"_id": POOL_SETTINGS_ID}) or {}
    threshold = int(settings.get("low_balance_threshold", DEFAULT_LOW_BALANCE_THRESHOLD))
    purchased_active = sum(int(x.get("credits", 0)) for x in active_lots)
    unallocated_active = sum(int(x.get("unallocated", 0)) for x in active_lots)
    expired_unallocated = sum(int(x.get("unallocated", 0)) for x in expired_lots)
    tenant_active = await db.nilvera_tenant_credit_lots.find({"expires_at": {"$gt": now}}).to_list(length=10000)
    tenant_remaining = sum(int(x.get("remaining", 0)) for x in tenant_active)
    consumed_active = sum(int(x.get("allocated", 0)) - int(x.get("remaining", 0)) for x in tenant_active)
    next_expiry = min((x["expires_at"] for x in active_lots), default=None)
    usable_remaining = unallocated_active + tenant_remaining
    return {
        "purchased_active": purchased_active,
        "unallocated_active": unallocated_active,
        "tenant_remaining_active": tenant_remaining,
        "consumed_active": consumed_active,
        "usable_remaining": usable_remaining,
        "expired_unallocated": expired_unallocated,
        "low_balance_threshold": threshold,
        "low_balance": usable_remaining <= threshold,
        "next_expiry_at": next_expiry,
    }


async def set_low_balance_threshold(threshold: int, *, actor_id: str | None = None) -> dict[str, Any]:
    if threshold < 0:
        raise NilveraCreditPoolError("threshold cannot be negative")
    db = get_system_db()
    await db.nilvera_credit_pool_settings.update_one(
        {"_id": POOL_SETTINGS_ID},
        {"$set": {"low_balance_threshold": threshold, "updated_at": _now(), "updated_by": actor_id}},
        upsert=True,
    )
    return await get_pool_summary()


async def list_events(*, tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    db = get_system_db()
    query: dict[str, Any] = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    docs = await db.nilvera_credit_events.find(query).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(length=max(1, min(limit, 500)))
    return [_clean(x) for x in docs]


async def _audit(db, *, event_type: str, amount: int, actor_id: str | None = None, tenant_id: str | None = None, source_lot_id: str | None = None, tenant_lot_id: str | None = None, reference: str | None = None) -> None:
    await db.nilvera_credit_events.insert_one(
        {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "amount": amount,
            "tenant_id": tenant_id,
            "source_lot_id": source_lot_id,
            "tenant_lot_id": tenant_lot_id,
            "reference": reference,
            "actor_id": actor_id,
            "created_at": _now(),
        }
    )


def _clean(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("_id", None)
    return out
