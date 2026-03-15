"""
Operational Monitoring — Alert Dispatch
=========================================

Delivers alerts to configured channels:
  - Dashboard (primary — always on)
  - Slack webhook (optional)
  - Email (optional)
"""
import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger("monitoring.dispatch")


async def dispatch_to_slack(
    webhook_url: str,
    alert: Dict[str, Any],
) -> bool:
    """Send alert to Slack via incoming webhook."""
    if not webhook_url:
        return False

    severity = alert.get("severity", "info")
    emoji_map = {"critical": ":rotating_light:", "high": ":warning:", "medium": ":large_blue_circle:", "info": ":information_source:"}
    emoji = emoji_map.get(severity, ":bell:")

    payload = {
        "text": f"{emoji} *Channel Manager Alert*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{alert.get('title', 'Alert')}*\n"
                        f"*Severity:* `{severity}`\n"
                        f"*Provider:* {alert.get('provider', 'system')}\n"
                        f"*Type:* `{alert.get('alert_type', '')}`\n"
                        f"*Details:* {alert.get('details', '')}"
                    ),
                },
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
