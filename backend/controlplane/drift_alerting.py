"""
Drift Threshold Alerting — Inventory Drift Alert Engine
=========================================================
Transforms the Ops screen from passive visibility to active intervention.

Thresholds:
  - warning:  1+ drift record in 15 min window  → dashboard only
  - critical: 3+ room-night drift in 15 min window → ALERT_WEBHOOK_URL
  - severe:   drift persists after reconciliation → ALERT_WEBHOOK_URL + ESCALATION_WEBHOOK_URL

Alert payload:
  tenant, property, provider, drift_count, drift_nights,
  drift_or_stale, last_reconciliation_result, runbook_link

Notification routing (config-driven, no-op if URLs absent):
  warning  → cp_drift_alerts + log only
  critical → cp_drift_alerts + log + ALERT_WEBHOOK_URL
  severe   → cp_drift_alerts + log + ALERT_WEBHOOK_URL + ESCALATION_WEBHOOK_URL + auto-action
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.database import db

logger = logging.getLogger("controlplane.drift_alerting")

COLL_DRIFT_ALERTS = "cp_drift_alerts"
COLL_DRIFT_EVAL_LOG = "cp_drift_eval_log"

EVALUATION_WINDOW_MINUTES = 15
COOLDOWN_MINUTES = 15

THRESHOLDS = {
    "warning": {"drift_records": 1, "drift_nights": 0},
    "critical": {"drift_records": 0, "drift_nights": 3},
    "severe": {"post_recon_drift": True},
}

# Notification routing matrix
NOTIFICATION_ROUTING = {
    "warning": {"dashboard": True, "webhook": False, "escalation": False},
    "critical": {"dashboard": True, "webhook": True, "escalation": False},
    "severe": {"dashboard": True, "webhook": True, "escalation": True},
}

RUNBOOK_LINK = "/api/ops/runbooks/inventory_drift_detected"


async def evaluate_drift_alerts(
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate current inventory state and fire drift alerts if thresholds are breached.

    Returns: evaluation result with any fired alerts.
    """
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=EVALUATION_WINDOW_MINUTES)).isoformat()

    # Auto-detect tenant if not provided
    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        return {"evaluated": False, "reason": "no_tenant", "alerts_fired": []}

    # Gather drift evidence from multiple sources
    drift_evidence = await _collect_drift_evidence(tenant_id, window_start, now)
    alignment_state = await _get_current_alignment(tenant_id)
    recon_state = await _get_last_reconciliation(tenant_id)

    fired_alerts: List[Dict[str, Any]] = []

    # Check SEVERE first: drift persists after reconciliation
    if drift_evidence["post_recon_drift"]:
        alert = await _fire_drift_alert(
            severity="severe",
            tenant_id=tenant_id,
            evidence=drift_evidence,
            alignment=alignment_state,
            recon=recon_state,
            reason="Drift persists after reconciliation — manual intervention required",
            now=now,
        )
        if alert:
            fired_alerts.append(alert)

    # Check CRITICAL: 3+ room-night drift in window
    elif drift_evidence["total_drift_nights"] >= THRESHOLDS["critical"]["drift_nights"]:
        alert = await _fire_drift_alert(
            severity="critical",
            tenant_id=tenant_id,
            evidence=drift_evidence,
            alignment=alignment_state,
            recon=recon_state,
            reason=f"{drift_evidence['total_drift_nights']} room-night drift in {EVALUATION_WINDOW_MINUTES} min window",
            now=now,
        )
        if alert:
            fired_alerts.append(alert)

    # Check WARNING: 1+ drift record in window
    elif drift_evidence["total_drift_records"] >= THRESHOLDS["warning"]["drift_records"]:
        alert = await _fire_drift_alert(
            severity="warning",
            tenant_id=tenant_id,
            evidence=drift_evidence,
            alignment=alignment_state,
            recon=recon_state,
            reason=f"{drift_evidence['total_drift_records']} drift record(s) in {EVALUATION_WINDOW_MINUTES} min window",
            now=now,
        )
        if alert:
            fired_alerts.append(alert)

    # Log evaluation
    eval_record = {
        "eval_id": str(uuid4()),
        "tenant_id": tenant_id,
        "evaluated_at": now.isoformat(),
        "window_start": window_start,
        "drift_records": drift_evidence["total_drift_records"],
        "drift_nights": drift_evidence["total_drift_nights"],
        "post_recon_drift": drift_evidence["post_recon_drift"],
        "alignment_status": alignment_state.get("alignment_status", "unknown"),
        "freshness": alignment_state.get("freshness", "unknown"),
        "alerts_fired": len(fired_alerts),
        "alert_severities": [a["severity"] for a in fired_alerts],
    }
    try:
        await db[COLL_DRIFT_EVAL_LOG].insert_one({**eval_record})
    except Exception as e:
        logger.debug("Failed to log drift evaluation: %s", e)

    return {
        "evaluated": True,
        "tenant_id": tenant_id,
        "evaluated_at": now.isoformat(),
        "window_minutes": EVALUATION_WINDOW_MINUTES,
        "evidence": {
            "drift_records": drift_evidence["total_drift_records"],
            "drift_nights": drift_evidence["total_drift_nights"],
            "post_recon_drift": drift_evidence["post_recon_drift"],
            "providers_with_drift": drift_evidence["providers_with_drift"],
        },
        "alignment_status": alignment_state.get("alignment_status", "unknown"),
        "freshness": alignment_state.get("freshness", "unknown"),
        "alerts_fired": fired_alerts,
    }


async def get_drift_alerts(
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Get drift alerts with optional filters."""
    query: Dict[str, Any] = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    if severity:
        query["severity"] = severity
    if acknowledged is not None:
        query["acknowledged"] = acknowledged

    return await db[COLL_DRIFT_ALERTS].find(
        query, {"_id": 0}
    ).sort("fired_at", -1).limit(limit).to_list(limit)


async def acknowledge_drift_alert(alert_id: str, acknowledged_by: str = "operator") -> bool:
    """Acknowledge a drift alert."""
    result = await db[COLL_DRIFT_ALERTS].update_one(
        {"alert_id": alert_id, "acknowledged": False},
        {
            "$set": {
                "acknowledged": True,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                "acknowledged_by": acknowledged_by,
            }
        },
    )
    return result.modified_count > 0


async def get_drift_alert_summary(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Get a quick summary of active drift alerts for the ops dashboard."""
    query: Dict[str, Any] = {"acknowledged": False}
    if tenant_id:
        query["tenant_id"] = tenant_id

    active_alerts = await db[COLL_DRIFT_ALERTS].find(
        query, {"_id": 0}
    ).sort("fired_at", -1).limit(100).to_list(100)

    by_severity = {"warning": 0, "critical": 0, "severe": 0}
    for a in active_alerts:
        sev = a.get("severity", "warning")
        if sev in by_severity:
            by_severity[sev] += 1

    highest = "none"
    if by_severity["severe"] > 0:
        highest = "severe"
    elif by_severity["critical"] > 0:
        highest = "critical"
    elif by_severity["warning"] > 0:
        highest = "warning"

    return {
        "active_count": len(active_alerts),
        "by_severity": by_severity,
        "highest_severity": highest,
        "recent_alerts": active_alerts[:5],
    }


# ── Internal helpers ──────────────────────────────────────────────

async def _collect_drift_evidence(
    tenant_id: str, window_start: str, now: datetime
) -> Dict[str, Any]:
    """Collect drift evidence from timeline events and alignment data."""
    # Look for drift events in the event timeline
    drift_events = await db.event_timeline.find(
        {
            "tenant_id": tenant_id,
            "entity_type": "inventory_alignment",
            "stage": "drift_detected",
            "timestamp": {"$gte": window_start},
        },
        {"_id": 0},
    ).to_list(500)

    total_drift_records = len(drift_events)
    total_drift_nights = 0
    providers_with_drift: List[str] = []

    for ev in drift_events:
        meta = ev.get("metadata", {})
        total_drift_nights += meta.get("total_drift_count", 0)
        for p in meta.get("providers", []):
            pname = p.get("provider", "")
            if pname and pname not in providers_with_drift:
                providers_with_drift.append(pname)

    # Also check current alignment for live drift count
    from .inventory_alignment import compute_inventory_alignment
    try:
        current = await compute_inventory_alignment(tenant_id=tenant_id, days_ahead=14)
        live_drift = current.get("drift_count", 0)
        live_nights = current.get("drift_nights", 0)
        if live_drift > 0:
            total_drift_records = max(total_drift_records, 1)
            total_drift_nights = max(total_drift_nights, live_nights)
            for pb in current.get("provider_breakdown", []):
                if pb.get("drift_count", 0) > 0:
                    pname = pb.get("provider", "")
                    if pname and pname not in providers_with_drift:
                        providers_with_drift.append(pname)
    except Exception as e:
        logger.debug("Live alignment check failed: %s", e)

    # Check post-reconciliation drift
    post_recon_drift = await _check_post_recon_drift(tenant_id, window_start)

    return {
        "total_drift_records": total_drift_records,
        "total_drift_nights": total_drift_nights,
        "providers_with_drift": providers_with_drift,
        "post_recon_drift": post_recon_drift,
        "window_start": window_start,
    }


async def _check_post_recon_drift(tenant_id: str, window_start: str) -> bool:
    """Check if drift persists after the most recent reconciliation."""
    # Find last reconciliation event
    last_recon = await db.event_timeline.find_one(
        {
            "tenant_id": tenant_id,
            "entity_type": {"$in": ["reconciliation", "inventory_reconciliation"]},
            "stage": {"$in": ["completed", "success"]},
            "timestamp": {"$gte": window_start},
        },
        {"_id": 0, "timestamp": 1},
        sort=[("timestamp", -1)],
    )

    if not last_recon:
        return False

    recon_ts = last_recon.get("timestamp", "")

    # Check if drift events exist AFTER this reconciliation
    post_recon_drifts = await db.event_timeline.count_documents({
        "tenant_id": tenant_id,
        "entity_type": "inventory_alignment",
        "stage": "drift_detected",
        "timestamp": {"$gt": recon_ts},
    })

    return post_recon_drifts > 0


async def _get_current_alignment(tenant_id: str) -> Dict[str, Any]:
    """Get current alignment status without full computation."""
    from .inventory_alignment import compute_inventory_alignment
    try:
        return await compute_inventory_alignment(tenant_id=tenant_id, days_ahead=7)
    except Exception as e:
        logger.debug("Alignment check failed: %s", e)
        return {"alignment_status": "unknown", "freshness": "unknown"}


async def _get_last_reconciliation(tenant_id: str) -> Dict[str, Any]:
    """Get last reconciliation result."""
    last_recon = await db.event_timeline.find_one(
        {
            "tenant_id": tenant_id,
            "entity_type": {"$in": ["reconciliation", "inventory_reconciliation"]},
        },
        {"_id": 0},
        sort=[("timestamp", -1)],
    )

    if not last_recon:
        return {"status": "no_data", "timestamp": None}

    return {
        "status": last_recon.get("stage", "unknown"),
        "timestamp": last_recon.get("timestamp"),
        "metadata": last_recon.get("metadata", {}),
    }


async def _fire_drift_alert(
    severity: str,
    tenant_id: str,
    evidence: Dict[str, Any],
    alignment: Dict[str, Any],
    recon: Dict[str, Any],
    reason: str,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """Fire a drift alert with severity-based routing."""
    # Check cooldown: same tenant + severity within last COOLDOWN_MINUTES
    cooldown_cutoff = (now - timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
    recent = await db[COLL_DRIFT_ALERTS].find_one(
        {
            "tenant_id": tenant_id,
            "severity": severity,
            "fired_at": {"$gte": cooldown_cutoff},
        },
        {"_id": 0, "alert_id": 1},
    )
    if recent:
        logger.debug("Drift alert suppressed by cooldown: %s %s", tenant_id, severity)
        return None

    # Build provider details
    provider_details = []
    for pb in alignment.get("provider_breakdown", []):
        if pb.get("drift_count", 0) > 0:
            provider_details.append({
                "provider": pb.get("provider", "unknown"),
                "connector_id": pb.get("connector_id", ""),
                "drift_count": pb.get("drift_count", 0),
                "snapshots_checked": pb.get("snapshots_checked", 0),
            })

    # Determine drift_or_stale
    freshness = alignment.get("freshness", "unknown")
    alignment_status = alignment.get("alignment_status", "unknown")
    if freshness in ("stale", "empty"):
        drift_or_stale = "stale"
    elif alignment_status == "drift_detected":
        drift_or_stale = "drift"
    else:
        drift_or_stale = alignment_status

    alert = {
        "alert_id": str(uuid4()),
        "tenant_id": tenant_id,
        "severity": severity,
        "reason": reason,
        "fired_at": now.isoformat(),
        "acknowledged": False,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "notification_routing": NOTIFICATION_ROUTING.get(severity, {}),
        "auto_action_triggered": False,
        "auto_action_result": None,
        "payload": {
            "tenant": tenant_id,
            "property": alignment.get("date_range", {}).get("start", ""),
            "providers": evidence.get("providers_with_drift", []),
            "provider_details": provider_details,
            "drift_count": evidence.get("total_drift_records", 0),
            "drift_nights": evidence.get("total_drift_nights", 0),
            "drift_or_stale": drift_or_stale,
            "last_reconciliation_result": {
                "status": recon.get("status", "no_data"),
                "timestamp": recon.get("timestamp"),
            },
            "runbook_link": RUNBOOK_LINK,
        },
    }

    # Log
    log_fn = logger.critical if severity == "severe" else (
        logger.warning if severity == "critical" else logger.info
    )
    log_fn(
        "DRIFT ALERT [%s] tenant=%s: %s | providers=%s | drift_nights=%d",
        severity.upper(), tenant_id, reason,
        evidence.get("providers_with_drift", []),
        evidence.get("total_drift_nights", 0),
    )

    # Persist (copy to avoid _id mutation)
    try:
        await db[COLL_DRIFT_ALERTS].insert_one({**alert})
    except Exception as e:
        logger.exception("Failed to persist drift alert: %s", e)

    # Notification routing based on severity
    routing = NOTIFICATION_ROUTING.get(severity, {})

    # Webhook notification (critical + severe)
    if routing.get("webhook"):
        await _send_webhook_notification(alert, "ALERT_WEBHOOK_URL")

    # Escalation webhook (severe only)
    if routing.get("escalation"):
        await _send_webhook_notification(alert, "ESCALATION_WEBHOOK_URL")

    # Auto-action for severe alerts
    if severity == "severe":
        try:
            from .auto_actions import execute_auto_action
            action_result = await execute_auto_action(
                action_type="reconciliation",
                tenant_id=tenant_id,
                alert_id=alert["alert_id"],
                reason=reason,
                providers=evidence.get("providers_with_drift", []),
            )
            alert["auto_action_triggered"] = True
            alert["auto_action_result"] = action_result
            # Update persisted alert
            await db[COLL_DRIFT_ALERTS].update_one(
                {"alert_id": alert["alert_id"]},
                {"$set": {
                    "auto_action_triggered": True,
                    "auto_action_result": action_result,
                }},
            )
        except Exception as e:
            logger.exception("Auto-action failed for drift alert: %s", e)

    return alert


async def _send_webhook_notification(alert: Dict[str, Any], url_env_key: str) -> None:
    """Send alert via webhook. Config-driven: no-op if URL not set."""
    webhook_url = os.environ.get(url_env_key, "")
    if not webhook_url:
        logger.debug("Webhook skipped: %s not configured", url_env_key)
        return

    try:
        import aiohttp
        severity = alert.get("severity", "unknown")
        payload_data = alert.get("payload", {})
        severity_emoji = {"severe": ":rotating_light:", "critical": ":warning:", "warning": ":large_yellow_circle:"}
        emoji = severity_emoji.get(severity, ":bell:")

        providers_str = ", ".join(payload_data.get("providers", [])) or "N/A"
        slack_payload = {
            "text": f"{emoji} *Inventory Drift Alert [{severity.upper()}]*\n{alert.get('reason', '')}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"Drift Alert: {severity.upper()}"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Severity:* {severity}"},
                        {"type": "mrkdwn", "text": f"*Tenant:* {alert.get('tenant_id', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Providers:* {providers_str}"},
                        {"type": "mrkdwn", "text": f"*Drift Count:* {payload_data.get('drift_count', 0)}"},
                        {"type": "mrkdwn", "text": f"*Drift Nights:* {payload_data.get('drift_nights', 0)}"},
                        {"type": "mrkdwn", "text": f"*Status:* {payload_data.get('drift_or_stale', 'unknown')}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": alert.get("reason", "")},
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Runbook: {payload_data.get('runbook_link', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"Fired: {alert.get('fired_at', '')}"},
                    ],
                },
            ],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url, json=slack_payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    logger.warning("Webhook %s delivery failed: status=%d", url_env_key, resp.status)
                else:
                    logger.info("Webhook %s delivered for alert %s", url_env_key, alert.get("alert_id"))
    except ImportError:
        logger.debug("aiohttp not installed — webhook disabled")
    except Exception:
        logger.exception("Webhook %s delivery error", url_env_key)
