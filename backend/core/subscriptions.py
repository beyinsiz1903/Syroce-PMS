"""Marketplace subscription helpers.

A tenant has access to a module/integration when EITHER:
1. The module key exists in the tenant's plan-included modules, OR
2. There is an active (status=active, end_date > now) entry in
   the `tenant_subscriptions` collection.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _db():
    from server import db
    return db


async def get_active_subscriptions(tenant_id: str) -> list[dict[str, Any]]:
    db = _db()
    now = datetime.now(UTC)
    cur = db.tenant_subscriptions.find(
        {
            "tenant_id": tenant_id,
            "status": "active",
            "$or": [
                {"end_date": None},
                {"end_date": {"$gt": now.isoformat()}},
            ],
        },
        {"_id": 0},
    )
    return [doc async for doc in cur]


async def tenant_has_module(tenant_id: str, module_key: str) -> bool:
    """Return True if tenant has access to a module either via plan or
    an active marketplace subscription."""
    db = _db()
    tenant = await db.tenants.find_one(
        {"id": tenant_id},
        {"_id": 0, "modules": 1},
    )
    if tenant:
        modules = tenant.get("modules") or {}
        if isinstance(modules, dict) and modules.get(module_key):
            return True
        if isinstance(modules, list) and module_key in modules:
            return True

    now = datetime.now(UTC)
    sub = await db.tenant_subscriptions.find_one({
        "tenant_id": tenant_id,
        "product_key": module_key,
        "status": "active",
        "$or": [
            {"end_date": None},
            {"end_date": {"$gt": now.isoformat()}},
        ],
    })
    return sub is not None


async def ensure_indexes() -> None:
    db = _db()
    try:
        await db.marketplace_products.create_index(
            "key", unique=True, name="uniq_product_key"
        )
        await db.tenant_subscriptions.create_index(
            [("tenant_id", 1), ("product_key", 1)],
            name="idx_sub_tenant_product",
        )
        await db.tenant_subscriptions.create_index(
            "status", name="idx_sub_status"
        )
        await db.marketplace_orders.create_index(
            "order_id", unique=True, name="uniq_order_id"
        )
        # One subscription record per paid order — protects against
        # double-grant on callback replay.
        await db.tenant_subscriptions.create_index(
            "order_id",
            unique=True,
            sparse=True,
            name="uniq_sub_order_id",
        )
        await db.marketplace_orders.create_index(
            "tenant_id", name="idx_order_tenant"
        )
    except Exception:
        pass
