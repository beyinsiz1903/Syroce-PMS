"""
Entitlement, Metering & Feature Flags — Admin API
Super-admin endpoints for viewing/managing entitlements, usage, and feature flags.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import _raw_db
from core.entitlement import (
    check_quota,
    get_tenant_entitlements,
)
from core.feature_flags import (
    delete_flag,
    get_flag,
    is_flag_enabled,
    list_flags,
    remove_tenant_override,
    set_tenant_override,
    upsert_flag,
)
from core.helpers import require_super_admin_guard
from core.metering import (
    flush_buffer,
    get_system_usage_overview,
    get_tenant_usage_summary,
    get_tenant_usage_timeline,
)
from models.schemas import User

require_super_admin = require_super_admin_guard()

router = APIRouter(prefix="/api/admin", tags=["Entitlement & Metering"])


# ─── ENTITLEMENTS ───


@router.get("/tenants/{tenant_id}/entitlements")
async def api_get_tenant_entitlements(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Get full entitlement view for a tenant: modules, quotas, plan limits."""
    result = await get_tenant_entitlements(tenant_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/tenants/{tenant_id}/quota/{resource}")
async def api_check_tenant_quota(
    tenant_id: str,
    resource: str,
    current_user: User = Depends(require_super_admin),
):
    """Check quota for a specific resource (rooms, users)."""
    if resource not in ("rooms", "users"):
        raise HTTPException(status_code=400, detail="Gecersiz kaynak tipi. rooms veya users kullanin.")
    return await check_quota(tenant_id, resource)


@router.get("/entitlements/overview")
async def api_entitlements_overview(
    current_user: User = Depends(require_super_admin),
):
    """System-wide entitlements overview: tenant counts by tier, expired subs, quota alerts."""
    tenants = await _raw_db.tenants.find({}, {"_id": 0, "id": 1, "property_name": 1, "subscription_tier": 1, "subscription_status": 1, "subscription_end_date": 1}).to_list(1000)

    tier_counts: dict[str, int] = {}
    expired = []
    now = datetime.now(UTC)

    for t in tenants:
        tier = (t.get("subscription_tier") or "basic").lower()
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        end_date = t.get("subscription_end_date")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                if now > end_dt:
                    expired.append({
                        "tenant_id": t["id"],
                        "property_name": t.get("property_name", "?"),
                        "expired_at": end_date,
                    })
            except Exception:
                pass

    return {
        "total_tenants": len(tenants),
        "by_tier": tier_counts,
        "expired_subscriptions": expired,
        "expired_count": len(expired),
    }


# ─── USAGE METERING ───


@router.get("/tenants/{tenant_id}/usage")
async def api_get_tenant_usage(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_super_admin),
):
    """Get usage summary for a tenant."""
    await flush_buffer()
    return await get_tenant_usage_summary(tenant_id, days)


@router.get("/tenants/{tenant_id}/usage/timeline")
async def api_get_tenant_usage_timeline(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=365),
    event_type: str | None = None,
    current_user: User = Depends(require_super_admin),
):
    """Get daily usage timeline for charts."""
    await flush_buffer()
    timeline = await get_tenant_usage_timeline(tenant_id, days, event_type)
    return {"timeline": timeline}


@router.get("/usage/overview")
async def api_system_usage_overview(
    current_user: User = Depends(require_super_admin),
):
    """System-wide usage overview."""
    await flush_buffer()
    return await get_system_usage_overview()


# ─── FEATURE FLAGS ───


@router.get("/feature-flags")
async def api_list_feature_flags(
    current_user: User = Depends(require_super_admin),
):
    """List all feature flags."""
    flags = await list_flags()
    return {"flags": flags, "count": len(flags)}


@router.get("/feature-flags/{flag_key}")
async def api_get_feature_flag(
    flag_key: str,
    current_user: User = Depends(require_super_admin),
):
    """Get a single feature flag."""
    flag = await get_flag(flag_key)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag bulunamadi")
    return flag


@router.post("/feature-flags")
async def api_upsert_feature_flag(
    payload: dict,
    current_user: User = Depends(require_super_admin),
):
    """Create or update a feature flag.

    Body:
    {
        "flag_key": "new_booking_flow",
        "enabled": true,
        "description": "Yeni rezervasyon akisi",
        "rollout_percentage": 50,
        "tenant_overrides": {"tenant-123": true},
        "kill_switch": false,
        "expires_at": "2026-06-01T00:00:00Z"
    }
    """
    flag_key = payload.get("flag_key")
    if not flag_key:
        raise HTTPException(status_code=400, detail="flag_key gerekli")

    result = await upsert_flag(
        flag_key=flag_key,
        enabled=payload.get("enabled", False),
        description=payload.get("description", ""),
        rollout_percentage=payload.get("rollout_percentage"),
        tenant_overrides=payload.get("tenant_overrides"),
        kill_switch=payload.get("kill_switch", False),
        expires_at=payload.get("expires_at"),
        updated_by=current_user.name,
    )
    return {"success": True, "flag": result}


@router.delete("/feature-flags/{flag_key}")
async def api_delete_feature_flag(
    flag_key: str,
    current_user: User = Depends(require_super_admin),
):
    """Delete a feature flag."""
    deleted = await delete_flag(flag_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flag bulunamadi")
    return {"success": True, "message": f"Flag silindi: {flag_key}"}


@router.patch("/feature-flags/{flag_key}/tenant-override")
async def api_set_flag_tenant_override(
    flag_key: str,
    payload: dict,
    current_user: User = Depends(require_super_admin),
):
    """Set or remove a tenant-specific override.

    Body: {"tenant_id": "...", "enabled": true}
    Or to remove: {"tenant_id": "...", "remove": true}
    """
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id gerekli")

    flag = await get_flag(flag_key)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag bulunamadi")

    if payload.get("remove"):
        await remove_tenant_override(flag_key, tenant_id)
        return {"success": True, "message": f"Override kaldirildi: {tenant_id}"}
    else:
        enabled = payload.get("enabled", False)
        await set_tenant_override(flag_key, tenant_id, enabled)
        return {"success": True, "message": f"Override ayarlandi: {tenant_id} = {enabled}"}


@router.get("/feature-flags/{flag_key}/check")
async def api_check_flag_for_tenant(
    flag_key: str,
    tenant_id: str = Query(...),
    current_user: User = Depends(require_super_admin),
):
    """Check if a flag is enabled for a specific tenant."""
    enabled = await is_flag_enabled(flag_key, tenant_id)
    return {"flag_key": flag_key, "tenant_id": tenant_id, "enabled": enabled}


# ─── ONBOARDING ───

from core.onboarding import (
    get_all_onboarding_status,
    get_onboarding_progress,
    mark_step_complete,
    reset_onboarding,
)


@router.get("/tenants/{tenant_id}/onboarding")
async def api_get_onboarding_progress(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Get onboarding progress for a tenant with auto-detection."""
    return await get_onboarding_progress(tenant_id)


@router.post("/tenants/{tenant_id}/onboarding/{step_id}/complete")
async def api_mark_onboarding_step(
    tenant_id: str,
    step_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Manually mark an onboarding step as complete."""
    await mark_step_complete(tenant_id, step_id)
    return {"success": True, "step_id": step_id}


@router.delete("/tenants/{tenant_id}/onboarding")
async def api_reset_onboarding(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Reset onboarding progress for a tenant."""
    await reset_onboarding(tenant_id)
    return {"success": True, "message": "Onboarding sifirlandi"}


@router.get("/onboarding/overview")
async def api_onboarding_overview(
    current_user: User = Depends(require_super_admin),
):
    """System-wide onboarding status overview."""
    results = await get_all_onboarding_status()
    return {"tenants": results, "count": len(results)}
