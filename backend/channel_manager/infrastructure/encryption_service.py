"""
Encryption Service — REFACTORED to delegate to core.crypto.

Backward-compatible wrapper. All callers that import EncryptionService
or KeyManagementService continue to work without changes.
"""
import logging
from typing import Dict, Optional

from core.crypto import get_crypto_service

logger = logging.getLogger("channel_manager.infrastructure.encryption")

# Keep prefix constant for format detection compatibility
AES_PREFIX = "aes256gcm:"


class KeyManagementService:
    """Backward-compatible wrapper — key management is now in core.crypto.keys."""

    def __init__(self, raw_key: Optional[str] = None):
        self._raw_key = raw_key

    @property
    def key(self) -> bytes:
        svc = get_crypto_service()
        _, key = svc._keyring.encryption_key()
        return key

    def rotate_key(self, new_raw_key: str) -> "KeyManagementService":
        return KeyManagementService(raw_key=new_raw_key)


class EncryptionService:
    """AES-256-GCM encryption — delegates to core.crypto.CredentialEncryptionService."""

    def __init__(self, kms: Optional[KeyManagementService] = None):
        self._svc = get_crypto_service()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns encrypted string."""
        if not plaintext:
            return ""
        return self._svc.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string. Supports all formats via core.crypto."""
        if not ciphertext:
            return ""
        return self._svc.decrypt(ciphertext)

    def encrypt_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Encrypt all credential values."""
        return self._svc.encrypt_dict(credentials)

    def decrypt_credentials(self, encrypted: Dict[str, str]) -> Dict[str, str]:
        """Decrypt all credential values (supports all legacy formats)."""
        return self._svc.decrypt_dict(encrypted)

    def migrate_credentials(self, encrypted: Dict[str, str]) -> Dict[str, str]:
        """Re-encrypt credentials to current format."""
        return self._svc.re_encrypt_dict(encrypted)

    @staticmethod
    def is_aes_encrypted(value: str) -> bool:
        return isinstance(value, str) and (
            value.startswith(AES_PREFIX) or value.startswith("SYR1:")
        )
