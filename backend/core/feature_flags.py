"""
Dynamic Feature Flag Service
Supports: percentage rollout, tenant overrides, kill switches, expiry.
Stored in MongoDB `feature_flags` collection.
"""

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)

# ─── In-memory cache (refreshed periodically) ───
_cache: dict[str, dict[str, Any]] = {}
_cache_ts: datetime | None = None
CACHE_TTL_SECONDS = 30


async def _refresh_cache():
    """Reload all flags from DB into memory."""
    global _cache, _cache_ts
    try:
        flags = await db.feature_flags.find({}, {"_id": 0}).to_list(500)
        _cache = {f["flag_key"]: f for f in flags}
        _cache_ts = datetime.now(UTC)
    except Exception as e:
        logger.warning(f"Feature flag cache refresh failed: {e}")


async def _get_flags() -> dict[str, dict[str, Any]]:
    """Get cached flags, refresh if stale."""
    global _cache_ts
    now = datetime.now(UTC)
    if _cache_ts is None or (now - _cache_ts).total_seconds() > CACHE_TTL_SECONDS:
        await _refresh_cache()
    return _cache


async def is_flag_enabled(flag_key: str, tenant_id: str | None = None) -> bool:
    """Check if a feature flag is enabled for a given tenant.

    Resolution order:
    1. If flag doesn't exist → False
    2. If flag has `kill_switch=True` → False (global kill)
    3. If flag has expired → False
    4. If tenant_id is in `tenant_overrides` → use override value
    5. If flag has `rollout_percentage` → deterministic hash check
    6. Otherwise → flag's `enabled` field
    """
    flags = await _get_flags()
    flag = flags.get(flag_key)

    if not flag:
        return False

    # Kill switch
    if flag.get("kill_switch", False):
        return False

    # Expiry
    expires = flag.get("expires_at")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if datetime.now(UTC) > exp_dt:
                return False
        except Exception:
            pass

    # Tenant override
    overrides = flag.get("tenant_overrides", {})
    if tenant_id and tenant_id in overrides:
        return bool(overrides[tenant_id])

    # Percentage rollout
    pct = flag.get("rollout_percentage")
    if pct is not None and tenant_id:
        hash_val = int(hashlib.md5(f"{flag_key}:{tenant_id}".encode()).hexdigest(), 16) % 100
        return hash_val < pct

    return flag.get("enabled", False)


async def list_flags() -> list[dict[str, Any]]:
    """List all feature flags."""
    flags = await _get_flags()
    return list(flags.values())


async def get_flag(flag_key: str) -> dict[str, Any] | None:
    """Get a single feature flag."""
    flags = await _get_flags()
    return flags.get(flag_key)


async def upsert_flag(
    flag_key: str,
    enabled: bool = False,
    description: str = "",
    rollout_percentage: int | None = None,
    tenant_overrides: dict[str, bool] | None = None,
    kill_switch: bool = False,
    expires_at: str | None = None,
    updated_by: str = "system",
) -> dict[str, Any]:
    """Create or update a feature flag."""
    now = datetime.now(UTC).isoformat()

    doc = {
        "flag_key": flag_key,
        "enabled": enabled,
        "description": description,
        "rollout_percentage": rollout_percentage,
        "tenant_overrides": tenant_overrides or {},
        "kill_switch": kill_switch,
        "expires_at": expires_at,
        "updated_by": updated_by,
        "updated_at": now,
    }

    await db.feature_flags.update_one(
        {"flag_key": flag_key},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    # Invalidate cache
    global _cache_ts
    _cache_ts = None

    return doc


async def delete_flag(flag_key: str) -> bool:
    """Delete a feature flag."""
    result = await db.feature_flags.delete_one({"flag_key": flag_key})
    global _cache_ts
    _cache_ts = None
    return result.deleted_count > 0


async def set_tenant_override(flag_key: str, tenant_id: str, enabled: bool):
    """Set a tenant-specific override for a flag."""
    await db.feature_flags.update_one(
        {"flag_key": flag_key},
        {"$set": {f"tenant_overrides.{tenant_id}": enabled, "updated_at": datetime.now(UTC).isoformat()}},
    )
    global _cache_ts
    _cache_ts = None


async def remove_tenant_override(flag_key: str, tenant_id: str):
    """Remove a tenant-specific override."""
    await db.feature_flags.update_one(
        {"flag_key": flag_key},
        {"$unset": {f"tenant_overrides.{tenant_id}": ""}, "$set": {"updated_at": datetime.now(UTC).isoformat()}},
    )
    global _cache_ts
    _cache_ts = None


async def ensure_feature_flag_indexes():
    """Create indexes for feature_flags collection."""
    try:
        await db.feature_flags.create_index("flag_key", unique=True, name="idx_flag_key")
        logger.info("Feature flag indexes ensured")
    except Exception as e:
        logger.warning(f"Feature flag index creation: {e}")
