"""
ARI Push Engine — API Router.
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from cache_manager import cached
from core.security import _is_super_admin, get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from . import drift_worker, outbound_service
from . import repositories as repo
from .events import ARIChangeEvent
from datetime import UTC, datetime, timedelta
from .provider_snapshot_contract import (
    ProviderSnapshotUnavailable,
    CredentialsMissing,
    UnsupportedProvider,
)
from domains.channel_manager.providers.hotelrunner.snapshot_adapter import HotelRunnerSnapshotAdapter
from domains.channel_manager.providers.exely.snapshot_adapter import ExelySnapshotAdapter
from .truth_builder import build_pms_ari_snapshot

def _get_snapshot_adapter(provider: str):
    if provider == "hotelrunner":
        return HotelRunnerSnapshotAdapter()
    elif provider == "exely":
        return ExelySnapshotAdapter()
    raise UnsupportedProvider(f"Unknown provider: {provider}")
from .provider_test_harness import ExelyTestRunner, HotelRunnerTestRunner, get_checklist
from .schemas import (
    DriftCheckRequest,
    PublishARIEventRequest,
    PushChangeSetsRequest,
    ResyncRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/ari", tags=["ARI Push Engine"])


def _resolve_scope(
    user: User,
    tenant_id: str | None,
    property_id: str | None,
) -> tuple[str, str]:
    """
    Resolve effective tenant_id + property_id, enforcing tenant isolation.

    Non-admin users can NEVER read another tenant's data, regardless of what
    they pass as a query param. This closes the prior cross-tenant read CVE
    in /events, /change-sets, /outbound-logs, /drift, /stats, /test-harness.
    """
    user_tid = getattr(user, "tenant_id", None)
    user_pid = str(getattr(user, "hotel_id", "") or "")

    if _is_super_admin(user):
        eff_tid = tenant_id or user_tid
        eff_pid = property_id or user_pid
    else:
        # Force tenant_id to caller's. Property_id may be a hotel they own;
        # if not provided, fall back to their canonical hotel_id.
        if tenant_id and tenant_id != user_tid:
            raise HTTPException(status_code=403, detail="Cross-tenant access denied")
        eff_tid = user_tid
        eff_pid = property_id or user_pid

    if not eff_tid:
        raise HTTPException(status_code=400, detail="tenant_id resolution failed")
    return eff_tid, (eff_pid or "")


# ── Events ───────────────────────────────────────────────────────────


@router.post("/events/publish")
async def publish_event(
    req: PublishARIEventRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Publish an ARI change event into the push pipeline."""
    # Canonicalize tenant_id: non-admins can never publish to another tenant
    if not _is_super_admin(current_user):
        req.tenant_id = current_user.tenant_id
    event = ARIChangeEvent(
        tenant_id=req.tenant_id,
        property_id=req.property_id,
        source_service=req.source_service,
        event_type=req.event_type,
        room_type_code=req.room_type_code,
        rate_plan_code=req.rate_plan_code,
        date_from=req.date_from,
        date_to=req.date_to,
        payload=req.payload,
        actor_id=req.actor_id,
    )
    return await outbound_service.publish_ari_event(event)


@router.get("/events")
async def list_events(
    tenant_id: str | None = None,
    property_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    events = await repo.get_ari_events(eff_tid, eff_pid, limit, skip, event_type)
    return {"events": events, "count": len(events)}


@router.get("/change-sets")
async def list_change_sets(
    tenant_id: str | None = None,
    property_id: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    change_sets = await repo.get_change_sets(eff_tid, eff_pid, status, provider, limit, skip)
    return {"change_sets": change_sets, "count": len(change_sets)}


@router.post("/change-sets/{cs_id}/push")
async def force_push_change_set(
    cs_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """
    Force-push a specific change set. Closes IDOR: a tenant operator can
    NEVER trigger a push on another tenant's change set even if they
    obtain its UUID.
    """
    from core.database import db

    from .models import COLL_ARI_CHANGE_SETS

    cs = await db[COLL_ARI_CHANGE_SETS].find_one(
        {"id": cs_id},
        {"_id": 0, "tenant_id": 1},
    )
    if not cs:
        raise HTTPException(status_code=404, detail="Change set not found")
    if not _is_super_admin(current_user) and cs.get("tenant_id") != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant push denied")
    return await outbound_service.force_push_change_set(cs_id)


@router.post("/push")
async def push_pending(
    req: PushChangeSetsRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    if not _is_super_admin(current_user):
        req.tenant_id = current_user.tenant_id
    return await outbound_service.push_pending_changes(
        req.tenant_id,
        req.provider,
        req.limit,
    )


@router.post("/resync")
async def resync(
    req: ResyncRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    if not _is_super_admin(current_user):
        req.tenant_id = current_user.tenant_id
    return await outbound_service.resync_property(
        req.tenant_id,
        req.property_id,
        req.provider,
        req.scope,
    )


@router.get("/outbound-logs")
async def list_outbound_logs(
    tenant_id: str | None = None,
    property_id: str | None = None,
    provider: str | None = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    logs = await repo.get_outbound_logs(eff_tid, eff_pid, provider, limit, skip)
    return {"logs": logs, "count": len(logs)}


# ── Drift ────────────────────────────────────────────────────────────


@router.get("/drift")
async def list_drift_states(
    tenant_id: str | None = None,
    property_id: str | None = None,
    provider: str | None = None,
    drift_only: bool = False,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    states = await repo.get_drift_states(eff_tid, eff_pid, provider, drift_only, limit)
    return {"drift_states": states, "count": len(states)}


@router.post("/drift/check")
async def check_drift(
    req: DriftCheckRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """
    Run a drift check by comparing the PMS truth with the provider snapshot.
    """
    if not _is_super_admin(current_user):
        req.tenant_id = current_user.tenant_id

    try:
        adapter = _get_snapshot_adapter(req.provider)
    except UnsupportedProvider as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    date_from = req.date_from or datetime.now(UTC).date().isoformat()
    date_to = req.date_to or (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    
    # We do not have real credentials vault retrieval yet, we pass empty dict.
    # The adapter will fail-closed since it's not implemented yet.
    credentials = {}

    try:
        pms_snapshot = await build_pms_ari_snapshot(
            tenant_id=req.tenant_id,
            property_id=req.property_id,
            provider=req.provider,
            date_from=date_from,
            date_to=date_to,
        )
        
        provider_snapshot = await adapter.fetch_snapshot(
            tenant_id=req.tenant_id,
            property_id=req.property_id,
            credentials=credentials,
            date_from=date_from,
            date_to=date_to,
        )
        
        return await drift_worker.check_drift(
            tenant_id=req.tenant_id,
            property_id=req.property_id,
            provider=req.provider,
            pms_snapshot=pms_snapshot,
            provider_snapshot=provider_snapshot,
        )
        
    except CredentialsMissing as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProviderSnapshotUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during drift check: {e}")
        raise HTTPException(status_code=502, detail="Unexpected provider error")


@router.post("/drift/reconcile")
async def reconcile(
    req: DriftCheckRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    if not _is_super_admin(current_user):
        req.tenant_id = current_user.tenant_id
    return await drift_worker.reconcile_drift(
        req.tenant_id,
        req.property_id,
        req.provider,
    )


@router.get("/drift/mode")
async def get_drift_worker_mode(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get current TENANT-scoped drift worker mode (normal/recovery)."""
    return await repo.get_tenant_drift_mode(current_user.tenant_id)


@router.post("/drift/mode/{mode}")
async def set_drift_worker_mode(
    mode: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Set TENANT-scoped drift worker mode."""
    result = await repo.set_tenant_drift_mode(
        current_user.tenant_id,
        mode,
        getattr(current_user, "id", None),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Stats (cached, scoped) ───────────────────────────────────────────


@cached(ttl=60, key_prefix="ari_stats")
async def _stats_cached(tenant_id: str, property_id: str, _nocache: bool = False) -> dict:
    return await repo.get_ari_stats(tenant_id, property_id)


@router.get("/stats")
async def get_stats(
    tenant_id: str | None = None,
    property_id: str | None = None,
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    return await _stats_cached(eff_tid, eff_pid, _nocache=nocache)


@router.get("/engine-stats")
async def get_engine_stats(
    _perm=Depends(require_op("view_system_diagnostics")),
):
    return outbound_service.get_engine_stats()


# ── Provider Test Harness ────────────────────────────────────────────


@router.get("/test-harness/checklist/{provider}")
async def get_provider_checklist(
    provider: str,
    _perm=Depends(require_op("view_system_diagnostics")),
):
    checklist = get_checklist(provider)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    return {"provider": provider, "steps": checklist, "total": len(checklist)}


@router.post("/test-harness/run/{provider}")
async def run_provider_test(
    provider: str,
    step: str | None = None,
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Run provider validation test(s)."""
    if provider == "hotelrunner":
        runner = HotelRunnerTestRunner()
    elif provider == "exely":
        runner = ExelyTestRunner()
    else:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if step:
        result = await runner.run_step(step)
        return {"provider": provider, "results": [result]}
    results = await runner.run_all()
    passed = sum(1 for r in results if r["success"])
    return {
        "provider": provider,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
        },
    }


@cached(ttl=60, key_prefix="ari_test_harness_metrics")
async def _metrics_cached(tenant_id: str, property_id: str, _nocache: bool = False) -> dict:
    return await repo.get_operational_metrics(tenant_id, property_id)


@router.get("/test-harness/metrics")
async def get_provider_metrics(
    tenant_id: str | None = None,
    property_id: str | None = None,
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get operational metrics: provider health, latency percentiles, queue stats."""
    eff_tid, eff_pid = _resolve_scope(current_user, tenant_id, property_id)
    return await _metrics_cached(eff_tid, eff_pid, _nocache=nocache)
