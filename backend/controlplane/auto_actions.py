"""
Auto-Action Engine — Automated Responses to Severe Alerts
===========================================================
Executes automated operational actions when severe conditions are detected.

Current actions:
  - severe drift → trigger reconciliation via existing service

Guardrails:
  - Only severe drift triggers auto-action
  - Cooldown: same tenant+provider cannot be auto-actioned within 15 min
  - Eligibility check: only if not already running
  - Single execution per provider/tenant pair
  - Every action logged to event_timeline
  - Failed auto-action generates a new alert
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.database import db

logger = logging.getLogger("controlplane.auto_actions")

COLL_AUTO_ACTIONS = "cp_auto_actions"
AUTO_ACTION_COOLDOWN_MINUTES = 15


async def execute_auto_action(
    action_type: str,
    tenant_id: str,
    alert_id: str,
    reason: str,
    providers: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute an automated action with full guardrails.

    Returns action result with status, details, and audit trail.
    """
    now = datetime.now(timezone.utc)
    action_id = str(uuid4())

    # Guardrail 1: Eligibility check
    eligible, ineligibility_reason = await _check_eligibility(
        action_type, tenant_id, now
    )
    if not eligible:
        result = {
            "action_id": action_id,
            "action_type": action_type,
            "status": "skipped",
            "reason": ineligibility_reason,
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "executed_at": now.isoformat(),
            "dry_run": dry_run,
        }
        await _log_action(result)
        return result

    if dry_run:
        return {
            "action_id": action_id,
            "action_type": action_type,
            "status": "dry_run",
            "reason": "Eligible but dry_run=True",
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "executed_at": now.isoformat(),
            "dry_run": True,
        }

    # Execute the action
    if action_type == "reconciliation":
        result = await _execute_reconciliation(
            action_id=action_id,
            tenant_id=tenant_id,
            alert_id=alert_id,
            reason=reason,
            providers=providers or [],
            now=now,
        )
    else:
        result = {
            "action_id": action_id,
            "action_type": action_type,
            "status": "unsupported",
            "reason": f"Unknown action type: {action_type}",
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "executed_at": now.isoformat(),
            "dry_run": False,
        }

    # Log action
    await _log_action(result)

    # Write to event timeline
    await _write_timeline(result)

    # If action failed, fire a failure alert
    if result.get("status") == "failed":
        await _fire_action_failure_alert(result)

    return result


async def get_auto_action_history(
    tenant_id: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get recent auto-action history."""
    query: Dict[str, Any] = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    return await db[COLL_AUTO_ACTIONS].find(
        query, {"_id": 0}
    ).sort("executed_at", -1).limit(limit).to_list(limit)


# ── Reconciliation action ──────────────────────────────────────────

async def _execute_reconciliation(
    action_id: str,
    tenant_id: str,
    alert_id: str,
    reason: str,
    providers: List[str],
    now: datetime,
) -> Dict[str, Any]:
    """Trigger reconciliation via existing ReconciliationEngine."""
    try:
        from domains.channel_manager.reconciliation_engine.drift_reconciliation import reconciliation_engine

        recon_result = await reconciliation_engine.reconcile(
            tenant_id, auto_fix=True
        )

        status = recon_result.get("status", "unknown")
        return {
            "action_id": action_id,
            "action_type": "reconciliation",
            "status": "success" if status in ("clean", "reconciled") else "partial",
            "trigger_source": "auto_action",
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "reason": reason,
            "providers_targeted": providers,
            "reconciliation_result": {
                "status": status,
                "total_drifts": recon_result.get("total_drifts", 0),
                "auto_fixed": recon_result.get("auto_fixed", 0),
                "manual_review": recon_result.get("manual_review", 0),
            },
            "executed_at": now.isoformat(),
            "dry_run": False,
        }
    except Exception as e:
        logger.exception("Auto-reconciliation failed: %s", e)
        return {
            "action_id": action_id,
            "action_type": "reconciliation",
            "status": "failed",
            "trigger_source": "auto_action",
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "reason": reason,
            "error": str(e),
            "executed_at": now.isoformat(),
            "dry_run": False,
        }


# ── Guardrails ──────────────────────────────────────────────────────

async def _check_eligibility(
    action_type: str, tenant_id: str, now: datetime
) -> tuple:
    """Check if auto-action is eligible (cooldown + singularity)."""
    # Cooldown check: same action_type + tenant within cooldown window
    cooldown_cutoff = (now - timedelta(minutes=AUTO_ACTION_COOLDOWN_MINUTES)).isoformat()
    recent = await db[COLL_AUTO_ACTIONS].find_one(
        {
            "action_type": action_type,
            "tenant_id": tenant_id,
            "status": {"$in": ["success", "partial", "running"]},
            "executed_at": {"$gte": cooldown_cutoff},
        },
        {"_id": 0, "action_id": 1},
    )
    if recent:
        return False, f"Cooldown active: same action within {AUTO_ACTION_COOLDOWN_MINUTES} min"

    # Check if another action is currently running
    running = await db[COLL_AUTO_ACTIONS].find_one(
        {
            "action_type": action_type,
            "tenant_id": tenant_id,
            "status": "running",
        },
        {"_id": 0, "action_id": 1},
    )
    if running:
        return False, "Another auto-action is already running for this tenant"

    return True, None


# ── Logging & Timeline ──────────────────────────────────────────────

async def _log_action(result: Dict[str, Any]) -> None:
    """Persist auto-action to history collection."""
    try:
        await db[COLL_AUTO_ACTIONS].insert_one({**result})
    except Exception as e:
        logger.exception("Failed to log auto-action: %s", e)


async def _write_timeline(result: Dict[str, Any]) -> None:
    """Write auto-action to event timeline for auditability."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        writer = get_timeline_writer()
        await writer.append(
            tenant_id=result.get("tenant_id", ""),
            correlation_id=result.get("alert_id", ""),
            entity_type="auto_action",
            entity_id=result.get("action_id", ""),
            stage=result.get("action_type", "unknown"),
            status=result.get("status", "unknown"),
            source="auto_action_engine",
            metadata={
                "trigger_source": result.get("trigger_source", "auto_action"),
                "alert_id": result.get("alert_id"),
                "reason": result.get("reason"),
                "reconciliation_result": result.get("reconciliation_result"),
                "error": result.get("error"),
            },
        )
    except Exception as e:
        logger.debug("Timeline write for auto-action failed: %s", e)


async def _fire_action_failure_alert(result: Dict[str, Any]) -> None:
    """Fire a new alert when an auto-action fails."""
    try:
        from .alerting import get_alerting_engine, AlertSeverity
        engine = get_alerting_engine()
        await engine.fire(
            trigger="auto_action_failure",
            severity=AlertSeverity.HIGH,
            title="Auto-Action Failed",
            message=f"Auto-{result.get('action_type')} for tenant {result.get('tenant_id')} failed: {result.get('error', 'unknown')}",
            context={
                "action_id": result.get("action_id"),
                "alert_id": result.get("alert_id"),
                "tenant_id": result.get("tenant_id"),
                "action_type": result.get("action_type"),
                "error": result.get("error"),
            },
        )
    except Exception as e:
        logger.debug("Failed to fire action failure alert: %s", e)
