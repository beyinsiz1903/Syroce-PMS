import logging
from datetime import UTC, datetime
from typing import Callable

from fastapi import Depends, HTTPException
from starlette.requests import Request

from core.database import db
from core.entitlements.registry import get_module_definition
from core.security import get_current_user
from core.subscriptions import tenant_has_module
from models.schemas import User

logger = logging.getLogger(__name__)

async def get_tenant_active_editions(tenant_id: str, module_key: str) -> list[str]:
    """
    Returns the list of active edition keys (e.g. ['basic', 'pro'])
    a tenant has for a given module.
    It checks both the legacy tenant 'modules' field (if we migrate it, it would act as basic or pro)
    and the `tenant_subscriptions` collection.
    """
    now = datetime.now(UTC)
    subs = await db.tenant_subscriptions.find(
        {
            "tenant_id": tenant_id,
            "status": "active",
            "$or": [
                {"end_date": None},
                {"end_date": {"$gt": now.isoformat()}},
            ],
            "product_key": {"$regex": f"^{module_key}_"}
        },
        {"_id": 0, "product_key": 1}
    ).to_list(100)

    editions = []
    for sub in subs:
        pk = sub.get("product_key", "")
        # e.g. pos_fnb_pro -> edition is 'pro'
        if pk.startswith(f"{module_key}_"):
            editions.append(pk[len(module_key)+1:])

    # Fallback to check if module is natively enabled via legacy tenant plan
    if not editions:
        has_legacy = await tenant_has_module(tenant_id, module_key)
        if has_legacy:
            # We assume legacy module access maps to 'pro' for now to avoid breaking existing users.
            editions.append("pro")

    return editions

async def tenant_has_feature(tenant_id: str, module_key: str, feature_key: str) -> bool:
    """Check if the tenant has a specific feature for the given module."""
    editions = await get_tenant_active_editions(tenant_id, module_key)
    if not editions:
        return False

    module_def = get_module_definition(module_key)
    if not module_def:
        # If no definition is found, we fall back to strict rejection.
        return False

    for ed in editions:
        edition_def = module_def.editions.get(ed)
        if edition_def and feature_key in edition_def.features:
            return True

    return False

async def get_tenant_limit(tenant_id: str, module_key: str, limit_key: str) -> int | None:
    """
    Get the highest limit for a given limit_key across all active editions
    the tenant has for the module.
    """
    editions = await get_tenant_active_editions(tenant_id, module_key)
    if not editions:
        return 0

    module_def = get_module_definition(module_key)
    if not module_def:
        return 0

    max_limit = -1
    for ed in editions:
        edition_def = module_def.editions.get(ed)
        if edition_def and limit_key in edition_def.limits:
            limit_val = edition_def.limits[limit_key]
            # None or 0 means unlimited in some contexts, but let's assume integers
            if limit_val > max_limit:
                max_limit = limit_val

    return max_limit if max_limit >= 0 else 0


import os

# ─── FASTAPI DEPENDENCIES ───

def require_module(module_key: str) -> Callable:
    async def _require_module(request: Request, current_user: User = Depends(get_current_user)):
        has_access = await tenant_has_module(current_user.tenant_id, module_key)
        if not has_access:
            mode = os.environ.get("ENTITLEMENT_ENFORCEMENT_MODE", "observe")
            if mode == "observe":
                logger.warning(f"[ENTITLEMENT_OBSERVE] Tenant {current_user.tenant_id} blocked for {module_key} but allowed due to observe mode.")
                return
            raise HTTPException(
                status_code=403,
                detail=f"Bu islem icin {module_key} modulu gereklidir.",
            )
    return _require_module

def require_feature(module_key: str, feature_key: str) -> Callable:
    async def _require_feature(request: Request, current_user: User = Depends(get_current_user)):
        has_feature = await tenant_has_feature(current_user.tenant_id, module_key, feature_key)
        if not has_feature:
            mode = os.environ.get("ENTITLEMENT_ENFORCEMENT_MODE", "observe")
            if mode == "observe":
                logger.warning(f"[ENTITLEMENT_OBSERVE] Tenant {current_user.tenant_id} blocked for feature {feature_key} but allowed due to observe mode.")
                return
            raise HTTPException(
                status_code=403,
                detail=f"Bu islem icin {module_key} ({feature_key}) ozelligi gereklidir. Lutfen planinizi yukseltin.",
            )
    return _require_feature

def require_limit(module_key: str, limit_key: str, current_count_resolver: Callable) -> Callable:
    """
    To use this, pass a callable that takes the current FastAPI dependencies (like `request`, `current_user`)
    and returns the current usage count.
    Currently, we will just provide the limit getter, and let the endpoint check it manually to avoid
    complex dynamic dependencies.
    """
    # Alternative: it's often easier to check limits inside the router logic
    # instead of a Depends, because counting usage might require DB queries.
    pass
