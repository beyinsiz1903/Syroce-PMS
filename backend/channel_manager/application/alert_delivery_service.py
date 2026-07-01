"""
Alert Delivery Service — Real notification delivery for alerting engine.

Delivery Channels:
  - Email (SMTP/API)
  - Webhook (generic HTTP POST)
  - Slack webhook
  - Microsoft Teams webhook

Features:
  - Severity-based filtering per channel
  - Alert deduplication (fingerprint-based)
  - Throttling (per-channel rate limit)
  - Delivery retry with exponential backoff
  - Delivery audit log
  - Tenant + connector-scoped channel configuration
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.alert_delivery")

DELIVERY_LOG = "cm_alert_delivery_log"
DELIVERY_CHANNELS = "cm_alert_delivery_channels"
DELIVERY_FINGERPRINTS = "cm_alert_fingerprints"
_NO_ID = {"_id": 0}

# Throttle defaults
DEFAULT_THROTTLE_SECONDS = 300  # 5 min per channel+trigger combo
MAX_DELIVERY_RETRIES = 3


class AlertDeliveryService:
    """Delivers alert notifications through configured channels."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    # ─── Channel Configuration ─────────────────────────────────────────

    async def get_channels(self, tenant_id: str, connector_id: str | None = None) -> list[dict]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[DELIVERY_CHANNELS].find(q, _NO_ID).to_list(50)

    async def upsert_channel(self, tenant_id: str, channel_data: dict[str, Any]) -> dict:
        channel = {
            "id": channel_data.get("id") or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": channel_data.get("connector_id", "*"),
            "channel_type": channel_data["channel_type"],
            "name": channel_data.get("name", ""),
            "enabled": channel_data.get("enabled", True),
            "min_severity": channel_data.get("min_severity", "warning"),
            "config": channel_data.get("config", {}),
            "throttle_seconds": channel_data.get("throttle_seconds", DEFAULT_THROTTLE_SECONDS),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await db[DELIVERY_CHANNELS].replace_one(
            {"tenant_id": tenant_id, "id": channel["id"]},
            channel,
            upsert=True,
        )
        channel.pop("_id", None)
        return channel

    async def delete_channel(self, tenant_id: str, channel_id: str) -> bool:
        r = await db[DELIVERY_CHANNELS].delete_one({"tenant_id": tenant_id, "id": channel_id})
        return r.deleted_count > 0

    # ─── Delivery Orchestration ────────────────────────────────────────

    async def deliver_alert(self, tenant_id: str, alert: dict[str, Any]) -> dict[str, Any]:
        """Deliver an alert to all matching channels with filtering, dedup, throttle."""
        connector_id = alert.get("connector_id", "")
        severity = alert.get("severity", "info")
        trigger = alert.get("trigger", "")
        alert_id = alert.get("id", "")

        # Get applicable channels
        channels = await self._get_applicable_channels(tenant_id, connector_id)
        if not channels:
            return {"delivered": 0, "skipped": 0, "reason": "no_channels_configured"}

        severity_order = {"info": 0, "warning": 1, "critical": 2}
        alert_severity = severity_order.get(severity, 0)

        delivered = 0
        skipped = 0
        results = []

        for ch in channels:
            if not ch.get("enabled", True):
                skipped += 1
                continue

            # Severity filter
            min_sev = severity_order.get(ch.get("min_severity", "info"), 0)
            if alert_severity < min_sev:
                skipped += 1
                continue

            # Deduplication check
            fingerprint = self._make_fingerprint(tenant_id, ch["id"], trigger, connector_id)
            if await self._is_duplicate(fingerprint):
                skipped += 1
                continue

            # Throttle check
            throttle_secs = ch.get("throttle_seconds", DEFAULT_THROTTLE_SECONDS)
            if await self._is_throttled(tenant_id, ch["id"], trigger, throttle_secs):
                skipped += 1
                continue

            # Deliver with retry
            success = await self._deliver_with_retry(ch, alert)
            await self._log_delivery(tenant_id, alert_id, ch, success)
            await self._store_fingerprint(fingerprint, throttle_secs)

            if success:
                delivered += 1
            results.append(
                {
                    "channel_id": ch["id"],
                    "channel_type": ch["channel_type"],
                    "success": success,
                }
            )

        return {
            "alert_id": alert_id,
            "delivered": delivered,
            "skipped": skipped,
            "total_channels": len(channels),
            "results": results,
        }

    async def _get_applicable_channels(self, tenant_id: str, connector_id: str) -> list[dict]:
        """Get channels that apply to this tenant/connector."""
        all_channels = (
            await db[DELIVERY_CHANNELS]
            .find(
                {"tenant_id": tenant_id},
                _NO_ID,
            )
            .to_list(50)
        )
        applicable = []
        for ch in all_channels:
            ch_connector = ch.get("connector_id", "*")
            if ch_connector == "*" or ch_connector == connector_id:
                applicable.append(ch)
        return applicable

    # ─── Channel Dispatchers ───────────────────────────────────────────

    async def _deliver_with_retry(self, channel: dict, alert: dict) -> bool:
        """Attempt delivery with exponential backoff retry."""
        ch_type = channel.get("channel_type", "")
        for attempt in range(MAX_DELIVERY_RETRIES):
            try:
                if ch_type == "email":
                    return await self._deliver_email(channel, alert)
                elif ch_type == "webhook":
                    return await self._deliver_webhook(channel, alert)
                elif ch_type == "slack":
                    return await self._deliver_slack(channel, alert)
                elif ch_type == "teams":
                    return await self._deliver_teams(channel, alert)
                else:
                    logger.warning("Unknown channel type: %s", ch_type)
                    return False
            except Exception as e:
                logger.warning(
                    "Delivery attempt %d/%d failed for channel %s: %s",
                    attempt + 1,
                    MAX_DELIVERY_RETRIES,
                    channel.get("id"),
                    e,
                )
                if attempt < MAX_DELIVERY_RETRIES - 1:
                    await asyncio.sleep(min(2**attempt, 10))
        return False

    async def _deliver_email(self, channel: dict, alert: dict) -> bool:
        """Deliver alert via email (SMTP or API)."""
        config = channel.get("config", {})
        to_email = config.get("to_email", "")
        smtp_host = config.get("smtp_host", "")
        api_key = config.get("api_key", "")

        if not to_email:
            logger.warning("Email channel %s: no to_email configured", channel.get("id"))
            return False

        subject = f"[{alert.get('severity', 'info').upper()}] {alert.get('trigger', 'Alert')}"
        body = self._format_email_body(alert)

        if api_key:
            return await self._send_email_api(config, to_email, subject, body)

        if smtp_host:
            return await self._send_email_smtp(config, to_email, subject, body)

        logger.warning("Email channel %s: no smtp_host or api_key configured", channel.get("id"))
        return False

    async def _send_email_api(self, config: dict, to: str, subject: str, body: str) -> bool:
        """Send email via generic API (SendGrid-compatible)."""
        api_key = config.get("api_key", "")
        from_email = config.get("from_email", "alerts@syroce.com")
        api_url = config.get("api_url", "https://api.sendgrid.com/v3/mail/send")

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": body}],
        }
        # v109 Bug DAL round-7 follow-up #3: api_url is tenant-configurable
        # (defaults to SendGrid). Rebinding-safe POST.
        from integrations.xchange.safety import EgressDenied, safe_post_async

        try:
            resp = await safe_post_async(
                api_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
        except EgressDenied as _e:
            logger.warning("Email API delivery blocked (SSRF guard): %s", _e)
            return False
        return resp.status_code in (200, 201, 202)

    async def _send_email_smtp(self, config: dict, to: str, subject: str, body: str) -> bool:
        """Send email via SMTP (asyncio-compatible)."""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", 587))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_pass", "")
        from_email = config.get("from_email", smtp_user)

        # v109 round-7 follow-up: validate tenant-supplied SMTP host against
        # SSRF/DNS-rebinding policy. Connect to pinned IP, not the hostname.
        from integrations.xchange.safety import EgressDenied, assert_safe_host

        try:
            pinned_ip = assert_safe_host(smtp_host, smtp_port)
        except EgressDenied as eg:
            logger.warning("SMTP egress denied for %s: %s", smtp_host, eg)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to
        msg.attach(MIMEText(body, "html"))

        loop = asyncio.get_event_loop()
        try:

            def _send():
                with smtplib.SMTP(pinned_ip, smtp_port) as server:
                    server.starttls()
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(from_email, [to], msg.as_string())

            await loop.run_in_executor(None, _send)
            return True
        except Exception as e:
            logger.error("SMTP send failed: %s", e)
            return False

    async def _deliver_webhook(self, channel: dict, alert: dict) -> bool:
        """Deliver alert via generic webhook (HTTP POST)."""
        config = channel.get("config", {})
        url = config.get("url", "")
        if not url:
            return False

        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")
        secret = config.get("secret", "")

        payload = {
            "event": "alert",
            "alert_id": alert.get("id", ""),
            "severity": alert.get("severity", ""),
            "trigger": alert.get("trigger", ""),
            "connector_id": alert.get("connector_id", ""),
            "description": alert.get("description", ""),
            "created_at": alert.get("created_at", ""),
            "metadata": alert.get("metadata", {}),
        }

        if secret:
            import hmac

            sig = hmac.new(secret.encode(), str(payload).encode(), hashlib.sha256).hexdigest()
            headers["X-Signature"] = sig

        # v109 Bug DAL round-7 (T12 SSRF + rebinding follow-up): tenant admins
        # can configure arbitrary webhook URLs. ``safe_post_async`` validates
        # scheme + every resolved IP, then pins the connection to the
        # validated IP so a hostname can't rebind to 169.254.169.254 between
        # validation and the actual TCP connect.
        from integrations.xchange.safety import EgressDenied, safe_post_async

        try:
            resp = await safe_post_async(url, json=payload, headers=headers)
        except EgressDenied as _e:
            logger.warning("Webhook delivery blocked (SSRF guard): %s", _e)
            return False
        return 200 <= resp.status_code < 300

    async def _deliver_slack(self, channel: dict, alert: dict) -> bool:
        """Deliver alert via Slack incoming webhook."""
        config = channel.get("config", {})
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return False

        severity = alert.get("severity", "info")
        color = {"critical": "#dc2626", "warning": "#f59e0b", "info": "#3b82f6"}.get(severity, "#6b7280")
        emoji = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":information_source:"}.get(severity, ":bell:")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} {alert.get('trigger', 'Alert').replace('_', ' ').title()}"}},
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Severity:* {severity.upper()}"},
                                {"type": "mrkdwn", "text": f"*Connector:* {alert.get('connector_id', 'N/A')}"},
                                {"type": "mrkdwn", "text": f"*Description:* {alert.get('description', '')}"},
                                {"type": "mrkdwn", "text": f"*Time:* {alert.get('created_at', '')}"},
                            ],
                        },
                    ],
                }
            ],
        }
        # v109 Bug DAL round-7 (T12 SSRF + rebinding follow-up). See
        # _deliver_webhook for full rationale; Slack webhooks should be on
        # hooks.slack.com but ``safe_post_async`` defends against operator
        # misconfig and rebinding attacks alike.
        from integrations.xchange.safety import EgressDenied, safe_post_async

        try:
            resp = await safe_post_async(webhook_url, json=payload)
        except EgressDenied as _e:
            logger.warning("Slack delivery blocked (SSRF guard): %s", _e)
            return False
        return resp.status_code == 200

    async def _deliver_teams(self, channel: dict, alert: dict) -> bool:
        """Deliver alert via Microsoft Teams incoming webhook."""
        config = channel.get("config", {})
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return False

        severity = alert.get("severity", "info")
        color = {"critical": "dc2626", "warning": "f59e0b", "info": "3b82f6"}.get(severity, "6b7280")

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"Alert: {alert.get('trigger', '')}",
            "sections": [
                {
                    "activityTitle": f"Channel Manager Alert: {alert.get('trigger', '').replace('_', ' ').title()}",
                    "facts": [
                        {"name": "Severity", "value": severity.upper()},
                        {"name": "Connector", "value": alert.get("connector_id", "N/A")},
                        {"name": "Description", "value": alert.get("description", "")},
                        {"name": "Time", "value": alert.get("created_at", "")},
                    ],
                    "markdown": True,
                }
            ],
        }
        # v109 Bug DAL round-7 (T12 SSRF + rebinding follow-up). See
        # _deliver_webhook for full rationale.
        from integrations.xchange.safety import EgressDenied, safe_post_async

        try:
            resp = await safe_post_async(webhook_url, json=payload)
        except EgressDenied as _e:
            logger.warning("Teams delivery blocked (SSRF guard): %s", _e)
            return False
        return resp.status_code == 200

    # ─── Deduplication & Throttle ──────────────────────────────────────

    @staticmethod
    def _make_fingerprint(tenant_id: str, channel_id: str, trigger: str, connector_id: str) -> str:
        raw = f"{tenant_id}:{channel_id}:{trigger}:{connector_id}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _is_duplicate(self, fingerprint: str) -> bool:
        existing = await db[DELIVERY_FINGERPRINTS].find_one(
            {"fingerprint": fingerprint, "expires_at": {"$gt": datetime.now(UTC).isoformat()}},
        )
        return existing is not None

    async def _store_fingerprint(self, fingerprint: str, ttl_seconds: int):
        expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        await db[DELIVERY_FINGERPRINTS].replace_one(
            {"fingerprint": fingerprint},
            {"fingerprint": fingerprint, "expires_at": expires},
            upsert=True,
        )

    async def _is_throttled(self, tenant_id: str, channel_id: str, trigger: str, throttle_secs: int) -> bool:
        cutoff = (datetime.now(UTC) - timedelta(seconds=throttle_secs)).isoformat()
        recent = await db[DELIVERY_LOG].find_one(
            {
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "trigger": trigger,
                "delivered_at": {"$gte": cutoff},
                "success": True,
            }
        )
        return recent is not None

    # ─── Audit & Logging ──────────────────────────────────────────────

    async def _log_delivery(self, tenant_id: str, alert_id: str, channel: dict, success: bool):
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "channel_id": channel.get("id", ""),
            "channel_type": channel.get("channel_type", ""),
            "trigger": "",
            "success": success,
            "delivered_at": datetime.now(UTC).isoformat(),
        }
        await db[DELIVERY_LOG].insert_one(doc)

    async def get_delivery_log(
        self,
        tenant_id: str,
        alert_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if alert_id:
            q["alert_id"] = alert_id
        return await db[DELIVERY_LOG].find(q, _NO_ID).sort("delivered_at", -1).to_list(limit)

    # ─── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _format_email_body(alert: dict) -> str:
        # Bug CN (architect Round-2): connector_id/description/created_at,
        # external connector payload tarafından (HotelRunner vs.) etkilenebilir
        # — `description` özellikle vendor error message'ından geliyor, yani
        # 3rd-party kontrolünde. Outbound HTML'e raw zerk operatör inbox'ında
        # phishing/XSS riski. Tüm dinamik alanları HTML-escape ediyoruz.
        from core.mailing_safe import safe_html_value

        severity = alert.get("severity", "info").upper()
        trigger = safe_html_value(alert.get("trigger", "Alert").replace("_", " ").title())
        connector_id = safe_html_value(alert.get("connector_id", "N/A"))
        description = safe_html_value(alert.get("description", ""))
        created_at = safe_html_value(alert.get("created_at", ""))
        return f"""
        <div style="font-family: sans-serif; max-width: 600px;">
            <div style="background: {"#dc2626" if severity == "CRITICAL" else "#f59e0b" if severity == "WARNING" else "#3b82f6"};
                        color: white; padding: 16px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0;">{severity}: {trigger}</h2>
            </div>
            <div style="border: 1px solid #e5e7eb; padding: 16px; border-radius: 0 0 8px 8px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; font-weight: bold;">Connector:</td><td style="padding: 8px;">{connector_id}</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">Description:</td><td style="padding: 8px;">{description}</td></tr>
                    <tr><td style="padding: 8px; font-weight: bold;">Time:</td><td style="padding: 8px;">{created_at}</td></tr>
                </table>
                <p style="color: #6b7280; font-size: 12px; margin-top: 16px;">Syroce PMS Alert System</p>
            </div>
        </div>
        """
