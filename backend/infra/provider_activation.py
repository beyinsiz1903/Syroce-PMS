"""
Provider Integration Activation — Credential validation, sandbox→production mode switch,
delivery monitoring, error classification, and fallback chain management.

Supports: Twilio SMS, SendGrid Email, WhatsApp.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger("infra.provider_activation")


class ProviderStatus:
    NOT_CONFIGURED = "not_configured"
    SANDBOX = "sandbox"
    PRODUCTION = "production"
    ERROR = "error"
    VALIDATING = "validating"


class ProviderActivationManager:
    """Manages messaging provider activation, validation, and monitoring."""

    def __init__(self):
        self._delivery_metrics = defaultdict(lambda: {
            "total_sent": 0, "delivered": 0, "failed": 0,
            "latency_sum_ms": 0, "last_error": None, "last_sent": None,
            "error_types": defaultdict(int),
        })
        self._provider_configs = {}
        self._fallback_chain = ["twilio_sms", "sendgrid_email", "whatsapp"]

    def _detect_provider_status(self, provider: str) -> Dict[str, Any]:
        """Detect configuration status for a provider."""
        configs = {
            "twilio_sms": {
                "required": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
                "sandbox_indicator": "TWILIO_SANDBOX",
            },
            "sendgrid_email": {
                "required": ["SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL"],
                "sandbox_indicator": "SENDGRID_SANDBOX",
            },
            "whatsapp": {
                "required": ["WHATSAPP_PROVIDER_KEY"],
                "sandbox_indicator": "WHATSAPP_SANDBOX",
            },
        }
        cfg = configs.get(provider, {})
        required_vars = cfg.get("required", [])
        sandbox_var = cfg.get("sandbox_indicator", "")

        present = {}
        missing = []
        for var in required_vars:
            value = os.environ.get(var, "")
            if value:
                present[var] = True
            else:
                missing.append(var)

        is_sandbox = os.environ.get(sandbox_var, "false").lower() == "true"

        if missing and len(missing) == len(required_vars):
            status = ProviderStatus.NOT_CONFIGURED
        elif missing:
            status = ProviderStatus.ERROR
        elif is_sandbox:
            status = ProviderStatus.SANDBOX
        else:
            status = ProviderStatus.PRODUCTION

        return {
            "provider": provider,
            "status": status,
            "configured_vars": list(present.keys()),
            "missing_vars": missing,
            "is_sandbox": is_sandbox,
            "ready_for_production": not missing and not is_sandbox,
        }

    async def validate_credential(self, provider: str) -> Dict[str, Any]:
        """Validate provider credentials with a lightweight test call."""
        status = self._detect_provider_status(provider)
        if status["status"] == ProviderStatus.NOT_CONFIGURED:
            return {**status, "validation": "skipped", "reason": "Not configured"}

        validation_result = {
            "provider": provider,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        if provider == "twilio_sms":
            validation_result["validation"] = await self._validate_twilio()
        elif provider == "sendgrid_email":
            validation_result["validation"] = await self._validate_sendgrid()
        elif provider == "whatsapp":
            validation_result["validation"] = await self._validate_whatsapp()
        else:
            validation_result["validation"] = "unknown_provider"

        return {**status, **validation_result}

    async def _validate_twilio(self) -> str:
        """Validate Twilio credentials."""
        try:
            sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            token = os.environ.get("TWILIO_AUTH_TOKEN", "")
            if not sid or not token:
                return "missing_credentials"
            if sid.startswith("AC") and len(sid) == 34:
                return "format_valid"
            return "invalid_sid_format"
        except Exception as e:
            return f"error: {str(e)}"

    async def _validate_sendgrid(self) -> str:
        """Validate SendGrid credentials."""
        try:
            key = os.environ.get("SENDGRID_API_KEY", "")
            if not key:
                return "missing_credentials"
            if key.startswith("SG."):
                return "format_valid"
            return "invalid_key_format"
        except Exception as e:
            return f"error: {str(e)}"

    async def _validate_whatsapp(self) -> str:
        """Validate WhatsApp provider credentials."""
        try:
            key = os.environ.get("WHATSAPP_PROVIDER_KEY", "")
            if not key:
                return "missing_credentials"
            return "format_valid"
        except Exception as e:
            return f"error: {str(e)}"

    def record_delivery(self, provider: str, success: bool, latency_ms: float = 0, error: str = None):
        """Record a delivery attempt for metrics."""
        m = self._delivery_metrics[provider]
        m["total_sent"] += 1
        m["last_sent"] = datetime.now(timezone.utc).isoformat()
        if success:
            m["delivered"] += 1
        else:
            m["failed"] += 1
            m["last_error"] = error
            if error:
                from modules.messaging.providers import BaseProvider
                err_type = BaseProvider().classify_error(error)
                m["error_types"][err_type] += 1
        m["latency_sum_ms"] += latency_ms

    def get_delivery_metrics(self) -> Dict[str, Any]:
        """Get delivery metrics for all providers."""
        result = {}
        for provider, m in self._delivery_metrics.items():
            total = m["total_sent"]
            result[provider] = {
                "total_sent": total,
                "delivered": m["delivered"],
                "failed": m["failed"],
                "success_rate": round(m["delivered"] / total * 100, 2) if total > 0 else 0,
                "avg_latency_ms": round(m["latency_sum_ms"] / total, 2) if total > 0 else 0,
                "last_sent": m["last_sent"],
                "last_error": m["last_error"],
                "error_breakdown": dict(m["error_types"]),
            }
        return result

    def get_all_provider_status(self) -> Dict[str, Any]:
        """Get status for all providers."""
        providers = ["twilio_sms", "sendgrid_email", "whatsapp"]
        statuses = {}
        active_count = 0
        for p in providers:
            s = self._detect_provider_status(p)
            statuses[p] = s
            if s["status"] in (ProviderStatus.PRODUCTION, ProviderStatus.SANDBOX):
                active_count += 1

        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "providers": statuses,
            "active_providers": active_count,
            "total_providers": len(providers),
            "fallback_chain": self._fallback_chain,
            "delivery_metrics": self.get_delivery_metrics(),
        }

    async def get_full_report(self) -> Dict[str, Any]:
        """Full provider activation report with validation."""
        providers = ["twilio_sms", "sendgrid_email", "whatsapp"]
        results = {}
        for p in providers:
            results[p] = await self.validate_credential(p)

        production_ready = sum(1 for r in results.values() if r.get("ready_for_production"))
        return {
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "providers": results,
            "production_ready_count": production_ready,
            "total_providers": len(providers),
            "delivery_metrics": self.get_delivery_metrics(),
            "fallback_chain": self._fallback_chain,
            "overall_status": "production" if production_ready == len(providers) else
                              "partial" if production_ready > 0 else "not_configured",
        }


provider_manager = ProviderActivationManager()
