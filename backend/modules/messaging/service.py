"""
Messaging service – orchestrates sending, retry, consent, rate limiting, fallback.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from .models import (
    DeliveryStatus, MessageChannel, new_delivery_log, ConsentStatus,
)
from .providers import PROVIDER_MAP, CHANNEL_PROVIDER_MAP, FALLBACK_CHAIN

logger = logging.getLogger(__name__)


class MessagingService:
    """Central orchestrator for all outbound messaging."""

    def __init__(self, db):
        self.db = db
        self._rate_counters: Dict[str, int] = {}

    # ── helpers ──

    async def _get_provider_config(self, tenant_id: str, provider_type: str) -> Optional[dict]:
        return await self.db.messaging_provider_configs.find_one(
            {"tenant_id": tenant_id, "provider_type": provider_type, "enabled": True},
            {"_id": 0},
        )

    async def _check_consent(self, tenant_id: str, recipient: str, channel: str) -> bool:
        """Check if the recipient has opted-in for this channel."""
        doc = await self.db.messaging_consents.find_one(
            {"tenant_id": tenant_id, "recipient": recipient, "channel": channel},
            {"_id": 0},
        )
        if not doc:
            return True  # no explicit opt-out => allow
        return doc.get("status") != ConsentStatus.OPT_OUT.value

    async def _check_rate_limit(self, tenant_id: str, provider_type: str, limit: int = 60) -> bool:
        key = f"{tenant_id}:{provider_type}"
        count = self._rate_counters.get(key, 0)
        if count >= limit:
            return False
        self._rate_counters[key] = count + 1
        return True

    def _render_template(self, body_template: str, variables: dict) -> str:
        result = body_template
        for k, v in variables.items():
            result = result.replace(f"{{{{{k}}}}}", str(v))
        return result

    # ── main send ──

    async def send_message(
        self,
        tenant_id: str,
        channel: str,
        recipient: str,
        body: Optional[str] = None,
        subject: Optional[str] = None,
        template_id: Optional[str] = None,
        variables: dict = None,
        booking_id: Optional[str] = None,
        guest_id: Optional[str] = None,
        property_id: Optional[str] = None,
        use_case: Optional[str] = None,
    ) -> dict:
        """Send a message via the requested channel with fallback support."""
        variables = variables or {}

        # resolve template
        if template_id:
            tmpl = await self.db.messaging_templates.find_one(
                {"id": template_id, "tenant_id": tenant_id, "is_active": True},
                {"_id": 0},
            )
            if tmpl:
                body = self._render_template(tmpl.get("body_template", ""), variables)
                subject = subject or tmpl.get("subject")

        if not body:
            return {"success": False, "error": "No message body"}

        # consent check
        if not await self._check_consent(tenant_id, recipient, channel):
            return {"success": False, "error": "Recipient opted out"}

        # determine provider
        provider_type = CHANNEL_PROVIDER_MAP.get(channel)
        if not provider_type:
            return {"success": False, "error": f"Unknown channel: {channel}"}

        config = await self._get_provider_config(tenant_id, provider_type)

        # create delivery log
        log_doc = new_delivery_log(
            tenant_id=tenant_id,
            property_id=property_id,
            channel=channel,
            provider_type=provider_type,
            recipient=recipient,
            template_id=template_id,
            subject=subject,
            body=body,
            booking_id=booking_id,
            guest_id=guest_id,
            use_case=use_case,
        )

        if not config:
            log_doc["status"] = DeliveryStatus.FAILED.value
            log_doc["error_message"] = f"No active provider config for {provider_type}"
            await self.db.messaging_delivery_logs.insert_one(log_doc)
            # attempt fallback
            return await self._try_fallback(
                tenant_id, channel, recipient, body, subject, log_doc, booking_id, guest_id, property_id, use_case
            )

        # rate limit
        rl = config.get("rate_limit_per_minute", 60)
        if not await self._check_rate_limit(tenant_id, provider_type, rl):
            log_doc["status"] = DeliveryStatus.FAILED.value
            log_doc["error_message"] = "Rate limit exceeded"
            await self.db.messaging_delivery_logs.insert_one(log_doc)
            return {"success": False, "error": "Rate limit exceeded", "delivery_id": log_doc["id"]}

        # send
        provider = PROVIDER_MAP.get(provider_type)
        if not provider:
            log_doc["status"] = DeliveryStatus.FAILED.value
            log_doc["error_message"] = "Provider not implemented"
            await self.db.messaging_delivery_logs.insert_one(log_doc)
            return {"success": False, "error": "Provider not implemented", "delivery_id": log_doc["id"]}

        credentials = config.get("credentials_encrypted", {})
        is_sandbox = config.get("is_sandbox", False)

        log_doc["status"] = DeliveryStatus.SENDING.value
        await self.db.messaging_delivery_logs.insert_one(log_doc)

        result = await provider.send(recipient, body, subject, credentials, is_sandbox)

        if result.get("success"):
            await self.db.messaging_delivery_logs.update_one(
                {"id": log_doc["id"]},
                {"$set": {
                    "status": DeliveryStatus.SENT.value,
                    "provider_message_id": result.get("provider_message_id"),
                    "delivered_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            return {"success": True, "delivery_id": log_doc["id"], "provider_message_id": result.get("provider_message_id")}
        else:
            await self.db.messaging_delivery_logs.update_one(
                {"id": log_doc["id"]},
                {"$set": {
                    "status": DeliveryStatus.FAILED.value,
                    "error_message": result.get("error"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            # attempt fallback
            return await self._try_fallback(
                tenant_id, channel, recipient, body, subject, log_doc, booking_id, guest_id, property_id, use_case
            )

    async def _try_fallback(self, tenant_id, original_channel, recipient, body, subject,
                            original_log, booking_id, guest_id, property_id, use_case) -> dict:
        fallbacks = FALLBACK_CHAIN.get(original_channel, [])
        for fb_channel in fallbacks:
            fb_provider_type = CHANNEL_PROVIDER_MAP.get(fb_channel)
            fb_config = await self._get_provider_config(tenant_id, fb_provider_type)
            if not fb_config:
                continue
            provider = PROVIDER_MAP.get(fb_provider_type)
            if not provider:
                continue
            creds = fb_config.get("credentials_encrypted", {})
            sandbox = fb_config.get("is_sandbox", False)
            result = await provider.send(recipient, body, subject, creds, sandbox)
            if result.get("success"):
                fb_log = new_delivery_log(
                    tenant_id=tenant_id, property_id=property_id, channel=fb_channel,
                    provider_type=fb_provider_type, recipient=recipient, template_id=None,
                    subject=subject, body=body, booking_id=booking_id, guest_id=guest_id, use_case=use_case,
                )
                fb_log["status"] = DeliveryStatus.SENT.value
                fb_log["provider_message_id"] = result.get("provider_message_id")
                fb_log["delivered_at"] = datetime.now(timezone.utc).isoformat()
                await self.db.messaging_delivery_logs.insert_one(fb_log)
                return {"success": True, "delivery_id": fb_log["id"], "fallback_channel": fb_channel,
                        "provider_message_id": result.get("provider_message_id")}
        return {"success": False, "error": original_log.get("error_message", "All channels failed"),
                "delivery_id": original_log["id"]}

    # ── retry failed ──

    async def retry_failed(self, tenant_id: str, delivery_id: str) -> dict:
        doc = await self.db.messaging_delivery_logs.find_one(
            {"id": delivery_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not doc:
            return {"success": False, "error": "Delivery not found"}
        if doc.get("retry_count", 0) >= doc.get("max_retries", 3):
            return {"success": False, "error": "Max retries reached"}

        provider_type = doc.get("provider_type")
        config = await self._get_provider_config(tenant_id, provider_type)
        if not config:
            return {"success": False, "error": "Provider not configured"}

        provider = PROVIDER_MAP.get(provider_type)
        creds = config.get("credentials_encrypted", {})
        sandbox = config.get("is_sandbox", False)

        result = await provider.send(doc["recipient"], doc["body"], doc.get("subject"), creds, sandbox)
        new_count = doc.get("retry_count", 0) + 1

        if result.get("success"):
            await self.db.messaging_delivery_logs.update_one(
                {"id": delivery_id},
                {"$set": {
                    "status": DeliveryStatus.SENT.value,
                    "retry_count": new_count,
                    "provider_message_id": result.get("provider_message_id"),
                    "delivered_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            return {"success": True, "delivery_id": delivery_id}
        else:
            next_retry = datetime.now(timezone.utc) + timedelta(minutes=2 ** new_count)
            await self.db.messaging_delivery_logs.update_one(
                {"id": delivery_id},
                {"$set": {
                    "retry_count": new_count,
                    "error_message": result.get("error"),
                    "next_retry_at": next_retry.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            return {"success": False, "error": result.get("error"), "retry_count": new_count}

    # ── delivery metrics ──

    async def get_delivery_metrics(self, tenant_id: str, days: int = 7) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": {"channel": "$channel", "status": "$status"},
                "count": {"$sum": 1},
            }},
        ]
        cursor = self.db.messaging_delivery_logs.aggregate(pipeline)
        results = await cursor.to_list(200)
        metrics = {}
        total = 0
        for r in results:
            ch = r["_id"]["channel"]
            st = r["_id"]["status"]
            if ch not in metrics:
                metrics[ch] = {}
            metrics[ch][st] = r["count"]
            total += r["count"]
        return {"metrics_by_channel": metrics, "total_messages": total, "period_days": days}

    # ── provider health ──

    async def check_all_providers(self, tenant_id: str) -> list:
        configs = await self.db.messaging_provider_configs.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(20)
        results = []
        for cfg in configs:
            pt = cfg.get("provider_type")
            provider = PROVIDER_MAP.get(pt)
            if not provider:
                results.append({"provider_type": pt, "status": "not_implemented"})
                continue
            health = await provider.check_health(cfg.get("credentials_encrypted", {}), cfg.get("is_sandbox", False))
            await self.db.messaging_provider_configs.update_one(
                {"id": cfg["id"]},
                {"$set": {"health_status": health.get("status"), "last_health_check": health.get("checked_at")}},
            )
            results.append({"provider_type": pt, "config_id": cfg["id"], **health})
        return results
