"""
Sales Domain — Schemas
Request/response models extracted from sales routers.
"""
from pydantic import BaseModel, EmailStr, conint
from typing import Optional
from enum import Enum


class LeadStage(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    CONVERTED = "converted"
    LOST = "lost"


class CreateLeadRequest(BaseModel):
    guest_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    stage: LeadStage = LeadStage.COLD
    source: str
    notes: Optional[str] = None
    expected_checkin: Optional[str] = None
    expected_revenue: float = 0


class UpdateLeadStageRequest(BaseModel):
    stage: LeadStage
    notes: Optional[str] = None


class PmsLiteLeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    LOST = "lost"
    WON = "won"


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


class PmsLiteLeadCreateRequest(BaseModel):
    contact: PmsLiteLeadContact
    hotel: PmsLiteLeadHotel
    metadata: Optional[PmsLiteLeadMetadata] = None


class PmsLiteLeadAdminUpdateRequest(BaseModel):
    status: Optional[PmsLiteLeadStatus] = None
    note: Optional[str] = None
