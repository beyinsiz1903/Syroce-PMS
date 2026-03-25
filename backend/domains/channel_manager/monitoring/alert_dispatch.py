"""
Operational Monitoring — Alert Dispatch Service
=================================================

Delivers alerts to configured channels:
  - Dashboard (primary — always on)
  - Slack webhook (optional, configurable)
  - Email (future)

Dispatch architecture:
  Alert Engine → Dispatch Service
                    ├── Dashboard (always)
                    ├── Slack (optional)
                    └── Email (future)
"""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from core.database import db

logger = logging.getLogger("monitoring.dispatch")

COLL_ALERT_CONFIG = "alert_dispatch_config"
_NO_ID = {"_id": 0}

# ── Severity → Slack emoji/color mapping ─────────────────────────────

SLACK_SEVERITY = {
    "critical": {"emoji": ":rotating_light:", "color": "#dc2626"},
    "high": {"emoji": ":warning:", "color": "#f59e0b"},
    "medium": {"emoji": ":large_blue_circle:", "color": "#3b82f6"},
    "info": {"emoji": ":information_source:", "color": "#6b7280"},
}

# Default severity filter (which severities trigger Slack)
DEFAULT_SLACK_SEVERITIES = ["critical", "high"]


# ── Configuration CRUD ────────────────────────────────────────────────

async def get_dispatch_config(tenant_id: str = "system") -> dict[str, Any]:
    """Get alert dispatch configuration."""
    config = await db[COLL_ALERT_CONFIG].find_one(
        {"tenant_id": tenant_id}, _NO_ID,
    )
    if not config:
        return {
            "tenant_id": tenant_id,
            "slack": {
                "enabled": False,
                "webhook_url": "",
                "severities": DEFAULT_SLACK_SEVERITIES,
                "channel_name": "",
            },
            "email": {
                "enabled": False,
                "recipients": [],
                "severities": ["critical"],
            },
        }
    return config


async def update_dispatch_config(
    tenant_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Update alert dispatch configuration."""
    config["tenant_id"] = tenant_id
    config["updated_at"] = datetime.now(UTC).isoformat()

    await db[COLL_ALERT_CONFIG].replace_one(
        {"tenant_id": tenant_id},
        config,
        upsert=True,
    )
    return config


async def test_slack_webhook(webhook_url: str) -> dict[str, Any]:
    """Send a test message to the Slack webhook."""
    payload = {
        "text": ":white_check_mark: *Syroce PMS — Slack Alert Test*\nThis is a test message from the Channel Manager monitoring system.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":white_check_mark: *Slack Alert Test Successful*\n"
                        "*System:* Syroce PMS Channel Manager\n"
                        "*Time:* " + datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC") + "\n"
                        "Alert notifications are now configured."
                    ),
                },
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                return {"success": True, "message": "Test message sent to Slack"}
            return {"success": False, "message": f"Slack returned HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Alert Dispatch ────────────────────────────────────────────────────

async def dispatch_alert(alert: dict[str, Any], tenant_id: str = "system") -> dict[str, Any]:
    """
    Dispatch an alert to all configured channels.
    Called by the alert engine when a new alert is created.
    """
    result = {"dashboard": True, "slack": False, "email": False}

    config = await get_dispatch_config(tenant_id)
    severity = alert.get("severity", "info")

    # Slack dispatch
    slack_config = config.get("slack", {})
    if slack_config.get("enabled") and slack_config.get("webhook_url"):
        allowed = slack_config.get("severities", DEFAULT_SLACK_SEVERITIES)
        if severity in allowed:
            result["slack"] = await _send_slack_alert(
                slack_config["webhook_url"], alert,
            )

    return result


async def _send_slack_alert(webhook_url: str, alert: dict[str, Any]) -> bool:
    """Send formatted alert to Slack via incoming webhook."""
    if not webhook_url:
        return False

    severity = alert.get("severity", "info")
    style = SLACK_SEVERITY.get(severity, SLACK_SEVERITY["info"])

    payload = {
        "text": f"{style['emoji']} *Channel Manager Alert — {severity.upper()}*",
        "attachments": [
            {
                "color": style["color"],
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{style['emoji']} *{alert.get('title', 'Alert')}*\n"
                                f"*Severity:* `{severity}`\n"
                                f"*Provider:* {alert.get('provider', 'system') or 'system'}\n"
                                f"*Type:* `{alert.get('alert_type', '')}`\n"
                                f"*Details:* {alert.get('details', '')}"
                            ),
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Syroce PMS | {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                            },
                        ],
                    },
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Slack alert sent: {alert.get('title')}")
                return True
            logger.warning(f"Slack webhook returned {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Slack dispatch error: {e}")
        return False
