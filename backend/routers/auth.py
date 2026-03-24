"""
Auth Router - Authentication, Registration, Email Verification, Password Reset
Extracted from server.py for modularity.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr

from core.database import db
from core.security import (
    get_current_user, hash_password, verify_password,
    create_token, JWT_EXPIRATION_HOURS,
)
from core.helpers import load_tenant_doc, resolve_tenant_features
from models.enums import UserRole
from models.schemas import (
    User, Tenant, TenantRegister, GuestRegister, UserLogin,
    TokenResponse, NotificationPreferences,
)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

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
    Default password: EMERGENT_SUPER_SETUP_2024
    """
    # Security check
    if request.setup_password != "EMERGENT_SUPER_SETUP_2024":
        raise HTTPException(status_code=403, detail="Invalid setup password")
    
    # Update ALL users with this email to super_admin (all tenants)
    result = await db.users.update_many(
        {"email": request.email},
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
    if setup_password != "EMERGENT_SUPER_SETUP_2024":
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
        {"email": email},
        {"$set": {"role": "super_admin"}}
    )
    
    if result.matched_count == 0:
        # Try case-insensitive
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


@router.post("/auth/register", response_model=TokenResponse)
async def register_tenant(data: TenantRegister):
    existing = await db.users.find_one({'email': data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    tenant = Tenant(
        name=data.name,
        property_name=data.property_name,
        email=data.email,
        phone=data.phone,
        address=data.address,
        location=data.location,
        description=data.description
    )
    tenant_dict = tenant.model_dump()
    tenant_dict['created_at'] = tenant_dict['created_at'].isoformat()
    await db.tenants.insert_one(tenant_dict)
    
    user = User(
        tenant_id=tenant.id,
        email=data.email,
        name=data.name,
        role=UserRole.ADMIN,
        phone=data.phone
    )
    user_dict = user.model_dump()
    user_dict['hashed_password'] = hash_password(data.password)
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    await db.users.insert_one(user_dict)
    
    token = create_token(user.id, tenant.id)
    return TokenResponse(access_token=token, user=user, tenant=tenant)

@router.post("/auth/register-guest", response_model=TokenResponse)
async def register_guest(data: GuestRegister):
    existing = await db.users.find_one({'email': data.email})
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
    await db.users.insert_one(user_dict)
    
    prefs = NotificationPreferences(user_id=user.id)
    await db.notification_preferences.insert_one(prefs.model_dump())
    
    token = create_token(user.id, None)
    return TokenResponse(access_token=token, user=user, tenant=None)

@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    import hashlib as _hl
    from infra.simple_cache import simple_cache as _login_cache

    cache_key = f"login:{_hl.sha256(f'{data.email}:{data.password}'.encode()).hexdigest()[:24]}"

    # --- Check session cache first (skip bcrypt if cached) ---
    cached = _login_cache.get(cache_key)
    if cached:
        return TokenResponse(**cached)

    user_doc = await db.users.find_one({'email': data.email})
    if user_doc:
        user_doc.pop('_id', None)
        if 'id' not in user_doc:
            import uuid
            user_doc['id'] = str(uuid.uuid4())
            await db.users.update_one(
                {'email': data.email},
                {'$set': {'id': user_doc['id']}}
            )

    hashed_pwd = user_doc.get('hashed_password') or user_doc.get('password_hash') or user_doc.get('password', '') if user_doc else ''

    if not user_doc or not verify_password(data.password, hashed_pwd):
        await db.audit_logs.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "tenant_id": user_doc.get('tenant_id') if user_doc else None,
            "user_email": data.email,
            "action": "login_failed",
            "resource_type": "auth",
            "details": "Invalid credentials",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise HTTPException(status_code=401, detail="Invalid credentials")

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    token = create_token(user.id, user.tenant_id)
    response = TokenResponse(access_token=token, user=user, tenant=tenant)

    # Usage metering
    if user.tenant_id:
        try:
            from core.metering import record_usage, UsageEventType
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

@router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_HOURS * 3600,
    }


@router.get("/security/summary")
async def get_security_summary(current_user: User = Depends(get_current_user)):
    """Güvenlik özet dashboard verisi."""
    now = datetime.now(timezone.utc)
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
    property_name: Optional[str] = None  # Hotel için
    phone: Optional[str] = None
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
    existing = await db.users.find_one({'email': data.email})
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
        'created_at': datetime.now(timezone.utc),
        'expires_at': datetime.now(timezone.utc) + timedelta(minutes=15),
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
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await db.verification_codes.delete_one({'_id': verification['_id']})
        raise HTTPException(status_code=400, detail="Doğrulama kodu süresi dolmuş. Lütfen yeni kod isteyin")
    
    # E-posta zaten kullanılmış mı kontrol et (tekrar)
    existing = await db.users.find_one({'email': data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kayıtlı")
    
    # Kullanıcı tipine göre kayıt
    if verification['user_type'] == 'hotel':
        # Hotel admin kullanıcısı
        tenant = Tenant(
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
            name=verification['name'],
            role=UserRole.ADMIN,
            phone=verification.get('phone'),
            is_active=True
        )
        user_dict = user.model_dump()
        user_dict['hashed_password'] = verification['password']
        user_dict['created_at'] = user_dict['created_at'].isoformat()
        user_dict['email_verified'] = True
        user_dict['email_verified_at'] = datetime.now(timezone.utc).isoformat()
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
        user_dict['email_verified_at'] = datetime.now(timezone.utc).isoformat()
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

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Şifre sıfırlama kodu gönder"""
    # Kullanıcı var mı kontrol et
    user = await db.users.find_one({'email': data.email})
    if not user:
        # Güvenlik için başarılı mesajı döndür (e-posta enumeration saldırısını önle)
        return {
            'success': True,
            'message': 'Eğer bu e-posta kayıtlıysa, şifre sıfırlama kodu gönderildi'
        }
    
    # Sıfırlama kodu oluştur
    from modules.messaging.email_service import email_service
    code = email_service.generate_verification_code()
    
    # Kodu veritabanına kaydet
    reset_doc = {
        'email': data.email,
        'code': code,
        'created_at': datetime.now(timezone.utc),
        'expires_at': datetime.now(timezone.utc) + timedelta(minutes=15),
        'used': False
    }
    
    # Eski kodları sil
    await db.password_reset_codes.delete_many({'email': data.email})
    
    # Yeni kodu kaydet
    await db.password_reset_codes.insert_one(reset_doc)
    
    # E-posta gönder (mock)
    await email_service.send_password_reset_code(data.email, code, user.get('name'))
    
    return {
        'success': True,
        'message': 'Eğer bu e-posta kayıtlıysa, şifre sıfırlama kodu gönderildi',
        'expires_in_minutes': 15
    }

@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """Şifre sıfırlama kodunu doğrula ve yeni şifre belirle"""
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
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await db.password_reset_codes.delete_one({'_id': reset['_id']})
        raise HTTPException(status_code=400, detail="Sıfırlama kodu süresi dolmuş. Lütfen yeni kod isteyin")
    
    # Kullanıcıyı bul
    user = await db.users.find_one({'email': data.email})
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Şifreyi güncelle
    new_hashed_password = hash_password(data.new_password)
    await db.users.update_one(
        {'email': data.email},
        {
            '$set': {
                'hashed_password': new_hashed_password,
                'password_reset_at': datetime.now(timezone.utc).isoformat()
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
        {'$set': {'used': True, 'used_at': datetime.now(timezone.utc)}}
    )
    
    return {
        'success': True,
        'message': 'Şifreniz başarıyla güncellendi. Şimdi yeni şifrenizle giriş yapabilirsiniz'
    }

