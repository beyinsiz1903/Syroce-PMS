"""
HashiCorp Vault secrets backend — skeleton for future implementation.

This is an intentionally minimal placeholder. The interface is defined
so that adding Vault support requires only filling in the method bodies
with hvac client calls.

Do NOT overbuild this. Wait until Vault is actually needed.
"""
import logging
from typing import Any, Dict, Optional

from .provider import SecretsProviderBase, SecretPayload, SecretMetadata

logger = logging.getLogger("core.secrets.vault")


class VaultSecretsProvider(SecretsProviderBase):
    """
    HashiCorp Vault KV v2 backend — PLACEHOLDER.

    Future implementation should use the `hvac` library:
        pip install hvac
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        client.secrets.kv.v2.create_or_update_secret(...)
    """

    def __init__(self, vault_addr: str, vault_token: str):
        self._addr = vault_addr
        self._token = vault_token
        logger.info("VaultSecretsProvider initialized (PLACEHOLDER — not yet implemented)")

    async def create_secret(self, path, payload, tags=None) -> SecretMetadata:
        raise NotImplementedError("Vault backend not yet implemented. Use aws_secrets_manager or local_dev.")

    async def get_secret(self, path) -> Optional[SecretPayload]:
        raise NotImplementedError("Vault backend not yet implemented.")

    async def update_secret(self, path, payload) -> SecretMetadata:
        raise NotImplementedError("Vault backend not yet implemented.")

    async def delete_secret(self, path) -> bool:
        raise NotImplementedError("Vault backend not yet implemented.")

    async def rotate_secret(self, path, new_payload) -> SecretMetadata:
        raise NotImplementedError("Vault backend not yet implemented.")

    async def get_secret_metadata(self, path) -> Optional[SecretMetadata]:
        raise NotImplementedError("Vault backend not yet implemented.")

    async def health_check(self) -> Dict[str, Any]:
        return {
            "provider": "vault",
            "status": "not_implemented",
            "addr": self._addr,
            "message": "Vault backend is a placeholder. Not yet operational.",
        }
