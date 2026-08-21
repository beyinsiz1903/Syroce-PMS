"""Shared encrypted provider credential storage.

This module is intentionally domain-neutral so platform administration and the
channel-manager domain can use the same vault without cross-domain imports.
"""

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from core.crypto import AADContext, get_crypto_service
from core.database import db

logger = logging.getLogger("core.provider_credential_vault")

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
    credentials: dict[str, str], tenant_id: str, provider: str, property_id: str
) -> dict[str, str]:
    return get_crypto_service().encrypt_dict(
        credentials,
        aad=_build_aad(tenant_id, provider, property_id),
    )


def _decrypt_payload(
    encrypted: dict[str, str], tenant_id: str, provider: str, property_id: str
) -> dict[str, str]:
    return get_crypto_service().decrypt_dict(
        encrypted,
        aad=_build_aad(tenant_id, provider, property_id),
    )


async def store_secret(
    tenant_id: str,
    provider: str,
    property_id: str,
    credentials: dict[str, str],
    *,
    database=None,
) -> str:
    """Encrypt and upsert a provider secret, returning its stable id."""
    secret_id = str(uuid.uuid4())
    now = _now()
    encrypted = _encrypt_payload(credentials, tenant_id, provider, property_id)
    target_db = database if database is not None else db
    existing = await target_db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if existing:
        secret_id = existing["id"]
        await target_db[COLL_PROVIDER_SECRETS].update_one(
            {"id": secret_id},
            {
                "$set": {
                    "encrypted_payload": encrypted,
                    "key_version": get_crypto_service()._keyring.current_kid,
                    "field_names": list(credentials),
                    "updated_at": now,
                    "rotated_at": now,
                }
            },
        )
        logger.info("Rotated credentials for %s/%s", provider, property_id)
    else:
        await target_db[COLL_PROVIDER_SECRETS].insert_one(
            {
                "id": secret_id,
                "tenant_id": tenant_id,
                "provider": provider,
                "property_id": property_id,
                "encrypted_payload": encrypted,
                "key_version": get_crypto_service()._keyring.current_kid,
                "field_names": list(credentials),
                "created_at": now,
                "updated_at": now,
                "rotated_at": None,
            }
        )
        logger.info("Stored new credentials for %s/%s", provider, property_id)
    return secret_id


async def get_decrypted_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str] | None:
    """Retrieve and decrypt credentials in the active tenant context."""
    doc = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None
    return _decrypt_payload(doc.get("encrypted_payload", {}), tenant_id, provider, property_id)


async def get_masked_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
    *,
    database=None,
) -> dict[str, Any] | None:
    """Return masked credential metadata; plaintext values never leave the vault."""
    target_db = database if database is not None else db
    doc = await target_db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None
    decrypted = _decrypt_payload(doc.get("encrypted_payload", {}), tenant_id, provider, property_id)
    return {
        "secret_id": doc["id"],
        "provider": doc["provider"],
        "property_id": doc["property_id"],
        "fields": get_crypto_service().mask_credentials(decrypted),
        "field_names": doc.get("field_names", []),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "rotated_at": doc.get("rotated_at"),
    }


async def delete_secret(tenant_id: str, provider: str, property_id: str) -> bool:
    result = await db[COLL_PROVIDER_SECRETS].delete_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id}
    )
    return result.deleted_count > 0
