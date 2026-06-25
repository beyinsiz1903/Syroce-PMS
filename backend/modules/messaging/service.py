"""
Messaging service – orchestrates sending, retry, consent, rate limiting, fallback.
Production runtime with credential vault integration, delivery metrics,
provider latency tracking, cost/usage summary, and per-tenant policy.
"""
import logging
from datetime import UTC, datetime, timedelta

from .models import (
    ConsentStatus,
    DeliveryStatus,
    new_delivery_log,
)
from .providers import CHANNEL_PROVIDER_MAP, FALLBACK_CHAIN, PROVIDER_MAP, ProviderMode
from .recipient_crypto import reveal_recipient, seal_delivery_log

logger = logging.getLogger(__name__)

# Bug #15 fix: provider-type → secret credential keys (encrypted at-rest).
# Mirrored in routers/messaging.py (kept narrow per provider).
_PROVIDER_SECRET_KEYS = {
    "smtp_email": {"smtp_password"},
    "whatsapp": {"access_token", "webhook_verify_token", "app_secret"},
}


def _decrypt_provider_creds(creds: dict, provider_type: str) -> dict:
    """Return a plaintext copy of creds for runtime use.

    Falls back to the original dict if encryption service is unavailable
    (dual-read compat: legacy unencrypted creds pass through unchanged).
    """
    secret_keys = _PROVIDER_SECRET_KEYS.get(provider_type, set())
    if not secret_keys:
        return dict(creds or {})
    try:
        from security.field_encryption import get_field_encryption_service
        svc = get_field_encryption_service()
    except Exception:
        return dict(creds or {})
    out = dict(creds or {})
    for k in secret_keys:
        v = out.get(k)
        if v and isinstance(v, str):
            out[k] = svc.decrypt_value(v)
    return out


class MessagingService:
    """Central orchestrator for all outbound messaging."""

    def __init__(self, db):
        self.db = db
        self._rate_counters: dict[str, int] = {}
        self._provider_latencies: dict[str, list[float]] = {}
        self._provider_errors: dict[str, int] = {}
        self._provider_successes: dict[str, int] = {}
        self._fallback_usage: dict[str, int] = {}
        self._consent_rejections = 0

    # ── helpers ──

    async def _get_provider_config(self, tenant_id: str, provider_type: str) -> dict | None:
        return await self.db.messaging_provider_configs.find_one(
            {"tenant_id": tenant_id, "provider_type": provider_type, "enabled": True},
            {"_id": 0},
        )

    def _resolve_mode(self, config: dict) -> str:
        if config.get("is_sandbox"):
            return ProviderMode.SANDBOX
        if config.get("mode") == "test":
            return ProviderMode.TEST
        return ProviderMode.LIVE

    async def _load_credentials(self, tenant_id: str, config: dict) -> dict:
        """Load credentials, trying credential vault first then config.

        Bug #15 fix: credentials_encrypted'ta saklanan SMTP password / WhatsApp
        access_token / webhook_verify_token / app_secret artık envelope-encrypted
        (field_encryption). Provider'lara plaintext döndürmek için decrypt et.
        """
        try:
            from modules.security_hardening.credential_vault import credential_vault
            vault_key = f"messaging_{config.get('provider_type')}_{tenant_id}"
            creds = credential_vault.get_credential(vault_key)
            if creds:
                return creds
        except Exception:
            logger.warning("messaging: credential vault lookup failed; falling back to config", exc_info=True)
        return _decrypt_provider_creds(
            config.get("credentials_encrypted", {}) or {},
            config.get("provider_type", ""),
        )

    async def _check_consent(self, tenant_id: str, recipient: str, channel: str) -> bool:
        # PII-at-rest: consent recipients are sealed (recipient_enc +
        # recipient_hash blind-index). Match by the HMAC blind-index for an
        # exact-equality opt-out lookup, with a dual-read fallback to a legacy
        # plaintext `recipient` so an opt-out written before the backfill is
        # NEVER missed (fail-closed for opt-out enforcement).
        from .recipient_crypto import recipient_hash as _rhash

        q: dict = {"tenant_id": tenant_id, "channel": channel}
        r_hash = _rhash(recipient)
        or_terms: list[dict] = []
        if r_hash:
            or_terms.append({"recipient_hash": r_hash})
        if recipient:
            or_terms.append({"recipient": recipient})
        if or_terms:
            q["$or"] = or_terms
        # Fail-closed + deterministic: during/after migration a legacy
        # plaintext-keyed row and a new hash-keyed row can BOTH exist for the
        # same logical recipient/channel. find_one would pick one arbitrarily
        # (document order) and could miss an OPT_OUT. Scan ALL matching rows and
        # treat OPT_OUT as authoritative — if ANY matching consent is OPT_OUT,
        # block the send. OPT_OUT always wins, regardless of row count/order.
        rejected = False
        async for doc in self.db.messaging_consents.find(q, {"_id": 0, "status": 1}):
            if doc.get("status") == ConsentStatus.OPT_OUT.value:
                rejected = True
                break
        if rejected:
            self._consent_rejections += 1
            return False
        return True

    async def _check_rate_limit(self, tenant_id: str, provider_type: str, limit: int = 60) -> bool:
        key = f"{tenant_id}:{provider_type}"
        count = self._rate_counters.get(key, 0)
        if count >= limit:
            return False
        self._rate_counters[key] = count + 1
        return True

    def _render_template(self, body_template: str, variables: dict, escape_html: bool = False) -> str:
        # v41 Bug BG: escape variables for HTML/email channels so guest-controlled
        # fields (name, special_requests, etc.) cannot inject markup into rendered
        # email bodies. SMS/WhatsApp render plain-text — keep raw.
        import html as _html_mod
        result = body_template
        for k, v in variables.items():
            sv = str(v) if v is not None else ""
            if escape_html:
                sv = _html_mod.escape(sv, quote=True)
            result = result.replace(f"{{{{{k}}}}}", sv)
        return result

    def _track_latency(self, provider_type: str, latency_ms: float):
        if provider_type not in self._provider_latencies:
            self._provider_latencies[provider_type] = []
        self._provider_latencies[provider_type].append(latency_ms)
        if len(self._provider_latencies[provider_type]) > 500:
            self._provider_latencies[provider_type] = self._provider_latencies[provider_type][-250:]

    # ── main send ──

    async def send_message(
        self,
        tenant_id: str,
        channel: str,
        recipient: str,
        body: str | None = None,
        subject: str | None = None,
        template_id: str | None = None,
        variables: dict = None,
        booking_id: str | None = None,
        guest_id: str | None = None,
        property_id: str | None = None,
        use_case: str | None = None,
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
                # v41 Bug BG: HTML-escape variables when channel renders HTML (email).
                _esc = channel in ("email",)
                body = self._render_template(tmpl.get("body_template", ""), variables, escape_html=_esc)
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
            await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(log_doc))
            return await self._try_fallback(
                tenant_id, channel, recipient, body, subject, log_doc, booking_id, guest_id, property_id, use_case
            )

        # rate limit
        rl = config.get("rate_limit_per_minute", 60)
        if not await self._check_rate_limit(tenant_id, provider_type, rl):
            log_doc["status"] = DeliveryStatus.FAILED.value
            log_doc["error_message"] = "Rate limit exceeded"
            await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(log_doc))
            return {"success": False, "error": "Rate limit exceeded", "delivery_id": log_doc["id"]}

        # send
        provider = PROVIDER_MAP.get(provider_type)
        if not provider:
            log_doc["status"] = DeliveryStatus.FAILED.value
            log_doc["error_message"] = "Provider not implemented"
            await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(log_doc))
            return {"success": False, "error": "Provider not implemented", "delivery_id": log_doc["id"]}

        credentials = await self._load_credentials(tenant_id, config)
        mode = self._resolve_mode(config)

        log_doc["status"] = DeliveryStatus.SENDING.value
        await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(log_doc))

        result = await provider.send(recipient, body, subject, credentials, mode)

        # Track metrics
        latency = result.get("latency_ms", 0)
        if latency:
            self._track_latency(provider_type, latency)

        # Observability hook
        try:
            from modules.observability.metrics_collector import metrics as obs_metrics
            obs_metrics.record_messaging_delivery(provider_type, result.get("success", False))
        except Exception:
            logger.debug("messaging: observability metric record failed", exc_info=True)

        if result.get("success"):
            self._provider_successes[provider_type] = self._provider_successes.get(provider_type, 0) + 1
            await self.db.messaging_delivery_logs.update_one(
                {"id": log_doc["id"]},
                {"$set": {
                    "status": DeliveryStatus.SENT.value,
                    "provider_message_id": result.get("provider_message_id"),
                    "delivered_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            return {"success": True, "delivery_id": log_doc["id"],
                    "provider_message_id": result.get("provider_message_id")}
        else:
            self._provider_errors[provider_type] = self._provider_errors.get(provider_type, 0) + 1
            error_class = result.get("error_class", "unknown_error")
            await self.db.messaging_delivery_logs.update_one(
                {"id": log_doc["id"]},
                {"$set": {
                    "status": DeliveryStatus.FAILED.value,
                    "error_message": result.get("error"),
                    "error_class": error_class,
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
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
            creds = await self._load_credentials(tenant_id, fb_config)
            mode = self._resolve_mode(fb_config)
            result = await provider.send(recipient, body, subject, creds, mode)
            if result.get("success"):
                self._fallback_usage[fb_channel] = self._fallback_usage.get(fb_channel, 0) + 1
                fb_log = new_delivery_log(
                    tenant_id=tenant_id, property_id=property_id, channel=fb_channel,
                    provider_type=fb_provider_type, recipient=recipient, template_id=None,
                    subject=subject, body=body, booking_id=booking_id, guest_id=guest_id, use_case=use_case,
                )
                fb_log["status"] = DeliveryStatus.SENT.value
                fb_log["provider_message_id"] = result.get("provider_message_id")
                fb_log["delivered_at"] = datetime.now(UTC).isoformat()
                await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(fb_log))
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
        creds = await self._load_credentials(tenant_id, config)
        mode = self._resolve_mode(config)

        # Recipient is sealed at rest (recipient_enc); decrypt at the read
        # boundary to send. Dual-read falls back to legacy plaintext.
        result = await provider.send(reveal_recipient(doc), doc["body"], doc.get("subject"), creds, mode)
        new_count = doc.get("retry_count", 0) + 1

        if result.get("success"):
            await self.db.messaging_delivery_logs.update_one(
                {"id": delivery_id},
                {"$set": {
                    "status": DeliveryStatus.SENT.value,
                    "retry_count": new_count,
                    "provider_message_id": result.get("provider_message_id"),
                    "delivered_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            return {"success": True, "delivery_id": delivery_id}
        else:
            next_retry = datetime.now(UTC) + timedelta(minutes=2 ** new_count)
            await self.db.messaging_delivery_logs.update_one(
                {"id": delivery_id},
                {"$set": {
                    "retry_count": new_count,
                    "error_message": result.get("error"),
                    "next_retry_at": next_retry.isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            return {"success": False, "error": result.get("error"), "retry_count": new_count}

    # ── delivery metrics ──

    async def get_delivery_metrics(self, tenant_id: str, days: int = 7) -> dict:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
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

    # ── provider runtime status ──

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
            mode = self._resolve_mode(cfg)
            decrypted_creds = _decrypt_provider_creds(
                cfg.get("credentials_encrypted", {}) or {}, pt or "",
            )
            health = await provider.check_health(decrypted_creds, mode)
            await self.db.messaging_provider_configs.update_one(
                {"id": cfg["id"]},
                {"$set": {"health_status": health.get("status"), "last_health_check": health.get("checked_at")}},
            )
            results.append({"provider_type": pt, "config_id": cfg["id"], "mode": mode, **health})
        return results

    # ── admin runtime status ──

    def get_runtime_status(self) -> dict:
        """Get comprehensive messaging runtime status for admin dashboard."""
        provider_latency_summary = {}
        for pt, lats in self._provider_latencies.items():
            if lats:
                sorted_l = sorted(lats)
                n = len(sorted_l)
                provider_latency_summary[pt] = {
                    "count": n,
                    "avg_ms": round(sum(sorted_l) / n, 2),
                    "p95_ms": round(sorted_l[min(int(n * 0.95), n - 1)], 2),
                    "max_ms": round(sorted_l[-1], 2),
                }

        return {
            "provider_successes": dict(self._provider_successes),
            "provider_errors": dict(self._provider_errors),
            "provider_latency": provider_latency_summary,
            "fallback_usage": dict(self._fallback_usage),
            "consent_rejections": self._consent_rejections,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_retry_queue_size(self, tenant_id: str) -> int:
        return await self.db.messaging_delivery_logs.count_documents({
            "tenant_id": tenant_id,
            "status": DeliveryStatus.FAILED.value,
            "retry_count": {"$lt": 3},
        })
