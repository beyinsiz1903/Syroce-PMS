"""Commercial contracts shared by the marketplace UI, checkout and workers.

This module deliberately contains no HTTP concerns.  A product is sellable only
when its commercial unit, tax, provisioning and readiness contract are explicit.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger(__name__)

PRODUCT_CONTRACTS: dict[str, dict[str, Any]] = {
    "quick_id_integration": {"unit": "property", "included": 1, "setup_minutes": 15, "strategy": "native", "checks": ["quick_id_service", "camera_permission", "kbs_configuration"]},
    "mailing_starter": {"unit": "pack", "included": 5000, "setup_minutes": 10, "strategy": "credit", "checks": ["sender_domain", "mail_provider"]},
    "mailing_pro": {"unit": "pack", "included": 25000, "setup_minutes": 10, "strategy": "credit", "checks": ["sender_domain", "mail_provider"]},
    "af_sadakat": {"unit": "property", "included": 1, "setup_minutes": 30, "strategy": "external", "checks": ["sso", "guest_sync", "channel_credentials"]},
    "hr": {"unit": "employee", "included": 25, "setup_minutes": 45, "strategy": "native", "checks": ["employee_import", "approval_flow", "payroll_settings"]},
    "pos_fnb": {"unit": "outlet", "included": 1, "setup_minutes": 90, "strategy": "native", "checks": ["outlet", "menu", "tax", "folio_mapping", "printer"]},
    "invoices": {"unit": "property", "included": 1, "setup_minutes": 120, "strategy": "native", "checks": ["chart_of_accounts", "opening_balance", "tax_profile", "e_document"]},
    "revenue_management": {"unit": "room", "included": 30, "setup_minutes": 45, "strategy": "native", "checks": ["room_mapping", "rate_history", "forecast_health"]},
    "spa": {"unit": "outlet", "included": 1, "setup_minutes": 45, "strategy": "native", "checks": ["service_catalog", "therapist", "treatment_room", "folio_mapping"]},
    "mice": {"unit": "property", "included": 1, "setup_minutes": 60, "strategy": "native", "checks": ["venues", "packages", "tax", "beo_template"]},
    "maintenance": {"unit": "property", "included": 1, "setup_minutes": 45, "strategy": "native", "checks": ["asset_tree", "sla", "preventive_plan"]},
    "sales_crm": {"unit": "user", "included": 5, "setup_minutes": 30, "strategy": "native", "checks": ["pipeline", "owners", "lead_sources"]},
    "contact_center": {"unit": "user", "included": 3, "setup_minutes": 180, "strategy": "external", "checks": ["whatsapp", "telephony", "webhooks", "agent_routing"]},
    "academy": {"unit": "employee", "included": 25, "setup_minutes": 30, "strategy": "native", "checks": ["departments", "learning_paths", "content"]},
    "booking_engine": {"unit": "property", "included": 1, "setup_minutes": 90, "strategy": "external", "checks": ["domain", "theme", "payment", "policies", "rate_mapping"]},
    "multi_property": {"unit": "property", "included": 1, "setup_minutes": 120, "strategy": "native", "checks": ["property_links", "central_roles", "currency", "consolidation"]},
}

ROUTE_CONTRACTS = {
    "hr": "/hr?tab=suite", "pos_fnb": "/fnb-complete", "invoices": "/app/general-ledger",
    "revenue_management": "/app/revenue-hub", "spa": "/spa-wellness", "mice": "/app/mice",
    "maintenance": "/maintenance/work-orders", "sales_crm": "/crm", "contact_center": "/app/call-center",
    "academy": "/app/academy", "booking_engine": "/app/wbe-settings", "multi_property": "/app/multi-property",
}


def enrich_product(product: dict[str, Any]) -> dict[str, Any]:
    contract = PRODUCT_CONTRACTS.get(product["key"], {"unit": "property", "included": 1, "setup_minutes": 30, "strategy": "native", "checks": []})
    return {
        **product,
        "pricing_model": product.get("pricing_model", contract["unit"]),
        "included_units": product.get("included_units", contract["included"]),
        "unit_price_try": product.get("unit_price_try") if product.get("unit_price_try") is not None else product.get("price_try", 0),
        "tax_rate_pct": product.get("tax_rate_pct", 20),
        "setup_minutes": product.get("setup_minutes", contract["setup_minutes"]),
        "provisioning_strategy": product.get("provisioning_strategy", contract["strategy"]),
        "readiness_checks": product.get("readiness_checks", contract["checks"]),
        "price_version": product.get("price_version", 1),
        "price_valid_from": product.get("price_valid_from", "2026-10-09"),
        "price_source": product.get("price_source", "Syroce commercial review"),
        "price_source_url": product.get("price_source_url"),
        "auto_renew": product.get("auto_renew", product.get("billing_type") == "subscription"),
    }


def calculate_price(product: dict[str, Any], quantity: int = 1) -> dict[str, Any]:
    quantity = max(1, int(quantity or 1))
    unit = Decimal(str(product.get("unit_price_try", product.get("price_try", 0))))
    included = max(1, int(product.get("included_units") or 1))
    billable = max(1, (quantity + included - 1) // included)
    subtotal = (unit * billable).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax_rate = Decimal(str(product.get("tax_rate_pct", 20)))
    tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + tax
    return {"quantity": quantity, "billable_units": billable, "subtotal_try": float(subtotal), "tax_rate_pct": float(tax_rate), "tax_try": float(tax), "total_try": float(total), "currency": "TRY", "price_version": product.get("price_version", 1)}


async def provision_subscription(db, tenant_id: str, product: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    """Create a deterministic provisioning plan and enable native entitlement."""
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    strategy = product.get("provisioning_strategy", "native")
    checks = product.get("readiness_checks") or []
    steps = [{"key": key, "status": "pending", "required": True} for key in checks]
    status = "ready" if not steps else "setup_required"
    if strategy == "native":
        await db.tenants.update_one({"id": tenant_id}, {"$set": {f"modules.{product['key']}": True, "updated_at": now}})
    elif strategy == "external":
        await db.marketplace_setup_tasks.update_one(
            {"tenant_id": tenant_id, "product_key": product["key"], "status": {"$in": ["new", "in_progress"]}},
            {"$setOnInsert": {"id": f"setup-{subscription_id}", "tenant_id": tenant_id, "product_key": product["key"], "status": "new", "priority": "normal", "sla_due_at": (now_dt + timedelta(hours=4)).isoformat(), "created_at": now}},
            upsert=True,
        )
    plan = {"subscription_id": subscription_id, "tenant_id": tenant_id, "product_key": product["key"], "strategy": strategy, "status": status, "steps": steps, "updated_at": now}
    await db.marketplace_provisioning.update_one({"subscription_id": subscription_id}, {"$set": plan, "$setOnInsert": {"created_at": now}}, upsert=True)
    return plan


async def activate_subscription(db, order: dict[str, Any]) -> None:
    """Idempotently grant credits or activate/extend a paid subscription."""
    from pymongo.errors import DuplicateKeyError

    tenant_id, product_key = order["tenant_id"], order["product_key"]
    now = datetime.now(UTC)
    product = await db.marketplace_products.find_one({"key": product_key}, {"_id": 0}) or enrich_product(
        {"key": product_key, "price_try": order.get("subtotal_try", order.get("price_try", 0)), "billing_type": order.get("billing_type", "subscription")}
    )
    try:
        await db.tenant_subscription_activations.insert_one({"order_id": order["order_id"], "tenant_id": tenant_id, "product_key": product_key, "activated_at": now.isoformat()})
    except DuplicateKeyError:
        logger.info("[marketplace] order=%s already activated", order["order_id"])
        return

    credits = order.get("credits")
    if credits and product_key.startswith("mailing"):
        await db.mailing_credits.update_one(
            {"tenant_id": tenant_id},
            {"$inc": {"balance": int(credits), "lifetime_purchased": int(credits)}, "$setOnInsert": {"tenant_id": tenant_id, "created_at": now.isoformat()}, "$set": {"updated_at": now.isoformat()}},
            upsert=True,
        )
        await db.marketplace_credit_grants.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_id, "product_key": product_key, "credits_granted": int(credits), "order_id": order["order_id"], "created_at": now.isoformat()})
        return

    existing = await db.tenant_subscriptions.find_one({"tenant_id": tenant_id, "product_key": product_key, "status": "active"})
    new_end = now + timedelta(days=order.get("duration_days") or 30)
    if existing and existing.get("end_date"):
        try:
            current_end = datetime.fromisoformat(existing["end_date"].replace("Z", "+00:00"))
            new_end = (current_end if current_end > now else now) + timedelta(days=order.get("duration_days") or 30)
        except (TypeError, ValueError):
            pass
        subscription_id = existing["id"]
        await db.tenant_subscriptions.update_one({"id": subscription_id}, {"$set": {"end_date": new_end.isoformat(), "last_renewal_order_id": order["order_id"], "trial": False, "auto_renew": bool(product.get("auto_renew", True)), "quantity": order.get("quantity", 1), "updated_at": now.isoformat()}})
    else:
        subscription_id = str(uuid.uuid4())
        await db.tenant_subscriptions.insert_one({"id": subscription_id, "tenant_id": tenant_id, "product_key": product_key, "status": "active", "start_date": now.isoformat(), "end_date": new_end.isoformat(), "order_id": order["order_id"], "trial": False, "auto_renew": bool(product.get("auto_renew", True)), "quantity": order.get("quantity", 1), "renewal_status": "scheduled", "created_at": now.isoformat()})

    if product_key == "af_sadakat":
        try:
            from core.afsadakat_provisioner import provision_tenant
            await provision_tenant(tenant_id)
        except Exception as exc:
            logger.exception("[marketplace] afsadakat provision failed for %s: %s", tenant_id, exc)
    await provision_subscription(db, tenant_id, product, subscription_id)
