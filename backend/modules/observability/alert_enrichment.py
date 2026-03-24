"""
Observability — Alert Enrichment Engine
========================================
Production-grade alert rules engine with severity mapping, cooldown/dedupe,
runbook hints, blast radius assessment, and route compatibility
(Grafana/Alertmanager/PagerDuty/Slack).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class AlertCategory(str, Enum):
    PMS = "pms"
    CHANNEL_MANAGER = "channel_manager"
    QUEUE = "queue"
    WORKER = "worker"
    SECURITY = "security"
    MESSAGING = "messaging"
    WEBSOCKET = "websocket"
    TENANT = "tenant"
    ML = "ml"
    NIGHT_AUDIT = "night_audit"
    RECONCILIATION = "reconciliation"


# ── Alert Rule Definitions ───────────────────────────────────────────

ALERT_RULES: List[Dict[str, Any]] = [
    # Night Audit
    {
        "rule_id": "night_audit_duration_breach",
        "name": "Night Audit Duration Breach",
        "category": AlertCategory.NIGHT_AUDIT,
        "severity": AlertSeverity.HIGH,
        "condition": "night_audit_duration_ms > 300000",
        "threshold_field": "duration_ms",
        "threshold_value": 300000,
        "cooldown_minutes": 60,
        "blast_radius": "property",
        "runbook": "Check folio count, room count, and DB query performance. Consider dry-run first.",
        "owner": "pms-team",
    },
    {
        "rule_id": "audit_exception_spike",
        "name": "Audit Exception Spike",
        "category": AlertCategory.NIGHT_AUDIT,
        "severity": AlertSeverity.HIGH,
        "condition": "audit_exceptions_count > 10 in 1h",
        "threshold_field": "exception_count",
        "threshold_value": 10,
        "cooldown_minutes": 30,
        "blast_radius": "property",
        "runbook": "Review night_audit_exceptions collection. Group by exception_type. Check folio/tax consistency.",
        "owner": "pms-team",
    },
    # Queue / Worker
    {
        "rule_id": "queue_lag_threshold",
        "name": "Queue Lag Threshold Exceeded",
        "category": AlertCategory.QUEUE,
        "severity": AlertSeverity.HIGH,
        "condition": "queue_pending_count > 500",
        "threshold_field": "pending_count",
        "threshold_value": 500,
        "cooldown_minutes": 15,
        "blast_radius": "platform",
        "runbook": "Scale workers horizontally. Check for stuck tasks. Review dead letter queue.",
        "owner": "platform-team",
    },
    {
        "rule_id": "worker_heartbeat_missing",
        "name": "Worker Heartbeat Missing",
        "category": AlertCategory.WORKER,
        "severity": AlertSeverity.CRITICAL,
        "condition": "last_worker_heartbeat > 120s ago",
        "threshold_field": "heartbeat_age_seconds",
        "threshold_value": 120,
        "cooldown_minutes": 5,
        "blast_radius": "platform",
        "runbook": "Check Celery workers. Restart if needed. Check Redis connectivity.",
        "owner": "platform-team",
    },
    {
        "rule_id": "dead_letter_growth",
        "name": "Dead Letter Queue Growth",
        "category": AlertCategory.QUEUE,
        "severity": AlertSeverity.WARNING,
        "condition": "dead_letter_count growth > 20 in 1h",
        "threshold_field": "dead_letter_growth",
        "threshold_value": 20,
        "cooldown_minutes": 30,
        "blast_radius": "platform",
        "runbook": "Review DLQ entries. Check for systematic failures. Consider replay after fix.",
        "owner": "platform-team",
    },
    # Channel Manager / Drift / Reconciliation
    {
        "rule_id": "drift_issue_spike",
        "name": "Drift Issue Spike",
        "category": AlertCategory.CHANNEL_MANAGER,
        "severity": AlertSeverity.HIGH,
        "condition": "drift_count > 20 in 30min",
        "threshold_field": "drift_count",
        "threshold_value": 20,
        "cooldown_minutes": 30,
        "blast_radius": "tenant",
        "runbook": "Check provider sync status. Trigger manual reconciliation. Review ARI update logs.",
        "owner": "cm-team",
    },
    {
        "rule_id": "reconciliation_failure_spike",
        "name": "Reconciliation Failure Spike",
        "category": AlertCategory.RECONCILIATION,
        "severity": AlertSeverity.CRITICAL,
        "condition": "recon_failures > 5 in 1h",
        "threshold_field": "failure_count",
        "threshold_value": 5,
        "cooldown_minutes": 30,
        "blast_radius": "tenant",
        "runbook": "Check provider connectivity. Review failed reconciliation logs. Manual re-trigger needed.",
        "owner": "cm-team",
    },
    {
        "rule_id": "provider_circuit_breaker_open",
        "name": "Provider Circuit Breaker Open",
        "category": AlertCategory.CHANNEL_MANAGER,
        "severity": AlertSeverity.CRITICAL,
        "condition": "circuit_breaker_state == open",
        "threshold_field": "circuit_state",
        "threshold_value": "open",
        "cooldown_minutes": 15,
        "blast_radius": "tenant",
        "runbook": "Provider outage detected. Check provider status page. Monitor for half-open recovery.",
        "owner": "cm-team",
    },
    # WebSocket / Dashboard
    {
        "rule_id": "websocket_stale_data",
        "name": "WebSocket Stale Dashboard Data",
        "category": AlertCategory.WEBSOCKET,
        "severity": AlertSeverity.WARNING,
        "condition": "last_ws_event > 120s ago",
        "threshold_field": "event_age_seconds",
        "threshold_value": 120,
        "cooldown_minutes": 10,
        "blast_radius": "platform",
        "runbook": "Check Socket.IO server health. Verify event emitter is running. Check network.",
        "owner": "platform-team",
    },
    # Messaging
    {
        "rule_id": "message_delivery_failure_spike",
        "name": "Message Delivery Failure Spike",
        "category": AlertCategory.MESSAGING,
        "severity": AlertSeverity.HIGH,
        "condition": "message_failures > 10 in 30min",
        "threshold_field": "failure_count",
        "threshold_value": 10,
        "cooldown_minutes": 30,
        "blast_radius": "tenant",
        "runbook": "Check messaging provider status. Review failed message logs. Verify credentials.",
        "owner": "messaging-team",
    },
    # Security
    {
        "rule_id": "rate_limit_burst",
        "name": "Rate Limit Burst Detected",
        "category": AlertCategory.SECURITY,
        "severity": AlertSeverity.WARNING,
        "condition": "rate_limit_hits > 100 in 5min",
        "threshold_field": "rate_limit_hits",
        "threshold_value": 100,
        "cooldown_minutes": 10,
        "blast_radius": "tenant",
        "runbook": "Identify source IP/tenant. Consider temporary block. Review rate limit policy.",
        "owner": "security-team",
    },
    {
        "rule_id": "tenant_guard_violation",
        "name": "Tenant Guard Violation",
        "category": AlertCategory.SECURITY,
        "severity": AlertSeverity.CRITICAL,
        "condition": "tenant_guard_violations > 0",
        "threshold_field": "violation_count",
        "threshold_value": 1,
        "cooldown_minutes": 5,
        "blast_radius": "platform",
        "runbook": "CRITICAL: Cross-tenant data access detected. Isolate tenant. Review audit logs immediately.",
        "owner": "security-team",
    },
    # Tenant
    {
        "rule_id": "noisy_tenant_saturation",
        "name": "Noisy Tenant Saturation",
        "category": AlertCategory.TENANT,
        "severity": AlertSeverity.HIGH,
        "condition": "tenant_request_ratio > 40%",
        "threshold_field": "request_ratio_percent",
        "threshold_value": 40,
        "cooldown_minutes": 30,
        "blast_radius": "platform",
        "runbook": "Identify noisy tenant. Apply throttling. Review resource allocation.",
        "owner": "platform-team",
    },
    # ML
    {
        "rule_id": "stale_model_output",
        "name": "Stale ML Model Output",
        "category": AlertCategory.ML,
        "severity": AlertSeverity.WARNING,
        "condition": "last_model_run > 24h ago",
        "threshold_field": "model_age_hours",
        "threshold_value": 24,
        "cooldown_minutes": 120,
        "blast_radius": "property",
        "runbook": "Check ML pipeline status. Verify training data freshness. Re-trigger model run.",
        "owner": "ml-team",
    },
    # Worker retry storm
    {
        "rule_id": "worker_retry_storm",
        "name": "Worker Retry Storm",
        "category": AlertCategory.WORKER,
        "severity": AlertSeverity.HIGH,
        "condition": "retry_count > 50 in 15min",
        "threshold_field": "retry_count",
        "threshold_value": 50,
        "cooldown_minutes": 15,
        "blast_radius": "platform",
        "runbook": "Check for systematic task failures. Review retry backoff config. Consider pausing queue.",
        "owner": "platform-team",
    },
]


class AlertEnrichmentEngine:
    """Evaluates alert rules against live metrics and manages alert lifecycle."""

    def __init__(self):
        from core.database import db
        self._db = db
        self._cooldown_cache: Dict[str, datetime] = {}

    async def evaluate_all_rules(
        self, ctx: OperationContext, metrics: Dict[str, Any]
    ) -> ServiceResult:
        """Evaluate all rules against provided metrics snapshot."""
        fired_alerts = []
        now = datetime.now(timezone.utc)

        for rule in ALERT_RULES:
            rule_id = rule["rule_id"]
            threshold_field = rule["threshold_field"]
            threshold_value = rule["threshold_value"]
            cooldown_minutes = rule["cooldown_minutes"]

            # Check cooldown
            last_fired = self._cooldown_cache.get(rule_id)
            if last_fired and (now - last_fired).total_seconds() < cooldown_minutes * 60:
                continue

            metric_value = metrics.get(threshold_field)
            if metric_value is None:
                continue

            # Evaluate threshold
            triggered = False
            if isinstance(threshold_value, (int, float)):
                triggered = metric_value > threshold_value
            elif isinstance(threshold_value, str):
                triggered = str(metric_value) == threshold_value

            if triggered:
                alert = self._build_alert(rule, metric_value, ctx, now)
                fired_alerts.append(alert)
                self._cooldown_cache[rule_id] = now

                # Persist alert
                await self._persist_alert(alert)

        return ServiceResult.success({
            "evaluated_rules": len(ALERT_RULES),
            "alerts_fired": len(fired_alerts),
            "alerts": fired_alerts,
            "evaluated_at": now.isoformat(),
        })

    def _build_alert(
        self, rule: Dict, metric_value: Any, ctx: OperationContext, now: datetime
    ) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "rule_id": rule["rule_id"],
            "name": rule["name"],
            "category": rule["category"],
            "severity": rule["severity"],
            "condition": rule["condition"],
            "metric_value": metric_value,
            "threshold_value": rule["threshold_value"],
            "blast_radius": rule["blast_radius"],
            "runbook": rule["runbook"],
            "owner": rule["owner"],
            "tenant_id": ctx.tenant_id,
            "property_id": getattr(ctx, "property_id", None),
            "status": "firing",
            "acknowledged": False,
            "acknowledged_by": None,
            "resolved": False,
            "fired_at": now.isoformat(),
            "mtta": None,
            "mttr": None,
            "recommended_action": rule["runbook"],
        }

    async def _persist_alert(self, alert: Dict):
        try:
            await self._db.alert_events.insert_one(alert.copy())
        except Exception as e:
            logger.warning("Failed to persist alert: %s", e)

    async def get_active_alerts(
        self, ctx: OperationContext, severity: Optional[str] = None, limit: int = 50
    ) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id, "resolved": False}
        if severity:
            query["severity"] = severity
        alerts = await self._db.alert_events.find(
            query, {"_id": 0}
        ).sort("fired_at", -1).limit(limit).to_list(limit)
        return ServiceResult.success({
            "alerts": alerts,
            "count": len(alerts),
            "has_critical": any(a.get("severity") == "critical" for a in alerts),
        })

    async def acknowledge_alert(
        self, ctx: OperationContext, alert_id: str
    ) -> ServiceResult:
        now = datetime.now(timezone.utc)
        result = await self._db.alert_events.update_one(
            {"id": alert_id, "tenant_id": ctx.tenant_id},
            {
                "$set": {
                    "acknowledged": True,
                    "acknowledged_by": ctx.actor_id,
                    "acknowledged_at": now.isoformat(),
                }
            },
        )
        if result.modified_count == 0:
            return ServiceResult.fail("Alert not found", "NOT_FOUND")

        # Calculate MTTA
        alert = await self._db.alert_events.find_one({"id": alert_id}, {"_id": 0})
        if alert and alert.get("fired_at"):
            fired = datetime.fromisoformat(alert["fired_at"].replace("Z", "+00:00"))
            mtta = (now - fired).total_seconds()
            await self._db.alert_events.update_one(
                {"id": alert_id}, {"$set": {"mtta": round(mtta, 1)}}
            )

        return ServiceResult.success({"message": "Alert acknowledged", "alert_id": alert_id})

    async def resolve_alert(
        self, ctx: OperationContext, alert_id: str, resolution_note: str = ""
    ) -> ServiceResult:
        now = datetime.now(timezone.utc)
        result = await self._db.alert_events.update_one(
            {"id": alert_id, "tenant_id": ctx.tenant_id},
            {
                "$set": {
                    "resolved": True,
                    "resolved_by": ctx.actor_id,
                    "resolved_at": now.isoformat(),
                    "resolution_note": resolution_note,
                    "status": "resolved",
                }
            },
        )
        if result.modified_count == 0:
            return ServiceResult.fail("Alert not found", "NOT_FOUND")

        # Calculate MTTR
        alert = await self._db.alert_events.find_one({"id": alert_id}, {"_id": 0})
        if alert and alert.get("fired_at"):
            fired = datetime.fromisoformat(alert["fired_at"].replace("Z", "+00:00"))
            mttr = (now - fired).total_seconds()
            await self._db.alert_events.update_one(
                {"id": alert_id}, {"$set": {"mttr": round(mttr, 1)}}
            )

        return ServiceResult.success({"message": "Alert resolved", "alert_id": alert_id})

    async def get_alert_summary(
        self, ctx: OperationContext, hours: int = 24
    ) -> ServiceResult:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pipeline = [
            {"$match": {"tenant_id": ctx.tenant_id, "fired_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"severity": "$severity", "category": "$category"},
                    "count": {"$sum": 1},
                    "resolved": {"$sum": {"$cond": ["$resolved", 1, 0]}},
                    "avg_mtta": {"$avg": "$mtta"},
                    "avg_mttr": {"$avg": "$mttr"},
                }
            },
        ]
        results = await self._db.alert_events.aggregate(pipeline).to_list(100)
        by_severity = {}
        by_category = {}
        total = 0
        for r in results:
            sev = r["_id"]["severity"]
            cat = r["_id"]["category"]
            count = r["count"]
            total += count
            by_severity[sev] = by_severity.get(sev, 0) + count
            by_category[cat] = by_category.get(cat, 0) + count

        return ServiceResult.success({
            "period_hours": hours,
            "total_alerts": total,
            "by_severity": by_severity,
            "by_category": by_category,
            "rules_count": len(ALERT_RULES),
        })

    def get_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_id": r["rule_id"],
                "name": r["name"],
                "category": r["category"],
                "severity": r["severity"],
                "condition": r["condition"],
                "blast_radius": r["blast_radius"],
                "owner": r["owner"],
                "cooldown_minutes": r["cooldown_minutes"],
            }
            for r in ALERT_RULES
        ]


alert_enrichment_engine = AlertEnrichmentEngine()
