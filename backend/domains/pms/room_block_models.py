"""
Room Block Models - Out of Order / Out of Service / Maintenance
"""

from pydantic import BaseModel, Field

from models.enums import BlockStatus, BlockType


class RoomBlock(BaseModel):
    id: str
    room_id: str
    type: BlockType
    reason: str = Field(..., min_length=1, max_length=200)
    details: str | None = None
    start_date: str  # ISO format date
    end_date: str | None = None  # Nullable for open-ended
    allow_sell: bool = False  # Can room be sold during block?
    created_by: str
    created_at: str
    status: BlockStatus = BlockStatus.ACTIVE


class RoomBlockCreate(BaseModel):
    room_id: str
    type: BlockType
    reason: str = Field(..., min_length=1, max_length=200)
    details: str | None = None
    start_date: str
    end_date: str | None = None
    allow_sell: bool = False


class RoomBlockUpdate(BaseModel):
    reason: str | None = None
    details: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    allow_sell: bool | None = None
    status: BlockStatus | None = None
