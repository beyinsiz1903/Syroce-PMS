"""
Spa & Wellness Integration Models
Treatment bookings, therapist schedule, spa packages
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class TreatmentCategory(str, Enum):
    MASSAGE = "massage"
    FACIAL = "facial"
    BODY = "body"
    NAIL = "nail"
    PACKAGE = "package"

class SpaAppointment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: Optional[str] = None
    treatment_id: str
    therapist_id: Optional[str] = None
    appointment_date: datetime
    duration_minutes: int
    price: float
    status: str = "confirmed"  # confirmed, completed, cancelled, no_show
    charge_to_room: bool = False
    folio_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SpaTreatment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    category: TreatmentCategory
    description: str
    duration_minutes: int
    price: float
    available: bool = True
