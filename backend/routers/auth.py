"""
Auth Router - Authentication, Registration, Email Verification, Password Reset
Extracted from server.py for modularity.
"""
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr

from core.database import db as _tenant_db  # noqa: F401
from core.helpers import load_tenant_doc, resolve_tenant_features
from core.security import (
    JWT_ALGORITHM,
    JWT_EXPIRATION_MINUTES,
    JWT_SECRET,
    REFRESH_TOKEN_EXPIRATION_DAYS,
    create_refresh_token,
    create_token,
    get_current_user,
    hash_password,
    invalidate_user_doc_cache,
    revoke_jti,
    verify_password,
)
from core.tenant_db import get_system_db
from models.enums import UserRole
from models.schemas import (
    GuestRegister,
    NotificationPreferences,
    Tenant,
    TenantRegister,
    TokenResponse,
    User,
    UserLogin,
)
from models.schemas.identity import ChangePasswordRequest
from modules.pms_core.role_permission_service import require_op
from security.encrypted_lookup import (
    build_user_email_query,
    decrypt_user_doc,
    encrypt_user_doc,
)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

# Auth operations are system-level (no tenant context during login/register)
db = get_system_db()

router = APIRouter(prefix="/api", tags=["auth"])


# Bug AS fix — lazy unique+TTL index on consumed_jtis (idempotent, fail-closed)
# Architect note: must NOT swallow errors; if the unique index does not exist,
# the atomic single-use guarantee for 2FA challenge_token is silently lost
# (replay race re-opens). We only flip the ready flag after confirmed
# verification that a unique index on `jti` exists in the live collection.
_consumed_jti_index_ready = False

async def _ensure_consumed_jti_index():
    global _consumed_jti_index_ready
    if _consumed_jti_index_ready:
        return
    from core.database import db as _raw_db
    # Idempotent: create_index is a no-op if an identical index already exists.
    # Errors here (permissions, conflicting non-unique index, transient DB) are
    # propagated so the verify handler returns 500 rather than silently degrading
    # to a non-atomic mode that would re-enable Bug AS replay.
    await _raw_db.consumed_jtis.create_index("jti", unique=True)
    await _raw_db.consumed_jtis.create_index("expires_at", expireAfterSeconds=0)
    # Verify the unique constraint actually exists before declaring readiness.
    info = await _raw_db.consumed_jtis.index_information()
    has_unique_jti = any(
        spec.get("unique") and any(field == "jti" for field, _ in spec.get("key", []))
        for spec in info.values()
    )
    if not has_unique_jti:
        raise RuntimeError(
            "consumed_jtis: unique index on 'jti' missing — refusing to serve "
            "2FA verify without atomic single-use enforcement (Bug AS guard)."
        )
    _consumed_jti_index_ready = True

# Bug AI: timing-attack mitigation — precomputed bcrypt hash + dummy user doc
# so verify_password and decrypt_user_doc burn equal CPU on ghost users,
# preventing email/username enumeration via response-time differences.
_DUMMY_PWHASH = hash_password("__timing_attack_dummy__never_a_real_password__")
_DUMMY_USER_DOC = {
    "id": "00000000-0000-0000-0000-000000000000",
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "email": "__dummy@example.invalid",
    "username": "__dummy",
    "name": "__dummy",
    "phone": "+10000000000",
    "hashed_password": _DUMMY_PWHASH,
}
security = HTTPBearer()

# APM references (injected at init)
_apm_store = None
_get_rate_limit_stats = None


def init_auth_router(apm_store=None, get_rate_limit_stats=None):
    global _apm_store, _get_rate_limit_stats
    _apm_store = apm_store
    _get_rate_limit_stats = get_rate_limit_stats


# ============= AUTH ENDPOINTS =============

class MakeSuperAdminRequest(BaseModel):
    """Request to make a user super admin"""
    email: str
    setup_password: str

def _enforce_setup_enabled():
    """Bug CR (v57) — setup/admin/debug endpoints fail-closed by default.

    Gated by env ENABLE_SETUP_ENDPOINTS=1. Returns 404 (hide existence) when disabled.
    Even when enabled, the configured SETUP_SECRET must match (no hardcoded fallback).
    """
    import os
    if os.environ.get("ENABLE_SETUP_ENDPOINTS", "").strip() != "1":
        raise HTTPException(status_code=404, detail="Not Found")


def _verify_setup_secret(provided: str | None):
    import os
    import secrets as _secrets
    expected = os.environ.get("SETUP_SECRET", "").strip()
    if not expected or not provided or not _secrets.compare_digest(provided, expected):
        # Generic 404 + constant-time compare (no timing oracle, no existence leak)
        raise HTTPException(status_code=404, detail="Not Found")


@router.post("/setup/make-super-admin")
async def setup_make_super_admin(request: MakeSuperAdminRequest):
    """One-time setup: Make any user super_admin (gated, disabled by default).

    Bug CR-R2: blast radius narrowed — if email matches more than one user
    (cross-tenant collision), reject the request (operator must use scoped variants).
    """
    _enforce_setup_enabled()
    _verify_setup_secret(request.setup_password)

    matches = await db.users.count_documents(build_user_email_query(request.email))
    if matches > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple users match this email across tenants. Refusing to elevate all.",
        )
    result = await db.users.update_many(
        build_user_email_query(request.email),
        {"$set": {"role": "super_admin"}}
    )
    invalidate_user_doc_cache()  # update_many → flush all (cheap, setup-gated path)

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"No user found with email: {request.email}")

    return {
        "success": True,
        "message": f"Updated {result.modified_count} user(s) to super_admin",
        "email": request.email,
        "updated_count": result.modified_count
    }


@router.post("/setup/make-me-super-admin")
async def make_me_super_admin(
    setup_password: str,
    current_user: User = Depends(get_current_user)
):
    """Make YOURSELF super_admin (gated, disabled by default)."""
    _enforce_setup_enabled()
    _verify_setup_secret(setup_password)

    # Update current logged-in user to super_admin
    result = await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"role": "super_admin"}}
    )
    invalidate_user_doc_cache(current_user.id)

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Role güncellenemedi veya zaten super_admin")

    return {
        "success": True,
        "message": "Artık super_admin'siniz! Lütfen logout yapıp tekrar giriş yapın.",
        "email": current_user.email,
        "user_id": current_user.id
    }


@router.post("/admin/quick-super-admin")
async def quick_make_super_admin(
    email: str,
    secret: str | None = None
):
    """Bug CR (v57) — was GET with hardcoded secret (CSRF/log/referrer leak).
    Now POST + env-gated + no-fallback secret."""
    _enforce_setup_enabled()
    _verify_setup_secret(secret)

    # Bug CR-R2: refuse multi-match to limit blast radius
    matches = await db.users.count_documents(build_user_email_query(email))
    if matches > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple users match this email across tenants. Refusing to elevate all.",
        )
    result = await db.users.update_many(
        build_user_email_query(email),
        {"$set": {"role": "super_admin"}}
    )
    invalidate_user_doc_cache()  # update_many → flush all (cheap, setup-gated path)

    if result.matched_count == 0:
        # Bug CR-R3: case-insensitive fallback also enforces single-match guard
        import re as _re
        _safe_email = _re.escape(email.strip()) if isinstance(email, str) and email.strip() else "a^"
        ci_filter = {"email": {"$regex": f"^{_safe_email}$", "$options": "i"}}
        ci_matches = await db.users.count_documents(ci_filter)
        if ci_matches > 1:
            raise HTTPException(
                status_code=409,
                detail="Multiple users match this email (case-insensitive). Refusing to elevate all.",
            )
        result = await db.users.update_many(ci_filter, {"$set": {"role": "super_admin"}})
        invalidate_user_doc_cache()  # CI fallback also flushes

    return {
        "success": True,
        "updated": result.modified_count,
        "matched": result.matched_count,
        "email": email,
        "message": f"Updated {result.modified_count} user(s) to super_admin. Logout and login to see changes."
    }


@router.get("/admin/list-all-users-debug")
async def list_all_users_for_debug(secret: str | None = None):
    """Bug CR (v57) — gated; was hardcoded DEBUG_2024 leaking cross-tenant user inventory."""
    _enforce_setup_enabled()
    _verify_setup_secret(secret)

    users = await db.users.find({}, {"_id": 0, "hashed_password": 0, "password_hash": 0}).limit(20).to_list(20)

    return {
        "total": len(users),
        "users": [
            {
                "email": u.get("email"),
                "name": u.get("name"),
                "role": u.get("role"),
                "tenant_id": u.get("tenant_id", "")[:8] + "..."
            }
            for u in users
        ]
    }


async def _generate_unique_hotel_id() -> str:
    """Generate a 6-digit unique hotel_id, retrying on collision."""
    from core.hotel_ids import generate_unique_hotel_id
    return await generate_unique_hotel_id(db)


def _derive_username(email: str, name: str | None = None) -> str:
    """Derive a default username from email local-part."""
    import re as _re
    base = (email or "").split("@", 1)[0].strip().lower()
    base = _re.sub(r"[^a-z0-9._-]+", "", base) or "user"
    return base


def _build_token_response(user: User, tenant) -> TokenResponse:
    """Single source of truth for the V3 login/refresh response shape.

    Every successful authentication path (direct login, cached login,
    2FA verify, email verification, registration) MUST go through this
    helper so the response carries:
      * a fresh access token (`type="access"`, lifetime
        `JWT_EXPIRATION_MINUTES`)
      * a freshly-minted refresh token (`type="refresh"`, lifetime
        `REFRESH_TOKEN_EXPIRATION_DAYS`) — required for the V3 mobile
        rotation lifecycle.
      * `expires_in` so the client can plan its proactive refresh.
    Centralising this prevents path drift (e.g. a 2FA-verified login
    silently degrading to a refresh-less response).
    """
    access = create_token(user.id, user.tenant_id)
    refresh, _ = create_refresh_token(user.id, user.tenant_id)
    return TokenResponse(
        access_token=access,
        user=user,
        tenant=tenant,
        refresh_token=refresh,
        expires_in=JWT_EXPIRATION_MINUTES * 60,
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register_tenant(data: TenantRegister, request: Request):
    # v54 (Bug CO): per-IP and per-email throttle. Without these the
    # endpoint allowed unbounded tenant creation and account-enumeration
    # via the existing/new email response shape difference.
    from security.auth_throttle import (
        REGISTER_EMAIL,
        REGISTER_IP,
        client_ip,
        enforce,
        normalize_identity,
    )
    await enforce(REGISTER_IP, f"ip:{client_ip(request)}", "kayıt isteği")
    await enforce(REGISTER_EMAIL, f"em:{normalize_identity(data.email)}", "kayıt isteği")

    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        # v54 (Bug CO): generic message — do not confirm email existence.
        # Real enumeration mitigation is the per-email REGISTER_EMAIL
        # throttle above (1 req / 10 min) which stops bulk inventory scans
        # regardless of response shape. The 400 status is preserved for
        # frontend backward compatibility.
        raise HTTPException(status_code=400, detail="Bu bilgilerle kayıt yapılamadı")

    # Decide username (explicit > derived from email)
    username = (data.username or _derive_username(data.email)).strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı adı")

    # Generate unique hotel_id
    hotel_id = await _generate_unique_hotel_id()

    tenant = Tenant(
        hotel_id=hotel_id,
        property_name=data.property_name,
        contact_email=data.email,
        contact_phone=data.phone,
        address=data.address,
        location=data.location,
    )
    tenant_dict = tenant.model_dump()
    tenant_dict['created_at'] = tenant_dict['created_at'].isoformat()
    await db.tenants.insert_one(tenant_dict)

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        username=username,
        name=data.name,
        role=UserRole.ADMIN,
        phone=data.phone,
    )
    user_dict = user.model_dump()
    user_dict['hashed_password'] = hash_password(data.password)
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    user_dict = encrypt_user_doc(user_dict)
    await db.users.insert_one(user_dict)

    return _build_token_response(user, tenant)

@router.post("/auth/register-guest", response_model=TokenResponse)
async def register_guest(data: GuestRegister, request: Request):
    # v54 (Bug CO): per-IP and per-email throttle (see register_tenant).
    from security.auth_throttle import (
        REGISTER_EMAIL,
        REGISTER_IP,
        client_ip,
        enforce,
        normalize_identity,
    )
    await enforce(REGISTER_IP, f"ip:{client_ip(request)}", "kayıt isteği")
    await enforce(REGISTER_EMAIL, f"em:{normalize_identity(data.email)}", "kayıt isteği")

    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Bu bilgilerle kayıt yapılamadı")

    user = User(
        tenant_id=None,
        email=data.email,
        name=data.name,
        role=UserRole.GUEST,
        phone=data.phone
    )
    user_dict = user.model_dump()
    user_dict['hashed_password'] = hash_password(data.password)
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    user_dict = encrypt_user_doc(user_dict)
    await db.users.insert_one(user_dict)

    prefs = NotificationPreferences(user_id=user.id)
    await db.notification_preferences.insert_one(prefs.model_dump())

    return _build_token_response(user, None)

@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request):
    """Hotel staff login via (hotel_id + username) OR legacy guest login via (email).

    Resolution order:
      1) If hotel_id + username are provided → look up tenant, then user (tenant_id+username).
      2) Else if email is provided (guest path) → look up by email.
    """
    import hashlib as _hl

    from infra.simple_cache import simple_cache as _login_cache
    from security.auth_throttle import (
        LOGIN_ACCOUNT,
        LOGIN_IP,
        client_ip,
        enforce,
        normalize_identity,
    )

    # Bug AT/AV fix — per-IP and per-account throttle on login attempts.
    # Per-IP catches credential-stuffing across many accounts; per-account
    # catches password brute-force against a single user. Successful login
    # resets the per-account counter at the bottom of this handler.
    # Architect-fix: normalize_identity (NFKC + strip + casefold) prevents
    # Unicode/whitespace bypass of per-account lockout.
    _ip = client_ip(request)
    _acct_key = (
        f"acc:hid:{normalize_identity(data.hotel_id)}|u:{normalize_identity(data.username)}"
        if data.hotel_id and data.username
        else f"acc:em:{normalize_identity(data.email)}"
    )
    await enforce(LOGIN_IP, f"ip:{_ip}", "giriş denemesi")
    await enforce(LOGIN_ACCOUNT, _acct_key, "giriş denemesi")

    # Build a stable cache key
    if data.hotel_id and data.username:
        cache_seed = f"hid:{data.hotel_id}|u:{data.username.lower()}|p:{data.password}"
        identity_label = f"hotel_id={data.hotel_id} username={data.username}"
    elif data.email:
        cache_seed = f"em:{data.email}|p:{data.password}"
        identity_label = data.email
    else:
        raise HTTPException(status_code=400, detail="Otel ID + kullanıcı adı veya e-posta gereklidir")

    cache_key = f"login:{_hl.sha256(cache_seed.encode()).hexdigest()[:24]}"
    cached = _login_cache.get(cache_key)
    if cached:
        # Verify the cached non-2FA response is still valid: if the
        # user has since enabled 2FA, the cached `access_token` must
        # NOT be honored — fall through to the full login path so the
        # caller is forced through the challenge flow.
        try:
            cached_user = cached.get("user")
            cached_uid = (
                getattr(cached_user, "id", None)
                if cached_user is not None
                else None
            )
            # v47 (Bug CD architect Round-1): cache-hit path must also honor
            # the password-change watermark. The in-memory cache is per-process
            # and `_login_cache.clear()` is best-effort (other workers keep
            # stale entries). If the cached entry was populated BEFORE the
            # current `tokens_invalid_before`, evict + fall through so bcrypt
            # is re-evaluated against the new password.
            cached_at = int(cached.get("cached_at") or 0)
            if cached_uid:
                u = await db.users.find_one(
                    {"id": cached_uid},
                    {"_id": 0, "two_factor_enabled": 1, "tokens_invalid_before": 1},
                )
                _watermark = int((u or {}).get("tokens_invalid_before") or 0)
                if u and u.get("two_factor_enabled"):
                    _login_cache.set(cache_key, None, ttl=1)  # evict
                    # fall through to full login path → challenge flow
                elif _watermark and cached_at < _watermark:
                    # Stale cache from before password change — never honor.
                    _login_cache.set(cache_key, None, ttl=1)
                    # fall through to full login path → bcrypt re-check
                else:
                    # v44 (Bug BJ): cached path must mint a FRESH token
                    # (new jti) — otherwise logout/refresh-rotation can be
                    # bypassed by re-logging in within the 5-min cache TTL.
                    # If the cache shape is unexpected (no user object), evict
                    # and fall through to the full login path. Never return
                    # the cached access_token field.
                    cached_user = cached.get("user")
                    if cached_user is None:
                        _login_cache.set(cache_key, None, ttl=1)
                        # fall through
                    else:
                        # V3: cached path must also issue a refresh token so
                        # the rotation lifecycle works identically whether
                        # the login hit the bcrypt-skipping cache or the
                        # full path. Build via the shared helper so it
                        # cannot drift from the canonical login response.
                        return _build_token_response(cached_user, cached.get("tenant"))
            else:
                # No user_id in cache → cannot verify watermark/2FA freshness.
                # Fail-closed: evict and fall through.
                _login_cache.set(cache_key, None, ttl=1)
                # fall through
        except Exception:
            # FAIL-CLOSED: if the recheck fails (DB error, etc.), do NOT
            # honor the cached token — fall through to full login path so
            # bcrypt + 2FA gate are re-evaluated against live data.
            _login_cache.set(cache_key, None, ttl=1)  # evict

    user_doc = None

    if data.hotel_id and data.username:
        # Lookup tenant by hotel_id
        tenant_doc_for_lookup = await db.tenants.find_one({"hotel_id": str(data.hotel_id).strip()})
        if not tenant_doc_for_lookup:
            await db.audit_logs.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "tenant_id": None,
                "user_email": identity_label,
                "action": "login_failed",
                "resource_type": "auth",
                "details": "Hotel ID not found",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            raise HTTPException(status_code=401, detail="Otel ID veya bilgiler hatalı")
        tid = tenant_doc_for_lookup.get("id")
        user_doc = await db.users.find_one({
            "tenant_id": tid,
            "username": data.username.strip().lower(),
        })
    elif data.email:
        user_doc = await db.users.find_one(build_user_email_query(data.email))

    if user_doc:
        user_doc.pop('_id', None)
        user_doc = decrypt_user_doc(user_doc)
        if 'id' not in user_doc:
            import uuid
            user_doc['id'] = str(uuid.uuid4())
            await db.users.update_one(
                {"tenant_id": user_doc.get("tenant_id"), "username": user_doc.get("username")} if user_doc.get("username") else build_user_email_query(data.email or ""),
                {'$set': {'id': user_doc['id']}}
            )
            invalidate_user_doc_cache(user_doc['id'])
    else:
        # Bug AI: keep ghost-user path as expensive as the real-user path
        # by running an equivalent dummy decrypt to prevent timing-based
        # email/username enumeration.
        try:
            decrypt_user_doc(_DUMMY_USER_DOC)
        except Exception:
            pass

    hashed_pwd = user_doc.get('hashed_password') or user_doc.get('password_hash') or user_doc.get('password', '') if user_doc else ''

    # Bug AI: ALWAYS run verify_password to keep bcrypt cost constant
    # (avoid `not user_doc or ...` short-circuit which would skip bcrypt
    # on the ghost-user path and leak ~250ms timing difference).
    pw_ok = verify_password(data.password, hashed_pwd or _DUMMY_PWHASH)
    if not user_doc or not pw_ok:
        await db.audit_logs.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "tenant_id": user_doc.get('tenant_id') if user_doc else None,
            "user_email": identity_label,
            "action": "login_failed",
            "resource_type": "auth",
            "details": "Invalid credentials",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=401, detail="Otel ID, kullanıcı adı veya şifre hatalı")

    user_data = {k: v for k, v in user_doc.items() if k not in ['password', 'hashed_password', 'password_hash']}
    user = User(**user_data)

    tenant = None
    if user.tenant_id:
        tenant_doc = await load_tenant_doc(user.tenant_id)
        if tenant_doc:
            if not tenant_doc.get("subscription_plan"):
                tenant_doc["subscription_plan"] = tenant_doc.get("plan") or tenant_doc.get("subscription_tier") or "core_small_hotel"
            tenant_doc["features"] = resolve_tenant_features(tenant_doc)
            tenant = Tenant(**tenant_doc)

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": user.tenant_id,
        "user_id": user.id,
        "user_email": user.email,
        "action": "login_success",
        "resource_type": "auth",
        "details": f"Login successful for {user.name}",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    # ── 2FA challenge gate ──────────────────────────────────────
    # If the user has enabled TOTP, do NOT issue a real access token
    # yet. Mint a short-lived (5 min) challenge token; the client must
    # exchange it via POST /auth/2fa/verify with a valid 6-digit code.
    if user_doc.get("two_factor_enabled"):
        import uuid as _uuid

        import jwt as _jwt

        from core.security import JWT_ALGORITHM, JWT_SECRET
        challenge_jti = str(_uuid.uuid4())
        # v47 (Bug CD): include `iat` so /auth/2fa/verify can reject
        # challenge tokens that were minted before a password change
        # (tokens_invalid_before watermark). Without iat the verify path
        # would mint a fresh access_token from a stale credential.
        _now_dt = datetime.now(UTC)
        challenge = _jwt.encode(
            {
                "user_id": user.id,
                "tenant_id": user.tenant_id,
                "purpose": "2fa_challenge",
                "jti": challenge_jti,
                "iat": int(_now_dt.timestamp()),
                "exp": _now_dt + timedelta(minutes=5),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        await db.audit_logs.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "tenant_id": user.tenant_id,
            "user_id": user.id,
            "user_email": user.email,
            "action": "login_2fa_required",
            "resource_type": "auth",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        # Do NOT cache challenge responses.
        return TokenResponse(
            access_token="",
            user=user,
            tenant=tenant,
            requires_2fa=True,
            challenge_token=challenge,
        )

    response = _build_token_response(user, tenant)

    # Usage metering
    if user.tenant_id:
        try:
            from core.metering import UsageEventType, record_usage
            await record_usage(user.tenant_id, UsageEventType.LOGIN)
        except Exception:
            pass

    # Cache the response for 5 minutes (avoids bcrypt on repeat logins).
    # v47 (Bug CD architect Round-1): record cached_at so the cache-hit
    # path can compare against `tokens_invalid_before` and refuse to honor
    # entries populated before a password change (multi-worker safe).
    _login_cache.set(cache_key, {
        "access_token": response.access_token,
        "user": response.user,
        "tenant": response.tenant,
        "cached_at": int(datetime.now(UTC).timestamp()),
    }, ttl=300)

    # Successful login → clear per-account throttle so a legitimate user
    # who mistyped recently isn't penalised after the right password lands.
    try:
        await LOGIN_ACCOUNT.reset(_acct_key)
    except Exception:
        pass

    return response


# ── 2FA verify (exchange challenge_token for real access_token) ──
class TwoFAVerifyIn(BaseModel):
    challenge_token: str
    code: str


@router.post("/auth/2fa/verify", response_model=TokenResponse)
async def verify_2fa_login(payload: TwoFAVerifyIn, request: Request):
    # Bug AT (companion) — per-IP throttle on 2FA verify. With Bug AS fix
    # each challenge_token is single-use, so the brute-force surface is
    # already (login → challenge → ONE verify); throttling here also caps
    # the rate at which an attacker can spin up fresh challenges to retry.
    from security.auth_throttle import TWOFA_VERIFY_IP, client_ip, enforce
    await enforce(TWOFA_VERIFY_IP, f"ip:{client_ip(request)}", "doğrulama denemesi")

    import jwt as _jwt

    from core.security import JWT_ALGORITHM, JWT_SECRET
    from core.twofa import (
        consume_totp_counters,
        decrypt_secret,
        verify_totp_matching_counters,
    )

    try:
        decoded = _jwt.decode(
            payload.challenge_token, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Doğrulama süresi doldu, tekrar giriş yapın")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz doğrulama belirteci")
    if decoded.get("purpose") != "2fa_challenge":
        raise HTTPException(status_code=401, detail="Yanlış belirteç türü")
    jti = decoded.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Geçersiz doğrulama belirteci")

    # F8AH P0 follow-up — per-user-id throttle MUST run BEFORE the
    # consumed_jtis insert below, otherwise over-limit attackers still
    # incur a DB write per attempt (write amplification under brute
    # force). user_id comes from the JWT-trusted challenge_token claim.
    _user_id_for_throttle = decoded.get("user_id")
    if _user_id_for_throttle:
        from security.auth_throttle import TWOFA_VERIFY_USER, enforce as _enforce_user
        await _enforce_user(
            TWOFA_VERIFY_USER,
            f"user:{_user_id_for_throttle}",
            "doğrulama denemesi",
        )

    # Bug AS (CRITICAL): Atomic single-use enforcement via DB unique index.
    # Previously we used in-memory cache + check-then-set, which had a TOCTOU
    # race window between get() and set() that allowed N concurrent verifies
    # to each succeed with the SAME challenge_token + same TOTP code,
    # producing N independent access_tokens. Replaced with insert_one against
    # a `consumed_jtis` collection (unique index on jti + TTL on expires_at),
    # which is atomic across asyncio coroutines AND multi-worker deployments.
    from pymongo.errors import DuplicateKeyError
    await _ensure_consumed_jti_index()
    try:
        await db.consumed_jtis.insert_one({
            "jti": jti,
            "consumed_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=401, detail="Doğrulama belirteci zaten kullanıldı")

    user_id = decoded.get("user_id")

    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user_doc or not user_doc.get("two_factor_enabled"):
        raise HTTPException(status_code=401, detail="2FA durumu bulunamadı")

    # v47 (Bug CD): mass-revoke watermark also applies to in-flight
    # challenge tokens — otherwise a stolen challenge could be redeemed
    # for a fresh access_token after the victim changed their password,
    # bypassing the v46 tokens_invalid_before guard. Challenge tokens
    # without `iat` (pre-v47) are treated as invalid once watermark exists.
    invalid_before = user_doc.get("tokens_invalid_before")
    if invalid_before:
        ch_iat = decoded.get("iat")
        if not ch_iat or int(ch_iat) < int(invalid_before):
            await db.audit_logs.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "tenant_id": user_doc.get("tenant_id"),
                "user_id": user_id,
                "action": "login_2fa_failed",
                "resource_type": "auth",
                "details": "challenge_stale_password_changed",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            raise HTTPException(
                status_code=401,
                detail="Şifre değişti - lütfen yeniden giriş yapın",
            )

    user_doc = decrypt_user_doc(user_doc)

    secret_enc = user_doc.get("two_factor_secret_enc", "")
    try:
        secret = decrypt_secret(secret_enc)
    except ValueError:
        raise HTTPException(status_code=500, detail="2FA gizli anahtar çözülemedi")

    code = (payload.code or "").strip()
    totp_counters = verify_totp_matching_counters(secret, code)
    matched_totp = bool(totp_counters)
    matched_backup = False
    matched_hash = None
    if not matched_totp:
        backup_hashes = user_doc.get("two_factor_backup_codes") or []
        # Identify which stored hash matches (no DB write yet).
        from core.twofa import _pwd as _bcrypt_ctx
        norm = code.upper().replace("-", "").replace(" ", "")
        for h in backup_hashes:
            try:
                if _bcrypt_ctx.verify(norm, h):
                    matched_hash = h
                    matched_backup = True
                    break
            except Exception:
                continue

    if not (matched_totp or matched_backup):
        await db.audit_logs.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "tenant_id": user_doc.get("tenant_id"),
            "user_id": user_id,
            "action": "login_2fa_failed",
            "resource_type": "auth",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=401, detail="2FA kodu hatalı")

    # Atomic single-use enforcement for backup codes:
    # use $pull keyed on the exact hash; if two requests race for the
    # same code, only one of them will modify_count==1, the other 0.
    # Bug CB (CRITICAL, v45): Same-window TOTP replay guard.
    # The challenge_token is single-use (Bug AS), but the TOTP code itself
    # remained valid for ±30s. An attacker who shoulder-surfs/peeks the
    # current 6-digit code could log in N times in that window by spinning
    # up N challenges and reusing the same code. We now atomically claim
    # the matched (user_id, counter) slot via a unique-index insert; the
    # second use of the same code returns 401.
    if matched_totp and totp_counters:
        from core.database import db as _raw_db
        try:
            # Claim ALL matching counters atomically — closes adjacent-window
            # collision (~1e-6) where the same code is valid for two slots.
            won = await consume_totp_counters(_raw_db, user_id, totp_counters)
        except Exception as exc:
            logger.error("TOTP counter consume failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="2FA doğrulama servisi geçici olarak kullanılamıyor",
            )
        if not won:
            await db.audit_logs.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "tenant_id": user_doc.get("tenant_id"),
                "user_id": user_id,
                "action": "login_2fa_failed",
                "resource_type": "auth",
                "details": "totp_replay_rejected",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            raise HTTPException(
                status_code=401, detail="Bu doğrulama kodu zaten kullanıldı"
            )

    if matched_backup and matched_hash is not None:
        pull_res = await db.users.update_one(
            {"id": user_id, "two_factor_backup_codes": matched_hash},
            {
                "$pull": {"two_factor_backup_codes": matched_hash},
                "$set": {"two_factor_last_used_at": datetime.now(UTC).isoformat()},
            },
        )
        invalidate_user_doc_cache(user_id)
        if pull_res.modified_count == 0:
            await db.audit_logs.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "tenant_id": user_doc.get("tenant_id"),
                "user_id": user_id,
                "action": "login_2fa_failed",
                "resource_type": "auth",
                "details": "backup_code_race_lost",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            raise HTTPException(status_code=401, detail="Yedek kod zaten kullanıldı")
    else:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"two_factor_last_used_at": datetime.now(UTC).isoformat()}},
        )
        invalidate_user_doc_cache(user_id)

    # jti consumption already enforced atomically at top of handler via
    # DB unique index (Bug AS fix); no further marker write needed.

    user = User(**{k: v for k, v in user_doc.items() if k not in ['password', 'hashed_password', 'password_hash']})
    tenant = None
    if user.tenant_id:
        tenant_doc = await load_tenant_doc(user.tenant_id)
        if tenant_doc:
            if not tenant_doc.get("subscription_plan"):
                tenant_doc["subscription_plan"] = tenant_doc.get("plan") or tenant_doc.get("subscription_tier") or "core_small_hotel"
            tenant_doc["features"] = resolve_tenant_features(tenant_doc)
            tenant = Tenant(**tenant_doc)

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": user.tenant_id,
        "user_id": user.id,
        "user_email": user.email,
        "action": "login_2fa_success",
        "resource_type": "auth",
        "details": "backup_code" if matched_backup else "totp",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    # V3: 2FA-verified login must also issue a refresh token so the
    # mobile rotation lifecycle works identically whether the user
    # took the 2FA path or the direct path.
    return _build_token_response(user, tenant)

_USER_RESPONSE_SAFE = set(User.model_fields.keys())

@router.get("/auth/me", response_model=User, response_model_exclude={"password"})
async def get_me(current_user: User = Depends(get_current_user)):
    # User modeli extra="allow" oldugu icin hashed_password gibi sizinti riski tasiyan
    # alanlari kasten ayikla — sadece bilinen guvenli field'lari geri don.
    safe = {k: v for k, v in current_user.model_dump().items() if k in _USER_RESPONSE_SAFE}
    return User(**safe)


class UpdateMeRequest(BaseModel):
    name: str | None = None
    phone: str | None = None


@router.put("/auth/me", response_model=User)
async def update_me(
    data: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
):
    """Allow the authenticated user to update their own name and phone."""
    update_fields: dict = {}
    if data.name is not None:
        cleaned = data.name.strip()
        if len(cleaned) < 2:
            raise HTTPException(status_code=400, detail="Ad Soyad en az 2 karakter olmalı")
        update_fields["name"] = cleaned
    if data.phone is not None:
        update_fields["phone"] = data.phone.strip() or None

    if not update_fields:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    await db.users.update_one({"id": current_user.id}, {"$set": update_fields})
    invalidate_user_doc_cache(current_user.id)

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "action": "profile_updated",
        "resource_type": "user",
        "details": ",".join(update_fields.keys()),
        "timestamp": datetime.now(UTC).isoformat(),
    })

    refreshed = await db.users.find_one({"id": current_user.id})
    refreshed.pop("_id", None)
    refreshed = decrypt_user_doc(refreshed)
    return User(**{k: v for k, v in refreshed.items() if k in User.model_fields})


@router.post("/auth/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Allow an authenticated user to change their own password."""
    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı")
    if data.new_password == data.current_password:
        raise HTTPException(status_code=400, detail="Yeni şifre eskisinden farklı olmalı")

    # v48 (Bug CE): per-user throttle on the current_password check. Without
    # this, a stolen access_token can dictionary-attack the password at
    # bcrypt-throttled speed (login throttle does not apply because the call
    # is authenticated). Allow a few attempts per 15 min for legitimate UX
    # then 429.
    from security.auth_throttle import SENSITIVE_AUTH_USER
    from security.auth_throttle import enforce as _throttle
    await _throttle(SENSITIVE_AUTH_USER, f"chgpw:{current_user.id}", "şifre değiştirme denemesi")

    user_doc = await db.users.find_one({"id": current_user.id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    user_doc.pop('_id', None)
    user_doc = decrypt_user_doc(user_doc)
    hashed_pwd = user_doc.get('hashed_password') or user_doc.get('password_hash') or user_doc.get('password', '')
    if not verify_password(data.current_password, hashed_pwd):
        await db.audit_logs.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "password_change_failed",
            "resource_type": "auth",
            "details": "Mevcut şifre hatalı",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=401, detail="Mevcut şifre hatalı")
    # v48 (Bug CE): success → reset throttle so a legitimate user who
    # mistyped recently isn't penalised after the right password lands.
    try:
        await SENSITIVE_AUTH_USER.reset(f"chgpw:{current_user.id}")
    except Exception:
        pass

    new_hash = hash_password(data.new_password)
    # v46 (Bug CC): set tokens_invalid_before watermark so all existing JWTs
    # for this user (incl. the one used to make this request) are rejected
    # by get_current_user — OWASP ASVS V3.3.1 mass-revoke on credential change.
    invalid_before_ts = int(datetime.now(UTC).timestamp()) + 1
    await db.users.update_one(
        {"id": current_user.id},
        {
            "$set": {"hashed_password": new_hash, "tokens_invalid_before": invalid_before_ts},
            "$unset": {"password_hash": "", "password": ""},
        },
    )
    invalidate_user_doc_cache(current_user.id)

    # Invalidate any cached login responses for this user (best-effort)
    try:
        from infra.simple_cache import simple_cache as _login_cache
        _login_cache.clear()
    except Exception:
        pass

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_email": getattr(current_user, "email", None),
        "action": "password_change",
        "resource_type": "auth",
        "details": "Şifre güncellendi",
        "timestamp": datetime.now(UTC).isoformat(),
    })
    return {"success": True, "message": "Şifre başarıyla güncellendi"}


def _decode_bearer_payload(request: Request) -> dict:
    """Decode the bearer token attached to the request, no exp check needed
    here (already validated upstream by get_current_user)."""
    import jwt as _jwt
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return {}
    token = auth.split(" ", 1)[1].strip()
    try:
        return _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return {}


def _enforce_refresh_invariants(user_doc: dict, payload: dict, *, kind: str) -> None:
    """Apply the same user-level invalidation guards as `get_current_user`
    before issuing a new access (and possibly refresh) token.

    Without this, a body-based refresh that intentionally sidesteps
    `Depends(get_current_user)` (so an *expired* access token can still
    rotate) would also sidestep:
      * `is_active=False` lock-outs
      * `tokens_invalid_before` mass-revocation watermark (Bug CC v46) —
        a stolen refresh token would otherwise survive a password change.

    Centralised here so Path A (refresh-token in body) and Path B
    (legacy bearer rotation) cannot drift.
    """
    # `is_active=False` → fully locked out. Treat as if the user does not
    # exist for token-issuance purposes.
    if user_doc.get("is_active") is False:
        raise HTTPException(status_code=401, detail="Hesap devre dışı")

    # Mass-revocation watermark. Tokens minted before the watermark
    # (including refresh tokens issued from the *previous* password) must
    # be rejected. Tokens lacking `iat` are treated as invalid once a
    # watermark exists (fail-closed) — matches `core.security.get_current_user`.
    invalid_before = user_doc.get("tokens_invalid_before")
    if invalid_before:
        iat = payload.get("iat")
        if not iat or int(iat) < int(invalid_before):
            raise HTTPException(
                status_code=401,
                detail="Şifre değişti - lütfen yeniden giriş yapın",
            )

    # Defence-in-depth: token's tenant_id must match the user record. A
    # forged refresh token claiming a different tenant_id is rejected.
    jwt_tenant = payload.get("tenant_id")
    doc_tenant = user_doc.get("tenant_id")
    if jwt_tenant and doc_tenant and jwt_tenant != doc_tenant:
        logger.warning(
            "[%s] tenant mismatch on refresh: user=%s jwt=%s doc=%s",
            kind, user_doc.get("id"), jwt_tenant, doc_tenant,
        )
        raise HTTPException(status_code=401, detail="Token-tenant uyuşmuyor")


@router.post("/auth/refresh-token")
async def refresh_token(request: Request, body: dict | None = Body(default=None)):
    """JWT token yenileme — V3 dual-mode endpoint.

    Path A (V3 / mobile, preferred):
        POST body { "refresh_token": "<long-lived JWT, type=refresh>" }
        Validated independently — does NOT require a still-valid access
        token. The refresh JWT's jti is rotated (old → revoked, new minted).

    Path B (legacy / web):
        POST with `Authorization: Bearer <access_token>` and no body.
        The access token must still be valid; its jti is rotated.

    Either way the response carries `access_token`, `expires_in`, and
    (Path A) a brand-new `refresh_token`. Old refresh tokens remain valid
    until natural expiry only if rotation was not attempted with them —
    once used, they're revoked and cannot be replayed.
    """
    import jwt as _jwt
    body = body or {}

    submitted_refresh: str | None = None
    if isinstance(body, dict):
        rt = body.get("refresh_token")
        if isinstance(rt, str) and rt.strip():
            submitted_refresh = rt.strip()

    user_id: str | None = None
    tenant_id: str | None = None
    user_email: str = ""
    old_jti: str | None = None
    old_exp: int | None = None
    rotation_kind: str = "access"

    if submitted_refresh:
        # ── Path A: V3 mobile refresh-token flow ──
        try:
            rt_payload = _jwt.decode(
                submitted_refresh, JWT_SECRET, algorithms=[JWT_ALGORITHM]
            )
        except _jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Refresh token expired — please login again")
        except _jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if rt_payload.get("type") != "refresh":
            # An access token sent in the refresh-token slot is rejected so
            # callers can't blur the distinction (defence in depth).
            raise HTTPException(status_code=401, detail="Wrong token type for refresh")
        user_id = rt_payload.get("user_id")
        tenant_id = rt_payload.get("tenant_id")
        old_jti = rt_payload.get("jti")
        old_exp = rt_payload.get("exp")
        rotation_kind = "refresh"
        if not user_id:
            raise HTTPException(status_code=401, detail="Malformed refresh token")
        # Resolve user (no Depends → tolerates missing/expired access token).
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=401, detail="User no longer exists")
        # Enforce the same invariants `get_current_user` would have applied,
        # so a refresh cannot bypass an `is_active=False` lock-out, a
        # `tokens_invalid_before` mass-revocation, or a tenant mismatch.
        _enforce_refresh_invariants(user_doc, rt_payload, kind="refresh")
        user_email = user_doc.get("email", "")
    else:
        # ── Path B: legacy access-token rotation ──
        # Manually decode + load user so we can produce the same audit row
        # without forcing all callers through Depends(get_current_user).
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = auth.split(" ", 1)[1].strip()
        try:
            ax_payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except _jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Access token expired — send refresh_token in body")
        except _jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid access token")
        # Reject refresh tokens sent in the bearer slot — same defence in depth.
        if ax_payload.get("type") == "refresh":
            raise HTTPException(status_code=401, detail="Refresh token cannot be used as bearer")
        user_id = ax_payload.get("user_id")
        tenant_id = ax_payload.get("tenant_id")
        old_jti = ax_payload.get("jti")
        old_exp = ax_payload.get("exp")
        if not user_id:
            raise HTTPException(status_code=401, detail="Malformed access token")
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=401, detail="User no longer exists")
        # Same invariants as Path A: a Path-B bearer rotation also bypasses
        # `Depends(get_current_user)` (we manually decode), so we need to
        # re-apply the lock-out / watermark / tenant-mismatch guards here.
        _enforce_refresh_invariants(user_doc, ax_payload, kind="access")
        user_email = user_doc.get("email", "")

    # v44 race-hardening: only the request that wins the revocation insert
    # is allowed to mint a fresh token. Concurrent refreshes with the same
    # old jti → only one rotates, the others get 401.
    if old_jti and old_exp:
        try:
            won = await revoke_jti(
                old_jti, int(old_exp),
                user_id=user_id,
                tenant_id=tenant_id,
                reason=f"{rotation_kind}_rotation",
            )
        except Exception as e:
            logger.error("refresh_token: revoke_jti raised: %s", e)
            raise HTTPException(status_code=503, detail="Token rotation unavailable, please retry")
        if not won:
            raise HTTPException(status_code=401, detail="Refresh replay rejected — please login again")

    new_access = create_token(user_id, tenant_id)
    new_refresh: str | None = None
    if rotation_kind == "refresh":
        new_refresh, _ = create_refresh_token(user_id, tenant_id)

    # Audit log
    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "user_email": user_email,
        "action": "token_refresh",
        "resource_type": "auth",
        "details": f"Token refreshed via {rotation_kind} (rotated jti={old_jti or 'legacy'})",
        "ip_address": "",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    response: dict[str, object] = {
        "access_token": new_access,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_MINUTES * 60,
    }
    if new_refresh:
        response["refresh_token"] = new_refresh
        response["refresh_expires_in"] = REFRESH_TOKEN_EXPIRATION_DAYS * 24 * 3600
    return response


@router.post("/auth/logout")
async def logout(
    request: Request,
    body: dict | None = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    """v44 (Bug BJ): server-side logout — current token jti revoke listesine
    yazılır, downstream istekler 401 alır.

    V3 (Syroce mobil): if the client also submits its refresh token in
    the body (`{"refresh_token": "<jwt>"}`), revoke that jti too so a
    stolen refresh token cannot keep the session alive after explicit
    logout. Best-effort: failures are logged but never block the access-
    token revocation that this endpoint guarantees.
    """
    import jwt as _jwt
    payload = _decode_bearer_payload(request)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        # v44 race-hardening: revoke_jti raises on non-duplicate errors.
        # Logout must NOT report success if the revocation could not be
        # persisted — otherwise the client will believe it is logged out
        # while the token still grants access.
        try:
            await revoke_jti(
                jti, int(exp),
                user_id=current_user.id,
                tenant_id=current_user.tenant_id,
                reason="logout",
            )
        except Exception as e:
            logger.error("logout: revoke_jti raised: %s", e)
            raise HTTPException(status_code=503, detail="Logout failed, please retry")

    # F8U P0 fix — mass-revoke watermark. Even when the client does NOT
    # submit its refresh_token in the body, /auth/logout MUST invalidate
    # ALL outstanding tokens for this user — otherwise a stolen refresh
    # token survives the explicit logout and can be exchanged for fresh
    # access tokens. We bump `tokens_invalid_before` to now+1s so every
    # access AND refresh token whose `iat` precedes this moment is
    # rejected by `get_current_user` (access) and `_enforce_refresh_invariants`
    # (refresh). Trade-off: this terminates the user's other live sessions
    # too — acceptable single-button-logout semantics for a staff PMS
    # (matches typical enterprise behaviour; matches threat_model.md
    # § Spoofing "enforce revocation/invalid-before semantics").
    # Fail-closed: a watermark write failure means we cannot guarantee
    # refresh-token revocation. Match the access-token revocation contract
    # above (503 on failure) so the client never sees a 2xx that doesn't
    # actually invalidate the session.
    try:
        invalid_before_ts = int(datetime.now(UTC).timestamp()) + 1
        await db.users.update_one(
            {"id": current_user.id},
            {"$set": {"tokens_invalid_before": invalid_before_ts}},
        )
        try:
            invalidate_user_doc_cache(current_user.id)
        except Exception:
            pass
    except Exception as e:
        logger.error("logout: watermark update failed: %s", e)
        raise HTTPException(status_code=503, detail="Logout failed, please retry")

    # V3: revoke the submitted refresh token if any.
    refresh_jti: str | None = None
    if isinstance(body, dict):
        rt = body.get("refresh_token")
        if isinstance(rt, str) and rt.strip():
            try:
                rt_payload = _jwt.decode(rt.strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
                # Only honour real refresh tokens; ignore anything else
                # silently so a malformed body doesn't crash logout.
                if rt_payload.get("type") == "refresh":
                    refresh_jti = rt_payload.get("jti")
                    refresh_exp = rt_payload.get("exp")
                    if refresh_jti and refresh_exp:
                        try:
                            await revoke_jti(
                                refresh_jti, int(refresh_exp),
                                user_id=current_user.id,
                                tenant_id=current_user.tenant_id,
                                reason="logout_refresh",
                            )
                        except Exception as e:
                            # Best-effort: log but don't fail logout — the
                            # access token is already revoked above.
                            logger.warning("logout: refresh revoke failed: %s", e)
            except _jwt.InvalidTokenError:
                # Submitted refresh token was not parsable — skip silently.
                pass

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "action": "logout",
        "resource_type": "auth",
        "details": (
            f"Logout (jti={jti or 'legacy'}"
            + (f", refresh_jti={refresh_jti}" if refresh_jti else "")
            + ")"
        ),
        "ip_address": "",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    return {"success": True, "message": "Çıkış yapıldı"}


@router.get("/security/summary")
@cached(ttl=120, key_prefix="security_summary")
async def get_security_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v85 DU: security özet (admin/exec)
):
    """Güvenlik özet dashboard verisi."""
    now = datetime.now(UTC)
    last_24h = (now - timedelta(hours=24)).isoformat()
    last_7d = (now - timedelta(days=7)).isoformat()

    # Failed login attempts (last 24h)
    failed_logins_24h = await db.audit_logs.count_documents({
        "tenant_id": current_user.tenant_id,
        "action": "login_failed",
        "timestamp": {"$gte": last_24h},
    })

    # Successful logins (last 24h)
    successful_logins_24h = await db.audit_logs.count_documents({
        "tenant_id": current_user.tenant_id,
        "action": {"$in": ["login", "login_success"]},
        "timestamp": {"$gte": last_24h},
    })

    # Rate limit hits (from APM)
    rate_limit_stats = {}
    try:
        if _get_rate_limit_stats:
            rate_limit_stats = _get_rate_limit_stats()
    except Exception:
        pass

    # Active sessions estimate (tokens refreshed in last 2h)
    active_sessions = await db.audit_logs.count_documents({
        "tenant_id": current_user.tenant_id,
        "action": {"$in": ["login", "login_success", "token_refresh"]},
        "timestamp": {"$gte": (now - timedelta(hours=2)).isoformat()},
    })

    # Recent security events (last 7 days)
    security_events = await db.audit_logs.find(
        {
            "tenant_id": current_user.tenant_id,
            "action": {"$in": ["login_failed", "password_change", "user_created", "user_deleted", "role_change", "token_refresh"]},
            "timestamp": {"$gte": last_7d},
        },
        {"_id": 0}
    ).sort("timestamp", -1).limit(50).to_list(50)

    # User count
    total_users = await db.users.count_documents({"tenant_id": current_user.tenant_id})

    # APM summary
    apm_summary = {}
    try:
        if _apm_store:
            apm_summary = _apm_store.get_summary(minutes=60)
    except Exception:
        pass

    return {
        "overview": {
            "failed_logins_24h": failed_logins_24h,
            "successful_logins_24h": successful_logins_24h,
            "active_sessions": active_sessions,
            "total_users": total_users,
            "rate_limit_hits": rate_limit_stats.get("total_hits", 0),
        },
        "apm": {
            "requests_per_minute": apm_summary.get("requests_per_minute", 0),
            "error_rate": apm_summary.get("error_rate_percent", 0),
            "avg_response_ms": apm_summary.get("avg_duration_ms", 0),
            "slow_requests": apm_summary.get("slow_request_count", 0),
        },
        "rate_limits": rate_limit_stats,
        "recent_events": security_events[:20],
        "timestamp": now.isoformat(),
    }

# ============= NEW USER REGISTRATION WITH EMAIL VERIFICATION =============

class EmailVerificationRequest(BaseModel):
    """E-posta doğrulama kodu talebi"""
    email: EmailStr
    name: str
    password: str
    property_name: str | None = None  # Hotel için
    phone: str | None = None
    user_type: str = "hotel"  # "hotel" veya "guest"

class VerifyCodeRequest(BaseModel):
    """Doğrulama kodu kontrolü"""
    email: EmailStr
    code: str

class ForgotPasswordRequest(BaseModel):
    """Şifre sıfırlama talebi"""
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    """Yeni şifre belirleme"""
    email: EmailStr
    code: str
    new_password: str

_REQUEST_VERIFICATION_GENERIC_RESPONSE = {
    'success': True,
    'message': 'Doğrulama kodu e-posta adresinize gönderildi',
    'expires_in_minutes': 15,
}


@router.post("/auth/request-verification")
async def request_verification_code(data: EmailVerificationRequest, request: Request):
    """E-posta doğrulama kodu gönder.

    v54 (Bug CO): The previous implementation returned a 400 'Bu e-posta
    adresi zaten kayıtlı' for existing accounts and a 200 success for new
    ones — a textbook account-enumeration oracle. It also had no rate
    limit, so the endpoint was a Resend cost-amplification / email-bomb
    primitive (one POST → one outbound mail to any attacker-supplied
    address). We now:
      * throttle per-IP (5/10min) and per-email (1/10min),
      * always return the same 200 response shape regardless of whether
        the account exists,
      * for an existing account, send a 'someone tried to register with
        your email' notice mail (best-effort, in background) instead of
        a verification code,
      * background tasks make existing/new branches indistinguishable in
        request latency.
    """
    from security.auth_throttle import (
        REGISTER_EMAIL,
        REGISTER_IP,
        client_ip,
        enforce,
        normalize_identity,
    )
    await enforce(REGISTER_IP, f"ip:{client_ip(request)}", "kayıt isteği")
    await enforce(REGISTER_EMAIL, f"em:{normalize_identity(data.email)}", "kayıt isteği")

    existing = await db.users.find_one(build_user_email_query(data.email))

    import asyncio as _asyncio
    import logging as _logging
    _bg_log = _logging.getLogger(__name__)

    async def _bg_existing_notice():
        try:
            from core.email import send_email
            from core.mailing_safe import safe_html_value
            safe_email = safe_html_value(data.email)
            html = (
                f"<p>Merhaba,</p>"
                f"<p>Hesabınızla ({safe_email}) ilişkili bir kayıt denemesi tespit ettik. "
                f"Bu işlemi siz yaptıysanız bu mesajı dikkate almayın.</p>"
                f"<p>Eğer bu siz değilseniz, hesabınızın güvenliğini gözden geçirmenizi öneririz.</p>"
                f"<p>Syroce Güvenlik</p>"
            )
            await send_email(data.email, "Hesabınız için kayıt denemesi", html)
        except Exception as e:
            _bg_log.warning("[request-verification] notice mail failed: %s", e)

    async def _bg_new_signup():
        try:
            from modules.messaging.email_service import email_service
            code = email_service.generate_verification_code()
            verification_doc = {
                'email': data.email,
                'code': code,
                'name': data.name,
                'password': hash_password(data.password),
                'property_name': data.property_name,
                'phone': data.phone,
                'user_type': data.user_type,
                'created_at': datetime.now(UTC),
                'expires_at': datetime.now(UTC) + timedelta(minutes=15),
                'verified': False,
                'attempts': 0,  # v54 (Bug CO): brute-force counter
            }
            await db.verification_codes.delete_many({'email': data.email})
            await db.verification_codes.insert_one(verification_doc)
            await email_service.send_verification_code(data.email, code, data.name)
        except Exception as e:
            _bg_log.warning("[request-verification] signup mail failed: %s", e)

    _t = _asyncio.create_task(_bg_existing_notice() if existing else _bg_new_signup())
    _FORGOT_BG_TASKS.add(_t)
    _t.add_done_callback(_FORGOT_BG_TASKS.discard)

    return _REQUEST_VERIFICATION_GENERIC_RESPONSE

@router.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email_and_register(data: VerifyCodeRequest, request: Request):
    """E-posta kodunu doğrula ve kullanıcı oluştur.

    v54 (Bug CO): added per-email sliding-window throttle (5 / 15 min)
    and an attempt counter on the verification_codes document itself.
    Without these the 6-digit code (1M space) was brute-forceable in
    ~17 min within the 15-min validity window, with zero account-side
    consequence on miss. After 5 wrong attempts the code is invalidated;
    user must request a fresh one (which re-rate-limits).
    """
    from security.auth_throttle import VERIFY_CODE_EMAIL, enforce, normalize_identity
    await enforce(VERIFY_CODE_EMAIL, f"em:{normalize_identity(data.email)}", "doğrulama denemesi")

    # Look up by email FIRST (without code) so a wrong-code attempt still
    # increments the per-doc attempt counter — otherwise an attacker's
    # wrong guesses would never touch the doc.
    pending = await db.verification_codes.find_one({'email': data.email})
    if not pending:
        raise HTTPException(status_code=400, detail="Geçersiz veya hatalı doğrulama kodu")
    if pending.get('attempts', 0) >= 5:
        await db.verification_codes.delete_one({'_id': pending['_id']})
        raise HTTPException(status_code=400, detail="Çok fazla hatalı deneme. Lütfen yeni kod isteyin")
    if pending.get('code') != data.code:
        await db.verification_codes.update_one(
            {'_id': pending['_id']},
            {'$inc': {'attempts': 1}},
        )
        raise HTTPException(status_code=400, detail="Geçersiz veya hatalı doğrulama kodu")
    verification = pending
    if not verification:
        raise HTTPException(status_code=400, detail="Geçersiz veya hatalı doğrulama kodu")

    # Kod süresi dolmuş mu kontrol et
    expires_at = verification['expires_at']
    if not expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        await db.verification_codes.delete_one({'_id': verification['_id']})
        raise HTTPException(status_code=400, detail="Doğrulama kodu süresi dolmuş. Lütfen yeni kod isteyin")

    # E-posta zaten kullanılmış mı kontrol et (tekrar)
    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kayıtlı")

    # Kullanıcı tipine göre kayıt
    if verification['user_type'] == 'hotel':
        # Hotel admin kullanıcısı — must have hotel_id + username for new login flow
        new_hotel_id = await _generate_unique_hotel_id()
        new_username = (verification.get('username') or _derive_username(data.email)).strip().lower()
        tenant = Tenant(
            hotel_id=new_hotel_id,
            name=verification['name'],
            property_name=verification.get('property_name', f"{verification['name']} Hotel"),
            email=data.email,
            phone=verification.get('phone'),
            address='',
            location='',
            description=''
        )
        tenant_dict = tenant.model_dump()
        tenant_dict['created_at'] = tenant_dict['created_at'].isoformat()
        await db.tenants.insert_one(tenant_dict)

        user = User(
            tenant_id=tenant.id,
            email=data.email,
            username=new_username,
            name=verification['name'],
            role=UserRole.ADMIN,
            phone=verification.get('phone'),
            is_active=True
        )
        user_dict = user.model_dump()
        user_dict['hashed_password'] = verification['password']
        user_dict['created_at'] = user_dict['created_at'].isoformat()
        user_dict['email_verified'] = True
        user_dict['email_verified_at'] = datetime.now(UTC).isoformat()
        user_dict = encrypt_user_doc(user_dict)
        await db.users.insert_one(user_dict)

        # Doğrulama kaydını sil
        await db.verification_codes.delete_one({'_id': verification['_id']})

        # Hoşgeldin e-postası gönder
        from modules.messaging.email_service import email_service
        await email_service.send_welcome_email(data.email, verification['name'])

        return _build_token_response(user, tenant)

    else:
        # Guest kullanıcısı
        user = User(
            tenant_id=None,
            email=data.email,
            name=verification['name'],
            role=UserRole.GUEST,
            phone=verification.get('phone'),
            is_active=True
        )
        user_dict = user.model_dump()
        user_dict['hashed_password'] = verification['password']
        user_dict['created_at'] = user_dict['created_at'].isoformat()
        user_dict['email_verified'] = True
        user_dict['email_verified_at'] = datetime.now(UTC).isoformat()
        user_dict = encrypt_user_doc(user_dict)
        await db.users.insert_one(user_dict)

        prefs = NotificationPreferences(user_id=user.id)
        await db.notification_preferences.insert_one(prefs.model_dump())

        # Doğrulama kaydını sil
        await db.verification_codes.delete_one({'_id': verification['_id']})

        # Hoşgeldin e-postası gönder
        from modules.messaging.email_service import email_service
        await email_service.send_welcome_email(data.email, verification['name'])

        return _build_token_response(user, None)

_FORGOT_GENERIC_RESPONSE = {
    'success': True,
    'message': 'Eğer bu e-posta kayıtlıysa, şifre sıfırlama bağlantısı gönderildi',
    'expires_in_minutes': 30,
}

# Strong references to in-flight forgot-password background tasks
# (asyncio holds only weak refs; without this set the GC may cancel
# tasks mid-flight and lose token persistence / email delivery).
_FORGOT_BG_TASKS: set = set()


@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, request: Request):
    """Şifre sıfırlama kodu gönder.

    Returns an identical response shape regardless of whether the email exists,
    to prevent account-enumeration attacks. Audit log records the attempt.
    """
    # Bug AU fix — per-email and per-IP throttle to block email-bomb /
    # Resend-cost amplification on a target inbox. 3 emails / 10 minutes
    # per address is more than enough for a real user, far too few for abuse.
    from security.auth_throttle import (
        FORGOT_PW_EMAIL,
        FORGOT_PW_IP,
        client_ip,
        enforce,
        normalize_identity,
    )
    await enforce(FORGOT_PW_IP, f"ip:{client_ip(request)}", "sıfırlama isteği")
    await enforce(FORGOT_PW_EMAIL, f"em:{normalize_identity(data.email)}", "sıfırlama isteği")

    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "user_email": data.email,
        "action": "password_reset_requested",
        "resource_type": "auth",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    user = await db.users.find_one(build_user_email_query(data.email))

    # Bug AK: ALL post-lookup work (4 DB writes + Resend HTTP call) happens
    # in a background task so that existing-account and not-found branches
    # return in identical time. Previously the existing-account branch was
    # ~800ms slower, giving an account-enumeration timing oracle.
    if user:
        import logging as _logging
        _bg_logger = _logging.getLogger(__name__)

        async def _bg_reset():
            try:
                import secrets as _secrets

                from core.email import _frontend_base_url, render_password_reset_email, send_email
                from modules.messaging.email_service import email_service

                code = email_service.generate_verification_code()
                token = _secrets.token_urlsafe(32)
                await db.password_reset_codes.delete_many({'email': data.email})
                await db.password_reset_codes.insert_one({
                    'email': data.email,
                    'code': code,
                    'token': token,
                    'created_at': datetime.now(UTC),
                    'expires_at': datetime.now(UTC) + timedelta(minutes=30),
                    'used': False,
                })
                reset_link = f"{_frontend_base_url()}/auth/reset-password?token={token}"
                subject, html = render_password_reset_email(
                    name=user.get('name'),
                    reset_link=reset_link,
                    code=code,
                    expires_in_minutes=30,
                )
                send_result = await send_email(data.email, subject, html)
                if not send_result.get("sent"):
                    try:
                        await email_service.send_password_reset_code(data.email, code, user.get('name'))
                    except Exception:
                        pass
            except Exception as e:
                _bg_logger.warning("[forgot-password] background reset failed: %s", e)

        # Track tasks in a module-level set so they aren't garbage-collected
        # mid-flight and can be observed/cancelled at shutdown if needed.
        import asyncio as _asyncio
        _t = _asyncio.create_task(_bg_reset())
        _FORGOT_BG_TASKS.add(_t)
        _t.add_done_callback(_FORGOT_BG_TASKS.discard)

    # Use the exact same response shape regardless of whether the user
    # exists, to prevent account enumeration via response differences.
    return _FORGOT_GENERIC_RESPONSE


@router.post("/auth/reset-password-by-token")
async def reset_password_by_token(payload: dict, request: Request):
    """Reset a password using the token embedded in the email link."""
    # Bug AX fix — per-IP throttle on reset-token submissions to block
    # token brute-force. Legit users hit this exactly once per email link.
    from security.auth_throttle import RESET_TOKEN_IP, client_ip, enforce
    await enforce(RESET_TOKEN_IP, f"ip:{client_ip(request)}", "şifre sıfırlama denemesi")

    token = (payload.get("token") or "").strip()
    new_password = payload.get("new_password") or ""
    if not token:
        raise HTTPException(status_code=400, detail="Geçersiz bağlantı")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    reset = await db.password_reset_codes.find_one({"token": token, "used": False})
    if not reset:
        raise HTTPException(status_code=400, detail="Bağlantı geçersiz veya kullanılmış")

    expires_at = reset['expires_at']
    if not getattr(expires_at, 'tzinfo', None):
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        await db.password_reset_codes.delete_one({'_id': reset['_id']})
        raise HTTPException(status_code=400, detail="Bağlantının süresi dolmuş. Lütfen yeniden talep edin.")

    email = reset.get('email')
    user = await db.users.find_one(build_user_email_query(email))
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    new_hash = hash_password(new_password)
    # v46 (Bug CC): mass-revoke parallel sessions on password reset.
    invalid_before_ts = int(datetime.now(UTC).timestamp()) + 1
    await db.users.update_one(
        build_user_email_query(email),
        {"$set": {
            "hashed_password": new_hash,
            "password_reset_at": datetime.now(UTC).isoformat(),
            "tokens_invalid_before": invalid_before_ts,
        }},
    )
    invalidate_user_doc_cache(user.get('id'))

    # Invalidate cached login responses
    try:
        from infra.simple_cache import simple_cache as _login_cache
        for k in list(_login_cache._cache.keys()):
            if k.startswith("login:"):
                _login_cache.delete(k)
    except Exception:
        pass

    await db.password_reset_codes.update_one(
        {"_id": reset['_id']},
        {"$set": {"used": True, "used_at": datetime.now(UTC)}},
    )
    return {"success": True, "message": "Şifreniz başarıyla güncellendi."}

@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordRequest, request: Request):
    """Şifre sıfırlama kodunu doğrula ve yeni şifre belirle"""
    # Task-170 (Bug AY) — apply per-IP and per-email throttles before any DB
    # work.  The 6-digit numeric code has only 900 000 possibilities; without
    # these guards an attacker can sweep the full space within the 30-minute
    # expiry window using parallel requests.
    from security.auth_throttle import (
        RESET_CODE_EMAIL,
        RESET_CODE_IP,
        client_ip,
        enforce,
        normalize_identity,
    )
    await enforce(RESET_CODE_IP, f"ip:{client_ip(request)}", "sıfırlama denemesi")
    await enforce(RESET_CODE_EMAIL, f"rset:{normalize_identity(data.email)}", "sıfırlama denemesi")

    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    # Task-170 (Bug AY) — look up by email only (NOT by code) so that wrong
    # guesses can be counted against the stored record.  Looking up by code
    # directly would return no-match on wrong guesses and never increment the
    # counter, leaving a gap for multi-IP distributed brute-force.
    # Sort by created_at descending so that in the rare concurrent race where
    # multiple un-used reset records exist for the same email (e.g. user hit
    # forgot-password twice in quick succession), we always operate on the
    # most recently issued code — matching what was sent in the last email.
    _MAX_RESET_ATTEMPTS = 5
    reset = await db.password_reset_codes.find_one(
        {'email': data.email, 'used': False},
        sort=[('created_at', -1)],
    )

    if not reset:
        raise HTTPException(status_code=400, detail="Geçersiz veya kullanılmış sıfırlama kodu")

    # Kod süresi dolmuş mu kontrol et
    expires_at = reset['expires_at']
    if not expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        await db.password_reset_codes.delete_one({'_id': reset['_id']})
        raise HTTPException(status_code=400, detail="Sıfırlama kodu süresi dolmuş. Lütfen yeni kod isteyin")

    # Task-170 (Bug AY) — per-record attempt counter.  After _MAX_RESET_ATTEMPTS
    # wrong guesses the record is marked used so it cannot be retried even from
    # a fresh IP that has not yet hit the sliding-window throttle above.
    failed_attempts = reset.get('failed_attempts', 0)
    if failed_attempts >= _MAX_RESET_ATTEMPTS:
        await db.password_reset_codes.update_one(
            {'_id': reset['_id']},
            {'$set': {'used': True, 'used_at': datetime.now(UTC)}}
        )
        raise HTTPException(
            status_code=400,
            detail="Çok fazla hatalı deneme. Lütfen yeni sıfırlama kodu isteyin."
        )

    # Constant-time comparison to avoid timing oracle on the code value.
    import secrets as _secrets_mod
    if not _secrets_mod.compare_digest(str(reset.get('code', '')), str(data.code)):
        new_count = failed_attempts + 1
        if new_count >= _MAX_RESET_ATTEMPTS:
            await db.password_reset_codes.update_one(
                {'_id': reset['_id']},
                {'$set': {'used': True, 'used_at': datetime.now(UTC), 'failed_attempts': new_count}}
            )
            raise HTTPException(
                status_code=400,
                detail="Çok fazla hatalı deneme. Lütfen yeni sıfırlama kodu isteyin."
            )
        await db.password_reset_codes.update_one(
            {'_id': reset['_id']},
            {'$inc': {'failed_attempts': 1}}
        )
        raise HTTPException(status_code=400, detail="Geçersiz veya kullanılmış sıfırlama kodu")

    # Kullanıcıyı bul
    user = await db.users.find_one(build_user_email_query(data.email))
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    # Şifreyi güncelle
    new_hashed_password = hash_password(data.new_password)
    # v46 (Bug CC): mass-revoke parallel sessions on password reset (code path).
    invalid_before_ts = int(datetime.now(UTC).timestamp()) + 1
    await db.users.update_one(
        build_user_email_query(data.email),
        {
            '$set': {
                'hashed_password': new_hashed_password,
                'password_reset_at': datetime.now(UTC).isoformat(),
                'tokens_invalid_before': invalid_before_ts,
            }
        }
    )
    invalidate_user_doc_cache(user.get('id'))

    # Invalidate login cache for this user
    from infra.simple_cache import simple_cache as _login_cache
    _login_cache.cleanup_expired()
    for k in list(_login_cache._cache.keys()):
        if k.startswith("login:"):
            _login_cache.delete(k)

    # Kodu kullanıldı olarak işaretle
    await db.password_reset_codes.update_one(
        {'_id': reset['_id']},
        {'$set': {'used': True, 'used_at': datetime.now(UTC)}}
    )

    return {
        'success': True,
        'message': 'Şifreniz başarıyla güncellendi. Şimdi yeni şifrenizle giriş yapabilirsiniz'
    }

