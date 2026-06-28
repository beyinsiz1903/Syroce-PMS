"""
MongoDB-backed secrets store.

Stores secrets in MongoDB collection `_dev_secrets` with AES-256-GCM encryption
via core.crypto.CredentialEncryptionService.

Usable in two modes:
  - Development (default): SECRETS_PROVIDER=local_dev, APP_ENV != production.
  - Production-approved: SECRETS_PROVIDER=env (encrypted-at-rest store for
    deployments without AWS Secrets Manager / Vault). The master key
    (CM_MASTER_KEY_CURRENT) is required and validated at startup.

SECRETS_PROVIDER=local_dev remains forbidden in production by
SecretsConfig.validate().
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from core.crypto import AADContext, get_crypto_service

from .provider import SecretMetadata, SecretPayload, SecretsProviderBase

logger = logging.getLogger("core.secrets.local_dev")

COLL_DEV_SECRETS = "_dev_secrets"
_NO_ID = {"_id": 0}


class LocalDevSecretsProvider(SecretsProviderBase):
    """
    MongoDB-backed development secrets store with AES-256-GCM encryption at rest.

    Delegates all encryption to core.crypto.CredentialEncryptionService.
    Approved for production only via SECRETS_PROVIDER=env (deployments without
    AWS Secrets Manager / Vault). SECRETS_PROVIDER=local_dev is gated to
    non-production by SecretsConfig.validate() at startup.
    """

    def __init__(self, encryption_key: str = ""):
        # encryption_key parameter kept for backward compat but ignored —
        # all encryption now handled by core.crypto
        self._svc = get_crypto_service()

        app_env = os.environ.get("APP_ENV", "development")
        provider = os.environ.get("SECRETS_PROVIDER", "local_dev")
        is_production = app_env in ("production", "staging")

        if is_production and provider == "env":
            # Sanctioned production mode: MongoDB-backed store with
            # AES-256-GCM encryption at rest via core.crypto. The master key
            # (CM_MASTER_KEY_CURRENT) is required and validated at startup by
            # core.crypto.load_keyring, so reaching this point means it is set.
            logger.info(
                "Secrets backend active: MongoDB-encrypted store (SECRETS_PROVIDER=env, APP_ENV=%s). Credentials encrypted at rest via core.crypto.",
                app_env,
            )
        elif is_production:
            # Reached production with a non-'env' local backend. This should
            # have been blocked by SecretsConfig.validate(); warn loudly in
            # case that guard is ever bypassed.
            logger.warning(
                "LocalDevSecretsProvider initialized in production with SECRETS_PROVIDER=%s — THIS IS NOT A PRODUCTION-APPROVED MODE",
                provider,
            )
        else:
            logger.info(
                "Secrets backend active: MongoDB-encrypted store (development mode, APP_ENV=%s).",
                app_env,
            )

    def _get_db(self):
        # Use raw db (not TenantAwareDBProxy) — `_dev_secrets` is a system
        # collection and must not be auto-scoped by tenant context.
        from core.database import _raw_db

        return _raw_db

    def _build_aad(self, path: str) -> AADContext:
        """Build AAD from secret path for context binding."""
        parts = path.split("/")
        return AADContext(
            tenant_id=parts[3] if len(parts) > 3 else "",
            provider=parts[4] if len(parts) > 4 else "",
            property_id=parts[5] if len(parts) > 5 else "",
            environment=os.environ.get("APP_ENV", "development"),
            context_type="secret",
        )

    def _encrypt_payload(self, data: dict[str, str], path: str) -> str:
        """Encrypt the entire payload as a single JSON blob."""
        plaintext = json.dumps(data)
        aad = self._build_aad(path)
        return self._svc.encrypt(plaintext, aad=aad)

    def _decrypt_payload(self, encrypted: str, path: str) -> dict[str, str]:
        """Decrypt a JSON blob back to dict."""
        aad = self._build_aad(path)
        plaintext = self._svc.decrypt(encrypted, aad=aad)
        return json.loads(plaintext)

    async def create_secret(
        self,
        path: str,
        payload: dict[str, str],
        tags: dict[str, str] | None = None,
    ) -> SecretMetadata:
        db = self._get_db()
        existing = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if existing:
            raise ValueError(f"Secret already exists: {path}")

        now = datetime.now(UTC).isoformat()
        doc = {
            "path": path,
            "encrypted_payload": self._encrypt_payload(payload, path),
            "field_names": list(payload.keys()),
            "version": "1",
            "key_version": self._svc._keyring.current_kid,
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

    async def get_secret(self, path: str) -> SecretPayload | None:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            return None

        data = self._decrypt_payload(doc["encrypted_payload"], path)
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
        payload: dict[str, str],
    ) -> SecretMetadata:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            raise ValueError(f"Secret not found for update: {path}")

        now = datetime.now(UTC).isoformat()
        await db[COLL_DEV_SECRETS].update_one(
            {"path": path},
            {
                "$set": {
                    "encrypted_payload": self._encrypt_payload(payload, path),
                    "field_names": list(payload.keys()),
                    "key_version": self._svc._keyring.current_kid,
                    "updated_at": now,
                }
            },
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
        new_payload: dict[str, str],
    ) -> SecretMetadata:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one({"path": path}, _NO_ID)
        if not doc:
            raise ValueError(f"Secret not found for rotation: {path}")

        now = datetime.now(UTC).isoformat()
        new_count = doc.get("rotation_count", 0) + 1
        new_version = str(int(doc.get("version", "1")) + 1)

        await db[COLL_DEV_SECRETS].update_one(
            {"path": path},
            {
                "$set": {
                    "encrypted_payload": self._encrypt_payload(new_payload, path),
                    "field_names": list(new_payload.keys()),
                    "version": new_version,
                    "key_version": self._svc._keyring.current_kid,
                    "rotation_count": new_count,
                    "updated_at": now,
                }
            },
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

    async def get_secret_metadata(self, path: str) -> SecretMetadata | None:
        db = self._get_db()
        doc = await db[COLL_DEV_SECRETS].find_one(
            {"path": path},
            {"_id": 0, "encrypted_payload": 0},
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

    async def health_check(self) -> dict[str, Any]:
        try:
            db = self._get_db()
            await db[COLL_DEV_SECRETS].find_one({}, {"_id": 1})
            return {
                "provider": "local_dev",
                "status": "healthy",
                "mode": "NON-PRODUCTION",
                "crypto": self._svc.health(),
            }
        except Exception as e:
            return {
                "provider": "local_dev",
                "status": "unhealthy",
                "error": str(e),
            }
