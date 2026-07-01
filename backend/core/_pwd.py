"""Bcrypt direct shim — `passlib` replacement.

Background: `passlib.context.CryptContext(schemes=["bcrypt"])` works fine on
Python ≤ 3.12 but transitively imports the standard-library `crypt` module,
which is removed in Python 3.13. To keep migration friction zero we expose a
drop-in `BcryptContext` with the same `.hash`, `.verify`, and `.dummy_verify`
surface the codebase already calls.

Why a class (instead of free functions): existing call sites do
`pwd_context = CryptContext(...)` then `pwd_context.hash(...)` /
`pwd_context.verify(...)`. Keeping the same shape means a one-line import
swap per file with no behavioral change.
"""

from __future__ import annotations

import bcrypt


class BcryptContext:
    """Drop-in replacement for `passlib.context.CryptContext(schemes=["bcrypt"])`.

    Methods preserved:
      - `hash(plain) -> str`     : returns ascii-decoded bcrypt hash
      - `verify(plain, hashed) -> bool` : constant-time match, swallows malformed input
      - `dummy_verify() -> None` : constant-cost verify against a fixed dummy
        hash (used by login flows on user-not-found to neutralize timing
        attacks; mirrors passlib's `dummy_verify`).
    """

    # Pre-computed at import time. Cost factor 12 matches passlib's default
    # `bcrypt__default_rounds` so the timing profile of a user-not-found path
    # stays indistinguishable from a real verify.
    _DUMMY_HASH: bytes = bcrypt.hashpw(
        b"dummy-password-for-constant-time-verify",
        bcrypt.gensalt(rounds=12),
    )

    def hash(self, password: str) -> str:
        if isinstance(password, str):
            password = password.encode("utf-8")
        return bcrypt.hashpw(password, bcrypt.gensalt()).decode("ascii")

    def verify(self, plain: str | bytes, hashed: str | bytes) -> bool:
        if not plain or not hashed:
            return False
        if isinstance(plain, str):
            plain = plain.encode("utf-8")
        if isinstance(hashed, str):
            hashed = hashed.encode("ascii")
        try:
            return bcrypt.checkpw(plain, hashed)
        except (ValueError, TypeError):
            # Malformed hash — treat as mismatch, never raise (legacy
            # passlib behavior wraps these into UnknownHashError; callers
            # of `.verify` already treat exceptions as failure, but
            # returning False is safer for the credential_guard scan).
            return False

    def dummy_verify(self) -> None:
        """Constant-cost bcrypt verify for timing-attack defense."""
        try:
            bcrypt.checkpw(b"dummy", self._DUMMY_HASH)
        except Exception:
            # Defensive: this path must never raise.
            pass
