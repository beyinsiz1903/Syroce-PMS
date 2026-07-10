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

import hmac
import logging
import os
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

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
    _previous_kid: str | None = field(default=None)
    _previous_key: bytes | None = field(default=None, repr=False)

    def encryption_key(self) -> tuple:
        """Returns (kid, derived_key) for encrypting new data."""
        return (self.current_kid, self._current_key)

    def decryption_key(self, kid: str) -> bytes:
        """Resolve derived key by kid. Rejects unknown kids strictly."""
        if kid == self.current_kid:
            return self._current_key
        if self._previous_key is not None and kid == self._previous_kid:
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
        previous_key: bytes | None = None,
        previous_kid: str | None = None,
    ) -> "KeyRing":
        """Create a KeyRing with raw key bytes for testing. NOT for production use."""
        return cls(
            current_kid=kid,
            _current_key=current_key,
            _previous_kid=previous_kid,
            _previous_key=previous_key,
        )


def load_keyring() -> KeyRing:
    """Load keyring from environment variables. Fails loudly in production."""
    app_env = os.environ.get("APP_ENV", "development")
    is_prod = app_env in PRODUCTION_ENVS

    current_master = os.environ.get("CM_MASTER_KEY_CURRENT", "")
    previous_master = os.environ.get("CM_MASTER_KEY_PREVIOUS", "")

    # Enforce CM_KEY_VERSION_CURRENT as canonical if both exist, reject if mismatched.
    legacy_version = os.environ.get("CM_KEY_VERSION")
    canon_version = os.environ.get("CM_KEY_VERSION_CURRENT")
    if legacy_version and canon_version and legacy_version != canon_version:
        raise KeyDerivationError("CM_KEY_VERSION and CM_KEY_VERSION_CURRENT are both set but do not match.")

    key_version_current = canon_version or legacy_version
    if not key_version_current:
        if is_prod:
            raise KeyDerivationError("CM_KEY_VERSION_CURRENT is mandatory in production/staging.")
        key_version_current = "v1"

    key_version_previous = os.environ.get("CM_KEY_VERSION_PREVIOUS", "")

    if bool(previous_master) != bool(key_version_previous):
        raise KeyDerivationError("Both CM_MASTER_KEY_PREVIOUS and CM_KEY_VERSION_PREVIOUS must be set together.")

    if previous_master and hmac.compare_digest(current_master.encode("utf-8"), previous_master.encode("utf-8")):
        raise KeyDerivationError("Current and previous master keys cannot be identical.")

    if key_version_previous and key_version_current == key_version_previous:
        raise KeyDerivationError("Current and previous key versions (kids) cannot be identical.")

    if is_prod:
        if not current_master:
            raise KeyDerivationError("CM_MASTER_KEY_CURRENT is required in production/staging. Set it to a cryptographically strong secret (32+ characters).")
        if len(current_master.encode("utf-8")) < 32:
            raise KeyDerivationError("CM_MASTER_KEY_CURRENT is too weak for production (minimum 32 bytes required).")
        if previous_master and len(previous_master.encode("utf-8")) < 32:
            raise KeyDerivationError("CM_MASTER_KEY_PREVIOUS is too weak for production (minimum 32 bytes required).")

    if not current_master:
        # Development fallback chain: CM_CREDENTIAL_KEY → hardcoded dev key
        current_master = os.environ.get("CM_CREDENTIAL_KEY", "") or _DEV_FALLBACK_KEY
        logger.warning("CM_MASTER_KEY_CURRENT not set — using dev fallback. NOT SAFE FOR PRODUCTION.")

    current_key = derive_key(current_master)
    previous_key = derive_key(previous_master) if previous_master else None

    logger.info(
        "KeyRing loaded: kid=%s previous_kid=%s env=%s",
        key_version_current,
        key_version_previous if previous_key else None,
        app_env,
    )
    return KeyRing(
        current_kid=key_version_current,
        _current_key=current_key,
        _previous_kid=key_version_previous if previous_key else None,
        _previous_key=previous_key,
    )
