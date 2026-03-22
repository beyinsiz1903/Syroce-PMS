"""
Key management — HKDF-SHA256 derivation, dual-key keyring, env-based loading.

Key hierarchy:
  Master Key (from env) → HKDF-SHA256 → Derived AES-256 Key

Environment variables:
  CM_MASTER_KEY_CURRENT   — active encryption key (REQUIRED in production)
  CM_MASTER_KEY_PREVIOUS  — previous key for decryption during rotation (optional)
  CM_KEY_VERSION          — current key identifier (e.g. "v1", "v2")
  APP_ENV                 — production | staging | development
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from .errors import KeyDerivationError, KeyNotFoundError

logger = logging.getLogger("core.crypto.keys")

# HKDF parameters — fixed, never change after first deployment
HKDF_SALT = b"syroce-credential-encryption-salt-v1"
HKDF_INFO = b"aes-256-gcm-key"

PRODUCTION_ENVS = {"production", "staging"}
_DEV_FALLBACK_KEY = "syroce-dev-master-NOT-FOR-PRODUCTION"


def derive_key(master_material: str) -> bytes:
    """Derive a 256-bit AES key from master material using HKDF-SHA256.

    Returns exactly 32 bytes suitable for AES-256.
    """
    if not master_material:
        raise KeyDerivationError("empty_master_material")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=HKDF_SALT,
        info=HKDF_INFO,
    )
    return hkdf.derive(master_material.encode("utf-8"))


@dataclass(frozen=True)
class KeyRing:
    """Immutable keyring holding current and optionally previous derived keys.

    - Current key: used for all new encryptions.
    - Previous key: used only for decryption of data encrypted before rotation.
    """
    current_kid: str
    _current_key: bytes = field(repr=False)
    _previous_key: Optional[bytes] = field(default=None, repr=False)

    def encryption_key(self) -> tuple:
        """Returns (kid, derived_key) for encrypting new data."""
        return (self.current_kid, self._current_key)

    def decryption_key(self, kid: str) -> bytes:
        """Resolve derived key by kid. Falls back to previous for non-current kids."""
        if kid == self.current_kid:
            return self._current_key
        if self._previous_key is not None:
            return self._previous_key
        raise KeyNotFoundError(kid)

    @property
    def has_previous(self) -> bool:
        return self._previous_key is not None

    @classmethod
    def _from_test(
        cls,
        current_key: bytes,
        kid: str = "test-v1",
        previous_key: Optional[bytes] = None,
        previous_kid: Optional[str] = None,
    ) -> "KeyRing":
        """Create a KeyRing with raw key bytes for testing. NOT for production use."""
        return cls(
            current_kid=kid,
            _current_key=current_key,
            _previous_key=previous_key,
        )


def load_keyring() -> KeyRing:
    """Load keyring from environment variables. Fails loudly in production."""
    app_env = os.environ.get("APP_ENV", "development")
    is_prod = app_env in PRODUCTION_ENVS

    current_master = os.environ.get("CM_MASTER_KEY_CURRENT", "")
    previous_master = os.environ.get("CM_MASTER_KEY_PREVIOUS", "")
    key_version = os.environ.get("CM_KEY_VERSION", "v1")

    if not current_master:
        if is_prod:
            raise KeyDerivationError(
                "CM_MASTER_KEY_CURRENT is required in production/staging. "
                "Set it to a cryptographically strong secret (32+ characters)."
            )
        # Development fallback chain: CM_CREDENTIAL_KEY → hardcoded dev key
        current_master = os.environ.get("CM_CREDENTIAL_KEY", "") or _DEV_FALLBACK_KEY
        logger.warning(
            "CM_MASTER_KEY_CURRENT not set — using dev fallback. NOT SAFE FOR PRODUCTION."
        )

    current_key = derive_key(current_master)
    previous_key = derive_key(previous_master) if previous_master else None

    logger.info(
        "KeyRing loaded: kid=%s has_previous=%s env=%s",
        key_version, previous_key is not None, app_env,
    )
    return KeyRing(
        current_kid=key_version,
        _current_key=current_key,
        _previous_key=previous_key,
    )
