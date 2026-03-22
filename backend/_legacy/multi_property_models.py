"""
Multi-Property Management Models - Enhanced
=============================================
Çoklu otel yönetimi, merkezi rezervasyon, zincir yönetimi,
property group, cross-property raporlama modelleri.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
from enum import Enum

class PropertyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    OPENING_SOON = "opening_soon"
    CLOSED = "closed"

class PropertyType(str, Enum):
    HOTEL = "hotel"
    RESORT = "resort"
    BOUTIQUE = "boutique"
    BUSINESS = "business"
    AIRPORT = "airport"
    CONVENTION = "convention"

class PropertyGroup(BaseModel):
    """Otel grubu/zinciri"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    group_name: str
    brand_name: Optional[str] = None
    headquarters_location: str
    headquarters_country: str = "TR"
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    total_properties: int = 0
    total_rooms: int = 0
    admin_user_ids: List[str] = []
    tenant_ids: List[str] = []
    settings: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PropertyProfile(BaseModel):
    """Detaylı otel profili"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_name: str
    property_type: PropertyType = PropertyType.HOTEL
    property_status: PropertyStatus = PropertyStatus.ACTIVE
    star_rating: int = 5
    total_rooms: int = 0
    total_floors: int = 0
    address: str = ""
    city: str = ""
    country: str = "TR"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone_str: str = "Europe/Istanbul"
    currency: str = "TRY"
    check_in_time: str = "14:00"
    check_out_time: str = "12:00"
    amenities: List[str] = []
    certifications: List[str] = []  # Green Key, ISO 9001, etc.
    
    # Operasyonel bilgiler
    general_manager: Optional[str] = None
    operations_manager: Optional[str] = None
    revenue_manager: Optional[str] = None
    
    # Segment bilgisi
    primary_segment: str = "leisure"  # leisure, business, mixed
    target_markets: List[str] = []
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ConsolidatedMetrics(BaseModel):
    """Birleştirilmiş metrikler"""
    group_id: str
    report_date: datetime
    
    # Occupancy
    total_rooms: int
    total_occupied: int
    group_occupancy_pct: float
    
    # Revenue
    total_revenue: float
    total_adr: float
    total_revpar: float
    
    # GOP (Gross Operating Profit)
    total_gop: float = 0
    gop_margin: float = 0
    goppar: float = 0  # GOP per available room
    
    # Guest metrics
    total_guests: int = 0
    new_guests: int = 0
    returning_guests: int = 0
    
    # By property
    property_breakdown: List[Dict[str, Any]] = []
    
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PropertyBudget(BaseModel):
    """Otel bütçe hedefi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    period: str = "monthly"  # monthly, quarterly, yearly
    year: int = 2026
    month: Optional[int] = None
    quarter: Optional[int] = None
    
    revenue_target: float = 0
    occupancy_target: float = 75.0
    adr_target: float = 200.0
    revpar_target: float = 150.0
    expense_budget: float = 0
    gop_target: float = 0
    
    set_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CrossPropertyTransfer(BaseModel):
    """Oteller arası misafir transferi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_tenant_id: str
    target_tenant_id: str
    guest_id: str
    booking_id: Optional[str] = None
    reason: str
    status: str = "pending"  # pending, approved, completed, rejected
    transfer_date: Optional[str] = None
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChainPolicy(BaseModel):
    """Zincir geneli politika"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    group_id: str
    policy_type: str  # pricing, security, service, branding
    policy_name: str
    description: str
    rules: Dict[str, Any] = {}
    applies_to: List[str] = []  # tenant_ids, empty = all
    is_mandatory: bool = True
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
