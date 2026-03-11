"""
Credential Vault - AES-256-GCM encryption at rest for connector credentials.

Features:
  - AES-256-GCM encryption with secure random IV and auth tag (tamper detection)
  - Legacy XOR migration support
  - Secret rotation support
  - Masked display for UI
  - Audit trail for all credential operations
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository
from ..infrastructure.encryption_service import EncryptionService

logger = logging.getLogger("channel_manager.infrastructure.credential_vault")


class CredentialVault:
    """Manages AES-256-GCM encrypted credential storage with audit trail."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()
        self._encryption = EncryptionService()

    def encrypt_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Encrypt credential values using AES-256-GCM."""
        return self._encryption.encrypt_credentials(credentials)

    def decrypt_credentials(self, encrypted: Dict[str, str]) -> Dict[str, str]:
        """Decrypt credential values (supports both AES-GCM and legacy XOR)."""
        return self._encryption.decrypt_credentials(encrypted)

    @staticmethod
    def mask_credentials(credentials: Dict[str, Any]) -> Dict[str, str]:
        """Mask credential values for UI display."""
        masked = {}
        for k, v in credentials.items():
            if isinstance(v, str) and len(v) > 4:
                masked[k] = v[:4] + "*" * (len(v) - 4)
            elif isinstance(v, str):
                masked[k] = "****"
            else:
                masked[k] = "****"
        return masked

    async def store_credentials(
        self,
        tenant_id: str,
        connector_id: str,
        credentials: Dict[str, str],
        actor_id: Optional[str] = None,
        is_rotation: bool = False,
    ) -> None:
        """Encrypt and store credentials using AES-256-GCM."""
        encrypted = self.encrypt_credentials(credentials)

        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")

        connector["credentials"] = encrypted
        connector["credentials_encrypted"] = True
        connector["encryption_algorithm"] = "AES-256-GCM"
        connector["credentials_updated_at"] = datetime.now(timezone.utc).isoformat()
        if is_rotation:
            connector["credentials_rotated_at"] = datetime.now(timezone.utc).isoformat()
        await self._repo.upsert_connector(connector)

        action = AuditAction.CREDENTIAL_ROTATED if is_rotation else AuditAction.CREDENTIAL_CHANGED
        await self._audit(
            tenant_id, connector.get("property_id", ""), connector_id,
            action, actor_id,
            {"keys_updated": list(credentials.keys()), "encrypted": True, "algorithm": "AES-256-GCM"},
        )

    async def retrieve_credentials(
        self, tenant_id: str, connector_id: str,
    ) -> Dict[str, str]:
        """Retrieve and decrypt credentials for a connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")
        creds = connector.get("credentials", {})
        if connector.get("credentials_encrypted"):
            return self.decrypt_credentials(creds)
        return creds

    async def rotate_credentials(
        self,
        tenant_id: str,
        connector_id: str,
        new_credentials: Dict[str, str],
        actor_id: Optional[str] = None,
    ) -> None:
        """Rotate credentials with audit trail."""
        await self.store_credentials(
            tenant_id, connector_id, new_credentials,
            actor_id=actor_id, is_rotation=True,
        )

    async def migrate_legacy_credentials(
        self,
        tenant_id: str,
        connector_id: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Migrate XOR-encrypted credentials to AES-256-GCM."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")

        creds = connector.get("credentials", {})
        if not creds:
            return {"migrated": False, "reason": "No credentials found"}

        already_aes = all(
            self._encryption.is_aes_encrypted(v)
            for v in creds.values()
            if isinstance(v, str) and v
        )
        if already_aes:
            return {"migrated": False, "reason": "Already AES-256-GCM encrypted"}

        migrated = self._encryption.migrate_credentials(creds)
        connector["credentials"] = migrated
        connector["credentials_encrypted"] = True
        connector["encryption_algorithm"] = "AES-256-GCM"
        connector["credentials_updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._repo.upsert_connector(connector)

        await self._audit(
            tenant_id, connector.get("property_id", ""), connector_id,
            AuditAction.CREDENTIAL_CHANGED, actor_id,
            {"migration": "XOR->AES-256-GCM", "keys_migrated": list(creds.keys())},
        )

        return {"migrated": True, "keys_migrated": list(creds.keys()), "algorithm": "AES-256-GCM"}

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
