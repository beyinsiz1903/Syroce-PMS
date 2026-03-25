"""
PMS Services Router — Operational service endpoints.
Extracted from pms.py (Stage 3a).

Routes:
  GET  /pms/room-services
  PUT  /pms/room-services/{service_id}
  GET  /pms/staff-tasks
  POST /pms/staff-tasks
  PUT  /pms/staff-tasks/{task_id}
  GET  /pms/allotment-contracts
  POST /pms/allotment-contracts
  POST /pms/allotment-contracts/{contract_id}/release
  GET  /pms/group-reservations
  POST /pms/group-reservations
  GET  /pms/setup-status
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

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

router = APIRouter(prefix="/api", tags=["pms-services"])


# ═══════════════════════════════════════════════════════════════════
# Room Services
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/room-services")
@cached(ttl=300, key_prefix="pms_room_services")  # Cache for 5 min
async def get_hotel_room_services(current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return services


@router.put("/pms/room-services/{service_id}")
async def update_room_service(service_id: str, updates: Dict[str, Any], current_user: User = Depends(get_current_user)):
    if 'status' in updates and updates['status'] == 'completed':
        updates['completed_at'] = datetime.now(timezone.utc).isoformat()
    await db.room_services.update_one({'id': service_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    service = await db.room_services.find_one({'id': service_id}, {'_id': 0})
    return service


# ═══════════════════════════════════════════════════════════════════
# Staff Tasks
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/staff-tasks")
async def get_staff_tasks(
    department: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get staff tasks (engineering, housekeeping, maintenance)"""
    query = {'tenant_id': current_user.tenant_id}
    if department:
        query['department'] = department
    if status:
        query['status'] = status

    tasks = await db.staff_tasks.find(query, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return tasks


@router.post("/pms/staff-tasks")
async def create_staff_task(
    task_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create a new staff task"""
    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_type': task_data.get('task_type', 'maintenance'),
        'department': task_data.get('department', 'engineering'),
        'title': task_data.get('title', 'Staff Task'),
        'room_id': task_data.get('room_id'),
        'priority': task_data.get('priority', 'normal'),
        'description': task_data.get('description'),
        'assigned_to': task_data.get('assigned_to'),
        'status': task_data.get('status', 'pending'),
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    # Get room number if room_id provided
    if task['room_id']:
        room = await db.rooms.find_one({'id': task['room_id']}, {'_id': 0, 'room_number': 1})
        if room:
            task['room_number'] = room['room_number']

    await db.staff_tasks.insert_one(task)

    # Return the task without MongoDB ObjectId
    return {
        'id': task['id'],
        'tenant_id': task['tenant_id'],
        'task_type': task['task_type'],
        'department': task['department'],
        'title': task['title'],
        'room_id': task['room_id'],
        'room_number': task.get('room_number'),
        'priority': task['priority'],
        'description': task['description'],
        'assigned_to': task['assigned_to'],
        'status': task['status'],
        'created_by': task['created_by'],
        'created_at': task['created_at']
    }


@router.put("/pms/staff-tasks/{task_id}")
async def update_staff_task(
    task_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update staff task status"""
    await db.staff_tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    # Return updated task
    updated_task = await db.staff_tasks.find_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )

    if not updated_task:
        raise HTTPException(status_code=404, detail="Task not found")

    return updated_task


# ═══════════════════════════════════════════════════════════════════
# Allotment Contracts
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/allotment-contracts")
async def get_allotment_contracts(
    current_user: User = Depends(get_current_user)
):
    """Get tour operator allotment contracts with dynamic usage count"""
    contracts = await db.allotment_contracts.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    # Dynamically calculate used_rooms from active bookings
    ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
    for contract in contracts:
        room_type = contract.get('room_type')
        start_date = contract.get('start_date')
        end_date = contract.get('end_date')
        if room_type and start_date and end_date:
            # Find rooms of this type
            room_ids = []
            async for room in db.rooms.find(
                {"tenant_id": current_user.tenant_id, "room_type": room_type},
                {"_id": 0, "id": 1}
            ):
                room_ids.append(room["id"])

            if room_ids:
                used = await db.bookings.count_documents({
                    "tenant_id": current_user.tenant_id,
                    "room_id": {"$in": room_ids},
                    "status": {"$in": ACTIVE_STATUSES},
                    "check_in": {"$lt": end_date},
                    "check_out": {"$gt": start_date},
                })
                contract['used_rooms'] = used

    return contracts


@router.post("/pms/allotment-contracts")
async def create_allotment_contract(
    contract_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create new allotment contract"""
    contract = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'tour_operator': contract_data.get('tour_operator'),
        'room_type': contract_data.get('room_type'),
        'allocated_rooms': contract_data.get('allocated_rooms'),
        'used_rooms': 0,
        'start_date': contract_data.get('start_date'),
        'end_date': contract_data.get('end_date'),
        'rate': contract_data.get('rate'),
        'release_days': contract_data.get('release_days', 7),
        'status': 'active',
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    await db.allotment_contracts.insert_one(contract)
    contract.pop('_id', None)
    return contract


@router.post("/pms/allotment-contracts/{contract_id}/release")
async def release_allotment_rooms(
    contract_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release unused allotment rooms back to inventory"""
    contract = await db.allotment_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    available_rooms = contract['allocated_rooms'] - contract.get('used_rooms', 0)

    await db.allotment_contracts.update_one(
        {'id': contract_id},
        {'$set': {
            'released_rooms': available_rooms,
            'released_at': datetime.now(timezone.utc).isoformat()
        }}
    )

    return {
        "message": f"Released {available_rooms} rooms",
        "released_rooms": available_rooms
    }


# ═══════════════════════════════════════════════════════════════════
# Group Reservations
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/group-reservations")
async def get_group_reservations(current_user: User = Depends(get_current_user)):
    groups = await db.group_reservations.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    return {'groups': groups}


@router.post("/pms/group-reservations")
async def create_group_reservation(
    group_data: dict,
    current_user: User = Depends(get_current_user)
):
    group = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **group_data,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.group_reservations.insert_one(group)
    group.pop('_id', None)
    return group


# ═══════════════════════════════════════════════════════════════════
# Setup Status
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/setup-status")
async def pms_setup_status(current_user: User = Depends(get_current_user)):
    """Return minimal setup status for PMS Lite onboarding (rooms/bookings counts)."""
    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})
    return {"rooms_count": rooms_count, "bookings_count": bookings_count}
