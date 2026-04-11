"""
Credential Vault — Secure credential storage with rotation support.
REFACTORED: Uses core.crypto for real encryption instead of base64 encoding.
"""
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.crypto import AADContext, get_crypto_service
from core.database import db

logger = logging.getLogger("security.vault")


class CredentialVault:
    """Manages tenant-specific credentials with encryption and rotation."""

    CREDENTIAL_TYPES = [
        "twilio", "sendgrid", "whatsapp", "stripe", "ota_api",
        "redis", "smtp", "webhook", "custom",
    ]

    def _build_aad(self, tenant_id: str, credential_type: str, credential_key: str) -> AADContext:
        return AADContext(
            tenant_id=tenant_id,
            provider=credential_type,
            property_id=credential_key,
            environment=os.environ.get("APP_ENV", "development"),
            context_type="credential",
        )

    def _mask_value(self, value: str) -> str:
        svc = get_crypto_service()
        return svc.mask(value, visible_suffix=4)

    async def store_credential(self, tenant_id: str, credential_type: str,
                               credential_key: str, credential_value: str,
                               description: str = "",
                               rotation_days: int = 90) -> dict[str, Any]:
        """Store a credential securely with real encryption."""
        cred_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        svc = get_crypto_service()
        aad = self._build_aad(tenant_id, credential_type, credential_key)
        encrypted = svc.encrypt(credential_value, aad=aad)

        record = {
            "id": cred_id,
            "tenant_id": tenant_id,
            "credential_type": credential_type,
            "credential_key": credential_key,
            "credential_encrypted": encrypted,
            "key_version": svc._keyring.current_kid,
            "description": description,
            "rotation_days": rotation_days,
            "next_rotation": (now + timedelta(days=rotation_days)).isoformat(),
            "last_rotated": now.isoformat(),
            "access_count": 0,
            "last_accessed": None,
            "created_at": now.isoformat(),
            "status": "active",
        }

        await db.credential_vault.insert_one({**record})
        logger.info("Credential stored: %s/%s for tenant %s", credential_type, credential_key, tenant_id)

        return {
            "id": cred_id,
            "credential_type": credential_type,
            "credential_key": credential_key,
            "masked_value": self._mask_value(credential_value),
            "next_rotation": record["next_rotation"],
            "status": "active",
        }

    async def get_credential(self, tenant_id: str, credential_type: str,
                             credential_key: str) -> str | None:
        """Retrieve and decrypt a credential value."""
        record = await db.credential_vault.find_one(
            {
                "tenant_id": tenant_id,
                "credential_type": credential_type,
                "credential_key": credential_key,
                "status": "active",
            },
            {"_id": 0},
        )
        if not record:
            return None

        # Update access tracking
        await db.credential_vault.update_one(
            {"id": record["id"]},
            {
                "$inc": {"access_count": 1},
                "$set": {"last_accessed": datetime.now(UTC).isoformat()},
            },
        )

        # Decrypt — supports both new and legacy formats
        svc = get_crypto_service()
        aad = self._build_aad(tenant_id, credential_type, credential_key)

        # New format
        encrypted = record.get("credential_encrypted", "")
        if encrypted:
            return svc.decrypt(encrypted, aad=aad)

        # Legacy base64 format (backward compat)
        encoded = record.get("credential_value_encoded", "")
        if encoded:
            return svc.decrypt_legacy_base64(encoded)

        return None

    async def rotate_credential(self, tenant_id: str, credential_id: str,
                                new_value: str) -> dict[str, Any]:
        """Rotate a credential to a new value."""
        now = datetime.now(UTC)
        record = await db.credential_vault.find_one(
            {"id": credential_id, "tenant_id": tenant_id},
            {"_id": 0},
        )
        if not record:
            return {"error": "Credential not found"}

        svc = get_crypto_service()
        aad = self._build_aad(
            tenant_id, record["credential_type"], record["credential_key"],
        )
        encrypted = svc.encrypt(new_value, aad=aad)

        await db.credential_vault.update_one(
            {"id": credential_id},
            {"$set": {
                "credential_encrypted": encrypted,
                "key_version": svc._keyring.current_kid,
                "last_rotated": now.isoformat(),
                "next_rotation": (now + timedelta(days=record.get("rotation_days", 90))).isoformat(),
                # Clear legacy field if present
                "credential_value_encoded": None,
                "credential_value_hash": None,
            }},
        )
        return {
            "id": credential_id,
            "rotated": True,
            "rotated_at": now.isoformat(),
            "next_rotation": (now + timedelta(days=record.get("rotation_days", 90))).isoformat(),
        }

    async def get_vault_status(self, tenant_id: str) -> dict[str, Any]:
        """Get vault status and rotation needs."""
        now = datetime.now(UTC).isoformat()
        creds = await db.credential_vault.find(
            {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}
        ).to_list(100)

        needs_rotation = [
            {
                "id": c["id"],
                "type": c["credential_type"],
                "key": c["credential_key"],
                "next_rotation": c.get("next_rotation"),
                "days_overdue": max(0, (datetime.now(UTC) - datetime.fromisoformat(
                    c.get("next_rotation", now).replace("Z", "+00:00")
                )).days) if c.get("next_rotation") else 0,
            }
            for c in creds
            if c.get("next_rotation", "") < now
        ]

        return {
            "tenant_id": tenant_id,
            "total_credentials": len(creds),
            "by_type": {},
            "needs_rotation": needs_rotation,
            "rotation_overdue_count": len(needs_rotation),
            "vault_health": "healthy" if len(needs_rotation) == 0 else "attention_needed",
            "checked_at": now,
        }

    async def check_leakage(self, tenant_id: str) -> dict[str, Any]:
        """Check for potential credential leakage indicators."""
        creds = await db.credential_vault.find(
            {"tenant_id": tenant_id, "status": "active"},
            {"_id": 0, "id": 1, "credential_type": 1, "credential_key": 1,
             "access_count": 1, "last_accessed": 1},
        ).to_list(100)

        high_access = [c for c in creds if c.get("access_count", 0) > 100]
        return {
            "tenant_id": tenant_id,
            "total_credentials": len(creds),
            "high_access_credentials": len(high_access),
            "leakage_risk": "low" if len(high_access) == 0 else "medium",
            "details": high_access[:10],
        }


credential_vault = CredentialVault()
