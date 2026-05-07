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
import time
from datetime import UTC, datetime, timedelta

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from core._pwd import BcryptContext

logger = logging.getLogger(__name__)

ISSUER = "Syroce PMS"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LEN = 8  # 8 hex chars = 32 bits entropy per code

# Bcrypt for backup codes — same context as passwords, separate purpose.
_pwd = BcryptContext()


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
    """Verify a 6-digit TOTP code. window=1 → ±30s tolerance.

    NOTE: This helper alone does NOT prevent same-window replay. For login
    and any state-changing TOTP gate, use `verify_totp_with_counter` plus
    `consume_totp_counter` so the matched 30-second slot can only be used
    once per user.
    """
    if not code or not code.strip().isdigit():
        return False
    try:
        return pyotp.TOTP(secret_b32).verify(code.strip(), valid_window=window)
    except Exception:
        return False


def verify_totp_with_counter(
    secret_b32: str, code: str, window: int = 1
) -> tuple[bool, int | None]:
    """Backward-compatible single-counter helper. Prefers the current 30s
    slot (offset 0), then -1, then +1, etc. so the consumed counter is the
    most likely one. NOTE: callers that need same-window replay protection
    should use `verify_totp_matching_counters` and `consume_totp_counters`
    so an adjacent-counter collision (the same 6-digit code happening to
    valid for two adjacent slots, ~1e-6) cannot be exploited.
    """
    counters = verify_totp_matching_counters(secret_b32, code, window=window)
    return (bool(counters), counters[0] if counters else None)


def verify_totp_matching_counters(
    secret_b32: str, code: str, window: int = 1
) -> list[int]:
    """Return EVERY RFC-6238 counter (unix_seconds//30) within ±window
    whose generated code equals `code`. Order: current slot first, then
    expanding outward (-1, +1, -2, +2, ...). Empty list = no match.

    The full list matters for replay protection: if the same 6-digit code
    is valid for two adjacent counters, both slots must be consumed
    atomically. Otherwise an attacker could claim slot W on the first
    verify and replay against slot W-1 on the second.
    """
    if not code or not code.strip().isdigit():
        return []
    try:
        totp = pyotp.TOTP(secret_b32)
        now = int(time.time())
        offsets = [0]
        for d in range(1, window + 1):
            offsets.append(-d)
            offsets.append(d)
        out: list[int] = []
        target = code.strip()
        for off in offsets:
            t = now + off * 30
            if totp.at(t) == target:
                out.append(t // 30)
        return out
    except Exception:
        return []


# ── Same-window TOTP replay guard (Bug CB / v45) ──────────────────
# We keep a `consumed_totp` collection with a unique compound index on
# (user_id, counter) so concurrent requests for the same matched 30s slot
# race atomically: exactly one winner, others see DuplicateKeyError.
_consumed_totp_index_ready = False


async def _ensure_consumed_totp_index(raw_db) -> None:
    """Idempotent index creation + post-verification. Raises on failure so
    the verify path fails closed rather than silently allowing replay."""
    global _consumed_totp_index_ready
    if _consumed_totp_index_ready:
        return
    await raw_db.consumed_totp.create_index(
        [("user_id", 1), ("counter", 1)], unique=True, name="user_counter_unique"
    )
    await raw_db.consumed_totp.create_index("expires_at", expireAfterSeconds=0)
    info = await raw_db.consumed_totp.index_information()
    has_unique = False
    for spec in info.values():
        if not spec.get("unique"):
            continue
        keys = [f for f, _ in spec.get("key", [])]
        if keys == ["user_id", "counter"]:
            has_unique = True
            break
    if not has_unique:
        raise RuntimeError(
            "consumed_totp: unique (user_id, counter) index missing — refusing "
            "to verify TOTP without same-window replay protection (Bug CB guard)."
        )
    _consumed_totp_index_ready = True


async def consume_totp_counter(
    raw_db, user_id: str, counter: int, ttl_seconds: int = 180
) -> bool:
    """Single-counter convenience wrapper around `consume_totp_counters`."""
    return await consume_totp_counters(raw_db, user_id, [counter], ttl_seconds=ttl_seconds)


async def consume_totp_counters(
    raw_db, user_id: str, counters: list[int], ttl_seconds: int = 180
) -> bool:
    """Atomically claim ALL of (user_id, c) for c in counters. Returns
    True only if every slot was newly inserted. If any slot was already
    consumed (DuplicateKeyError), returns False and any not-yet-claimed
    slots in the same call are still inserted (defensive — leaves no
    unclaimed adjacent-counter window for a follow-up replay).

    Raises on any non-duplicate DB error (fail-closed)."""
    from pymongo.errors import BulkWriteError
    await _ensure_consumed_totp_index(raw_db)
    if not counters:
        return False
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    docs = [
        {"user_id": user_id, "counter": c, "consumed_at": now, "expires_at": expires_at}
        for c in counters
    ]
    try:
        # ordered=False so a duplicate on one slot does not prevent claiming
        # the others — we want both adjacent slots locked even if one
        # collided (so the attacker has nowhere to replay to).
        await raw_db.consumed_totp.insert_many(docs, ordered=False)
        return True
    except BulkWriteError as exc:
        details = exc.details or {}
        write_errors = details.get("writeErrors", []) or []
        non_dup = [e for e in write_errors if e.get("code") != 11000]
        if non_dup:
            # propagate genuine errors so the auth handler returns 503
            raise
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
                logger.warning("2FA: backup-code hash verify failed; treating as no-match", exc_info=True)
        remaining.append(h)
    return matched, remaining
