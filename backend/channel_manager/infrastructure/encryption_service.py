"""
Encryption Service — Phase 3: Credential Security Hardening.

Replaces XOR encryption with AES-256-GCM:
  - Secure random 12-byte IV (nonce)
  - 16-byte authentication tag (tamper detection)
  - Key derived from environment variable via SHA-256
  - Migration path from legacy XOR-encrypted credentials
"""
import base64
import hashlib
import logging
import os
import secrets
from typing import Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("channel_manager.infrastructure.encryption")

_ENV_KEY = os.environ.get("CM_CREDENTIAL_KEY", "")
_LEGACY_KEY_RAW = os.environ.get("CM_CREDENTIAL_KEY", "")

# Magic prefix to distinguish AES-GCM ciphertext from legacy XOR
AES_PREFIX = "aes256gcm:"


class KeyManagementService:
    """Derives and manages encryption keys from environment secrets."""

    def __init__(self, raw_key: Optional[str] = None):
        source = raw_key or _ENV_KEY or "syroce-pms-default-key-change-in-production"
        self._key = hashlib.sha256(source.encode()).digest()  # 32 bytes

    @property
    def key(self) -> bytes:
        return self._key

    def rotate_key(self, new_raw_key: str) -> "KeyManagementService":
        return KeyManagementService(raw_key=new_raw_key)


class EncryptionService:
    """AES-256-GCM encryption/decryption with tamper detection."""

    def __init__(self, kms: Optional[KeyManagementService] = None):
        self._kms = kms or KeyManagementService()
        self._aesgcm = AESGCM(self._kms.key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string using AES-256-GCM. Returns base64 string prefixed with 'aes256gcm:'."""
        nonce = secrets.token_bytes(12)  # 96-bit nonce per NIST recommendation
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # ct includes 16-byte auth tag appended by AESGCM
        encoded = base64.b64encode(nonce + ct).decode("ascii")
        return f"{AES_PREFIX}{encoded}"

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an AES-256-GCM encrypted string. Raises on tamper."""
        if not ciphertext.startswith(AES_PREFIX):
            raise ValueError("Not an AES-256-GCM ciphertext — may be legacy format")
        raw = base64.b64decode(ciphertext[len(AES_PREFIX):])
        nonce = raw[:12]
        ct = raw[12:]
        plaintext = self._aesgcm.decrypt(nonce, ct, None)
        return plaintext.decode("utf-8")

    def encrypt_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Encrypt all credential values."""
        encrypted = {}
        for k, v in credentials.items():
            if isinstance(v, str) and v:
                encrypted[k] = self.encrypt(v)
            else:
                encrypted[k] = v
        return encrypted

    def decrypt_credentials(self, encrypted: Dict[str, str]) -> Dict[str, str]:
        """Decrypt all credential values, supporting both AES and legacy XOR."""
        decrypted = {}
        for k, v in encrypted.items():
            if isinstance(v, str) and v.startswith(AES_PREFIX):
                decrypted[k] = self.decrypt(v)
            elif isinstance(v, str) and v:
                # Try legacy XOR decryption
                decrypted[k] = self._legacy_decrypt(v)
            else:
                decrypted[k] = v
        return decrypted

    def migrate_credentials(self, encrypted: Dict[str, str]) -> Dict[str, str]:
        """Migrate legacy XOR-encrypted credentials to AES-256-GCM."""
        decrypted = self.decrypt_credentials(encrypted)
        return self.encrypt_credentials(decrypted)

    @staticmethod
    def is_aes_encrypted(value: str) -> bool:
        return isinstance(value, str) and value.startswith(AES_PREFIX)

    # ─── Legacy XOR Support ──────────────────────────────────────────

    def _legacy_decrypt(self, ciphertext: str) -> str:
        """Attempt legacy XOR decryption for migration purposes."""
        try:
            raw = base64.b64decode(ciphertext)
            nonce = raw[:16]
            cipher = raw[16:]
            key = self._kms.key + nonce
            plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(cipher))
            return plain.decode("utf-8")
        except Exception:
            return ciphertext  # Return as-is if decryption fails
