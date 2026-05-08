"""Vendor authentication — separate JWT scope from hotel/staff users.

Tokens carry `scope=vendor` and `vendor_id`, are signed with the same
JWT_SECRET but verified via this module's dependency so a hotel user
JWT cannot access vendor endpoints (and vice versa).
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core._pwd import BcryptContext

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    # v107 (Bug DAG): hardcoded "syroce-dev-secret" was a known-string fallback
    # — anyone could forge vendor-scoped JWT in production. Now opt-in fail-closed.
    if os.environ.get("STRICT_JWT_SECRET") == "1" or os.environ.get("ENV", "").lower() == "production":
        raise RuntimeError("JWT_SECRET environment variable is required in production (STRICT_JWT_SECRET=1 or ENV=production set).")
    import secrets as _secrets
    JWT_SECRET = _secrets.token_urlsafe(64)
    logger.warning("⚠️ JWT_SECRET unset; vendor_auth using random per-process secret (DEV ONLY).")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24

_pwd = BcryptContext()
_security = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        logger.warning("vendor_auth: password verify failed", exc_info=True)
        return False


def create_vendor_token(vendor_id: str, email: str) -> str:
    payload = {
        "scope": "vendor",
        "vendor_id": vendor_id,
        "sub": email,
        "exp": datetime.now(UTC) + timedelta(hours=TOKEN_TTL_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_vendor_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    """FastAPI dependency — returns the vendor_id from a vendor-scoped JWT."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    if payload.get("scope") != "vendor":
        raise HTTPException(status_code=403, detail="Not a vendor token")
    vendor_id = payload.get("vendor_id")
    if not vendor_id:
        raise HTTPException(status_code=401, detail="Token missing vendor_id")
    return vendor_id
