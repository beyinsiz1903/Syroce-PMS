"""
Channel Manager — Credential Encryption at Rest
Encrypts and decrypts OTA provider credentials stored in MongoDB.
"""
import base64
import hashlib
import logging
import os
import secrets

logger = logging.getLogger(__name__)

# Derive encryption key from environment or generate a deterministic one
_ENCRYPTION_KEY = os.environ.get("CM_ENCRYPTION_KEY", "")


def _get_key() -> bytes:
    """Get 32-byte encryption key."""
    if _ENCRYPTION_KEY:
        return hashlib.sha256(_ENCRYPTION_KEY.encode()).digest()
    # Fallback: derive from JWT_SECRET if available
    jwt_secret = os.environ.get("JWT_SECRET", "default-hotel-pms-secret")
    return hashlib.sha256(f"cm-cred:{jwt_secret}".encode()).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR-based encryption (lightweight, suitable for credential storage)."""
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string for storage."""
    if not plaintext:
        return ""
    key = _get_key()
    salt = secrets.token_bytes(16)
    derived = hashlib.sha256(key + salt).digest()
    encrypted = _xor_bytes(plaintext.encode("utf-8"), derived)
    # salt (16) + encrypted
    return base64.urlsafe_b64encode(salt + encrypted).decode("ascii")


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a stored credential string."""
    if not ciphertext:
        return ""
    try:
        raw = base64.urlsafe_b64decode(ciphertext)
        salt = raw[:16]
        encrypted = raw[16:]
        key = _get_key()
        derived = hashlib.sha256(key + salt).digest()
        return _xor_bytes(encrypted, derived).decode("utf-8")
    except Exception as e:
        logger.error(f"Credential decryption failed: {e}")
        return ""


def mask_credential(value: str, visible_chars: int = 4) -> str:
    """Mask a credential for display, showing only last N chars."""
    if not value or len(value) <= visible_chars:
        return "****"
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]
