"""
Auto-Remediation Rules Engine v1
================================

Sprint 2 P1.5: Guardrail-based automation rules

Provides:
  - Connector status auto-degradation on repeated failures
  - Alert severity escalation
  - Controlled queueing during rate limits
  - Backlog drain on recovery
  - DLQ retry success → auto-resolve event

This is NOT full automation — it's guardrail-based:
  - Rules have thresholds and cooldowns
  - Actions are logged and reversible
  - Operators can override
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from routers.ops_event_emitter import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    emit_ops_event,
)

logger = logging.getLogger("auto_remediation")

# ══════════════════════════════════════════════════════════════════════
# Rule Definitions
# ══════════════════════════════════════════════════════════════════════

# Rule 1: Connector degradation on repeated failures
CONNECTOR_DEGRADE_THRESHOLD = 3  # failures in window
CONNECTOR_DEGRADE_WINDOW_MINUTES = 10

# Rule 2: Alert escalation
ALERT_ESCALATE_THRESHOLD = 5  # terminal failures in window
ALERT_ESCALATE_WINDOW_MINUTES = 10

# Rule 3: Rate limit controlled queueing
RATE_LIMIT_QUEUE_ENABLED = True

# Rule 4: Recovery backlog drain
RECOVERY_DRAIN_ENABLED = True

# Rule 5: DLQ auto-resolve
DLQ_AUTO_RESOLVE_ENABLED = True


# ══════════════════════════════════════════════════════════════════════
# Rule Engine
# ══════════════════════════════════════════════════════════════════════

class AutoRemediationEngine:
    """Guardrail-based auto-remediation engine."""

    def __init__(self):
        self._rule_cooldowns: dict[str, datetime] = {}
        self._running = False
        self._task = None

    async def start(self):
        """Start the background remediation checker."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[AUTO-REMEDIATION] Engine started")

    async def stop(self):
        """Stop the background checker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[AUTO-REMEDIATION] Engine stopped")

    async def _run_loop(self):
        """Background loop that checks rules periodically."""
        while self._running:
            try:
                await self._evaluate_all_rules()
            except Exception as exc:
                logger.error("[AUTO-REMEDIATION] Rule evaluation error: %s", exc)
            await asyncio.sleep(60)  # Check every 60 seconds

    async def _evaluate_all_rules(self):
        """Evaluate all remediation rules."""
        # Get all tenants
        tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(100)
        
        for tenant in tenants:
            tenant_id = tenant.get("id", "")
            if not tenant_id:
                continue

            await self._rule_connector_degradation(tenant_id)
            await self._rule_alert_escalation(tenant_id)
            await self._rule_recovery_check(tenant_id)

    # ── Rule 1: Connector Degradation ────────────────────────────────

    async def _rule_connector_degradation(self, tenant_id: str):
        """Degrade connector status on repeated 5xx failures."""
        cooldown_key = f"degrade:{tenant_id}"
        if self._is_in_cooldown(cooldown_key, minutes=5):
            return

        since = (datetime.now(UTC) - timedelta(minutes=CONNECTOR_DEGRADE_WINDOW_MINUTES)).isoformat()

        # Count terminal failures per connector
        connectors = await db.cm_connectors.find(
            {"tenant_id": tenant_id, "status": {"$ne": "degraded"}},
            {"_id": 0, "id": 1, "provider": 1, "status": 1}
        ).to_list(50)

        for conn in connectors:
            connector_id = conn.get("id", "")
            provider = conn.get("provider", "")

            # Count 5xx failures
            failure_count = await db.ops_events.count_documents({
                "tenant_id": tenant_id,
                "event_type": {"$in": [
                    "webhook.delivery.terminal_failure",
                    "push.failed_terminal"
                ]},
                "created_at": {"$gte": since},
                "$or": [
                    {"connector_id": connector_id},
                    {"channel": {"$regex": provider, "$options": "i"}},
                ],
            })

            if failure_count >= CONNECTOR_DEGRADE_THRESHOLD:
                # Degrade connector
                await db.cm_connectors.update_one(
                    {"id": connector_id, "tenant_id": tenant_id},
                    {"$set": {
                        "status": "degraded",
                        "degraded_at": datetime.now(UTC).isoformat(),
                        "degraded_reason": f"Auto-remediation: {failure_count} failures in {CONNECTOR_DEGRADE_WINDOW_MINUTES}min",
                    }}
                )

                # Emit event
                await emit_ops_event(
                    "connector.auto_degraded",
                    tenant_id,
                    channel=provider,
                    connector_id=connector_id,
                    severity=SEVERITY_WARNING,
                    title=f"Connector otomatik olarak degraded durumuna alındı: {provider}",
                    details={
                        "connector_id": connector_id,
                        "provider": provider,
                        "failure_count": failure_count,
                        "threshold": CONNECTOR_DEGRADE_THRESHOLD,
                        "window_minutes": CONNECTOR_DEGRADE_WINDOW_MINUTES,
                        "action": "auto_degrade",
                        "reversible": True,
                    },
                    affected_entity_type="connector",
                    affected_entity_id=connector_id,
                )

                logger.warning(
                    "[AUTO-REMEDIATION] Connector %s degraded: %d failures in %d min",
                    connector_id, failure_count, CONNECTOR_DEGRADE_WINDOW_MINUTES
                )

                self._set_cooldown(cooldown_key)

    # ── Rule 2: Alert Escalation ─────────────────────────────────────

    async def _rule_alert_escalation(self, tenant_id: str):
        """Escalate alert severity on repeated terminal failures."""
        cooldown_key = f"escalate:{tenant_id}"
        if self._is_in_cooldown(cooldown_key, minutes=10):
            return

        since = (datetime.now(UTC) - timedelta(minutes=ALERT_ESCALATE_WINDOW_MINUTES)).isoformat()

        # Count terminal failures
        terminal_count = await db.ops_events.count_documents({
            "tenant_id": tenant_id,
            "event_type": {"$in": [
                "webhook.delivery.terminal_failure",
                "webhook.delivery.dlq",
                "push.failed_terminal",
            ]},
            "created_at": {"$gte": since},
        })

        if terminal_count >= ALERT_ESCALATE_THRESHOLD:
            # Emit escalation event
            await emit_ops_event(
                "alert.severity_escalated",
                tenant_id,
                severity=SEVERITY_CRITICAL,
                title=f"Alert seviyesi yükseltildi: {terminal_count} terminal failure",
                details={
                    "terminal_failure_count": terminal_count,
                    "threshold": ALERT_ESCALATE_THRESHOLD,
                    "window_minutes": ALERT_ESCALATE_WINDOW_MINUTES,
                    "action": "severity_escalation",
                    "new_severity": "critical",
                },
                affected_entity_type="system",
                affected_entity_id="alert_system",
            )

            logger.warning(
                "[AUTO-REMEDIATION] Alert escalated for tenant %s: %d terminal failures",
                tenant_id, terminal_count
            )

            self._set_cooldown(cooldown_key)

    # ── Rule 3: Recovery Check ───────────────────────────────────────

    async def _rule_recovery_check(self, tenant_id: str):
        """Check if degraded connectors have recovered."""
        cooldown_key = f"recover:{tenant_id}"
        if self._is_in_cooldown(cooldown_key, minutes=5):
            return

        # Find degraded connectors
        degraded = await db.cm_connectors.find(
            {"tenant_id": tenant_id, "status": "degraded"},
            {"_id": 0, "id": 1, "provider": 1, "degraded_at": 1}
        ).to_list(50)

        since_30m = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        for conn in degraded:
            connector_id = conn.get("id", "")
            provider = conn.get("provider", "")

            # Check for recent successes
            success_count = await db.ops_events.count_documents({
                "tenant_id": tenant_id,
                "event_type": {"$in": [
                    "webhook.delivery.succeeded",
                    "push.succeeded",
                ]},
                "created_at": {"$gte": since_30m},
                "$or": [
                    {"connector_id": connector_id},
                    {"channel": {"$regex": provider, "$options": "i"}},
                ],
            })

            # Check for recent failures
            failure_count = await db.ops_events.count_documents({
                "tenant_id": tenant_id,
                "event_type": {"$in": [
                    "webhook.delivery.terminal_failure",
                    "push.failed_terminal",
                ]},
                "created_at": {"$gte": since_30m},
                "$or": [
                    {"connector_id": connector_id},
                    {"channel": {"$regex": provider, "$options": "i"}},
                ],
            })

            # Recovery condition: successes > 3 and no recent failures
            if success_count >= 3 and failure_count == 0:
                # Recover connector
                await db.cm_connectors.update_one(
                    {"id": connector_id, "tenant_id": tenant_id},
                    {"$set": {
                        "status": "active",
                        "recovered_at": datetime.now(UTC).isoformat(),
                    },
                    "$unset": {"degraded_at": "", "degraded_reason": ""}}
                )

                # Emit recovery event
                await emit_ops_event(
                    "connector.auto_recovered",
                    tenant_id,
                    channel=provider,
                    connector_id=connector_id,
                    severity=SEVERITY_INFO,
                    title=f"Connector otomatik olarak recovered: {provider}",
                    details={
                        "connector_id": connector_id,
                        "provider": provider,
                        "success_count_30m": success_count,
                        "failure_count_30m": failure_count,
                        "action": "auto_recover",
                    },
                    affected_entity_type="connector",
                    affected_entity_id=connector_id,
                )

                logger.info(
                    "[AUTO-REMEDIATION] Connector %s recovered: %d successes, 0 failures",
                    connector_id, success_count
                )

                self._set_cooldown(cooldown_key)

    # ── Cooldown Management ──────────────────────────────────────────

    def _is_in_cooldown(self, key: str, minutes: int = 5) -> bool:
        """Check if a rule is in cooldown."""
        if key not in self._rule_cooldowns:
            return False
        cooldown_until = self._rule_cooldowns[key]
        return datetime.now(UTC) < cooldown_until

    def _set_cooldown(self, key: str, minutes: int = 5):
        """Set cooldown for a rule."""
        self._rule_cooldowns[key] = datetime.now(UTC) + timedelta(minutes=minutes)


# ══════════════════════════════════════════════════════════════════════
# Singleton Instance
# ══════════════════════════════════════════════════════════════════════

_engine: AutoRemediationEngine | None = None


def get_remediation_engine() -> AutoRemediationEngine:
    """Get or create the remediation engine singleton."""
    global _engine
    if _engine is None:
        _engine = AutoRemediationEngine()
    return _engine


# ══════════════════════════════════════════════════════════════════════
# Event Handlers (called from webhook_retry_service, etc.)
# ══════════════════════════════════════════════════════════════════════

async def on_dlq_retry_success(tenant_id: str, dlq_id: str, correlation_id: str):
    """Called when a DLQ item is successfully retried.
    
    Emits an auto-resolve event.
    """
    if not DLQ_AUTO_RESOLVE_ENABLED:
        return

    await emit_ops_event(
        "incident.auto_resolved",
        tenant_id,
        severity=SEVERITY_INFO,
        title="DLQ retry başarılı — incident otomatik çözüldü",
        details={
            "dlq_id": dlq_id,
            "action": "auto_resolve",
            "trigger": "dlq_retry_success",
        },
        correlation_id=correlation_id,
        affected_entity_type="dlq",
        affected_entity_id=dlq_id,
    )

    logger.info("[AUTO-REMEDIATION] DLQ %s auto-resolved after successful retry", dlq_id)


async def on_rate_limit_active(tenant_id: str, provider: str, cooldown_until: str):
    """Called when rate limit becomes active.
    
    Enables controlled queueing for new pushes.
    """
    if not RATE_LIMIT_QUEUE_ENABLED:
        return

    # Store rate limit state
    await db.rate_limit_state.update_one(
        {"tenant_id": tenant_id, "provider": provider},
        {"$set": {
            "is_throttled": True,
            "cooldown_until": cooldown_until,
            "queue_enabled": True,
            "updated_at": datetime.now(UTC).isoformat(),
        }},
        upsert=True
    )

    logger.info(
        "[AUTO-REMEDIATION] Rate limit active for %s/%s — queueing enabled until %s",
        tenant_id, provider, cooldown_until
    )


async def on_rate_limit_cleared(tenant_id: str, provider: str):
    """Called when rate limit is cleared.
    
    Triggers backlog drain if enabled.
    """
    if not RECOVERY_DRAIN_ENABLED:
        return

    # Update rate limit state
    await db.rate_limit_state.update_one(
        {"tenant_id": tenant_id, "provider": provider},
        {"$set": {
            "is_throttled": False,
            "queue_enabled": False,
            "cleared_at": datetime.now(UTC).isoformat(),
        }}
    )

    # Emit backlog drain event
    await emit_ops_event(
        "rate_limit.cleared_drain_started",
        tenant_id,
        channel=provider,
        severity=SEVERITY_INFO,
        title=f"Rate limit temizlendi — backlog drain başlatıldı: {provider}",
        details={
            "provider": provider,
            "action": "backlog_drain",
        },
        affected_entity_type="rate_limiter",
        affected_entity_id=provider,
    )

    logger.info(
        "[AUTO-REMEDIATION] Rate limit cleared for %s/%s — backlog drain started",
        tenant_id, provider
    )


# ══════════════════════════════════════════════════════════════════════
# Manual Trigger API
# ══════════════════════════════════════════════════════════════════════

async def manually_recover_connector(tenant_id: str, connector_id: str) -> dict[str, Any]:
    """Manually recover a degraded connector."""
    result = await db.cm_connectors.update_one(
        {"id": connector_id, "tenant_id": tenant_id, "status": "degraded"},
        {"$set": {
            "status": "active",
            "recovered_at": datetime.now(UTC).isoformat(),
            "recovered_by": "manual",
        },
        "$unset": {"degraded_at": "", "degraded_reason": ""}}
    )

    if result.modified_count == 0:
        return {"ok": False, "error": "Connector bulunamadı veya zaten aktif"}

    conn = await db.cm_connectors.find_one(
        {"id": connector_id, "tenant_id": tenant_id},
        {"_id": 0, "provider": 1}
    )
    provider = conn.get("provider", "") if conn else ""

    await emit_ops_event(
        "connector.manual_recovered",
        tenant_id,
        channel=provider,
        connector_id=connector_id,
        severity=SEVERITY_INFO,
        title=f"Connector manuel olarak recovered: {provider}",
        details={
            "connector_id": connector_id,
            "provider": provider,
            "action": "manual_recover",
        },
        affected_entity_type="connector",
        affected_entity_id=connector_id,
    )

    return {"ok": True, "connector_id": connector_id, "status": "active"}


async def manually_degrade_connector(tenant_id: str, connector_id: str, reason: str = "") -> dict[str, Any]:
    """Manually degrade a connector."""
    result = await db.cm_connectors.update_one(
        {"id": connector_id, "tenant_id": tenant_id, "status": {"$ne": "degraded"}},
        {"$set": {
            "status": "degraded",
            "degraded_at": datetime.now(UTC).isoformat(),
            "degraded_reason": reason or "Manuel degrade",
        }}
    )

    if result.modified_count == 0:
        return {"ok": False, "error": "Connector bulunamadı veya zaten degraded"}

    conn = await db.cm_connectors.find_one(
        {"id": connector_id, "tenant_id": tenant_id},
        {"_id": 0, "provider": 1}
    )
    provider = conn.get("provider", "") if conn else ""

    await emit_ops_event(
        "connector.manual_degraded",
        tenant_id,
        channel=provider,
        connector_id=connector_id,
        severity=SEVERITY_WARNING,
        title=f"Connector manuel olarak degraded: {provider}",
        details={
            "connector_id": connector_id,
            "provider": provider,
            "reason": reason,
            "action": "manual_degrade",
        },
        affected_entity_type="connector",
        affected_entity_id=connector_id,
    )

    return {"ok": True, "connector_id": connector_id, "status": "degraded"}
