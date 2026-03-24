"""
Production Configuration Validator — Environment validation, startup checks,
missing secrets detection, and masked configuration audit.

Validates all required production environment variables at startup and
provides a masked inspection endpoint for debugging without exposing secrets.
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("infra.production_config")


# ── Required Production Variables ──────────────────────────────────
PRODUCTION_VARIABLES = {
    # Core Infrastructure
    "MONGO_URL": {"category": "database", "critical": True, "description": "MongoDB connection URI"},
    "JWT_SECRET": {"category": "auth", "critical": True, "description": "JWT signing secret"},
    "CORS_ORIGINS": {"category": "security", "critical": True, "description": "Allowed CORS origins"},

    # Redis
    "REDIS_URL": {"category": "redis", "critical": False, "description": "Redis connection URL"},
    "REDIS_MODE": {"category": "redis", "critical": False, "description": "Redis mode: standalone|sentinel|cluster"},
    "REDIS_MAX_CONNECTIONS": {"category": "redis", "critical": False, "description": "Redis pool size"},

    # Observability
    "SENTRY_DSN": {"category": "observability", "critical": False, "description": "Sentry error tracking DSN"},
    "OTEL_EXPORTER_ENDPOINT": {"category": "observability", "critical": False, "description": "OpenTelemetry collector endpoint"},
    "OTEL_SERVICE_NAME": {"category": "observability", "critical": False, "description": "OTel service name"},

    # Messaging Providers
    "TWILIO_ACCOUNT_SID": {"category": "messaging", "critical": False, "description": "Twilio Account SID"},
    "TWILIO_AUTH_TOKEN": {"category": "messaging", "critical": False, "description": "Twilio Auth Token"},
    "TWILIO_FROM_NUMBER": {"category": "messaging", "critical": False, "description": "Twilio sender number"},
    "SENDGRID_API_KEY": {"category": "messaging", "critical": False, "description": "SendGrid API key"},
    "SENDGRID_FROM_EMAIL": {"category": "messaging", "critical": False, "description": "SendGrid sender email"},
    "WHATSAPP_PROVIDER_KEY": {"category": "messaging", "critical": False, "description": "WhatsApp provider key"},

    # Secrets Management
    "SECRETS_PROVIDER": {"category": "secrets", "critical": False, "description": "Secrets provider: aws|vault|env"},
    "AWS_REGION": {"category": "secrets", "critical": False, "description": "AWS region for Secrets Manager"},
    "VAULT_ADDR": {"category": "secrets", "critical": False, "description": "HashiCorp Vault address"},

    # Backup
    "BACKUP_ENABLED": {"category": "backup", "critical": False, "description": "Enable automated backups"},
    "BACKUP_RETENTION_DAYS": {"category": "backup", "critical": False, "description": "Backup retention days"},

    # Scaling
    "INSTANCE_ID": {"category": "scaling", "critical": False, "description": "Instance identifier"},
    "SCALING_MODE": {"category": "scaling", "critical": False, "description": "Scaling mode: single|multi"},
}

SENSITIVE_PATTERNS = re.compile(
    r"(token|secret|key|password|dsn|auth|sid|credential)", re.IGNORECASE
)


def _mask_value(key: str, value: str) -> str:
    """Mask sensitive values for safe display."""
    if not value:
        return ""
    if SENSITIVE_PATTERNS.search(key):
        if len(value) <= 8:
            return "***"
        return value[:4] + "***" + value[-4:]
    return value


class ProductionConfigValidator:
    """Validates and audits production environment configuration."""

    def __init__(self):
        self._validated = False
        self._validation_result: Optional[Dict] = None
        self._startup_time = datetime.now(timezone.utc).isoformat()

    def validate_all(self) -> Dict[str, Any]:
        """Run full environment validation. Returns structured result."""
        results = {
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "categories": {},
            "missing_critical": [],
            "missing_optional": [],
            "present": [],
            "total_configured": 0,
            "total_required": len(PRODUCTION_VARIABLES),
            "critical_pass": True,
            "overall_status": "READY",
        }

        category_stats = {}
        for var_name, meta in PRODUCTION_VARIABLES.items():
            cat = meta["category"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "configured": 0, "missing_critical": 0, "variables": []}
            category_stats[cat]["total"] += 1

            value = os.environ.get(var_name, "")
            is_set = bool(value)
            entry = {
                "variable": var_name,
                "description": meta["description"],
                "critical": meta["critical"],
                "configured": is_set,
                "masked_value": _mask_value(var_name, value) if is_set else None,
            }
            category_stats[cat]["variables"].append(entry)

            if is_set:
                category_stats[cat]["configured"] += 1
                results["present"].append(var_name)
                results["total_configured"] += 1
            else:
                if meta["critical"]:
                    results["missing_critical"].append(var_name)
                    category_stats[cat]["missing_critical"] += 1
                else:
                    results["missing_optional"].append(var_name)

        results["categories"] = category_stats
        results["critical_pass"] = len(results["missing_critical"]) == 0

        if not results["critical_pass"]:
            results["overall_status"] = "NOT_READY"
        elif len(results["missing_optional"]) > len(results["present"]):
            results["overall_status"] = "DEGRADED"
        else:
            results["overall_status"] = "READY"

        self._validated = True
        self._validation_result = results
        return results

    def get_masked_config(self) -> Dict[str, Any]:
        """Return all configured variables with masked values."""
        config = {}
        for var_name in PRODUCTION_VARIABLES:
            value = os.environ.get(var_name, "")
            config[var_name] = {
                "configured": bool(value),
                "masked_value": _mask_value(var_name, value) if value else None,
                "category": PRODUCTION_VARIABLES[var_name]["category"],
            }
        return {
            "inspected_at": datetime.now(timezone.utc).isoformat(),
            "config": config,
        }

    def startup_check(self) -> Dict[str, Any]:
        """Lightweight startup validation — fails fast on missing critical vars."""
        missing = []
        for var_name, meta in PRODUCTION_VARIABLES.items():
            if meta["critical"] and not os.environ.get(var_name, ""):
                missing.append(var_name)

        status = "pass" if not missing else "fail"
        if missing:
            logger.error(f"Startup check FAILED — missing critical vars: {missing}")
        else:
            logger.info("Startup check passed — all critical variables present")

        return {
            "status": status,
            "missing_critical": missing,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "startup_time": self._startup_time,
        }

    def detect_leaked_secrets(self) -> Dict[str, Any]:
        """Scan for potential secret leakage in non-secret environment variables."""
        suspicious = []
        safe_secret_vars = set(PRODUCTION_VARIABLES.keys())

        for key, value in os.environ.items():
            if key in safe_secret_vars:
                continue
            if not value or len(value) < 16:
                continue
            if SENSITIVE_PATTERNS.search(key):
                suspicious.append({
                    "variable": key,
                    "reason": "Name matches sensitive pattern but not in managed config",
                    "length": len(value),
                })

        return {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "suspicious_count": len(suspicious),
            "suspicious_variables": suspicious,
            "status": "clean" if not suspicious else "review_needed",
        }


production_config = ProductionConfigValidator()
