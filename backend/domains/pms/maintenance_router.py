"""
PMS / Maintenance Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import (
    get_current_user,
)
from models.schemas import MaintenanceAsset, MaintenanceWorkOrder, PreventiveMaintenancePlan, SensorAlert, User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Maintenance"])

@router.get("/iot/room-devices/{room_id}")
async def get_room_devices(room_id: str, current_user: User = Depends(get_current_user)):
    """Odadaki akıllı cihazlar"""
    devices = await db.smart_room_devices.find({'room_id': room_id}, {'_id': 0}).to_list(100)
    return {'room_id': room_id, 'devices': devices, 'total': len(devices)}



@router.post("/iot/control-device")
async def control_smart_device(control_data: dict, current_user: User = Depends(get_current_user)):
    """Akıllı cihaz kontrol"""
    command = {
        'device_id': control_data['device_id'],
        'command': control_data['command'],
        'value': control_data.get('value'),
        'executed_at': datetime.now(UTC).isoformat()
    }
    await db.iot_commands.insert_one(command)
    return {'success': True, 'message': 'Cihaz komutu gönderildi (MOCK)'}



@router.get("/iot/energy-consumption")
async def get_energy_consumption(days: int = 30, current_user: User = Depends(get_current_user)):
    """Enerji tüketim raporu"""
    from datetime import timedelta
    start = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    consumption = await db.energy_consumption.find({
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': start}
    }, {'_id': 0}).to_list(1000)

    total_kwh = sum([c.get('consumption_kwh', 0) for c in consumption])
    total_cost = sum([c.get('cost', 0) for c in consumption])

    return {
        'period_days': days,
        'total_kwh': round(total_kwh, 2),
        'total_cost': round(total_cost, 2),
        'daily_avg_kwh': round(total_kwh / days, 2) if days > 0 else 0,
        'records': len(consumption)
    }

# ============= HR & STAFF MANAGEMENT =============



@router.post("/maintenance/work-orders")
async def create_maintenance_work_order(
    data: MaintenanceWorkOrder,
    current_user: User = Depends(get_current_user)
):
    """Create a new maintenance work order (from HK, Front Desk, GM, etc.)"""
    payload = data.model_dump()
    payload.update({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'reported_by_user_id': data.reported_by_user_id or current_user.id,
        'reported_by_role': data.reported_by_role or current_user.role,
        'created_at': datetime.now(UTC).isoformat(),
        'status': data.status or 'open',
    })
    await db.maintenance_work_orders.insert_one(payload)
    return payload




@router.get("/maintenance/work-orders")
async def get_maintenance_work_orders(
    status: str | None = None,
    room_id: str | None = None,
    priority: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """List maintenance work orders with basic filters"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if room_id:
        query['room_id'] = room_id
    if priority:
        query['priority'] = priority

    items = await db.maintenance_work_orders.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    return {'items': items, 'count': len(items)}




@router.patch("/maintenance/work-orders/{work_order_id}")
async def update_maintenance_work_order(
    work_order_id: str,
    status: str | None = None,
    priority: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Update status/priority of a maintenance work order"""
    updates: dict = {}
    if status:
        updates['status'] = status
        if status == 'completed':
            updates['completed_at'] = datetime.now(UTC)
    if priority:
        updates['priority'] = priority

    if not updates:
        return {'updated': False}

    result = await db.maintenance_work_orders.update_one(
        {'tenant_id': current_user.tenant_id, 'id': work_order_id},
        {'$set': updates}
    )

    return {'updated': result.modified_count == 1}


@router.post("/engineering/sensor-alerts")
async def ingest_sensor_alert(
    alert: SensorAlert,
    current_user: User = Depends(get_current_user)
):
    """Receive IoT sensor alert and optionally create maintenance work order

    Bu endpoint, BMS/IoT sistemlerinden gelen uyarıları alır ve
    belirlenen metrik ve eşiklere göre otomatik bakım iş emri üretebilir.
    """
    tenant_id = current_user.tenant_id

    payload = alert.model_dump()
    payload.update({
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'created_at': datetime.now(UTC).isoformat(),
    })

    await db.sensor_alerts.insert_one(payload)

    # Basit kural motoru: belirli metrik ve severity için otomatik ticket
    auto_created_work_order = None

    metric = alert.metric
    severity = alert.severity
    threshold_breached = alert.threshold_breached

    should_create = False
    issue_type = 'other'
    priority = 'normal'

    if metric in ['water_leak', 'flood'] and (threshold_breached or severity in ['high', 'critical']):
        should_create = True
        issue_type = 'plumbing'
        priority = 'urgent'
    elif metric == 'temperature' and alert.value > 28 and severity in ['warning', 'high', 'critical']:
        should_create = True
        issue_type = 'hvac'
        priority = 'high'
    elif metric == 'humidity' and alert.value > 80 and severity in ['warning', 'high', 'critical']:
        should_create = True
        issue_type = 'hvac'
        priority = 'high'

    if should_create:
        wo_data = MaintenanceWorkOrder(
            room_id=alert.room_id,
            room_number=alert.room_number,
            issue_type=issue_type,
            priority=priority,
            source='sensor',
            description=alert.message or f"Sensor alert from {alert.sensor_id} ({metric}={alert.value})"
        )
        wo_payload = wo_data.model_dump()
        wo_payload.update({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'reported_by_user_id': current_user.id,
            'reported_by_role': current_user.role,
            'created_at': datetime.now(UTC).isoformat(),
            'status': 'open',
        })
        await db.maintenance_work_orders.insert_one(wo_payload)
        auto_created_work_order = wo_payload

    return {
        'ingested': True,
        'sensor_alert_id': payload['id'],
        'auto_created_work_order': auto_created_work_order,
    }



@router.post("/maintenance/mobile/technician-task")
async def technician_submit_task(
    task_id: str,
    status: str,  # started, completed, needs_parts
    notes: str | None = None,
    time_spent_minutes: int | None = None,
    parts_used: list[dict] | None = None,
    photo_urls: list[str] | None = None,
    current_user: User = Depends(get_current_user)
):
    """Mobile technician app - submit task update"""
    task = await db.maintenance_tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = {
        'status': status,
        'updated_at': datetime.now(UTC).isoformat()
    }

    if status == 'completed':
        updates['completed_at'] = datetime.now(UTC).isoformat()
        updates['completed_by'] = current_user.name

    if time_spent_minutes:
        updates['time_spent_minutes'] = time_spent_minutes

    if notes:
        updates['technician_notes'] = notes

    if parts_used:
        updates['parts_used'] = parts_used

    if photo_urls:
        updates['photo_urls'] = photo_urls

    await db.maintenance_tasks.update_one(
        {'id': task_id},
        {'$set': updates}
    )

    return {
        'success': True,
        'task_id': task_id,
        'message': f'Task {status}',
        'updates': updates
    }




@router.get("/maintenance/repeat-issues")
async def get_repeat_issues(
    days: int = 90,
    min_occurrences: int = 3,
    current_user: User = Depends(get_current_user)
):
    """
    Detect repeat issues
    - Same room, same issue type multiple times
    - Preventive maintenance needed
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    # Get all maintenance tasks in period
    tasks = []
    async for task in db.maintenance_tasks.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        tasks.append(task)

    # Group by room + issue type
    issue_groups = {}
    for task in tasks:
        room_id = task.get('room_id')
        issue_type = task.get('issue_type', 'general')
        key = f"{room_id}_{issue_type}"

        if key not in issue_groups:
            issue_groups[key] = {
                'room_id': room_id,
                'issue_type': issue_type,
                'occurrences': [],
                'total_cost': 0
            }

        issue_groups[key]['occurrences'].append({
            'date': task.get('created_at'),
            'description': task.get('description')
        })
        issue_groups[key]['total_cost'] += task.get('cost', 0)

    # Filter repeat issues
    repeat_issues = []
    for key, data in issue_groups.items():
        if len(data['occurrences']) >= min_occurrences:
            # Get room details
            room = await db.rooms.find_one({'id': data['room_id']})

            repeat_issues.append({
                'room_number': room.get('room_number') if room else 'Unknown',
                'room_id': data['room_id'],
                'issue_type': data['issue_type'],
                'occurrence_count': len(data['occurrences']),
                'total_cost': round(data['total_cost'], 2),
                'avg_cost_per_occurrence': round(data['total_cost'] / len(data['occurrences']), 2),
                'first_occurrence': data['occurrences'][0]['date'],
                'last_occurrence': data['occurrences'][-1]['date'],
                'recommendation': 'Schedule preventive maintenance or consider equipment replacement'
            })

    # Sort by occurrence count
    repeat_issues.sort(key=lambda x: x['occurrence_count'], reverse=True)

    return {
        'period_days': days,
        'min_occurrences': min_occurrences,
        'total_repeat_issues': len(repeat_issues),
        'repeat_issues': repeat_issues,
        'total_cost_all_repeats': round(sum(r['total_cost'] for r in repeat_issues), 2)
    }




@router.get("/maintenance/sla-metrics")
async def get_maintenance_sla(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """
    SLA measurement for maintenance
    - Average completion time
    - SLA compliance rate
    - By priority level
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    # SLA targets (in hours)
    sla_targets = {
        'urgent': 2,
        'high': 4,
        'normal': 24,
        'low': 72
    }

    # Get completed tasks
    tasks = []
    async for task in db.maintenance_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        tasks.append(task)

    # Calculate SLA metrics by priority
    sla_by_priority = {}
    for priority in ['urgent', 'high', 'normal', 'low']:
        priority_tasks = [t for t in tasks if t.get('priority') == priority]

        if not priority_tasks:
            continue

        completion_times = []
        sla_met_count = 0

        for task in priority_tasks:
            created = datetime.fromisoformat(task.get('created_at'))
            completed = datetime.fromisoformat(task.get('completed_at'))
            hours = (completed - created).total_seconds() / 3600
            completion_times.append(hours)

            if hours <= sla_targets[priority]:
                sla_met_count += 1

        avg_completion = sum(completion_times) / len(completion_times) if completion_times else 0
        sla_compliance = (sla_met_count / len(priority_tasks) * 100) if priority_tasks else 0

        sla_by_priority[priority] = {
            'priority': priority,
            'sla_target_hours': sla_targets[priority],
            'total_tasks': len(priority_tasks),
            'avg_completion_hours': round(avg_completion, 1),
            'sla_met_count': sla_met_count,
            'sla_compliance_pct': round(sla_compliance, 1),
            'status': '✅ Good' if sla_compliance >= 90 else '⚠️ Needs Improvement' if sla_compliance >= 70 else '❌ Poor'
        }

    # Overall metrics
    total_tasks = len(tasks)
    total_sla_met = sum(m['sla_met_count'] for m in sla_by_priority.values())
    overall_compliance = (total_sla_met / total_tasks * 100) if total_tasks > 0 else 0

    return {
        'period_days': days,
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'overall_metrics': {
            'total_tasks': total_tasks,
            'sla_met': total_sla_met,
            'sla_compliance_pct': round(overall_compliance, 1)
        },
        'by_priority': list(sla_by_priority.values())
    }


@router.get("/maintenance/parts-inventory")
async def get_maintenance_parts_inventory(
    category: str | None = None,
    low_stock_only: bool = False,
    current_user: User = Depends(get_current_user),
):
    """List spare parts inventory for the maintenance team."""
    query: dict = {'tenant_id': current_user.tenant_id}
    if category:
        query['category'] = category
    parts = await db.maintenance_parts.find(query, {'_id': 0}).sort('name', 1).to_list(2000)
    if low_stock_only:
        parts = [p for p in parts if (p.get('stock') or 0) < (p.get('min_stock') or 0)]
    return {'parts': parts, 'count': len(parts)}


@router.post("/maintenance/parts-inventory")
async def create_or_update_part(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """Create or upsert a maintenance spare part."""
    if not payload.get('name'):
        raise HTTPException(status_code=400, detail='name is required')
    part = {
        'id': payload.get('id') or str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': payload.get('name'),
        'category': payload.get('category') or 'Genel',
        'stock': int(payload.get('stock') or 0),
        'min_stock': int(payload.get('min_stock') or 0),
        'unit_price': float(payload.get('unit_price') or 0),
        'unit': payload.get('unit') or 'adet',
        'location': payload.get('location') or '',
        'updated_at': datetime.now(UTC).isoformat(),
    }
    await db.maintenance_parts.update_one(
        {'tenant_id': current_user.tenant_id, 'id': part['id']},
        {'$set': part, '$setOnInsert': {'created_at': part['updated_at']}},
        upsert=True,
    )
    return part


@router.get("/maintenance/tasks")
@cached(ttl=180, key_prefix="maintenance_tasks")  # Cache for 3 min
async def get_maintenance_tasks(current_user: User = Depends(get_current_user)):
    """Get all maintenance tasks"""
    try:
        tasks = await db.maintenance_tasks.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(1000)
        return tasks
    except Exception as e:
        logger.info(f"Maintenance tasks error: {str(e)}")


@router.post("/maintenance/assets")
async def create_maintenance_asset(
    data: MaintenanceAsset,
    current_user: User = Depends(get_current_user)
):
    asset = data.model_copy(update={
        'tenant_id': current_user.tenant_id,
        'id': str(uuid.uuid4()),
    })
    await db.maintenance_assets.insert_one(asset.model_dump())
    return asset




@router.get("/maintenance/assets")
async def list_maintenance_assets(
    asset_type: str | None = None,
    room_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if asset_type:
        query['asset_type'] = asset_type
    if room_id:
        query['room_id'] = room_id

    items = await db.maintenance_assets.find(query, {'_id': 0}).to_list(1000)
    return {'items': items, 'count': len(items)}




@router.post("/maintenance/plans")
async def create_preventive_plan(
    data: PreventiveMaintenancePlan,
    current_user: User = Depends(get_current_user)
):
    plan = data.model_copy(update={
        'tenant_id': current_user.tenant_id,
        'id': str(uuid.uuid4()),
    })
    await db.maintenance_plans.insert_one(plan.model_dump())
    return plan




@router.get("/maintenance/plans")
async def list_preventive_plans(
    asset_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if asset_id:
        query['asset_id'] = asset_id

    items = await db.maintenance_plans.find(query, {'_id': 0}).to_list(1000)
    return {'items': items, 'count': len(items)}




@router.post("/maintenance/plans/run-scheduler")
async def run_preventive_maintenance_scheduler(
    current_user: User = Depends(get_current_user)
):
    """Trigger preventive maintenance scheduler

    - Finds plans where next_due_date <= today and is_active
    - Creates maintenance work orders for due plans
    - Updates last_completed_date and next_due_date
    """
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    now.date()

    due_plans_cursor = db.maintenance_plans.find({
        'tenant_id': tenant_id,
        'is_active': True,
        'next_due_date': {'$lte': now.isoformat()}
    }, {'_id': 0})

    created_orders = []

    async for plan in due_plans_cursor:
        asset = None
        if plan.get('asset_id'):
            asset = await db.maintenance_assets.find_one({
                'tenant_id': tenant_id,
                'id': plan['asset_id']
            }, {'_id': 0})

        room_id = asset.get('room_id') if asset else None
        room_number = asset.get('room_number') if asset else None

        wo_data = MaintenanceWorkOrder(
            asset_id=plan.get('asset_id'),
            plan_id=plan.get('id'),
            room_id=room_id,
            room_number=room_number,
            issue_type=plan.get('default_issue_type', 'other'),
            priority=plan.get('default_priority', 'normal'),
            source='preventive_plan',
            description=plan.get('description') or f"Preventive maintenance for plan {plan.get('id')}"
        )
        wo_payload = wo_data.model_dump()
        wo_payload.update({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'reported_by_user_id': current_user.id,
            'reported_by_role': current_user.role,
            'created_at': now.isoformat(),
            'status': 'open',
        })

        await db.maintenance_work_orders.insert_one(wo_payload)
        created_orders.append(wo_payload)

        # Calculate next_due_date
        freq_type = plan.get('frequency_type')
        freq_val = plan.get('frequency_value', 0)
        next_due = now
        if freq_type == 'days':
            next_due = now + timedelta(days=freq_val)
        elif freq_type == 'weeks':
            next_due = now + timedelta(weeks=freq_val)
        elif freq_type == 'months':
            # Approximate months as 30 days
            next_due = now + timedelta(days=30 * freq_val)

        await db.maintenance_plans.update_one(
            {'tenant_id': tenant_id, 'id': plan['id']},
            {'$set': {
                'last_completed_date': now.isoformat(),
                'next_due_date': next_due.isoformat(),
            }}
        )

    return {
        'created_count': len(created_orders),
        'orders': created_orders,
    }


# 3. GET /api/corporate/rates - Contract rates

