"""
maintenance

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

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    require_op,
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW



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


# ── GET /maintenance/mobile/preventive-maintenance-schedule ──
@router.get("/maintenance/mobile/preventive-maintenance-schedule")
async def get_pm_schedule_mobile(
    days: int = 7,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get preventive maintenance schedule for mobile"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)
    end_date = today + timedelta(days=days)

    # Get scheduled PM tasks
    pm_schedule = []

    # Check equipment maintenance schedules
    async for equipment in db.equipment.find({
        'tenant_id': current_user.tenant_id,
        'next_maintenance_date': {
            '$gte': today,
            '$lte': end_date
        }
    }):
        pm_schedule.append({
            'id': equipment.get('id'),
            'equipment_name': equipment.get('name'),
            'equipment_type': equipment.get('type'),
            'location': equipment.get('location'),
            'next_maintenance_date': equipment.get('next_maintenance_date').isoformat(),
            'maintenance_type': equipment.get('maintenance_type', 'preventive'),
            'frequency': equipment.get('maintenance_frequency', 'monthly'),
            'last_maintenance_date': equipment.get('last_maintenance_date').isoformat() if equipment.get('last_maintenance_date') else None,
            'assigned_technician': equipment.get('assigned_technician'),
            'status': 'scheduled'
        })

    # Sort by date
    pm_schedule.sort(key=lambda x: x['next_maintenance_date'])

    return {
        'pm_schedule': pm_schedule,
        'count': len(pm_schedule),
        'date_range': {
            'from': today.isoformat(),
            'to': end_date.isoformat()
        }
    }
# ── POST /maintenance/mobile/quick-issue ──
@router.post("/maintenance/mobile/quick-issue")
async def create_quick_issue_mobile(
    request: QuickIssueRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Create a quick maintenance issue from mobile"""
    current_user = await get_current_user(credentials)
    room_id = request.room_id
    issue_type = request.issue_type
    description = request.description
    priority = request.priority

    # Validate room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Create maintenance task
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'department': 'maintenance',
        'title': f"{issue_type} - Room {room.get('room_number')}",
        'description': description,
        'issue_type': issue_type,
        'priority': priority,
        'status': 'new',
        'created_at': datetime.now(UTC),
        'created_by': current_user.username,
        'reported_by': current_user.username
    }

    await db.tasks.insert_one(task)

    # If priority is urgent or high, update room status
    if priority in ['urgent', 'high']:
        await db.rooms.update_one(
            {'id': room_id, 'tenant_id': current_user.tenant_id},
            {'$set': {'status': 'maintenance'}}
        )

    return {
        'message': 'Maintenance issue created successfully',
        'task_id': task_id,
        'room_number': room.get('room_number'),
        'issue_type': issue_type,
        'priority': priority
    }
# ── GET /maintenance/mobile/sla-configurations ──
@router.get("/maintenance/mobile/sla-configurations")
async def get_sla_configurations(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get SLA configurations for different priorities"""
    current_user = await get_current_user(credentials)

    configurations = []
    async for config in db.sla_configurations.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }).sort('priority', 1):
        configurations.append({
            'id': config.get('id'),
            'priority': config.get('priority'),
            'response_time_minutes': config.get('response_time_minutes'),
            'resolution_time_minutes': config.get('resolution_time_minutes'),
            'is_active': config.get('is_active', True)
        })

    # If no configurations exist, return defaults
    if not configurations:
        default_slas = [
            {'priority': 'emergency', 'response_time_minutes': 15, 'resolution_time_minutes': 120},
            {'priority': 'urgent', 'response_time_minutes': 30, 'resolution_time_minutes': 240},
            {'priority': 'high', 'response_time_minutes': 60, 'resolution_time_minutes': 480},
            {'priority': 'normal', 'response_time_minutes': 120, 'resolution_time_minutes': 1440},
            {'priority': 'low', 'response_time_minutes': 240, 'resolution_time_minutes': 2880}
        ]
        configurations = default_slas

    return {
        'sla_configurations': configurations,
        'count': len(configurations)
    }
# ── POST /maintenance/mobile/sla-configurations ──
@router.post("/maintenance/mobile/sla-configurations")
async def update_sla_configuration(
    priority: str,
    response_time_minutes: int,
    resolution_time_minutes: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Update or create SLA configuration"""
    current_user = await get_current_user(credentials)

    # Check if configuration exists
    existing = await db.sla_configurations.find_one({
        'tenant_id': current_user.tenant_id,
        'priority': priority
    })

    if existing:
        # Update
        await db.sla_configurations.update_one(
            {'id': existing['id'], 'tenant_id': current_user.tenant_id},
            {'$set': {
                'response_time_minutes': response_time_minutes,
                'resolution_time_minutes': resolution_time_minutes,
                'updated_at': datetime.now(UTC)
            }}
        )
        config_id = existing['id']
    else:
        # Create new
        config_id = str(uuid.uuid4())
        await db.sla_configurations.insert_one({
            'id': config_id,
            'tenant_id': current_user.tenant_id,
            'priority': priority,
            'response_time_minutes': response_time_minutes,
            'resolution_time_minutes': resolution_time_minutes,
            'is_active': True,
            'created_at': datetime.now(UTC),
            'updated_at': datetime.now(UTC)
        })

    return {
        'message': 'SLA configuration updated',
        'config_id': config_id,
        'priority': priority,
        'response_time_minutes': response_time_minutes,
        'resolution_time_minutes': resolution_time_minutes
    }
# ── POST /maintenance/mobile/task/{task_id}/status ──
@router.post("/maintenance/mobile/task/{task_id}/status")
async def update_task_status_mobile(
    task_id: str,
    new_status: str,
    reason: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Update task status (complete, on_hold, waiting_parts, in_progress)"""
    current_user = await get_current_user(credentials)

    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC)
    }

    if new_status == 'in_progress':
        if not task.get('started_at'):
            update_data['started_at'] = datetime.now(UTC)

    elif new_status == 'completed':
        update_data['completed_at'] = datetime.now(UTC)

        # Calculate actual duration
        if task.get('started_at'):
            started = task['started_at']
            completed = datetime.now(UTC)
            duration_minutes = int((completed - started).total_seconds() / 60)
            update_data['actual_duration_minutes'] = duration_minutes

    elif new_status == 'on_hold':
        update_data['on_hold_at'] = datetime.now(UTC)
        if reason:
            update_data['on_hold_reason'] = reason

    elif new_status == 'waiting_parts':
        update_data['parts_waiting'] = True
        if reason:
            update_data['on_hold_reason'] = reason

    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    return {
        'message': f'Task status updated to {new_status}',
        'task_id': task_id,
        'new_status': new_status,
        'updated_at': update_data['updated_at'].isoformat()
    }
# ── POST /maintenance/mobile/task/{task_id}/photo ──
@router.post("/maintenance/mobile/task/{task_id}/photo")
async def upload_task_photo_mobile(
    task_id: str,
    photo_data: str,  # Base64 encoded
    photo_type: str,  # before, during, after
    description: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Upload photo for maintenance task"""
    current_user = await get_current_user(credentials)

    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Create photo record
    photo_id = str(uuid.uuid4())
    photo = {
        'id': photo_id,
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'photo_url': photo_data,  # In production, upload to S3/storage
        'photo_type': photo_type,
        'description': description,
        'uploaded_by': current_user.username,
        'uploaded_at': datetime.now(UTC)
    }

    await db.task_photos.insert_one(photo)

    # Update task with photo reference
    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'photos': photo_id}}
    )

    return {
        'message': 'Photo uploaded successfully',
        'photo_id': photo_id,
        'task_id': task_id,
        'photo_type': photo_type
    }
# ── GET /maintenance/mobile/task/{task_id}/photos ──
@router.get("/maintenance/mobile/task/{task_id}/photos")
async def get_task_photos_mobile(
    task_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all photos for a task"""
    current_user = await get_current_user(credentials)

    photos = []
    async for photo in db.task_photos.find({
        'tenant_id': current_user.tenant_id,
        'task_id': task_id
    }).sort('uploaded_at', -1):
        photos.append({
            'id': photo.get('id'),
            'photo_url': photo.get('photo_url'),
            'photo_type': photo.get('photo_type'),
            'description': photo.get('description'),
            'uploaded_by': photo.get('uploaded_by'),
            'uploaded_at': photo.get('uploaded_at').isoformat() if photo.get('uploaded_at') else None
        })

    return {
        'photos': photos,
        'count': len(photos)
    }
# ── GET /maintenance/mobile/spare-parts ──
@router.get("/maintenance/mobile/spare-parts")
async def get_spare_parts_mobile(
    low_stock_only: bool = False,
    warehouse_location: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get spare parts inventory"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if warehouse_location:
        query['warehouse_location'] = warehouse_location

    parts = []
    low_stock_count = 0
    total_value = 0.0

    async for part in db.spare_parts.find(query).sort('part_name', 1):
        current_stock = part.get('current_stock', 0)
        minimum_stock = part.get('minimum_stock', 0)
        is_low_stock = current_stock <= minimum_stock

        if low_stock_only and not is_low_stock:
            continue

        if is_low_stock:
            low_stock_count += 1

        stock_value = current_stock * part.get('unit_price', 0)
        total_value += stock_value

        parts.append({
            'id': part.get('id'),
            'part_number': part.get('part_number'),
            'part_name': part.get('part_name'),
            'description': part.get('description'),
            'category': part.get('category'),
            'warehouse_location': part.get('warehouse_location'),
            'current_stock': current_stock,
            'minimum_stock': minimum_stock,
            'is_low_stock': is_low_stock,
            'unit_price': part.get('unit_price', 0),
            'stock_value': stock_value,
            'supplier': part.get('supplier'),
            'qr_code': part.get('qr_code'),
            'last_restocked': part.get('last_restocked').isoformat() if part.get('last_restocked') else None
        })

    return {
        'spare_parts': parts,
        'summary': {
            'total_count': len(parts),
            'low_stock_count': low_stock_count,
            'total_inventory_value': total_value
        }
    }
# ── POST /maintenance/mobile/spare-parts/use ──
@router.post("/maintenance/mobile/spare-parts/use")
async def use_spare_part_mobile(
    task_id: str,
    spare_part_id: str,
    quantity: int,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Record spare part usage for a task"""
    current_user = await get_current_user(credentials)

    # Validate task
    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Validate spare part
    part = await db.spare_parts.find_one({
        'id': spare_part_id,
        'tenant_id': current_user.tenant_id
    })

    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")

    # Check stock
    current_stock = part.get('current_stock', 0)
    if current_stock < quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {current_stock}, Requested: {quantity}")

    # Calculate cost
    unit_price = part.get('unit_price', 0)
    total_cost = unit_price * quantity

    # Record usage
    usage_id = str(uuid.uuid4())
    usage = {
        'id': usage_id,
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'spare_part_id': spare_part_id,
        'part_name': part.get('part_name'),
        'quantity': quantity,
        'unit_price': unit_price,
        'total_cost': total_cost,
        'used_by': current_user.username,
        'used_at': datetime.now(UTC),
        'notes': notes
    }

    await db.spare_part_usage.insert_one(usage)

    # Update stock
    new_stock = current_stock - quantity
    await db.spare_parts.update_one(
        {'id': spare_part_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'current_stock': new_stock,
            'updated_at': datetime.now(UTC)
        }}
    )

    # Add part to task
    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'parts_list': f"{part.get('part_name')} x{quantity}"}}
    )

    return {
        'message': 'Spare part usage recorded',
        'usage_id': usage_id,
        'part_name': part.get('part_name'),
        'quantity': quantity,
        'total_cost': total_cost,
        'remaining_stock': new_stock,
        'is_low_stock': new_stock <= part.get('minimum_stock', 0)
    }
# ── GET /maintenance/mobile/asset/{asset_id}/history ──
@router.get("/maintenance/mobile/asset/{asset_id}/history")
async def get_asset_history_mobile(
    asset_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get maintenance history for an asset with MTBF calculation"""
    current_user = await get_current_user(credentials)

    # Get maintenance history
    history = []
    total_cost = 0.0
    total_downtime = 0
    corrective_count = 0

    async for record in db.asset_maintenance_history.find({
        'tenant_id': current_user.tenant_id,
        'asset_id': asset_id
    }).sort('completed_at', -1):
        total_cost += record.get('total_cost', 0)
        total_downtime += record.get('downtime_minutes', 0)

        if record.get('maintenance_type') == 'corrective':
            corrective_count += 1

        history.append({
            'id': record.get('id'),
            'task_id': record.get('task_id'),
            'maintenance_type': record.get('maintenance_type'),
            'description': record.get('description'),
            'parts_cost': record.get('parts_cost', 0),
            'labor_cost': record.get('labor_cost', 0),
            'total_cost': record.get('total_cost', 0),
            'technician': record.get('technician'),
            'completed_at': record.get('completed_at').isoformat() if record.get('completed_at') else None,
            'downtime_minutes': record.get('downtime_minutes'),
            'notes': record.get('notes')
        })

    # Calculate MTBF (Mean Time Between Failures)
    mtbf_hours = 0.0
    if corrective_count > 1 and history:
        first_failure = history[-1].get('completed_at') if history else None
        last_failure = history[0].get('completed_at') if history else None

        if first_failure and last_failure:
            from dateutil import parser
            first_dt = parser.isoparse(first_failure)
            last_dt = parser.isoparse(last_failure)
            total_hours = (last_dt - first_dt).total_seconds() / 3600
            mtbf_hours = total_hours / (corrective_count - 1) if corrective_count > 1 else 0

    return {
        'asset_id': asset_id,
        'maintenance_history': history,
        'summary': {
            'total_maintenance_count': len(history),
            'corrective_maintenance_count': corrective_count,
            'preventive_maintenance_count': len(history) - corrective_count,
            'total_cost': total_cost,
            'total_downtime_minutes': total_downtime,
            'total_downtime_hours': round(total_downtime / 60, 2),
            'mtbf_hours': round(mtbf_hours, 2),
            'mtbf_days': round(mtbf_hours / 24, 2)
        }
    }
# ── GET /maintenance/mobile/planned-maintenance ──
@router.get("/maintenance/mobile/planned-maintenance")
async def get_planned_maintenance_mobile(
    upcoming_days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get planned maintenance calendar"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    end_date = today + timedelta(days=upcoming_days)

    planned_items = []
    overdue_count = 0

    async for item in db.planned_maintenance.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }).sort('next_maintenance', 1):
        next_maintenance_date = item.get('next_maintenance')

        if isinstance(next_maintenance_date, str):
            next_maintenance_date = datetime.fromisoformat(next_maintenance_date).date()
        elif isinstance(next_maintenance_date, datetime):
            next_maintenance_date = next_maintenance_date.date()

        if next_maintenance_date <= end_date:
            is_overdue = next_maintenance_date < today
            days_until = (next_maintenance_date - today).days

            if is_overdue:
                overdue_count += 1

            planned_items.append({
                'id': item.get('id'),
                'asset_id': item.get('asset_id'),
                'asset_name': item.get('asset_name'),
                'maintenance_type': item.get('maintenance_type'),
                'frequency_days': item.get('frequency_days'),
                'last_maintenance': item.get('last_maintenance').isoformat() if item.get('last_maintenance') else None,
                'next_maintenance': next_maintenance_date.isoformat(),
                'estimated_duration_minutes': item.get('estimated_duration_minutes'),
                'assigned_to': item.get('assigned_to'),
                'is_overdue': is_overdue,
                'days_until': days_until,
                'notes': item.get('notes')
            })

    return {
        'planned_maintenance': planned_items,
        'summary': {
            'total_count': len(planned_items),
            'overdue_count': overdue_count,
            'upcoming_7days': len([p for p in planned_items if 0 <= p['days_until'] <= 7]),
            'upcoming_30days': len([p for p in planned_items if 0 <= p['days_until'] <= 30])
        }
    }
# ── GET /maintenance/mobile/tasks/filtered ──
@router.get("/maintenance/mobile/tasks/filtered")
async def get_filtered_tasks_mobile(
    status: str | None = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get filtered maintenance tasks"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status
    if priority:
        query['priority'] = priority
    if assigned_to:
        query['assigned_to'] = assigned_to

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter['$lte'] = datetime.fromisoformat(end_date)
        query['created_at'] = date_filter

    tasks = []
    async for task in db.tasks.find(query).sort('created_at', -1).limit(100):
        tasks.append({
            'id': task.get('id'),
            'task_number': task.get('task_number'),
            'title': task.get('title'),
            'description': task.get('description'),
            'priority': task.get('priority'),
            'status': task.get('status'),
            'room_number': task.get('room_number'),
            'assigned_to': task.get('assigned_to'),
            'created_at': task.get('created_at').isoformat() if task.get('created_at') else None,
            'started_at': task.get('started_at').isoformat() if task.get('started_at') else None,
            'completed_at': task.get('completed_at').isoformat() if task.get('completed_at') else None
        })

    return {
        'tasks': tasks,
        'count': len(tasks),
        'filters_applied': {
            'status': status,
            'priority': priority,
            'assigned_to': assigned_to,
            'start_date': start_date,
            'end_date': end_date
        }
    }
