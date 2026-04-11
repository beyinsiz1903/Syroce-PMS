"""
Sales CRM & Pipeline Models
Lead management, sales funnel, activity tracking
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from datetime import datetime, timezone
from enum import Enum
import uuid

class LeadSource(str, Enum):
    """Lead kaynağı"""
    WEBSITE = "website"
    PHONE = "phone"
    EMAIL = "email"
    WALK_IN = "walk_in"
    REFERRAL = "referral"
    OTA = "ota"
    TRAVEL_AGENT = "travel_agent"
    CORPORATE = "corporate"

class LeadStatus(str, Enum):
    """Lead durumu"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATING = "negotiating"
    WON = "won"
    LOST = "lost"

class LeadPriority(str, Enum):
    """Lead önceliği"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class Lead(BaseModel):
    """Satış lead'i"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Contact Info
    company_name: Optional[str] = None
    contact_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    
    # Lead Details
    source: LeadSource
    status: LeadStatus = LeadStatus.NEW
    priority: LeadPriority = LeadPriority.MEDIUM
    
    # Opportunity
    estimated_value: Optional[float] = None
    estimated_rooms: Optional[int] = None
    target_checkin: Optional[date] = None
    target_checkout: Optional[date] = None
    
    # Assignment
    assigned_to: Optional[str] = None
    
    # Lead Score (0-100)
    lead_score: int = 0
    
    # Notes
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    
    # Tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_contacted_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None

class SalesActivity(BaseModel):
    """Satış aktivitesi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    lead_id: str
    
    # Activity details
    activity_type: str  # call, email, meeting, proposal, follow_up
    subject: str
    description: Optional[str] = None
    
    # Outcome
    outcome: Optional[str] = None  # successful, no_answer, follow_up_needed
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    
    # User
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SalesFunnelMetrics(BaseModel):
    """Satış hunisi metrikleri"""
    tenant_id: str
    period_start: date
    period_end: date
    
    # Funnel stages
    new_leads: int = 0
    contacted: int = 0
    qualified: int = 0
    proposal_sent: int = 0
    negotiating: int = 0
    won: int = 0
    lost: int = 0
    
    # Conversion rates
    contact_rate: float = 0.0
    qualification_rate: float = 0.0
    win_rate: float = 0.0
    
    # Value
    total_value_won: float = 0.0
    total_value_lost: float = 0.0
    
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
