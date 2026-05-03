"""
dashboard

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


# ── GET /dashboard/mobile/critical-issues ──
@router.get("/dashboard/mobile/critical-issues")
async def get_critical_issues_mobile(
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent critical issues for GM mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Get critical maintenance tasks
    critical_tasks = []
    async for task in db.tasks.find({
        'tenant_id': current_user.tenant_id,
        'department': 'maintenance',
        'priority': 'urgent',
        'status': {'$ne': 'completed'}
    }).sort('created_at', -1).limit(limit):
        critical_tasks.append({
            'id': task.get('id'),
            'title': task.get('title'),
            'description': task.get('description'),
            'room_number': task.get('room_number'),
            'priority': task.get('priority'),
            'status': task.get('status'),
            'created_at': task.get('created_at'),
            'type': 'maintenance'
        })

    # Get overbooking situations
    today = datetime.now(UTC)
    overbookings = []
    candidate_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': today + timedelta(days=1)},
        'status': 'confirmed'
    }, {'_id': 0, 'id': 1, 'room_id': 1, 'room_number': 1, 'guest_name': 1, 'created_at': 1}).to_list(length=None)
    occupied_room_ids: set = set()
    cb_room_ids = [b.get('room_id') for b in candidate_bookings if b.get('room_id')]
    if cb_room_ids:
        async for r in db.rooms.find(
            {'id': {'$in': cb_room_ids}, 'tenant_id': current_user.tenant_id, 'status': 'occupied'},
            {'_id': 0, 'id': 1},
        ):
            occupied_room_ids.add(r['id'])
    for booking in candidate_bookings:
        if booking.get('room_id') in occupied_room_ids:
            overbookings.append({
                'id': booking.get('id'),
                'title': f"Overbooking - Room {booking.get('room_number')}",
                'description': f"Guest: {booking.get('guest_name')}",
                'room_number': booking.get('room_number'),
                'priority': 'urgent',
                'created_at': booking.get('created_at'),
                'type': 'overbooking'
            })

    # Combine and sort by date
    all_issues = critical_tasks + overbookings[:limit]
    all_issues.sort(key=lambda x: x['created_at'], reverse=True)

    return {
        'critical_issues': all_issues[:limit],
        'total_count': len(all_issues)
    }
# ── GET /dashboard/mobile/recent-complaints ──
@router.get("/dashboard/mobile/recent-complaints")
async def get_recent_complaints_mobile(
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent guest complaints for GM mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Get recent negative feedback/reviews
    complaints = []
    async for feedback in db.feedback.find({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'rating': {'$lte': 3}},
            {'sentiment': 'negative'}
        ]
    }).sort('created_at', -1).limit(limit):
        complaints.append({
            'id': feedback.get('id'),
            'guest_name': feedback.get('guest_name'),
            'rating': feedback.get('rating'),
            'comment': feedback.get('comment', ''),
            'category': feedback.get('category', 'general'),
            'sentiment': feedback.get('sentiment', 'negative'),
            'source': feedback.get('source', 'internal'),
            'created_at': feedback.get('created_at'),
            'status': feedback.get('status', 'new')
        })

    return {
        'complaints': complaints,
        'total_count': len(complaints)
    }
