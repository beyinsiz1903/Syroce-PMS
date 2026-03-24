"""
Admin Domain — Schemas
Request/response models extracted from admin/router.py.
"""
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, EmailStr, Field, conint


class PermissionCheckRequest(BaseModel):
    permission: str


class TenantModulesUpdate(BaseModel):
    modules: Dict[str, bool]


class SubscriptionUpdateRequest(BaseModel):
    subscription_days: Optional[int] = None
    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None


class ChangePlanRequest(BaseModel):
    new_tier: str
    billing_cycle: str = "monthly"


class UpdateHotelInfoRequest(BaseModel):
    property_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    total_rooms: Optional[int] = None


class CreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
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
    status: Optional[PmsLiteLeadStatus] = None
    note: Optional[str] = None


class AdminUpdateTenantInfoRequest(BaseModel):
    property_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    total_rooms: Optional[int] = None


class AdminCreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    role: str = "front_desk"
    password: str


class PmsLiteLeadContact(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None


class PmsLiteLeadHotel(BaseModel):
    property_name: str
    location: Optional[str] = None
    rooms_count: conint(ge=1, le=200)


class PmsLiteLeadMetadata(BaseModel):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
