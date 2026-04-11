"""
Mobile Domain — Pydantic Schemas
Extracted from mobile_router.py inline models.
"""

from pydantic import BaseModel


class ProcessNoShowRequest(BaseModel):
    booking_id: str


class ChangeRoomRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str | None = None


class QuickTaskRequest(BaseModel):
    room_id: str
    task_type: str
    priority: str = "normal"
    assigned_to: str | None = None
    notes: str | None = None


class QuickIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = "normal"


class QuickOrderItem(BaseModel):
    item_id: str
    quantity: int = 1


class QuickOrderRequest(BaseModel):
    outlet_id: str
    table_number: str | None = None
    items: list[QuickOrderItem] = []
    notes: str | None = None


class MenuPriceUpdateRequest(BaseModel):
    new_price: float
    reason: str | None = None
