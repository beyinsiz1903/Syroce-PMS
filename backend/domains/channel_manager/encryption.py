"""
Channel Manager — Credential Encryption at Rest (REFACTORED)

Delegates ALL encryption to core.crypto.CredentialEncryptionService.
This module is a thin backward-compatible wrapper.

Legacy callers that import encrypt_credential / decrypt_credential / mask_credential
continue to work without changes.
"""

import logging
import os

from core.crypto import AADContext, get_crypto_service, mask_value

logger = logging.getLogger(__name__)


def _build_aad() -> AADContext:
    """Build AAD context for channel manager credentials."""
    return AADContext(
        environment=os.environ.get("APP_ENV", "development"),
        context_type="credential",
    )


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string for storage."""
    if not plaintext:
        return ""
    svc = get_crypto_service()
    return svc.encrypt(plaintext, aad=_build_aad())


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a stored credential string. Raises on failure — never returns empty."""
    if not ciphertext:
        return ""
    svc = get_crypto_service()
    return svc.decrypt(ciphertext, aad=_build_aad())


def mask_credential(value: str, visible_chars: int = 4) -> str:
    """Mask a credential for display, showing only last N chars."""
    return mask_value(value, visible_suffix=visible_chars)
