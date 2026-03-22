"""
Legacy format detection, decryption, and classification.

Supported legacy formats:
  1. "SYR1:<base64(json)>"            — current versioned envelope (NOT legacy)
  2. "aes256gcm:<base64(nonce+ct)>"   — old AES-GCM, SHA-256 key, no AAD
  3. base64url(salt[16] + xor_data)   — old XOR obfuscation
  4. base64(plaintext)                — base64-only "encryption"

Each legacy format uses its own key derivation and must be decrypted
with the original key material before re-encryption with the new system.
"""
import base64
import hashlib
import logging
import os
from enum import Enum

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import DecryptionError, LegacyFormatError

logger = logging.getLogger("core.crypto.migration")

AES_LEGACY_PREFIX = "aes256gcm:"
ENVELOPE_PREFIX = "SYR1:"


class CiphertextFormat(Enum):
    """All known ciphertext formats in the system."""
    ENVELOPE_V1 = "envelope_v1"
    AES_GCM_LEGACY = "aes_gcm_legacy"
    XOR_LEGACY = "xor_legacy"
    BASE64_PLAIN = "base64_plain"
    PLAINTEXT = "plaintext"
    UNKNOWN = "unknown"


def detect_format(ciphertext: str) -> CiphertextFormat:
    """Detect the encryption format of a ciphertext string.

    Prefixed formats (SYR1:, aes256gcm:) are detected definitively.
    Unprefixed formats require contextual hints for reliable classification.
    """
    if not ciphertext or not isinstance(ciphertext, str):
        return CiphertextFormat.UNKNOWN
    if ciphertext.startswith(ENVELOPE_PREFIX):
        return CiphertextFormat.ENVELOPE_V1
    if ciphertext.startswith(AES_LEGACY_PREFIX):
        return CiphertextFormat.AES_GCM_LEGACY
    # Non-prefixed: could be XOR, base64-plain, or actual plaintext
    # Return UNKNOWN — callers should use explicit methods
    return CiphertextFormat.UNKNOWN


class LegacyDecryptor:
    """Decrypts all historical encryption formats.

    Reads legacy key materials from environment for backward compatibility.
    This class should be removed after all data is migrated to SYR1 format.
    """

    def __init__(self):
        self._cm_credential_key = os.environ.get("CM_CREDENTIAL_KEY", "")
        self._cm_encryption_key = os.environ.get("CM_ENCRYPTION_KEY", "")
        self._jwt_secret = os.environ.get("JWT_SECRET", "")

    def decrypt(self, ciphertext: str, fmt: CiphertextFormat) -> str:
        """Decrypt a legacy-format ciphertext. Raises on failure — never returns empty."""
        if fmt == CiphertextFormat.AES_GCM_LEGACY:
            return self._decrypt_aes_gcm_legacy(ciphertext)
        elif fmt == CiphertextFormat.XOR_LEGACY:
            return self._decrypt_xor_legacy(ciphertext)
        elif fmt == CiphertextFormat.BASE64_PLAIN:
            return self._decrypt_base64_plain(ciphertext)
        else:
            raise LegacyFormatError(fmt.value)

    def decrypt_auto(self, ciphertext: str) -> str:
        """Try all legacy formats in order. First success wins.

        Order: AES-GCM (prefixed) → XOR → Base64
        """
        fmt = detect_format(ciphertext)
        if fmt == CiphertextFormat.AES_GCM_LEGACY:
            return self._decrypt_aes_gcm_legacy(ciphertext)

        # Try XOR first (more structured format)
        try:
            result = self._decrypt_xor_legacy(ciphertext)
            if result and self._looks_like_valid_text(result):
                return result
        except (DecryptionError, Exception):
            pass

        # Try base64 plain
        try:
            result = self._decrypt_base64_plain(ciphertext)
            if result and self._looks_like_valid_text(result):
                return result
        except (DecryptionError, Exception):
            pass

        raise DecryptionError("all_legacy_formats_failed")

    def _decrypt_aes_gcm_legacy(self, ciphertext: str) -> str:
        """Decrypt old 'aes256gcm:' format — SHA-256 key derivation, no AAD."""
        if not ciphertext.startswith(AES_LEGACY_PREFIX):
            raise DecryptionError("not_aes_gcm_legacy_prefix")

        key_material = (
            self._cm_credential_key
            or "syroce-pms-default-key-change-in-production"
        )
        key = hashlib.sha256(key_material.encode()).digest()

        try:
            raw = base64.b64decode(ciphertext[len(AES_LEGACY_PREFIX):])
            nonce = raw[:12]
            ct = raw[12:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ct, None)
            return plaintext.decode("utf-8")
        except Exception:
            raise DecryptionError("aes_gcm_legacy_decryption_failed")

    def _decrypt_xor_legacy(self, ciphertext: str) -> str:
        """Decrypt old XOR obfuscation — SHA-256(key+salt) XOR."""
        key_material = self._cm_encryption_key
        if key_material:
            key = hashlib.sha256(key_material.encode()).digest()
        else:
            jwt = self._jwt_secret or "default-hotel-pms-secret"
            key = hashlib.sha256(f"cm-cred:{jwt}".encode()).digest()

        try:
            raw = base64.urlsafe_b64decode(ciphertext)
            if len(raw) <= 16:
                raise DecryptionError("xor_payload_too_short")
            salt = raw[:16]
            encrypted = raw[16:]
            derived = hashlib.sha256(key + salt).digest()
            plain = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(encrypted))
            return plain.decode("utf-8")
        except DecryptionError:
            raise
        except Exception:
            raise DecryptionError("xor_legacy_decryption_failed")

    def _decrypt_base64_plain(self, ciphertext: str) -> str:
        """Decode base64-only 'encryption' — no real crypto, just encoding."""
        try:
            return base64.b64decode(ciphertext.encode()).decode("utf-8")
        except Exception:
            raise DecryptionError("base64_decode_failed")

    @staticmethod
    def _looks_like_valid_text(text: str) -> bool:
        """Heuristic: does the decrypted text look like valid credential data?"""
        if not text:
            return False
        # Check if most characters are printable ASCII
        printable_count = sum(1 for c in text if 32 <= ord(c) <= 126)
        return printable_count / len(text) > 0.8
