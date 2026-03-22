"""  
GDS Integration Models
Amadeus, Sabre, Galileo global distribution system
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class GDSProvider(str, Enum):
    AMADEUS = "amadeus"
    SABRE = "sabre"
    GALILEO = "galileo"
    WORLDSPAN = "worldspan"

class GDSReservation(BaseModel):
    """GDS'ten gelen rezervasyon"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    gds_provider: GDSProvider
    gds_confirmation: str
    pnr_number: str  # Passenger Name Record
    
    # Guest info from GDS
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    
    # Booking details
    check_in: str
    check_out: str
    room_type: str
    adults: int
    
    # GDS specific
    travel_agent_iata: Optional[str] = None
    commission_pct: float = 10.0
    
    # Status
    synced_to_pms: bool = False
    pms_booking_id: Optional[str] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GDSRateUpdate(BaseModel):
    """GDS'e rate güncellemesi"""
    tenant_id: str
    gds_provider: GDSProvider
    room_type: str
    date_range_start: str
    date_range_end: str
    rate: float
    availability: int
    pushed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = True
