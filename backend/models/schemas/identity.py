"""Auto-split from schemas.py — domain: identity."""
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.enums import (
    UserRole,
)


class Tenant(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hotel_id: str | None = None  # 6-digit human-friendly ID (e.g. "482917")
    property_name: str
    property_type: str | None = "hotel"
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    total_rooms: int | None = 50
    subscription_status: str = "active"
    subscription_start_date: str | None = None
    subscription_end_date: str | None = None
    subscription_tier: str | None = "basic"
    plan: str = "core_small_hotel"
    subscription_plan: str | None = None
    location: str | None = None
    amenities: list[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    modules: dict[str, bool] = Field(
        default_factory=lambda: {
            "pms": True,
            "reports": True,
            "invoices": True,
            "ai": True,
        }
    )
    features: dict[str, bool] | None = None

class User(BaseModel):
    model_config = ConfigDict(extra="allow")  # Changed from "ignore" to "allow" to fix tenant_id loading
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None  # Hotel ID
    agency_id: str | None = None  # Agency ID (new for agency users)
    email: EmailStr
    username: str | None = None  # Login username (unique within tenant)
    name: str
    role: UserRole
    phone: str | None = None
    is_active: bool = True
    email_verified: bool = False
    email_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    password: str | None = Field(None, exclude=True)  # Exclude password from responses
    # Task #28: rol-bazlı izinlere ek olarak kullanıcıya tek tek verilen
    # operasyon-seviyesi izinler (ör. "send_urgent_message"). Boş liste
    # default — geriye dönük uyumlu, yalnız adminler doldurur.
    granted_permissions: list[str] = Field(default_factory=list)

# Helper function (defined after User class)
def _ensure_hotel_context(user: User):
    """Ensure user has hotel/tenant context"""
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Hotel context required")

class TenantRegister(BaseModel):
    property_name: str
    property_type: str | None = "city_hotel"
    email: EmailStr
    password: str
    name: str
    username: str | None = None  # Optional; if not provided, derived from email local-part
    phone: str
    address: str
    location: str | None = None
    total_rooms: int | None = None
    description: str | None = None
    subscription_days: int | None = None
    subscription_plan: str | None = None
    subscription_tier: str | None = "basic"

class GuestRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: str

class UserLogin(BaseModel):
    """Hotel staff login. Either (hotel_id + username) or legacy email is accepted."""
    hotel_id: str | None = None
    username: str | None = None
    email: EmailStr | None = None  # Legacy fallback (guest login still uses email)
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
    tenant: Tenant | None = None
    # 2FA challenge: when True, access_token is empty and the client
    # must POST /auth/2fa/verify with `challenge_token` + 6-digit code
    # to obtain a real access_token.
    requires_2fa: bool = False
    challenge_token: str | None = None
    # V3 (Syroce mobil): long-lived refresh token for the mobile app.
    # Optional so legacy/web flows that don't ask for one don't break.
    # When present the client should store it in SecureStore and POST
    # it (in the body) to /api/auth/refresh-token to rotate the access
    # token without a fresh password prompt.
    refresh_token: str | None = None
    # Access-token lifetime in seconds — lets the mobile client schedule
    # its proactive refresh exactly instead of hard-coding 15 min.
    expires_in: int | None = None

class NotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email_notifications: bool = True
    whatsapp_notifications: bool = False
    in_app_notifications: bool = True
    booking_updates: bool = True
    promotional: bool = True
    room_service_updates: bool = True


