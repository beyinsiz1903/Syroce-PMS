"""
AES-256-GCM encryption engine with AAD context binding and envelope wrapping.

This module performs the actual cryptographic operations. It should only be
called through CredentialEncryptionService (core/crypto/service.py).

Security properties:
  - AES-256-GCM: authenticated encryption with associated data (AEAD)
  - 96-bit random nonce per encryption (NIST SP 800-38D)
  - AAD binds ciphertext to tenant/provider/property/env context
  - GCM tag (128-bit) detects any tampering or context mismatch
"""
import logging
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .envelope import EncryptionEnvelope
from .errors import DecryptionError, KeyNotFoundError, TamperDetectedError
from .keys import KeyRing

logger = logging.getLogger("core.crypto.engine")

NONCE_SIZE = 12  # 96-bit per NIST SP 800-38D


@dataclass(frozen=True)
class AADContext:
    """Associated Authenticated Data for context binding.

    All fields MUST be deterministic and reconstructible at decrypt time.
    NEVER include: timestamps, random values, mutable fields.

    Format: tenant_id|provider|property_id|environment|context_type
    """
    tenant_id: str = ""
    provider: str = ""
    property_id: str = ""
    environment: str = ""
    context_type: str = "credential"

    def to_bytes(self) -> bytes:
        """Deterministic AAD byte representation."""
        return (
            f"{self.tenant_id}|{self.provider}|{self.property_id}"
            f"|{self.environment}|{self.context_type}"
        ).encode()


class AESGCMEngine:
    """Core AES-256-GCM encryption engine with envelope wrapping."""

    def __init__(self, keyring: KeyRing):
        self._keyring = keyring

    def encrypt(self, plaintext: str, *, aad: AADContext | None = None) -> str:
        """Encrypt plaintext → SYR1: envelope string.

        Args:
            plaintext: The secret value to encrypt.
            aad: Optional context binding (tenant, provider, etc.).

        Returns:
            Serialized SYR1: envelope string.
        """
        kid, key = self._keyring.encryption_key()
        nonce = secrets.token_bytes(NONCE_SIZE)
        aad_bytes = aad.to_bytes() if aad else None

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad_bytes)

        envelope = EncryptionEnvelope.create(
            kid=kid,
            nonce=nonce,
            ciphertext=ciphertext,
            aad=aad_bytes,
        )
        return envelope.serialize()

    def decrypt(self, envelope_str: str, *, aad: AADContext | None = None) -> str:
        """Decrypt a SYR1: envelope string → plaintext.

        Args:
            envelope_str: Serialized SYR1: envelope.
            aad: Must match the AAD used during encryption.

        Returns:
            Decrypted plaintext string.

        Raises:
            TamperDetectedError: GCM tag mismatch (wrong key, wrong AAD, or tampered).
            KeyNotFoundError: Key ID not in keyring.
            DecryptionError: Any other decryption failure.
        """
        envelope = EncryptionEnvelope.deserialize(envelope_str)
        aad_bytes = aad.to_bytes() if aad else None

        try:
            key = self._keyring.decryption_key(envelope.kid)
        except KeyNotFoundError:
            raise

        aesgcm = AESGCM(key)
        try:
            plaintext_bytes = aesgcm.decrypt(
                envelope.nonce, envelope.ciphertext, aad_bytes,
            )
        except InvalidTag:
            raise TamperDetectedError(kid=envelope.kid)
        except Exception:
            raise DecryptionError("aes_gcm_failure", kid=envelope.kid)

        return plaintext_bytes.decode("utf-8")
