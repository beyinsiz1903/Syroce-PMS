"""
Production Config Activation Workflow — Required/optional config validation,
secret source inspection, invalid format detection, boot blocker/warning
classification, and readiness validator integration.
"""
import os
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("infra.config_activation")


# ── Config definitions with format rules and blocker classification ──
CONFIG_DEFINITIONS = {
    # Database
    "MONGO_URL": {
        "category": "database",
        "required": True,
        "blocker": True,
        "format_regex": r"^mongodb(\+srv)?://",
        "format_hint": "Must start with mongodb:// or mongodb+srv://",
        "description": "MongoDB connection URI",
    },
    "DB_NAME": {
        "category": "database",
        "required": True,
        "blocker": True,
        "format_regex": r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        "format_hint": "Valid database name",
        "description": "MongoDB database name",
    },
    # Redis
    "REDIS_URL": {
        "category": "redis",
        "required": True,
        "blocker": False,
        "format_regex": r"^redis(s)?://",
        "format_hint": "Must start with redis:// or rediss://",
        "description": "Redis connection URL",
    },
    "REDIS_MODE": {
        "category": "redis",
        "required": False,
        "blocker": False,
        "format_regex": r"^(standalone|sentinel|cluster)$",
        "format_hint": "standalone, sentinel, or cluster",
        "description": "Redis deployment mode",
    },
    # Auth
    "JWT_SECRET": {
        "category": "auth",
        "required": True,
        "blocker": True,
        "format_regex": r".{32,}",
        "format_hint": "At least 32 characters",
        "description": "JWT signing secret",
    },
    "CORS_ORIGINS": {
        "category": "security",
        "required": True,
        "blocker": False,
        "format_regex": None,
        "format_hint": "Comma-separated origins",
        "description": "Allowed CORS origins",
    },
    # Observability
    "SENTRY_DSN": {
        "category": "observability",
        "required": False,
        "blocker": False,
        "format_regex": r"^https://.*@.*\.ingest\..*sentry\.io",
        "format_hint": "Sentry DSN URL format",
        "description": "Sentry error tracking DSN",
    },
    "OTEL_EXPORTER_ENDPOINT": {
        "category": "observability",
        "required": False,
        "blocker": False,
        "format_regex": r"^https?://",
        "format_hint": "HTTP(S) endpoint URL",
        "description": "OpenTelemetry collector endpoint",
    },
    "OTEL_SERVICE_NAME": {
        "category": "observability",
        "required": False,
        "blocker": False,
        "format_regex": None,
        "format_hint": "Service identifier",
        "description": "OTel service name",
    },
    # Messaging - Twilio
    "TWILIO_ACCOUNT_SID": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": r"^AC[a-f0-9]{32}$",
        "format_hint": "AC followed by 32 hex chars",
        "description": "Twilio Account SID",
    },
    "TWILIO_AUTH_TOKEN": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": r"^[a-f0-9]{32}$",
        "format_hint": "32 hex characters",
        "description": "Twilio Auth Token",
    },
    "TWILIO_FROM_NUMBER": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": r"^\+\d{10,15}$",
        "format_hint": "E.164 format phone number",
        "description": "Twilio sender number",
    },
    # Messaging - SendGrid
    "SENDGRID_API_KEY": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": r"^SG\.",
        "format_hint": "Must start with SG.",
        "description": "SendGrid API key",
    },
    "SENDGRID_FROM_EMAIL": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": r"^[^@]+@[^@]+\.[^@]+$",
        "format_hint": "Valid email address",
        "description": "SendGrid sender email",
    },
    # Messaging - WhatsApp
    "WHATSAPP_PROVIDER_KEY": {
        "category": "messaging",
        "required": False,
        "blocker": False,
        "format_regex": None,
        "format_hint": "Provider API key",
        "description": "WhatsApp provider key",
    },
    # Backup
    "BACKUP_ENABLED": {
        "category": "backup",
        "required": False,
        "blocker": False,
        "format_regex": r"^(true|false)$",
        "format_hint": "true or false",
        "description": "Enable automated backups",
    },
    "BACKUP_RETENTION_DAYS": {
        "category": "backup",
        "required": False,
        "blocker": False,
        "format_regex": r"^\d+$",
        "format_hint": "Integer number of days",
        "description": "Backup retention period",
    },
    # Queue
    "CELERY_BROKER_URL": {
        "category": "queue",
        "required": False,
        "blocker": False,
        "format_regex": r"^(redis|amqp|sqs)://",
        "format_hint": "Broker URL",
        "description": "Celery broker URL",
    },
}

SENSITIVE_PATTERNS = re.compile(
    r"(token|secret|key|password|dsn|auth|sid|credential)", re.IGNORECASE
)


def _mask_value(key: str, value: str) -> str:
    if not value:
        return ""
    if SENSITIVE_PATTERNS.search(key):
        if len(value) <= 8:
            return "***"
        return value[:3] + "*" * min(len(value) - 6, 20) + value[-3:]
    if len(value) > 60:
        return value[:20] + "..." + value[-10:]
    return value


def _detect_source(key: str) -> str:
    """Detect where the config value originates from."""
    vault_addr = os.environ.get("VAULT_ADDR", "")
    aws_region = os.environ.get("AWS_REGION", "")
    value = os.environ.get(key, "")

    if not value:
        return "missing"
    if vault_addr and key.startswith("VAULT_"):
        return "vault"
    if aws_region and os.environ.get("SECRETS_PROVIDER", "") == "aws":
        return "aws_secrets_manager"
    if os.path.exists(f"/run/secrets/{key.lower()}"):
        return "docker_secret"
    return "env"


class ConfigActivationWorkflow:
    """Validates production config completeness and format correctness."""

    def validate_all(self) -> Dict[str, Any]:
        """Full validation with blocker/warning classification."""
        blockers: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        passed: List[Dict[str, Any]] = []
        format_errors: List[Dict[str, Any]] = []
        categories: Dict[str, Dict[str, Any]] = {}

        for var_name, cfg in CONFIG_DEFINITIONS.items():
            cat = cfg["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "configured": 0, "blockers": 0, "warnings": 0, "variables": []}

            categories[cat]["total"] += 1
            value = os.environ.get(var_name, "")
            is_set = bool(value)
            source = _detect_source(var_name)

            entry = {
                "variable": var_name,
                "description": cfg["description"],
                "required": cfg["required"],
                "blocker": cfg["blocker"],
                "configured": is_set,
                "source": source,
                "masked_value": _mask_value(var_name, value) if is_set else None,
                "format_valid": True,
                "format_hint": cfg.get("format_hint"),
            }

            # Format validation
            if is_set and cfg.get("format_regex"):
                if not re.match(cfg["format_regex"], value):
                    entry["format_valid"] = False
                    format_errors.append({
                        "variable": var_name,
                        "hint": cfg["format_hint"],
                        "blocker": cfg["blocker"],
                    })

            categories[cat]["variables"].append(entry)

            if is_set and entry["format_valid"]:
                categories[cat]["configured"] += 1
                passed.append(entry)
            elif not is_set:
                if cfg["blocker"]:
                    categories[cat]["blockers"] += 1
                    blockers.append(entry)
                elif cfg["required"]:
                    categories[cat]["warnings"] += 1
                    warnings.append(entry)
                else:
                    warnings.append(entry)

        total = len(CONFIG_DEFINITIONS)
        configured = len(passed)

        # Boot check
        has_blockers = len(blockers) > 0 or any(f["blocker"] for f in format_errors)
        if has_blockers:
            boot_status = "BLOCKED"
        elif len(warnings) > configured:
            boot_status = "WARNING"
        else:
            boot_status = "CLEAR"

        return {
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "boot_status": boot_status,
            "total_variables": total,
            "configured_count": configured,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "format_error_count": len(format_errors),
            "blockers": blockers,
            "warnings": warnings,
            "format_errors": format_errors,
            "categories": categories,
            "source_summary": self._get_source_summary(),
        }

    def _get_source_summary(self) -> Dict[str, int]:
        """Summary of config sources."""
        sources: Dict[str, int] = {}
        for var_name in CONFIG_DEFINITIONS:
            src = _detect_source(var_name)
            sources[src] = sources.get(src, 0) + 1
        return sources

    def get_boot_check(self) -> Dict[str, Any]:
        """Lightweight boot blocker check."""
        blockers = []
        for var_name, cfg in CONFIG_DEFINITIONS.items():
            if cfg["blocker"] and not os.environ.get(var_name, ""):
                blockers.append(var_name)

        return {
            "status": "BLOCKED" if blockers else "CLEAR",
            "blockers": blockers,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_category_status(self, category: str) -> Dict[str, Any]:
        """Get status for a specific config category."""
        entries = []
        for var_name, cfg in CONFIG_DEFINITIONS.items():
            if cfg["category"] != category:
                continue
            value = os.environ.get(var_name, "")
            entries.append({
                "variable": var_name,
                "configured": bool(value),
                "source": _detect_source(var_name),
                "masked_value": _mask_value(var_name, value) if value else None,
            })
        return {"category": category, "variables": entries}


# Singleton
config_activation = ConfigActivationWorkflow()
