"""
housekeeping

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Mobile

Extracted from legacy_routes.py — Mobile dashboard, GM mobile, department mobile endpoints.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    )

# ============================================================================
# MOBILE ENDPOINTS - Department-Based Mobile Dashboard APIs
# ============================================================================

# Mobile Endpoint Pydantic Models
class ProcessNoShowRequest(BaseModel):
    booking_id: str

class ChangeRoomRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str | None = None

class QuickTaskRequest(BaseModel):
    room_id: str
    task_type: str
    priority: str = 'normal'
    assigned_to: str | None = None
    notes: str | None = None

class QuickIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = 'normal'

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

# --------------------------------------------------------------------------
# GM Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Front Desk Mobile Dashboard Endpoints
# --------------------------------------------------------------------------











# --------------------------------------------------------------------------
# Housekeeping Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Housekeeping Enhanced - Inspection, Lost & Found, Task Assignment, Timer
# --------------------------------------------------------------------------

























# --------------------------------------------------------------------------
# Maintenance Mobile Dashboard Endpoints
# --------------------------------------------------------------------------





# --------------------------------------------------------------------------
# Technical Service Enhancements - SLA, Spare Parts, Task Management
# --------------------------------------------------------------------------























# --------------------------------------------------------------------------
# F&B Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Finance Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["mobile"])


# ── GET /housekeeping/mobile/sla-delayed-rooms ──
@router.get("/housekeeping/mobile/sla-delayed-rooms")
async def get_sla_delayed_rooms_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get rooms with SLA delays for housekeeping mobile"""
    current_user = await get_current_user(credentials)

    # SLA standard: cleaning should complete within 30 minutes
    sla_threshold = timedelta(minutes=30)
    delayed_rooms = []

    now_utc = datetime.now(UTC)
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'task_type': 'cleaning',
        'status': 'in_progress'
    }):
        started_at = task.get('started_at')
        if started_at:
            if isinstance(started_at, str):
                try:
                    started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            duration = now_utc - started_at
            if duration > sla_threshold:
                room = await db.rooms.find_one({
                    'id': task.get('room_id'),
                    'tenant_id': current_user.tenant_id
                })

                delayed_rooms.append({
                    'task_id': task.get('id'),
                    'room_id': task.get('room_id'),
                    'room_number': room.get('room_number') if room else 'N/A',
                    'assigned_to': task.get('assigned_to'),
                    'started_at': started_at.isoformat(),
                    'duration_minutes': int(duration.total_seconds() / 60),
                    'sla_breach_minutes': int((duration - sla_threshold).total_seconds() / 60),
                    'priority': task.get('priority', 'normal')
                })

    # Sort by breach time (most delayed first)
    delayed_rooms.sort(key=lambda x: x['sla_breach_minutes'], reverse=True)

    return {
        'sla_delayed_rooms': delayed_rooms,
        'count': len(delayed_rooms),
        'sla_threshold_minutes': 30
    }
# ── GET /housekeeping/mobile/team-assignments ──
@router.get("/housekeeping/mobile/team-assignments")
async def get_team_assignments_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get team assignment overview for housekeeping mobile"""
    current_user = await get_current_user(credentials)

    # Get all active housekeeping staff
    staff_assignments = {}

    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['assigned', 'in_progress']},
        'assigned_to': {'$exists': True, '$ne': None}
    }):
        staff_name = task.get('assigned_to')

        if staff_name not in staff_assignments:
            staff_assignments[staff_name] = {
                'staff_name': staff_name,
                'assigned_rooms': [],
                'total_tasks': 0,
                'completed_today': 0,
                'in_progress': 0
            }

        room = await db.rooms.find_one({
            'id': task.get('room_id'),
            'tenant_id': current_user.tenant_id
        })

        staff_assignments[staff_name]['assigned_rooms'].append({
            'room_number': room.get('room_number') if room else 'N/A',
            'task_type': task.get('task_type'),
            'status': task.get('status'),
            'priority': task.get('priority')
        })

        staff_assignments[staff_name]['total_tasks'] += 1

        if task.get('status') == 'in_progress':
            staff_assignments[staff_name]['in_progress'] += 1

    # Get completed tasks today for each staff
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)

    for staff_name in staff_assignments:
        completed_count = await db.housekeeping_tasks.count_documents({
            'tenant_id': current_user.tenant_id,
            'assigned_to': staff_name,
            'status': 'completed',
            'completed_at': {'$gte': today}
        })
        staff_assignments[staff_name]['completed_today'] = completed_count

    return {
        'team_assignments': list(staff_assignments.values()),
        'total_staff': len(staff_assignments)
    }
# ── POST /housekeeping/mobile/quick-task ──
@router.post("/housekeeping/mobile/quick-task")
async def create_quick_task_mobile(
    request: QuickTaskRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Create a quick housekeeping task from mobile"""
    current_user = await get_current_user(credentials)
    room_id = request.room_id
    task_type = request.task_type
    priority = request.priority
    assigned_to = request.assigned_to
    notes = request.notes

    # Validate room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Create task
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'task_type': task_type,
        'priority': priority,
        'status': 'assigned' if assigned_to else 'new',
        'assigned_to': assigned_to,
        'notes': notes,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.housekeeping_tasks.insert_one(task)

    # Update room status if needed
    if task_type == 'cleaning':
        await db.rooms.update_one(
            {'id': room_id, 'tenant_id': current_user.tenant_id},
            {'$set': {'status': 'cleaning'}}
        )

    return {
        'message': 'Task created successfully',
        'task_id': task_id,
        'room_number': room.get('room_number'),
        'task_type': task_type,
        'priority': priority,
        'assigned_to': assigned_to
    }
# ── GET /housekeeping/mobile/inspection-checklist ──
@router.get("/housekeeping/mobile/inspection-checklist")
async def get_inspection_checklist_template(
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get inspection checklist template"""
    await get_current_user(credentials)

    # Default checklist template
    checklist = [
        # Bathroom
        {'area': 'bathroom', 'item': 'Towels (bath, hand, face)', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Toilet paper', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Soap/Shampoo', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Hair dryer', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Cleanliness (sink, shower, toilet)', 'status': 'pending'},

        # Bedroom
        {'area': 'bedroom', 'item': 'Bed linens fresh', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Pillows (quantity)', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Duvet/blanket', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Curtains functional', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Carpet/floor clean', 'status': 'pending'},

        # Minibar
        {'area': 'minibar', 'item': 'Minibar stocked', 'status': 'pending'},
        {'area': 'minibar', 'item': 'Minibar clean', 'status': 'pending'},
        {'area': 'minibar', 'item': 'Glasses/cups clean', 'status': 'pending'},

        # Amenities
        {'area': 'amenities', 'item': 'TV remote working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'AC working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Safe working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Phone working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Light bulbs OK', 'status': 'pending'},

        # General
        {'area': 'general', 'item': 'No damage visible', 'status': 'pending'},
        {'area': 'general', 'item': 'No stains', 'status': 'pending'},
        {'area': 'general', 'item': 'No odors', 'status': 'pending'},
    ]

    return {
        'checklist': checklist,
        'template_name': 'Standard Room Inspection',
        'total_items': len(checklist)
    }
# ── POST /housekeeping/mobile/inspection ──
@router.post("/housekeeping/mobile/inspection")
async def create_room_inspection(
    room_id: str,
    room_number: str,
    inspection_type: str,
    checklist: list[dict[str, Any]],
    photos: list[str] | None = None,
    notes: str | None = None,
    maintenance_required: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Create room inspection record"""
    current_user = await get_current_user(credentials)

    inspection_id = str(uuid.uuid4())

    # Check for issues
    issues_found = []
    for item in checklist:
        if item.get('status') in ['missing', 'damaged', 'dirty']:
            issues_found.append(f"{item.get('area')}: {item.get('item')} - {item.get('status')}")

    # Create maintenance task if needed
    maintenance_task_id = None
    if maintenance_required and issues_found:
        task_id = str(uuid.uuid4())
        await db.tasks.insert_one({
            'id': task_id,
            'tenant_id': current_user.tenant_id,
            'title': f'Maintenance Required - Room {room_number}',
            'description': '\n'.join(issues_found),
            'priority': 'high',
            'status': 'new',
            'room_id': room_id,
            'room_number': room_number,
            'department': 'maintenance',
            'created_by': current_user.username,
            'created_at': datetime.now(UTC)
        })
        maintenance_task_id = task_id

    # Create inspection record
    inspection = {
        'id': inspection_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room_number,
        'inspection_type': inspection_type,
        'inspector': current_user.username,
        'inspection_status': 'completed' if not maintenance_required else 'failed',
        'checklist': checklist,
        'photos': photos or [],
        'notes': notes,
        'issues_found': issues_found,
        'maintenance_required': maintenance_required,
        'maintenance_task_id': maintenance_task_id,
        'completed_at': datetime.now(UTC),
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.room_inspections.insert_one(inspection)

    return {
        'message': 'Inspection completed',
        'inspection_id': inspection_id,
        'issues_count': len(issues_found),
        'maintenance_required': maintenance_required,
        'maintenance_task_id': maintenance_task_id,
        'status': 'passed' if not issues_found else 'failed'
    }
# ── POST /housekeeping/mobile/lost-found ──
@router.post("/housekeeping/mobile/lost-found")
async def create_lost_found_item(
    item_description: str,
    category: str,
    room_number: str,
    found_location: str,
    photos: list[str] | None = None,
    storage_location: str = "Lost & Found Office",
    storage_number: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Register lost & found item"""
    current_user = await get_current_user(credentials)

    # Generate item number
    count = await db.lost_found_items.count_documents({'tenant_id': current_user.tenant_id})
    item_number = f"LF-{count + 1:05d}"

    item_id = str(uuid.uuid4())
    item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'item_number': item_number,
        'item_description': item_description,
        'category': category,
        'room_number': room_number,
        'found_location': found_location,
        'found_date': datetime.now(UTC),
        'found_by': current_user.username,
        'photos': photos or [],
        'storage_location': storage_location,
        'storage_number': storage_number or item_number,
        'status': 'in_storage',
        'notes': notes,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.lost_found_items.insert_one(item)

    return {
        'message': 'Lost & Found item registered',
        'item_id': item_id,
        'item_number': item_number,
        'storage_number': storage_number or item_number
    }
# ── GET /housekeeping/mobile/lost-found/items ──
@router.get("/housekeeping/mobile/lost-found/items")
async def get_lost_found_items(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get lost & found items"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    items = []
    async for item in db.lost_found_items.find(query).sort('found_date', -1).limit(100):
        items.append({
            'id': item.get('id'),
            'item_number': item.get('item_number'),
            'item_description': item.get('item_description'),
            'category': item.get('category'),
            'room_number': item.get('room_number'),
            'found_location': item.get('found_location'),
            'found_date': item.get('found_date').isoformat() if item.get('found_date') else None,
            'found_by': item.get('found_by'),
            'storage_location': item.get('storage_location'),
            'storage_number': item.get('storage_number'),
            'status': item.get('status'),
            'photos_count': len(item.get('photos', [])),
            'claimed_by': item.get('claimed_by'),
            'claimed_date': item.get('claimed_date').isoformat() if item.get('claimed_date') else None
        })

    # Summary
    summary = {
        'total': len(items),
        'in_storage': len([i for i in items if i['status'] == 'in_storage']),
        'claimed': len([i for i in items if i['status'] == 'claimed']),
        'delivered': len([i for i in items if i['status'] == 'delivered'])
    }

    return {
        'items': items,
        'summary': summary
    }
# ── PUT /housekeeping/mobile/lost-found/{item_id}/claim ──
@router.put("/housekeeping/mobile/lost-found/{item_id}/claim")
async def claim_lost_found_item(
    item_id: str,
    claimed_by: str,
    guest_id: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Mark item as claimed"""
    current_user = await get_current_user(credentials)

    item = await db.lost_found_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.lost_found_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'claimed',
            'claimed_by': claimed_by,
            'guest_id': guest_id,
            'claimed_date': datetime.now(UTC),
            'delivery_notes': notes,
            'updated_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Item marked as claimed',
        'item_id': item_id,
        'item_number': item.get('item_number'),
        'claimed_by': claimed_by
    }
# ── POST /housekeeping/mobile/assign-tasks ──
@router.post("/housekeeping/mobile/assign-tasks")
async def assign_hk_tasks(
    staff_id: str,
    staff_name: str,
    room_ids: list[str],
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Assign rooms to housekeeping staff"""
    current_user = await get_current_user(credentials)

    assignment_id = str(uuid.uuid4())
    assignment = {
        'id': assignment_id,
        'tenant_id': current_user.tenant_id,
        'assignment_date': datetime.now(UTC),
        'staff_id': staff_id,
        'staff_name': staff_name,
        'assigned_rooms': room_ids,
        'room_count': len(room_ids),
        'status': 'assigned',
        'assigned_by': current_user.username,
        'notes': notes,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.hk_task_assignments.insert_one(assignment)

    # Update rooms status
    await db.rooms.update_many(
        {
            'id': {'$in': room_ids},
            'tenant_id': current_user.tenant_id
        },
        {'$set': {
            'assigned_to': staff_name,
            'assigned_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Tasks assigned successfully',
        'assignment_id': assignment_id,
        'staff_name': staff_name,
        'room_count': len(room_ids)
    }
# ── GET /housekeeping/mobile/staff-assignments ──
@router.get("/housekeeping/mobile/staff-assignments")
async def get_staff_assignments(
    assignment_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get staff task assignments"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if assignment_date:
        date_obj = datetime.fromisoformat(assignment_date).date()
        start_of_day = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(date_obj, datetime.max.time()).replace(tzinfo=UTC)
        query['assignment_date'] = {'$gte': start_of_day, '$lte': end_of_day}
    else:
        # Today
        today = datetime.now(UTC).date()
        start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)
        query['assignment_date'] = {'$gte': start_of_day, '$lte': end_of_day}

    assignments = []
    async for assignment in db.hk_task_assignments.find(query).sort('assignment_date', -1):
        # Get room details
        rooms = []
        async for room in db.rooms.find({
            'id': {'$in': assignment.get('assigned_rooms', [])},
            'tenant_id': current_user.tenant_id
        }):
            rooms.append({
                'room_id': room.get('id'),
                'room_number': room.get('room_number'),
                'status': room.get('status')
            })

        assignments.append({
            'assignment_id': assignment.get('id'),
            'staff_id': assignment.get('staff_id'),
            'staff_name': assignment.get('staff_name'),
            'room_count': assignment.get('room_count'),
            'rooms': rooms,
            'status': assignment.get('status'),
            'assigned_by': assignment.get('assigned_by'),
            'assignment_date': assignment.get('assignment_date').isoformat() if assignment.get('assignment_date') else None
        })

    return {
        'assignments': assignments,
        'total_staff': len(assignments),
        'total_rooms': sum(a['room_count'] for a in assignments)
    }
# ── POST /housekeeping/mobile/cleaning/start ──
@router.post("/housekeeping/mobile/cleaning/start")
async def start_cleaning_timer(
    room_id: str,
    room_number: str,
    task_type: str = "checkout",
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Start cleaning timer"""
    current_user = await get_current_user(credentials)

    # Check if already started
    existing = await db.cleaning_timers.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'status': 'in_progress'
    })

    if existing:
        return {
            'message': 'Timer already running',
            'timer_id': existing.get('id'),
            'started_at': existing.get('started_at').isoformat()
        }

    timer_id = str(uuid.uuid4())
    timer = {
        'id': timer_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room_number,
        'staff_id': current_user.id,
        'staff_name': current_user.username,
        'task_type': task_type,
        'started_at': datetime.now(UTC),
        'status': 'in_progress'
    }

    await db.cleaning_timers.insert_one(timer)

    # Update room status
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'cleaning'}}
    )

    return {
        'message': 'Cleaning started',
        'timer_id': timer_id,
        'room_number': room_number,
        'started_at': timer['started_at'].isoformat()
    }
# ── POST /housekeeping/mobile/cleaning/stop ──
@router.post("/housekeeping/mobile/cleaning/stop")
async def stop_cleaning_timer(
    room_id: str,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Stop cleaning timer"""
    current_user = await get_current_user(credentials)

    timer = await db.cleaning_timers.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'status': 'in_progress'
    })

    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    completed_at = datetime.now(UTC)
    duration = (completed_at - timer['started_at']).total_seconds() / 60

    await db.cleaning_timers.update_one(
        {'id': timer['id'], 'tenant_id': current_user.tenant_id},
        {'$set': {
            'completed_at': completed_at,
            'duration_minutes': int(duration),
            'status': 'completed',
            'notes': notes
        }}
    )

    # Update room status
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'clean'}}
    )

    return {
        'message': 'Cleaning completed',
        'room_number': timer.get('room_number'),
        'duration_minutes': int(duration),
        'started_at': timer['started_at'].isoformat(),
        'completed_at': completed_at.isoformat()
    }
# ── POST /housekeeping/mobile/report-maintenance ──
@router.post("/housekeeping/mobile/report-maintenance")
async def report_maintenance_from_hk(
    room_id: str,
    room_number: str,
    issue_type: str,
    description: str,
    priority: str = "normal",
    photos: list[str] | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Report maintenance issue from housekeeping"""
    current_user = await get_current_user(credentials)

    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'task_number': f'MAINT-HK-{task_id[:8]}',
        'title': f'{issue_type} - Room {room_number}',
        'description': description,
        'priority': priority,
        'status': 'new',
        'room_id': room_id,
        'room_number': room_number,
        'department': 'maintenance',
        'reported_by': current_user.username,
        'source': 'housekeeping',
        'photos': photos or [],
        'created_at': datetime.now(UTC)
    }

    await db.tasks.insert_one(task)

    return {
        'message': 'Maintenance task created',
        'task_id': task_id,
        'task_number': task['task_number'],
        'priority': priority
    }
# ── GET /housekeeping/mobile/reports/daily ──
@router.get("/housekeeping/mobile/reports/daily")
async def get_hk_daily_report(
    report_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get housekeeping daily report"""
    current_user = await get_current_user(credentials)

    if report_date:
        target_date = datetime.fromisoformat(report_date).date()
    else:
        target_date = datetime.now(UTC).date()

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

    # Room statistics
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    clean_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'clean'})
    dirty_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'dirty'})
    occupied_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'occupied'})

    # Cleaning timers today
    timers = []
    total_duration = 0
    async for timer in db.cleaning_timers.find({
        'tenant_id': current_user.tenant_id,
        'started_at': {'$gte': start_of_day, '$lte': end_of_day},
        'status': 'completed'
    }):
        duration = timer.get('duration_minutes', 0)
        total_duration += duration
        timers.append({
            'room_number': timer.get('room_number'),
            'staff_name': timer.get('staff_name'),
            'task_type': timer.get('task_type'),
            'duration_minutes': duration
        })

    avg_cleaning_time = total_duration / len(timers) if timers else 0

    # Lost & Found today
    lf_count = await db.lost_found_items.count_documents({
        'tenant_id': current_user.tenant_id,
        'found_date': {'$gte': start_of_day, '$lte': end_of_day}
    })

    # Inspections today
    inspection_count = await db.room_inspections.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    })

    # Maintenance reports from HK
    maintenance_count = await db.tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'source': 'housekeeping',
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    })

    return {
        'report_date': target_date.isoformat(),
        'room_statistics': {
            'total_rooms': total_rooms,
            'clean_rooms': clean_rooms,
            'dirty_rooms': dirty_rooms,
            'occupied_rooms': occupied_rooms,
            'cleaning_percentage': (clean_rooms / total_rooms * 100) if total_rooms > 0 else 0
        },
        'cleaning_performance': {
            'rooms_cleaned_today': len(timers),
            'total_cleaning_time_minutes': total_duration,
            'average_cleaning_time_minutes': round(avg_cleaning_time, 1),
            'details': timers
        },
        'lost_and_found': {
            'items_found_today': lf_count
        },
        'quality_control': {
            'inspections_completed': inspection_count
        },
        'maintenance_reports': {
            'issues_reported_today': maintenance_count
        }
    }
