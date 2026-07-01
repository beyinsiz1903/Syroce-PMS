"""
Channel Manager Domain — Schemas
Request/response models extracted from channel_manager routers.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CMActorType(str, Enum):
    agency = "agency"
    ota = "ota"
    gds = "gds"
    direct = "direct"


class CMEventType(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    confirm = "confirm"
    cancel = "cancel"


class APIKeyModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    prefix: str
    key_hash: str
    actor_type: CMActorType = CMActorType.agency
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_by: str | None = None
    last_used_at: str | None = None
    scopes: list[str] = ["cm:read", "cm:write"]


class CMRestrictions(BaseModel):
    stop_sell: bool = False
    min_stay: int = 1
    cta: bool = False
    ctd: bool = False
    max_stay: int | None = None


class CMRateInfo(BaseModel):
    amount: float | None = None
    currency: str = "TRY"
    tax_included: bool = True
    source: str | None = None
    rate_plan_id: str | None = None
    board_code: str | None = None


class CMARIDay(BaseModel):
    date: str
    available: int
    sold: int
    restrictions: CMRestrictions
    rate: CMRateInfo


class CMARIRoomType(BaseModel):
    room_type_id: str
    name: str
    days: list[CMARIDay]


class CMARIV2Response(BaseModel):
    hotel_id: str
    currency: str = "TRY"
    date_from: str
    date_to: str
    room_types: list[CMARIRoomType]


class CMARIResponseDay(BaseModel):
    date: str
    room_type: str
    available: int
    sold: int
    stop_sell: bool = False
    rate: float | None = None
    currency: str = "TRY"
    rate_source: str | None = None


class CMARIResponse(BaseModel):
    tenant_id: str
    start_date: str
    end_date: str
    days: list[CMARIResponseDay]


class ChannelConnectionCreate(BaseModel):
    channel_name: str
    channel_type: str = "ota"
    api_key: str | None = None
    api_secret: str | None = None
    hotel_id: str | None = None
    property_code: str | None = None
    endpoint_url: str | None = None
    is_active: bool = True
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_restrictions: bool = True


class PermissionCheckRequest(BaseModel):
    resource: str
    action: str
