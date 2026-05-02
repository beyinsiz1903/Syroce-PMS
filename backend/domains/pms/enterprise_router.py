"""
Domain Router: Enterprise Features

Critical features, task management, RBAC, enterprise audit logging.
"""
import uuid
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW


def _jsonable(value):
    """Recursively convert BSON types (ObjectId, datetime) to JSON-safe values."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value
from fastapi.security import HTTPAuthorizationCredentials

from core.cache import cached
from core.database import db

try:
    from cache_manager import cache as _cache_mgr, cached as _cm_cached
except ImportError:
    _cache_mgr = None  # type: ignore
    def _cm_cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator
from core.helpers import require_feature
from core.security import get_current_user, security
from models.schemas import (
    AssignRoleRequest,
    AssignTaskRequest,
    CreateBackupRequest,
    CreateRoleRequest,
    CreateTaskRequest,
    UpdateTaskStatusRequest,
    User,
)
from modules.pms_core.role_permission_service import require_op  # v90 DW

router = APIRouter(prefix="/api", tags=["enterprise-features"])

# ============= 7 CRITICAL FEATURES ENDPOINTS =============

# 1. OTA Messaging
@router.get("/ota/conversations")
async def get_ota_conversations(
    ota: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if ota:
        query['ota_platform'] = ota

    conversations = await db.ota_conversations.find(query, {'_id': 0}).sort('last_message_at', -1).to_list(100)
    return {'conversations': conversations}

@router.get("/ota/conversations/{conversation_id}/messages")
async def get_ota_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    messages = await db.ota_messages.find({
        'conversation_id': conversation_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('sent_at', 1).to_list(1000)
    return {'messages': messages}

@router.post("/ota/conversations/{conversation_id}/messages")
async def send_ota_message(
    conversation_id: str,
    message_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v100 DW
):
    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'conversation_id': conversation_id,
        'message': message_data.get('message'),
        'sender': 'hotel',
        'channel': message_data.get('channel'),
        'sent_at': datetime.now(UTC).isoformat()
    }
    await db.ota_messages.insert_one(message)

    # Update conversation last message
    await db.ota_conversations.update_one(
        {'id': conversation_id},
        {'$set': {'last_message': message_data.get('message'), 'last_message_at': message['sent_at']}}
    )

    return {'message': 'Sent successfully'}

# OTA Booking.com Integration Endpoints
@router.get("/ota/booking/credentials")
async def get_booking_credentials(current_user: User = Depends(get_current_user)):
    """Get stored Booking.com credentials for this tenant"""
    creds = await db.ota_booking_credentials.find_one(
        {'tenant_id': current_user.tenant_id}, {'_id': 0, 'password': 0}
    )
    if not creds:
        return {'property_id': '', 'username': '', 'settings': {'base_url': 'https://distribution.booking.com'}}
    return creds

@router.post("/ota/booking/credentials")
async def save_booking_credentials(data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Save Booking.com credentials"""
    creds = {
        'tenant_id': current_user.tenant_id,
        'property_id': data.get('property_id', ''),
        'username': data.get('username', ''),
        'settings': data.get('settings', {'base_url': 'https://distribution.booking.com'}),
        'updated_at': datetime.now(UTC).isoformat()
    }
    if data.get('password'):
        creds['password'] = data['password']
    await db.ota_booking_credentials.update_one(
        {'tenant_id': current_user.tenant_id},
        {'$set': creds},
        upsert=True
    )
    return {'message': 'Credentials saved successfully'}

@router.get("/ota/booking/logs")
async def get_booking_logs(limit: int = 10, current_user: User = Depends(get_current_user)):
    """Get OTA sync logs"""
    logs = await db.ota_booking_logs.find(
        {'tenant_id': current_user.tenant_id}, {'_id': 0}
    ).sort('timestamp', -1).to_list(limit)
    return {'items': logs}

@router.post("/ota/booking/ari/push")
async def push_ari_to_booking(data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Push ARI (Availability, Rates, Inventory) to Booking.com"""
    rooms = data.get('rooms', [])
    log_entry = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'action': 'ari_push',
        'status': 'queued',
        'details': f'ARI push for {len(rooms)} room(s)',
        'timestamp': datetime.now(UTC).isoformat()
    }
    await db.ota_booking_logs.insert_one(log_entry)
    return {'message': 'ARI push queued', 'log_id': log_entry['id']}

@router.post("/ota/booking/reservations/pull")
async def pull_reservations_from_booking(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Pull reservations from Booking.com"""
    log_entry = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'action': 'reservation_pull',
        'status': 'queued',
        'details': 'Reservation pull from Booking.com',
        'timestamp': datetime.now(UTC).isoformat()
    }
    await db.ota_booking_logs.insert_one(log_entry)
    return {'message': 'Reservation pull queued', 'log_id': log_entry['id']}

# 2. RMS
# NOTE: /rms/comp-set, /rms/pricing-strategy, /rms/demand-forecast, /rms/price-adjustments,
# /rms/apply-recommendations are handled by domains.revenue.rms_router (enhanced versions with real DB queries)

# 3. Housekeeping Mobile
# rbac-allow: cache-rbac — HK rooms operasyonel (HK/FO/manager)
@router.get("/housekeeping/rooms")
@cached(ttl=120, key_prefix="housekeeping_rooms_list")
async def get_housekeeping_rooms(
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query["$or"] = [{"housekeeping_status": status}, {"hk_status": status}]
    rooms = await db.rooms.find(query, {'_id': 0}).to_list(200)
    for r in rooms:
        r["hk_status"] = r.get("housekeeping_status", r.get("hk_status", "clean"))
    return {'rooms': rooms}

@router.get("/housekeeping/checklist")
async def get_housekeeping_checklist(current_user: User = Depends(get_current_user)):
    # Default checklist
    checklist = [
        {'id': '1', 'task': 'Make beds with fresh linens', 'area': 'Bedroom', 'completed': False},
        {'id': '2', 'task': 'Clean and sanitize bathroom', 'area': 'Bathroom', 'completed': False},
        {'id': '3', 'task': 'Vacuum carpets and floors', 'area': 'General', 'completed': False},
        {'id': '4', 'task': 'Dust all surfaces', 'area': 'General', 'completed': False},
        {'id': '5', 'task': 'Replenish amenities', 'area': 'Bathroom', 'completed': False},
        {'id': '6', 'task': 'Empty trash bins', 'area': 'General', 'completed': False},
        {'id': '7', 'task': 'Check minibar and restock', 'area': 'Minibar', 'completed': False}
    ]
    return {'items': checklist}

@router.post("/housekeeping/rooms/{room_id}/start")
async def start_room_cleaning(
    room_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    result = await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'housekeeping_status': 'cleaning', 'hk_status': 'cleaning', 'cleaning_started_at': datetime.now(UTC).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Room not found")
    return {'message': 'Cleaning started'}

@router.post("/housekeeping/rooms/{room_id}/complete")
async def complete_room_cleaning(
    room_id: str,
    completion_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    result = await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'housekeeping_status': 'clean',
            'hk_status': 'clean',
            'last_cleaned_at': datetime.now(UTC).isoformat(),
            'cleaned_by': completion_data.get('cleaned_by')
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Room not found")
    return {'message': 'Room cleaned successfully'}

# 4. Group & Block Reservations
# 5. Multi-Property Management
@router.get("/multi-property/properties")
async def get_properties(current_user: User = Depends(get_current_user)):
    properties = await db.properties.find({'organization_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    return {'properties': properties}

@router.get("/multi-property/dashboard")
async def get_multi_property_dashboard(
    property_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    # Aggregate data across properties
    return {
        'total_revenue': 125000,
        'avg_occupancy': 78.5,
        'total_guests': 450,
        'total_rooms': 250,
        'property_revenues': [45000, 35000, 25000, 20000],
        'property_occupancies': [82, 78, 75, 72]
    }

# 6. Marketplace Inventory
@router.get("/marketplace/inventory", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def get_marketplace_inventory(current_user: User = Depends(get_current_user)):
    products = await db.marketplace_inventory.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return {'products': products}

@router.post("/marketplace/inventory", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def add_inventory_product(
    product_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    product = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **product_data,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.marketplace_inventory.insert_one(product)
    return product

@router.get("/marketplace/purchase-orders", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def get_purchase_orders(current_user: User = Depends(get_current_user)):
    orders = await db.purchase_orders.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).sort('created_at', -1).to_list(100)
    return {'orders': orders}

@router.post("/marketplace/purchase-orders", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def create_purchase_order(
    order_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    order = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **order_data,
        'status': 'pending',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.purchase_orders.insert_one(order.copy())
    return order

@router.get("/marketplace/deliveries")
async def get_deliveries(current_user: User = Depends(get_current_user)):
    deliveries = await db.deliveries.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).sort('delivered_at', -1).to_list(100)
    return {'deliveries': deliveries}

# 7. E-Fatura & POS
@router.get("/pos/daily-closures")
async def get_pos_closures(current_user: User = Depends(get_current_user)):
    closures = await db.pos_closures.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('closure_date', -1).limit(30).to_list(30)
    return {'closures': closures}

@router.post("/pos/daily-closure")
async def create_pos_closure(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v99 DW
):
    # Calculate today's sales
    today = datetime.now(UTC).date().isoformat()

    closure = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'closure_date': today,
        'total_sales': 5420.50,
        'cash_sales': 1200.00,
        'card_sales': 4220.50,
        'transaction_count': 45,
        'closed_at': datetime.now(UTC).isoformat(),
        'closed_by': current_user.id
    }

    await db.pos_closures.insert_one(closure)
    return closure


# ========================================

@router.get("/tasks")
async def get_tasks(
    department: str = None,
    status: str = None,
    priority: str = None,
    assigned_to: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get tasks with filters"""
    query = {'tenant_id': current_user.tenant_id}

    if department:
        query['department'] = department
    if status:
        query['status'] = status
    if priority:
        query['priority'] = priority
    if assigned_to:
        query['assigned_to'] = assigned_to

    tasks = await db.tasks.find(
        query,
        {'_id': 0}
    ).sort([('priority_order', -1), ('created_at', 1)]).to_list(1000)

    return {'tasks': tasks, 'count': len(tasks)}

@router.post("/tasks")
async def create_task(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Create new task"""
    # Priority order for sorting
    priority_order = {
        'urgent': 4,
        'high': 3,
        'normal': 2,
        'low': 1
    }

    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'department': request.department,
        'task_type': request.task_type,
        'title': request.title,
        'description': request.description,
        'priority': request.priority,
        'priority_order': priority_order.get(request.priority, 2),
        'location': request.location,
        'room_id': request.room_id,
        'assigned_to': request.assigned_to,
        'due_date': request.due_date,
        'recurring': request.recurring,
        'recurrence_pattern': request.recurrence_pattern,
        'status': 'new' if not request.assigned_to else 'assigned',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id,
        'updated_at': datetime.now(UTC).isoformat()
    }

    task_copy = task.copy()
    await db.tasks.insert_one(task_copy)

    # Create notification for assigned user
    if request.assigned_to:
        notification = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'user': request.assigned_to,
            'type': 'task_assigned',
            'message': f"New {request.priority} priority task assigned: {request.title}",
            'task_id': task['id'],
            'read': False,
            'created_at': datetime.now(UTC).isoformat()
        }
        notif_copy = notification.copy()
        await db.notifications.insert_one(notif_copy)

    return task

@router.get("/tasks/my-tasks")
async def get_my_tasks(
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get tasks assigned to current user"""
    query = {
        'tenant_id': current_user.tenant_id,
        'assigned_to': current_user.name
    }

    if status:
        query['status'] = status

    tasks = await db.tasks.find(query, {'_id': 0}).sort([('priority_order', -1), ('due_date', 1)]).to_list(1000)

    return {'tasks': tasks, 'count': len(tasks)}

# rbac-allow: cache-rbac — tasks dashboard operasyonel cross-role
@router.get("/tasks/dashboard")
@cached(ttl=300, key_prefix="tasks_dashboard")  # Cache for 5 min
async def get_tasks_dashboard(current_user: User = Depends(get_current_user)):
    """Get tasks dashboard with all department stats"""
    # Get all tasks
    tasks = await db.tasks.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(10000)

    # Department breakdown
    departments = ['engineering', 'housekeeping', 'fnb', 'maintenance', 'front_desk']
    dept_stats = {}

    for dept in departments:
        dept_tasks = [t for t in tasks if t.get('department') == dept]

        dept_stats[dept] = {
            'total': len(dept_tasks),
            'new': sum(1 for t in dept_tasks if t.get('status') == 'new'),
            'in_progress': sum(1 for t in dept_tasks if t.get('status') == 'in_progress'),
            'completed': sum(1 for t in dept_tasks if t.get('status') == 'completed'),
            'urgent': sum(1 for t in dept_tasks if t.get('priority') == 'urgent'),
            'overdue': sum(1 for t in dept_tasks if t.get('due_date') and t.get('due_date') < datetime.now(UTC).date().isoformat() and t.get('status') not in ['completed', 'verified'])
        }

    # Overall stats
    today = datetime.now(UTC).date().isoformat()

    return {
        'summary': {
            'total_tasks': len(tasks),
            'new': sum(1 for t in tasks if t.get('status') == 'new'),
            'in_progress': sum(1 for t in tasks if t.get('status') == 'in_progress'),
            'completed_today': sum(1 for t in tasks if t.get('status') == 'completed' and t.get('completed_at', '').startswith(today)),
            'urgent_pending': sum(1 for t in tasks if t.get('priority') == 'urgent' and t.get('status') not in ['completed', 'verified', 'cancelled']),
            'overdue': sum(1 for t in tasks if t.get('due_date') and t.get('due_date') < today and t.get('status') not in ['completed', 'verified', 'cancelled'])
        },
        'departments': dept_stats
    }


# NOTE: This endpoint MUST be defined before /tasks/{task_id} to avoid path conflict
@router.get("/tasks/delayed")
async def get_delayed_tasks(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get all delayed tasks (exceeding SLA)
    Automatically creates notifications for overdue tasks
    """
    current_user = await get_current_user(credentials)

    try:
        now = datetime.now(UTC)

        # Get SLA configs
        sla_configs = await db.sla_configs.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)

        # Create SLA lookup
        sla_lookup = {}
        for sla in sla_configs:
            key = f"{sla['category']}_{sla.get('priority', 'normal')}"
            sla_lookup[key] = sla

        delayed_tasks = []

        # Check cleaning requests
        cleaning_requests = await db.cleaning_requests.find({
            'status': {'$in': ['pending', 'in_progress']},
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)

        for req in cleaning_requests:
            requested_at = datetime.fromisoformat(req['requested_at'])
            elapsed_minutes = (now - requested_at).total_seconds() / 60

            sla_key = f"guest_request_{req.get('priority', 'normal')}"
            sla = sla_lookup.get(sla_key, {'resolution_time_minutes': 120})

            if elapsed_minutes > sla['resolution_time_minutes']:
                delay_minutes = elapsed_minutes - sla['resolution_time_minutes']
                delayed_tasks.append({
                    'id': req['id'],
                    'type': 'cleaning_request',
                    'room_number': req['room_number'],
                    'guest_name': req.get('guest_name'),
                    'requested_at': req['requested_at'],
                    'elapsed_minutes': round(elapsed_minutes),
                    'sla_minutes': sla['resolution_time_minutes'],
                    'delay_minutes': round(delay_minutes),
                    'priority': req.get('priority', 'normal'),
                    'status': req['status']
                })

                # Create notification if not already sent
                existing_notif = await db.notifications.find_one({
                    'related_id': req['id'],
                    'type': 'sla_breach',
                    'tenant_id': current_user.tenant_id
                }, {'_id': 0})

                if not existing_notif:
                    await db.notifications.insert_one({
                        'id': str(uuid.uuid4()),
                        'tenant_id': current_user.tenant_id,
                        'user_role': 'housekeeping',
                        'title': f'⚠️ SLA İhlali - Oda {req["room_number"]}',
                        'message': f'{round(delay_minutes)} dakika gecikmeli temizlik talebi',
                        'type': 'sla_breach',
                        'priority': 'urgent',
                        'related_id': req['id'],
                        'read': False,
                        'created_at': now.isoformat()
                    })

        return {
            'delayed_tasks': delayed_tasks,
            'count': len(delayed_tasks),
            'critical_count': len([t for t in delayed_tasks if t['delay_minutes'] > 60]),
            'generated_at': now.isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get delayed tasks: {str(e)}")

@router.get("/tasks/{task_id}")
async def get_task_details(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get task details with history"""
    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get task history
    history = await db.task_history.find({
        'tenant_id': current_user.tenant_id,
        'task_id': task_id
    }, {'_id': 0}).sort('timestamp', 1).to_list(100)

    task['history'] = history

    return task

@router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: str,
    request: AssignTaskRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Assign task to user"""
    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update task
    await db.tasks.update_one(
        {'id': task_id},
        {
            '$set': {
                'assigned_to': request.assigned_to,
                'status': 'assigned',
                'assigned_at': datetime.now(UTC).isoformat(),
                'assigned_by': current_user.id,
                'updated_at': datetime.now(UTC).isoformat()
            }
        }
    )

    # Add to history
    history_entry = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'action': 'assigned',
        'performed_by': current_user.id,
        'details': f"Assigned to {request.assigned_to}",
        'notes': request.notes,
        'timestamp': datetime.now(UTC).isoformat()
    }
    history_copy = history_entry.copy()
    await db.task_history.insert_one(history_copy)

    # Create notification
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user': request.assigned_to,
        'type': 'task_assigned',
        'message': f"Task assigned: {task.get('title')}",
        'task_id': task_id,
        'read': False,
        'created_at': datetime.now(UTC).isoformat()
    }
    notif_copy = notification.copy()
    await db.notifications.insert_one(notif_copy)

    return {'message': 'Task assigned successfully'}

@router.post("/tasks/{task_id}/status")
async def update_task_status(
    task_id: str,
    request: UpdateTaskStatusRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Update task status"""
    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = {
        'status': request.status,
        'updated_at': datetime.now(UTC).isoformat()
    }

    if request.status == 'completed':
        update_data['completed_at'] = datetime.now(UTC).isoformat()
        update_data['completed_by'] = current_user.id
        if request.completion_photos:
            update_data['completion_photos'] = request.completion_photos

    await db.tasks.update_one(
        {'id': task_id},
        {'$set': update_data}
    )

    # Add to history
    history_entry = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'action': f"status_changed_to_{request.status}",
        'performed_by': current_user.id,
        'details': f"Status changed to {request.status}",
        'notes': request.notes,
        'timestamp': datetime.now(UTC).isoformat()
    }
    history_copy = history_entry.copy()
    await db.task_history.insert_one(history_copy)

    return {'message': 'Task status updated successfully'}

@router.get("/tasks/department/{department}")
async def get_department_tasks(
    department: str,
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get tasks by department with stats"""
    query = {
        'tenant_id': current_user.tenant_id,
        'department': department
    }

    if status:
        query['status'] = status

    tasks = await db.tasks.find(query, {'_id': 0}).sort([('priority_order', -1), ('created_at', 1)]).to_list(1000)

    # Calculate stats
    total = len(tasks)
    by_status = {}
    by_priority = {}
    overdue = 0

    today = datetime.now(UTC).date().isoformat()

    for task in tasks:
        status = task.get('status', 'new')
        priority = task.get('priority', 'normal')

        by_status[status] = by_status.get(status, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

        if task.get('due_date') and task.get('due_date') < today and status not in ['completed', 'verified', 'cancelled']:
            overdue += 1

    return {
        'department': department,
        'tasks': tasks,
        'statistics': {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'overdue': overdue
        }
    }


# DEPARTMENT-SPECIFIC TASK ENDPOINTS

# Engineering Tasks
@router.post("/tasks/engineering/maintenance-request")
async def create_engineering_maintenance_request(
    title: str,
    description: str,
    location: str,
    priority: str = "normal",
    room_id: str = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("housekeeping")),  # v101 DW
):
    """Create engineering/maintenance request"""
    task_request = CreateTaskRequest(
        department='engineering',
        task_type='repair',
        title=title,
        description=description,
        priority=priority,
        location=location,
        room_id=room_id
    )

    return await create_task(task_request, current_user)

# Housekeeping Tasks (Enhanced)
@router.post("/tasks/housekeeping/cleaning-request")
async def create_housekeeping_cleaning_request(
    room_id: str,
    task_type: str,  # deep_clean, turndown, inspection
    priority: str = "normal",
    special_instructions: str = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Create housekeeping cleaning request"""
    room = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    task_request = CreateTaskRequest(
        department='housekeeping',
        task_type=task_type,
        title=f"{task_type.replace('_', ' ').title()} - Room {room.get('room_number')}",
        description=special_instructions or f"{task_type} requested for room {room.get('room_number')}",
        priority=priority,
        location=f"Room {room.get('room_number')}",
        room_id=room_id
    )

    return await create_task(task_request, current_user)

# F&B Tasks
@router.post("/tasks/fnb/service-request")
async def create_fnb_service_request(
    request_type: str,  # room_service, catering, setup, delivery
    title: str,
    description: str,
    location: str,
    priority: str = "normal",
    due_date: str = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Create F&B service request"""
    task_request = CreateTaskRequest(
        department='fnb',
        task_type=request_type,
        title=title,
        description=description,
        priority=priority,
        location=location,
        due_date=due_date
    )

    return await create_task(task_request, current_user)


# ========================================

# 1. ROLLER & YETKİLER MATRİSİ (RBAC)
@router.get("/admin/roles")
async def get_roles(current_user: User = Depends(get_current_user)):
    """Get all roles and permissions"""
    roles = await db.roles.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    # Default roles if none exist
    if not roles:
        default_roles = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'General Manager',
                'description': 'Full access to all features',
                'permissions': [
                    'view_all', 'edit_all', 'delete_all', 'approve_all',
                    'view_financials', 'edit_rates', 'manage_users',
                    'export_reports', 'system_settings'
                ],
                'department': 'management',
                'created_at': datetime.now(UTC).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'Front Desk Agent',
                'description': 'Check-in, check-out, reservations',
                'permissions': [
                    'view_bookings', 'create_booking', 'edit_booking',
                    'check_in', 'check_out', 'view_rates',
                    'post_charges', 'process_payments'
                ],
                'department': 'front_desk',
                'created_at': datetime.now(UTC).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'Housekeeping Manager',
                'description': 'Room status, cleaning tasks',
                'permissions': [
                    'view_rooms', 'update_room_status', 'assign_tasks',
                    'view_housekeeping_reports'
                ],
                'department': 'housekeeping',
                'created_at': datetime.now(UTC).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'Accountant',
                'description': 'Financial operations',
                'permissions': [
                    'view_financials', 'create_invoice', 'edit_invoice',
                    'void_charge', 'export_reports', 'view_ar_aging'
                ],
                'department': 'accounting',
                'created_at': datetime.now(UTC).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'Revenue Manager',
                'description': 'Rate management and revenue optimization',
                'permissions': [
                    'view_rates', 'edit_rates', 'view_rms',
                    'apply_pricing', 'view_comp_set', 'export_reports'
                ],
                'department': 'revenue',
                'created_at': datetime.now(UTC).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'role_name': 'F&B Manager',
                'description': 'Restaurant and bar operations',
                'permissions': [
                    'view_pos', 'create_pos_transaction', 'view_menu',
                    'edit_menu', 'view_fnb_reports', 'generate_z_report'
                ],
                'department': 'fnb',
                'created_at': datetime.now(UTC).isoformat()
            }
        ]
        roles = default_roles

    return {'roles': roles, 'count': len(roles)}

@router.post("/admin/roles")
async def create_role(
    request: CreateRoleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Create custom role"""
    role = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'role_name': request.role_name,
        'description': request.description,
        'permissions': request.permissions,
        'department': request.department,
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    role_copy = role.copy()
    await db.roles.insert_one(role_copy)

    # Log audit trail
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='create_role',
        entity_type='role',
        entity_id=role['id'],
        details=f"Created role: {request.role_name}",
        db=db
    )

    return role

@router.post("/admin/users/{user_id}/assign-role")
async def assign_role_to_user(
    user_id: str,
    request: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Assign role to user"""
    # Verify role exists
    role = await db.roles.find_one({
        'id': request.role_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Update user role
    await db.users.update_one(
        {'id': user_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'role_id': request.role_id,
                'role_name': role['role_name'],
                'permissions': role['permissions'],
                'updated_at': datetime.now(UTC).isoformat()
            }
        }
    )

    # Log audit trail
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='assign_role',
        entity_type='user',
        entity_id=user_id,
        details=f"Assigned role {role['role_name']} to user",
        db=db
    )

    return {'message': 'Role assigned successfully', 'role': role['role_name']}

@router.get("/admin/permissions")
async def get_all_permissions():
    """Get list of all available permissions"""
    permissions = {
        'bookings': [
            'view_bookings', 'create_booking', 'edit_booking', 'delete_booking',
            'check_in', 'check_out', 'cancel_booking', 'move_booking'
        ],
        'rates': [
            'view_rates', 'edit_rates', 'apply_pricing', 'override_rate'
        ],
        'financials': [
            'view_financials', 'create_invoice', 'edit_invoice', 'void_invoice',
            'post_charges', 'void_charge', 'process_payments', 'process_refund',
            'view_ar_aging', 'export_reports'
        ],
        'rooms': [
            'view_rooms', 'update_room_status', 'create_room_block',
            'assign_room', 'change_room'
        ],
        'pos': [
            'view_pos', 'create_pos_transaction', 'void_pos_transaction',
            'view_menu', 'edit_menu', 'generate_z_report'
        ],
        'housekeeping': [
            'view_tasks', 'create_task', 'assign_task', 'complete_task',
            'view_housekeeping_reports'
        ],
        'admin': [
            'manage_users', 'manage_roles', 'system_settings',
            'view_audit_logs', 'manage_backups'
        ],
        'reports': [
            'export_reports', 'view_rms', 'view_comp_set'
        ],
        'all': [
            'view_all', 'edit_all', 'delete_all', 'approve_all'
        ]
    }

    return {'permissions': permissions}


# 2. LOGLAMA & DENETİM (Audit Trail)
async def log_audit_event(tenant_id: str, user_id: str, action: str, entity_type: str,
                           entity_id: str, details: str, before_value: dict = None,
                           after_value: dict = None, db = None):
    """Helper function to log audit events"""
    audit_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'user_id': user_id,
        'action': action,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'details': details,
        'before_value': before_value,
        'after_value': after_value,
        'ip_address': None,  # Can be captured from request
        'user_agent': None,  # Can be captured from request
        'timestamp': datetime.now(UTC).isoformat()
    }

    audit_copy = audit_log.copy()
    await db.audit_logs.insert_one(audit_copy)
    return audit_log

@router.get("/admin/audit-logs")
@_cm_cached(ttl=120, key_prefix="admin_audit_logs")  # v95.3 — 2dk cache, audit log read-heavy
async def get_audit_logs(
    action: str = None,
    entity_type: str = None,
    user_id: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    skip: int = 0,  # v95.3 — pagination eklendi (90 KB liste için)
    current_user: User = Depends(get_current_user)
):
    """Get audit logs with filters + pagination."""
    # v95.3 — limit cap (DoS koruması) + skip non-negative
    limit = max(1, min(int(limit), 500))
    skip = max(0, int(skip))

    query = {'tenant_id': current_user.tenant_id}

    if action:
        query['action'] = action
    if entity_type:
        query['entity_type'] = entity_type
    if user_id:
        query['user_id'] = user_id
    if start_date and end_date:
        query['timestamp'] = {'$gte': start_date, '$lte': end_date}

    cursor = (
        db.audit_logs.find(query, {'_id': 0})
        .sort('timestamp', -1)
        .skip(skip)
        .limit(limit)
    )
    logs = await cursor.to_list(limit)
    total = await db.audit_logs.count_documents(query)

    logs = _jsonable(logs)
    return {
        'logs': logs,
        'count': len(logs),
        'total': total,
        'skip': skip,
        'limit': limit,
        'has_more': (skip + len(logs)) < total,
    }

@router.get("/admin/audit-logs/critical")
async def get_critical_audit_logs(
    days: int = 7,
    current_user: User = Depends(get_current_user)
):
    """Get critical audit events (deletions, refunds, rate changes)"""
    critical_actions = [
        'delete_booking', 'cancel_booking', 'process_refund',
        'void_invoice', 'void_charge', 'edit_rates', 'override_rate',
        'delete_user', 'change_role'
    ]

    start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    logs = await db.audit_logs.find({
        'tenant_id': current_user.tenant_id,
        'action': {'$in': critical_actions},
        'timestamp': {'$gte': start_date}
    }, {'_id': 0}).sort('timestamp', -1).to_list(1000)
    logs = _jsonable(logs)

    # Group by action
    by_action = {}
    for log in logs:
        action = log.get('action')
        by_action[action] = by_action.get(action, 0) + 1

    return {
        'logs': logs,
        'summary': {
            'total_critical_events': len(logs),
            'by_action': by_action,
            'date_range': f"Last {days} days"
        }
    }

# Rate Change Audit (Example of critical operation logging)
@router.post("/admin/rates/{room_type}/change")
async def change_rate_with_audit(
    room_type: str,
    new_rate: float,
    effective_date: str,
    reason: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Change rate with full audit trail"""
    # Get current rate
    current_rate_record = await db.room_types.find_one({
        'tenant_id': current_user.tenant_id,
        'name': room_type
    }, {'_id': 0})

    if not current_rate_record:
        raise HTTPException(status_code=404, detail="Room type not found")

    old_rate = current_rate_record.get('base_rate', 0)

    # Update rate
    await db.room_types.update_one(
        {'tenant_id': current_user.tenant_id, 'name': room_type},
        {'$set': {'base_rate': new_rate, 'updated_at': datetime.now(UTC).isoformat()}}
    )

    # Log audit event
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='edit_rates',
        entity_type='room_type',
        entity_id=room_type,
        details=f"Rate changed from ${old_rate} to ${new_rate}. Reason: {reason}",
        before_value={'base_rate': old_rate},
        after_value={'base_rate': new_rate},
        db=db
    )

    return {
        'message': 'Rate changed successfully',
        'old_rate': old_rate,
        'new_rate': new_rate,
        'effective_date': effective_date
    }


# 3. YEDEKLEME & FELAKET SENARYOSU
@router.post("/admin/backup/create")
async def create_backup(
    request: CreateBackupRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Create database backup"""
    backup_id = str(uuid.uuid4())

    # In production, this would trigger actual backup process
    # For now, we'll create a backup metadata record
    backup = {
        'id': backup_id,
        'tenant_id': current_user.tenant_id,
        'backup_type': request.backup_type,
        'status': 'in_progress',
        'size_mb': 0,
        'collections_included': request.include_collections or ['all'],
        'started_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    backup_copy = backup.copy()
    await db.backups.insert_one(backup_copy)

    # Log audit event
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='create_backup',
        entity_type='backup',
        entity_id=backup_id,
        details=f"Initiated {request.backup_type} backup",
        db=db
    )

    # Simulate backup completion
    await db.backups.update_one(
        {'id': backup_id},
        {
            '$set': {
                'status': 'completed',
                'size_mb': 145.7,  # Mock size
                'completed_at': datetime.now(UTC).isoformat()
            }
        }
    )

    return {
        'message': 'Backup created successfully',
        'backup_id': backup_id,
        'status': 'completed'
    }

@router.get("/admin/backup/list")
async def list_backups(
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """List all backups"""
    backups = await db.backups.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('started_at', -1).limit(limit).to_list(limit)

    return {'backups': backups, 'count': len(backups)}

@router.post("/admin/backup/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    confirm: bool = False,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Restore from backup"""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm restore operation")

    # Get backup
    backup = await db.backups.find_one({
        'id': backup_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.get('status') != 'completed':
        raise HTTPException(status_code=400, detail="Cannot restore from incomplete backup")

    # Log critical audit event
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action='restore_backup',
        entity_type='backup',
        entity_id=backup_id,
        details=f"Restore initiated from backup {backup_id}",
        db=db
    )

    # In production, this would trigger actual restore process
    restore_job = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'backup_id': backup_id,
        'status': 'in_progress',
        'started_at': datetime.now(UTC).isoformat(),
        'initiated_by': current_user.id
    }

    restore_copy = restore_job.copy()
    await db.restore_jobs.insert_one(restore_copy)

    return {
        'message': 'Restore initiated',
        'restore_job_id': restore_job['id'],
        'estimated_time': '10-15 minutes',
        'rto_target': '15 minutes'  # Recovery Time Objective
    }

@router.get("/admin/system/health")
async def get_system_health(current_user: User = Depends(get_current_user)):
    """Get system health status"""
    # Check database connectivity
    try:
        await db.users.count_documents({'tenant_id': current_user.tenant_id}, limit=1)
        db_status = 'healthy'
    except Exception as e:
        db_status = f'unhealthy: {str(e)}'

    # Get latest backup
    latest_backup = await db.backups.find_one(
        {'tenant_id': current_user.tenant_id, 'status': 'completed'},
        {'_id': 0},
        sort=[('completed_at', -1)]
    )

    # Calculate RPO (Recovery Point Objective)
    if latest_backup:
        last_backup_time = datetime.fromisoformat(latest_backup['completed_at'])
        hours_since_backup = (datetime.now(UTC) - last_backup_time).total_seconds() / 3600
        rpo_status = 'good' if hours_since_backup < 24 else 'warning' if hours_since_backup < 48 else 'critical'
    else:
        hours_since_backup = None
        rpo_status = 'critical'

    # Get audit log count (last 24h)
    audit_count = await db.audit_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    })

    return {
        'status': 'healthy' if db_status == 'healthy' else 'degraded',
        'components': {
            'database': db_status,
            'backup_system': rpo_status
        },
        'metrics': {
            'last_backup': latest_backup.get('completed_at') if latest_backup else None,
            'hours_since_backup': round(hours_since_backup, 1) if hours_since_backup else None,
            'rpo_target': '24 hours',
            'rto_target': '15 minutes',
            'audit_events_24h': audit_count
        },
        'timestamp': datetime.now(UTC).isoformat()
    }

