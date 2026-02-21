"""2FA (Two-Factor Authentication) Module - TOTP/SMS based"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import pyotp
import qrcode
import io
import base64
import uuid

router = APIRouter(prefix="/api/security/2fa", tags=["2FA Security"])

# ============= MODELS =============
class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code: str  # base64 encoded QR code image
    manual_entry_key: str
    issuer: str = "RoomOps PMS"

class TwoFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)

class TwoFAStatusResponse(BaseModel):
    enabled: bool
    method: Optional[str] = None  # 'totp' or 'sms'
    last_verified: Optional[str] = None
    backup_codes_remaining: int = 0

class TwoFALoginVerifyRequest(BaseModel):
    email: str
    temp_token: str
    code: str

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
    import secrets
    return [secrets.token_hex(4).upper() for _ in range(count)]

# ============= ENDPOINTS =============
def create_2fa_routes(db, get_current_user):
    """Create 2FA routes with database and auth dependencies"""
    
    @router.get("/status", response_model=TwoFAStatusResponse)
    async def get_2fa_status(current_user=Depends(get_current_user)):
        """Get current 2FA status for user"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        if not user_2fa or not user_2fa.get("enabled"):
            return TwoFAStatusResponse(enabled=False)
        
        return TwoFAStatusResponse(
            enabled=True,
            method=user_2fa.get("method", "totp"),
            last_verified=user_2fa.get("last_verified"),
            backup_codes_remaining=len(user_2fa.get("backup_codes", []))
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
        
        # Store pending setup (not yet verified)
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
        current_user=Depends(get_current_user)
    ):
        """Verify TOTP code and enable 2FA"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa:
            raise HTTPException(status_code=400, detail="2FA kurulumu bulunamadi. Once /setup endpoint'ini kullanin.")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Gecersiz dogrulama kodu. Tekrar deneyin.")
        
        # Generate backup codes
        backup_codes = generate_backup_codes(10)
        
        # Enable 2FA
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "enabled": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "last_verified": datetime.now(timezone.utc).isoformat(),
                "backup_codes": backup_codes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Log audit
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
            "message": "2FA basariyla etkinlestirildi",
            "backup_codes": backup_codes,
            "warning": "Yedek kodlarinizi guvenli bir yerde saklayin. Bu kodlar bir daha gosterilmeyecek."
        }
    
    @router.post("/disable")
    async def disable_2fa(
        request: TwoFAVerifyRequest,
        current_user=Depends(get_current_user)
    ):
        """Disable 2FA (requires current TOTP code)"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa or not user_2fa.get("enabled"):
            raise HTTPException(status_code=400, detail="2FA zaten devre disi")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Gecersiz dogrulama kodu")
        
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "enabled": False,
                "disabled_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "2fa_disabled",
            "resource_type": "security",
            "details": {"method": "totp"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": "2FA basariyla devre disi birakildi"}
    
    @router.post("/validate")
    async def validate_2fa_code(
        request: TwoFAVerifyRequest,
        current_user=Depends(get_current_user)
    ):
        """Validate a 2FA code (for login flow)"""
        user_2fa = await db.user_2fa.find_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        if not user_2fa or not user_2fa.get("enabled"):
            return {"valid": True, "message": "2FA etkin degil, dogrulama gerekmez"}
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        # Check TOTP code
        if totp.verify(request.code, valid_window=1):
            await db.user_2fa.update_one(
                {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
                {"$set": {"last_verified": datetime.now(timezone.utc).isoformat()}}
            )
            return {"valid": True, "message": "Kod dogrulandi"}
        
        # Check backup codes
        backup_codes = user_2fa.get("backup_codes", [])
        if request.code.upper() in backup_codes:
            backup_codes.remove(request.code.upper())
            await db.user_2fa.update_one(
                {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
                {"$set": {
                    "backup_codes": backup_codes,
                    "last_verified": datetime.now(timezone.utc).isoformat()
                }}
            )
            return {
                "valid": True,
                "message": "Yedek kod kullanildi",
                "backup_codes_remaining": len(backup_codes)
            }
        
        raise HTTPException(status_code=400, detail="Gecersiz dogrulama kodu")
    
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
            raise HTTPException(status_code=400, detail="2FA etkin degil")
        
        secret = user_2fa.get("secret")
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Gecersiz dogrulama kodu")
        
        new_codes = generate_backup_codes(10)
        await db.user_2fa.update_one(
            {"user_id": current_user.id, "tenant_id": current_user.tenant_id},
            {"$set": {
                "backup_codes": new_codes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "backup_codes": new_codes,
            "warning": "Eski yedek kodlar gecersiz kilinmistir"
        }
    
    @router.get("/tenant-policy")
    async def get_tenant_2fa_policy(current_user=Depends(get_current_user)):
        """Get tenant's 2FA policy"""
        policy = await db.tenant_security_policies.find_one(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        return policy or {
            "tenant_id": current_user.tenant_id,
            "require_2fa": False,
            "require_2fa_roles": [],
            "enforce_after_days": 0
        }
    
    @router.put("/tenant-policy")
    async def update_tenant_2fa_policy(
        require_2fa: bool = False,
        require_2fa_roles: list = [],
        enforce_after_days: int = 7,
        current_user=Depends(get_current_user)
    ):
        """Update tenant 2FA policy (admin only)"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        await db.tenant_security_policies.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "require_2fa": require_2fa,
                "require_2fa_roles": require_2fa_roles,
                "enforce_after_days": enforce_after_days,
                "updated_by": current_user.id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return {"success": True, "message": "2FA politikasi guncellendi"}
    
    return router
