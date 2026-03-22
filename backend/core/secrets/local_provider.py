"""
Local development secrets backend.

Stores secrets in MongoDB collection `_dev_secrets` with AES-256-GCM encryption.
Explicitly gated: only usable when APP_ENV != production/staging.
Clearly marked as NON-PRODUCTION in all outputs.

This backend exists for developer ergonomics. It must NEVER silently become
the production default.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .provider import SecretsProviderBase, SecretPayload, SecretMetadata

logger = logging.getLogger("core.secrets.local_dev")

COLL_DEV_SECRETS = "_dev_secrets"
_NO_ID = {"_id": 0}


class LocalDevSecretsProvider(SecretsProviderBase):
    """
    MongoDB-backed development secrets store with AES-256-GCM encryption at rest.

    NOT FOR PRODUCTION. Gated by SecretsConfig.validate() at startup.
    """

    def __init__(self, encryption_key: str):
        from channel_manager.infrastructure.encryption_service import EncryptionService, KeyManagementService
        kms = KeyManagementService(raw_key=encryption_key or "dev-local-key-not-for-production")
        self._enc = EncryptionService(kms=kms)
        logger.warning(
            "LocalDevSecretsProvider initialized — THIS IS NOT A PRODUCTION SECRETS BACKEND"
        )

    def _get_db(self):
        from core.database import db
        return db

    def _encrypt_payload(self, data: Dict[str, str]) -> str:
        """Encrypt the entire payload as a single JSON blob."""
        plaintext = json.dumps(data)
        return self._enc.encrypt(plaintext)

    def _decrypt_payload(self, encrypted: str) -> Dict[str, str]:
        """Decrypt a JSON blob back to dict."""
        plaintext = self._enc.decrypt(encrypted)
        return json.loads(plaintext)

    async def create_secret(
        self,
        path: str,
        payload: Dict[str, str],
        tags: Optional[Dict[str, str]] = None,
    ) -> SecretMetadata:
        db = self._get_db()
        existing = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if existing:
            raise ValueError(f"Secret already exists: {path}")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "path": path,
            "encrypted_payload": self._encrypt_payload(payload),
            "field_names": list(payload.keys()),
            "version": "1",
            "rotation_count": 0,
            "tags": tags or {},
            "created_at": now,
            "updated_at": now,
            "backend": "local_dev",
        }
        await db[COLL_DEV_SECRETS].insert_one(doc)
        logger.info("[DEV] Secret created: %s", path)

        return SecretMetadata(
            secret_path=path,
            provider="local_dev",
            field_names=list(payload.keys()),
            version="1",
            created_at=now,
            updated_at=now,
            rotation_count=0,
            tags=tags or {},
        )

    async def get_secret(self, path: str) -> Optional[SecretPayload]:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            return None

        data = self._decrypt_payload(doc["encrypted_payload"])
        return SecretPayload(
            data=data,
            version=doc.get("version", "1"),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
            rotation_count=doc.get("rotation_count", 0),
        )

    async def update_secret(
        self,
        path: str,
        payload: Dict[str, str],
    ) -> SecretMetadata:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            raise ValueError(f"Secret not found for update: {path}")

        now = datetime.now(timezone.utc).isoformat()
        await db[COLL_DEV_SECRETS].update_one(
            {"path": path},
            {"$set": {
                "encrypted_payload": self._encrypt_payload(payload),
                "field_names": list(payload.keys()),
                "updated_at": now,
            }},
        )
        logger.info("[DEV] Secret updated: %s", path)

        return SecretMetadata(
            secret_path=path,
            provider="local_dev",
            field_names=list(payload.keys()),
            version=doc.get("version", "1"),
            created_at=doc.get("created_at", ""),
            updated_at=now,
            rotation_count=doc.get("rotation_count", 0),
            tags=doc.get("tags", {}),
        )

    async def delete_secret(self, path: str) -> bool:
        db = self._get_db()
        result = await db[COLL_DEV_SECRETS].delete_one({"path": path})
        if result.deleted_count > 0:
            logger.info("[DEV] Secret deleted: %s", path)
            return True
        return False

    async def rotate_secret(
        self,
        path: str,
        new_payload: Dict[str, str],
    ) -> SecretMetadata:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            raise ValueError(f"Secret not found for rotation: {path}")

        now = datetime.now(timezone.utc).isoformat()
        new_count = doc.get("rotation_count", 0) + 1
        new_version = str(int(doc.get("version", "1")) + 1)

        await db[COLL_DEV_SECRETS].update_one(
            {"path": path},
            {"$set": {
                "encrypted_payload": self._encrypt_payload(new_payload),
                "field_names": list(new_payload.keys()),
                "version": new_version,
                "rotation_count": new_count,
                "updated_at": now,
            }},
        )
        logger.info("[DEV] Secret rotated: %s (v%s, #%d)", path, new_version, new_count)

        return SecretMetadata(
            secret_path=path,
            provider="local_dev",
            field_names=list(new_payload.keys()),
            version=new_version,
            created_at=doc.get("created_at", ""),
            updated_at=now,
            rotation_count=new_count,
            tags=doc.get("tags", {}),
        )

    async def get_secret_metadata(self, path: str) -> Optional[SecretMetadata]:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one(
            {"path": path},
            {"_id": 0, "encrypted_payload": 0},  # Never return payload
        )
        if not doc:
            return None

        return SecretMetadata(
            secret_path=path,
            provider="local_dev",
            field_names=doc.get("field_names", []),
            version=doc.get("version", "1"),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
            rotation_count=doc.get("rotation_count", 0),
            tags=doc.get("tags", {}),
        )

    async def health_check(self) -> Dict[str, Any]:
        try:
            db = self._get_db()
            await db[COLL_DEV_SECRETS].find_one({}, {"_id": 1})
            return {
                "provider": "local_dev",
                "status": "healthy",
                "mode": "NON-PRODUCTION",
            }
        except Exception as e:
            return {
                "provider": "local_dev",
                "status": "unhealthy",
                "error": str(e),
            }
