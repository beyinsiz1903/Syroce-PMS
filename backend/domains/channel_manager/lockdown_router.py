"""
Core Lockdown — Observability & Health Router
===============================================

Production-grade endpoints for:
- Reservation traceability (end-to-end event trace)
- Mapping health score
- Ingest / duplicate / drift / push metrics
- Provider capability matrix
- Reconciliation truth table
- System lockdown status

These endpoints produce DATA, not dashboards.
Visibility first, visuals later.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from core.database import db
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RECONCILIATION_CASES,
    COLL_RESERVATION_LINEAGE,
    COLL_ROOM_MAPPINGS,
)
from domains.channel_manager.mapping_validator import compute_mapping_health
from domains.channel_manager.provider_capability import (
    PROVIDER_CAPABILITIES,
)
from domains.channel_manager.reconciliation_truth import (
    get_truth_table_summary,
)
from models.schemas import User

logger = logging.getLogger("lockdown.router")
router = APIRouter(prefix="/api/lockdown", tags=["Core Lockdown"])

_NO_ID = {"_id": 0}


# ══════════════════════════════════════════════════════════════════════
# 1. RESERVATION TRACEABILITY
# ══════════════════════════════════════════════════════════════════════

@router.get("/trace/reservation/{external_reservation_id}")
async def trace_reservation(
    external_reservation_id: str,
    provider: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    End-to-end trace for a single reservation:
    received → normalized → mapped → decisioned → persisted → synced → reconciled
    """
    tenant_id = current_user.tenant_id

    # 1. Raw events for this reservation
    q = {
        "tenant_id": tenant_id,
        "external_reservation_id": external_reservation_id,
    }
    if provider:
        q["provider"] = provider

    raw_events = await db[COLL_RAW_CHANNEL_EVENTS].find(
        q, _NO_ID,
    ).sort("received_at", 1).to_list(100)

    # 2. Lineage record
    lineage = None
    if provider:
        lineage = await repo.get_lineage_by_external_id(
            tenant_id, provider, external_reservation_id,
        )
    else:
        # Try both providers
        for p in ["exely", "hotelrunner"]:
            lineage = await repo.get_lineage_by_external_id(
                tenant_id, p, external_reservation_id,
            )
            if lineage:
                break

    # 3. Reconciliation cases
    recon_cases = await db[COLL_RECONCILIATION_CASES].find(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": external_reservation_id,
        },
        _NO_ID,
    ).sort("created_at", -1).to_list(50)

    return {
        "external_reservation_id": external_reservation_id,
        "trace": {
            "raw_events": {
                "count": len(raw_events),
                "events": [
                    {
                        "id": e.get("id"),
                        "received_at": e.get("received_at"),
                        "provider_timestamp": e.get("provider_timestamp") or e.get("provider_last_modified_at"),
                        "processed_at": e.get("processed_at"),
                        "processing_status": e.get("processing_status"),
                        "decision_result": e.get("decision_result"),
                        "decision_reason": e.get("decision_reason"),
                        "payload_hash": e.get("payload_hash"),
                        "trace_id": e.get("trace_id") or e.get("correlation_id"),
                    }
                    for e in raw_events
                ],
            },
            "lineage": lineage,
            "reconciliation_cases": {
                "count": len(recon_cases),
                "cases": recon_cases,
            },
        },
    }


# ══════════════════════════════════════════════════════════════════════
# 2. MAPPING HEALTH
# ══════════════════════════════════════════════════════════════════════

@router.get("/health/mapping")
async def mapping_health(
    provider: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Mapping health score per provider.
    Completeness %, broken/inactive/ambiguous counts.
    """
    tenant_id = current_user.tenant_id
    property_id = getattr(current_user, "property_id", "default")

    providers = [provider] if provider else ["exely", "hotelrunner"]
    results = []

    for p in providers:
        room_maps = await repo.get_room_mappings(tenant_id, property_id, p)
        rate_maps = await repo.get_rate_plan_mappings(tenant_id, property_id, p)
        health = await compute_mapping_health(
            tenant_id, property_id, p, room_maps, rate_maps,
        )
        results.append(health)

    return {
        "mapping_health": results,
        "overall_production_ready": all(r["is_production_ready"] for r in results) if results else False,
    }


# ══════════════════════════════════════════════════════════════════════
# 3. INGEST METRICS
# ══════════════════════════════════════════════════════════════════════

@router.get("/metrics/ingest")
async def ingest_metrics(
    hours: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Ingest pipeline metrics for the last N hours:
    - success rate, duplicate rate, out-of-order rate
    - processing latency, failed decision count
    """
    tenant_id = current_user.tenant_id
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {
            "tenant_id": tenant_id,
            "received_at": {"$gte": since},
        }},
        {"$group": {
            "_id": "$processing_status",
            "count": {"$sum": 1},
        }},
    ]

    stats = {}
    async for doc in db[COLL_RAW_CHANNEL_EVENTS].aggregate(pipeline):
        stats[doc["_id"]] = doc["count"]

    total = sum(stats.values())
    processed = stats.get("processed", 0)
    duplicate = stats.get("duplicate", 0)
    stale = stats.get("stale", 0)
    failed = stats.get("failed", 0)
    pending = stats.get("pending", 0)

    # Decision breakdown
    decision_pipeline = [
        {"$match": {
            "tenant_id": tenant_id,
            "received_at": {"$gte": since},
            "decision_result": {"$ne": None},
        }},
        {"$group": {
            "_id": "$decision_result",
            "count": {"$sum": 1},
        }},
    ]
    decision_stats = {}
    async for doc in db[COLL_RAW_CHANNEL_EVENTS].aggregate(decision_pipeline):
        if doc["_id"]:
            decision_stats[doc["_id"]] = doc["count"]

    return {
        "period_hours": hours,
        "since": since,
        "totals": {
            "total_events": total,
            "processed": processed,
            "duplicate": duplicate,
            "stale": stale,
            "failed": failed,
            "pending": pending,
        },
        "rates": {
            "success_rate_pct": round(processed / total * 100, 1) if total > 0 else 0,
            "duplicate_rate_pct": round(duplicate / total * 100, 1) if total > 0 else 0,
            "stale_rate_pct": round(stale / total * 100, 1) if total > 0 else 0,
            "failure_rate_pct": round(failed / total * 100, 1) if total > 0 else 0,
        },
        "decisions": decision_stats,
    }


# ══════════════════════════════════════════════════════════════════════
# 4. LINEAGE METRICS
# ══════════════════════════════════════════════════════════════════════

@router.get("/metrics/lineage")
async def lineage_metrics(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Reservation lineage metrics:
    - by status, by provider, reconciliation status
    """
    tenant_id = current_user.tenant_id

    status_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id": {"status": "$status", "provider": "$provider"},
            "count": {"$sum": 1},
        }},
    ]

    by_status = {}
    by_provider = {}
    total = 0
    reconciled = 0

    async for doc in db[COLL_RESERVATION_LINEAGE].aggregate(status_pipeline):
        status = doc["_id"]["status"]
        provider = doc["_id"]["provider"]
        count = doc["count"]
        total += count
        by_status[status] = by_status.get(status, 0) + count
        by_provider[provider] = by_provider.get(provider, 0) + count

    reconciled = await db[COLL_RESERVATION_LINEAGE].count_documents(
        {"tenant_id": tenant_id, "reconciled": True},
    )

    return {
        "total_lineages": total,
        "by_status": by_status,
        "by_provider": by_provider,
        "reconciled": reconciled,
        "unreconciled": total - reconciled,
    }


# ══════════════════════════════════════════════════════════════════════
# 5. RECONCILIATION METRICS
# ══════════════════════════════════════════════════════════════════════

@router.get("/metrics/reconciliation")
async def reconciliation_metrics(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Reconciliation case metrics:
    - open cases by type, by severity
    - unresolved mismatch age
    """
    tenant_id = current_user.tenant_id

    summary = await repo.get_reconciliation_summary(tenant_id)

    # Oldest unresolved case
    oldest = await db[COLL_RECONCILIATION_CASES].find_one(
        {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}},
        _NO_ID,
        sort=[("created_at", 1)],
    )
    oldest_age_hours = None
    if oldest:
        created = datetime.fromisoformat(oldest["created_at"].replace("Z", "+00:00"))
        oldest_age_hours = round(
            (datetime.now(UTC) - created).total_seconds() / 3600, 1,
        )

    return {
        **summary,
        "oldest_unresolved_age_hours": oldest_age_hours,
    }


# ══════════════════════════════════════════════════════════════════════
# 6. PROVIDER CAPABILITY MATRIX
# ══════════════════════════════════════════════════════════════════════

@router.get("/providers/capabilities")
async def provider_capabilities(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Full provider capability matrix.
    Not just config — behavioral contract for each provider.
    """
    result = []
    for name, cap in PROVIDER_CAPABILITIES.items():
        result.append({
            "provider": name,
            "display_name": cap.display_name,
            "reservation": {
                "ingest_type": cap.reservation_ingest_type.value,
                "cancellation_behavior": cap.cancellation_behavior.value,
                "modification_behavior": cap.modification_behavior.value,
            },
            "ari": {
                "push_behavior": cap.ari_push_behavior.value,
                "supports_delta_push": cap.supports_delta_push,
                "supports_restrictions": cap.supports_restriction_push,
                "max_date_range_days": cap.max_date_range_days,
            },
            "consistency": {
                "eventual_consistency_window_sec": cap.eventual_consistency_window_seconds,
                "typical_ack_latency_ms": cap.typical_ack_latency_ms,
                "ack_means_applied": cap.ack_means_applied,
            },
            "rate_limits": {
                "requests_per_minute": cap.rate_limits.requests_per_minute,
                "requests_per_hour": cap.rate_limits.requests_per_hour,
                "burst_limit": cap.rate_limits.burst_limit,
            },
            "retry_policy": {
                "max_attempts": cap.retry_policy.max_attempts,
                "base_delay_sec": cap.retry_policy.base_delay_seconds,
                "max_delay_sec": cap.retry_policy.max_delay_seconds,
            },
            "error_classes": {
                pattern: cls.value
                for pattern, cls in cap.error_classification.items()
            },
        })

    return {"providers": result}


# ══════════════════════════════════════════════════════════════════════
# 7. RECONCILIATION TRUTH TABLE
# ══════════════════════════════════════════════════════════════════════

@router.get("/reconciliation/truth-table")
async def truth_table(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    The system's constitutional document for data ownership.
    Defines gold source and resolution policy for each drift type.
    """
    return {
        "truth_table": get_truth_table_summary(),
    }


# ══════════════════════════════════════════════════════════════════════
# 8. SYSTEM LOCKDOWN STATUS
# ══════════════════════════════════════════════════════════════════════

@router.get("/status")
async def lockdown_status(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Overall system lockdown status.
    Checks: mapping health, ingest health, reconciliation health.
    """
    tenant_id = current_user.tenant_id

    # Quick health checks
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    # Ingest stats (last 24h)
    total_events = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"tenant_id": tenant_id, "received_at": {"$gte": since_24h}},
    )
    failed_events = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"tenant_id": tenant_id, "received_at": {"$gte": since_24h}, "processing_status": "failed"},
    )

    # Open recon cases
    open_cases = await db[COLL_RECONCILIATION_CASES].count_documents(
        {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}},
    )
    critical_cases = await db[COLL_RECONCILIATION_CASES].count_documents(
        {"tenant_id": tenant_id, "status": "open", "severity": "critical"},
    )

    # Mapping health (quick)
    room_maps = await db[COLL_ROOM_MAPPINGS].count_documents(
        {"tenant_id": tenant_id, "is_active": True},
    )
    broken_room_maps = await db[COLL_ROOM_MAPPINGS].count_documents(
        {"tenant_id": tenant_id, "is_active": True, "pms_room_type_id": {"$in": [None, ""]}},
    )

    # Unreconciled lineages
    unreconciled = await db[COLL_RESERVATION_LINEAGE].count_documents(
        {"tenant_id": tenant_id, "reconciled": False},
    )

    ingest_healthy = failed_events == 0 or (total_events > 0 and failed_events / total_events < 0.05)
    mapping_healthy = broken_room_maps == 0
    recon_healthy = critical_cases == 0

    return {
        "status": "healthy" if (ingest_healthy and mapping_healthy and recon_healthy) else "degraded",
        "checks": {
            "ingest": {
                "status": "healthy" if ingest_healthy else "degraded",
                "events_24h": total_events,
                "failed_24h": failed_events,
                "failure_rate_pct": round(failed_events / total_events * 100, 1) if total_events > 0 else 0,
            },
            "mapping": {
                "status": "healthy" if mapping_healthy else "degraded",
                "active_room_mappings": room_maps,
                "broken_room_mappings": broken_room_maps,
            },
            "reconciliation": {
                "status": "healthy" if recon_healthy else "degraded",
                "open_cases": open_cases,
                "critical_cases": critical_cases,
                "unreconciled_lineages": unreconciled,
            },
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
