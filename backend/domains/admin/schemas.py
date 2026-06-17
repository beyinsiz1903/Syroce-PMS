"""
Admin Domain — Schemas
Request/response models extracted from admin/router.py.
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, conint


class PermissionCheckRequest(BaseModel):
    permission: str


class TenantModulesUpdate(BaseModel):
    modules: dict[str, bool]
    # Per-tenant kanal yoneticisi altyapisi secimi (super_admin). Yalnizca
    # explicit gonderildiginde yazilir; None gonderilirse secim temizlenir
    # (otomatik tespite doner). Gecersiz deger -> 422.
    channel_manager_provider: Literal["exely", "hotelrunner"] | None = None


class SubscriptionUpdateRequest(BaseModel):
    subscription_days: int | None = None
    subscription_start_date: str | None = None
    subscription_end_date: str | None = None


class ChangePlanRequest(BaseModel):
    new_tier: str
    billing_cycle: str = "monthly"


class UpdateHotelInfoRequest(BaseModel):
    property_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    location: str | None = None
    description: str | None = None
    total_rooms: int | None = None


class CreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: str | None = None
    role: str = "front_desk"
    password: str


class UpdateTeamMemberRoleRequest(BaseModel):
    role: str


class SLAConfig(BaseModel):
    category: str
    response_time_minutes: int
    resolution_time_minutes: int
    priority: str = "normal"


class DemoRequest(BaseModel):
    name: str
    email: str
    phone: str
    hotel_name: str = Field(..., alias='hotelName')
    room_count: str = Field(..., alias='roomCount')


class PmsLiteLeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    LOST = "lost"
    WON = "won"


class PmsLiteLeadAdminUpdateRequest(BaseModel):
    status: PmsLiteLeadStatus | None = None
    note: str | None = None


class AdminUpdateTenantInfoRequest(BaseModel):
    property_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    location: str | None = None
    description: str | None = None
    total_rooms: int | None = None


class UpdateGrantedPermissionsRequest(BaseModel):
    """Task #28: Kullanıcıya tek tek verilen operasyon-seviyesi izinler.

    Şu an yalnızca `send_urgent_message` yönetiliyor; ileride başka
    operasyonlar bu listeye eklenebilir. Whitelist dışı bir izin
    gönderilirse endpoint 400 ile reddeder.
    """
    permissions: list[str] = Field(default_factory=list)


class AdminCreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: str | None = None
    role: str = "front_desk"
    password: str


class PmsLiteLeadContact(BaseModel):
    full_name: str
    phone: str
    email: EmailStr | None = None


class PmsLiteLeadHotel(BaseModel):
    property_name: str
    location: str | None = None
    rooms_count: conint(ge=1, le=200)


class PmsLiteLeadMetadata(BaseModel):
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    user_agent: str | None = None
    ip: str | None = None
