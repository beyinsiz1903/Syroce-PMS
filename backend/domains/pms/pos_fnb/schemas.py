"""
POS & F&B Domain — Pydantic Schemas
Extracted from pos_fnb_router.py inline models.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class POSCategory(str, Enum):
    FOOD = "food"
    BEVERAGE = "beverage"
    ALCOHOL = "alcohol"
    DESSERT = "dessert"
    APPETIZER = "appetizer"


class POSMenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_name: str
    category: POSCategory
    unit_price: float
    available: bool = True


class POSOrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    item_name: str
    category: POSCategory
    quantity: int
    unit_price: float
    total_price: float


class POSOrderItemRequest(BaseModel):
    item_id: str
    quantity: int = 1


class POSOrderCreateRequest(BaseModel):
    booking_id: Optional[str] = None
    folio_id: Optional[str] = None
    order_items: List[POSOrderItemRequest]


class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: Optional[str] = None
    guest_id: Optional[str] = None
    folio_id: Optional[str] = None
    order_items: List[POSOrderItem]
    subtotal: float
    tax_amount: float
    total_amount: float
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment_type: str
    quantity: int
    reason: str
    notes: Optional[str] = None


class UpdateOrderStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class TableLayout(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    outlet_id: str
    table_number: str
    seats: int
    position_x: float
    position_y: float
    shape: str = "rectangle"
    width: float = 100
    height: float = 100
    status: str = "available"
    current_transaction_id: Optional[str] = None
    server_assigned: Optional[str] = None


class KitchenOrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_id: str
    table_number: str
    item_name: str
    quantity: int
    special_instructions: Optional[str] = None
    station: str
    status: str = "pending"
    priority: str = "normal"
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ready_at: Optional[datetime] = None
    served_at: Optional[datetime] = None


class Alert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    alert_type: str
    priority: str
    title: str
    description: str
    source_module: str
    source_id: Optional[str] = None
    assigned_to: Optional[str] = None
    status: str = "unread"
    action_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read_at: Optional[datetime] = None
