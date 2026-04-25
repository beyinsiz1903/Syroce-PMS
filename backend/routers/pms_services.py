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
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW
from modules.pms_core.role_permission_service import require_op  # v101 DW

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

# noqa: cache-rbac — oda servis kayıtları operasyonel (FO/HK/restoran/manager/admin)
@router.get("/pms/room-services")
@cached(ttl=300, key_prefix="pms_room_services")  # Cache for 5 min
async def get_hotel_room_services(current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return services


_ROOM_SERVICE_UPDATE_ALLOWED = {
    "service_type", "description", "status", "priority", "assigned_to",
    "scheduled_at", "completed_at", "notes", "amount", "quantity",
    "room_id", "guest_id", "metadata",
}

@router.put("/pms/room-services/{service_id}")
async def update_room_service(service_id: str, updates: dict[str, Any], current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="Gecersiz guncelleme verisi")
    safe = {k: v for k, v in updates.items() if k in _ROOM_SERVICE_UPDATE_ALLOWED}
    if not safe:
        raise HTTPException(status_code=400, detail="Guncellenecek izinli alan yok")
    if safe.get('status') == 'completed':
        safe['completed_at'] = datetime.now(UTC).isoformat()
    await db.room_services.update_one({'id': service_id, 'tenant_id': current_user.tenant_id}, {'$set': safe})
    service = await db.room_services.find_one({'id': service_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not service:
        raise HTTPException(status_code=404, detail="Hizmet bulunamadi")
    return service


# ═══════════════════════════════════════════════════════════════════
# Staff Tasks
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/staff-tasks")
async def get_staff_tasks(
    department: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get staff tasks (engineering, housekeeping, maintenance)"""
    query = {'tenant_id': current_user.tenant_id}
    if department:
        query['department'] = department
    if status:
        query['status'] = status

    total = await db.staff_tasks.count_documents(query)
    skip = (page - 1) * page_size
    tasks = await db.staff_tasks.find(query, {'_id': 0}).sort('created_at', -1).skip(skip).limit(page_size).to_list(page_size)
    return {'tasks': tasks, 'total': total, 'page': page, 'page_size': page_size}


@router.post("/pms/staff-tasks")
async def create_staff_task(
    task_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
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
        'created_at': datetime.now(UTC).isoformat()
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
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


@router.delete("/pms/staff-tasks/{task_id}")
async def delete_staff_task(task_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    result = await db.staff_tasks.delete_one({'id': task_id, 'tenant_id': current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {'success': True, 'message': 'Staff task deleted'}


# ═══════════════════════════════════════════════════════════════════
# Allotment Contracts
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/allotment-contracts")
async def get_allotment_contracts(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get tour operator allotment contracts with dynamic usage count.

    `used_rooms` is calculated by matching active bookings to the contract via:
      - room_type matches contract.room_type
      - check-in/out overlaps contract date range
      - status is active (pending/confirmed/guaranteed/checked_in)
      - tour_operator name matches one of the booking's agency/channel fields
        (agency_name, channel_display, channel, source_channel, ota_channel)
        OR the booking is explicitly linked via allotment_contract_id.
    Also returns `total_revenue` and `bookings_count` for reporting.
    """
    import re
    query = {'tenant_id': current_user.tenant_id}
    total = await db.allotment_contracts.count_documents(query)
    skip = (page - 1) * page_size
    contracts = await db.allotment_contracts.find(query, {'_id': 0}).skip(skip).limit(page_size).to_list(page_size)

    ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
    for contract in contracts:
        room_type = contract.get('room_type')
        start_date = contract.get('start_date')
        end_date = contract.get('end_date')
        tour_operator = (contract.get('tour_operator') or '').strip()
        contract_id = contract.get('id')

        # Defaults if calculation can't run
        contract.setdefault('used_rooms', 0)
        contract['bookings_count'] = 0
        contract['total_revenue'] = 0.0

        # Need at least date range + (tour_operator OR contract_id) to attribute bookings
        if not (room_type and start_date and end_date):
            continue
        if not tour_operator and not contract_id:
            continue

        # Find rooms of this type
        room_ids = []
        async for room in db.rooms.find(
            {"tenant_id": current_user.tenant_id, "room_type": room_type},
            {"_id": 0, "id": 1}
        ):
            room_ids.append(room["id"])
        if not room_ids:
            continue

        # Build $or: explicit allotment_contract_id link AND/OR
        # case-insensitive substring match on operator name across agency/channel fields.
        match_or = []
        if contract_id:
            match_or.append({"allotment_contract_id": contract_id})
        if tour_operator:
            op_regex = re.escape(tour_operator)
            match_or.extend([
                {"agency_name": {"$regex": op_regex, "$options": "i"}},
                {"channel_display": {"$regex": op_regex, "$options": "i"}},
                {"channel": {"$regex": op_regex, "$options": "i"}},
                {"source_channel": {"$regex": op_regex, "$options": "i"}},
                {"ota_channel": {"$regex": op_regex, "$options": "i"}},
            ])

        # Single aggregation: count + revenue server-side (no cursor iteration)
        pipeline = [
            {"$match": {
                "tenant_id": current_user.tenant_id,
                "room_id": {"$in": room_ids},
                "status": {"$in": ACTIVE_STATUSES},
                "check_in": {"$lt": end_date},
                "check_out": {"$gt": start_date},
                "$or": match_or,
            }},
            {"$group": {
                "_id": None,
                "count": {"$sum": 1},
                "revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
            }},
        ]
        agg = await db.bookings.aggregate(pipeline).to_list(1)
        if agg:
            used = int(agg[0].get("count") or 0)
            try:
                revenue = float(agg[0].get("revenue") or 0)
            except (TypeError, ValueError):
                revenue = 0.0
            contract['used_rooms'] = used
            contract['bookings_count'] = used
            contract['total_revenue'] = round(revenue, 2)

    return {'contracts': contracts, 'total': total, 'page': page, 'page_size': page_size}


@router.post("/pms/allotment-contracts")
async def create_allotment_contract(
    contract_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
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
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.allotment_contracts.insert_one(contract)
    contract.pop('_id', None)
    return contract


@router.post("/pms/allotment-contracts/{contract_id}/release")
async def release_allotment_rooms(
    contract_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
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
        {'id': contract_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'released_rooms': available_rooms,
            'released_at': datetime.now(UTC).isoformat()
        }}
    )

    return {
        "message": f"Released {available_rooms} rooms",
        "released_rooms": available_rooms
    }


@router.delete("/pms/allotment-contracts/{contract_id}")
async def delete_allotment_contract(contract_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    result = await db.allotment_contracts.delete_one({'id': contract_id, 'tenant_id': current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contract not found")
    return {'success': True, 'message': 'Allotment contract deleted'}


# ═══════════════════════════════════════════════════════════════════
# Group Reservations
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/group-reservations")
async def get_group_reservations(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    total = await db.group_reservations.count_documents(query)
    skip = (page - 1) * page_size
    groups = await db.group_reservations.find(query, {'_id': 0}).skip(skip).limit(page_size).to_list(page_size)
    return {'groups': groups, 'total': total, 'page': page, 'page_size': page_size}


@router.post("/pms/group-reservations")
async def create_group_reservation(
    group_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    # Bug AR (mass-assignment): strip server-controlled keys before spread so
    # caller cannot smuggle id/tenant_id/created_at into the persisted doc.
    from core.helpers import strip_reserved
    group_data = strip_reserved(group_data)
    group = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **group_data,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.group_reservations.insert_one(group)
    group.pop('_id', None)
    return group


@router.delete("/pms/group-reservations/{group_id}")
async def delete_group_reservation(group_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    result = await db.group_reservations.delete_one({'id': group_id, 'tenant_id': current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group reservation not found")
    return {'success': True, 'message': 'Group reservation deleted'}


# ═══════════════════════════════════════════════════════════════════
# Setup Status
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/setup-status")
async def pms_setup_status(current_user: User = Depends(get_current_user)):
    """Return minimal setup status for PMS Lite onboarding (rooms/bookings counts)."""
    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})
    return {"rooms_count": rooms_count, "bookings_count": bookings_count}
