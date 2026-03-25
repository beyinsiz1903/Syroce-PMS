"""
Room Block Models - Out of Order / Out of Service / Maintenance
"""
from typing import Optional

from pydantic import BaseModel, Field

from models.enums import BlockStatus, BlockType


class RoomBlock(BaseModel):
    id: str
    room_id: str
    type: BlockType
    reason: str = Field(..., min_length=1, max_length=200)
    details: Optional[str] = None
    start_date: str  # ISO format date
    end_date: Optional[str] = None  # Nullable for open-ended
    allow_sell: bool = False  # Can room be sold during block?
    created_by: str
    created_at: str
    status: BlockStatus = BlockStatus.ACTIVE

class RoomBlockCreate(BaseModel):
    room_id: str
    type: BlockType
    reason: str = Field(..., min_length=1, max_length=200)
    details: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    allow_sell: bool = False

class RoomBlockUpdate(BaseModel):
    reason: Optional[str] = None
    details: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    allow_sell: Optional[bool] = None
    status: Optional[BlockStatus] = None
