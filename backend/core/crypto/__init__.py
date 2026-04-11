"""
core.crypto — Production-grade credential encryption.

Public API:
  get_crypto_service()     → CredentialEncryptionService singleton
  AADContext(...)           → Context binding for AEAD
  mask_value(v)            → Display masking
  mask_dict(d)             → Dict display masking
  CiphertextFormat         → Format detection enum
  detect_format(v)         → Detect ciphertext format

Exceptions:
  CryptoError              → Base
  DecryptionError          → Decryption failure
  TamperDetectedError      → GCM tag mismatch
  KeyNotFoundError         → Missing key
  LegacyFormatError        → Legacy format
  EnvelopeParseError       → Bad envelope

Usage:
  from core.crypto import get_crypto_service, AADContext

  svc = get_crypto_service()
  encrypted = svc.encrypt("secret", aad=AADContext(tenant_id="t1", provider="exely"))
  decrypted = svc.decrypt(encrypted, aad=AADContext(tenant_id="t1", provider="exely"))
"""
from .engine import AADContext
from .errors import (
    CryptoError,
    DecryptionError,
    EnvelopeParseError,
    KeyDerivationError,
    KeyNotFoundError,
    LegacyFormatError,
    TamperDetectedError,
)
from .masking import mask_dict, mask_value
from .migration import CiphertextFormat, detect_format
from .service import CredentialEncryptionService, get_crypto_service, reset_crypto_service

__all__ = [
    "CredentialEncryptionService",
    "get_crypto_service",
    "reset_crypto_service",
    "AADContext",
    "mask_value",
    "mask_dict",
    "CryptoError",
    "DecryptionError",
    "TamperDetectedError",
    "KeyNotFoundError",
    "KeyDerivationError",
    "LegacyFormatError",
    "EnvelopeParseError",
    "CiphertextFormat",
    "detect_format",
]
