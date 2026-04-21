"""
Auth Router - Authentication, Registration, Email Verification, Password Reset
Extracted from server.py for modularity.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr

from core.database import db as _tenant_db  # noqa: F401
from core.helpers import load_tenant_doc, resolve_tenant_features
from core.security import (
    JWT_EXPIRATION_HOURS,
    create_token,
    get_current_user,
    hash_password,
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

@router.post("/setup/make-super-admin")
async def setup_make_super_admin(request: MakeSuperAdminRequest):
    """One-time setup: Make any user super_admin

    ONLY USE FOR INITIAL SETUP!
    Default password: SYROCE_SUPER_SETUP_2024
    """
    # Security check
    if request.setup_password != "SYROCE_SUPER_SETUP_2024":
        raise HTTPException(status_code=403, detail="Invalid setup password")

    # Update ALL users with this email to super_admin (all tenants)
    result = await db.users.update_many(
        build_user_email_query(request.email),
        {"$set": {"role": "super_admin"}}
    )

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
    """Make YOURSELF super_admin (requires login)

    ONLY USE FOR INITIAL SETUP!
    Safer than email-based because you must be logged in.
    """
    # Security check
    if setup_password != "SYROCE_SUPER_SETUP_2024":
        raise HTTPException(status_code=403, detail="Invalid setup password")

    # Update current logged-in user to super_admin
    result = await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"role": "super_admin"}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Role güncellenemedi veya zaten super_admin")

    return {
        "success": True,
        "message": "Artık super_admin'siniz! Lütfen logout yapıp tekrar giriş yapın.",
        "email": current_user.email,
        "user_id": current_user.id
    }


@router.get("/admin/quick-super-admin")
async def quick_make_super_admin(
    email: str,
    secret: str = "QUICK_SUPER_2024"
):
    """Quick way to make user super_admin via browser URL

    Usage: /api/admin/quick-super-admin?email=user@example.com&secret=QUICK_SUPER_2024
    """
    if secret != "QUICK_SUPER_2024":
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Try exact match first
    result = await db.users.update_many(
        build_user_email_query(email),
        {"$set": {"role": "super_admin"}}
    )

    if result.matched_count == 0:
        # Try case-insensitive (only for plaintext emails)
        result = await db.users.update_many(
            {"email": {"$regex": f"^{email}$", "$options": "i"}},
            {"$set": {"role": "super_admin"}}
        )

    return {
        "success": True,
        "updated": result.modified_count,
        "matched": result.matched_count,
        "email": email,
        "message": f"Updated {result.modified_count} user(s) to super_admin. Logout and login to see changes."
    }


@router.get("/admin/list-all-users-debug")
async def list_all_users_for_debug(secret: str = "DEBUG_2024"):
    """List all users in database (for debugging)

    Usage: /api/admin/list-all-users-debug?secret=DEBUG_2024
    """
    if secret != "DEBUG_2024":
        raise HTTPException(status_code=403, detail="Invalid secret")

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


@router.post("/auth/register", response_model=TokenResponse)
async def register_tenant(data: TenantRegister):
    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

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

    token = create_token(user.id, tenant.id)
    return TokenResponse(access_token=token, user=user, tenant=tenant)

@router.post("/auth/register-guest", response_model=TokenResponse)
async def register_guest(data: GuestRegister):
    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

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

    token = create_token(user.id, None)
    return TokenResponse(access_token=token, user=user, tenant=None)

@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    """Hotel staff login via (hotel_id + username) OR legacy guest login via (email).

    Resolution order:
      1) If hotel_id + username are provided → look up tenant, then user (tenant_id+username).
      2) Else if email is provided (guest path) → look up by email.
    """
    import hashlib as _hl

    from infra.simple_cache import simple_cache as _login_cache

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
            if cached_uid:
                u = await db.users.find_one(
                    {"id": cached_uid},
                    {"_id": 0, "two_factor_enabled": 1},
                )
                if u and u.get("two_factor_enabled"):
                    _login_cache.set(cache_key, None, ttl=1)  # evict
                    # fall through to full login path → challenge flow
                else:
                    return TokenResponse(**cached)
            else:
                return TokenResponse(**cached)
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

    hashed_pwd = user_doc.get('hashed_password') or user_doc.get('password_hash') or user_doc.get('password', '') if user_doc else ''

    if not user_doc or not verify_password(data.password, hashed_pwd):
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
        challenge = _jwt.encode(
            {
                "user_id": user.id,
                "tenant_id": user.tenant_id,
                "purpose": "2fa_challenge",
                "jti": challenge_jti,
                "exp": datetime.now(UTC) + timedelta(minutes=5),
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

    token = create_token(user.id, user.tenant_id)
    response = TokenResponse(access_token=token, user=user, tenant=tenant)

    # Usage metering
    if user.tenant_id:
        try:
            from core.metering import UsageEventType, record_usage
            await record_usage(user.tenant_id, UsageEventType.LOGIN)
        except Exception:
            pass

    # Cache the response for 5 minutes (avoids bcrypt on repeat logins)
    _login_cache.set(cache_key, {
        "access_token": response.access_token,
        "user": response.user,
        "tenant": response.tenant,
    }, ttl=300)

    return response


# ── 2FA verify (exchange challenge_token for real access_token) ──
class TwoFAVerifyIn(BaseModel):
    challenge_token: str
    code: str


@router.post("/auth/2fa/verify", response_model=TokenResponse)
async def verify_2fa_login(payload: TwoFAVerifyIn):
    import jwt as _jwt

    from core.security import JWT_ALGORITHM, JWT_SECRET
    from core.twofa import (
        decrypt_secret,
        verify_totp,
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
    # One-time use: refuse if this jti has already been consumed.
    from infra.simple_cache import simple_cache as _consumed_cache
    consumed_key = f"2fa_jti_consumed:{jti}"
    if _consumed_cache.get(consumed_key):
        raise HTTPException(status_code=401, detail="Doğrulama belirteci zaten kullanıldı")
    user_id = decoded.get("user_id")

    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user_doc or not user_doc.get("two_factor_enabled"):
        raise HTTPException(status_code=401, detail="2FA durumu bulunamadı")
    user_doc = decrypt_user_doc(user_doc)

    secret_enc = user_doc.get("two_factor_secret_enc", "")
    try:
        secret = decrypt_secret(secret_enc)
    except ValueError:
        raise HTTPException(status_code=500, detail="2FA gizli anahtar çözülemedi")

    code = (payload.code or "").strip()
    matched_totp = verify_totp(secret, code)
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
    if matched_backup and matched_hash is not None:
        pull_res = await db.users.update_one(
            {"id": user_id, "two_factor_backup_codes": matched_hash},
            {
                "$pull": {"two_factor_backup_codes": matched_hash},
                "$set": {"two_factor_last_used_at": datetime.now(UTC).isoformat()},
            },
        )
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

    # Mark the challenge jti as consumed (TTL = remaining token lifetime).
    _consumed_cache.set(consumed_key, True, ttl=600)

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

    token = create_token(user.id, user.tenant_id)
    return TokenResponse(access_token=token, user=user, tenant=tenant)

@router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


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

    new_hash = hash_password(data.new_password)
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"hashed_password": new_hash}, "$unset": {"password_hash": "", "password": ""}},
    )

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


@router.post("/auth/refresh-token")
async def refresh_token(current_user: User = Depends(get_current_user)):
    """JWT token yenileme - mevcut geçerli token ile yeni token al."""
    new_token = create_token(current_user.id, current_user.tenant_id)

    # Audit log
    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "action": "token_refresh",
        "resource_type": "auth",
        "details": "Token refreshed",
        "ip_address": "",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_HOURS * 3600,
    }


@router.get("/security/summary")
@cached(ttl=120, key_prefix="security_summary")
async def get_security_summary(current_user: User = Depends(get_current_user)):
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

@router.post("/auth/request-verification")
async def request_verification_code(data: EmailVerificationRequest):
    """E-posta doğrulama kodu gönder"""
    # E-posta daha önce kullanılmış mı kontrol et
    existing = await db.users.find_one(build_user_email_query(data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kayıtlı")

    # Doğrulama kodu oluştur
    from modules.messaging.email_service import email_service
    code = email_service.generate_verification_code()

    # Kodu veritabanına kaydet
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
        'verified': False
    }

    # Eski kodları sil
    await db.verification_codes.delete_many({'email': data.email})

    # Yeni kodu kaydet
    await db.verification_codes.insert_one(verification_doc)

    # E-posta gönder (mock)
    await email_service.send_verification_code(data.email, code, data.name)

    return {
        'success': True,
        'message': 'Doğrulama kodu e-posta adresinize gönderildi',
        'expires_in_minutes': 15
    }

@router.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email_and_register(data: VerifyCodeRequest):
    """E-posta kodunu doğrula ve kullanıcı oluştur"""
    # Doğrulama kodunu bul
    verification = await db.verification_codes.find_one({
        'email': data.email,
        'code': data.code
    })

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

        token = create_token(user.id, tenant.id)
        return TokenResponse(access_token=token, user=user, tenant=tenant)

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

        token = create_token(user.id, None)
        return TokenResponse(access_token=token, user=user, tenant=None)

_FORGOT_GENERIC_RESPONSE = {
    'success': True,
    'message': 'Eğer bu e-posta kayıtlıysa, şifre sıfırlama bağlantısı gönderildi',
    'expires_in_minutes': 30,
}


@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Şifre sıfırlama kodu gönder.

    Returns an identical response shape regardless of whether the email exists,
    to prevent account-enumeration attacks. Audit log records the attempt.
    """
    await db.audit_logs.insert_one({
        "id": str(__import__('uuid').uuid4()),
        "user_email": data.email,
        "action": "password_reset_requested",
        "resource_type": "auth",
        "timestamp": datetime.now(UTC).isoformat(),
    })

    user = await db.users.find_one(build_user_email_query(data.email))
    if not user:
        return _FORGOT_GENERIC_RESPONSE

    # Sıfırlama kodu oluştur
    from modules.messaging.email_service import email_service
    code = email_service.generate_verification_code()

    # Kodu veritabanına kaydet
    reset_doc = {
        'email': data.email,
        'code': code,
        'created_at': datetime.now(UTC),
        'expires_at': datetime.now(UTC) + timedelta(minutes=15),
        'used': False
    }

    # Eski kodları sil
    await db.password_reset_codes.delete_many({'email': data.email})

    # Yeni kodu kaydet
    await db.password_reset_codes.insert_one(reset_doc)

    # Generate a token for the link-based reset flow as well.
    import secrets as _secrets
    token = _secrets.token_urlsafe(32)
    await db.password_reset_codes.update_one(
        {"_id": (await db.password_reset_codes.find_one({"email": data.email, "code": code}))['_id']},
        {"$set": {"token": token, "expires_at": datetime.now(UTC) + timedelta(minutes=30)}},
    )

    # Build reset link + send via Resend (falls back to console if no API key).
    from core.email import _frontend_base_url, render_password_reset_email, send_email

    reset_link = f"{_frontend_base_url()}/auth/reset-password?token={token}"
    subject, html = render_password_reset_email(
        name=user.get('name'),
        reset_link=reset_link,
        code=code,
        expires_in_minutes=30,
    )
    send_result = await send_email(data.email, subject, html)

    # Best-effort fallback: if Resend not configured, also call legacy mock.
    if not send_result.get("sent"):
        try:
            await email_service.send_password_reset_code(data.email, code, user.get('name'))
        except Exception:
            pass

    # Use the exact same response shape as the not-found branch to prevent
    # account enumeration via response differences.
    return _FORGOT_GENERIC_RESPONSE


@router.post("/auth/reset-password-by-token")
async def reset_password_by_token(payload: dict):
    """Reset a password using the token embedded in the email link."""
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
    await db.users.update_one(
        build_user_email_query(email),
        {"$set": {"hashed_password": new_hash, "password_reset_at": datetime.now(UTC).isoformat()}},
    )

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
async def reset_password(data: ResetPasswordRequest):
    """Şifre sıfırlama kodunu doğrula ve yeni şifre belirle"""
    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    # Sıfırlama kodunu bul
    reset = await db.password_reset_codes.find_one({
        'email': data.email,
        'code': data.code,
        'used': False
    })

    if not reset:
        raise HTTPException(status_code=400, detail="Geçersiz veya kullanılmış sıfırlama kodu")

    # Kod süresi dolmuş mu kontrol et
    expires_at = reset['expires_at']
    if not expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        await db.password_reset_codes.delete_one({'_id': reset['_id']})
        raise HTTPException(status_code=400, detail="Sıfırlama kodu süresi dolmuş. Lütfen yeni kod isteyin")

    # Kullanıcıyı bul
    user = await db.users.find_one(build_user_email_query(data.email))
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    # Şifreyi güncelle
    new_hashed_password = hash_password(data.new_password)
    await db.users.update_one(
        build_user_email_query(data.email),
        {
            '$set': {
                'hashed_password': new_hashed_password,
                'password_reset_at': datetime.now(UTC).isoformat()
            }
        }
    )

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

