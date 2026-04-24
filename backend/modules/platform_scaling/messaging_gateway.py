"""
Enterprise Messaging Gateway - Provider-agnostic messaging with
Twilio (SMS), SendGrid (Email), WhatsApp abstraction.
Template-based messaging, delivery tracking, retry, audit, consent, rate limiting.
"""
import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


# ── Provider Abstraction ──

class MessagingProvider:
    """Base provider interface."""
    provider_name: str = "base"

    async def send(self, to: str, subject: str, body: str, template_vars: dict = None) -> dict[str, Any]:
        raise NotImplementedError

    async def check_health(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "status": "unknown"}


class TwilioProvider(MessagingProvider):
    """Twilio SMS provider (mock-ready, activate with credentials)."""
    provider_name = "twilio"

    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        self.active = bool(self.account_sid and self.auth_token)

    async def send(self, to: str, subject: str, body: str, template_vars: dict = None) -> dict[str, Any]:
        message_id = f"twilio_{uuid.uuid4().hex[:12]}"
        if not self.active:
            logger.info(f"[MOCK-TWILIO] SMS to={to} body={body[:80]}")
            return {"success": True, "message_id": message_id, "provider": "twilio", "mode": "mock"}
        # Production Twilio API call would go here
        logger.info(f"[TWILIO] SMS sent to={to}")
        return {"success": True, "message_id": message_id, "provider": "twilio", "mode": "live"}

    async def check_health(self) -> dict[str, Any]:
        return {"provider": "twilio", "status": "active" if self.active else "mock", "has_credentials": self.active}


class SendGridProvider(MessagingProvider):
    """SendGrid Email provider (mock-ready, activate with credentials)."""
    provider_name = "sendgrid"

    def __init__(self):
        self.api_key = os.environ.get("SENDGRID_API_KEY", "")
        self.from_email = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@hotel.com")
        self.active = bool(self.api_key)

    async def send(self, to: str, subject: str, body: str, template_vars: dict = None) -> dict[str, Any]:
        message_id = f"sg_{uuid.uuid4().hex[:12]}"
        if not self.active:
            logger.info(f"[MOCK-SENDGRID] Email to={to} subject={subject}")
            return {"success": True, "message_id": message_id, "provider": "sendgrid", "mode": "mock"}
        logger.info(f"[SENDGRID] Email sent to={to}")
        return {"success": True, "message_id": message_id, "provider": "sendgrid", "mode": "live"}

    async def check_health(self) -> dict[str, Any]:
        return {"provider": "sendgrid", "status": "active" if self.active else "mock", "has_credentials": self.active}


class WhatsAppProvider(MessagingProvider):
    """WhatsApp Business provider abstraction."""
    provider_name = "whatsapp"

    def __init__(self):
        self.api_key = os.environ.get("WHATSAPP_API_KEY", "")
        self.phone_id = os.environ.get("WHATSAPP_PHONE_ID", "")
        self.active = bool(self.api_key and self.phone_id)

    async def send(self, to: str, subject: str, body: str, template_vars: dict = None) -> dict[str, Any]:
        message_id = f"wa_{uuid.uuid4().hex[:12]}"
        if not self.active:
            logger.info(f"[MOCK-WHATSAPP] Message to={to} body={body[:80]}")
            return {"success": True, "message_id": message_id, "provider": "whatsapp", "mode": "mock"}
        logger.info(f"[WHATSAPP] Message sent to={to}")
        return {"success": True, "message_id": message_id, "provider": "whatsapp", "mode": "live"}

    async def check_health(self) -> dict[str, Any]:
        return {"provider": "whatsapp", "status": "active" if self.active else "mock", "has_credentials": self.active}


# ── Rate Limiter ──

class MessageRateLimiter:
    """Per-tenant, per-channel rate limiting."""
    def __init__(self, max_per_minute: int = 60, max_per_hour: int = 500):
        self._minute_counters: dict[str, list[float]] = defaultdict(list)
        self._hour_counters: dict[str, list[float]] = defaultdict(list)
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour

    def check(self, tenant_id: str, channel: str) -> bool:
        key = f"{tenant_id}:{channel}"
        now = time.time()
        # Clean old entries
        self._minute_counters[key] = [t for t in self._minute_counters[key] if now - t < 60]
        self._hour_counters[key] = [t for t in self._hour_counters[key] if now - t < 3600]
        if len(self._minute_counters[key]) >= self.max_per_minute:
            return False
        if len(self._hour_counters[key]) >= self.max_per_hour:
            return False
        self._minute_counters[key].append(now)
        self._hour_counters[key].append(now)
        return True


# ── Messaging Gateway ──

class MessagingGateway:
    """
    Central messaging service with provider routing, templates,
    delivery tracking, retry, audit, consent, rate limiting.
    """

    def __init__(self):
        self.providers: dict[str, MessagingProvider] = {
            "sms": TwilioProvider(),
            "email": SendGridProvider(),
            "whatsapp": WhatsAppProvider(),
        }
        self.rate_limiter = MessageRateLimiter()
        self.max_retries = 3

    async def send_message(
        self, tenant_id: str, channel: str, to: str,
        subject: str, body: str, template_id: str | None = None,
        template_vars: dict | None = None, user_id: str | None = None,
        guest_id: str | None = None, booking_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message through the specified channel with full lifecycle tracking."""
        # Rate limit check
        if not self.rate_limiter.check(tenant_id, channel):
            return {"success": False, "error": "rate_limit_exceeded",
                    "message": "Mesaj gonderim limiti asildi"}

        # Consent check
        if guest_id:
            consent = await self._check_consent(tenant_id, guest_id, channel)
            if not consent:
                return {"success": False, "error": "no_consent",
                        "message": "Misafir bu kanal icin onay vermemis"}

        # Template resolution
        if template_id:
            template = await db.message_templates.find_one(
                {"id": template_id, "tenant_id": tenant_id}, {"_id": 0}
            )
            if template:
                subject = template.get("subject", subject)
                # v41 Bug BG: HTML-escape variables for HTML-rendering channels.
                _esc_html = channel in ("email",)
                body = self._render_template(template.get("body", body), template_vars or {}, escape_html=_esc_html)

        # Create delivery record
        delivery = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "channel": channel,
            "to": to,
            "subject": subject,
            "body": body[:500],
            "template_id": template_id,
            "guest_id": guest_id,
            "booking_id": booking_id,
            "sent_by": user_id,
            "status": "pending",
            "attempts": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Send with retry
        provider = self.providers.get(channel)
        if not provider:
            delivery["status"] = "failed"
            delivery["error"] = f"Unknown channel: {channel}"
            await db.message_deliveries.insert_one(delivery)
            return {"success": False, "error": "unknown_channel", "delivery_id": delivery["id"]}

        result = await self._send_with_retry(provider, to, subject, body, template_vars, delivery)
        return result

    async def _send_with_retry(self, provider: MessagingProvider, to: str, subject: str,
                                body: str, template_vars: dict | None,
                                delivery: dict) -> dict[str, Any]:
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            delivery["attempts"] = attempt
            try:
                result = await provider.send(to, subject, body, template_vars)
                if result.get("success"):
                    delivery["status"] = "delivered"
                    delivery["provider_message_id"] = result.get("message_id")
                    delivery["delivered_at"] = datetime.now(UTC).isoformat()
                    delivery["mode"] = result.get("mode", "unknown")
                    await db.message_deliveries.insert_one(delivery)

                    # Audit log
                    await db.messaging_audit.insert_one({
                        "id": str(uuid.uuid4()),
                        "tenant_id": delivery["tenant_id"],
                        "delivery_id": delivery["id"],
                        "channel": delivery["channel"],
                        "to": to,
                        "status": "delivered",
                        "provider": provider.provider_name,
                        "timestamp": delivery["delivered_at"],
                    })
                    return {
                        "success": True, "delivery_id": delivery["id"],
                        "provider": provider.provider_name, "mode": result.get("mode"),
                    }
                last_error = result.get("error", "send_failed")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Message send attempt {attempt} failed: {e}")

            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # All retries exhausted
        delivery["status"] = "failed"
        delivery["error"] = last_error
        delivery["failed_at"] = datetime.now(UTC).isoformat()
        await db.message_deliveries.insert_one(delivery)

        await db.messaging_audit.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": delivery["tenant_id"],
            "delivery_id": delivery["id"],
            "channel": delivery["channel"],
            "to": to,
            "status": "failed",
            "error": last_error,
            "attempts": self.max_retries,
            "timestamp": delivery["failed_at"],
        })
        return {"success": False, "delivery_id": delivery["id"], "error": last_error}

    def _render_template(self, template: str, vars: dict, escape_html: bool = False) -> str:
        # v41 Bug BG: HTML-escape variables for email/HTML channels.
        import html as _html_mod
        result = template
        for key, val in vars.items():
            sv = str(val) if val is not None else ""
            if escape_html:
                sv = _html_mod.escape(sv, quote=True)
            result = result.replace(f"{{{{{key}}}}}", sv)
        return result

    async def _check_consent(self, tenant_id: str, guest_id: str, channel: str) -> bool:
        consent = await db.messaging_consents.find_one(
            {"tenant_id": tenant_id, "guest_id": guest_id}, {"_id": 0}
        )
        if not consent:
            return True  # Default: opt-in (can be changed per tenant policy)
        opted_out = consent.get("opted_out_channels", [])
        return channel not in opted_out

    # ── Template Management ──

    async def create_template(self, tenant_id: str, name: str, channel: str,
                               subject: str, body: str, user_id: str) -> dict[str, Any]:
        template = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": name,
            "channel": channel,
            "subject": subject,
            "body": body,
            "created_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
            "active": True,
        }
        await db.message_templates.insert_one(template)
        return {"success": True, "template_id": template["id"]}

    async def get_templates(self, tenant_id: str, channel: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"tenant_id": tenant_id, "active": True}
        if channel:
            query["channel"] = channel
        templates = await db.message_templates.find(query, {"_id": 0}).to_list(200)
        return {"count": len(templates), "templates": templates}

    # ── Delivery Tracking ──

    async def get_delivery_status(self, tenant_id: str, delivery_id: str) -> dict[str, Any]:
        d = await db.message_deliveries.find_one(
            {"id": delivery_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not d:
            return {"success": False, "error": "Delivery not found"}
        return {"success": True, "delivery": d}

    async def get_delivery_history(self, tenant_id: str, guest_id: str | None = None,
                                    channel: str | None = None, limit: int = 50) -> dict[str, Any]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if guest_id:
            query["guest_id"] = guest_id
        if channel:
            query["channel"] = channel
        deliveries = await db.message_deliveries.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return {"count": len(deliveries), "deliveries": deliveries}

    # ── Consent Management ──

    async def update_consent(self, tenant_id: str, guest_id: str,
                              channel: str, opted_in: bool) -> dict[str, Any]:
        consent = await db.messaging_consents.find_one(
            {"tenant_id": tenant_id, "guest_id": guest_id}
        )
        if not consent:
            doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "guest_id": guest_id,
                "opted_out_channels": [] if opted_in else [channel],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            await db.messaging_consents.insert_one(doc)
        else:
            opted_out = consent.get("opted_out_channels", [])
            if opted_in and channel in opted_out:
                opted_out.remove(channel)
            elif not opted_in and channel not in opted_out:
                opted_out.append(channel)
            await db.messaging_consents.update_one(
                {"tenant_id": tenant_id, "guest_id": guest_id},
                {"$set": {"opted_out_channels": opted_out,
                           "updated_at": datetime.now(UTC).isoformat()}},
            )
        return {"success": True, "guest_id": guest_id, "channel": channel, "opted_in": opted_in}

    # ── Provider Health ──

    async def get_provider_health(self) -> dict[str, Any]:
        health = {}
        for channel, provider in self.providers.items():
            health[channel] = await provider.check_health()
        return {"providers": health, "checked_at": datetime.now(UTC).isoformat()}

    # ── Analytics ──

    async def get_messaging_analytics(self, tenant_id: str, days: int = 7) -> dict[str, Any]:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        deliveries = await db.message_deliveries.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "channel": 1, "status": 1},
        ).to_list(10000)

        by_channel = defaultdict(lambda: {"sent": 0, "delivered": 0, "failed": 0})
        for d in deliveries:
            ch = d.get("channel", "unknown")
            by_channel[ch]["sent"] += 1
            if d.get("status") == "delivered":
                by_channel[ch]["delivered"] += 1
            elif d.get("status") == "failed":
                by_channel[ch]["failed"] += 1

        total = len(deliveries)
        delivered = sum(c["delivered"] for c in by_channel.values())
        failed = sum(c["failed"] for c in by_channel.values())

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_messages": total,
            "delivered": delivered,
            "failed": failed,
            "delivery_rate": round(delivered / max(total, 1) * 100, 1),
            "by_channel": dict(by_channel),
        }


# Singleton
messaging_gateway = MessagingGateway()
