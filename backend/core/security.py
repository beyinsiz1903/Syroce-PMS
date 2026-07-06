"""
Syroce PMS - Security & Authentication Helpers
JWT token management, password hashing, and user authentication.
"""

import logging

logger = logging.getLogger(__name__)

import base64
import io
import os
import secrets
import time
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core._pwd import BcryptContext
from models.enums import UserRole

# ---------------------------------------------------------------------------
# Per-process user-doc cache.
#
# Why this exists: every authenticated request used to hit Atlas with a
# `db.users.find_one(...)` (~150ms RTT to the cluster). On the bookings
# endpoint that single lookup accounted for the bulk of the ~265ms in-handler
# auth time. We cache the *raw* (still-encrypted) user doc keyed by user_id
# for 30 seconds. JWT decode, jti revocation check, and tokens_invalid_before
# enforcement still run on every request — only the Atlas round-trip is
# memoized. 30 s is the grace window after logout / password change before
# in-flight tokens are rejected (acceptable: login sessions are hours long
# and Redis-based jti revocation still bites immediately).
#
# Decrypted docs are deliberately NOT cached (each request re-decrypts) so
# plaintext PII never lingers in process memory longer than one request.
# ---------------------------------------------------------------------------
_USER_DOC_CACHE: dict[str, tuple[dict, float]] = {}
_USER_DOC_CACHE_TTL = 30.0  # seconds
_USER_DOC_CACHE_MAX = 1000


def _user_doc_cache_get(user_id: str) -> dict | None:
    entry = _USER_DOC_CACHE.get(user_id)
    if not entry:
        return None
    doc, expires_at = entry
    if expires_at <= time.time():
        _USER_DOC_CACHE.pop(user_id, None)
        return None
    return doc


def _user_doc_cache_set(user_id: str, doc: dict) -> None:
    if len(_USER_DOC_CACHE) >= _USER_DOC_CACHE_MAX:
        # Cheap eviction: drop the 200 entries closest to expiry. Avoids the
        # O(n log n) full sort of LRU; good enough for a 1k-entry bound.
        for k in sorted(_USER_DOC_CACHE, key=lambda k: _USER_DOC_CACHE[k][1])[:200]:
            _USER_DOC_CACHE.pop(k, None)
    _USER_DOC_CACHE[user_id] = (doc, time.time() + _USER_DOC_CACHE_TTL)


def _local_evict_user_doc(user_id: str | None = None) -> None:
    """Drop entries from the local in-process cache *only*. Used by the
    pub/sub listener so receiving an eviction event never re-publishes
    (which would loop forever across workers)."""
    if user_id is None:
        _USER_DOC_CACHE.clear()
    else:
        _USER_DOC_CACHE.pop(user_id, None)


def invalidate_user_doc_cache(user_id: str | None = None) -> None:
    """Force-evict cached user doc(s) on this worker AND every other
    worker via Redis pub/sub. Call after profile updates, password
    changes, or role changes that must take effect immediately instead
    of waiting up to 30 s for the cache to expire.

    The local evict happens unconditionally so single-worker / Redis-down
    deployments stay correct. Cross-worker broadcast is best-effort."""
    _local_evict_user_doc(user_id)
    # A role change is also a super-admin-cache change. Evict the entitlement
    # super-admin cache on this worker too (cross-worker handled by the
    # pub/sub listener, which evicts both caches on receipt). Lazy import to
    # avoid a load-time cycle (security ↔ entitlement ↔ database).
    try:
        from core.entitlement import _local_evict_super_admin

        _local_evict_super_admin(user_id)
    except Exception:
        pass
    # Lazy import: infra.auth_cache_pubsub depends on this module's
    # ``_local_evict_user_doc`` for its listener, so we must not import
    # it at module-load time (circular).
    try:
        from infra.auth_cache_pubsub import auth_cache_pubsub

        auth_cache_pubsub.schedule_publish_user(user_id)
    except Exception:
        # Any failure here must not block the mutation result; local
        # eviction has already happened so this worker is correct.
        pass


# Password hashing — direct bcrypt (passlib retired, see core/_pwd.py)
pwd_context = BcryptContext()

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    # v107 (Bug DAG, architect P0 follow-up): tutarlılık için 5 fail-open noktasının
    # SONUNCUSU. Önceki davranış: random fallback + INFO log → multi-worker prod'da
    # her worker farklı secret → cross-worker token reject + INFO seviyesi log
    # gözden kaçar. Şimdi 5 yer hepsi aynı opt-in pattern.
    if os.environ.get("STRICT_JWT_SECRET") == "1" or os.environ.get("ENV", "").lower() == "production":
        raise RuntimeError(
            "JWT_SECRET environment variable is required in production (STRICT_JWT_SECRET=1 or ENV=production set). Without it, multi-worker deployments would have inconsistent token verification."
        )
    import hashlib
    JWT_SECRET = hashlib.sha256(b"syroce_local_dev_environment_static_key").hexdigest()
    logger.warning(
        "⚠️ JWT_SECRET unset; core/security using a static dev secret (DEV ONLY). For production set JWT_SECRET + STRICT_JWT_SECRET=1."
    )
JWT_ALGORITHM = "HS256"
# v44 (Bug BJ): default lowered 168h → 24h. 7-day tokens are way too long for
# a stolen-token blast radius given there was previously no revocation path.
# Override via env if a deployment really needs longer-lived tokens.
#
# V3 (Syroce mobil) — the access-token lifetime DEFAULT is now 15 minutes,
# matching the task acceptance criteria. Web sessions still rotate via
# `/api/auth/refresh-token` (or via the mobile refresh-token flow on
# native), so this is a safe default everywhere. Operators that need a
# longer lifetime can still override via either env var:
#   * `JWT_EXPIRATION_MINUTES` (preferred, integer minutes)
#   * `JWT_EXPIRATION_HOURS` (legacy, fractional hours)
# Setting `JWT_EXPIRATION_HOURS` explicitly continues to honour the old
# value so existing deployments that pinned 24h aren't surprised at upgrade.
_V3_DEFAULT_ACCESS_MINUTES = 120
if os.environ.get("TESTING") == "1":
    _V3_DEFAULT_ACCESS_MINUTES = 120


def _resolve_jwt_lifetime_minutes() -> int:
    raw_minutes = os.environ.get("JWT_EXPIRATION_MINUTES")
    if raw_minutes:
        try:
            return max(120, int(raw_minutes))
        except (TypeError, ValueError):
            pass
    raw_hours = os.environ.get("JWT_EXPIRATION_HOURS")
    if raw_hours is not None:
        try:
            return max(120, int(round(float(raw_hours) * 60)))
        except (TypeError, ValueError):
            pass
    return max(120, _V3_DEFAULT_ACCESS_MINUTES)


JWT_EXPIRATION_MINUTES = _resolve_jwt_lifetime_minutes()
# Kept for backwards-compat; some legacy callers still import this constant
# (router responses, server bootstrap log line, etc.). Rounding up means a
# 15-minute token still surfaces as "1 hour" in the legacy field rather
# than 0 — those consumers don't gate behaviour on the value.
JWT_EXPIRATION_HOURS = max(1, round(JWT_EXPIRATION_MINUTES / 60))

# V3 (Syroce mobil): refresh tokens are long-lived (default 30 days) and
# carry `type: "refresh"` so they cannot be used to authenticate against
# normal API endpoints. They sit in SecureStore on the device, are sent
# explicitly in the body of `/api/auth/refresh-token`, and are rotated
# (old jti revoked) on every successful refresh. This decouples the
# 15-minute access-token lifetime from the user's session lifetime.
REFRESH_TOKEN_EXPIRATION_DAYS = max(1, int(os.environ.get("REFRESH_TOKEN_EXPIRATION_DAYS", "30")))

class CookieHTTPBearer(HTTPBearer):
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        res = await super().__call__(request)
        if res:
            return res
        token = request.cookies.get("access_token")
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        if self.auto_error:
            raise HTTPException(status_code=403, detail="Not authenticated")
        return None

security = CookieHTTPBearer(auto_error=False)

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
    try:
        await sys_db.revoked_tokens.create_index("jti", unique=True)
        await sys_db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
        info = await sys_db.revoked_tokens.index_information()
        has_unique = any(spec.get("unique") and any(f == "jti" for f, _ in spec.get("key", [])) for spec in info.values())
        if not has_unique:
            logger.warning("revoked_tokens.jti unique index is missing or non-unique, revocation may not be atomic")
    except Exception as e:
        logger.error("Failed to ensure revoked_tokens index: %s", e)
    _revoked_index_ready = True


async def revoke_jti(jti: str, exp_ts: int, *, user_id: str | None = None, tenant_id: str | None = None, reason: str = "logout") -> bool:
    """Insert jti into the revocation set with TTL aligned to token exp.

    Returns True if THIS call inserted the jti (winner), False if it was
    already revoked (loser / replayed refresh). Raises on any other error
    so callers can fail-closed instead of pretending success.
    """
    if not jti:
        return False
    await _ensure_revoked_tokens_index()
    from pymongo.errors import DuplicateKeyError

    from core.tenant_db import get_system_db

    sys_db = get_system_db()
    try:
        await sys_db.revoked_tokens.insert_one(
            {
                "jti": jti,
                "expires_at": datetime.fromtimestamp(int(exp_ts), tz=UTC),
                "user_id": user_id,
                "tenant_id": tenant_id,
                "reason": reason,
                "revoked_at": datetime.now(UTC),
            }
        )
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
        return False  # Changed from True to False to prevent infinite logout loop on DB errors


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
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "jti": secrets.token_urlsafe(16),  # v44: revocable token id
        "exp": now + timedelta(minutes=JWT_EXPIRATION_MINUTES),
        # V3: explicit token type so refresh tokens (which decode under the
        # same JWT_SECRET) can't be silently used as access tokens.
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, tenant_id: str | None = None) -> tuple[str, int]:
    """V3 — Syroce mobil refresh-token issuance.

    Mints a long-lived JWT (default 30d, `REFRESH_TOKEN_EXPIRATION_DAYS`)
    distinguishable from the access token by `type: "refresh"`. Returns
    `(token, exp_unix_ts)` so the auth router can immediately persist the
    expiry alongside the rotation audit row without re-decoding.

    This token is sent in the request body to `/api/auth/refresh-token`
    (NOT the Authorization header) so an attacker who steals an Authorization
    bearer in transit cannot use it to keep the session alive indefinitely.
    """
    now = datetime.now(UTC)
    exp = now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "jti": secrets.token_urlsafe(24),
        "exp": exp,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), int(exp.timestamp())


async def get_current_user(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Decode JWT token and return the authenticated User."""
    # Import here to avoid circular imports with schemas
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request as StarletteRequest

    from models.schemas import User
    from security.encrypted_lookup import decrypt_user_doc

    # Support backwards compatibility for manual calls like: get_current_user(credentials)
    # where credentials object is passed as the first positional argument `request`.
    if isinstance(request, HTTPAuthorizationCredentials):
        credentials = request
        request = None

    try:
        token = None
        if isinstance(request, StarletteRequest):
            token = request.cookies.get("access_token")
        if not token and credentials and hasattr(credentials, "credentials"):
            token = credentials.credentials

        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user_id")

        # V3 — Syroce mobil hardening: refresh tokens carry `type="refresh"`
        # and have a 30-day lifetime. They MUST NOT authenticate normal API
        # endpoints — only the dedicated `/api/auth/refresh-token` flow.
        # Reject any non-access token presented as a bearer credential.
        # Tokens minted before V3 lack the `type` claim entirely; those are
        # accepted (backwards-compat) but every newly-minted access token
        # carries `type="access"` explicitly via `create_token()`.
        token_type = payload.get("type")
        if token_type and token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong token type — refresh tokens cannot access API endpoints",
            )

        # v44: revoked-token check (logout/refresh-rotation enforcement).
        # Tokens issued before v44 lack `jti` → treated as non-revocable but
        # still expire naturally; new tokens always carry a jti.
        jti = payload.get("jti")
        if jti and await is_jti_revoked(jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked - please login again")

        # Cached read avoids a per-request Atlas round-trip (~150 ms RTT).
        # See `_user_doc_cache_*` block above for the full rationale and
        # security tradeoffs (30 s grace after logout / password change).
        user_doc = _user_doc_cache_get(user_id)
        if user_doc is None:
            from core.tenant_db import get_system_db
            sys_db = get_system_db()
            user_doc = await sys_db.users.find_one({"$or": [{"id": user_id}, {"user_id": user_id}]}, {"_id": 0})
            if user_doc:
                _user_doc_cache_set(user_id, user_doc)

        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # v46 (Bug CC): mass-revoke on password change. If the user has
        # `tokens_invalid_before` set (epoch seconds), any token whose `iat`
        # is older must be rejected — covers all parallel sessions without
        # tracking each jti individually. Tokens lacking `iat` (pre-v44) are
        # treated as invalid once this watermark is set (fail-closed).
        invalid_before = user_doc.get("tokens_invalid_before")
        if invalid_before:
            iat = payload.get("iat")
            # Allow a 10-second leeway to prevent race conditions during immediate logout/login or clock drift
            if not iat or int(iat) < int(invalid_before) - 10:
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
        jwt_tenant = payload.get("tenant_id")
        doc_tenant = user_doc.get("tenant_id")
        if jwt_tenant and doc_tenant and jwt_tenant != doc_tenant:
            logger.warning(f"JWT tenant mismatch: user={user_id} jwt_tenant={jwt_tenant} doc_tenant={doc_tenant}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token-tenant mismatch - please login again",
            )

        user_doc = decrypt_user_doc(user_doc)

        # Force-reset sigortasi: requires_password_change=True olan kullanici,
        # sifresini degistirene kadar yalnizca sifre-degistirme / cikis / profil
        # uclarina erisebilir. Diger her sey fail-closed 403. Istek yolu
        # belirlenemiyorsa (dogrudan, non-Depends cagri) yine reddedilir.
        if user_doc.get("requires_password_change"):
            # Exact-path allowlist (suffix degil) — gelecekte ayni son-eke sahip
            # yeni bir route'un yanlislikla izin acmasini onler. Hem /api on-ekli
            # hem on-eksiz mount varyantlari kapsanir.
            _allowed = {
                "/api/auth/change-password",
                "/auth/change-password",
                "/api/auth/logout",
                "/auth/logout",
                "/api/auth/me",
                "/auth/me",
            }
            _path = request.url.path.rstrip("/") if request is not None else None
            if not _path or _path not in _allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Devam etmeden once sifrenizi degistirmelisiniz.",
                )

        if "id" not in user_doc:
            user_doc["id"] = user_doc.get("user_id", user_id)
        if "user_id" not in user_doc:
            user_doc["user_id"] = user_doc.get("id", user_id)

        return User(**user_doc)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired - please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token - please login again")
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.info(f"Auth error: {str(e)}\n{traceback.format_exc()}")
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
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def generate_time_based_qr_token(booking_id: str, expiry_hours: int = 72) -> str:
    expiry = datetime.now(UTC) + timedelta(hours=expiry_hours)
    token = secrets.token_urlsafe(32)
    return jwt.encode({"booking_id": booking_id, "token": token, "exp": expiry}, JWT_SECRET, algorithm=JWT_ALGORITHM)
