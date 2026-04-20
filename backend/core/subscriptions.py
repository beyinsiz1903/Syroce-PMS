"""Marketplace subscription helpers.

A tenant has access to a module/integration when EITHER:
1. The module key exists in the tenant's plan-included modules, OR
2. There is an active (status=active, end_date > now) entry in
   the `tenant_subscriptions` collection.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _db():
    """Raw, non-tenant-scoped DB. tenant_subscriptions stores tenant_id
    explicitly and we always filter on it manually."""
    from core.database import _raw_db
    return _raw_db


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


# Canonical entitlement key → list of accepted marketplace product keys.
# Allows route-level checks (e.g. "mailing") to be satisfied by ANY of the
# matching marketplace SKUs (e.g. "mailing_starter" credit pack).
MODULE_ALIASES: dict[str, list[str]] = {
    "mailing": ["mailing", "mailing_starter", "mailing_pro"],
    "quick_id": ["quick_id", "quick_id_integration"],
    "af_sadakat": ["af_sadakat", "af_sadakat_loyalty"],
}


async def tenant_has_module(tenant_id: str, module_key: str) -> bool:
    """Return True if tenant has access to a module either via plan or
    an active marketplace subscription (any aliased SKU counts)."""
    db = _db()
    accepted_keys = MODULE_ALIASES.get(module_key, [module_key])

    tenant = await db.tenants.find_one(
        {"id": tenant_id},
        {"_id": 0, "modules": 1},
    )
    if tenant:
        modules = tenant.get("modules") or {}
        if isinstance(modules, dict):
            for k in accepted_keys:
                if modules.get(k):
                    return True
        elif isinstance(modules, list):
            if any(k in modules for k in accepted_keys):
                return True

    now = datetime.now(UTC)
    sub = await db.tenant_subscriptions.find_one({
        "tenant_id": tenant_id,
        "product_key": {"$in": accepted_keys},
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
        # Enforce single ACTIVE subscription per (tenant, product). Lookup
        # for trial idempotency and prevents concurrent double-grants.
        # Partial filter restricts uniqueness to active rows only — historic
        # cancelled/expired subs may coexist.
        await db.tenant_subscriptions.create_index(
            [("tenant_id", 1), ("product_key", 1)],
            unique=True,
            partialFilterExpression={"status": "active"},
            name="uniq_active_sub_per_tenant_product",
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
        # Atomic activation marker: any callback (paid OR trial) inserts
        # one row per order_id. Unique index makes concurrent/replayed
        # callbacks fail-fast on the second insert, preventing duplicate
        # entitlement grants in the "extend existing sub" branch where
        # tenant_subscriptions.order_id is not always written.
        await db.tenant_subscription_activations.create_index(
            "order_id", unique=True, name="uniq_activation_order_id"
        )
        # Outbound folio-charge idempotency: enforce uniqueness on the
        # caller-supplied external_ref scoped per (tenant, source).
        # Sparse so charges without external_ref are not constrained.
        await db.folio_charges.create_index(
            [("tenant_id", 1), ("source", 1), ("external_ref", 1)],
            unique=True,
            partialFilterExpression={"external_ref": {"$type": "string"}},
            name="uniq_folio_charge_external_ref",
        )
    except Exception:
        logger.warning("subscriptions: failed to ensure folio_charge external_ref index", exc_info=True)
