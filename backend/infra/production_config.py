"""
Production Configuration Validator — Environment validation, startup checks,
missing secrets detection, and masked configuration audit.

Validates all required production environment variables at startup and
provides a masked inspection endpoint for debugging without exposing secrets.
"""
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.production_config")


def is_production_env() -> bool:
    """Unified production-mode detection across env-var conventions.

    Returns True when ANY of these is set to ``"production"`` (case-insensitive):
        - ``APP_ENV``       (used by crypto/secrets/controlplane fail-hard checks)
        - ``ENVIRONMENT``   (Replit deployment convention)
        - ``NODE_ENV``      (frontend / cross-stack convention)

    A single helper prevents the bug where one production gate activates while
    another silently no-ops because the operator set a different env-var key.
    """
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        if os.environ.get(key, "").strip().lower() == "production":
            return True
    return False


def is_strict_env() -> bool:
    """True when running in production OR staging (any of the 3 keys).

    Used by the crypto/secrets/controlplane startup blocks that historically
    re-raise on init failures in both production and staging environments.
    Mirrors the prior ``APP_ENV in ("production", "staging")`` semantics but
    additionally honors ENVIRONMENT/NODE_ENV so deployments using the Replit
    naming convention are protected by the same fail-hard gates.
    """
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        if os.environ.get(key, "").strip().lower() in {"production", "staging"}:
            return True
    return False


# v109 round-8 6th-pass: hoisted to module scope so tests can monkey-patch
# the table and exercise the real ``startup_check`` code path with a sentinel
# hash, instead of replacing the method entirely.
FORBIDDEN_DEV_HASHES: dict[str, str] = {
    "JWT_SECRET": "22a37967b374a741a098889a2e138a1899499d0ae54e05fcd503e7bb6f86196d",
    "QUICKID_SERVICE_KEY": "868a835b20ce9fa05d2a549e0d3812178d717279e438cde6bd56e6bbd10b2929",
    "AFSADAKAT_ADMIN_TOKEN": "0b2b61eaa2e151477eb687402d1c9ef6252c76644419d78964ed3145afcc681c",
    "CM_MASTER_KEY_CURRENT": "6c746409f783b492d492026d654d7680a0ea9ca4078fc7aecdcfa1837c3ea4bf",
    "HR_TOKEN": "d8653c8676059b84c4299f805848f826b998746cc44a25c838c9daa976aa4815",
}


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

    # Web Push (PWA) — VAPID keypair shared by every backend instance.
    # Required in production: web_push.get_vapid_keys() refuses to fall back to
    # a per-process keypair (which would invalidate every browser
    # PushSubscription pinned to the previous public key and write the private
    # key to MongoDB in plain text). Marked critical so they surface in the
    # readiness report; the explicit boot-time gate lives in startup_check().
    "VAPID_PUBLIC_KEY": {"category": "messaging", "critical": True, "description": "Web Push VAPID public key (P-256 raw, base64url)"},
    "VAPID_PRIVATE_KEY": {"category": "messaging", "critical": True, "description": "Web Push VAPID private key (32-byte scalar, base64url)"},

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
        self._validation_result: dict | None = None
        self._startup_time = datetime.now(UTC).isoformat()

    def validate_all(self) -> dict[str, Any]:
        """Run full environment validation. Returns structured result."""
        results = {
            "validated_at": datetime.now(UTC).isoformat(),
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

    def get_masked_config(self) -> dict[str, Any]:
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
            "inspected_at": datetime.now(UTC).isoformat(),
            "config": config,
        }

    def startup_check(self) -> dict[str, Any]:
        """Lightweight startup validation — fails fast on missing critical vars."""
        import hashlib
        missing = []
        for var_name, meta in PRODUCTION_VARIABLES.items():
            if meta["critical"] and not os.environ.get(var_name, ""):
                missing.append(var_name)

        # v42 round-2 + v109 round-8 5th-pass: fail-closed tenant isolation guard.
        # Production MUST run with STRICT_TENANT_MODE=true (defense-in-depth
        # around any handler that forgets `Depends(get_current_user)`). In
        # production we abort startup; in dev we only warn so local debugging
        # is unaffected. Detection unified across APP_ENV/ENVIRONMENT/NODE_ENV
        # so an operator setting any one of them activates all production
        # gates (existing crypto/secrets/controlplane checks above use APP_ENV).
        is_prod = is_production_env()
        strict_ok = os.environ.get("STRICT_TENANT_MODE", "").lower() == "true"
        tenant_guard_violation = is_prod and not strict_ok

        # v109 round-8 architect 3rd-pass: production must NOT boot with the
        # known leaked dev values present in `.replit` plaintext. We use only
        # SHA-256 fingerprints (the actual secret bytes are never embedded in
        # code). The table lives at module scope so tests can monkey-patch it
        # to validate this real code path with a synthetic sentinel hash.
        forbidden_present = []
        if is_prod:
            # Read the table fresh each call so monkeypatch.setattr works.
            forbidden_table = globals()["FORBIDDEN_DEV_HASHES"]
            for var_name, expected_hash in forbidden_table.items():
                value = os.environ.get(var_name, "")
                if value and hashlib.sha256(value.encode()).hexdigest() == expected_hash:
                    forbidden_present.append(var_name)

        # Task #33: surface missing Web Push VAPID keys at boot instead of
        # only at first push delivery. `web_push.get_vapid_keys()` already
        # raises `VapidKeysMissingError` in production when these env vars
        # are unset, but that exception fires lazily on the first urgent
        # message, often hours/days after the deploy. Promote the same gate
        # to startup time so a misconfigured production deploy fails loud
        # immediately. Dev keeps the historical fallback (db-persisted
        # auto-generated keypair) and only logs a warning here.
        vapid_missing = [
            v for v in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY")
            if not os.environ.get(v, "")
        ]
        vapid_violation = is_prod and bool(vapid_missing)

        status = "pass" if not missing and not tenant_guard_violation and not forbidden_present and not vapid_violation else "fail"
        if missing:
            level = logging.WARNING if not is_prod else logging.ERROR
            logger.log(level, "Startup check — missing critical vars: %s", missing)
        if tenant_guard_violation:
            logger.error(
                "Startup check FAILED — STRICT_TENANT_MODE must be 'true' in production "
                "(defense-in-depth tenant isolation). Refusing to boot."
            )
            raise RuntimeError(
                "STRICT_TENANT_MODE=true is required in production. "
                "Remove the override or set ENVIRONMENT/NODE_ENV != 'production'."
            )
        if forbidden_present:
            logger.error(
                "Startup check FAILED — production environment is using KNOWN DEV/LEAKED "
                "values for: %s. Rotate these secrets via the Replit Secrets vault BEFORE "
                "publishing and remove the plaintext from .replit. Refusing to boot.",
                forbidden_present,
            )
            raise RuntimeError(
                f"Production refused to boot: forbidden dev secret values detected for "
                f"{forbidden_present}. See replit.md → Round-8 production checklist."
            )
        # Task #33: VAPID gate. In production, missing Web Push keys must
        # abort the boot so urgent push notifications never silently degrade.
        # In dev, log a single warning so the developer notices but local
        # work is unaffected (web_push.get_vapid_keys keeps the db fallback).
        if vapid_missing:
            if vapid_violation:
                logger.error(
                    "Startup check FAILED — Web Push VAPID keys are not configured: %s. "
                    "Set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY as Replit Secrets so every "
                    "backend instance shares the same keypair and the private key is never "
                    "written to MongoDB. Refusing to boot.",
                    vapid_missing,
                )
                raise RuntimeError(
                    f"Production refused to boot: missing Web Push VAPID env vars "
                    f"{vapid_missing}. Configure them in Replit Secrets before deploying."
                )
            logger.warning(
                "Startup check — Web Push VAPID keys are not set (%s). Development "
                "fallback (db-persisted auto-generated keypair) will be used; production "
                "deploys will refuse to start without these env vars.",
                vapid_missing,
            )
        if not missing and not tenant_guard_violation and not forbidden_present and not vapid_violation:
            logger.info("Startup check passed — all critical variables present")

        return {
            "status": status,
            "missing_critical": missing,
            "strict_tenant_mode": strict_ok,
            "forbidden_dev_secrets_present": forbidden_present,
            "vapid_keys_missing": vapid_missing,
            "checked_at": datetime.now(UTC).isoformat(),
            "startup_time": self._startup_time,
        }

    def detect_leaked_secrets(self) -> dict[str, Any]:
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
            "scanned_at": datetime.now(UTC).isoformat(),
            "suspicious_count": len(suspicious),
            "suspicious_variables": suspicious,
            "status": "clean" if not suspicious else "review_needed",
        }


production_config = ProductionConfigValidator()
