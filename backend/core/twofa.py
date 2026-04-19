"""Two-Factor Authentication (TOTP RFC 6238) helpers.

Storage model on the user document:
  - two_factor_enabled: bool
  - two_factor_secret_enc: str   # AES (Fernet) encrypted base32 secret
  - two_factor_backup_codes: list[str]  # bcrypt hashes of one-time codes
  - two_factor_last_used_at: ISO datetime
  - two_factor_enabled_at: ISO datetime

The TOTP secret is encrypted at rest using the same key as other PII
fields. Backup codes are stored as bcrypt hashes (never plaintext).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

ISSUER = "Syroce PMS"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LEN = 8  # 8 hex chars = 32 bits entropy per code

# Bcrypt for backup codes — same context as passwords, separate purpose.
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _derive_key() -> bytes:
    """Derive a Fernet key from JWT_SECRET (or TWOFA_SECRET if set).

    Uses a domain separation prefix so even if JWT_SECRET is shared the
    derived key is unique to 2FA storage. Falls back to the runtime
    JWT_SECRET constant in core.security (which is itself required to
    be set in production); never to a hard-coded literal.
    """
    base = os.environ.get("TWOFA_SECRET") or os.environ.get("JWT_SECRET", "")
    if not base:
        try:
            from core.security import JWT_SECRET as _RUNTIME_JWT_SECRET
            base = _RUNTIME_JWT_SECRET or ""
        except Exception:
            base = ""
    if not base:
        raise RuntimeError(
            "TWOFA_SECRET or JWT_SECRET must be set to derive 2FA encryption key"
        )
    digest = hashlib.sha256(b"2fa-secret-v1|" + base.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_FERNET = Fernet(_derive_key())


def encrypt_secret(plain_b32: str) -> str:
    return _FERNET.encrypt(plain_b32.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("2FA secret could not be decrypted (key mismatch)")


# ── TOTP ──────────────────────────────────────────────────────────
def generate_secret() -> str:
    """Return a fresh base32 TOTP secret (32 chars / 160 bits)."""
    return pyotp.random_base32()


def provisioning_uri(secret_b32: str, account_label: str) -> str:
    """otpauth:// URI for QR codes (compatible with Google/MS Authenticator)."""
    return pyotp.TOTP(secret_b32).provisioning_uri(
        name=account_label, issuer_name=ISSUER
    )


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verify a 6-digit TOTP code. window=1 → ±30s tolerance."""
    if not code or not code.strip().isdigit():
        return False
    try:
        return pyotp.TOTP(secret_b32).verify(code.strip(), valid_window=window)
    except Exception:
        return False


# ── Backup codes ──────────────────────────────────────────────────
def generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> list[str]:
    """Generate plaintext backup codes (shown once to the user)."""
    return [secrets.token_hex(BACKUP_CODE_LEN // 2).upper() for _ in range(n)]


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [_pwd.hash(c) for c in codes]


def consume_backup_code(stored_hashes: list[str], code: str) -> tuple[bool, list[str]]:
    """Try to consume a backup code. Returns (matched, remaining_hashes).

    On match the matching hash is removed (single-use).
    """
    if not code:
        return False, stored_hashes
    code = code.strip().upper().replace("-", "").replace(" ", "")
    remaining: list[str] = []
    matched = False
    for h in stored_hashes:
        if not matched:
            try:
                if _pwd.verify(code, h):
                    matched = True
                    continue  # drop this hash
            except Exception:
                pass
        remaining.append(h)
    return matched, remaining
