"""Authentication & authorization utilities"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from _pwd import BcryptContext
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import re
import logging

logger = logging.getLogger("quickid.auth")

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    # v107 (Bug DAG, architect P0): hardcoded "quickid-fallback-CHANGE-ME-IN-PRODUCTION"
    # was a known-string secret — anyone could forge admin JWT in production if
    # JWT_SECRET was accidentally unset. Now: opt-in fail-closed for prod,
    # random per-process for dev (matches backend/core/security.py pattern).
    if os.environ.get("STRICT_JWT_SECRET") == "1" or os.environ.get("ENV", "").lower() == "production":
        raise RuntimeError("JWT_SECRET environment variable is required in production (STRICT_JWT_SECRET=1 or ENV=production set).")
    import secrets as _secrets
    JWT_SECRET = _secrets.token_urlsafe(64)
    logger.warning("⚠️ JWT_SECRET unset; using random per-process secret (DEV ONLY — tokens invalid on restart, multi-worker inconsistent).")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))

# Service-to-service key (Syroce PMS backend -> Quick-ID)
QUICKID_SERVICE_KEY = os.environ.get("QUICKID_SERVICE_KEY", "")

# ===== Password Policy =====
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
ACCOUNT_LOCKOUT_THRESHOLD = 5      # Başarısız deneme sayısı
ACCOUNT_LOCKOUT_DURATION_MINUTES = 15  # Kilitleme süresi (dakika)
ACCOUNT_LOCKOUT_WINDOW_MINUTES = 15    # Deneme penceresi (dakika)

pwd_context = BcryptContext()
security = HTTPBearer(auto_error=False)


def validate_password_strength(password: str) -> dict:
    """Şifre güçlülük kontrolü - kurallar ve puan döndürür"""
    errors = []
    score = 0

    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Şifre en az {PASSWORD_MIN_LENGTH} karakter olmalı")
    else:
        score += 1

    if len(password) > PASSWORD_MAX_LENGTH:
        errors.append(f"Şifre en fazla {PASSWORD_MAX_LENGTH} karakter olabilir")

    if not re.search(r'[A-Z]', password):
        errors.append("En az 1 büyük harf gerekli (A-Z)")
    else:
        score += 1

    if not re.search(r'[a-z]', password):
        errors.append("En az 1 küçük harf gerekli (a-z)")
    else:
        score += 1

    if not re.search(r'[0-9]', password):
        errors.append("En az 1 rakam gerekli (0-9)")
    else:
        score += 1

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]', password):
        errors.append("En az 1 özel karakter gerekli (!@#$%^&*...)")
    else:
        score += 1

    # Bonus: length
    if len(password) >= 12:
        score += 1
    if len(password) >= 16:
        score += 1

    # Strength label
    if score <= 2:
        strength = "weak"
        strength_label = "Zayıf"
    elif score <= 4:
        strength = "medium"
        strength_label = "Orta"
    elif score <= 5:
        strength = "strong"
        strength_label = "Güçlü"
    else:
        strength = "very_strong"
        strength_label = "Çok Güçlü"

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "score": score,
        "max_score": 7,
        "strength": strength,
        "strength_label": strength_label,
    }


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# v108 (Bug DAI): timing-attack defense — login user_not_found path için constant-time
# bcrypt verify. Passlib'in built-in `dummy_verify()` metodunu kullanırız: bu, kayıtlı
# en yüksek bcrypt cost factor'a göre dummy hash kullanır (heterogen rounds=10/12
# durumunda bile timing eşitlenir). Manuel hash compute riski elimine olur.
def dummy_verify_password() -> None:
    """Run a constant-cost bcrypt verify against passlib's built-in dummy hash.

    Used by login when the supplied email is not found, so attackers cannot
    use response timing to enumerate which emails exist. Passlib's
    `dummy_verify()` automatically tracks the maximum bcrypt cost in use,
    eliminating the heterogeneous-cost timing-drift risk.
    """
    try:
        pwd_context.dummy_verify()
    except Exception:
        # Defensive: never let dummy verification surface as an error.
        pass


def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


SERVICE_ALLOWED_PATHS = (
    "/api/scan",
    "/api/scan/",
    "/api/scan/providers",
    "/api/scan/ocr-status",
    "/api/health",
    "/api/providers",
)


def _check_service_key(request) -> Optional[dict]:
    """Service-to-service: X-Service-Key header eşleşirse sentetik kullanıcı döndürür.
    Yalnızca SERVICE_ALLOWED_PATHS içindeki yollarda geçerlidir; admin yetkisi verilmez."""
    if not QUICKID_SERVICE_KEY:
        return None
    try:
        svc = request.headers.get("x-service-key") or request.headers.get("X-Service-Key")
        path = str(request.url.path or "")
    except Exception:
        return None
    if not svc or svc != QUICKID_SERVICE_KEY:
        return None
    # Yetki sadece beyaz listedeki path'ler için
    if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in SERVICE_ALLOWED_PATHS):
        return None
    acting = request.headers.get("x-acting-user") or "syroce-pms"
    return {
        "sub": "service",
        "email": acting,
        "name": f"Syroce PMS ({acting})",
        "role": "service",
        "is_service": True,
    }


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency: extract current user from JWT token. Returns None if no token."""
    if request is not None:
        svc_user = _check_service_key(request)
        if svc_user:
            return svc_user
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    return payload


_PWD_CHANGE_BYPASS_PATHS = (
    "/api/auth/change-password",
    "/api/auth/logout",
    "/api/auth/me",
)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency: require valid auth token veya servis anahtarı.

    v107 (Bug DAH P0, architect 2nd round): force_password_change enforcement.
    Eğer user.force_password_change=True ise → change-password/logout/me dışındaki
    tüm route'lar 403 PASSWORD_CHANGE_REQUIRED döner. Frontend bu kodu yakalayıp
    change-password sayfasına yönlendirir. DB'ye sadece flag set edip enforce
    etmemek = post-rotation user'ın cleanup yapmadan tüm modülleri kullanması.
    """
    if request is not None:
        svc_user = _check_service_key(request)
        if svc_user:
            return svc_user
    if not credentials:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token")

    # Force password change enforcement
    try:
        path = str(request.url.path) if request is not None else ""
    except Exception:
        path = ""
    if path not in _PWD_CHANGE_BYPASS_PATHS:
        try:
            from db import users_col
            email = payload.get("email")
            # v107 EK-3 round-4 (architect P0): email/user_doc None case fail-closed.
            # Önceki davranış: email yoksa veya user_doc yoksa skip → silinmiş user'ın
            # token'ı ile request geçerdi (stale token bypass).
            if not email:
                raise HTTPException(status_code=401, detail={
                    "message": "Token geçersiz (email claim eksik).",
                    "error_code": "INVALID_TOKEN",
                })
            user_doc = await users_col.find_one(
                {"email": email},
                {"force_password_change": 1, "is_active": 1},
            )
            if not user_doc:
                raise HTTPException(status_code=401, detail={
                    "message": "Kullanıcı bulunamadı veya silinmiş.",
                    "error_code": "USER_NOT_FOUND",
                })
            if user_doc.get("is_active") is False:
                raise HTTPException(status_code=403, detail={
                    "message": "Hesap devre dışı bırakıldı. Yöneticiyle iletişime geçin.",
                    "error_code": "ACCOUNT_DISABLED",
                })
            if user_doc.get("force_password_change"):
                raise HTTPException(status_code=403, detail={
                    "message": "Devam etmeden önce şifrenizi değiştirmeniz gerekiyor.",
                    "error_code": "PASSWORD_CHANGE_REQUIRED",
                })
        except HTTPException:
            raise
        except Exception as e:
            # v107 EK-2 (Bug DAH P0 round-3, architect): fail-CLOSED.
            # Önceki davranış: silent bypass → DB outage'da force_password_change/is_active
            # check'leri atlanırdı → broken access control. Şimdi 503 dön; client retry eder.
            # Tüm sistem yatmaz çünkü yalnızca authenticated route'lar etkilenir + transient.
            import logging as _l
            _l.getLogger(__name__).error(f"require_auth status lookup failed (fail-closed): {e}")
            raise HTTPException(status_code=503, detail={
                "message": "Geçici bir doğrulama hatası oluştu. Lütfen tekrar deneyin.",
                "error_code": "AUTH_STATUS_LOOKUP_FAILED",
            })

    return payload


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency: require admin role. Service key bypass admin yetkisi vermez.

    v48 (Bug CH, architect Round-3): re-fetch user_doc and verify role +
    is_active at request time. Without this, a token issued before role
    revocation (or account disable) keeps full admin privileges until expiry,
    enabling a long-lived admin compromise even after the human admin is
    demoted/disabled. Service-key path bypasses re-fetch (already trusted by
    `_check_service_key`).
    """
    user = await require_auth(request, credentials)
    # Service key shortcut: if `_check_service_key` returned, `user` won't have
    # a Mongo `_id`/`sub` shape we can re-look up. Treat presence of
    # `service_key` marker as already-trusted.
    if user.get("service_key"):
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gerekiyor")
        return user
    sub = user.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    # Lazy import to avoid circular dep at module load
    from bson import ObjectId
    from db import users_col  # type: ignore
    try:
        oid = ObjectId(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    db_user = await users_col.find_one({"_id": oid})
    if not db_user:
        raise HTTPException(status_code=401, detail="Hesap bulunamadı")
    if not db_user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Hesabınız devre dışı bırakılmış")
    if db_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için admin yetkisi gerekiyor")
    return user


# ===== Account Lockout Helpers =====
async def check_account_lockout(db, email: str) -> dict:
    """Hesap kilidi kontrolü - kilitliyse bilgi döndürür"""
    lockout_col = db["login_attempts"]
    window_start = datetime.now(timezone.utc) - timedelta(minutes=ACCOUNT_LOCKOUT_WINDOW_MINUTES)

    # Son penceredeki başarısız denemeleri say
    failed_count = await lockout_col.count_documents({
        "email": email,
        "success": False,
        "timestamp": {"$gte": window_start}
    })

    if failed_count >= ACCOUNT_LOCKOUT_THRESHOLD:
        # En son denemeyi bul
        last_attempt = await lockout_col.find_one(
            {"email": email, "success": False},
            sort=[("timestamp", -1)]
        )
        if last_attempt:
            # MongoDB BSON datetime'lar pymongo default'ta naive döner. tz-aware'e
            # normalize et ki "now" (aware) ile karşılaştırma TypeError vermesin.
            ts = last_attempt["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            lockout_until = ts + timedelta(minutes=ACCOUNT_LOCKOUT_DURATION_MINUTES)
            now = datetime.now(timezone.utc)
            if now < lockout_until:
                remaining_seconds = int((lockout_until - now).total_seconds())
                remaining_minutes = remaining_seconds // 60 + 1
                return {
                    "locked": True,
                    "remaining_minutes": remaining_minutes,
                    "remaining_seconds": remaining_seconds,
                    "failed_attempts": failed_count,
                    "message": f"Hesap kilitlendi. {remaining_minutes} dakika sonra tekrar deneyin."
                }

    remaining_attempts = ACCOUNT_LOCKOUT_THRESHOLD - failed_count
    return {
        "locked": False,
        "failed_attempts": failed_count,
        "remaining_attempts": remaining_attempts,
    }


async def record_login_attempt(db, email: str, success: bool, ip_address: str = None):
    """Giriş denemesini kaydet"""
    lockout_col = db["login_attempts"]
    await lockout_col.insert_one({
        "email": email,
        "success": success,
        "ip_address": ip_address,
        "timestamp": datetime.now(timezone.utc),
    })

    # Başarılı girişte eski başarısız denemeleri temizle
    if success:
        await lockout_col.delete_many({
            "email": email,
            "success": False,
        })


async def unlock_account(db, email: str):
    """Admin tarafından hesap kilidini aç"""
    lockout_col = db["login_attempts"]
    result = await lockout_col.delete_many({
        "email": email,
        "success": False,
    })
    return {"cleared_attempts": result.deleted_count}
