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
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from cache_manager import cached
from core.database import db
from core.security import get_current_user
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
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger("lockdown.router")
router = APIRouter(prefix="/api/lockdown", tags=["Core Lockdown"])

_NO_ID = {"_id": 0}


def _resolve_property(current_user: User, property_id: str | None) -> str:
    """
    Resolve effective property_id with proper precedence:
    1. Query param (allows multi-property tenants to switch)
    2. user.property_id (set in user record)
    3. user.hotel_id (canonical hotel ID)
    4. "default" — last-resort fallback for legacy data written
       before per-property scoping existed
    """
    return (
        property_id
        or getattr(current_user, "property_id", None)
        or getattr(current_user, "hotel_id", None)
        or "default"
    )


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

    q = {
        "tenant_id": tenant_id,
        "external_reservation_id": external_reservation_id,
    }
    if provider:
        q["provider"] = provider

    raw_events = await db[COLL_RAW_CHANNEL_EVENTS].find(
        q, _NO_ID,
    ).sort("received_at", 1).to_list(100)

    lineage = None
    if provider:
        lineage = await repo.get_lineage_by_external_id(
            tenant_id, provider, external_reservation_id,
        )
    else:
        for p in ["exely", "hotelrunner"]:
            lineage = await repo.get_lineage_by_external_id(
                tenant_id, p, external_reservation_id,
            )
            if lineage:
                break

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
# 2. MAPPING HEALTH (cached)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=60, key_prefix="lockdown_mapping_health")
async def _mapping_health_cached(
    tenant_id: str, property_id: str, provider: str | None,
    _nocache: bool = False,
) -> dict:
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


@router.get("/health/mapping")
async def mapping_health(
    provider: str | None = None,
    property_id: str | None = None,
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Mapping health score per provider. Completeness %, broken/inactive/ambiguous."""
    eff_pid = _resolve_property(current_user, property_id)
    return await _mapping_health_cached(
        current_user.tenant_id, eff_pid, provider, _nocache=nocache,
    )


# ══════════════════════════════════════════════════════════════════════
# 3. INGEST METRICS (cached)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=60, key_prefix="lockdown_ingest_metrics")
async def _ingest_metrics_cached(
    tenant_id: str, hours: int, _nocache: bool = False,
) -> dict:
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


@router.get("/metrics/ingest")
async def ingest_metrics(
    hours: int = Query(default=24, ge=1, le=168),
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Ingest pipeline metrics for the last N hours."""
    return await _ingest_metrics_cached(
        current_user.tenant_id, hours, _nocache=nocache,
    )


# ══════════════════════════════════════════════════════════════════════
# 4. LINEAGE METRICS (cached)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=60, key_prefix="lockdown_lineage_metrics")
async def _lineage_metrics_cached(tenant_id: str, _nocache: bool = False) -> dict:
    status_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id": {"status": "$status", "provider": "$provider"},
            "count": {"$sum": 1},
        }},
    ]

    by_status: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    total = 0

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


@router.get("/metrics/lineage")
async def lineage_metrics(
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Reservation lineage metrics: by status, by provider, reconciliation status."""
    return await _lineage_metrics_cached(current_user.tenant_id, _nocache=nocache)


# ══════════════════════════════════════════════════════════════════════
# 5. RECONCILIATION METRICS (cached, contract-fixed)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=60, key_prefix="lockdown_recon_metrics")
async def _recon_metrics_cached(tenant_id: str, _nocache: bool = False) -> dict:
    """
    Returns BOTH the legacy summary fields (total_open, by_type, by_severity)
    AND the dashboard-card contract (total_cases, open_cases, resolved_cases,
    investigating_cases, critical_cases). The dashboard previously rendered
    "0/0/0" because only the legacy fields existed — this closes that gap.
    """
    summary, total_cases, open_cases, investigating_cases, resolved_cases, critical_cases, oldest = await asyncio.gather(
        repo.get_reconciliation_summary(tenant_id),
        db[COLL_RECONCILIATION_CASES].count_documents({"tenant_id": tenant_id}),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id, "status": "open"},
        ),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id, "status": "investigating"},
        ),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id, "status": {"$in": ["resolved", "auto_resolved"]}},
        ),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id,
             "status": {"$in": ["open", "investigating"]},
             "severity": "critical"},
        ),
        db[COLL_RECONCILIATION_CASES].find_one(
            {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}},
            _NO_ID,
            sort=[("created_at", 1)],
        ),
    )

    oldest_age_hours = None
    if oldest and oldest.get("created_at"):
        try:
            created = datetime.fromisoformat(
                oldest["created_at"].replace("Z", "+00:00"),
            )
            oldest_age_hours = round(
                (datetime.now(UTC) - created).total_seconds() / 3600, 1,
            )
        except (ValueError, AttributeError):
            oldest_age_hours = None

    return {
        **summary,
        "total_cases": total_cases,
        "open_cases": open_cases + investigating_cases,
        "investigating_cases": investigating_cases,
        "resolved_cases": resolved_cases,
        "critical_cases": critical_cases,
        "oldest_unresolved_age_hours": oldest_age_hours,
    }


@router.get("/metrics/reconciliation")
async def reconciliation_metrics(
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Reconciliation case metrics — open/critical/resolved counts + oldest age."""
    return await _recon_metrics_cached(current_user.tenant_id, _nocache=nocache)


# ══════════════════════════════════════════════════════════════════════
# 6. PROVIDER CAPABILITY MATRIX (cached, static-ish)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=300, key_prefix="lockdown_provider_capabilities")
async def _capabilities_cached(_nocache: bool = False) -> dict:
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


@router.get("/providers/capabilities")
async def provider_capabilities(
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Provider capability matrix — behavioral contract."""
    return await _capabilities_cached(_nocache=nocache)


# ══════════════════════════════════════════════════════════════════════
# 7. RECONCILIATION TRUTH TABLE (cached, fully static)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=300, key_prefix="lockdown_truth_table")
async def _truth_table_cached(_nocache: bool = False) -> dict:
    return {"truth_table": get_truth_table_summary()}


@router.get("/reconciliation/truth-table")
async def truth_table(
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Truth table: gold source + resolution policy per drift type."""
    return await _truth_table_cached(_nocache=nocache)


# ══════════════════════════════════════════════════════════════════════
# 8. SYSTEM LOCKDOWN STATUS (cached, parallelized)
# ══════════════════════════════════════════════════════════════════════

@cached(ttl=30, key_prefix="lockdown_status")
async def _status_cached(tenant_id: str, _nocache: bool = False) -> dict:
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    # 6 sequential count_documents → asyncio.gather (one round-trip equivalent)
    (
        total_events,
        failed_events,
        open_cases,
        critical_cases,
        room_maps,
        broken_room_maps,
        unreconciled,
    ) = await asyncio.gather(
        db[COLL_RAW_CHANNEL_EVENTS].count_documents(
            {"tenant_id": tenant_id, "received_at": {"$gte": since_24h}},
        ),
        db[COLL_RAW_CHANNEL_EVENTS].count_documents(
            {"tenant_id": tenant_id, "received_at": {"$gte": since_24h}, "processing_status": "failed"},
        ),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}},
        ),
        db[COLL_RECONCILIATION_CASES].count_documents(
            {"tenant_id": tenant_id, "status": "open", "severity": "critical"},
        ),
        db[COLL_ROOM_MAPPINGS].count_documents(
            {"tenant_id": tenant_id, "is_active": True},
        ),
        db[COLL_ROOM_MAPPINGS].count_documents(
            {"tenant_id": tenant_id, "is_active": True, "pms_room_type_id": {"$in": [None, ""]}},
        ),
        db[COLL_RESERVATION_LINEAGE].count_documents(
            {"tenant_id": tenant_id, "reconciled": False},
        ),
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


@router.get("/status")
async def lockdown_status(
    nocache: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Overall system lockdown status — ingest, mapping, reconciliation health."""
    return await _status_cached(current_user.tenant_id, _nocache=nocache)
