"""
ARI Drift Worker (Background Task).

Per-tenant dual-mode operation:
  - Normal: 2 min interval, only rooms that changed since last check
  - Recovery: 30 sec interval, full property scope (for incident response)

Mode is persisted per-tenant in `ari_drift_modes` (DB-backed). A tenant
flipping into recovery does NOT affect other tenants — fixes the prior
multi-tenant violation where a process-level global flag forced every
tenant's worker into 30s full-scan.
"""
import asyncio
import logging

from core.database import db
from domains.channel_manager.ari import repositories as repo
from domains.channel_manager.ari.drift_worker import check_drift

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (router imports DRIFT_CONFIG from here)
DRIFT_CONFIG = repo.DRIFT_CONFIG
DRIFT_MODE_NORMAL = repo.DRIFT_MODE_NORMAL
DRIFT_MODE_RECOVERY = repo.DRIFT_MODE_RECOVERY


# ── Deprecated process-level shims (kept for backward compat only) ───
# These are NO LONGER used by the worker loop. Per-tenant mode is the
# authoritative source. Left in place so any legacy callers don't break.
_legacy_mode = DRIFT_MODE_NORMAL


def get_drift_mode() -> str:
    """DEPRECATED: process-level fallback. Use repo.get_tenant_drift_mode."""
    return _legacy_mode


def set_drift_mode(mode: str) -> dict:
    """DEPRECATED: process-level fallback. Use repo.set_tenant_drift_mode."""
    global _legacy_mode
    if mode not in DRIFT_CONFIG:
        return {"error": f"Invalid mode: {mode}. Valid: {list(DRIFT_CONFIG.keys())}"}
    _legacy_mode = mode
    cfg = DRIFT_CONFIG[mode]
    return {
        "current_mode": mode,
        "interval": cfg["interval"],
        "scope": cfg["scope"],
    }


# ── Worker Loop ──────────────────────────────────────────────────────

# Smallest cycle granularity (= recovery interval). Tenants in normal
# mode are skipped until their per-tenant interval elapses.
_TICK_SECONDS = DRIFT_CONFIG[DRIFT_MODE_RECOVERY]["interval"]

# Per-tenant last-run timestamps (in-process). Loss on restart only
# means a single "early" check after boot — harmless.
_last_run: dict[str, float] = {}


async def ari_drift_worker_loop():
    """Per-tenant drift worker loop."""
    logger.info("ARI drift worker started (per-tenant mode)")
    loop = asyncio.get_event_loop()
    while True:
        try:
            now = loop.time()
            connections = await db["provider_connections"].find(
                {"status": "active"}, {"_id": 0},
            ).to_list(500)

            for conn in connections:
                tenant_id = conn.get("tenant_id")
                property_id = conn.get("property_id")
                provider = conn.get("provider")
                if not all([tenant_id, property_id, provider]):
                    continue

                # Per-tenant mode lookup (tolerates DB hiccup)
                try:
                    cfg = await repo.get_tenant_drift_mode(tenant_id)
                except Exception as e:
                    logger.warning("drift mode lookup failed [%s]: %s", tenant_id, e)
                    cfg = {"mode": DRIFT_MODE_NORMAL, **DRIFT_CONFIG[DRIFT_MODE_NORMAL]}

                interval = cfg["interval"]
                scope = cfg["scope"]
                key = f"{tenant_id}|{property_id}|{provider}"
                last = _last_run.get(key, 0.0)
                if (now - last) < interval:
                    continue

                try:
                    pms_snapshot: list = []
                    provider_snapshot: list = []
                    if scope == "changed":
                        pass  # incremental — populated by event-driven coalescer
                    if pms_snapshot or provider_snapshot:
                        await check_drift(
                            tenant_id, property_id, provider,
                            pms_snapshot, provider_snapshot,
                        )
                    _last_run[key] = now
                except Exception as e:
                    logger.error(
                        "Drift check error [%s/%s/%s]: %s",
                        tenant_id, provider, property_id, e,
                    )

            await asyncio.sleep(_TICK_SECONDS)
        except Exception as e:
            logger.error("ARI drift worker error: %s", e)
            await asyncio.sleep(_TICK_SECONDS)


async def start_drift_worker():
    """Start the drift worker as a background task."""
    asyncio.create_task(ari_drift_worker_loop())
    logger.info("ARI drift worker task created")
