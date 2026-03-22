"""  
Guest Journey Mapping Models
Touchpoint tracking, satisfaction measurement
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class JourneyTouchpoint(str, Enum):
    """Müsafir temas noktaları"""
    BOOKING = "booking"
    PRE_ARRIVAL = "pre_arrival"
    ARRIVAL = "arrival"
    CHECK_IN = "check_in"
    ROOM_ENTRY = "room_entry"
    HOUSEKEEPING = "housekeeping"
    FNB_SERVICE = "fnb_service"
    CONCIERGE = "concierge"
    SPA = "spa"
    CHECK_OUT = "check_out"
    POST_STAY = "post_stay"

class GuestJourneyEvent(BaseModel):
    """Müsafir yolculuğu olayı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: str
    
    touchpoint: JourneyTouchpoint
    event_type: str
    description: str
    
    # Satisfaction
    satisfaction_score: Optional[int] = None  # 1-10
    feedback: Optional[str] = None
    
    # Timing
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_minutes: Optional[int] = None
    
    # Staff involved
    staff_id: Optional[str] = None
    department: Optional[str] = None

class NPSSurvey(BaseModel):
    """Net Promoter Score anketi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: str
    
    # NPS Question: "0-10 arasında, bizi tavsiye eder misiniz?"
    nps_score: int  # 0-10
    
    # Category
    category: str  # detractor (0-6), passive (7-8), promoter (9-10)
    
    # Additional feedback
    feedback: Optional[str] = None
    
    # Department scores
    front_desk_score: Optional[int] = None
    housekeeping_score: Optional[int] = None
    fnb_score: Optional[int] = None
    
    surveyed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
