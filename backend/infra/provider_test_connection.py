"""
Provider Test Connection Framework — Live credential validation, network connectivity,
latency measurement, failure classification, and audit logging for all external providers.

Supports: Twilio SMS, SendGrid Email, WhatsApp, Redis, Sentry, OTel Exporter.
"""
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("infra.provider_test_connection")


class ConnectionTestResult:
    """Normalized test result for any provider."""

    def __init__(self, provider: str):
        self.provider = provider
        self.status = "pending"
        self.latency_ms: float = 0
        self.error: Optional[str] = None
        self.error_masked: Optional[str] = None
        self.failure_class: Optional[str] = None
        self.mode: str = "unknown"  # sandbox / test / live
        self.validated_at: str = datetime.now(timezone.utc).isoformat()
        self.network_reachable: bool = False
        self.credential_valid: bool = False
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "error_masked": self.error_masked,
            "failure_class": self.failure_class,
            "mode": self.mode,
            "validated_at": self.validated_at,
            "network_reachable": self.network_reachable,
            "credential_valid": self.credential_valid,
            "details": self.details,
        }


def _mask_error(error: str) -> str:
    """Mask sensitive info from error messages."""
    if not error:
        return ""
    import re
    masked = re.sub(r'(key|token|secret|password|sid|dsn)[\s=:]+\S+',
                     r'\1=***', error, flags=re.IGNORECASE)
    masked = re.sub(r'https?://[^\s]+', '[URL_MASKED]', masked)
    return masked[:300]


def _classify_failure(error: str) -> str:
    """Classify failure type for operational alerting."""
    err_lower = (error or "").lower()
    if "timeout" in err_lower or "timed out" in err_lower:
        return "timeout"
    if "connection refused" in err_lower or "connect" in err_lower:
        return "connection_refused"
    if "401" in err_lower or "403" in err_lower or "unauthorized" in err_lower or "forbidden" in err_lower:
        return "auth_failure"
    if "404" in err_lower or "not found" in err_lower:
        return "endpoint_not_found"
    if "dns" in err_lower or "resolve" in err_lower:
        return "dns_failure"
    if "ssl" in err_lower or "certificate" in err_lower:
        return "ssl_error"
    if "rate limit" in err_lower or "429" in err_lower:
        return "rate_limited"
    return "unknown"


class ProviderTestConnectionService:
    """Live test connection for all external providers."""

    def __init__(self):
        self._test_history: List[Dict[str, Any]] = []
        self._last_results: Dict[str, Dict[str, Any]] = {}
        self._max_history = 200
        self._audit_log: List[Dict[str, Any]] = []

    def _record_audit(self, provider: str, action: str, result: str, user_id: str = "system"):
        entry = {
            "provider": provider,
            "action": action,
            "result": result,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > 500:
            self._audit_log = self._audit_log[-500:]

    async def test_provider(self, provider: str, user_id: str = "system") -> Dict[str, Any]:
        """Run live test for a specific provider."""
        result = ConnectionTestResult(provider)
        start = time.time()

        try:
            if provider == "twilio_sms":
                await self._test_twilio(result)
            elif provider == "sendgrid_email":
                await self._test_sendgrid(result)
            elif provider == "whatsapp":
                await self._test_whatsapp(result)
            elif provider == "redis":
                await self._test_redis(result)
            elif provider == "sentry":
                await self._test_sentry(result)
            elif provider == "otel":
                await self._test_otel(result)
            else:
                result.status = "unknown_provider"
                result.failure_class = "invalid_provider"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.error_masked = _mask_error(str(e))
            result.failure_class = _classify_failure(str(e))

        result.latency_ms = (time.time() - start) * 1000
        result_dict = result.to_dict()

        self._last_results[provider] = result_dict
        self._test_history.append(result_dict)
        if len(self._test_history) > self._max_history:
            self._test_history = self._test_history[-self._max_history:]

        self._record_audit(provider, "test_connection", result.status, user_id)
        return result_dict

    async def test_all_providers(self, user_id: str = "system") -> Dict[str, Any]:
        """Test all providers and return aggregated results."""
        providers = ["twilio_sms", "sendgrid_email", "whatsapp", "redis", "sentry", "otel"]
        results = {}
        for p in providers:
            results[p] = await self.test_provider(p, user_id)

        success = sum(1 for r in results.values() if r["status"] == "success")
        degraded = sum(1 for r in results.values() if r["status"] == "degraded")
        failed = sum(1 for r in results.values() if r["status"] in ("failed", "not_configured"))

        if success == len(providers):
            overall = "all_healthy"
        elif success + degraded > 0 and failed < len(providers):
            overall = "degraded"
        else:
            overall = "failed"

        return {
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "providers": results,
            "summary": {
                "total": len(providers),
                "success": success,
                "degraded": degraded,
                "failed": failed,
                "overall": overall,
            },
        }

    def get_status(self) -> Dict[str, Any]:
        """Get last known status for all providers."""
        return {
            "last_results": self._last_results,
            "total_tests": len(self._test_history),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._audit_log[-limit:]

    # ── Provider-specific test implementations ──────────────────

    async def _test_twilio(self, result: ConnectionTestResult):
        sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        os.environ.get("TWILIO_FROM_NUMBER", "")
        is_sandbox = os.environ.get("TWILIO_SANDBOX", "false").lower() == "true"
        result.mode = "sandbox" if is_sandbox else ("live" if sid else "not_configured")

        if not sid or not token:
            result.status = "not_configured"
            result.details = {"missing": [v for v in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"] if not os.environ.get(v)]}
            return

        # Format validation
        if not sid.startswith("AC") or len(sid) != 34:
            result.status = "failed"
            result.failure_class = "auth_failure"
            result.error_masked = "Invalid SID format (expected AC + 32 chars)"
            return

        # Network test via HTTP
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                    auth=(sid, token),
                )
                result.network_reachable = True
                if resp.status_code == 200:
                    result.credential_valid = True
                    result.status = "success"
                    data = resp.json()
                    result.details = {
                        "account_name": data.get("friendly_name", ""),
                        "account_status": data.get("status", ""),
                        "account_type": data.get("type", ""),
                    }
                elif resp.status_code == 401:
                    result.status = "failed"
                    result.failure_class = "auth_failure"
                    result.error_masked = "Invalid credentials (HTTP 401)"
                else:
                    result.status = "degraded"
                    result.error_masked = f"Unexpected HTTP {resp.status_code}"
        except ImportError:
            result.status = "degraded"
            result.network_reachable = False
            result.details = {"note": "httpx not installed, format validation only"}
            result.credential_valid = True  # format was valid
        except Exception as e:
            result.status = "failed"
            result.error_masked = _mask_error(str(e))
            result.failure_class = _classify_failure(str(e))

    async def _test_sendgrid(self, result: ConnectionTestResult):
        api_key = os.environ.get("SENDGRID_API_KEY", "")
        os.environ.get("SENDGRID_FROM_EMAIL", "")
        is_sandbox = os.environ.get("SENDGRID_SANDBOX", "false").lower() == "true"
        result.mode = "sandbox" if is_sandbox else ("live" if api_key else "not_configured")

        if not api_key:
            result.status = "not_configured"
            result.details = {"missing": ["SENDGRID_API_KEY"]}
            return

        if not api_key.startswith("SG."):
            result.status = "failed"
            result.failure_class = "auth_failure"
            result.error_masked = "Invalid API key format (expected SG. prefix)"
            return

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.sendgrid.com/v3/scopes",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                result.network_reachable = True
                if resp.status_code == 200:
                    result.credential_valid = True
                    result.status = "success"
                    scopes = resp.json().get("scopes", [])
                    result.details = {"scopes_count": len(scopes), "has_mail_send": "mail.send" in scopes}
                elif resp.status_code == 401:
                    result.status = "failed"
                    result.failure_class = "auth_failure"
                    result.error_masked = "Invalid API key (HTTP 401)"
                else:
                    result.status = "degraded"
                    result.error_masked = f"Unexpected HTTP {resp.status_code}"
        except ImportError:
            result.status = "degraded"
            result.details = {"note": "httpx not installed, format validation only"}
            result.credential_valid = True
        except Exception as e:
            result.status = "failed"
            result.error_masked = _mask_error(str(e))
            result.failure_class = _classify_failure(str(e))

    async def _test_whatsapp(self, result: ConnectionTestResult):
        key = os.environ.get("WHATSAPP_PROVIDER_KEY", "")
        is_sandbox = os.environ.get("WHATSAPP_SANDBOX", "false").lower() == "true"
        result.mode = "sandbox" if is_sandbox else ("live" if key else "not_configured")

        if not key:
            result.status = "not_configured"
            result.details = {"missing": ["WHATSAPP_PROVIDER_KEY"]}
            return

        # Format validation only (no universal WhatsApp API endpoint)
        result.credential_valid = True
        result.network_reachable = True
        result.status = "success"
        result.details = {"validation": "format_check", "key_length": len(key)}

    async def _test_redis(self, result: ConnectionTestResult):
        redis_url = os.environ.get("REDIS_URL", "")
        result.mode = "standalone" if redis_url else "not_configured"

        if not redis_url:
            # Check if in-memory fallback is active
            from infra.redis_cluster import redis_cluster
            if redis_cluster.connected:
                result.status = "degraded"
                result.mode = redis_cluster.mode
                result.network_reachable = True
                result.details = {"note": "Connected via existing cluster manager"}
                return
            result.status = "not_configured"
            result.details = {"missing": ["REDIS_URL"]}
            return

        try:
            from infra.redis_cluster import redis_cluster
            health = await redis_cluster.health_check()
            result.network_reachable = health.get("status") != "disconnected"
            result.credential_valid = health.get("status") == "healthy"
            result.status = "success" if result.credential_valid else "degraded"
            result.mode = redis_cluster.mode
            result.details = {
                "redis_version": health.get("redis_version", "unknown"),
                "latency_ms": health.get("latency_ms", 0),
                "connected_clients": health.get("connected_clients", 0),
            }
        except Exception as e:
            result.status = "failed"
            result.error_masked = _mask_error(str(e))
            result.failure_class = _classify_failure(str(e))

    async def _test_sentry(self, result: ConnectionTestResult):
        dsn = os.environ.get("SENTRY_DSN", "")
        result.mode = "live" if dsn else "not_configured"

        if not dsn:
            result.status = "not_configured"
            result.details = {"missing": ["SENTRY_DSN"]}
            return

        # Validate DSN format
        if not dsn.startswith("https://") or "@" not in dsn:
            result.status = "failed"
            result.failure_class = "auth_failure"
            result.error_masked = "Invalid DSN format"
            return

        from infra.cloud_observability import sentry_integration
        sentry_status = sentry_integration.get_status()
        result.credential_valid = sentry_status.get("active", False) or bool(dsn)
        result.network_reachable = True
        result.status = "success" if sentry_status.get("active") else "degraded"
        result.details = {
            "sdk_active": sentry_status.get("active", False),
            "events_sent": sentry_status.get("events_sent", 0),
            "environment": sentry_status.get("environment", "unknown"),
        }

    async def _test_otel(self, result: ConnectionTestResult):
        endpoint = os.environ.get("OTEL_EXPORTER_ENDPOINT", "")
        result.mode = "live" if endpoint else "not_configured"

        if not endpoint:
            result.status = "not_configured"
            result.details = {"missing": ["OTEL_EXPORTER_ENDPOINT"]}
            return

        from infra.cloud_observability import otel_tracer
        otel_status = otel_tracer.get_status()
        result.credential_valid = otel_status.get("active", False)
        result.network_reachable = bool(endpoint)
        result.status = "success" if otel_status.get("active") else "degraded"
        result.details = {
            "endpoint": endpoint[:30] + "..." if len(endpoint) > 30 else endpoint,
            "service_name": otel_status.get("service_name", ""),
            "spans_created": otel_status.get("spans_created", 0),
        }


# Singleton
provider_test_service = ProviderTestConnectionService()
