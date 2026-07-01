"""
Typed cryptographic exceptions.

Designed to provide actionable error classification without leaking
any secret material in messages, tracebacks, or logs.

Hierarchy:
  CryptoError
  ├── DecryptionError
  │   └── TamperDetectedError
  ├── KeyNotFoundError
  ├── KeyDerivationError
  ├── LegacyFormatError
  └── EnvelopeParseError
"""


class CryptoError(Exception):
    """Base class for all cryptographic errors."""


class DecryptionError(CryptoError):
    """Decryption failed — wrong key, tampered data, or malformed payload."""

    def __init__(self, reason: str = "decryption_failed", *, kid: str = ""):
        self.reason = reason
        self.kid = kid
        super().__init__(f"Decryption failed: {reason}")


class TamperDetectedError(DecryptionError):
    """GCM authentication tag mismatch — data tampered or wrong AAD."""

    def __init__(self, *, kid: str = ""):
        super().__init__(reason="gcm_tag_mismatch", kid=kid)


class KeyNotFoundError(CryptoError):
    """Key ID referenced in ciphertext is not available in the keyring."""

    def __init__(self, kid: str):
        self.kid = kid
        super().__init__(f"Key not found: kid={kid}")


class KeyDerivationError(CryptoError):
    """Key derivation failed — invalid or missing master key."""

    def __init__(self, reason: str = "derivation_failed"):
        self.reason = reason
        super().__init__(f"Key derivation error: {reason}")


class LegacyFormatError(CryptoError):
    """Legacy ciphertext format detected, migration needed or legacy support disabled."""

    def __init__(self, format_type: str = "unknown"):
        self.format_type = format_type
        super().__init__(f"Legacy format: {format_type}")


class EnvelopeParseError(CryptoError):
    """Encryption envelope structure is malformed or unsupported."""

    def __init__(self, reason: str = "malformed"):
        self.reason = reason
        super().__init__(f"Envelope error: {reason}")
