"""
Meeting & Events Management Models
Meeting room booking, event coordination, BEO
"""
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, timezone
from enum import Enum
import uuid

class SetupType(str, Enum):
    THEATER = "theater"
    CLASSROOM = "classroom"
    BOARDROOM = "boardroom"
    U_SHAPE = "u_shape"
    BANQUET = "banquet"
    COCKTAIL = "cocktail"

class MeetingRoom(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_name: str
    capacity: int
    area_sqm: float
    floor: int
    amenities: List[str] = []  # projector, whiteboard, wifi, etc
    hourly_rate: float
    available: bool = True

class EventBooking(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    event_name: str
    organization: str
    contact_name: str
    contact_email: str
    meeting_room_id: str
    event_date: datetime
    start_time: str
    end_time: str
    setup_type: SetupType
    expected_attendees: int
    catering_required: bool = False
    av_equipment: List[str] = []
    total_cost: float
    status: str = "confirmed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
