"""
Sales Domain — Schemas
Request/response models extracted from sales routers.
"""
from enum import Enum

from pydantic import BaseModel, EmailStr, conint


class LeadStage(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    CONVERTED = "converted"
    LOST = "lost"


class CreateLeadRequest(BaseModel):
    guest_name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    stage: LeadStage = LeadStage.COLD
    source: str
    notes: str | None = None
    expected_checkin: str | None = None
    expected_revenue: float = 0


class UpdateLeadStageRequest(BaseModel):
    stage: LeadStage
    notes: str | None = None


class PmsLiteLeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    LOST = "lost"
    WON = "won"


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


class PmsLiteLeadCreateRequest(BaseModel):
    contact: PmsLiteLeadContact
    hotel: PmsLiteLeadHotel
    metadata: PmsLiteLeadMetadata | None = None


class PmsLiteLeadAdminUpdateRequest(BaseModel):
    status: PmsLiteLeadStatus | None = None
    note: str | None = None
