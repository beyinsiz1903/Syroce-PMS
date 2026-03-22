"""  
HR & Staff Management Models
Personel, vardiya, performans yönetimi
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class Department(str, Enum):
    FRONT_DESK = "front_desk"
    HOUSEKEEPING = "housekeeping"
    FNB = "fnb"
    MAINTENANCE = "maintenance"
    SALES = "sales"
    MANAGEMENT = "management"

class StaffMember(BaseModel):
    """Personel kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    name: str
    email: str
    phone: str
    department: Department
    position: str
    
    # Employment
    hire_date: datetime
    employment_type: str = "full_time"  # full_time, part_time, contract
    
    # Performance
    performance_score: float = 0.0
    total_tasks_completed: int = 0
    
    # Status
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ShiftSchedule(BaseModel):
    """Vardiya programı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    staff_id: str
    
    shift_date: datetime
    shift_type: str  # morning, afternoon, night
    start_time: str  # "07:00"
    end_time: str  # "15:00"
    
    # Attendance
    clocked_in: Optional[datetime] = None
    clocked_out: Optional[datetime] = None
    
    status: str = "scheduled"  # scheduled, completed, no_show, sick_leave
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PerformanceReview(BaseModel):
    """Performans değerlendirmesi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    staff_id: str
    
    review_period_start: datetime
    review_period_end: datetime
    
    # Scores (1-10)
    quality_score: float
    efficiency_score: float
    teamwork_score: float
    customer_service_score: float
    overall_score: float
    
    # Notes
    strengths: Optional[str] = None
    areas_for_improvement: Optional[str] = None
    goals: Optional[str] = None
    
    reviewed_by: str
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
