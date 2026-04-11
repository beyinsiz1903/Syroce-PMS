"""
Secret Classification Router — APIs for secret lifecycle management.

Provides:
  GET  /api/ops/secrets/classification   — Secret classification policy
  GET  /api/ops/secrets/inventory        — Classified secret inventory
  GET  /api/ops/pii/policy               — PII masking policy document
  GET  /api/ops/pii/audit                — PII access audit trail
  GET  /api/ops/pii/anomalies            — PII access anomaly detection
  GET  /api/ops/kms/status               — KMS envelope encryption status
  GET  /api/ops/pii/metrics              — PII masking middleware metrics
"""
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from core.database import db
from security.ops_guard import require_ops_access

logger = logging.getLogger("security.classification_router")

router = APIRouter(
    prefix="/api/ops",
    tags=["Security — Classification & PII"],
    dependencies=[Depends(require_ops_access)],
)


@router.get("/secrets/classification")
async def secrets_classification():
    """Return the full secret classification policy with lifecycle rules."""
    from security.pii_registry import SECRET_LIFECYCLE, SecretType

    classification = {}
    for secret_type in SecretType:
        lifecycle = SECRET_LIFECYCLE.get(secret_type, {})
        classification[secret_type.value] = {
            "type": secret_type.value,
            "lifecycle": lifecycle,
            "description": _SECRET_DESCRIPTIONS.get(secret_type, ""),
        }

    return {
        "classification": classification,
        "policy_version": "1.0.0",
        "last_updated": "2026-02-26",
        "enforcement": "active",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/secrets/inventory")
async def secrets_inventory():
    """Classified inventory of all managed secrets."""
    from security.pii_registry import SECRET_LIFECYCLE, SecretType

    inventory = {st.value: {"count": 0, "items": []} for st in SecretType}

    # Scan _dev_secrets
    try:
        async for doc in db["_dev_secrets"].find(
            {}, {"_id": 0, "path": 1, "created_at": 1, "updated_at": 1,
                 "rotation_count": 1, "tags": 1}
        ):
            path = doc.get("path", "")
            parts = path.split("/")
            if len(parts) < 6:
                continue

            secret_type = _classify_secret(parts)
            lifecycle = SECRET_LIFECYCLE.get(secret_type, {})

            item = {
                "path_masked": _mask_path(path),
                "type": secret_type.value,
                "created_at": doc.get("created_at", ""),
                "updated_at": doc.get("updated_at", ""),
                "rotation_count": doc.get("rotation_count", 0),
                "max_rotation_days": lifecycle.get("rotation_max_days", 0),
            }
            inventory[secret_type.value]["count"] += 1
            inventory[secret_type.value]["items"].append(item)
    except Exception as e:
        logger.error("Secret inventory scan failed: %s", e)

    # Count env-based secrets
    env_secrets = _scan_env_secrets()
    for secret in env_secrets:
        st = secret["type"]
        inventory[st]["count"] += 1
        inventory[st]["items"].append(secret)

    total = sum(v["count"] for v in inventory.values())

    return {
        "inventory": inventory,
        "total_secrets": total,
        "environment": os.environ.get("APP_ENV", "development"),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/pii/policy")
async def pii_policy():
    """Return the full PII masking policy document."""
    from security.pii_registry import get_pii_policy_summary

    return {
        "policy": get_pii_policy_summary(),
        "enforcement": "middleware_active",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/pii/audit")
async def pii_audit_trail(
    tenant_id: str | None = Query(None),
    user_id: str | None = Query(None),
    unmasked_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Query PII access audit trail."""
    from security.pii_audit import get_pii_audit

    audit = get_pii_audit()
    result = await audit.get_audit_trail(
        tenant_id=tenant_id,
        user_id=user_id,
        was_unmasked=True if unmasked_only else None,
        limit=limit,
        skip=skip,
    )
    return result


@router.get("/pii/anomalies")
async def pii_anomalies(
    hours: int = Query(24, ge=1, le=168),
    tenant_id: str | None = Query(None),
):
    """Detect anomalous PII access patterns."""
    from security.pii_audit import get_pii_audit

    audit = get_pii_audit()
    return await audit.get_anomalies(hours=hours, tenant_id=tenant_id)


@router.get("/kms/status")
async def kms_status():
    """AWS KMS envelope encryption status and health."""
    from core.crypto.kms_provider import get_kms_encryption

    kms = get_kms_encryption()
    health = kms.health_check()

    return {
        **health,
        "envelope_format": "KMS1:",
        "config": {
            "key_arn_configured": bool(os.environ.get("AWS_KMS_KEY_ARN")),
            "region": os.environ.get("AWS_REGION", "not_set"),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/pii/metrics")
async def pii_metrics():
    """PII masking middleware runtime metrics."""
    return {
        "middleware": "active",
        "pii_fields_registered": _count_pii_fields(),
        "categories": _count_pii_categories(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ── Helpers ────────────────────────────────────────────────────────

_SECRET_DESCRIPTIONS = {}

def _init_descriptions():
    from security.pii_registry import SecretType
    global _SECRET_DESCRIPTIONS
    _SECRET_DESCRIPTIONS = {
        SecretType.JWT_APP: "JWT signing keys and application secrets",
        SecretType.CONNECTOR_CREDENTIAL: "Channel manager provider credentials (Exely, Booking.com, etc.)",
        SecretType.WEBHOOK_SECRET: "Webhook signing and verification secrets",
        SecretType.ENCRYPTION_KEY: "Master encryption keys and key material",
        SecretType.THIRD_PARTY_API: "External third-party API keys",
        SecretType.DATABASE: "Database connection strings and passwords",
        SecretType.INTERNAL: "Internal service-to-service tokens",
    }

_init_descriptions()


def _classify_secret(path_parts: list[str]):
    """Classify a secret based on its path."""
    from security.pii_registry import SecretType

    if len(path_parts) < 5:
        return SecretType.INTERNAL

    segment = path_parts[2].lower() if len(path_parts) > 2 else ""
    provider = path_parts[4].lower() if len(path_parts) > 4 else ""

    if segment == "channel-manager":
        return SecretType.CONNECTOR_CREDENTIAL
    if "webhook" in provider:
        return SecretType.WEBHOOK_SECRET
    if "key" in provider or "encryption" in provider:
        return SecretType.ENCRYPTION_KEY
    return SecretType.CONNECTOR_CREDENTIAL


def _mask_path(path: str) -> str:
    """Mask tenant/property IDs in secret path for display."""
    parts = path.split("/")
    if len(parts) >= 6:
        parts[3] = parts[3][:4] + "***"  # tenant
        parts[5] = parts[5][:4] + "***"  # property
    return "/".join(parts)


def _scan_env_secrets() -> list[dict]:
    """Identify secrets stored as environment variables."""
    from security.pii_registry import SecretType

    env_secrets = []
    secret_env_map = {
        "JWT_SECRET": SecretType.JWT_APP,
        "CM_CREDENTIAL_KEY": SecretType.ENCRYPTION_KEY,
        "CM_MASTER_KEY_CURRENT": SecretType.ENCRYPTION_KEY,
        "CM_MASTER_KEY_PREVIOUS": SecretType.ENCRYPTION_KEY,
        "EMERGENT_LLM_KEY": SecretType.THIRD_PARTY_API,
        "MONGO_URL": SecretType.DATABASE,
    }

    for env_name, secret_type in secret_env_map.items():
        if os.environ.get(env_name):
            env_secrets.append({
                "path_masked": f"env://{env_name}",
                "type": secret_type.value,
                "storage": "environment_variable",
                "created_at": "N/A",
                "updated_at": "N/A",
                "rotation_count": 0,
                "max_rotation_days": 0,
            })

    return env_secrets


def _count_pii_fields() -> int:
    from security.pii_registry import PII_FIELDS
    return len(PII_FIELDS)


def _count_pii_categories() -> dict:
    from security.pii_registry import PII_FIELDS
    cats: dict[str, int] = {}
    for rule in PII_FIELDS.values():
        cat = rule.category.value
        cats[cat] = cats.get(cat, 0) + 1
    return cats
