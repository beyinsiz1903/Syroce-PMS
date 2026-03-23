"""
Room Blocks Router — OOO / OOS / Maintenance Management
==========================================================
API for blocking/unblocking rooms using the same room_night_locks
table as bookings (INV-5: single availability truth).

Endpoints:
  POST /api/room-blocks       — Apply a room block
  DELETE /api/room-blocks      — Release a room block
  GET /api/room-blocks         — List active blocks
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user

logger = logging.getLogger("routers.room_blocks")

router = APIRouter(prefix="/api/room-blocks", tags=["Room Blocks"])


class RoomBlockRequest(BaseModel):
    room_id: str
    block_type: str  # "ooo", "oos", "maintenance"
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD (exclusive)
    reason: str = ""


@router.post("")
async def apply_room_block(req: RoomBlockRequest, current_user=Depends(get_current_user)):
    """Block a room for OOO/OOS/Maintenance.
    Uses the same room_night_locks table as bookings (INV-5)."""
    if req.block_type not in ("ooo", "oos", "maintenance"):
        raise HTTPException(status_code=400, detail="block_type must be ooo, oos, or maintenance")

    from core.atomic_booking import apply_room_block
    result = await apply_room_block(
        tenant_id=current_user.tenant_id,
        room_id=req.room_id,
        block_type=req.block_type,
        start_date=req.start_date,
        end_date=req.end_date,
        reason=req.reason,
        actor=str(getattr(current_user, "id", "system")),
    )
    return result


@router.delete("")
async def release_room_block(
    room_id: str,
    block_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """Release an OOO/OOS/Maintenance block."""
    if block_type not in ("ooo", "oos", "maintenance"):
        raise HTTPException(status_code=400, detail="block_type must be ooo, oos, or maintenance")

    from core.atomic_booking import release_room_block
    result = await release_room_block(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        block_type=block_type,
        start_date=start_date,
        end_date=end_date,
        actor=str(getattr(current_user, "id", "system")),
    )
    return result


@router.get("")
async def list_room_blocks(
    room_id: Optional[str] = None,
    block_type: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """List active room blocks."""
    from core.atomic_booking import get_room_blocks
    blocks = await get_room_blocks(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        block_type=block_type,
    )
    return {"blocks": blocks, "count": len(blocks)}
