"""
HR Management - Complete Suite
Time & Attendance, Payroll, Leave Management, Performance, Recruitment
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, date
import uuid

class AttendanceRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    staff_id: str
    date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    total_hours: float = 0.0
    overtime_hours: float = 0.0
    status: str = "present"  # present, absent, late, half_day
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LeaveRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    staff_id: str
    leave_type: str  # annual, sick, personal, unpaid
    start_date: date
    end_date: date
    total_days: int
    reason: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected
    approved_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PayrollRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    staff_id: str
    period_month: str  # "2025-11"
    base_salary: float
    overtime_pay: float = 0.0
    bonuses: float = 0.0
    deductions: float = 0.0
    net_salary: float
    paid: bool = False
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class JobPosting(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    job_title: str
    department: str
    location: str
    employment_type: str  # full_time, part_time
    salary_range: str
    requirements: str
    description: str
    status: str = "active"  # active, filled, closed
    applicants_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
