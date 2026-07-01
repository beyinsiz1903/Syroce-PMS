"""Auto-split from schemas.py — domain: fnb."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    MeasurementUnit,
    OrderStatus,
    OutletType,
)


# F&B Management Models
class Outlet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    outlet_type: OutletType
    department: str  # F&B department
    location: str
    capacity: int
    is_active: bool = True
    opening_time: str | None = None
    closing_time: str | None = None
    contact_phone: str | None = None
    manager: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Ingredient(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    category: str  # Meat, Vegetables, Dairy, Beverages, etc.
    unit: MeasurementUnit
    current_stock: float = 0.0
    minimum_stock: float = 0.0
    unit_cost: float = 0.0
    supplier: str | None = None
    last_restocked: datetime | None = None
    expiry_date: datetime | None = None
    storage_location: str = "main_kitchen"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecipeIngredient(BaseModel):
    ingredient_id: str
    ingredient_name: str
    quantity: float
    unit: MeasurementUnit
    cost: float


class Recipe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    menu_item_id: str
    menu_item_name: str
    ingredients: list[RecipeIngredient] = []
    preparation_time_minutes: int
    serving_size: int = 1
    total_cost: float = 0.0
    selling_price: float = 0.0
    profit_margin: float = 0.0
    notes: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    order_number: str
    outlet_id: str
    outlet_name: str
    table_number: str | None = None
    room_number: str | None = None
    order_type: str  # dine_in, room_service, takeaway
    items: list[dict[str, Any]] = []
    subtotal: float = 0.0
    tax: float = 0.0
    service_charge: float = 0.0
    total: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    waiter: str | None = None
    chef: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    ready_at: datetime | None = None
    served_at: datetime | None = None
    notes: str | None = None


class StockConsumption(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    ingredient_id: str
    ingredient_name: str
    consumed_quantity: float


# Marketplace Models
class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str
    description: str
    price: float
    unit: str
    supplier: str
    image_url: str | None = None
    in_stock: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrderCreate(BaseModel):
    items: list[dict[str, Any]]
    total_amount: float
    delivery_address: str


class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    items: list[dict[str, Any]]
    total_amount: float
    status: str = "pending"
    delivery_address: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
