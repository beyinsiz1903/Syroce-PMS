"""
Unified Secrets Manager — the single entry point for all secret operations.

Responsibilities:
  - Provider resolution based on SECRETS_PROVIDER config
  - Tenant/provider/property-aware secret CRUD via SecretIdentity naming
  - Dual-read during migration: new backend first, legacy fallback if allowed
  - Access audit logging on every operation
  - Credential masking utility
  - Startup validation

Usage:
    from core.secrets import get_secrets_manager

    sm = get_secrets_manager()
    await sm.store_provider_credentials(tenant_id, "exely", property_id, creds)
    creds = await sm.get_provider_credentials(tenant_id, "exely", property_id)
"""

import logging
from typing import Any

from .audit import SecretAuditLogger
from .config import SecretsConfig, get_secrets_config
from .naming import SecretIdentity
from .provider import SecretMetadata, SecretsProviderBase

logger = logging.getLogger("core.secrets.manager")


def _build_provider(config: SecretsConfig) -> SecretsProviderBase:
    """Instantiate the correct backend based on config."""
    if config.provider == "aws_secrets_manager":
        from .aws_provider import AWSSecretsProvider

        return AWSSecretsProvider(region=config.aws_region)
    elif config.provider == "vault":
        import os

        from .vault_provider import VaultSecretsProvider

        return VaultSecretsProvider(
            vault_addr=os.environ.get("VAULT_ADDR", ""),
            vault_token=os.environ.get("VAULT_TOKEN", ""),
        )
    elif config.provider in ("local_dev", "env"):
        from .local_provider import LocalDevSecretsProvider

        return LocalDevSecretsProvider(encryption_key=config.encryption_key)
    else:
        raise RuntimeError(f"Unknown secrets provider: {config.provider}")


class SecretsManager:
    """
    Unified secrets manager.

    Provides high-level tenant-aware secret operations backed by
    a configurable provider (AWS, local_dev, Vault).
    """

    def __init__(self, config: SecretsConfig):
        self._config = config
        self._provider = _build_provider(config)
        self._audit = SecretAuditLogger(enabled=config.audit_enabled)

    def _identity(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
    ) -> SecretIdentity:
        return SecretIdentity(
            prefix=self._config.aws_secret_prefix,
            environment=self._config.app_env,
            tenant_id=tenant_id,
            provider=provider,
            property_id=property_id,
        )

    # ── High-level Provider Credential API ────────────────────────────

    async def store_provider_credentials(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        credentials: dict[str, str],
        actor: str = "system",
    ) -> str:
        """
        Store provider credentials. Creates or updates.
        Returns the secret path.
        """
        identity = self._identity(tenant_id, provider, property_id)
        path = identity.path

        try:
            existing = await self._provider.get_secret(path)
            if existing:
                await self._provider.update_secret(path, credentials)
                action = "update"
            else:
                await self._provider.create_secret(
                    path,
                    credentials,
                    tags=identity.to_metadata(),
                )
                action = "create"

            await self._audit.log(
                action=action,
                secret_path=path,
                result="success",
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                actor=actor,
                metadata={"field_names": list(credentials.keys())},
            )
            return path

        except Exception as e:
            await self._audit.log(
                action="create",
                secret_path=path,
                result="failure",
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                actor=actor,
                error_class=type(e).__name__,
            )
            raise

    async def get_provider_credentials(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        actor: str = "system",
    ) -> dict[str, str] | None:
        """
        Retrieve decrypted provider credentials.
        Supports dual-read: tries new backend first, falls back to legacy if enabled.
        """
        identity = self._identity(tenant_id, provider, property_id)
        path = identity.path

        # Try primary backend
        payload = await self._provider.get_secret(path)
        if payload:
            await self._audit.log(
                action="read",
                secret_path=path,
                result="success",
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                actor=actor,
            )
            return payload.data

        # Legacy fallback during migration
        if self._config.enable_legacy_fallback:
            legacy_creds = await self._read_legacy_credentials(
                tenant_id,
                provider,
                property_id,
            )
            if legacy_creds:
                await self._audit.log(
                    action="read",
                    secret_path=path,
                    result="success",
                    tenant_id=tenant_id,
                    provider=provider,
                    property_id=property_id,
                    actor=actor,
                    metadata={"source": "legacy_fallback"},
                )
                return legacy_creds

        await self._audit.log(
            action="read",
            secret_path=path,
            result="not_found",
            tenant_id=tenant_id,
            provider=provider,
            property_id=property_id,
            actor=actor,
        )
        return None

    async def delete_provider_credentials(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        actor: str = "system",
    ) -> bool:
        identity = self._identity(tenant_id, provider, property_id)
        path = identity.path

        deleted = await self._provider.delete_secret(path)
        await self._audit.log(
            action="delete",
            secret_path=path,
            result="success" if deleted else "not_found",
            tenant_id=tenant_id,
            provider=provider,
            property_id=property_id,
            actor=actor,
        )
        return deleted

    async def rotate_provider_credentials(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        new_credentials: dict[str, str],
        actor: str = "system",
    ) -> SecretMetadata:
        identity = self._identity(tenant_id, provider, property_id)
        path = identity.path

        try:
            meta = await self._provider.rotate_secret(path, new_credentials)
            await self._audit.log(
                action="rotate",
                secret_path=path,
                result="success",
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                actor=actor,
                metadata={
                    "field_names": list(new_credentials.keys()),
                    "rotation_count": meta.rotation_count,
                },
            )
            return meta
        except Exception as e:
            await self._audit.log(
                action="rotate",
                secret_path=path,
                result="failure",
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                actor=actor,
                error_class=type(e).__name__,
            )
            raise

    async def get_provider_credential_metadata(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
    ) -> SecretMetadata | None:
        identity = self._identity(tenant_id, provider, property_id)
        return await self._provider.get_secret_metadata(identity.path)

    # ── Webhook Signing Secrets ──────────────────────────────────────
    # Per-property inbound webhook signing secrets are stored under a
    # dedicated "<provider>_webhook" namespace so rotating the webhook secret
    # never touches the API credentials (and vice-versa). The value is
    # encrypted at rest exactly like provider credentials and is never written
    # to the connection document.

    async def store_webhook_secret(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        secret: str,
        actor: str = "system",
    ) -> str:
        """Create or overwrite a per-property webhook signing secret."""
        return await self.store_provider_credentials(
            tenant_id=tenant_id,
            provider=f"{provider}_webhook",
            property_id=property_id,
            credentials={"webhook_secret": secret},
            actor=actor,
        )

    async def get_webhook_secret(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
        actor: str = "system",
    ) -> str | None:
        """Retrieve the decrypted per-property webhook signing secret."""
        creds = await self.get_provider_credentials(
            tenant_id=tenant_id,
            provider=f"{provider}_webhook",
            property_id=property_id,
            actor=actor,
        )
        if not creds:
            return None
        return creds.get("webhook_secret")

    # ── Masking ──────────────────────────────────────────────────────

    @staticmethod
    def mask_credentials(credentials: dict[str, str]) -> dict[str, str]:
        """Mask credential values for safe display."""
        masked = {}
        for k, v in credentials.items():
            sv = str(v)
            if len(sv) > 6:
                masked[k] = sv[:3] + "*" * (len(sv) - 6) + sv[-3:]
            else:
                masked[k] = "****"
        return masked

    # ── Legacy Fallback ──────────────────────────────────────────────

    async def _read_legacy_credentials(
        self,
        tenant_id: str,
        provider: str,
        property_id: str,
    ) -> dict[str, str] | None:
        """
        Read from legacy provider_secrets collection (XOR/AES encrypted).
        Only used during migration window.
        """
        try:
            from domains.channel_manager.credential_vault import get_decrypted_credentials

            creds = await get_decrypted_credentials(tenant_id, provider, property_id)
            if creds:
                logger.info(
                    "Legacy fallback used for %s/%s/%s — consider migrating",
                    tenant_id,
                    provider,
                    property_id,
                )
            return creds
        except Exception:
            logger.debug(
                "Legacy fallback failed for %s/%s/%s",
                tenant_id,
                provider,
                property_id,
            )
            return None

    async def _read_legacy_connection_credentials(
        self,
        tenant_id: str,
        provider: str,
    ) -> dict[str, str] | None:
        """
        Read raw credentials from connection documents (HotelRunner pattern).
        Only used during migration window.
        """
        try:
            from core.database import db

            if provider == "hotelrunner":
                conn = await db.hotelrunner_connections.find_one(
                    {"tenant_id": tenant_id, "is_active": True},
                    {"_id": 0, "token": 1, "hr_id": 1},
                )
                if conn and conn.get("token"):
                    return {"token": conn["token"], "hr_id": conn.get("hr_id", "")}
            return None
        except Exception:
            return None

    # ── Health / Status ──────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        provider_health = await self._provider.health_check()
        return {
            **provider_health,
            "legacy_fallback_enabled": self._config.enable_legacy_fallback,
            "audit_enabled": self._config.audit_enabled,
        }

    async def ensure_indexes(self) -> None:
        await self._audit.ensure_indexes()


# ── Singleton ────────────────────────────────────────────────────────

_instance: SecretsManager | None = None


def get_secrets_manager() -> SecretsManager:
    """Get or create the singleton SecretsManager."""
    global _instance
    if _instance is None:
        config = get_secrets_config()
        _instance = SecretsManager(config)
    return _instance


def reset_secrets_manager() -> None:
    """For testing only."""
    global _instance
    _instance = None
