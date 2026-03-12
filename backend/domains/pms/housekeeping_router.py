"""
PMS / Housekeeping Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body, Query, File, UploadFile, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date
import os
import uuid
import random
import logging
import io

from core.database import db
from core.security import (
    get_current_user, security, JWT_SECRET, JWT_ALGORITHM,
    generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    create_audit_log, require_feature, require_module,
    require_super_admin_guard as require_super_admin, require_admin,
    get_tenant_modules, load_tenant_doc,
)
from models.schemas import User, ReportIssueRequest, UploadPhotoRequest
from models.enums import UserRole

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Housekeeping"])


# ── Inline Models ──

class CleaningRequestStatusUpdate(BaseModel):
    status: str  # in_progress, completed, cancelled
    assigned_to: Optional[str] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None


@router.get("/housekeeping/ai/predict-time")
async def predict_cleaning_time(
    schedule_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Flash report otomatik gönderim ayarla"""
    from report_automation import get_report_automation
    from email_service import email_service
    
    automation = get_report_automation(db, email_service)
    schedule = automation.schedule_daily_report(
        current_user.tenant_id,
        schedule_data['recipients'],
        schedule_data.get('send_time', '07:00')
    )
    
    return {
        'success': True,
        'message': 'Flash report otomatik gönderim ayarlandı',
        'send_time': schedule['send_time'],
        'recipients': schedule['recipients']
    }

# ============= HOUSEKEEPING AI =============



@router.post("/housekeeping/ai-assignment")
async def get_ai_room_assignment(
    staff_data: dict,
    current_user: User = Depends(get_current_user)
):
    """AI ile oda dağılımı optimizasyonu"""
    from housekeeping_ai import get_housekeeping_ai
    
    ai = get_housekeeping_ai(db)
    assignments = await ai.optimize_room_assignment(
        current_user.tenant_id,
        staff_data['staff_list']
    )
    
    return {
        'success': True,
        'assignments': assignments,
        'total_rooms': len(assignments),
        'total_estimated_time': sum([a['estimated_minutes'] for a in assignments])
    }



@router.get("/housekeeping/predict-time")
async def predict_cleaning_time(
    room_type: str,
    staff_id: str,
    current_user: User = Depends(get_current_user)
):
    """Temizlik süresi tahmini"""
    from housekeeping_ai import get_housekeeping_ai
    
    ai = get_housekeeping_ai(db)
    prediction = await ai.predict_cleaning_time(room_type, staff_id)
    
    return prediction



@router.post("/housekeeping/upload-photo")
async def upload_room_photo(
    photo: UploadFile = File(...),
    room_id: str = Form(...),
    photo_type: Optional[str] = Form(None),
    legacy_type: Optional[str] = Form(None, alias="type"),
    room_number: Optional[str] = Form(None),
    quality_score: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a housekeeping photo (before/after/issue) with optional quality metadata.
    Stores a base64 inline preview so mobile/desktop apps can show the image instantly.
    """
    file_bytes = await photo.read()
    file_size = len(file_bytes)
    
    # Encode preview for quick rendering if file is reasonably small (<2MB)
    inline_preview = None
    if file_size <= 2_000_000:
        encoded = base64.b64encode(file_bytes).decode('utf-8')
        inline_preview = f"data:{photo.content_type};base64,{encoded}"
    
    # Determine final inspection type
    normalized_type = (photo_type or legacy_type or 'inspection').lower()
    
    # Safe quality score parsing
    parsed_quality = None
    if quality_score is not None:
        try:
            parsed_quality = max(1, min(10, int(quality_score)))
        except (TypeError, ValueError):
            parsed_quality = None
    
    photo_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room_number,
        'photo_type': normalized_type,  # before, after, inspection, issue
        'quality_score': parsed_quality,
        'notes': notes,
        'uploaded_by': current_user.id,
        'uploaded_by_name': current_user.name,
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'file_name': photo.filename,
        'content_type': photo.content_type,
        'size_kb': round(file_size / 1024, 2),
        'storage': 'inline',
        'inline_preview': inline_preview,
        # Placeholder URL until external storage (S3/R2) is configured
        'url': f'/photos/{room_id}_{normalized_type}_{str(uuid.uuid4())[:8]}.jpg'
    }
    
    await db.room_photos.insert_one(photo_record)
    return {
        'success': True,
        'photo_id': photo_record['id'],
        'inline_preview': photo_record['inline_preview'],
        'quality_score': photo_record['quality_score']
    }




@router.get("/housekeeping/photos/feed")
async def get_housekeeping_photo_feed(
    limit: int = 12,
    room_id: Optional[str] = None,
    photo_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Return the most recent housekeeping photos for quick quality control."""
    query = {'tenant_id': current_user.tenant_id}
    if room_id:
        query['room_id'] = room_id
    if photo_type:
        query['photo_type'] = photo_type
    
    limit = max(1, min(limit, 50))
    photos = await db.room_photos.find(query, {'_id': 0}).sort('uploaded_at', -1).to_list(limit)
    return {'photos': photos, 'count': len(photos)}

# Helper functions for push notification delivery


@router.get("/housekeeping/mobile/my-tasks")
@cached(ttl=60, key_prefix="mobile_hk_my_tasks")  # Cache for 1 min
async def get_my_housekeeping_tasks(
    status: str = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("mobile_housekeeping")),
):
    """Get tasks assigned to current user"""
    query = {
        'tenant_id': current_user.tenant_id,
        'assigned_to': current_user.name
    }
    if status:
        query['status'] = status
    
    tasks = await db.housekeeping_tasks.find(
        query,
        {'_id': 0}
    ).sort('priority', -1).to_list(100)
    
    # Enrich with room details
    for task in tasks:
        if task.get('room_id'):
            room = await db.rooms.find_one(
                {'id': task['room_id'], 'tenant_id': current_user.tenant_id},
                {'_id': 0}
            )
            if room:
                task['room_number'] = room['room_number']
                task['room_type'] = room['room_type']
    
    return {'tasks': tasks, 'count': len(tasks)}



@router.post("/housekeeping/mobile/start-task/{task_id}")
async def start_housekeeping_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Start working on a task"""
    task = await db.housekeeping_tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'assigned_to': current_user.name
    })
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await db.housekeeping_tasks.update_one(
        {'id': task_id},
        {
            '$set': {
                'status': 'in_progress',
                'started_at': datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Update room status to cleaning
    if task.get('room_id'):
        await db.rooms.update_one(
            {'id': task['room_id'], 'tenant_id': current_user.tenant_id},
            {'$set': {'room_status': 'cleaning'}}
        )
    
    return {'message': 'Task started successfully'}



@router.post("/housekeeping/mobile/complete-task/{task_id}")
async def complete_housekeeping_task(
    task_id: str,
    notes: str = None,
    photos: list = [],
    current_user: User = Depends(get_current_user)
):
    """Complete a housekeeping task"""
    task = await db.housekeeping_tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'assigned_to': current_user.name
    })
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await db.housekeeping_tasks.update_one(
        {'id': task_id},
        {
            '$set': {
                'status': 'completed',
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'completion_notes': notes,
                'photos': photos
            }
        }
    )
    
    # Update room status based on task type
    if task.get('room_id'):
        new_status = 'inspected' if task.get('task_type') == 'inspection' else 'clean'
        await db.rooms.update_one(
            {'id': task['room_id'], 'tenant_id': current_user.tenant_id},
            {'$set': {'room_status': new_status}}
        )
    
    return {'message': 'Task completed successfully'}



@router.post("/housekeeping/mobile/report-issue")
async def report_housekeeping_issue(
    request: ReportIssueRequest,
    current_user: User = Depends(get_current_user)
):
    """Report maintenance or cleaning issue"""
    issue = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': request.room_id,
        'issue_type': request.issue_type,
        'description': request.description,
        'priority': request.priority,
        'photos': request.photos,
        'status': 'open',
        'reported_by': current_user.name,
        'reported_at': datetime.now(timezone.utc).isoformat()
    }
    
    issue_copy = issue.copy()
    await db.housekeeping_issues.insert_one(issue_copy)
    
    # If maintenance issue, create maintenance task
    if request.issue_type == 'maintenance':
        maintenance_task = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'room_id': request.room_id,
            'task_type': 'maintenance',
            'description': request.description,
            'priority': request.priority,
            'status': 'pending',
            'assigned_to': 'Engineering',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.housekeeping_tasks.insert_one(maintenance_task)
    
    return {'message': 'Issue reported successfully', 'issue_id': issue['id']}



@router.post("/housekeeping/mobile/upload-photo")
async def upload_housekeeping_photo(
    request: UploadPhotoRequest,
    current_user: User = Depends(get_current_user)
):
    """Upload photo for housekeeping task"""
    photo_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_id': request.task_id,
        'photo_data': request.photo_base64[:100] + '...',  # Store truncated for demo
        'uploaded_by': current_user.name,
        'uploaded_at': datetime.now(timezone.utc).isoformat()
    }
    
    photo_copy = photo_record.copy()
    await db.housekeeping_photos.insert_one(photo_copy)
    
    return {'message': 'Photo uploaded successfully', 'photo_id': photo_record['id']}



@router.get("/housekeeping/mobile/room-status/{room_id}")
async def get_mobile_room_status(
    room_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed room status for mobile app"""
    room = await db.rooms.find_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get current booking
    booking = None
    if room.get('current_booking_id'):
        booking = await db.bookings.find_one(
            {'id': room['current_booking_id']},
            {'_id': 0}
        )
    
    # Get pending tasks for this room
    tasks = await db.housekeeping_tasks.find(
        {
            'tenant_id': current_user.tenant_id,
            'room_id': room_id,
            'status': {'$in': ['pending', 'in_progress']}
        },
        {'_id': 0}
    ).to_list(10)
    
    return {
        'room': room,
        'current_booking': booking,
        'pending_tasks': tasks
    }


@router.get("/housekeeping/task-timing")
async def get_task_timing_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    staff_member: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get housekeeping task timing and duration analysis
    - Cleaning duration per room
    - Staff performance comparison
    - Time trends
    """
    # Default to last 30 days
    if not end_date:
        end_dt = datetime.now(timezone.utc)
    else:
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    
    if not start_date:
        start_dt = end_dt - timedelta(days=30)
    else:
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    
    # Get completed tasks with timing
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }
    
    if staff_member:
        match_criteria['assigned_to'] = staff_member
    
    tasks = []
    async for task in db.housekeeping_tasks.find(match_criteria):
        # Calculate duration
        if task.get('started_at') and task.get('completed_at'):
            try:
                started = datetime.fromisoformat(task['started_at'])
                completed = datetime.fromisoformat(task['completed_at'])
                duration_minutes = (completed - started).total_seconds() / 60
            except:
                duration_minutes = None
        else:
            duration_minutes = None
        
        task['duration_minutes'] = duration_minutes
        tasks.append(task)
    
    # Calculate statistics
    total_tasks = len(tasks)
    tasks_with_timing = [t for t in tasks if t.get('duration_minutes')]
    
    if tasks_with_timing:
        avg_duration = sum(t['duration_minutes'] for t in tasks_with_timing) / len(tasks_with_timing)
        min_duration = min(t['duration_minutes'] for t in tasks_with_timing)
        max_duration = max(t['duration_minutes'] for t in tasks_with_timing)
        median_duration = sorted(t['duration_minutes'] for t in tasks_with_timing)[len(tasks_with_timing) // 2]
    else:
        avg_duration = min_duration = max_duration = median_duration = 0
    
    # By staff member
    staff_performance = {}
    for task in tasks_with_timing:
        staff = task.get('assigned_to', 'Unassigned')
        if staff not in staff_performance:
            staff_performance[staff] = {
                'staff_name': staff,
                'total_tasks': 0,
                'durations': []
            }
        staff_performance[staff]['total_tasks'] += 1
        staff_performance[staff]['durations'].append(task['duration_minutes'])
    
    # Calculate staff averages
    staff_stats = []
    for staff, data in staff_performance.items():
        if data['durations']:
            staff_avg = sum(data['durations']) / len(data['durations'])
            staff_stats.append({
                'staff_name': staff,
                'total_tasks': data['total_tasks'],
                'avg_duration_minutes': round(staff_avg, 1),
                'min_duration_minutes': round(min(data['durations']), 1),
                'max_duration_minutes': round(max(data['durations']), 1),
                'efficiency_rating': 'Fast' if staff_avg < 20 else 'Average' if staff_avg < 30 else 'Slow'
            })
    
    # Sort by avg duration (fastest first)
    staff_stats.sort(key=lambda x: x['avg_duration_minutes'])
    
    # By task type
    task_type_stats = {}
    for task in tasks_with_timing:
        task_type = task.get('task_type', 'cleaning')
        if task_type not in task_type_stats:
            task_type_stats[task_type] = []
        task_type_stats[task_type].append(task['duration_minutes'])
    
    task_type_analysis = []
    for task_type, durations in task_type_stats.items():
        task_type_analysis.append({
            'task_type': task_type,
            'count': len(durations),
            'avg_duration_minutes': round(sum(durations) / len(durations), 1),
            'min_duration_minutes': round(min(durations), 1),
            'max_duration_minutes': round(max(durations), 1)
        })
    
    return {
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'staff_filter': staff_member,
        'summary': {
            'total_tasks': total_tasks,
            'tasks_with_timing': len(tasks_with_timing),
            'avg_duration_minutes': round(avg_duration, 1),
            'median_duration_minutes': round(median_duration, 1),
            'min_duration_minutes': round(min_duration, 1),
            'max_duration_minutes': round(max_duration, 1),
            'target_duration_minutes': 25  # Industry standard
        },
        'staff_performance': staff_stats,
        'task_type_analysis': task_type_analysis,
        'performance_insights': [
            f"✅ Average cleaning time: {round(avg_duration, 1)} minutes" if avg_duration < 30 else f"⚠️ Average cleaning time is {round(avg_duration, 1)} minutes (target: 25 min)",
            f"⭐ Top performer: {staff_stats[0]['staff_name']} ({staff_stats[0]['avg_duration_minutes']} min avg)" if staff_stats else None,
            f"📊 {len(staff_stats)} staff members tracked"
        ]
    }




@router.get("/housekeeping/staff-performance-table")
async def get_staff_performance_table(
    period_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """
    Get housekeeping staff performance table
    - Tasks completed
    - Average duration
    - Quality score (based on inspections)
    - Attendance/punctuality
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=period_days)
    
    # Get all completed tasks
    tasks = []
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        tasks.append(task)
    
    # Group by staff
    staff_data = {}
    for task in tasks:
        staff = task.get('assigned_to', 'Unassigned')
        if staff not in staff_data:
            staff_data[staff] = {
                'tasks_completed': 0,
                'durations': [],
                'room_ids': set()
            }
        
        staff_data[staff]['tasks_completed'] += 1
        staff_data[staff]['room_ids'].add(task.get('room_id'))
        
        # Calculate duration
        if task.get('started_at') and task.get('completed_at'):
            try:
                started = datetime.fromisoformat(task['started_at'])
                completed = datetime.fromisoformat(task['completed_at'])
                duration = (completed - started).total_seconds() / 60
                staff_data[staff]['durations'].append(duration)
            except:
                pass
    
    # Get inspection results for quality score
    inspection_scores = {}
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'task_type': 'inspection',
        'completed_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        # In real system, inspection would have a pass/fail or score
        # For now, assume 95% pass rate
        staff = task.get('assigned_to')
        if staff:
            if staff not in inspection_scores:
                inspection_scores[staff] = {'passed': 0, 'total': 0}
            inspection_scores[staff]['total'] += 1
            inspection_scores[staff]['passed'] += 1  # Simulated
    
    # Build performance table
    performance_table = []
    for staff, data in staff_data.items():
        avg_duration = sum(data['durations']) / len(data['durations']) if data['durations'] else 0
        
        # Quality score from inspections
        if staff in inspection_scores:
            quality_score = (inspection_scores[staff]['passed'] / inspection_scores[staff]['total']) * 100
        else:
            quality_score = 95  # Default assumption
        
        # Calculate performance score (weighted)
        # Speed: 40%, Quality: 40%, Quantity: 20%
        speed_score = max(0, 100 - ((avg_duration - 25) * 2)) if avg_duration > 0 else 0
        quantity_score = min(100, (data['tasks_completed'] / period_days) * 10)
        overall_score = (speed_score * 0.4) + (quality_score * 0.4) + (quantity_score * 0.2)
        
        performance_table.append({
            'staff_name': staff,
            'tasks_completed': data['tasks_completed'],
            'rooms_cleaned': len(data['room_ids']),
            'avg_duration_minutes': round(avg_duration, 1),
            'quality_score': round(quality_score, 1),
            'overall_performance_score': round(overall_score, 1),
            'rating': '⭐⭐⭐⭐⭐' if overall_score >= 90 else '⭐⭐⭐⭐' if overall_score >= 80 else '⭐⭐⭐' if overall_score >= 70 else '⭐⭐',
            'tasks_per_day': round(data['tasks_completed'] / period_days, 1)
        })
    
    # Sort by overall score
    performance_table.sort(key=lambda x: x['overall_performance_score'], reverse=True)
    
    return {
        'period_days': period_days,
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'total_staff': len(performance_table),
        'staff_performance': performance_table,
        'summary': {
            'total_tasks_completed': sum(s['tasks_completed'] for s in performance_table),
            'avg_quality_score': round(sum(s['quality_score'] for s in performance_table) / len(performance_table), 1) if performance_table else 0,
            'top_performer': performance_table[0]['staff_name'] if performance_table else None,
            'needs_training': [s['staff_name'] for s in performance_table if s['overall_performance_score'] < 70]
        }
    }




@router.get("/housekeeping/linen-inventory")
async def get_linen_inventory(
    low_stock_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Get linen inventory status
    - Current stock levels
    - Items in use
    - Items in laundry
    - Low stock alerts
    """
    linen_items = []
    async for item in db.linen_inventory.find({
        'tenant_id': current_user.tenant_id
    }):
        total_available = item.get('quantity_in_stock', 0)
        in_use = item.get('quantity_in_use', 0)
        in_laundry = item.get('quantity_in_laundry', 0)
        damaged = item.get('quantity_damaged', 0)
        reorder_level = item.get('reorder_level', 50)
        
        # Calculate status
        is_low_stock = total_available < reorder_level
        stock_percentage = (total_available / reorder_level * 100) if reorder_level > 0 else 100
        
        item_data = {
            'id': item.get('id'),
            'item_type': item.get('item_type'),
            'size': item.get('size'),
            'quantity_in_stock': total_available,
            'quantity_in_use': in_use,
            'quantity_in_laundry': in_laundry,
            'quantity_damaged': damaged,
            'total_quantity': total_available + in_use + in_laundry + damaged,
            'reorder_level': reorder_level,
            'stock_status': 'critical' if stock_percentage < 30 else 'low' if stock_percentage < 50 else 'adequate' if stock_percentage < 80 else 'good',
            'stock_percentage': round(stock_percentage, 1),
            'needs_reorder': is_low_stock,
            'unit_cost': item.get('unit_cost', 0.0),
            'estimated_reorder_cost': item.get('unit_cost', 0.0) * (reorder_level - total_available) if is_low_stock else 0,
            'last_restocked': item.get('last_restocked')
        }
        
        if not low_stock_only or is_low_stock:
            linen_items.append(item_data)
    
    # If no items exist, create default inventory
    if not linen_items:
        default_items = [
            {'item_type': 'bed_sheet', 'size': 'single', 'reorder_level': 100},
            {'item_type': 'bed_sheet', 'size': 'double', 'reorder_level': 150},
            {'item_type': 'bed_sheet', 'size': 'king', 'reorder_level': 80},
            {'item_type': 'pillowcase', 'size': 'standard', 'reorder_level': 200},
            {'item_type': 'duvet_cover', 'size': 'double', 'reorder_level': 100},
            {'item_type': 'bath_towel', 'size': 'large', 'reorder_level': 150},
            {'item_type': 'hand_towel', 'size': 'standard', 'reorder_level': 200},
            {'item_type': 'bathrobe', 'size': 'l', 'reorder_level': 50}
        ]
        
        for default in default_items:
            new_item = LinenInventoryItem(
                tenant_id=current_user.tenant_id,
                item_type=default['item_type'],
                size=default['size'],
                quantity_in_stock=120,  # Starting stock
                quantity_in_use=30,
                quantity_in_laundry=15,
                reorder_level=default['reorder_level'],
                unit_cost=10.0
            )
            
            item_dict = new_item.model_dump()
            item_dict['created_at'] = item_dict['created_at'].isoformat()
            await db.linen_inventory.insert_one(item_dict)
            
            linen_items.append({
                'id': new_item.id,
                'item_type': new_item.item_type,
                'size': new_item.size,
                'quantity_in_stock': new_item.quantity_in_stock,
                'quantity_in_use': new_item.quantity_in_use,
                'quantity_in_laundry': new_item.quantity_in_laundry,
                'quantity_damaged': new_item.quantity_damaged,
                'total_quantity': 165,
                'reorder_level': new_item.reorder_level,
                'stock_status': 'good',
                'stock_percentage': 100.0,
                'needs_reorder': False,
                'unit_cost': new_item.unit_cost,
                'estimated_reorder_cost': 0,
                'last_restocked': None
            })
    
    # Sort by stock percentage (critical items first)
    linen_items.sort(key=lambda x: x['stock_percentage'])
    
    # Calculate summary
    total_items = len(linen_items)
    low_stock_count = sum(1 for item in linen_items if item['needs_reorder'])
    critical_count = sum(1 for item in linen_items if item['stock_status'] == 'critical')
    total_reorder_cost = sum(item['estimated_reorder_cost'] for item in linen_items)
    
    return {
        'total_item_types': total_items,
        'low_stock_items': low_stock_count,
        'critical_items': critical_count,
        'total_reorder_cost': round(total_reorder_cost, 2),
        'inventory': linen_items,
        'alerts': [
            f"🚨 {critical_count} items at critical stock level" if critical_count > 0 else None,
            f"⚠️ {low_stock_count} items need reordering" if low_stock_count > 0 else "✅ All items adequately stocked",
            f"💰 Estimated reorder cost: ${round(total_reorder_cost, 2)}" if total_reorder_cost > 0 else None
        ]
    }




@router.post("/housekeeping/linen-inventory/adjust")
async def adjust_linen_inventory(
    item_id: str,
    adjustment_type: str,  # restock, use, return_from_use, send_to_laundry, return_from_laundry, mark_damaged
    quantity: int,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Adjust linen inventory
    - Restock: Add to stock
    - Use: Move from stock to in-use
    - Return from use: Move from in-use to laundry
    - Return from laundry: Move from laundry to stock
    - Mark damaged: Move to damaged
    """
    item = await db.linen_inventory.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not item:
        raise HTTPException(status_code=404, detail="Linen item not found")
    
    updates = {}
    
    if adjustment_type == 'restock':
        updates['quantity_in_stock'] = item.get('quantity_in_stock', 0) + quantity
        updates['last_restocked'] = datetime.now(timezone.utc).isoformat()
    
    elif adjustment_type == 'use':
        if item.get('quantity_in_stock', 0) < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        updates['quantity_in_stock'] = item.get('quantity_in_stock', 0) - quantity
        updates['quantity_in_use'] = item.get('quantity_in_use', 0) + quantity
    
    elif adjustment_type == 'return_from_use':
        if item.get('quantity_in_use', 0) < quantity:
            raise HTTPException(status_code=400, detail="Insufficient items in use")
        updates['quantity_in_use'] = item.get('quantity_in_use', 0) - quantity
        updates['quantity_in_laundry'] = item.get('quantity_in_laundry', 0) + quantity
    
    elif adjustment_type == 'return_from_laundry':
        if item.get('quantity_in_laundry', 0) < quantity:
            raise HTTPException(status_code=400, detail="Insufficient items in laundry")
        updates['quantity_in_laundry'] = item.get('quantity_in_laundry', 0) - quantity
        updates['quantity_in_stock'] = item.get('quantity_in_stock', 0) + quantity
    
    elif adjustment_type == 'mark_damaged':
        # Can come from any category
        updates['quantity_damaged'] = item.get('quantity_damaged', 0) + quantity
    
    else:
        raise HTTPException(status_code=400, detail="Invalid adjustment type")
    
    # Update database
    await db.linen_inventory.update_one(
        {'id': item_id},
        {'$set': updates}
    )
    
    # Create audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="LINEN_ADJUSTMENT",
        entity_type="linen_inventory",
        entity_id=item_id,
        changes={
            'adjustment_type': adjustment_type,
            'quantity': quantity,
            'notes': notes,
            **updates
        }
    )
    
    return {
        'success': True,
        'message': f'Linen inventory adjusted: {adjustment_type}',
        'item_id': item_id,
        'updates': updates
    }


# ============= ROOM DETAILS ENHANCEMENTS =============

# ============= GUEST PROFILE ENHANCEMENTS =============



@router.get("/housekeeping/mobile/room-assignments")
async def get_room_assignments(
    staff_name: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room assignments showing who is cleaning which room"""
    current_user = await get_current_user(credentials)
    
    # Build query
    query = {
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['pending', 'in_progress']}
    }
    
    if staff_name:
        query['assigned_to'] = staff_name
    
    # Get all active housekeeping tasks
    assignments = []
    async for task in db.housekeeping_tasks.find(query):
        # Get room info
        room = await db.rooms.find_one({'id': task['room_id'], 'tenant_id': current_user.tenant_id})
        
        # Calculate duration if in progress
        duration_minutes = None
        if task.get('started_at') and task['status'] == 'in_progress':
            started_at = task['started_at']
            # Parse string to datetime if needed
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            # Ensure started_at is timezone-aware
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            duration_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
        
        assignments.append({
            'task_id': task['id'],
            'room_number': room.get('room_number') if room else 'N/A',
            'room_type': room.get('room_type') if room else 'N/A',
            'assigned_to': task.get('assigned_to', 'Unassigned'),
            'task_type': task.get('task_type'),
            'status': task['status'],
            'priority': task.get('priority', 'normal'),
            'started_at': task.get('started_at'),
            'duration_minutes': round(duration_minutes, 1) if duration_minutes else None
        })
    
    return {
        'assignments': assignments,
        'total_count': len(assignments)
    }



@router.get("/housekeeping/cleaning-time-statistics")
async def get_cleaning_time_statistics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room cleaning time statistics by staff member"""
    current_user = await get_current_user(credentials)
    
    # Date range
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        # Default to last 30 days
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
    
    # Get completed tasks
    completed_tasks = []
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': start, '$lte': end},
        'started_at': {'$exists': True}
    }):
        if task.get('started_at') and task.get('completed_at'):
            duration_minutes = (task['completed_at'] - task['started_at']).total_seconds() / 60
            completed_tasks.append({
                'assigned_to': task.get('assigned_to', 'Unknown'),
                'task_type': task.get('task_type'),
                'duration_minutes': duration_minutes
            })
    
    # Group by staff member
    staff_stats = {}
    for task in completed_tasks:
        staff_name = task['assigned_to']
        if staff_name not in staff_stats:
            staff_stats[staff_name] = {
                'total_tasks': 0,
                'total_duration': 0,
                'by_task_type': {}
            }
        
        staff_stats[staff_name]['total_tasks'] += 1
        staff_stats[staff_name]['total_duration'] += task['duration_minutes']
        
        task_type = task['task_type']
        if task_type not in staff_stats[staff_name]['by_task_type']:
            staff_stats[staff_name]['by_task_type'][task_type] = {
                'count': 0,
                'total_duration': 0
            }
        
        staff_stats[staff_name]['by_task_type'][task_type]['count'] += 1
        staff_stats[staff_name]['by_task_type'][task_type]['total_duration'] += task['duration_minutes']
    
    # Calculate averages
    statistics = []
    for staff_name, stats in staff_stats.items():
        avg_duration = stats['total_duration'] / stats['total_tasks'] if stats['total_tasks'] > 0 else 0
        
        task_type_avg = {}
        for task_type, type_stats in stats['by_task_type'].items():
            task_type_avg[task_type] = {
                'count': type_stats['count'],
                'avg_duration': round(type_stats['total_duration'] / type_stats['count'], 1) if type_stats['count'] > 0 else 0
            }
        
        statistics.append({
            'staff_name': staff_name,
            'total_tasks_completed': stats['total_tasks'],
            'avg_cleaning_time_minutes': round(avg_duration, 1),
            'by_task_type': task_type_avg
        })
    
    # Sort by total tasks
    statistics.sort(key=lambda x: x['total_tasks_completed'], reverse=True)
    
    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat()
        },
        'statistics': statistics,
        'total_staff_members': len(statistics)
    }

# ===== 3. GUEST PROFILE ENHANCEMENTS =====



@router.get("/housekeeping/cleaning-requests")
async def get_cleaning_requests(
    status: Optional[str] = None,  # pending, in_progress, completed
    priority: Optional[str] = None,  # normal, urgent
    current_user: User = Depends(get_current_user)
):
    """
    Get all cleaning requests for housekeeping staff
    """
    try:
        filter_dict = {'tenant_id': current_user.tenant_id}
        
        if status:
            filter_dict['status'] = status
        
        if priority:
            filter_dict['priority'] = priority
        
        # Get cleaning requests
        requests = await db.cleaning_requests.find(filter_dict, {'_id': 0}).sort('requested_at', -1).to_list(100)
        
        # Categorize by status
        pending = [r for r in requests if r['status'] == 'pending']
        in_progress = [r for r in requests if r['status'] == 'in_progress']
        completed_today = [r for r in requests if r['status'] == 'completed' and r.get('completed_at', '').startswith(datetime.now(timezone.utc).date().isoformat())]
        
        return {
            'requests': requests,
            'count': len(requests),
            'pending_count': len(pending),
            'in_progress_count': len(in_progress),
            'completed_today_count': len(completed_today),
            'urgent_count': len([r for r in pending if r.get('priority') == 'urgent']),
            'categories': {
                'pending': pending,
                'in_progress': in_progress,
                'completed_today': completed_today
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve cleaning requests: {str(e)}")


# 3. UPDATE CLEANING REQUEST STATUS


@router.put("/housekeeping/cleaning-request/{request_id}/status")
async def update_cleaning_request_status(
    request_id: str,
    update_data: CleaningRequestStatusUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update cleaning request status
    """
    try:
        request = await db.cleaning_requests.find_one({
            'id': request_id,
            'tenant_id': current_user.tenant_id
        }, {'_id': 0})
        
        if not request:
            raise HTTPException(status_code=404, detail="Cleaning request not found")
        
        update_fields = {
            'status': update_data.status,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        if update_data.status == 'in_progress':
            update_fields['assigned_to'] = update_data.assigned_to or current_user.name
            update_fields['started_at'] = datetime.now(timezone.utc).isoformat()
        
        if update_data.status == 'completed':
            update_fields['completed_at'] = datetime.now(timezone.utc).isoformat()
            update_fields['completed_by'] = update_data.completed_by or current_user.name
            
            # Notify guest
            await db.notifications.insert_one({
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'user_id': request['guest_id'],
                'title': 'Oda Temizliği Tamamlandı',
                'message': f'Oda {request["room_number"]} temizliği tamamlandı',
                'type': 'cleaning_completed',
                'priority': 'normal',
                'related_id': request_id,
                'read': False,
                'created_at': datetime.now(timezone.utc).isoformat()
            })
        
        await db.cleaning_requests.update_one(
            {'id': request_id},
            {'$set': update_fields}
        )
        
        return {
            'message': f'Temizlik talebi {update_data.status} olarak güncellendi',
            'request_id': request_id,
            'status': update_data.status,
            'room_number': request['room_number']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cleaning request: {str(e)}")


# 4. GET GUEST'S CLEANING REQUESTS

