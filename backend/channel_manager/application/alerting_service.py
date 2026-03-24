"""
Alerting Service — Phase 2: Proactive alert system for critical health drops and anomalies.

Collections: cm_alerts, cm_alert_rules
Alert triggers: health_score drop, ack failures, sync failures, provider unavailable,
                scheduler drift, invalid mapping, stale sync, retry spike, latency spike,
                reconciliation critical issue increase.
Severity: info, warning, critical
Actions: acknowledge, resolve, mute, snooze, dismiss
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.alerting")

ALERTS = "cm_alerts"
ALERT_RULES = "cm_alert_rules"
_NO_ID = {"_id": 0}

DEFAULT_RULES = [
    {"trigger": "health_score_drop", "threshold": 50, "severity": "critical", "description": "Health score dropped below threshold", "enabled": True},
    {"trigger": "health_score_drop", "threshold": 70, "severity": "warning", "description": "Health score below warning threshold", "enabled": True},
    {"trigger": "consecutive_sync_failures", "threshold": 3, "severity": "critical", "description": "Multiple consecutive sync failures", "enabled": True},
    {"trigger": "ack_failure_spike", "threshold": 5, "severity": "warning", "description": "ACK failure count exceeded threshold", "enabled": True},
    {"trigger": "stale_sync", "threshold": 24, "severity": "warning", "description": "No successful sync in threshold hours", "enabled": True},
    {"trigger": "stale_sync", "threshold": 48, "severity": "critical", "description": "No successful sync in threshold hours", "enabled": True},
    {"trigger": "invalid_mapping_detected", "threshold": 1, "severity": "warning", "description": "Invalid mappings detected", "enabled": True},
    {"trigger": "retry_spike", "threshold": 30, "severity": "warning", "description": "Retry rate exceeded threshold %", "enabled": True},
    {"trigger": "recon_critical_increase", "threshold": 1, "severity": "critical", "description": "New critical reconciliation issues", "enabled": True},
    {"trigger": "provider_unavailable", "threshold": 1, "severity": "critical", "description": "Provider is unreachable", "enabled": True},
    {"trigger": "import_failure_spike", "threshold": 5, "severity": "warning", "description": "Reservation import failures exceeded threshold", "enabled": True},
    {"trigger": "import_failure_spike", "threshold": 10, "severity": "critical", "description": "Critical reservation import failure count", "enabled": True},
]


class AlertingService:
    """Proactive alerting system for channel manager operations."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    # ─── Alert Rule Management ─────────────────────────────────────────

    async def get_rules(self, tenant_id: str) -> List[Dict]:
        rules = await db[ALERT_RULES].find({"tenant_id": tenant_id}, _NO_ID).to_list(100)
        if not rules:
            await self._seed_default_rules(tenant_id)
            rules = await db[ALERT_RULES].find({"tenant_id": tenant_id}, _NO_ID).to_list(100)
        return rules

    async def create_rule(self, tenant_id: str, rule_data: Dict, actor_id: Optional[str] = None) -> Dict:
        rule = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "trigger": rule_data["trigger"],
            "threshold": rule_data.get("threshold", 1),
            "severity": rule_data.get("severity", "warning"),
            "description": rule_data.get("description", ""),
            "enabled": rule_data.get("enabled", True),
            "connector_id": rule_data.get("connector_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": actor_id,
        }
        await db[ALERT_RULES].insert_one(rule)
        rule.pop("_id", None)
        return rule

    async def update_rule(self, tenant_id: str, rule_id: str, updates: Dict, actor_id: Optional[str] = None) -> Dict:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        updates["updated_by"] = actor_id
        await db[ALERT_RULES].update_one(
            {"tenant_id": tenant_id, "id": rule_id}, {"$set": updates}
        )
        return await db[ALERT_RULES].find_one({"tenant_id": tenant_id, "id": rule_id}, _NO_ID) or {}

    async def delete_rule(self, tenant_id: str, rule_id: str) -> bool:
        r = await db[ALERT_RULES].delete_one({"tenant_id": tenant_id, "id": rule_id})
        return r.deleted_count > 0

    async def _seed_default_rules(self, tenant_id: str):
        docs = []
        for r in DEFAULT_RULES:
            docs.append({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                **r,
                "connector_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "system",
            })
        if docs:
            await db[ALERT_RULES].insert_many(docs)

    # ─── Alert Evaluation ──────────────────────────────────────────────

    async def evaluate_alerts(self, tenant_id: str) -> Dict[str, Any]:
        """Evaluate all active rules against current connector states."""
        rules = await self.get_rules(tenant_id)
        enabled_rules = [r for r in rules if r.get("enabled")]
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)

        alerts_created = 0
        for c in connectors:
            cid = c.get("id", "")
            for rule in enabled_rules:
                if rule.get("connector_id") and rule["connector_id"] != cid:
                    continue
                triggered = await self._check_rule(tenant_id, c, rule)
                if triggered:
                    existing = await db[ALERTS].find_one({
                        "tenant_id": tenant_id, "connector_id": cid,
                        "trigger": rule["trigger"], "status": {"$in": ["active", "acknowledged"]},
                    })
                    if not existing:
                        await self._create_alert(tenant_id, c, rule)
                        alerts_created += 1

        return {"evaluated_rules": len(enabled_rules), "connectors_checked": len(connectors), "alerts_created": alerts_created}

    async def _check_rule(self, tenant_id: str, connector: Dict, rule: Dict) -> bool:
        cid = connector.get("id", "")
        trigger = rule.get("trigger", "")
        threshold = rule.get("threshold", 0)

        if trigger == "health_score_drop":
            from ..application.reconciliation_service import ReconciliationService
            recon = ReconciliationService(self._repo)
            health = await recon.get_health_score(tenant_id, cid)
            return health.get("health_score", 100) < threshold

        elif trigger == "consecutive_sync_failures":
            return connector.get("consecutive_failures", 0) >= threshold

        elif trigger == "ack_failure_spike":
            count = await db.cm_imported_reservations.count_documents({
                "tenant_id": tenant_id, "connector_id": cid, "ack_status": "ack_failed",
            })
            return count >= threshold

        elif trigger == "stale_sync":
            last_sync = connector.get("last_successful_sync")
            if not last_sync:
                return True
            try:
                dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                hours_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                return hours_ago >= threshold
            except (ValueError, TypeError):
                return True

        elif trigger == "invalid_mapping_detected":
            mappings = await self._repo.get_mappings_by_validation_status(tenant_id, cid, "invalid")
            return len(mappings) >= threshold

        elif trigger == "retry_spike":
            jobs = await self._repo.get_sync_jobs(tenant_id, cid, limit=100)
            total = len(jobs)
            retried = sum(1 for j in jobs if j.get("retry_count", 0) > 0)
            rate = (retried / max(total, 1)) * 100
            return rate >= threshold

        elif trigger == "recon_critical_increase":
            summary = await self._repo.get_reconciliation_summary(tenant_id, cid)
            critical = summary.get("by_severity", {}).get("critical", 0)
            return critical >= threshold

        elif trigger == "provider_unavailable":
            return connector.get("status") == "error"

        elif trigger == "import_failure_spike":
            failed_imports = await db.cm_imported_reservations.count_documents({
                "tenant_id": tenant_id, "connector_id": cid, "import_status": "failed",
            })
            return failed_imports >= threshold

        return False

    async def _create_alert(self, tenant_id: str, connector: Dict, rule: Dict) -> Dict:
        cid = connector.get("id", "")
        from ..application.reconciliation_service import ReconciliationService
        recon = ReconciliationService(self._repo)
        health = await recon.get_health_score(tenant_id, cid)

        alert = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": cid,
            "property_id": connector.get("property_id", ""),
            "provider": connector.get("provider", ""),
            "display_name": connector.get("display_name", ""),
            "trigger": rule["trigger"],
            "rule_id": rule.get("id", ""),
            "severity": rule.get("severity", "warning"),
            "status": "active",
            "description": rule.get("description", ""),
            "health_score_snapshot": health.get("health_score", 0),
            "threshold": rule.get("threshold"),
            "recommended_action": self._get_recommended_action(rule["trigger"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_at": None,
            "resolved_at": None,
            "muted_until": None,
        }
        await db[ALERTS].insert_one(alert)
        alert.pop("_id", None)
        log = IntegrationAuditLog(
            tenant_id=tenant_id, connector_id=cid,
            action=AuditAction.ALERT_CREATED,
            metadata={"trigger": rule["trigger"], "severity": rule["severity"], "alert_id": alert["id"]},
        )
        await self._repo.create_audit_log(log.to_doc())

        # Deliver alert to configured channels
        try:
            from .alert_delivery_service import AlertDeliveryService
            delivery_svc = AlertDeliveryService(repo=self._repo)
            await delivery_svc.deliver_alert(tenant_id, alert)
        except Exception as e:
            logger.warning("Alert delivery failed for alert %s: %s", alert["id"], e)

        # Emit WebSocket event
        try:
            from .realtime_service import RealtimeEventService
            await RealtimeEventService.emit_alert_triggered(tenant_id, alert)
        except Exception as e:
            logger.debug("WS emit failed: %s", e)


        return alert

    @staticmethod
    def _get_recommended_action(trigger: str) -> str:
        actions = {
            "health_score_drop": "Review connector health and recent sync failures",
            "consecutive_sync_failures": "Check provider connectivity and credentials",
            "ack_failure_spike": "Investigate ACK failures and retry pending ACKs",
            "stale_sync": "Trigger manual sync or check scheduler status",
            "invalid_mapping_detected": "Review and fix invalid mappings",
            "retry_spike": "Investigate root cause of frequent retries",
            "recon_critical_increase": "Review critical reconciliation issues immediately",
            "provider_unavailable": "Check provider status and network connectivity",
            "import_failure_spike": "Review failed reservation imports and check mapping configuration",
        }
        return actions.get(trigger, "Investigate the issue")

    # ─── Alert CRUD & Actions ──────────────────────────────────────────

    async def get_alerts(
        self, tenant_id: str, status: Optional[str] = None,
        severity: Optional[str] = None, connector_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            q["status"] = status
        if severity:
            q["severity"] = severity
        if connector_id:
            q["connector_id"] = connector_id
        return await db[ALERTS].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def get_alert_summary(self, tenant_id: str) -> Dict[str, Any]:
        active = await db[ALERTS].count_documents({"tenant_id": tenant_id, "status": "active"})
        acknowledged = await db[ALERTS].count_documents({"tenant_id": tenant_id, "status": "acknowledged"})
        resolved = await db[ALERTS].count_documents({"tenant_id": tenant_id, "status": "resolved"})
        muted = await db[ALERTS].count_documents({"tenant_id": tenant_id, "status": "muted"})

        by_severity = {}
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "status": "active"}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        async for doc in db[ALERTS].aggregate(pipeline):
            by_severity[doc["_id"]] = doc["count"]

        return {
            "active": active, "acknowledged": acknowledged,
            "resolved": resolved, "muted": muted,
            "total_open": active + acknowledged,
            "by_severity": by_severity,
        }

    async def acknowledge_alert(self, tenant_id: str, alert_id: str, actor_id: Optional[str] = None) -> Dict:
        now = datetime.now(timezone.utc).isoformat()
        await db[ALERTS].update_one(
            {"tenant_id": tenant_id, "id": alert_id},
            {"$set": {"status": "acknowledged", "acknowledged_at": now, "acknowledged_by": actor_id}},
        )
        log = IntegrationAuditLog(
            tenant_id=tenant_id, action=AuditAction.ALERT_ACKNOWLEDGED,
            actor_id=actor_id, metadata={"alert_id": alert_id},
        )
        await self._repo.create_audit_log(log.to_doc())
        return {"success": True, "alert_id": alert_id, "action": "acknowledged"}

    async def resolve_alert(self, tenant_id: str, alert_id: str, actor_id: Optional[str] = None, reason: str = "") -> Dict:
        now = datetime.now(timezone.utc).isoformat()
        await db[ALERTS].update_one(
            {"tenant_id": tenant_id, "id": alert_id},
            {"$set": {"status": "resolved", "resolved_at": now, "resolved_by": actor_id, "resolve_reason": reason}},
        )
        log = IntegrationAuditLog(
            tenant_id=tenant_id, action=AuditAction.ALERT_RESOLVED,
            actor_id=actor_id, metadata={"alert_id": alert_id, "reason": reason},
        )
        await self._repo.create_audit_log(log.to_doc())
        return {"success": True, "alert_id": alert_id, "action": "resolved"}

    async def mute_alert(self, tenant_id: str, alert_id: str, hours: int = 24, actor_id: Optional[str] = None) -> Dict:
        muted_until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        await db[ALERTS].update_one(
            {"tenant_id": tenant_id, "id": alert_id},
            {"$set": {"status": "muted", "muted_until": muted_until, "muted_by": actor_id}},
        )
        log = IntegrationAuditLog(
            tenant_id=tenant_id, action=AuditAction.ALERT_MUTED,
            actor_id=actor_id, metadata={"alert_id": alert_id, "muted_hours": hours},
        )
        await self._repo.create_audit_log(log.to_doc())
        return {"success": True, "alert_id": alert_id, "action": "muted", "muted_until": muted_until}

    async def dismiss_alert(self, tenant_id: str, alert_id: str, actor_id: Optional[str] = None, reason: str = "") -> Dict:
        now = datetime.now(timezone.utc).isoformat()
        await db[ALERTS].update_one(
            {"tenant_id": tenant_id, "id": alert_id},
            {"$set": {"status": "dismissed", "dismissed_at": now, "dismissed_by": actor_id, "dismiss_reason": reason}},
        )
        return {"success": True, "alert_id": alert_id, "action": "dismissed"}


    async def check_and_fire_alert(
        self, tenant_id: str, trigger: str,
        connector_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Programmatic alert creation for automated triggers
        (e.g., reservation import failure spike, sandbox validation failures).
        Checks for duplicate active alerts before creating.
        """
        # Dedup: don't fire if same trigger is already active
        existing = await db[ALERTS].find_one({
            "tenant_id": tenant_id,
            "trigger": trigger,
            "connector_id": connector_id or "",
            "status": {"$in": ["active", "acknowledged"]},
        })
        if existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        alert = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": connector_id or "",
            "trigger": trigger,
            "severity": "critical" if "failure" in trigger else "warning",
            "title": f"Alert: {trigger.replace('_', ' ').title()}",
            "description": f"Automated alert triggered by {trigger}",
            "status": "active",
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        await db[ALERTS].insert_one(alert)
        alert.pop("_id", None)

        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            connector_id=connector_id,
            action=AuditAction.ALERT_CREATED,
            metadata={"trigger": trigger, "alert_id": alert["id"]},
        )
        await self._repo.create_audit_log(log.to_doc())

        # Deliver alert to configured channels
        try:
            from .alert_delivery_service import AlertDeliveryService
            delivery_svc = AlertDeliveryService(repo=self._repo)
            await delivery_svc.deliver_alert(tenant_id, alert)
        except Exception as e:
            logger.warning("Alert delivery failed for alert %s: %s", alert["id"], e)

        return alert
