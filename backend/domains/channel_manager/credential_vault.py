"""
Channel Manager — Credential Vault
====================================

Encrypted secret storage for provider credentials.
Vault-ready abstraction: today encrypted MongoDB collection,
tomorrow real secret manager (AWS Secrets Manager, HashiCorp Vault, etc.)

provider_connections stores credentials_ref → provider_secrets stores encrypted payload.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import db
from .encryption import encrypt_credential, decrypt_credential, mask_credential

logger = logging.getLogger("channel_manager.credential_vault")

COLL_PROVIDER_SECRETS = "provider_secrets"
_NO_ID = {"_id": 0}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encrypt_payload(credentials: Dict[str, str]) -> Dict[str, str]:
    """Encrypt all values in a credentials dict."""
    return {k: encrypt_credential(str(v)) for k, v in credentials.items() if v}


def _decrypt_payload(encrypted: Dict[str, str]) -> Dict[str, str]:
    """Decrypt all values in an encrypted credentials dict."""
    return {k: decrypt_credential(v) for k, v in encrypted.items()}


def _mask_payload(credentials: Dict[str, str]) -> Dict[str, str]:
    """Mask all values for display."""
    return {k: mask_credential(str(v)) for k, v in credentials.items()}


# ── CRUD Operations ──────────────────────────────────────────────────

async def store_secret(
    tenant_id: str,
    provider: str,
    property_id: str,
    credentials: Dict[str, str],
) -> str:
    """Encrypt and store credentials. Returns secret_id (credentials_ref)."""
    secret_id = str(uuid.uuid4())
    now = _now()
    encrypted = _encrypt_payload(credentials)

    doc = {
        "id": secret_id,
        "tenant_id": tenant_id,
        "provider": provider,
        "property_id": property_id,
        "encrypted_payload": encrypted,
        "key_version": "v1",
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
            {"$set": {
                "encrypted_payload": encrypted,
                "field_names": list(credentials.keys()),
                "updated_at": now,
                "rotated_at": now,
            }},
        )
        logger.info(f"Rotated credentials for {provider}/{property_id}")
    else:
        await db[COLL_PROVIDER_SECRETS].insert_one(doc)
        logger.info(f"Stored new credentials for {provider}/{property_id}")

    return secret_id


async def get_decrypted_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> Optional[Dict[str, str]]:
    """Retrieve and decrypt credentials."""
    doc = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None
    return _decrypt_payload(doc.get("encrypted_payload", {}))


async def get_masked_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> Optional[Dict[str, Any]]:
    """Get masked credentials for display (never expose raw values)."""
    doc = await db[COLL_PROVIDER_SECRETS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not doc:
        return None

    decrypted = _decrypt_payload(doc.get("encrypted_payload", {}))
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
