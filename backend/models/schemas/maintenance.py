"""Auto-split from schemas.py — domain: maintenance."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    MaintenancePriority,
    MaintenanceTaskStatus,
    MaintenanceType,
    WarehouseLocation,
)


# Maintenance & Technical Service Models
class SLAConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    priority: MaintenancePriority
    response_time_minutes: int  # Yanıt süresi (dakika)
    resolution_time_minutes: int  # Çözüm süresi (dakika)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SparePart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    part_number: str
    part_name: str
    description: str | None = None
    category: str  # Plumbing, Electrical, HVAC, etc.
    warehouse_location: WarehouseLocation
    current_stock: int = 0
    minimum_stock: int = 0
    unit_price: float = 0.0
    supplier: str | None = None
    qr_code: str | None = None
    last_restocked: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SparePartUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_id: str
    spare_part_id: str
    part_name: str
    quantity: int
    unit_price: float
    total_cost: float
    used_by: str  # User who used the part
    used_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


class TaskPhoto(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_id: str
    photo_url: str  # URL or base64 data
    photo_type: str  # before, during, after
    description: str | None = None
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssetMaintenanceHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str  # Equipment/Asset ID
    asset_name: str
    task_id: str
    maintenance_type: MaintenanceType
    description: str
    parts_cost: float = 0.0
    labor_cost: float = 0.0
    total_cost: float = 0.0
    technician: str
    completed_at: datetime
    downtime_minutes: int | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlannedMaintenance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str
    asset_name: str
    maintenance_type: MaintenanceType
    frequency_days: int  # Periyot (gün)
    last_maintenance: datetime | None = None
    next_maintenance: datetime
    estimated_duration_minutes: int
    assigned_to: str | None = None
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC()))


class MaintenanceTaskExtended(BaseModel):
    """Extended maintenance task with all new fields"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_number: str
    title: str
    description: str
    priority: MaintenancePriority
    status: MaintenanceTaskStatus
    maintenance_type: MaintenanceType
    asset_id: str | None = None
    asset_name: str | None = None
    room_id: str | None = None
    room_number: str | None = None
    reported_by: str
    assigned_to: str | None = None
    estimated_duration_minutes: int | None = None
    actual_duration_minutes: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    on_hold_at: datetime | None = None
    on_hold_reason: str | None = None
    parts_waiting: bool = False
    parts_list: list[str] = []
    photos: list[str] = []  # Photo IDs
    notes: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
