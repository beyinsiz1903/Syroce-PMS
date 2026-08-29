"""
Admin Domain — Schemas
Request/response models extracted from admin/router.py.
"""

from datetime import date
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


class TenantProvisioningUpdate(BaseModel):
    """Superadmin tarafından hedef otelin kurulum kapsamını günceller."""

    channel_manager_provider: Literal["exely", "hotelrunner"] | None = None
    chain_id: str | None = None
    is_chain_headquarters: bool | None = None


class AdminProviderCredentialsRequest(BaseModel):
    credentials: dict[str, str]


class AdminNilveraProvisioningRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    seller: dict | None = None


class AdminNilveraGLProvisioningRequest(BaseModel):
    incoming_mode: Literal["disabled", "review", "automatic"] = "review"
    outgoing_mode: Literal["disabled", "review", "automatic"] = "review"
    incoming_purchase_account_code: str = Field("153", min_length=1, max_length=40)
    incoming_vat_account_code: str = Field("191", min_length=1, max_length=40)
    incoming_payable_account_code: str = Field("320", min_length=1, max_length=40)
    incoming_other_tax_account_code: str | None = Field(None, max_length=40)
    incoming_deduction_account_code: str | None = Field(None, max_length=40)
    incoming_other_tax_accounts_by_code: dict[str, str] = Field(default_factory=dict)
    incoming_deduction_accounts_by_code: dict[str, str] = Field(default_factory=dict)
    outgoing_revenue_account_code: str = Field("600", min_length=1, max_length=40)
    outgoing_receivable_account_code: str = Field("120", min_length=1, max_length=40)
    outgoing_discount_account_code: str | None = Field("611", max_length=40)
    outgoing_vat_account_code: str | None = Field("391", max_length=40)
    outgoing_accommodation_tax_account_code: str | None = Field("360", max_length=40)
    outgoing_vat_accounts_by_rate: dict[str, str] = Field(default_factory=dict)
    outgoing_accommodation_tax_accounts_by_rate: dict[str, str] = Field(default_factory=dict)


class AdminCreateChainRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    headquarters_tenant_id: str | None = None


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
    tax_number: str | None = Field(default=None, max_length=20)
    license_number: str | None = Field(default=None, max_length=100)
    license_expires_at: date | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)


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
    hotel_name: str = Field(..., alias="hotelName")
    room_count: str = Field(..., alias="roomCount")


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
