"""
Channel Manager Domain — Schemas
Request/response models extracted from channel_manager routers.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None
    last_used_at: Optional[str] = None
    scopes: List[str] = ["cm:read", "cm:write"]


class CMRestrictions(BaseModel):
    stop_sell: bool = False
    min_stay: int = 1
    cta: bool = False
    ctd: bool = False
    max_stay: Optional[int] = None


class CMRateInfo(BaseModel):
    amount: Optional[float] = None
    currency: str = "TRY"
    tax_included: bool = True
    source: Optional[str] = None
    rate_plan_id: Optional[str] = None
    board_code: Optional[str] = None


class CMARIDay(BaseModel):
    date: str
    available: int
    sold: int
    restrictions: CMRestrictions
    rate: CMRateInfo


class CMARIRoomType(BaseModel):
    room_type_id: str
    name: str
    days: List[CMARIDay]


class CMARIV2Response(BaseModel):
    hotel_id: str
    currency: str = "TRY"
    date_from: str
    date_to: str
    room_types: List[CMARIRoomType]


class CMARIResponseDay(BaseModel):
    date: str
    room_type: str
    available: int
    sold: int
    stop_sell: bool = False
    rate: Optional[float] = None
    currency: str = "TRY"
    rate_source: Optional[str] = None


class CMARIResponse(BaseModel):
    tenant_id: str
    start_date: str
    end_date: str
    days: List[CMARIResponseDay]


class ChannelConnectionCreate(BaseModel):
    channel_name: str
    channel_type: str = "ota"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    hotel_id: Optional[str] = None
    property_code: Optional[str] = None
    endpoint_url: Optional[str] = None
    is_active: bool = True
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_restrictions: bool = True


class PermissionCheckRequest(BaseModel):
    resource: str
    action: str
