"""
Runtime Infrastructure Router — Production runtime status for all platform components.
Redis/Event Bus, Messaging Providers, Persistence Health, Alerts, Observability.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/runtime", tags=["runtime-infrastructure"])


# ── Event Bus Runtime ──

@router.get("/event-bus/status")
async def get_event_bus_runtime(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    status = await event_bus.get_status()
    metrics = await event_bus.get_metrics()
    return {"status": status, "metrics": metrics}


@router.get("/event-bus/delivery-metrics")
async def get_event_bus_delivery_metrics(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    metrics = await event_bus.get_metrics()
    return {
        "mode": metrics.get("mode"),
        "total_published": metrics.get("total_published"),
        "total_delivered": metrics.get("total_delivered"),
        "total_dropped": metrics.get("total_dropped"),
        "total_errors": metrics.get("total_errors"),
        "total_fallback_used": metrics.get("total_fallback_used"),
        "events_last_hour": metrics.get("events_last_hour"),
        "redis_delivery_metrics": metrics.get("redis_delivery_metrics"),
    }


# ── Messaging Provider Runtime ──

@router.get("/messaging/status")
async def get_messaging_runtime(current_user: User = Depends(get_current_user)):
    from modules.messaging.service import MessagingService
    from server import db
    svc = MessagingService(db)
    providers = await svc.check_all_providers(current_user.tenant_id)
    runtime = svc.get_runtime_status()
    retry_queue = await svc.get_retry_queue_size(current_user.tenant_id)
    return {
        "providers": providers,
        "runtime": runtime,
        "retry_queue_size": retry_queue,
    }


@router.get("/messaging/delivery-summary")
async def get_messaging_delivery_summary(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
):
    from modules.messaging.service import MessagingService
    from server import db
    svc = MessagingService(db)
    return await svc.get_delivery_metrics(current_user.tenant_id, days)


# ── Persistence Health ──

@router.get("/persistence/health")
async def get_persistence_health(current_user: User = Depends(get_current_user)):
    from core.database import db
    collections_to_check = [
        "event_bus_log", "messaging_delivery_logs", "observability_traces",
        "observability_metrics", "observability_errors", "alert_history",
        "messaging_provider_configs", "messaging_templates",
        "pipeline_runs", "analytics_export_history",
    ]
    results = {}
    for coll_name in collections_to_check:
        try:
            count = await db[coll_name].estimated_document_count()
            results[coll_name] = {"status": "healthy", "document_count": count}
        except Exception as e:
            results[coll_name] = {"status": "error", "error": str(e)[:200]}

    healthy = sum(1 for v in results.values() if v["status"] == "healthy")
    return {
        "overall": "healthy" if healthy == len(results) else "degraded",
        "collections": results,
        "healthy_count": healthy,
        "total_count": len(results),
    }


# ── Alerting ──

@router.get("/alerts/evaluate")
async def evaluate_alerts(current_user: User = Depends(get_current_user)):
    from modules.observability.alerting_engine import alert_engine
    alerts = await alert_engine.evaluate_all()
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/alerts/candidates")
async def get_alert_candidates(current_user: User = Depends(get_current_user)):
    from modules.observability.alerting_engine import alert_engine
    return await alert_engine.get_alert_candidates()


@router.get("/alerts/history")
async def get_alert_history(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    from modules.observability.alerting_engine import alert_engine
    return await alert_engine.get_alert_history(hours, limit)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, current_user: User = Depends(get_current_user)):
    from modules.observability.alerting_engine import alert_engine
    return await alert_engine.acknowledge_alert(alert_id, current_user.id)


@router.get("/alerts/engine-status")
async def get_alert_engine_status(current_user: User = Depends(get_current_user)):
    from modules.observability.alerting_engine import alert_engine
    return alert_engine.get_engine_status()


# ── Observability Summary ──

@router.get("/observability/summary")
async def get_observability_summary(current_user: User = Depends(get_current_user)):
    from modules.observability.metrics_collector import metrics
    from modules.observability.distributed_tracing import tracing
    from modules.observability.error_tracker import error_tracker
    from modules.observability.service_health import service_health

    dashboard_metrics = metrics.get_dashboard_metrics()
    trace_summary = await tracing.get_trace_summary(hours=1)
    error_summary = await error_tracker.get_error_summary(hours=1)
    health = await service_health.check_all_services()

    return {
        "metrics": dashboard_metrics,
        "traces": trace_summary,
        "errors": error_summary,
        "health": health,
    }


# ── Infrastructure Overview ──

@router.get("/overview")
async def get_infrastructure_overview(current_user: User = Depends(get_current_user)):
    """Single endpoint returning full runtime infrastructure status."""
    from modules.event_bus.abstraction import event_bus
    from modules.observability.alerting_engine import alert_engine

    bus_status = await event_bus.get_status()
    bus_metrics = await event_bus.get_metrics()

    # Alerts
    alert_candidates = await alert_engine.get_alert_candidates()

    # DB health
    try:
        from core.database import db as dbconn
        await dbconn.command("ping")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return {
        "event_bus": {
            "mode": bus_status.get("mode"),
            "status": bus_status.get("backend_status"),
            "redis_configured": bus_status.get("redis_configured", False),
            "active_sessions": bus_status.get("total_sessions", 0),
        },
        "database": {"status": db_status},
        "alerts": {
            "unacknowledged_count": len(alert_candidates),
            "recent": alert_candidates[:5],
        },
        "event_metrics": {
            "published": bus_metrics.get("total_published", 0),
            "delivered": bus_metrics.get("total_delivered", 0),
            "dropped": bus_metrics.get("total_dropped", 0),
            "events_last_hour": bus_metrics.get("events_last_hour", 0),
        },
    }
