"""
Control Plane — Startup Validation
====================================
Validates critical system components at application startup.
Fails LOUDLY if anything critical is missing or misconfigured.

Checks:
  1. Crypto keys loaded and functional
  2. Secrets manager operational
  3. Required MongoDB indexes exist
  4. Required environment variables present
"""
import logging
import os
from typing import Dict, List

logger = logging.getLogger("controlplane.startup_validator")


class StartupValidationError(RuntimeError):
    """Raised when a critical startup check fails."""
    pass


async def validate_startup(*, strict: bool = False) -> Dict[str, any]:
    """Run all startup validations.

    Args:
        strict: If True, raise on any failure (production mode).
                If False, log warnings but continue (dev mode).

    Returns:
        Validation report with pass/fail for each check.
    """
    report = {
        "crypto": {"status": "unknown", "details": {}},
        "secrets": {"status": "unknown", "details": {}},
        "indexes": {"status": "unknown", "details": {}},
        "env": {"status": "unknown", "details": {}},
    }
    failures: List[str] = []

    # ── 1. Crypto Keys ────────────────────────────────────────────
    try:
        from core.crypto import get_crypto_service
        crypto_svc = get_crypto_service()
        health = crypto_svc.health()
        report["crypto"] = {
            "status": "pass",
            "details": {
                "v2_enabled": health.get("v2_enabled", False),
                "current_kid": health.get("current_kid", ""),
                "bypass_active": health.get("bypass_active", False),
            },
        }
        if health.get("bypass_active"):
            logger.critical("STARTUP: CRYPTO_BYPASS_ALLOWED=true — ENCRYPTION DISABLED")
            if strict:
                failures.append("Crypto bypass is active in strict mode")
    except Exception as e:
        report["crypto"] = {"status": "fail", "details": {"error": str(e)}}
        failures.append(f"Crypto validation failed: {e}")
        logger.error("STARTUP: Crypto validation FAILED: %s", e)

    # ── 2. Secrets Manager ────────────────────────────────────────
    try:
        from core.secrets import get_secrets_manager, get_secrets_config
        config = get_secrets_config()
        sm = get_secrets_manager()
        await sm.ensure_indexes()
        report["secrets"] = {
            "status": "pass",
            "details": {
                "provider": config.provider,
                "app_env": config.app_env,
                "audit_enabled": config.audit_enabled,
            },
        }
    except Exception as e:
        report["secrets"] = {"status": "fail", "details": {"error": str(e)}}
        failures.append(f"Secrets manager validation failed: {e}")
        logger.error("STARTUP: Secrets manager validation FAILED: %s", e)

    # ── 3. Required Indexes ───────────────────────────────────────
    try:
        from controlplane.indexes import ensure_controlplane_indexes
        from core.database import db
        await ensure_controlplane_indexes(db)
        report["indexes"] = {"status": "pass", "details": {"created": True}}
    except Exception as e:
        report["indexes"] = {"status": "fail", "details": {"error": str(e)}}
        failures.append(f"Index creation failed: {e}")
        logger.error("STARTUP: Index creation FAILED: %s", e)

    # ── 4. Required Environment Variables ─────────────────────────
    required_vars = [
        "CM_MASTER_KEY_CURRENT",
        "CM_KEY_VERSION",
    ]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        report["env"] = {"status": "fail", "details": {"missing": missing}}
        failures.append(f"Missing env vars: {', '.join(missing)}")
        logger.error("STARTUP: Missing required env vars: %s", missing)
    else:
        report["env"] = {"status": "pass", "details": {"checked": required_vars}}

    # ── Result ────────────────────────────────────────────────────
    all_passed = len(failures) == 0
    report["overall"] = "pass" if all_passed else "fail"
    report["failures"] = failures

    if failures and strict:
        raise StartupValidationError(
            f"Startup validation failed ({len(failures)} issues): {'; '.join(failures)}"
        )

    if all_passed:
        logger.info("STARTUP: All control plane validations PASSED")
    else:
        logger.warning("STARTUP: Control plane validation issues: %s", failures)

    return report
