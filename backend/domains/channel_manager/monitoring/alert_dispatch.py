"""
Operational Monitoring — Alert Dispatch Service
=================================================

Delivers alerts to configured channels:
  - Dashboard (primary — always on)
  - Slack webhook (optional, configurable per tenant or via env)
  - Email via Resend (optional, configurable per tenant or via env)

Dispatch architecture:
  Alert Engine → Dispatch Service
                    ├── Dashboard (always)
                    ├── Slack (optional, tenant-config or OPS_ALERT_SLACK_WEBHOOK_URL)
                    └── Email (optional, tenant-config or OPS_ALERT_EMAIL_TO)
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

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
        {"tenant_id": tenant_id},
        _NO_ID,
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

    # v109 Bug DAL round-7 follow-up #3: webhook_url is tenant-configurable.
    from integrations.xchange.safety import EgressDenied, safe_post_async

    try:
        resp = await safe_post_async(webhook_url, timeout=10.0, json=payload)
        if resp.status_code == 200:
            return {"success": True, "message": "Test message sent to Slack"}
        return {"success": False, "message": f"Slack returned HTTP {resp.status_code}"}
    except EgressDenied as e:
        return {"success": False, "message": f"SSRF engellendi: {e}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Alert Dispatch ────────────────────────────────────────────────────


def _csv_env(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


# Keys whose value should be masked before rendering an alert payload to
# any external channel. Matches as a case-insensitive substring so e.g.
# "last_publish_error" and "REDIS_URL" both get redacted. Operators get a
# placeholder ("***") so they still know the field was present.
_REDACT_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "url",
    "uri",
    "dsn",
    "credential",
    "cookie",
    "session",
    "error",
    "stack",
    "trace",
)


def _redact_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of ``context`` with sensitive values masked.

    External notification channels (email/Slack) leave Replit's egress —
    we must never include raw provider URLs, tokens, exception strings or
    upstream error messages that may carry credentials.
    """
    if not context:
        return {}
    safe: dict[str, Any] = {}
    for key, value in context.items():
        lk = str(key).lower()
        if any(sub in lk for sub in _REDACT_SUBSTRINGS):
            safe[key] = "***"
            continue
        safe[key] = value
    return safe


async def dispatch_alert(alert: dict[str, Any], tenant_id: str = "system") -> dict[str, Any]:
    """
    Dispatch an alert to all configured channels.
    Called by the alert engine when a new alert is created.

    Channel selection order:
      1. Per-tenant config in `alert_dispatch_config` collection (admin UI):
            * If a doc exists and a channel is explicitly ``enabled: false``
              we honour that — the tenant has opted out and we will NOT
              fall back to env vars for that channel.
            * If a doc exists with ``enabled: true`` but the channel target
              is empty, we treat the channel as misconfigured (no-op) and
              also do not fall back.
      2. Env-var fallback (only when no tenant doc exists at all):
           - OPS_ALERT_SLACK_WEBHOOK_URL  (single webhook URL)
           - OPS_ALERT_EMAIL_TO           (comma-separated recipients)
           - OPS_ALERT_MIN_SEVERITY       (critical|high|warning|info,
                                           default: warning)

    A "warning"-or-higher severity floor is enforced for the env fallback so
    the inbox isn't flooded by INFO-level signals like stale datasets.

    All outbound payloads (email + Slack) flow through ``_redact_context``
    so secrets, URLs, tokens and raw exception strings never leave the
    egress boundary.
    """
    result = {"dashboard": True, "slack": False, "email": False}

    # Read raw doc to distinguish "no config" from "config with disabled
    # channel" — get_dispatch_config returns a synthesised default in
    # both cases, so we can't rely on it for that distinction.
    raw_doc = await db[COLL_ALERT_CONFIG].find_one(
        {"tenant_id": tenant_id},
        _NO_ID,
    )
    has_tenant_config = raw_doc is not None
    config = raw_doc or await get_dispatch_config(tenant_id)

    severity = alert.get("severity", "info")
    safe_alert = dict(alert)
    safe_alert["context"] = _redact_context(alert.get("context"))

    # ── Slack ──────────────────────────────────────────────────────
    slack_config = config.get("slack", {}) or {}
    slack_url = ""
    slack_allowed = slack_config.get("severities", DEFAULT_SLACK_SEVERITIES)
    if slack_config.get("enabled"):
        slack_url = (slack_config.get("webhook_url") or "").strip()
    elif not has_tenant_config:
        env_url = os.environ.get("OPS_ALERT_SLACK_WEBHOOK_URL", "").strip()
        if env_url:
            slack_url = env_url
            slack_allowed = _env_severity_allowlist()

    if slack_url and severity in slack_allowed:
        result["slack"] = await _send_slack_alert(slack_url, safe_alert)

    # ── Email ──────────────────────────────────────────────────────
    email_config = config.get("email", {}) or {}
    recipients: list[str] = []
    email_allowed = email_config.get("severities", ["critical"])
    if email_config.get("enabled"):
        recipients = [r for r in (email_config.get("recipients") or []) if r]
    elif not has_tenant_config:
        env_recipients = _csv_env("OPS_ALERT_EMAIL_TO")
        if env_recipients:
            recipients = env_recipients
            email_allowed = _env_severity_allowlist()

    if recipients and severity in email_allowed:
        result["email"] = await _send_email_alert(recipients, safe_alert)

    return result


def _env_severity_allowlist() -> list[str]:
    """Resolve env fallback severity floor → allow list (descending)."""
    floor = (os.environ.get("OPS_ALERT_MIN_SEVERITY") or "warning").lower()
    order = ["info", "warning", "high", "critical"]
    if floor not in order:
        floor = "warning"
    return order[order.index(floor) :]


async def _send_email_alert(recipients: list[str], alert: dict[str, Any]) -> bool:
    """Send an alert summary email via Resend (core.email)."""
    if not recipients:
        return False

    from core.email import send_email

    severity = (alert.get("severity") or "info").upper()
    title = alert.get("title") or "Alert"
    message = alert.get("message") or alert.get("details") or ""
    alert_type = alert.get("alert_type") or ""
    runbook = alert.get("runbook_hint") or ""
    context = alert.get("context") or {}
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    subject = f"[Syroce {severity}] {title}"
    ctx_lines = "".join(f"<li><code>{k}</code>: {str(v)[:300]}</li>" for k, v in context.items()) or "<li><em>none</em></li>"
    html = (
        f"<h2>{title}</h2>"
        f"<p><strong>Severity:</strong> {severity}<br>"
        f"<strong>Type:</strong> <code>{alert_type}</code><br>"
        f"<strong>When:</strong> {ts}</p>"
        f"<p>{message}</p>" + (f"<p><em>Runbook:</em> {runbook}</p>" if runbook else "") + f"<details><summary>Context</summary><ul>{ctx_lines}</ul></details>"
    )
    text = f"{title}\nSeverity: {severity}\nType: {alert_type}\nWhen: {ts}\n\n{message}\n" + (f"Runbook: {runbook}\n" if runbook else "")

    sent_any = False
    for addr in recipients:
        try:
            res = await send_email(addr, subject, html, text=text)
            if res.get("sent"):
                sent_any = True
            else:
                logger.warning(
                    "alert email send returned not-sent: to=%s err=%s",
                    addr,
                    res.get("error"),
                )
        except Exception as exc:
            logger.exception("alert email send failed to=%s: %s", addr, exc)
    return sent_any


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
                                f"*Details:* {alert.get('message') or alert.get('details') or ''}"
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

    # v109 Bug DAL round-7 follow-up #3: webhook_url is tenant-configurable.
    from integrations.xchange.safety import EgressDenied, safe_post_async

    try:
        resp = await safe_post_async(webhook_url, timeout=10.0, json=payload)
        if resp.status_code == 200:
            logger.info(f"Slack alert sent: {alert.get('title')}")
            return True
        logger.warning(f"Slack webhook returned {resp.status_code}")
        return False
    except EgressDenied as e:
        logger.warning(f"Slack dispatch blocked (SSRF guard): {e}")
        return False
    except Exception as e:
        logger.error(f"Slack dispatch error: {e}")
        return False
