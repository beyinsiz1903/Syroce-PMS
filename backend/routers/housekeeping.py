"""
Housekeeping Router - Room status, tasks, assignments, reports
Extracted from server.py for modularity.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from core.database import db
from core.security import get_current_user
from models.schemas import HousekeepingTask, User
from modules.inventory.services.create_room_block_service import CreateRoomBlockService
from modules.inventory.services.release_room_block_service import ReleaseRoomBlockService

try:
    from domains.pms.room_block_models import BlockStatus, RoomBlock, RoomBlockCreate, RoomBlockUpdate
except ImportError:
    RoomBlock = RoomBlockCreate = RoomBlockUpdate = BlockStatus = None

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["housekeeping"])
security = HTTPBearer()
create_room_block_service = CreateRoomBlockService()
release_room_block_service = ReleaseRoomBlockService()


# ============= HOUSEKEEPING =============

@router.get("/housekeeping/tasks")
@cached(ttl=120, key_prefix="housekeeping_tasks")  # Cache for 2 minutes
async def get_housekeeping_tasks(status: str | None = None, current_user: User = Depends(get_current_user)):
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    tasks = await db.housekeeping_tasks.find(query, {'_id': 0}).to_list(1000)
    enriched = []
    for task in tasks:
        room = await db.rooms.find_one({'id': task['room_id']}, {'_id': 0})
        enriched.append({**task, 'room': room})
    return enriched

@router.post("/housekeeping/tasks")
async def create_housekeeping_task(room_id: str, task_type: str, priority: str = "normal", notes: str | None = None, current_user: User = Depends(get_current_user)):
    task = HousekeepingTask(tenant_id=current_user.tenant_id, room_id=room_id, task_type=task_type, priority=priority, notes=notes)
    task_dict = task.model_dump()
    task_dict['created_at'] = task_dict['created_at'].isoformat()
    await db.housekeeping_tasks.insert_one(task_dict)
    return task

@router.put("/housekeeping/tasks/{task_id}")
async def update_housekeeping_task(task_id: str, status: str | None = None, assigned_to: str | None = None, current_user: User = Depends(get_current_user)):
    updates = {}
    if status:
        updates['status'] = status
        if status == 'in_progress':
            updates['started_at'] = datetime.now(UTC).isoformat()
        elif status == 'completed':
            updates['completed_at'] = datetime.now(UTC).isoformat()
            task = await db.housekeeping_tasks.find_one({'id': task_id}, {'_id': 0})
            if task and task['task_type'] == 'cleaning':
                await db.rooms.update_one({'id': task['room_id']}, {'$set': {'status': 'inspected', 'last_cleaned': datetime.now(UTC).isoformat()}})
    if assigned_to:
        updates['assigned_to'] = assigned_to
    await db.housekeeping_tasks.update_one({'id': task_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    task = await db.housekeeping_tasks.find_one({'id': task_id}, {'_id': 0})
    return task

@router.get("/housekeeping/room-status")
@cached(ttl=60, key_prefix="housekeeping_room_status")  # Cache for 1 minute (real-time data)
async def get_room_status_board(current_user: User = Depends(get_current_user)):
    """Get comprehensive room status board"""
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    status_counts = dict.fromkeys(['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'maintenance', 'out_of_order'], 0)
    for room in rooms:
        status_counts[room['status']] += 1
    return {'rooms': rooms, 'status_counts': status_counts, 'total_rooms': len(rooms)}

@router.get("/housekeeping/due-out")
@cached(ttl=120, key_prefix="hk_due_out")  # Cache for 2 min
async def get_due_out_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests checking out today"""
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)

    # Find bookings checking out today
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    }).to_list(1000)

    due_out_rooms = []
    for booking in bookings:
        try:
            # Handle both datetime and string formats
            checkout = booking.get('check_out')
            if isinstance(checkout, datetime):
                checkout_date = checkout.date()
            elif isinstance(checkout, str):
                checkout_date = datetime.fromisoformat(checkout.replace('Z', '+00:00')).date()
            else:
                continue

            if checkout_date == today or checkout_date == tomorrow:
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})

                due_out_rooms.append({
                    'room_number': room['room_number'] if room else 'N/A',
                    'room_type': room['room_type'] if room else 'N/A',
                    'guest_name': guest['name'] if guest else 'N/A',
                    'checkout_date': checkout.isoformat() if isinstance(checkout, datetime) else checkout,
                    'booking_id': booking['id'],
                    'is_today': checkout_date == today
                })
        except Exception as e:
            print(f"Error processing booking {booking.get('id')}: {e}")
            continue

    return {
        'due_out_rooms': due_out_rooms,
        'count': len(due_out_rooms)
    }

@router.get("/housekeeping/stayovers")
@cached(ttl=120, key_prefix="hk_stayovers")  # Cache for 2 min
async def get_stayover_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests staying beyond today"""
    today = datetime.now(UTC).date()

    # Find checked-in bookings not checking out today
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    }).to_list(1000)

    stayover_rooms = []
    for booking in bookings:
        try:
            # Handle both datetime and string formats
            checkout = booking.get('check_out')
            if isinstance(checkout, datetime):
                checkout_date = checkout.date()
            elif isinstance(checkout, str):
                checkout_date = datetime.fromisoformat(checkout.replace('Z', '+00:00')).date()
            else:
                continue

            if checkout_date > today:
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})

                nights_remaining = (checkout_date - today).days

                stayover_rooms.append({
                    'room_number': room['room_number'] if room else 'N/A',
                    'room_type': room['room_type'] if room else 'N/A',
                    'guest_name': guest['name'] if guest else 'N/A',
                    'checkout_date': checkout.isoformat() if isinstance(checkout, datetime) else checkout,
                    'nights_remaining': nights_remaining,
                    'booking_id': booking['id']
                })
        except Exception as e:
            print(f"Error processing stayover booking {booking.get('id')}: {e}")
            continue

    return {
        'stayover_rooms': stayover_rooms,
        'count': len(stayover_rooms)
    }


@router.get("/housekeeping/room-status-report")
@cached(ttl=120, key_prefix="hk_room_status_report")
async def get_room_status_report(current_user: User = Depends(get_current_user)):
    """Comprehensive room status report with DND, Sleep Out, OOO details"""

    # Get all rooms
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)

    # Calculate summary
    summary = {
        'total_rooms': len(rooms),
        'occupied': sum(1 for r in rooms if r.get('status') == 'occupied'),
        'vacant_clean': sum(1 for r in rooms if r.get('status') in ['available', 'inspected']),
        'vacant_dirty': sum(1 for r in rooms if r.get('status') == 'dirty'),
        'out_of_order': sum(1 for r in rooms if r.get('status') == 'out_of_order'),
        'out_of_service': sum(1 for r in rooms if r.get('status') == 'maintenance')
    }

    # Get DND (Do Not Disturb) rooms - occupied rooms with DND flag
    dnd_rooms = []
    sleep_out_rooms = []
    out_of_order_rooms = []

    # Get current bookings for occupied rooms
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    }, {'_id': 0}).to_list(1000)

    for booking in bookings:
        room = next((r for r in rooms if r.get('id') == booking.get('room_id')), None)
        if not room:
            continue

        guest = await db.guests.find_one({'id': booking.get('guest_id')}, {'_id': 0})
        guest_name = guest.get('name') if guest else 'Unknown'
        room_number = room.get('room_number')

        # Check for DND flag
        if booking.get('dnd_status') or room.get('dnd_status'):
            dnd_since = booking.get('dnd_since') or room.get('dnd_since', datetime.now(UTC).isoformat())
            try:
                dnd_time = datetime.fromisoformat(dnd_since.replace('Z', '+00:00'))
                duration_hours = int((datetime.now(UTC) - dnd_time).total_seconds() / 3600)
            except Exception:
                duration_hours = 0

            dnd_rooms.append({
                'room': room_number,
                'guest': guest_name,
                'dnd_since': dnd_since[:16] if isinstance(dnd_since, str) else dnd_since.strftime('%H:%M'),
                'duration_hours': duration_hours
            })

        # Check for Sleep Out (guest hasn't been in room for 24h+)
        last_activity = booking.get('last_room_activity')
        if last_activity:
            try:
                activity_time = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                hours_since = (datetime.now(UTC) - activity_time).total_seconds() / 3600
                if hours_since > 24:
                    sleep_out_rooms.append({
                        'room': room_number,
                        'guest': guest_name,
                        'last_activity': last_activity[:16] if isinstance(last_activity, str) else last_activity.strftime('%Y-%m-%d %H:%M'),
                        'status': 'suspected'
                    })
            except Exception:
                pass

    # Get Out of Order rooms
    for room in rooms:
        if room.get('status') == 'out_of_order':
            out_of_order_rooms.append({
                'room': room.get('room_number'),
                'reason': room.get('ooo_reason', 'Maintenance required'),
                'since': room.get('ooo_since', 'N/A'),
                'expected_fix': room.get('ooo_until', 'TBD')
            })

    return {
        'summary': summary,
        'dnd_rooms': dnd_rooms,
        'sleep_out': sleep_out_rooms,
        'out_of_order': out_of_order_rooms
    }


@router.get("/housekeeping/staff-performance-detailed")
@cached(ttl=300, key_prefix="hk_staff_perf_detailed")
async def get_staff_performance_detailed(current_user: User = Depends(get_current_user)):
    """Detailed staff performance metrics"""

    # Get completed tasks from last 30 days
    start_date = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': start_date}
    }, {'_id': 0}).to_list(5000)

    # Group by staff
    staff_stats = {}
    for task in tasks:
        staff = task.get('assigned_to', 'Unassigned')
        if staff not in staff_stats:
            staff_stats[staff] = {
                'staff_name': staff,
                'tasks_completed': 0,
                'durations': [],
                'quality_scores': []
            }

        staff_stats[staff]['tasks_completed'] += 1

        # Calculate duration if available
        if task.get('started_at') and task.get('completed_at'):
            try:
                started = datetime.fromisoformat(task['started_at'].replace('Z', '+00:00'))
                completed = datetime.fromisoformat(task['completed_at'].replace('Z', '+00:00'))
                duration = (completed - started).total_seconds() / 60
                staff_stats[staff]['durations'].append(duration)
            except Exception:
                pass

        # Quality score (from inspections or ratings)
        if task.get('quality_score'):
            staff_stats[staff]['quality_scores'].append(task['quality_score'])

    # Calculate final metrics
    staff_performance = []
    for staff, data in staff_stats.items():
        avg_duration = sum(data['durations']) / len(data['durations']) if data['durations'] else 0
        avg_quality = sum(data['quality_scores']) / len(data['quality_scores']) if data['quality_scores'] else 95

        # Performance rating
        if avg_duration > 0:
            speed_rating = 'Fast' if avg_duration < 20 else 'Average' if avg_duration < 30 else 'Slow'
        else:
            speed_rating = 'N/A'

        staff_performance.append({
            'staff_name': staff,
            'tasks_completed': data['tasks_completed'],
            'avg_duration_minutes': round(avg_duration, 1),
            'quality_score': round(avg_quality, 1),
            'speed_rating': speed_rating,
            'efficiency_rating': '⭐⭐⭐⭐⭐' if avg_quality >= 95 and avg_duration < 20 else '⭐⭐⭐⭐' if avg_quality >= 90 else '⭐⭐⭐'
        })

    # Sort by tasks completed
    staff_performance.sort(key=lambda x: x['tasks_completed'], reverse=True)

    return {
        'staff_performance': staff_performance,
        'total_staff': len(staff_performance),
        'total_tasks': sum(s['tasks_completed'] for s in staff_performance)
    }


@router.get("/housekeeping/arrivals")
@cached(ttl=120, key_prefix="hk_arrivals")  # Cache for 2 min
async def get_arrival_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests arriving today"""
    today = datetime.now(UTC).date()

    # Find bookings checking in today
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'pending']}
    }).to_list(1000)

    arrival_rooms = []
    for booking in bookings:
        try:
            # Handle both datetime and string formats
            checkin = booking.get('check_in')
            if isinstance(checkin, datetime):
                checkin_date = checkin.date()
            elif isinstance(checkin, str):
                checkin_date = datetime.fromisoformat(checkin.replace('Z', '+00:00')).date()
            else:
                continue

            if checkin_date == today:
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})

                arrival_rooms.append({
                    'room_number': room['room_number'] if room else 'N/A',
                    'room_type': room['room_type'] if room else 'N/A',
                    'room_status': room['status'] if room else 'unknown',
                    'guest_name': guest['name'] if guest else 'N/A',
                    'checkin_time': checkin.isoformat() if isinstance(checkin, datetime) else checkin,
                    'booking_id': booking['id'],
                    'booking_status': booking['status'],
                    'ready': room['status'] in ['available', 'inspected'] if room else False
                })
        except Exception as e:
            print(f"Error processing arrival booking {booking.get('id')}: {e}")
            continue

    return {
        'arrival_rooms': arrival_rooms,
        'count': len(arrival_rooms),
        'ready_count': sum(1 for r in arrival_rooms if r['ready'])
    }

@router.put("/housekeeping/room/{room_id}/status")
async def update_room_status_hk(
    room_id: str,
    new_status: str,
    notes: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Quick room status update from housekeeping"""
    valid_statuses = ['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'maintenance', 'out_of_order']

    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC).isoformat()
    }

    if notes:
        update_data['hk_notes'] = notes

    await db.rooms.update_one(
        {'id': room_id},
        {'$set': update_data}
    )

    return {
        'message': f'Room {room["room_number"]} status updated to {new_status}',
        'room_number': room['room_number'],
        'new_status': new_status
    }

@router.post("/housekeeping/assign")
async def assign_housekeeping_task(
    room_id: str,
    assigned_to: str,
    task_type: str = 'cleaning',
    priority: str = 'normal',
    notes: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Assign housekeeping task to staff"""
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        assigned_to=assigned_to,
        task_type=task_type,
        priority=priority,
        notes=notes or f"{task_type.title()} for Room {room['room_number']}"
    )

    task_dict = task.model_dump()
    task_dict['created_at'] = task_dict['created_at'].isoformat()
    await db.housekeeping_tasks.insert_one(task_dict)

    return {
        'message': f'Task assigned to {assigned_to}',
        'task': task
    }

# ============= ROOM BLOCKS (OUT OF ORDER / OUT OF SERVICE) =============

@router.get("/pms/room-blocks")
@cached(ttl=300, key_prefix="pms_room_blocks")  # Cache for 5 min
async def get_room_blocks(
    room_id: str | None = None,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get room blocks with optional filters"""
    query = {'tenant_id': current_user.tenant_id}

    if room_id:
        query['room_id'] = room_id

    if status:
        query['status'] = status

    # Date range filtering
    if from_date or to_date:
        date_query = {}
        if from_date:
            # Block overlaps if: block_start <= to_date AND (block_end >= from_date OR block_end is null)
            date_query['start_date'] = {'$lte': to_date if to_date else from_date}
        if to_date:
            # Also check end_date or open-ended blocks
            query['$or'] = [
                {'end_date': {'$gte': from_date if from_date else to_date}},
                {'end_date': None}
            ]

    blocks = await db.room_blocks.find(query, {'_id': 0}).to_list(1000)

    # Enrich with room information
    for block in blocks:
        room = await db.rooms.find_one({'id': block['room_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
        if room:
            block['room_number'] = room['room_number']
            block['room_type'] = room['room_type']

    return {
        'blocks': blocks,
        'count': len(blocks)
    }

@router.post("/pms/room-blocks")
async def create_room_block(
    block_data: RoomBlockCreate,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return await create_room_block_service.create(block_data, current_user, request)

@router.patch("/pms/room-blocks/{block_id}")
async def update_room_block(
    block_id: str,
    block_data: RoomBlockUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an existing room block"""
    block = await db.room_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not block:
        raise HTTPException(status_code=404, detail="Room block not found")

    # Build update dict
    update_data = {}
    changes = {}

    if block_data.reason is not None:
        update_data['reason'] = block_data.reason
        changes['reason'] = {'old': block.get('reason'), 'new': block_data.reason}

    if block_data.details is not None:
        update_data['details'] = block_data.details
        changes['details'] = {'old': block.get('details'), 'new': block_data.details}

    if block_data.start_date is not None:
        update_data['start_date'] = block_data.start_date
        changes['start_date'] = {'old': block.get('start_date'), 'new': block_data.start_date}

    if block_data.end_date is not None:
        update_data['end_date'] = block_data.end_date
        changes['end_date'] = {'old': block.get('end_date'), 'new': block_data.end_date}

    if block_data.allow_sell is not None:
        update_data['allow_sell'] = block_data.allow_sell
        changes['allow_sell'] = {'old': block.get('allow_sell'), 'new': block_data.allow_sell}

    if block_data.status is not None:
        update_data['status'] = block_data.status
        changes['status'] = {'old': block.get('status'), 'new': block_data.status}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update block
    await db.room_blocks.update_one(
        {'id': block_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    # Create audit log
    await db.audit_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.id,
        'user_name': current_user.name,
        'user_role': current_user.role,
        'action': 'UPDATE_ROOM_BLOCK',
        'entity_type': 'room_block',
        'entity_id': block_id,
        'changes': changes,
        'timestamp': datetime.now(UTC).isoformat()
    })

    # Get updated block
    updated_block = await db.room_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    return {
        'message': 'Room block updated successfully',
        'block': updated_block
    }

@router.post("/pms/room-blocks/{block_id}/cancel")
async def cancel_room_block(
    block_id: str,
    request: Request,
    reason: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Release a room block through the semantic inventory service."""
    return await release_room_block_service.release(block_id, current_user, request, reason=reason)

# ============= LOYALTY PROGRAM =============
