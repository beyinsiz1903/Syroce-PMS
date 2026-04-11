"""
CredentialEncryptionService — the SINGLE encryption boundary.

ALL credential encryption/decryption in the platform MUST go through this service.
No other module should import cryptographic primitives directly.

Feature flags:
  CRYPTO_V2_ENABLED=false  — Phase 0: encrypt with legacy format, decrypt both
  CRYPTO_V2_ENABLED=true   — Full: encrypt with SYR1 envelope, decrypt both

Break-glass:
  CRYPTO_BYPASS_ALLOWED=true — EMERGENCY ONLY: disables all encryption
"""
import base64
import hashlib
import logging
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .engine import AADContext, AESGCMEngine
from .envelope import is_envelope
from .errors import CryptoError, DecryptionError
from .keys import load_keyring
from .masking import mask_dict, mask_value
from .migration import (
    AES_LEGACY_PREFIX,
    CiphertextFormat,
    LegacyDecryptor,
    detect_format,
)

logger = logging.getLogger("core.crypto.service")


class CredentialEncryptionService:
    """Unified credential encryption service.

    Lifecycle of a credential:
      1. create  — caller builds plaintext credentials
      2. encrypt — this service encrypts before persistence
      3. store   — caller writes encrypted value to DB
      4. access  — this service decrypts at controlled access point
      5. rotate  — re-encrypt with new key via this service
      6. revoke  — caller deletes from DB
    """

    def __init__(self):
        self._v2_enabled = (
            os.environ.get("CRYPTO_V2_ENABLED", "false").lower() == "true"
        )
        self._bypass = (
            os.environ.get("CRYPTO_BYPASS_ALLOWED", "false").lower() == "true"
        )
        self._keyring = load_keyring()
        self._engine = AESGCMEngine(self._keyring)
        self._legacy = LegacyDecryptor()

        # Legacy key for Phase 0 encryption (old aes256gcm: format)
        legacy_key_material = (
            os.environ.get("CM_CREDENTIAL_KEY", "")
            or "syroce-pms-default-key-change-in-production"
        )
        self._legacy_aes_key = hashlib.sha256(legacy_key_material.encode()).digest()

        if self._bypass:
            logger.critical(
                "CRYPTO_BYPASS_ALLOWED=true — ENCRYPTION IS DISABLED. "
                "This MUST only be used in break-glass emergencies."
            )
        logger.info(
            "CredentialEncryptionService initialized: v2=%s bypass=%s kid=%s",
            self._v2_enabled, self._bypass, self._keyring.current_kid,
        )

    # ── Core Encrypt/Decrypt ──────────────────────────────────────────

    def encrypt(self, plaintext: str, *, aad: AADContext | None = None) -> str:
        """Encrypt a single credential value.

        When CRYPTO_V2_ENABLED=true:  returns SYR1: envelope with HKDF key + AAD
        When CRYPTO_V2_ENABLED=false: returns aes256gcm: format (legacy compat)

        Raises CryptoError on failure — NEVER returns empty string.
        """
        if self._bypass:
            logger.warning("BYPASS: encryption skipped")
            return plaintext
        if not plaintext:
            raise CryptoError("Cannot encrypt empty value")

        if self._v2_enabled:
            return self._engine.encrypt(plaintext, aad=aad)
        else:
            return self._legacy_encrypt_aes(plaintext)

    def decrypt(self, ciphertext: str, *, aad: AADContext | None = None) -> str:
        """Decrypt any supported format. Auto-detects SYR1: and aes256gcm: prefixes.

        For non-prefixed formats (XOR, base64), use decrypt_legacy_xor or
        decrypt_legacy_base64 explicitly, or pass format_hint.

        Raises DecryptionError on failure — NEVER returns empty string.
        """
        if self._bypass:
            logger.warning("BYPASS: decryption skipped")
            return ciphertext
        if not ciphertext:
            raise DecryptionError("empty_ciphertext")

        fmt = detect_format(ciphertext)

        if fmt == CiphertextFormat.ENVELOPE_V1:
            return self._engine.decrypt(ciphertext, aad=aad)
        elif fmt == CiphertextFormat.AES_GCM_LEGACY:
            return self._legacy.decrypt(ciphertext, CiphertextFormat.AES_GCM_LEGACY)
        else:
            # Try auto-detection for non-prefixed legacy formats
            return self._legacy.decrypt_auto(ciphertext)

    def decrypt_legacy_xor(self, ciphertext: str) -> str:
        """Explicitly decrypt XOR legacy format."""
        if self._bypass:
            return ciphertext
        return self._legacy.decrypt(ciphertext, CiphertextFormat.XOR_LEGACY)

    def decrypt_legacy_base64(self, encoded: str) -> str:
        """Explicitly decode base64-only format."""
        if self._bypass:
            return encoded
        return self._legacy.decrypt(encoded, CiphertextFormat.BASE64_PLAIN)

    # ── Dict Operations ───────────────────────────────────────────────

    def encrypt_dict(
        self,
        credentials: dict[str, str],
        *,
        aad: AADContext | None = None,
    ) -> dict[str, str]:
        """Encrypt all non-empty string values in a dict."""
        encrypted = {}
        for k, v in credentials.items():
            if isinstance(v, str) and v:
                encrypted[k] = self.encrypt(v, aad=aad)
            else:
                encrypted[k] = v
        return encrypted

    def decrypt_dict(
        self,
        encrypted: dict[str, str],
        *,
        aad: AADContext | None = None,
    ) -> dict[str, str]:
        """Decrypt all encrypted values in a dict. Handles mixed formats."""
        decrypted = {}
        for k, v in encrypted.items():
            if isinstance(v, str) and v and self._looks_encrypted(v):
                decrypted[k] = self.decrypt(v, aad=aad)
            else:
                decrypted[k] = v
        return decrypted

    def decrypt_dict_xor(self, encrypted: dict[str, str]) -> dict[str, str]:
        """Decrypt all values assuming XOR legacy format."""
        return {
            k: self.decrypt_legacy_xor(v) if isinstance(v, str) and v else v
            for k, v in encrypted.items()
        }

    def decrypt_dict_base64(self, encrypted: dict[str, str]) -> dict[str, str]:
        """Decrypt all values assuming base64-only format."""
        return {
            k: self.decrypt_legacy_base64(v) if isinstance(v, str) and v else v
            for k, v in encrypted.items()
        }

    # ── Re-encryption (Rotation / Migration) ─────────────────────────

    def re_encrypt(
        self,
        ciphertext: str,
        *,
        aad: AADContext | None = None,
    ) -> str:
        """Decrypt any format, re-encrypt with current key + SYR1 envelope.

        Always produces the newest format regardless of CRYPTO_V2_ENABLED.
        Used by migration scripts and key rotation.
        """
        plaintext = self.decrypt(ciphertext, aad=aad)
        return self._engine.encrypt(plaintext, aad=aad)

    def re_encrypt_dict(
        self,
        encrypted: dict[str, str],
        *,
        aad: AADContext | None = None,
    ) -> dict[str, str]:
        """Re-encrypt all values in a dict to current format."""
        result = {}
        for k, v in encrypted.items():
            if isinstance(v, str) and v and self._looks_encrypted(v):
                result[k] = self.re_encrypt(v, aad=aad)
            else:
                result[k] = v
        return result

    # ── Format Detection ──────────────────────────────────────────────

    @staticmethod
    def is_current_format(value: str) -> bool:
        """Check if value is in the current SYR1 envelope format."""
        return is_envelope(value)

    @staticmethod
    def detect_format(value: str) -> CiphertextFormat:
        """Detect the encryption format of a value."""
        return detect_format(value)

    # ── Masking (delegation) ──────────────────────────────────────────

    @staticmethod
    def mask(value: str, visible_suffix: int = 4) -> str:
        """Mask a credential for display. NOT encryption."""
        return mask_value(value, visible_suffix=visible_suffix)

    @staticmethod
    def mask_credentials(credentials: dict[str, str]) -> dict[str, str]:
        """Mask all credential values for safe display."""
        return mask_dict(credentials)

    # ── Health ────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Return crypto subsystem health status."""
        return {
            "v2_enabled": self._v2_enabled,
            "bypass_active": self._bypass,
            "current_kid": self._keyring.current_kid,
            "has_previous_key": self._keyring.has_previous,
        }

    # ── Internal ──────────────────────────────────────────────────────

    def _legacy_encrypt_aes(self, plaintext: str) -> str:
        """Encrypt using old aes256gcm: format for Phase 0 backward compatibility."""
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(self._legacy_aes_key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        encoded = base64.b64encode(nonce + ct).decode("ascii")
        return f"{AES_LEGACY_PREFIX}{encoded}"

    @staticmethod
    def _looks_encrypted(value: str) -> bool:
        """Heuristic: does this look like encrypted data vs plain text?"""
        if value.startswith("SYR1:") or value.startswith("aes256gcm:"):
            return True
        # Base64-encoded data is typically longer and has restricted charset
        if len(value) > 20:
            b64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=-_")
            if all(c in b64_chars for c in value):
                return True
        return False


# ── Singleton ─────────────────────────────────────────────────────────

_instance: CredentialEncryptionService | None = None


def get_crypto_service() -> CredentialEncryptionService:
    """Get or create the singleton CredentialEncryptionService."""
    global _instance
    if _instance is None:
        _instance = CredentialEncryptionService()
    return _instance


def reset_crypto_service() -> None:
    """For testing only."""
    global _instance
    _instance = None
