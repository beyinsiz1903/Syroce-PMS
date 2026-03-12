"""2FA Enhanced Security Module - TOTP/SMS, Login Flow, Rate Limiting, Enforcement
================================================================================
Gelişmiş 2FA modülü:
- TOTP ile QR kod tabanlı doğrulama
- Login akışına entegre 2FA kontrolü
- Rol bazlı zorunlu 2FA enforcement
- Brute-force koruması (rate limiting)
- Oturum yönetimi ile 2FA
- Yedek kod (backup code) yönetimi
- Cihaz güvenilirlik yönetimi (trusted devices)
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import pyotp
import qrcode
import io
import base64
import uuid
import hashlib
import secrets

router = APIRouter(prefix="/api/security/2fa", tags=["2FA Security"])

# ============= MODELS =============
class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code: str
    manual_entry_key: str
    issuer: str = "RoomOps PMS"

class TwoFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)  # 6 for TOTP, 8 for backup

class TwoFAStatusResponse(BaseModel):
    enabled: bool
    method: Optional[str] = None
    last_verified: Optional[str] = None
    backup_codes_remaining: int = 0
    trusted_devices: int = 0
    enforced_by_policy: bool = False

class TwoFALoginVerifyRequest(BaseModel):
    email: str
    temp_token: str
    code: str

class TrustedDeviceRequest(BaseModel):
    device_name: str
    device_fingerprint: str  # Browser fingerprint or device ID

class TwoFAPolicyUpdate(BaseModel):
    require_2fa: bool = False
    require_2fa_roles: List[str] = []
    enforce_after_days: int = 7
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 30
    trusted_device_days: int = 30
    require_2fa_for_sensitive_ops: bool = True

# ============= HELPER FUNCTIONS =============
def generate_qr_code_base64(provisioning_uri: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

def generate_backup_codes(count: int = 10) -> list:
    return [secrets.token_hex(4).upper() for _ in range(count)]

def hash_backup_code(code: str) -> str:
    """Backup code'u hash'le (güvenli saklama)"""
    return hashlib.sha256(code.upper().encode()).hexdigest()

def generate_device_token() -> str:
    """Güvenilir cihaz tokeni oluştur"""
    return secrets.token_urlsafe(32)

# ============= RATE LIMITING HELPER =============
async def check_rate_limit(db, user_id: str, tenant_id: str, max_attempts: int = 5, window_minutes: int = 30):
    """2FA doğrulama girişimi rate limiting"""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
    
    attempts = await db.twofa_attempts.count_documents({
        "user_id": user_id,
        "tenant_id": tenant_id,
        "timestamp": {"$gte": cutoff},
        "success": False
    })
    
    if attempts >= max_attempts:
        # Kilitlenme süresini kontrol et
        last_attempt = await db.twofa_attempts.find_one(
            {"user_id": user_id, "tenant_id": tenant_id, "success": False},
            sort=[("timestamp", -1)]
        )
        if last_attempt:
            lockout_until = (
                datetime.fromisoformat(last_attempt["timestamp"].replace("Z", "+00:00")) + 
                timedelta(minutes=window_minutes)
            )
            remaining = (lockout_until - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Çok fazla başarısız deneme. {int(remaining/60)} dakika sonra tekrar deneyin."
                )
    
    return attempts

async def record_attempt(db, user_id: str, tenant_id: str, success: bool, ip_address: str = None):
    """2FA girişim kaydı"""
    await db.twofa_attempts.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "success": success,
        "ip_address": ip_address,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


# ============= ENDPOINTS =============
def create_2fa_routes(db, get_current_user):
    """Create enhanced 2FA routes"""
    
    @router.get("/status", response_model=TwoFAStatusResponse)
    async def get_2fa_status(current_user=Depends(get_current_user)):
        """Get current 2FA status with enforcement info"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        # Politika kontrolü
        policy = await db.tenant_security_policies.find_one(
            {"tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        
        enforced = False
        if policy:
            if policy.get("require_2fa"):
                enforced = True
            elif current_user.role in policy.get("require_2fa_roles", []):
                enforced = True
        
        # Güvenilir cihaz sayısı
        trusted_count = await db.trusted_devices.count_documents({
            "user_id": current_user.id,
            "tenant_id": current_user.tenant_id,
            "is_active": True
        })
        
        if not user_2fa or not user_2fa.get("enabled"):
            return TwoFAStatusResponse(
                enabled=False,
                enforced_by_policy=enforced,
                trusted_devices=trusted_count
            )
        
        return TwoFAStatusResponse(
            enabled=True,
            method=user_2fa.get("method", "totp"),
            last_verified=user_2fa.get("last_verified"),
            backup_codes_remaining=len(user_2fa.get("backup_codes", [])),
            trusted_devices=trusted_count,
            enforced_by_policy=enforced
        )
    
    @router.post("/setup", response_model=TwoFASetupResponse)
    async def setup_2fa(current_user=Depends(get_current_user)):
        """Initialize 2FA setup - generates TOTP secret and QR code"""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        
        provisioning_uri = totp.provisioning_uri(
            name=current_user.email,
            issuer_name="RoomOps PMS"
        )
        
        qr_code = generate_qr_code_base64(provisioning_uri)
        
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "user_id": current_user.id,
                "tenant_id": current_user.tenant_id,
                "email": current_user.email,
                "secret": secret,
                "method": "totp",
                "enabled": False,
                "setup_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return TwoFASetupResponse(
            secret=secret,
            qr_code=qr_code,
            manual_entry_key=secret
        )
    
    @router.post("/verify")
    async def verify_and_enable_2fa(
        request: TwoFAVerifyRequest,
        req: Request = None,
        current_user=Depends(get_current_user)
    ):
        """Verify TOTP code and enable 2FA with rate limiting"""
        # Rate limit kontrolü
        await check_rate_limit(db, current_user.id, current_user.tenant_id)
        
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa:
            await record_attempt(db, current_user.id, current_user.tenant_id, False)
            raise HTTPException(status_code=400, detail="2FA kurulumu bulunamadı. Önce /setup endpoint'ini kullanın.")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            await record_attempt(db, current_user.id, current_user.tenant_id, False)
            raise HTTPException(status_code=400, detail="Geçersiz doğrulama kodu. Tekrar deneyin.")
        
        # Başarılı - kaydı güncelle
        await record_attempt(db, current_user.id, current_user.tenant_id, True)
        
        backup_codes = generate_backup_codes(10)
        hashed_codes = [hash_backup_code(c) for c in backup_codes]
        
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "enabled": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "last_verified": datetime.now(timezone.utc).isoformat(),
                "backup_codes": backup_codes,  # Plain text for display only
                "backup_codes_hashed": hashed_codes,  # Hashed for verification
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_enabled",
            "resource_type": "security",
            "details": {"method": "totp"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "success": True,
            "message": "2FA başarıyla etkinleştirildi",
            "backup_codes": backup_codes,
            "warning": "Yedek kodlarınızı güvenli bir yerde saklayın. Bu kodlar bir daha gösterilmeyecek."
        }
    
    @router.post("/disable")
    async def disable_2fa(
        request: TwoFAVerifyRequest,
        current_user=Depends(get_current_user)
    ):
        """Disable 2FA (requires current TOTP code)"""
        # Politika kontrolü - zorunlu 2FA varsa devre dışı bırakılamaz
        policy = await db.tenant_security_policies.find_one(
            {"tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        if policy:
            if policy.get("require_2fa") or current_user.role in policy.get("require_2fa_roles", []):
                raise HTTPException(
                    status_code=403, 
                    detail="Güvenlik politikası gereği 2FA devre dışı bırakılamaz"
                )
        
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa or not user_2fa.get("enabled"):
            raise HTTPException(status_code=400, detail="2FA zaten devre dışı")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Geçersiz doğrulama kodu")
        
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "enabled": False,
                "disabled_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Güvenilir cihazları temizle
        await db.trusted_devices.delete_many({
            "user_id": current_user.id, "tenant_id": current_user.tenant_id
        })
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_disabled",
            "resource_type": "security",
            "details": {"method": "totp"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": "2FA başarıyla devre dışı bırakıldı"}
    
    @router.post("/validate")
    async def validate_2fa_code(
        request: TwoFAVerifyRequest,
        current_user=Depends(get_current_user)
    ):
        """Validate a 2FA code (for login flow and sensitive operations)"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa or not user_2fa.get("enabled"):
            return {"valid": True, "message": "2FA etkin değil, doğrulama gerekmez"}
        
        # Rate limit kontrolü
        await check_rate_limit(db, current_user.id, current_user.tenant_id)
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        # TOTP kodu kontrolü
        if totp.verify(request.code, valid_window=1):
            await record_attempt(db, current_user.id, current_user.tenant_id, True)
            await db.user_2fa.update_one(
                {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
                {"$set": {"last_verified": datetime.now(timezone.utc).isoformat()}}
            )
            return {"valid": True, "message": "Kod doğrulandı"}
        
        # Yedek kod kontrolü
        backup_codes = user_2fa.get("backup_codes", [])
        code_upper = request.code.upper()
        if code_upper in backup_codes:
            backup_codes.remove(code_upper)
            await db.user_2fa.update_one(
                {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
                {"$set": {
                    "backup_codes": backup_codes,
                    "last_verified": datetime.now(timezone.utc).isoformat()
                }}
            )
            await record_attempt(db, current_user.id, current_user.tenant_id, True)
            return {
                "valid": True,
                "message": "Yedek kod kullanıldı",
                "backup_codes_remaining": len(backup_codes),
                "warning": "Yedek kodlarınız azalıyor" if len(backup_codes) < 3 else None
            }
        
        # Hashed backup code kontrolü
        hashed_codes = user_2fa.get("backup_codes_hashed", [])
        code_hash = hash_backup_code(code_upper)
        if code_hash in hashed_codes:
            hashed_codes.remove(code_hash)
            # Plain text listeden de kaldır (varsa)
            if code_upper in backup_codes:
                backup_codes.remove(code_upper)
            await db.user_2fa.update_one(
                {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
                {"$set": {
                    "backup_codes": backup_codes,
                    "backup_codes_hashed": hashed_codes,
                    "last_verified": datetime.now(timezone.utc).isoformat()
                }}
            )
            await record_attempt(db, current_user.id, current_user.tenant_id, True)
            return {
                "valid": True,
                "message": "Yedek kod kullanıldı",
                "backup_codes_remaining": len(hashed_codes)
            }
        
        await record_attempt(db, current_user.id, current_user.tenant_id, False)
        raise HTTPException(status_code=400, detail="Geçersiz doğrulama kodu")
    
    @router.post("/regenerate-backup-codes")
    async def regenerate_backup_codes(
        request: TwoFAVerifyRequest,
        current_user=Depends(get_current_user)
    ):
        """Regenerate backup codes (requires current TOTP code)"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa or not user_2fa.get("enabled"):
            raise HTTPException(status_code=400, detail="2FA etkin değil")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Geçersiz doğrulama kodu")
        
        new_codes = generate_backup_codes(10)
        hashed_codes = [hash_backup_code(c) for c in new_codes]
        
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "backup_codes": new_codes,
                "backup_codes_hashed": hashed_codes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "backup_codes": new_codes,
            "warning": "Eski yedek kodlar geçersiz kılınmıştır"
        }
    
    # ---- TRUSTED DEVICES ----
    @router.post("/trusted-devices")
    async def add_trusted_device(
        device: TrustedDeviceRequest,
        current_user=Depends(get_current_user)
    ):
        """Güvenilir cihaz ekle"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id, "enabled": True}
        )
        if not user_2fa:
            raise HTTPException(status_code=400, detail="2FA etkin değil")
        
        # Mevcut güvenilir cihaz sayısını kontrol et (max 5)
        existing = await db.trusted_devices.count_documents({
            "user_id": current_user.id, "tenant_id": current_user.tenant_id, "is_active": True
        })
        if existing >= 5:
            raise HTTPException(status_code=400, detail="Maksimum 5 güvenilir cihaz eklenebilir")
        
        device_token = generate_device_token()
        
        device_doc = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "tenant_id": current_user.tenant_id,
            "device_name": device.device_name,
            "device_fingerprint": hashlib.sha256(device.device_fingerprint.encode()).hexdigest(),
            "device_token": device_token,
            "is_active": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.trusted_devices.insert_one(device_doc)
        
        return {
            "success": True,
            "device_token": device_token,
            "expires_at": device_doc["expires_at"],
            "message": "Cihaz güvenilir olarak eklendi. 30 gün süreyle 2FA atlayabilirsiniz."
        }
    
    @router.get("/trusted-devices")
    async def list_trusted_devices(current_user=Depends(get_current_user)):
        """Güvenilir cihazları listele"""
        devices = await db.trusted_devices.find(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "device_token": 0, "device_fingerprint": 0}
        ).to_list(10)
        
        return {"devices": devices, "total": len(devices)}
    
    @router.delete("/trusted-devices/{device_id}")
    async def remove_trusted_device(device_id: str, current_user=Depends(get_current_user)):
        """Güvenilir cihazı kaldır"""
        result = await db.trusted_devices.update_one(
            {"id": device_id, "user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {"is_active": False, "revoked_at": datetime.now(timezone.utc).isoformat()}}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Cihaz bulunamadı")
        
        return {"success": True, "message": "Güvenilir cihaz kaldırıldı"}
    
    @router.delete("/trusted-devices")
    async def revoke_all_trusted_devices(current_user=Depends(get_current_user)):
        """Tüm güvenilir cihazları iptal et"""
        result = await db.trusted_devices.update_many(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id, "is_active": True},
            {"$set": {"is_active": False, "revoked_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {"success": True, "revoked_count": result.modified_count}
    
    # ---- TENANT POLICY ----
    @router.get("/tenant-policy")
    async def get_tenant_2fa_policy(current_user=Depends(get_current_user)):
        """Get tenant's 2FA security policy"""
        policy = await db.tenant_security_policies.find_one(
            {"tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        return policy or {
            "tenant_id": current_user.tenant_id,
            "require_2fa": False,
            "require_2fa_roles": [],
            "enforce_after_days": 0,
            "max_failed_attempts": 5,
            "lockout_duration_minutes": 30,
            "trusted_device_days": 30,
            "require_2fa_for_sensitive_ops": False
        }
    
    @router.put("/tenant-policy")
    async def update_tenant_2fa_policy(
        policy: TwoFAPolicyUpdate,
        current_user=Depends(get_current_user)
    ):
        """Update tenant 2FA policy (admin only)"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        await db.tenant_security_policies.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "require_2fa": policy.require_2fa,
                "require_2fa_roles": policy.require_2fa_roles,
                "enforce_after_days": policy.enforce_after_days,
                "max_failed_attempts": policy.max_failed_attempts,
                "lockout_duration_minutes": policy.lockout_duration_minutes,
                "trusted_device_days": policy.trusted_device_days,
                "require_2fa_for_sensitive_ops": policy.require_2fa_for_sensitive_ops,
                "updated_by": current_user.id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_policy_updated",
            "resource_type": "security",
            "details": policy.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": "2FA politikası güncellendi"}
    
    # ---- 2FA STATS ----
    @router.get("/stats")
    async def get_2fa_stats(current_user=Depends(get_current_user)):
        """Tenant 2FA istatistikleri"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        tenant_id = current_user.tenant_id
        
        total_users = await db.users.count_documents({"tenant_id": tenant_id, "is_active": True})
        enabled_2fa = await db.user_2fa.count_documents({"tenant_id": tenant_id, "enabled": True})
        
        # Son 30 günlük girişim istatistikleri
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        total_attempts = await db.twofa_attempts.count_documents({
            "tenant_id": tenant_id, "timestamp": {"$gte": cutoff}
        })
        failed_attempts = await db.twofa_attempts.count_documents({
            "tenant_id": tenant_id, "timestamp": {"$gte": cutoff}, "success": False
        })
        
        adoption_rate = round((enabled_2fa / total_users * 100), 1) if total_users > 0 else 0
        success_rate = round(
            ((total_attempts - failed_attempts) / total_attempts * 100), 1
        ) if total_attempts > 0 else 100
        
        return {
            "tenant_id": tenant_id,
            "total_users": total_users,
            "users_with_2fa": enabled_2fa,
            "users_without_2fa": total_users - enabled_2fa,
            "adoption_rate": adoption_rate,
            "last_30_days": {
                "total_attempts": total_attempts,
                "successful_attempts": total_attempts - failed_attempts,
                "failed_attempts": failed_attempts,
                "success_rate": success_rate
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    return router
