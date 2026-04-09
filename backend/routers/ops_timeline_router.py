"""
Operational Timeline & Incident Correlation Router
===================================================

Sprint 2 P0: Correlation timeline + drilldown

Provides endpoints for:
  - Event timeline by correlation_id
  - Incident summary and root cause analysis
  - Connector health aggregates with standardized contract
  - Prioritized incident feed
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("ops_timeline")

router = APIRouter(prefix="/api/ops-events", tags=["Ops Timeline & Incidents"])


def _get_tenant(user: User) -> str:
    return user.tenant_id


# ══════════════════════════════════════════════════════════════════════
# 1. Correlation Timeline — Full event chain for a single correlation_id
# ══════════════════════════════════════════════════════════════════════

@router.get("/timeline/{correlation_id}")
async def get_event_timeline(
    correlation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Tek bir correlation_id'nin tum yasam dongusu timeline'i.
    
    Webhook → import → push → retry → DLQ/success zincirini gosterir.
    """
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    tenant_id = _get_tenant(current_user)

    # 1. Get all ops_events with this correlation_id
    events = await db.ops_events.find(
        {"tenant_id": tenant_id, "correlation_id": correlation_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    if not events:
        raise HTTPException(status_code=404, detail="Bu correlation_id icin event bulunamadi")

    # 2. Get related delivery record (if webhook)
    delivery = await sysdb.webhook_deliveries.find_one(
        {"tenant_id": tenant_id, "correlation_id": correlation_id},
        {"_id": 0}
    )

    # 3. Get DLQ item if exists
    dlq_item = await sysdb.webhook_dlq.find_one(
        {"tenant_id": tenant_id, "correlation_id": correlation_id},
        {"_id": 0}
    )

    # 4. Analyze timeline
    first_event = events[0]
    last_event = events[-1]
    
    # Determine terminal state
    terminal_states = ["webhook.delivery.succeeded", "webhook.delivery.terminal_failure", 
                       "webhook.delivery.dlq", "push.succeeded", "push.failed_terminal",
                       "import.completed", "import.failed"]
    
    terminal_event = None
    for ev in reversed(events):
        if ev["event_type"] in terminal_states:
            terminal_event = ev
            break

    # Count retry attempts
    retry_count = sum(1 for ev in events if "retry" in ev["event_type"].lower())
    
    # Affected entities
    affected_tenant = first_event.get("tenant_id", "")
    affected_channel = first_event.get("channel", "")
    affected_entity_type = first_event.get("affected_entity_type", "")
    affected_entity_id = first_event.get("affected_entity_id", "")

    # Severity escalation
    severities = [ev.get("severity", "info") for ev in events]
    has_critical = "critical" in severities
    has_warning = "warning" in severities
    max_severity = "critical" if has_critical else ("warning" if has_warning else "info")

    # Check if recovered
    is_recovered = terminal_event and terminal_event["event_type"] in [
        "webhook.delivery.succeeded", "push.succeeded", "import.completed"
    ]
    is_terminal_failure = terminal_event and terminal_event["event_type"] in [
        "webhook.delivery.terminal_failure", "webhook.delivery.dlq", 
        "push.failed_terminal", "import.failed"
    ]

    # Calculate duration
    try:
        start_time = datetime.fromisoformat(first_event["created_at"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(last_event["created_at"].replace("Z", "+00:00"))
        duration_seconds = (end_time - start_time).total_seconds()
    except Exception:
        duration_seconds = 0

    # Last error
    last_error = None
    for ev in reversed(events):
        if ev.get("details", {}).get("last_error"):
            last_error = ev["details"]["last_error"]
            break
        if ev.get("details", {}).get("error"):
            last_error = ev["details"]["error"]
            break

    # Build timeline summary
    timeline_summary = {
        "correlation_id": correlation_id,
        "started_at": first_event["created_at"],
        "ended_at": last_event["created_at"],
        "duration_seconds": round(duration_seconds, 2),
        "event_count": len(events),
        "retry_count": retry_count,
        "max_severity": max_severity,
        "is_recovered": is_recovered,
        "is_terminal_failure": is_terminal_failure,
        "terminal_state": terminal_event["event_type"] if terminal_event else None,
        "last_error": last_error,
        "affected_tenant": affected_tenant,
        "affected_channel": affected_channel,
        "affected_entity_type": affected_entity_type,
        "affected_entity_id": affected_entity_id,
    }

    # Build event timeline with phases
    timeline_phases = []
    for ev in events:
        phase = {
            "event_id": ev.get("id"),
            "event_type": ev.get("event_type"),
            "severity": ev.get("severity"),
            "title": ev.get("title"),
            "timestamp": ev.get("created_at"),
            "details": ev.get("details", {}),
            "channel": ev.get("channel"),
        }
        timeline_phases.append(phase)

    return {
        "summary": timeline_summary,
        "timeline": timeline_phases,
        "delivery": delivery,
        "dlq_item": dlq_item,
    }


# ══════════════════════════════════════════════════════════════════════
# 2. Incident Summary — Quick incident overview by event ID
# ══════════════════════════════════════════════════════════════════════

@router.get("/incident/{event_id}/summary")
async def get_incident_summary(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    """Tek bir ops event'in ozet bilgileri ve baglamli timeline.
    
    Bir satira tiklandiginda drilldown icin kullanilir.
    """
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    tenant_id = _get_tenant(current_user)

    # Get the event
    event = await db.ops_events.find_one(
        {"tenant_id": tenant_id, "id": event_id},
        {"_id": 0}
    )

    if not event:
        raise HTTPException(status_code=404, detail="Event bulunamadi")

    correlation_id = event.get("correlation_id")
    
    # If has correlation_id, get full timeline
    related_events = []
    delivery = None
    dlq_item = None
    
    if correlation_id:
        related_events = await db.ops_events.find(
            {"tenant_id": tenant_id, "correlation_id": correlation_id},
            {"_id": 0}
        ).sort("created_at", 1).to_list(50)

        delivery = await sysdb.webhook_deliveries.find_one(
            {"tenant_id": tenant_id, "correlation_id": correlation_id},
            {"_id": 0}
        )

        dlq_item = await sysdb.webhook_dlq.find_one(
            {"tenant_id": tenant_id, "correlation_id": correlation_id},
            {"_id": 0}
        )

    # Check if notification was sent
    notification = await db.notifications.find_one(
        {"tenant_id": tenant_id, "correlation_id": correlation_id} if correlation_id else {"id": "nonexistent"},
        {"_id": 0, "id": 1, "read": 1, "created_at": 1}
    )

    # Determine impact
    impact = {
        "affected_tenant": event.get("tenant_id"),
        "affected_channel": event.get("channel"),
        "affected_entity_type": event.get("affected_entity_type"),
        "affected_entity_id": event.get("affected_entity_id"),
        "notification_sent": notification is not None,
        "notification_read": notification.get("read", False) if notification else False,
    }

    return {
        "event": event,
        "correlation_id": correlation_id,
        "related_events_count": len(related_events),
        "related_events": related_events[:10],  # First 10 for quick view
        "delivery": delivery,
        "dlq_item": dlq_item,
        "impact": impact,
    }


# ══════════════════════════════════════════════════════════════════════
# 3. Prioritized Incident Feed — Sorted by priority for ops dashboard
# ══════════════════════════════════════════════════════════════════════

@router.get("/incidents/prioritized")
async def get_prioritized_incidents(
    limit: int = Query(50, ge=1, le=200),
    include_resolved: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    """Onceliklendirmis incident listesi.
    
    Oncelik sirasi:
    1. terminal DLQ (critical)
    2. active throttle affecting pushes (critical)
    3. connector unhealthy (warning)
    4. repeated retry bursts (warning)
    5. info-level recovered events (info)
    """
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    tenant_id = _get_tenant(current_user)
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    # Priority 1: Terminal DLQ items (pending)
    dlq_pending = await sysdb.webhook_dlq.find(
        {"tenant_id": tenant_id, "status": "pending"},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    # Priority 2: Active rate limit / throttle events
    throttle_events = await db.ops_events.find(
        {
            "tenant_id": tenant_id,
            "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
            "created_at": {"$gte": since_24h},
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Priority 3: Terminal failures (last 24h)
    terminal_failures = await db.ops_events.find(
        {
            "tenant_id": tenant_id,
            "event_type": {"$in": [
                "webhook.delivery.terminal_failure",
                "push.failed_terminal",
                "import.failed"
            ]},
            "created_at": {"$gte": since_24h},
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    # Priority 4: Warning events (retrying)
    warning_events = await db.ops_events.find(
        {
            "tenant_id": tenant_id,
            "severity": "warning",
            "created_at": {"$gte": since_24h},
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    # Priority 5: Success/recovered (optional)
    recovered_events = []
    if include_resolved:
        recovered_events = await db.ops_events.find(
            {
                "tenant_id": tenant_id,
                "event_type": {"$in": [
                    "webhook.delivery.succeeded",
                    "push.succeeded",
                    "import.completed"
                ]},
                "created_at": {"$gte": since_24h},
            },
            {"_id": 0}
        ).sort("created_at", -1).limit(20).to_list(20)

    # Build prioritized feed
    prioritized = []

    # Add DLQ items as priority 1
    for item in dlq_pending:
        prioritized.append({
            "priority": 1,
            "priority_label": "KRITIK - DLQ",
            "type": "dlq",
            "id": item.get("id"),
            "correlation_id": item.get("correlation_id"),
            "title": f"DLQ: {item.get('event')}",
            "description": item.get("last_error", ""),
            "url": item.get("url"),
            "created_at": item.get("created_at"),
            "status": item.get("status"),
            "attempt_count": item.get("attempt_count"),
            "actionable": True,
            "action_type": "retry",
        })

    # Add throttle events as priority 2
    for ev in throttle_events:
        prioritized.append({
            "priority": 2,
            "priority_label": "KRITIK - Rate Limit",
            "type": "ops_event",
            "id": ev.get("id"),
            "correlation_id": ev.get("correlation_id"),
            "title": ev.get("title"),
            "description": f"Kanal: {ev.get('channel', 'N/A')}",
            "event_type": ev.get("event_type"),
            "created_at": ev.get("created_at"),
            "severity": ev.get("severity"),
            "details": ev.get("details", {}),
            "actionable": False,
        })

    # Add terminal failures as priority 3
    for ev in terminal_failures:
        prioritized.append({
            "priority": 3,
            "priority_label": "YUKSEK - Terminal Failure",
            "type": "ops_event",
            "id": ev.get("id"),
            "correlation_id": ev.get("correlation_id"),
            "title": ev.get("title"),
            "description": ev.get("details", {}).get("last_error", ""),
            "event_type": ev.get("event_type"),
            "created_at": ev.get("created_at"),
            "severity": ev.get("severity"),
            "details": ev.get("details", {}),
            "actionable": ev.get("event_type") == "webhook.delivery.terminal_failure",
            "action_type": "inspect",
        })

    # Add warning events as priority 4
    for ev in warning_events:
        # Skip if already added (throttle events)
        if any(p.get("id") == ev.get("id") for p in prioritized):
            continue
        prioritized.append({
            "priority": 4,
            "priority_label": "ORTA - Dikkat",
            "type": "ops_event",
            "id": ev.get("id"),
            "correlation_id": ev.get("correlation_id"),
            "title": ev.get("title"),
            "event_type": ev.get("event_type"),
            "created_at": ev.get("created_at"),
            "severity": ev.get("severity"),
            "details": ev.get("details", {}),
            "actionable": False,
        })

    # Add recovered as priority 5
    for ev in recovered_events:
        prioritized.append({
            "priority": 5,
            "priority_label": "BILGI - Cozuldu",
            "type": "ops_event",
            "id": ev.get("id"),
            "correlation_id": ev.get("correlation_id"),
            "title": ev.get("title"),
            "event_type": ev.get("event_type"),
            "created_at": ev.get("created_at"),
            "severity": ev.get("severity"),
            "actionable": False,
        })

    # Sort by priority then by created_at desc
    prioritized.sort(key=lambda x: (x["priority"], x.get("created_at", "")), reverse=False)
    # Reverse created_at within same priority
    prioritized.sort(key=lambda x: x["priority"])

    return {
        "incidents": prioritized[:limit],
        "counts": {
            "dlq_pending": len(dlq_pending),
            "throttle_active": len(throttle_events),
            "terminal_failures": len(terminal_failures),
            "warnings": len(warning_events),
            "resolved": len(recovered_events) if include_resolved else 0,
            "total": len(prioritized),
        },
    }


# ══════════════════════════════════════════════════════════════════════
# 4. Unified Connector Health Contract
# ══════════════════════════════════════════════════════════════════════

@router.get("/connectors/health")
async def get_connectors_health(
    current_user: User = Depends(get_current_user),
):
    """Tum connector'larin standardize edilmis health durumu.
    
    Her connector icin ayni schema:
    - provider
    - status (healthy/degraded/critical)
    - last_success_at
    - last_failure_at
    - failure_rate_1h
    - retry_backlog
    - dlq_count
    - throttle_active
    - next_available_at
    - health_score (0-100)
    """
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    tenant_id = _get_tenant(current_user)
    
    now = datetime.now(UTC)
    since_1h = (now - timedelta(hours=1)).isoformat()

    # Get all connectors
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id},
        {"_id": 0}
    ).to_list(50)

    health_reports = []

    for conn in connectors:
        provider = conn.get("provider", "unknown")
        connector_id = conn.get("id", "")
        property_name = conn.get("property_name", "")

        # Last success
        last_success = await db.cm_rate_push_metrics.find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id, "success": True},
            {"_id": 0},
            sort=[("recorded_at", -1)]
        )
        last_success_at = last_success.get("recorded_at") if last_success else None

        # Last failure
        last_failure = await db.cm_rate_push_metrics.find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id, "success": False},
            {"_id": 0},
            sort=[("recorded_at", -1)]
        )
        last_failure_at = last_failure.get("recorded_at") if last_failure else None

        # Failure rate (1h)
        total_1h = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "recorded_at": {"$gte": since_1h},
        })
        failed_1h = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": False,
            "recorded_at": {"$gte": since_1h},
        })
        failure_rate_1h = round(failed_1h / max(total_1h, 1) * 100, 1)

        # Retry backlog (deliveries in retrying status)
        retry_backlog = await sysdb.webhook_deliveries.count_documents({
            "tenant_id": tenant_id,
            "status": "retrying",
        })

        # DLQ count (pending)
        dlq_count = await sysdb.webhook_dlq.count_documents({
            "tenant_id": tenant_id,
            "status": "pending",
        })

        # Throttle status
        throttle_events = await db.ops_events.count_documents({
            "tenant_id": tenant_id,
            "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
            "channel": {"$regex": provider, "$options": "i"},
            "created_at": {"$gte": since_1h},
        })
        throttle_active = throttle_events > 0

        # Calculate health score (0-100)
        health_score = 100
        
        # Deduct for failure rate
        if failure_rate_1h > 50:
            health_score -= 40
        elif failure_rate_1h > 20:
            health_score -= 20
        elif failure_rate_1h > 5:
            health_score -= 10

        # Deduct for DLQ
        if dlq_count > 10:
            health_score -= 30
        elif dlq_count > 5:
            health_score -= 20
        elif dlq_count > 0:
            health_score -= 10

        # Deduct for throttle
        if throttle_active:
            health_score -= 15

        # Deduct for retry backlog
        if retry_backlog > 20:
            health_score -= 15
        elif retry_backlog > 5:
            health_score -= 5

        # Deduct for staleness (no success in 1h)
        if last_success_at:
            try:
                last_ts = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
                hours_since = (now - last_ts).total_seconds() / 3600
                if hours_since > 24:
                    health_score -= 20
                elif hours_since > 6:
                    health_score -= 10
                elif hours_since > 1:
                    health_score -= 5
            except Exception:
                pass

        health_score = max(0, health_score)

        # Determine status
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "critical"

        # Next available (for throttled connectors)
        next_available_at = None
        if throttle_active:
            # Get last throttle event details
            last_throttle = await db.ops_events.find_one(
                {
                    "tenant_id": tenant_id,
                    "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
                    "channel": {"$regex": provider, "$options": "i"},
                },
                {"_id": 0},
                sort=[("created_at", -1)]
            )
            if last_throttle:
                next_available_at = last_throttle.get("details", {}).get("next_available_at") or \
                                    last_throttle.get("details", {}).get("cooldown_until")

        health_reports.append({
            "connector_id": connector_id,
            "provider": provider,
            "property_name": property_name,
            "status": status,
            "health_score": health_score,
            "last_success_at": last_success_at,
            "last_failure_at": last_failure_at,
            "failure_rate_1h": failure_rate_1h,
            "retry_backlog": retry_backlog,
            "dlq_count": dlq_count,
            "throttle_active": throttle_active,
            "next_available_at": next_available_at,
            "metrics_1h": {
                "total_operations": total_1h,
                "failed_operations": failed_1h,
                "success_rate": round(100 - failure_rate_1h, 1),
            },
        })

    # Sort by health_score ascending (worst first)
    health_reports.sort(key=lambda x: x["health_score"])

    # Summary
    healthy_count = sum(1 for h in health_reports if h["status"] == "healthy")
    degraded_count = sum(1 for h in health_reports if h["status"] == "degraded")
    critical_count = sum(1 for h in health_reports if h["status"] == "critical")

    return {
        "connectors": health_reports,
        "summary": {
            "total": len(health_reports),
            "healthy": healthy_count,
            "degraded": degraded_count,
            "critical": critical_count,
            "overall_health": "critical" if critical_count > 0 else ("degraded" if degraded_count > 0 else "healthy"),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
# 5. Impacted Tenants/Channels Filter
# ══════════════════════════════════════════════════════════════════════

@router.get("/impact-analysis")
async def get_impact_analysis(
    since_hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
):
    """Belirtilen zaman diliminde etkilenen tenant ve kanallari analiz et."""
    tenant_id = _get_tenant(current_user)
    since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

    # Get all critical/warning events
    events = await db.ops_events.find(
        {
            "tenant_id": tenant_id,
            "severity": {"$in": ["critical", "warning"]},
            "created_at": {"$gte": since},
        },
        {"_id": 0}
    ).to_list(500)

    # Aggregate by channel
    channel_impact = {}
    for ev in events:
        ch = ev.get("channel", "unknown")
        if ch not in channel_impact:
            channel_impact[ch] = {
                "channel": ch,
                "critical_count": 0,
                "warning_count": 0,
                "event_types": set(),
                "first_event_at": ev.get("created_at"),
                "last_event_at": ev.get("created_at"),
            }
        
        if ev.get("severity") == "critical":
            channel_impact[ch]["critical_count"] += 1
        else:
            channel_impact[ch]["warning_count"] += 1
        
        channel_impact[ch]["event_types"].add(ev.get("event_type"))
        channel_impact[ch]["last_event_at"] = ev.get("created_at")

    # Convert to list and serialize
    impact_list = []
    for ch, data in channel_impact.items():
        data["event_types"] = list(data["event_types"])
        data["total_events"] = data["critical_count"] + data["warning_count"]
        impact_list.append(data)

    # Sort by total events desc
    impact_list.sort(key=lambda x: x["total_events"], reverse=True)

    return {
        "analysis_period_hours": since_hours,
        "impacted_channels": impact_list,
        "total_channels_impacted": len(impact_list),
        "total_critical_events": sum(c["critical_count"] for c in impact_list),
        "total_warning_events": sum(c["warning_count"] for c in impact_list),
    }



# ══════════════════════════════════════════════════════════════════════
# 6. Auto-Remediation Control Endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get("/remediation/status")
async def get_remediation_status(
    current_user: User = Depends(get_current_user),
):
    """Auto-remediation engine durumunu goster."""
    from routers.auto_remediation_engine import get_remediation_engine

    engine = get_remediation_engine()
    
    return {
        "engine_running": engine._running,
        "rules": {
            "connector_degradation": {
                "enabled": True,
                "threshold": 3,
                "window_minutes": 10,
            },
            "alert_escalation": {
                "enabled": True,
                "threshold": 5,
                "window_minutes": 10,
            },
            "rate_limit_queueing": {
                "enabled": True,
            },
            "recovery_drain": {
                "enabled": True,
            },
            "dlq_auto_resolve": {
                "enabled": True,
            },
        },
        "cooldowns_active": len(engine._rule_cooldowns),
    }


@router.post("/remediation/start")
async def start_remediation_engine(
    current_user: User = Depends(get_current_user),
):
    """Auto-remediation engine'i baslat."""
    from routers.auto_remediation_engine import get_remediation_engine

    engine = get_remediation_engine()
    await engine.start()
    
    return {"ok": True, "message": "Auto-remediation engine baslatildi"}


@router.post("/remediation/stop")
async def stop_remediation_engine(
    current_user: User = Depends(get_current_user),
):
    """Auto-remediation engine'i durdur."""
    from routers.auto_remediation_engine import get_remediation_engine

    engine = get_remediation_engine()
    await engine.stop()
    
    return {"ok": True, "message": "Auto-remediation engine durduruldu"}


@router.post("/connectors/{connector_id}/recover")
async def recover_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Degraded connector'i manuel olarak recover et."""
    from routers.auto_remediation_engine import manually_recover_connector

    tenant_id = _get_tenant(current_user)
    result = await manually_recover_connector(tenant_id, connector_id)
    
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Recovery basarisiz"))
    
    return result


@router.post("/connectors/{connector_id}/degrade")
async def degrade_connector(
    connector_id: str,
    reason: str = Query("Manuel degrade", description="Degrade nedeni"),
    current_user: User = Depends(get_current_user),
):
    """Connector'i manuel olarak degrade et."""
    from routers.auto_remediation_engine import manually_degrade_connector

    tenant_id = _get_tenant(current_user)
    result = await manually_degrade_connector(tenant_id, connector_id, reason)
    
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Degrade basarisiz"))
    
    return result
