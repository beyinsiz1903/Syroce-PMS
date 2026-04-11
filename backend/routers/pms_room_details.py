"""
PMS Room Details Enhanced Router — Extended room information.
Extracted from pms.py (Stage 3c-rooms).

Routes:
  GET  /rooms/{room_id}/details-enhanced
  POST /rooms/{room_id}/notes
  POST /rooms/{room_id}/minibar-update

Models:
  RoomNote, MiniBarUpdate
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms-room-details"])


# ── Models ───────────────────────────────────────────────────────────

class RoomNote(BaseModel):
    """Room-specific notes"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    note_type: str  # maintenance, issue, preference, general
    description: str
    priority: str = "normal"
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolved_at: datetime | None = None


class MiniBarUpdate(BaseModel):
    """Mini-bar last update tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    updated_by: str
    items_restocked: dict[str, int] = {}  # {item_name: quantity}
    items_consumed: dict[str, int] = {}
    total_value: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Routes ───────────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/details-enhanced")
@cached(ttl=180, key_prefix="room_details_enhanced")  # Cache for 3 min
async def get_room_details_enhanced(
    room_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced room details including:
    - Room notes (TV issues, pillow requests, etc)
    - Mini-bar last update
    - Next maintenance due
    """
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Get room notes
    notes = []
    async for note in db.room_notes.find({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'resolved': False
    }).sort('created_at', -1).limit(10):
        notes.append({
            'id': note.get('id'),
            'note_type': note.get('note_type'),
            'description': note.get('description'),
            'priority': note.get('priority'),
            'created_by': note.get('created_by'),
            'created_at': note.get('created_at')
        })

    # Get mini-bar last update
    minibar_update = await db.minibar_updates.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id
    }, sort=[('updated_at', -1)])

    minibar_info = None
    if minibar_update:
        updated_at = datetime.fromisoformat(minibar_update.get('updated_at'))
        hours_ago = (datetime.now(UTC) - updated_at).total_seconds() / 3600

        minibar_info = {
            'last_updated': minibar_update.get('updated_at'),
            'hours_ago': round(hours_ago, 1),
            'updated_by': minibar_update.get('updated_by'),
            'items_restocked': minibar_update.get('items_restocked', {}),
            'items_consumed': minibar_update.get('items_consumed', {}),
            'total_value': minibar_update.get('total_value', 0.0),
            'needs_restock': hours_ago > 24
        }

    # Get next maintenance due
    next_maintenance = await db.maintenance_schedule.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['scheduled', 'pending']},
        'scheduled_date': {'$gte': datetime.now(UTC).isoformat()}
    }, sort=[('scheduled_date', 1)])

    maintenance_info = None
    if next_maintenance:
        scheduled_date = datetime.fromisoformat(next_maintenance.get('scheduled_date'))
        days_until = (scheduled_date - datetime.now(UTC)).days

        maintenance_info = {
            'scheduled_date': next_maintenance.get('scheduled_date'),
            'days_until': days_until,
            'maintenance_type': next_maintenance.get('maintenance_type'),
            'description': next_maintenance.get('description'),
            'priority': next_maintenance.get('priority'),
            'is_overdue': days_until < 0
        }

    return {
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'room_type': room.get('room_type'),
        'status': room.get('status'),
        'notes': notes,
        'notes_count': len(notes),
        'minibar': minibar_info,
        'next_maintenance': maintenance_info,
        'alerts': [
            f"Warning: {len(notes)} unresolved room notes" if notes else "No outstanding room issues",
            "Mini-bar needs restock" if minibar_info and minibar_info.get('needs_restock') else None,
            f"Maintenance due in {maintenance_info['days_until']} days" if maintenance_info and maintenance_info['days_until'] <= 7 else None,
            "Maintenance OVERDUE!" if maintenance_info and maintenance_info.get('is_overdue') else None
        ]
    }



@router.post("/rooms/{room_id}/notes")
async def add_room_note(
    room_id: str,
    note_type: str,
    description: str,
    priority: str = "normal",
    current_user: User = Depends(get_current_user)
):
    """Add a note to a room"""
    note = RoomNote(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        note_type=note_type,
        description=description,
        priority=priority,
        created_by=current_user.name
    )

    note_dict = note.model_dump()
    note_dict['created_at'] = note_dict['created_at'].isoformat()
    await db.room_notes.insert_one(note_dict)

    return {'success': True, 'note_id': note.id, 'message': 'Room note added'}



@router.post("/rooms/{room_id}/minibar-update")
async def update_minibar(
    room_id: str,
    items_restocked: dict[str, int] = {},
    items_consumed: dict[str, int] = {},
    total_value: float = 0.0,
    current_user: User = Depends(get_current_user)
):
    """Update mini-bar status"""
    update = MiniBarUpdate(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        updated_by=current_user.name,
        items_restocked=items_restocked,
        items_consumed=items_consumed,
        total_value=total_value
    )

    update_dict = update.model_dump()
    update_dict['updated_at'] = update_dict['updated_at'].isoformat()
    await db.minibar_updates.insert_one(update_dict)

    return {'success': True, 'update_id': update.id, 'message': 'Mini-bar updated'}
