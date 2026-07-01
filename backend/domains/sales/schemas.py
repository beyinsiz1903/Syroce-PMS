"""
Sales Domain — Schemas
Request/response models extracted from sales routers.
"""

from enum import Enum

from pydantic import BaseModel, EmailStr, Field, conint, field_validator


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


class MarketingContactLeadRequest(BaseModel):
    """Public marketing-site contact form (no auth)."""

    full_name: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=40)
    email: EmailStr
    business_type: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=5000)
    metadata: PmsLiteLeadMetadata | None = None

    @field_validator("full_name", "company", "phone", mode="before")
    @classmethod
    def _strip_required(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("business_type", "message", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class SupplierLeadRequest(BaseModel):
    """Public supplier application form (no auth)."""

    company: str = Field(min_length=1, max_length=200)
    tax_no: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr
    metadata: PmsLiteLeadMetadata | None = None

    @field_validator("company", mode="before")
    @classmethod
    def _strip_company(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("tax_no", "phone", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v
