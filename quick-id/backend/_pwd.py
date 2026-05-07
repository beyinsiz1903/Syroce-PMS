"""Bcrypt direct shim — `passlib` replacement (Quick-ID copy).

See `backend/core/_pwd.py` for rationale. Quick-ID runs as a separate Python
process with its own sys.path, so it cannot import from `backend/core/`.
"""
from __future__ import annotations

import bcrypt


class BcryptContext:
    """Drop-in replacement for `passlib.context.CryptContext(schemes=["bcrypt"])`."""

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
            return False

    def dummy_verify(self) -> None:
        try:
            bcrypt.checkpw(b"dummy", self._DUMMY_HASH)
        except Exception:
            pass
