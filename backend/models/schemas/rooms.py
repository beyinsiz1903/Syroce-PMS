"""Auto-split from schemas.py — domain: rooms."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    RoomStatus,
)


# Room Models
class RoomCreate(BaseModel):
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: float
    amenities: list[str] = []

    # Extended fields
    view: str | None = None  # e.g. sea, city, garden, mountain
    bed_type: str | None = None

class Room(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: float | None = None
    price_per_night: float | None = None
    status: RoomStatus = RoomStatus.AVAILABLE
    amenities: list[str] = []

    # Extended fields
    view: str | None = None
    bed_type: str | None = None
    images: list[str] = []  # stored paths/urls

    # Virtual room (for no-show bookings)
    is_virtual: bool = False

    # Soft delete
    is_active: bool = True
    deleted_at: str | None = None

    current_booking_id: str | None = None
    last_cleaned: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class HousekeepingTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    task_type: str  # cleaning, inspection, maintenance
    assigned_to: str | None = None
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "normal"  # low, normal, high, urgent
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MaintenanceWorkOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    room_id: str | None = None
    room_number: str | None = None
    issue_type: str  # plumbing, hvac, electrical, furniture, housekeeping_damage, other
    priority: str = "normal"  # low, normal, high, urgent
    status: str = "open"  # open, in_progress, completed, cancelled
    source: str = "housekeeping"  # housekeeping, frontdesk, sensor, gm, other
    description: str | None = None
    reported_by_user_id: str | None = None
    asset_id: str | None = None
    plan_id: str | None = None

    reported_by_role: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SensorAlert(BaseModel):
    """IoT sensör uyarısı modeli - sensörden gelen ham veriyi ve bağlamı temsil eder"""
    id: str | None = None
    tenant_id: str | None = None
    sensor_id: str
    room_id: str | None = None
    room_number: str | None = None
    metric: str  # e.g. temperature, humidity, water_leak, door_open
    value: float
    threshold: float | None = None
    threshold_breached: bool | None = None
    severity: str = "info"  # info, warning, high, critical


class MaintenanceAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    name: str
    asset_type: str  # hvac, plumbing, electrical, elevator, room_fixture, other
    room_id: str | None = None
    room_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    installed_at: datetime | None = None
    warranty_until: datetime | None = None
    status: str = "active"  # active, retired, out_of_service


class PreventiveMaintenancePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    asset_id: str | None = None
    asset_type: str | None = None
    frequency_type: str  # days, weeks, months
    frequency_value: int
    next_due_date: datetime
    last_completed_date: datetime | None = None
    description: str | None = None
    default_issue_type: str = "other"
    default_priority: str = "normal"
    is_active: bool = True

    message: str | None = None
    metadata: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    completed_at: datetime | None = None



