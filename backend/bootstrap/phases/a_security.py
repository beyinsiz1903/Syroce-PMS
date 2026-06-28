"""Phase A — Security validators + core/control-plane indexes."""

import logging

from core.database import _raw_db

logger = logging.getLogger(__name__)


async def phase_a_security_and_core_indexes(app):
    # Crypto Service Validation
    try:
        from core.crypto import get_crypto_service

        crypto_svc = get_crypto_service()
        health = crypto_svc.health()
        logger.info(
            "Crypto service initialized: v2=%s kid=%s bypass=%s",
            health["v2_enabled"],
            health["current_kid"],
            health["bypass_active"],
        )
        if health["bypass_active"]:
            logger.critical("CRYPTO_BYPASS_ALLOWED=true — ENCRYPTION IS DISABLED")
    except Exception as e:
        logger.error(f"Crypto service startup failed: {e}")
        from infra.production_config import is_strict_env

        if is_strict_env():
            raise

    # Secrets Manager Validation
    try:
        from core.secrets import get_secrets_config, get_secrets_manager

        config = get_secrets_config()
        sm = get_secrets_manager()
        await sm.ensure_indexes()
        logger.info("Secrets manager initialized: provider=%s env=%s", config.provider, config.app_env)
    except Exception as e:
        logger.error(f"Secrets manager startup validation failed: {e}")
        from infra.production_config import is_strict_env

        if is_strict_env():
            raise

    # PII Audit indexes
    try:
        from security.pii_audit import get_pii_audit

        pii_audit = get_pii_audit()
        await pii_audit.ensure_indexes()
        logger.info("PII audit indexes ensured")
    except Exception as e:
        logger.warning(f"PII audit index creation error: {e}")

    # Rotation Engine indexes
    try:
        from security.rotation_engine import get_rotation_engine

        rotation_engine = get_rotation_engine()
        await rotation_engine.ensure_indexes()
        logger.info("Rotation engine indexes ensured")
    except Exception as e:
        logger.warning(f"Rotation engine index creation error: {e}")

    # Control Plane Startup Validation
    try:
        from controlplane.startup_validator import validate_startup
        from infra.production_config import is_strict_env

        strict = is_strict_env()
        cp_report = await validate_startup(strict=strict)
        logger.info(
            "Control plane validation: %s (%d issues)",
            cp_report.get("overall", "unknown"),
            len(cp_report.get("failures", [])),
        )
    except Exception as e:
        logger.error(f"Control plane startup validation failed: {e}")
        from infra.production_config import is_strict_env

        if is_strict_env():
            raise

    # Event Timeline indexes
    try:
        from controlplane.timeline_writer import ensure_timeline_indexes

        await ensure_timeline_indexes()
        logger.info("Event timeline indexes ensured")
    except Exception as e:
        logger.warning(f"Event timeline index creation error: {e}")

    # Webhook Raw Payload indexes
    try:
        await _raw_db.webhook_raw_payloads.create_index(
            [("correlation_id", 1)],
            name="idx_raw_payload_correlation",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("tenant_id", 1), ("external_id", 1), ("received_at", -1)],
            name="idx_raw_payload_tenant_ext",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("tenant_id", 1), ("provider", 1), ("received_at", -1)],
            name="idx_raw_payload_provider",
        )
        await _raw_db.webhook_raw_payloads.create_index(
            [("received_at", 1)],
            name="idx_raw_payload_ttl",
            expireAfterSeconds=7776000,  # 90 days
        )
        logger.info("Webhook raw payload indexes ensured")
    except Exception as e:
        logger.warning(f"Webhook raw payload index creation error: {e}")

    # Dashboard snapshot indexes + worker
    try:
        from controlplane.dashboard_aggregator import (
            ensure_snapshot_indexes,
            get_snapshot_worker,
        )

        await ensure_snapshot_indexes()
        snapshot_worker = get_snapshot_worker()
        await snapshot_worker.start()
        app.state.dashboard_snapshot_worker = snapshot_worker
        logger.info("Dashboard snapshot worker started (60s interval)")
    except Exception as e:
        logger.warning(f"Dashboard snapshot worker startup error: {e}")

    # Deploy event indexes
    try:
        from controlplane.deploy_tracker import ensure_deploy_indexes

        await ensure_deploy_indexes()
        logger.info("Deploy event indexes ensured")
    except Exception as e:
        logger.warning(f"Deploy event index creation error: {e}")
