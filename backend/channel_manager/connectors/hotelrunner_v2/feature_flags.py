"""
HotelRunner v2 — Feature Flags & Shadow Mode
==============================================

Tenant-level feature flags stored in MongoDB:
  - connector_enabled: bool (default False)
  - shadow_mode: bool (default True — ingest+compare only, no writes)
  - write_enabled: bool (default False)

Flag evaluation is cached per-request (no flag caching across requests
to ensure immediate effect on toggle).
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.flags")

COLL_FEATURE_FLAGS = "connector_feature_flags"
_NO_ID = {"_id": 0}

# Defaults: connector disabled, shadow mode on, writes off
_DEFAULTS = {
    "connector_enabled": False,
    "shadow_mode": True,
    "write_enabled": False,
    "dry_run_mode": False,
    "limited_scope": False,
    "reconciliation_enabled": True,
    "auto_fix_enabled": False,
}


async def get_flags(tenant_id: str) -> dict[str, Any]:
    """Get feature flags for tenant. Returns defaults if not configured."""
    doc = await db[COLL_FEATURE_FLAGS].find_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        _NO_ID,
    )
    if not doc:
        return {**_DEFAULTS, "tenant_id": tenant_id}
    return {**_DEFAULTS, **doc}


async def set_flags(tenant_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update feature flags for a tenant. Returns updated flags."""
    now = datetime.now(UTC).isoformat()
    allowed_keys = set(_DEFAULTS.keys())
    filtered = {k: v for k, v in updates.items() if k in allowed_keys}

    await db[COLL_FEATURE_FLAGS].update_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        {"$set": {**filtered, "updated_at": now}},
        upsert=True,
    )
    logger.info("[HRv2 flags] tenant=%s updated: %s", tenant_id, filtered)
    return await get_flags(tenant_id)


async def is_enabled(tenant_id: str) -> bool:
    """Quick check: is the v2 connector enabled for this tenant?"""
    flags = await get_flags(tenant_id)
    return flags.get("connector_enabled", False)


async def is_shadow_mode(tenant_id: str) -> bool:
    """Quick check: is shadow mode active? (ingest + compare, no writes)"""
    flags = await get_flags(tenant_id)
    return flags.get("shadow_mode", True)


async def is_write_enabled(tenant_id: str) -> bool:
    """Quick check: are writes (ARI push) allowed?"""
    flags = await get_flags(tenant_id)
    return flags.get("write_enabled", False) and not flags.get("shadow_mode", True)
