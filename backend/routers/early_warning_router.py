"""
Early Warning Router — Predictive Alerting API Endpoints
=========================================================

Sprint 4: Trend-based early warning system endpoints.

Provides:
  - GET /api/ops-events/early-warnings — Get all active warnings
  - GET /api/ops-events/early-warnings/summary — Dashboard summary
  - GET /api/ops-events/early-warnings/connector/{connector_id} — Connector-specific warnings
  - GET /api/ops-events/early-warnings/trends — Trend data for sparklines
  - POST /api/ops-events/early-warnings/engine/start — Start background engine
  - POST /api/ops-events/early-warnings/engine/stop — Stop background engine
  - GET /api/ops-events/early-warnings/engine/status — Engine status
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW
from routers.early_warning_engine import (
    analyze_connector_warnings,
    emit_warning_events,
    generate_all_warnings,
    get_backlog_trend,
    get_dlq_trend,
    get_early_warning_engine,
    get_failure_rate_trend,
    get_health_score_trend,
    get_staleness_data,
    get_throttle_trend,
)

logger = logging.getLogger("early_warning_router")

router = APIRouter(prefix="/api/ops-events/early-warnings", tags=["Early Warning & Predictive"])


def _get_tenant(user: User) -> str:
    return user.tenant_id


# ══════════════════════════════════════════════════════════════════════
# 1. Get All Early Warnings
# ══════════════════════════════════════════════════════════════════════

@router.get("")
async def get_early_warnings(
    emit_events: bool = Query(False, description="Emit ops events for warnings"),
    min_confidence: int = Query(50, ge=0, le=100, description="Minimum confidence filter"),
    current_user: User = Depends(get_current_user),
):
    """Tüm erken uyarıları getir.

    Her uyarı için:
    - warning_type: Uyarı tipi
    - provider: Etkilenen kanal
    - confidence: Güven skoru (0-100)
    - reason: Uyarı nedeni (Türkçe)
    - recommended_action: Önerilen aksiyon
    - impacted_scope: Etki alanı
    - trend_data: Trend verileri
    """
    tenant_id = _get_tenant(current_user)

    try:
        warnings = await generate_all_warnings(tenant_id)

        # Filter by confidence
        filtered = [w for w in warnings if w["confidence"] >= min_confidence]

        # Emit events if requested
        emitted_count = 0
        if emit_events and filtered:
            emitted_count = await emit_warning_events(tenant_id, filtered)

        # Group by severity
        critical = [w for w in filtered if w["severity"] == "critical"]
        warning_level = [w for w in filtered if w["severity"] == "warning"]
        info = [w for w in filtered if w["severity"] == "info"]

        return {
            "warnings": filtered,
            "total": len(filtered),
            "by_severity": {
                "critical": len(critical),
                "warning": len(warning_level),
                "info": len(info),
            },
            "events_emitted": emitted_count,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Failed to generate warnings: %s", exc)
        raise HTTPException(status_code=500, detail=f"Warning generation error: {exc}")


# ══════════════════════════════════════════════════════════════════════
# 2. Dashboard Summary (for UI card)
# ══════════════════════════════════════════════════════════════════════

@router.get("/summary")
async def get_early_warnings_summary(
    current_user: User = Depends(get_current_user),
):
    """Erken uyarı özeti — Dashboard kartı için optimize edilmiş.

    Returns:
    - warning_count: Toplam uyarı sayısı
    - critical_count: Kritik uyarı sayısı
    - top_warnings: En yüksek güvenli uyarılar (max 5)
    - connectors_at_risk: Risk altındaki connector'lar
    - system_health_indicator: Genel sistem durumu
    """
    tenant_id = _get_tenant(current_user)

    try:
        warnings = await generate_all_warnings(tenant_id)

        # Get only actionable warnings (confidence >= 50)
        actionable = [w for w in warnings if w["confidence"] >= 50]

        critical = [w for w in actionable if w["severity"] == "critical"]
        warning_level = [w for w in actionable if w["severity"] == "warning"]

        # Get unique connectors at risk
        connectors_at_risk = list({
            w["provider"] for w in actionable
            if w["provider"] and w["provider"] != "system"
        })

        # Calculate system health indicator
        if len(critical) > 0:
            system_health = "critical"
        elif len(warning_level) > 2:
            system_health = "degraded"
        elif len(actionable) > 0:
            system_health = "attention"
        else:
            system_health = "healthy"

        # Top warnings (sorted by confidence)
        top_warnings = actionable[:5]

        return {
            "warning_count": len(actionable),
            "critical_count": len(critical),
            "warning_count_warning": len(warning_level),
            "top_warnings": top_warnings,
            "connectors_at_risk": connectors_at_risk,
            "connectors_at_risk_count": len(connectors_at_risk),
            "system_health_indicator": system_health,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Failed to generate summary: %s", exc)
        return {
            "warning_count": 0,
            "critical_count": 0,
            "warning_count_warning": 0,
            "top_warnings": [],
            "connectors_at_risk": [],
            "connectors_at_risk_count": 0,
            "system_health_indicator": "unknown",
            "error": str(exc),
            "generated_at": datetime.now(UTC).isoformat(),
        }


# ══════════════════════════════════════════════════════════════════════
# 3. Connector-Specific Warnings
# ══════════════════════════════════════════════════════════════════════

@router.get("/connector/{connector_id}")
async def get_connector_warnings(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Belirli bir connector için erken uyarıları ve trend verilerini getir."""
    tenant_id = _get_tenant(current_user)

    # Get connector info
    connector = await db.cm_connectors.find_one(
        {"tenant_id": tenant_id, "id": connector_id},
        {"_id": 0}
    )

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    provider = connector.get("provider", "unknown")

    # Get warnings for this connector
    warnings = await analyze_connector_warnings(tenant_id, connector_id, provider)

    # Get detailed trend data
    failure_trend = await get_failure_rate_trend(tenant_id, connector_id, provider)
    staleness_data = await get_staleness_data(tenant_id, connector_id)
    health_trend = await get_health_score_trend(tenant_id, connector_id, provider)
    throttle_trend = await get_throttle_trend(tenant_id, provider)

    return {
        "connector_id": connector_id,
        "provider": provider,
        "property_name": connector.get("property_name", ""),
        "status": connector.get("status", "unknown"),
        "warnings": [w.to_dict() for w in warnings],
        "warning_count": len(warnings),
        "trends": {
            "failure_rate": failure_trend,
            "staleness": staleness_data,
            "health_score": health_trend,
            "throttle": throttle_trend,
        },
        "risk_assessment": {
            "overall_risk": "high" if any(w.severity == "critical" for w in warnings) else (
                "medium" if any(w.severity == "warning" for w in warnings) else "low"
            ),
            "max_confidence": max([w.confidence for w in warnings], default=0),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
# 4. Trend Data for Sparklines
# ══════════════════════════════════════════════════════════════════════

@router.get("/trends")
async def get_warning_trends(
    hours: int = Query(6, ge=1, le=24, description="Hours of trend data"),
    current_user: User = Depends(get_current_user),
):
    """Trend verileri — UI sparkline'lar için.

    Returns time-series data for:
    - failure_rate: Hata oranı trendi
    - dlq_count: DLQ sayısı trendi
    - health_scores: Connector health score'ları
    """
    tenant_id = _get_tenant(current_user)
    now = datetime.now(UTC)

    # Get connectors
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "provider": 1}
    ).to_list(50)

    # Build time buckets (1 hour each)
    buckets = []
    for h in range(hours, 0, -1):
        bucket_start = (now - timedelta(hours=h)).isoformat()
        bucket_end = (now - timedelta(hours=h-1)).isoformat()
        buckets.append({
            "start": bucket_start,
            "end": bucket_end,
            "label": f"{h}h ago",
        })

    # Aggregate failure rates per bucket
    failure_rate_series = []
    for bucket in buckets:
        total = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "recorded_at": {"$gte": bucket["start"], "$lt": bucket["end"]},
        })
        failed = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "success": False,
            "recorded_at": {"$gte": bucket["start"], "$lt": bucket["end"]},
        })
        rate = round(failed / max(total, 1) * 100, 1)
        failure_rate_series.append({
            "label": bucket["label"],
            "value": rate,
            "total": total,
            "failed": failed,
        })

    # Get current DLQ and backlog
    dlq_trend = await get_dlq_trend(tenant_id)
    backlog_trend = await get_backlog_trend(tenant_id)

    # Get connector health scores
    connector_scores = []
    for conn in connectors[:10]:  # Limit to 10 connectors
        health = await get_health_score_trend(tenant_id, conn["id"], conn.get("provider", ""))
        connector_scores.append({
            "connector_id": conn["id"],
            "provider": conn.get("provider", "unknown"),
            "current_score": health["current_score"],
            "trend_direction": health["trend_direction"],
            "score_delta": health["score_delta"],
        })

    return {
        "failure_rate_series": failure_rate_series,
        "dlq_current": dlq_trend["pending_count"],
        "dlq_recent_additions": dlq_trend["recent_additions"],
        "backlog_current": backlog_trend["current_backlog"],
        "connector_health_scores": connector_scores,
        "period_hours": hours,
        "generated_at": now.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
# 5. Recent Warning Events (from ops_events)
# ══════════════════════════════════════════════════════════════════════

@router.get("/recent-events")
async def get_recent_warning_events(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Son erken uyarı event'lerini getir (ops_events'tan)."""
    tenant_id = _get_tenant(current_user)
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    events = await db.ops_events.find(
        {
            "tenant_id": tenant_id,
            "event_type": {"$regex": "^predictive\\.warning\\."},
            "created_at": {"$gte": since_24h},
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Group by warning type
    by_type: dict[str, int] = {}
    for ev in events:
        wtype = ev.get("event_type", "unknown")
        by_type[wtype] = by_type.get(wtype, 0) + 1

    return {
        "events": events,
        "total": len(events),
        "by_type": by_type,
        "period": "24h",
    }


# ══════════════════════════════════════════════════════════════════════
# 6. Engine Control
# ══════════════════════════════════════════════════════════════════════

@router.get("/engine/status")
async def get_engine_status(
    current_user: User = Depends(get_current_user),
):
    """Early Warning Engine durumunu getir."""
    engine = get_early_warning_engine()

    return {
        "running": engine._running,
        "check_interval_seconds": engine._check_interval,
        "warning_types": [
            "predictive.warning.degradation_likely",
            "predictive.warning.failure_rate_rising",
            "predictive.warning.backlog_growth",
            "predictive.warning.dlq_spike",
            "predictive.warning.throttle_risk",
            "predictive.warning.staleness_risk",
            "predictive.warning.recovery_expected",
        ],
    }


@router.post("/engine/start")
async def start_warning_engine(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Early Warning Engine'i başlat."""
    engine = get_early_warning_engine()
    await engine.start()

    return {"ok": True, "message": "Early Warning Engine started"}


@router.post("/engine/stop")
async def stop_warning_engine(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Early Warning Engine'i durdur."""
    engine = get_early_warning_engine()
    await engine.stop()

    return {"ok": True, "message": "Early Warning Engine stopped"}


# ══════════════════════════════════════════════════════════════════════
# 7. Diagnostic: Force Generate & Emit
# ══════════════════════════════════════════════════════════════════════

@router.post("/force-check")
async def force_warning_check(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Manuel olarak uyarı kontrolü tetikle ve event'leri emit et."""
    tenant_id = _get_tenant(current_user)

    try:
        warnings = await generate_all_warnings(tenant_id)
        emitted = await emit_warning_events(tenant_id, warnings)

        return {
            "ok": True,
            "warnings_generated": len(warnings),
            "events_emitted": emitted,
            "warnings": warnings,
        }
    except Exception as exc:
        logger.error("Force check failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Check error: {exc}")
