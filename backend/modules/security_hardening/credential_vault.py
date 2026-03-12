"""
Credential Vault - Secure credential storage with rotation support.
Abstracts credential storage for tenant-specific provider credentials.
"""
import logging
import hashlib
import base64
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from core.database import db

logger = logging.getLogger("security.vault")


class CredentialVault:
    """Manages tenant-specific credentials with encryption and rotation."""

    CREDENTIAL_TYPES = [
        "twilio", "sendgrid", "whatsapp", "stripe", "ota_api",
        "redis", "smtp", "webhook", "custom",
    ]

    def _mask_value(self, value: str) -> str:
        if len(value) <= 8:
            return "****"
        return value[:4] + "*" * (len(value) - 8) + value[-4:]

    def _hash_value(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    async def store_credential(self, tenant_id: str, credential_type: str,
                               credential_key: str, credential_value: str,
                               description: str = "",
                               rotation_days: int = 90) -> Dict[str, Any]:
        """Store a credential securely."""
        cred_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Encode the value (in production, use real encryption like AES-256)
        encoded = base64.b64encode(credential_value.encode()).decode()

        record = {
            "id": cred_id,
            "tenant_id": tenant_id,
            "credential_type": credential_type,
            "credential_key": credential_key,
            "credential_value_hash": self._hash_value(credential_value),
            "credential_value_encoded": encoded,
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
        logger.info(f"Credential stored: {credential_type}/{credential_key} for tenant {tenant_id}")

        return {
            "id": cred_id,
            "credential_type": credential_type,
            "credential_key": credential_key,
            "masked_value": self._mask_value(credential_value),
            "next_rotation": record["next_rotation"],
            "status": "active",
        }

    async def get_credential(self, tenant_id: str, credential_type: str,
                             credential_key: str) -> Optional[str]:
        """Retrieve a credential value (decrypted)."""
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
                "$set": {"last_accessed": datetime.now(timezone.utc).isoformat()},
            },
        )

        encoded = record.get("credential_value_encoded", "")
        return base64.b64decode(encoded.encode()).decode() if encoded else None

    async def rotate_credential(self, tenant_id: str, credential_id: str,
                                new_value: str) -> Dict[str, Any]:
        """Rotate a credential to a new value."""
        now = datetime.now(timezone.utc)
        record = await db.credential_vault.find_one(
            {"id": credential_id, "tenant_id": tenant_id},
            {"_id": 0},
        )
        if not record:
            return {"error": "Credential not found"}

        encoded = base64.b64encode(new_value.encode()).decode()
        await db.credential_vault.update_one(
            {"id": credential_id},
            {"$set": {
                "credential_value_encoded": encoded,
                "credential_value_hash": self._hash_value(new_value),
                "last_rotated": now.isoformat(),
                "next_rotation": (now + timedelta(days=record.get("rotation_days", 90))).isoformat(),
            }},
        )
        return {
            "id": credential_id,
            "rotated": True,
            "rotated_at": now.isoformat(),
            "next_rotation": (now + timedelta(days=record.get("rotation_days", 90))).isoformat(),
        }

    async def get_vault_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get vault status and rotation needs."""
        now = datetime.now(timezone.utc).isoformat()
        creds = await db.credential_vault.find(
            {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}
        ).to_list(100)

        needs_rotation = [
            {
                "id": c["id"],
                "type": c["credential_type"],
                "key": c["credential_key"],
                "next_rotation": c.get("next_rotation"),
                "days_overdue": max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(
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

    async def check_leakage(self, tenant_id: str) -> Dict[str, Any]:
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
