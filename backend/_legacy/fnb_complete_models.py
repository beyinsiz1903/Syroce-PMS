"""
F&B Management - Complete Suite  
Recipe Costing, BEO Generator, Kitchen Display, Ingredient Inventory
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid

class Recipe(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    dish_name: str
    category: str  # appetizer, main, dessert, beverage
    ingredients: List[dict] = []  # [{ingredient_id, quantity, unit, cost}]
    total_cost: float = 0.0
    selling_price: float
    gp_percentage: float = 0.0  # Gross Profit %
    portion_size: str
    preparation_time: int  # minutes
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Ingredient(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    category: str  # meat, vegetable, dairy, etc
    unit: str  # kg, liter, piece
    current_stock: float = 0.0
    par_level: float = 0.0
    reorder_point: float = 0.0
    unit_cost: float
    supplier: Optional[str] = None
    last_order_date: Optional[datetime] = None

class BanquetEventOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    event_name: str
    event_date: datetime
    pax: int  # number of guests
    menu_items: List[dict] = []
    setup_details: dict = {}
    av_requirements: List[str] = []
    total_cost: float
    customer_name: str
    status: str = "confirmed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class KitchenOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    order_number: int
    table_number: Optional[str] = None
    room_number: Optional[str] = None
    items: List[dict] = []
    priority: str = "normal"  # urgent, normal, low
    status: str = "pending"  # pending, preparing, ready, served
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ready_at: Optional[datetime] = None
