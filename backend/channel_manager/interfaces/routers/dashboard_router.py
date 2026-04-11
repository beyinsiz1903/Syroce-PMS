"""
Unified Channel Manager Dashboard Router.

Aggregates connector health, reservations, failures, push queue,
and mapping visibility into a single operational overview.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ...application.auto_mapping_service import AutoMappingService
from ...infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.routers.dashboard")

router = APIRouter(tags=["CM Dashboard"])


@router.get("/dashboard/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    repo = ChannelManagerRepository()

    connectors = await repo.get_connectors_by_tenant(tenant_id)
    total = len(connectors)
    healthy = sum(1 for c in connectors if c.get("status") == "active" and c.get("consecutive_failures", 0) == 0)
    degraded = sum(1 for c in connectors if c.get("status") == "active" and c.get("consecutive_failures", 0) > 0)
    error_count = sum(1 for c in connectors if c.get("status") == "error")
    paused = sum(1 for c in connectors if c.get("status") == "paused")

    connector_details = []
    for c in connectors:
        connector_details.append({
            "id": c.get("id", ""),
            "display_name": c.get("display_name", ""),
            "provider": c.get("provider", ""),
            "status": c.get("status", ""),
            "property_id": c.get("property_id", ""),
            "last_successful_sync": c.get("last_successful_sync"),
            "last_error": c.get("last_error"),
            "last_error_at": c.get("last_error_at"),
            "consecutive_failures": c.get("consecutive_failures", 0),
            "total_syncs": c.get("total_syncs", 0),
            "total_errors": c.get("total_errors", 0),
        })

    now = datetime.now(UTC)
    since_24h = (now - timedelta(hours=24)).isoformat()

    recent_res = await db.cm_imported_reservations.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": since_24h},
    })

    failed_imports = await db.cm_imported_reservations.count_documents({
        "tenant_id": tenant_id,
        "import_status": "failed",
    })

    review_queue = await db.cm_imported_reservations.count_documents({
        "tenant_id": tenant_id,
        "import_status": "review",
    })

    recent_reservations = await db.cm_imported_reservations.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "external_reservation_id": 1, "connector_id": 1,
         "guest_name": 1, "import_status": 1, "check_in": 1, "check_out": 1,
         "room_type": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(10)

    push_queue_depth = await db.connector_outbox.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["pending", "retry"]},
    })

    ari_pending = await db.ari_change_sets.count_documents({
        "tenant_id": tenant_id,
        "status": "pending",
    })

    wire_failures_24h = 0
    for coll_name in ["ari_hard_fail_log", "exely_sync_logs"]:
        coll = db[coll_name]
        wire_failures_24h += await coll.count_documents({
            "tenant_id": tenant_id,
            "created_at": {"$gte": since_24h},
        })

    dlq_count = await db.connector_outbox.count_documents({
        "tenant_id": tenant_id,
        "status": "dead_letter",
    })

    mapping_svc = AutoMappingService(repo=repo)
    mapping_visibility = {
        "connectors_with_mappings": 0,
        "total_review_pending": 0,
        "total_conflicts": 0,
        "provider_summaries": [],
    }
    for c in connectors:
        cid = c.get("id", "")
        provider = c.get("provider", "")
        if c.get("status") not in ("active", "paused"):
            continue
        try:
            result = await mapping_svc.suggest_room_mappings(tenant_id, cid)
            summary = result.get("summary", {})
            conflicts = result.get("conflicts", [])
            has_mappings = summary.get("already_mapped", 0) > 0
            review_count = summary.get("needs_review", 0)
            conflict_count = len(conflicts)

            if has_mappings:
                mapping_visibility["connectors_with_mappings"] += 1
            mapping_visibility["total_review_pending"] += review_count
            mapping_visibility["total_conflicts"] += conflict_count

            mapping_visibility["provider_summaries"].append({
                "connector_id": cid,
                "connector_name": c.get("display_name", ""),
                "provider": provider,
                "mapped": summary.get("already_mapped", 0),
                "auto_matched": summary.get("auto_matched", 0),
                "needs_review": review_count,
                "unmatched": summary.get("unmatched", 0),
                "conflicts": conflict_count,
            })
        except Exception as e:
            logger.warning("Mapping visibility failed for connector %s: %s", cid, e)

    return {
        "kpis": {
            "total_connectors": total,
            "healthy": healthy,
            "degraded": degraded,
            "error": error_count,
            "paused": paused,
            "recent_reservations_24h": recent_res,
            "failed_imports": failed_imports,
            "review_queue": review_queue,
            "push_queue_depth": push_queue_depth + ari_pending,
            "wire_failures_24h": wire_failures_24h,
            "dlq_count": dlq_count,
        },
        "connectors": connector_details,
        "recent_reservations": recent_reservations,
        "mapping_visibility": mapping_visibility,
    }


@router.get("/dashboard/connector/{connector_id}")
async def get_connector_drilldown(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    repo = ChannelManagerRepository()

    connector = await repo.get_connector(tenant_id, connector_id)
    if not connector:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Connector bulunamadi")

    recent_failures = await db.ari_hard_fail_log.find(
        {"tenant_id": tenant_id, "connector_id": connector_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)

    queue_items = await db.connector_outbox.find(
        {"tenant_id": tenant_id, "connector_id": connector_id,
         "status": {"$in": ["pending", "retry", "dead_letter"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)

    res_stats = await db.cm_imported_reservations.aggregate([
        {"$match": {"tenant_id": tenant_id, "connector_id": connector_id}},
        {"$group": {
            "_id": "$import_status",
            "count": {"$sum": 1},
        }},
    ]).to_list(20)
    res_stats_dict = {r["_id"]: r["count"] for r in res_stats}

    mapping_svc = AutoMappingService(repo=repo)
    try:
        mapping_result = await mapping_svc.suggest_room_mappings(tenant_id, connector_id)
        mapping_summary = mapping_result.get("summary", {})
        mapping_conflicts = mapping_result.get("conflicts", [])
    except Exception:
        mapping_summary = {}
        mapping_conflicts = []

    return {
        "connector": {
            "id": connector.get("id", ""),
            "display_name": connector.get("display_name", ""),
            "provider": connector.get("provider", ""),
            "status": connector.get("status", ""),
            "property_id": connector.get("property_id", ""),
            "last_successful_sync": connector.get("last_successful_sync"),
            "last_error": connector.get("last_error"),
            "last_error_at": connector.get("last_error_at"),
            "consecutive_failures": connector.get("consecutive_failures", 0),
            "total_syncs": connector.get("total_syncs", 0),
            "total_errors": connector.get("total_errors", 0),
        },
        "recent_failures": recent_failures,
        "queue": {
            "items": queue_items,
            "pending": sum(1 for q in queue_items if q.get("status") == "pending"),
            "retry": sum(1 for q in queue_items if q.get("status") == "retry"),
            "dead_letter": sum(1 for q in queue_items if q.get("status") == "dead_letter"),
        },
        "reservation_stats": res_stats_dict,
        "mapping": {
            "summary": mapping_summary,
            "conflicts": mapping_conflicts,
        },
    }
