"""
Syroce PMS - Security & Authentication Helpers
JWT token management, password hashing, and user authentication.
"""
import logging

logger = logging.getLogger(__name__)

# Silence harmless passlib/bcrypt version-detection warning emitted on import.
# passlib 1.7.4 reads `bcrypt.__about__.__version__` which was removed in
# bcrypt>=4.1, producing a noisy "(trapped) error reading bcrypt version"
# warning even though hashing works correctly.
logging.getLogger("passlib").setLevel(logging.ERROR)

import base64
import io
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from core.database import db
from models.enums import UserRole

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    # v107 (Bug DAG, architect P0 follow-up): tutarlılık için 5 fail-open noktasının
    # SONUNCUSU. Önceki davranış: random fallback + INFO log → multi-worker prod'da
    # her worker farklı secret → cross-worker token reject + INFO seviyesi log
    # gözden kaçar. Şimdi 5 yer hepsi aynı opt-in pattern.
    if os.environ.get('STRICT_JWT_SECRET') == '1' or os.environ.get('ENV', '').lower() == 'production':
        raise RuntimeError(
            "JWT_SECRET environment variable is required in production "
            "(STRICT_JWT_SECRET=1 or ENV=production set). "
            "Without it, multi-worker deployments would have inconsistent token verification."
        )
    JWT_SECRET = secrets.token_urlsafe(64)
    logger.warning(
        "⚠️ JWT_SECRET unset; core/security using random per-process secret "
        "(DEV ONLY — tokens invalidate on restart, multi-worker inconsistent). "
        "For production set JWT_SECRET + STRICT_JWT_SECRET=1."
    )
JWT_ALGORITHM = 'HS256'
# v44 (Bug BJ): default lowered 168h → 24h. 7-day tokens are way too long for
# a stolen-token blast radius given there was previously no revocation path.
# Override via env if a deployment really needs longer-lived tokens.
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', '24'))

security = HTTPBearer()

# v44 — Token revocation (logout + refresh rotation).
# Tokens issued post-v44 carry a `jti` claim; on logout/rotation we insert that
# jti into `revoked_tokens` (unique + TTL on expires_at). `get_current_user`
# checks this set on every request.
_revoked_index_ready = False


async def _ensure_revoked_tokens_index():
    """Ensure the unique jti index exists. Raises on failure so callers in
    the auth path (revoke_jti) can fail-closed: without a unique index,
    concurrent refreshes could both insert and both win → replay bypass.
    """
    global _revoked_index_ready
    if _revoked_index_ready:
        return
    from core.tenant_db import get_system_db
    sys_db = get_system_db()
    await sys_db.revoked_tokens.create_index("jti", unique=True)
    await sys_db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
    # Verify the unique jti index actually landed (defence against an
    # existing non-unique index silently shadowing the new one).
    info = await sys_db.revoked_tokens.index_information()
    jti_idx = info.get("jti_1") or {}
    if not jti_idx.get("unique"):
        raise RuntimeError("revoked_tokens.jti unique index missing or non-unique")
    _revoked_index_ready = True


async def revoke_jti(jti: str, exp_ts: int, *, user_id: str | None = None,
                     tenant_id: str | None = None, reason: str = "logout") -> bool:
    """Insert jti into the revocation set with TTL aligned to token exp.

    Returns True if THIS call inserted the jti (winner), False if it was
    already revoked (loser / replayed refresh). Raises on any other error
    so callers can fail-closed instead of pretending success.
    """
    if not jti:
        return False
    await _ensure_revoked_tokens_index()
    from core.tenant_db import get_system_db
    from pymongo.errors import DuplicateKeyError
    sys_db = get_system_db()
    try:
        await sys_db.revoked_tokens.insert_one({
            "jti": jti,
            "expires_at": datetime.fromtimestamp(int(exp_ts), tz=UTC),
            "user_id": user_id,
            "tenant_id": tenant_id,
            "reason": reason,
            "revoked_at": datetime.now(UTC),
        })
        return True
    except DuplicateKeyError:
        # Already revoked → idempotent for logout, but the caller of refresh
        # uses the False return to reject the replay.
        return False


async def is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    await _ensure_revoked_tokens_index()
    from core.tenant_db import get_system_db
    sys_db = get_system_db()
    try:
        doc = await sys_db.revoked_tokens.find_one({"jti": jti}, {"_id": 0, "jti": 1})
        return doc is not None
    except Exception as e:
        # Fail-closed for revocation: if we can't check, refuse to honour the
        # token. Better a flaky logout than a permanent bypass.
        logger.error("is_jti_revoked lookup failed for %s: %s", jti, e)
        return True


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def create_token(user_id: str, tenant_id: str | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'iat': now,
        'jti': secrets.token_urlsafe(16),  # v44: revocable token id
        'exp': now + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Decode JWT token and return the authenticated User."""
    # Import here to avoid circular imports with schemas
    from models.schemas import User
    from security.encrypted_lookup import decrypt_user_doc

    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user_id")

        # v44: revoked-token check (logout/refresh-rotation enforcement).
        # Tokens issued before v44 lack `jti` → treated as non-revocable but
        # still expire naturally; new tokens always carry a jti.
        jti = payload.get('jti')
        if jti and await is_jti_revoked(jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked - please login again")

        user_doc = await db.users.find_one(
            {'$or': [{'id': user_id}, {'user_id': user_id}]}, {'_id': 0}
        )

        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # v46 (Bug CC): mass-revoke on password change. If the user has
        # `tokens_invalid_before` set (epoch seconds), any token whose `iat`
        # is older must be rejected — covers all parallel sessions without
        # tracking each jti individually. Tokens lacking `iat` (pre-v44) are
        # treated as invalid once this watermark is set (fail-closed).
        invalid_before = user_doc.get('tokens_invalid_before')
        if invalid_before:
            iat = payload.get('iat')
            if not iat or int(iat) < int(invalid_before):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Şifre değişti - lütfen yeniden giriş yapın",
                )

        # v105 Bug DAA (architect P1): defense-in-depth tenant consistency check.
        # Even though TenantContextMiddleware + TenantAwareDBProxy currently
        # short-circuit a forged JWT.tenant_id (the user_doc lookup itself
        # gets auto-scoped and returns nothing), a future raw query that
        # bypasses the proxy would lose that protection. This explicit check
        # rejects any token whose tenant_id does not match the user's record.
        jwt_tenant = payload.get('tenant_id')
        doc_tenant = user_doc.get('tenant_id')
        if jwt_tenant and doc_tenant and jwt_tenant != doc_tenant:
            logger.warning(
                f"JWT tenant mismatch: user={user_id} jwt_tenant={jwt_tenant} doc_tenant={doc_tenant}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token-tenant mismatch - please login again",
            )

        user_doc = decrypt_user_doc(user_doc)

        if 'id' not in user_doc:
            user_doc['id'] = user_doc.get('user_id', user_id)
        if 'user_id' not in user_doc:
            user_doc['user_id'] = user_doc.get('id', user_id)

        return User(**user_doc)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired - please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token - please login again")
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Auth error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


def _is_super_admin(current_user) -> bool:
    role = getattr(current_user, "role", None)
    if role == UserRole.SUPER_ADMIN:
        return True
    roles = getattr(current_user, "roles", None) or []
    return "super_admin" in roles


def generate_qr_code(data: str) -> str:
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def generate_time_based_qr_token(booking_id: str, expiry_hours: int = 72) -> str:
    expiry = datetime.now(UTC) + timedelta(hours=expiry_hours)
    token = secrets.token_urlsafe(32)
    return jwt.encode({
        'booking_id': booking_id,
        'token': token,
        'exp': expiry
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
