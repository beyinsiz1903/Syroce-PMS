"""
Channel Manager — Credential Vault (REFACTORED)

Encrypted secret storage for provider credentials.
Delegates all encryption to core.crypto.CredentialEncryptionService.

provider_connections stores credentials_ref → provider_secrets stores encrypted payload.
"""

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from core.crypto import AADContext, get_crypto_service
from core.database import db

logger = logging.getLogger("channel_manager.credential_vault")

COLL_PROVIDER_SECRETS = "provider_secrets"
_NO_ID = {"_id": 0}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _build_aad(tenant_id: str, provider: str, property_id: str) -> AADContext:
    return AADContext(
        tenant_id=tenant_id,
        provider=provider,
        property_id=property_id,
        environment=os.environ.get("APP_ENV", "development"),
        context_type="credential",
    )


def _encrypt_payload(
    credentials: dict[str, str],
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str]:
    """Encrypt all values in a credentials dict."""
    svc = get_crypto_service()
    aad = _build_aad(tenant_id, provider, property_id)
    return svc.encrypt_dict(credentials, aad=aad)


def _decrypt_payload(
    encrypted: dict[str, str],
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str]:
    """Decrypt all values in an encrypted credentials dict."""
    svc = get_crypto_service()
    aad = _build_aad(tenant_id, provider, property_id)
    return svc.decrypt_dict(encrypted, aad=aad)


def _mask_payload(credentials: dict[str, str]) -> dict[str, str]:
    """Mask all values for display."""
    svc = get_crypto_service()
    return svc.mask_credentials(credentials)


# ── CRUD Operations ──────────────────────────────────────────────────


async def store_secret(
    tenant_id: str,
    provider: str,
    property_id: str,
    credentials: dict[str, str],
) -> str:
    """Encrypt and store credentials. Returns secret_id (credentials_ref)."""
    secret_id = str(uuid.uuid4())
    now = _now()
    encrypted = _encrypt_payload(credentials, tenant_id, provider, property_id)

    doc = {
        "id": secret_id,
        "tenant_id": tenant_id,
        "provider": provider,
        "property_id": property_id,
        "encrypted_payload": encrypted,
        "key_version": get_crypto_service()._keyring.current_kid,
        "field_names": list(credentials.keys()),
        "created_at": now,
        "updated_at": now,
        "rotated_at": None,
    }

    # Upsert: one secret per tenant+provider+property
    existing = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if existing:
        secret_id = existing["id"]
        await db[COLL_PROVIDER_SECRETS].update_one(
            {"id": secret_id},
            {
                "$set": {
                    "encrypted_payload": encrypted,
                    "key_version": get_crypto_service()._keyring.current_kid,
                    "field_names": list(credentials.keys()),
                    "updated_at": now,
                    "rotated_at": now,
                }
            },
        )
        logger.info("Rotated credentials for %s/%s", provider, property_id)
    else:
        await db[COLL_PROVIDER_SECRETS].insert_one(doc)
        logger.info("Stored new credentials for %s/%s", provider, property_id)

    return secret_id


async def get_decrypted_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str] | None:
    """Retrieve and decrypt credentials."""
    doc = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None
    return _decrypt_payload(
        doc.get("encrypted_payload", {}),
        tenant_id,
        provider,
        property_id,
    )


async def get_masked_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, Any] | None:
    """Get masked credentials for display (never expose raw values)."""
    doc = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None

    decrypted = _decrypt_payload(
        doc.get("encrypted_payload", {}),
        tenant_id,
        provider,
        property_id,
    )
    masked = _mask_payload(decrypted)

    return {
        "secret_id": doc["id"],
        "provider": doc["provider"],
        "property_id": doc["property_id"],
        "fields": masked,
        "field_names": doc.get("field_names", []),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "rotated_at": doc.get("rotated_at"),
    }


async def delete_secret(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> bool:
    """Remove stored credentials."""
    r = await db[COLL_PROVIDER_SECRETS].delete_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
    )
    return r.deleted_count > 0


async def link_credentials_to_connection(
    tenant_id: str,
    provider: str,
    property_id: str,
    secret_id: str,
) -> None:
    """Update provider_connection with credentials_ref."""
    from .data_model import COLL_PROVIDER_CONNECTIONS

    await db[COLL_PROVIDER_CONNECTIONS].update_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        {"$set": {"credentials_ref": secret_id, "updated_at": _now()}},
    )
